"""SQLite persistence for postings, their grades, and a small AI cache.

A posting moves through a deliberately small set of statuses, all set by
you:

    new -> shortlisted -> applied
       \\-> dismissed

``closed_at`` is set by the pipeline when a posting disappears from its
board, so you can tell live openings from stale ones.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from rozgaar.models import Fit, ParsedJD, Posting

STATUSES = ("new", "shortlisted", "applied", "dismissed")
GRADE_ORDER = "CASE grade WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 3 ELSE 2 END"

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    id            TEXT PRIMARY KEY,
    url           TEXT NOT NULL UNIQUE,
    source        TEXT NOT NULL,
    board         TEXT NOT NULL,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    location      TEXT,
    description   TEXT,
    salary_text   TEXT,
    posted_on     TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    closed_at     TEXT,
    grade         TEXT,
    fit_score     REAL,
    fit           TEXT,
    parsed        TEXT,
    brief         TEXT,
    status        TEXT NOT NULL DEFAULT 'new',
    notes         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_postings_board  ON postings(source, board);
CREATE INDEX IF NOT EXISTS idx_postings_grade  ON postings(grade);
CREATE INDEX IF NOT EXISTS idx_postings_status ON postings(status);

CREATE TABLE IF NOT EXISTS ai_cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory = sqlite3.connect(":memory:") if str(path) == ":memory:" else None
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """One connection per operation, always closed (a leaked connection
        per call exhausts file descriptors on long scrapes)."""
        if self._memory is not None:
            self._memory.row_factory = sqlite3.Row
            with self._memory:
                yield self._memory
            return
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # -- postings --------------------------------------------------------

    def known_urls(self) -> set[str]:
        with self._conn() as c:
            return {r[0] for r in c.execute("SELECT url FROM postings")}

    def has_open_twin(self, posting: Posting) -> bool:
        """Same company + title already open under another URL (boards often
        repost one role per location)."""
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM postings WHERE company = ? AND title = ? AND url != ? "
                "AND closed_at IS NULL LIMIT 1",
                (posting.company, posting.title, posting.url),
            ).fetchone()
            return row is not None

    def touch(self, urls: list[str]) -> None:
        """Mark already-stored postings as still present on their board."""
        if not urls:
            return
        now = _now()
        with self._conn() as c:
            c.executemany(
                "UPDATE postings SET last_seen_at = ?, closed_at = NULL WHERE url = ?",
                [(now, u) for u in urls],
            )

    def close_missing(self, source: str, board: str, seen_urls: set[str]) -> int:
        """Flag postings from this board that weren't in the latest fetch."""
        now = _now()
        with self._conn() as c:
            rows = c.execute(
                "SELECT url FROM postings WHERE source = ? AND board = ? AND closed_at IS NULL",
                (source, board),
            ).fetchall()
            gone = [(now, r[0]) for r in rows if r[0] not in seen_urls]
            c.executemany("UPDATE postings SET closed_at = ? WHERE url = ?", gone)
            return len(gone)

    def add(self, p: Posting, parsed: ParsedJD | None, fit: Fit, brief: dict) -> None:
        now = _now()
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO postings
                   (id, url, source, board, company, title, location, description,
                    salary_text, posted_on, first_seen_at, last_seen_at,
                    grade, fit_score, fit, parsed, brief)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    p.id,
                    p.url,
                    p.source,
                    p.board,
                    p.company,
                    p.title,
                    p.location,
                    p.description,
                    p.salary_text,
                    p.posted_on.isoformat() if p.posted_on else None,
                    now,
                    now,
                    fit.grade,
                    fit.score,
                    json.dumps(fit.to_dict()),
                    json.dumps(parsed.to_dict()) if parsed else None,
                    json.dumps(brief),
                ),
            )

    def update_grade(self, posting_id: str, parsed: ParsedJD | None, fit: Fit, brief: dict) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE postings SET grade=?, fit_score=?, fit=?, parsed=?, brief=? WHERE id=?",
                (
                    fit.grade,
                    fit.score,
                    json.dumps(fit.to_dict()),
                    json.dumps(parsed.to_dict()) if parsed else None,
                    json.dumps(brief),
                    posting_id,
                ),
            )

    def set_status(self, id_prefix: str, status: str, note: str | None = None) -> dict | None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        row = self.get(id_prefix)
        if row is None:
            return None
        with self._conn() as c:
            if note is None:
                c.execute("UPDATE postings SET status=? WHERE id=?", (status, row["id"]))
            else:
                c.execute(
                    "UPDATE postings SET status=?, notes=? WHERE id=?", (status, note, row["id"])
                )
        return self.get(row["id"])

    def get(self, id_prefix: str) -> dict | None:
        """Look up by full id or a unique prefix (like git short hashes)."""
        if not id_prefix:
            return None
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM postings WHERE id LIKE ? LIMIT 2", (id_prefix + "%",)
            ).fetchall()
        if len(rows) != 1:
            return None
        return _decode(rows[0])

    def query(
        self,
        grades: tuple[str, ...] | None = None,
        statuses: tuple[str, ...] | None = None,
        company: str | None = None,
        include_closed: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        clauses, params = [], []
        if grades:
            wanted = [g for g in grades if g != "?"]
            parts = []
            if wanted:
                parts.append(f"grade IN ({','.join('?' * len(wanted))})")
                params.extend(wanted)
            if "?" in grades:
                parts.append("grade IS NULL")
            clauses.append("(" + " OR ".join(parts) + ")")
        if statuses:
            clauses.append(f"status IN ({','.join('?' * len(statuses))})")
            params.extend(statuses)
        if company:
            clauses.append("company LIKE ?")
            params.append(f"%{company}%")
        if not include_closed:
            clauses.append("closed_at IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM postings {where} ORDER BY {GRADE_ORDER}, fit_score DESC, posted_on DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._conn() as c:
            return [_decode(r) for r in c.execute(sql, params)]

    def stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
            open_ = c.execute("SELECT COUNT(*) FROM postings WHERE closed_at IS NULL").fetchone()[0]
            grades = dict(
                c.execute(
                    "SELECT COALESCE(grade, '?'), COUNT(*) FROM postings "
                    "WHERE closed_at IS NULL GROUP BY 1"
                ).fetchall()
            )
            statuses = dict(
                c.execute("SELECT status, COUNT(*) FROM postings GROUP BY 1").fetchall()
            )
            boards = c.execute(
                "SELECT source, board, COUNT(*) n FROM postings WHERE closed_at IS NULL "
                "GROUP BY source, board ORDER BY n DESC"
            ).fetchall()
        return {
            "total": total,
            "open": open_,
            "grades": grades,
            "statuses": statuses,
            "boards": [tuple(b) for b in boards],
        }

    # -- AI cache (implements fit.parsers.Cache) -------------------------

    def cache_get(self, key: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT value FROM ai_cache WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_set(self, key: str, value: dict) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ai_cache (key, value, created_at) VALUES (?,?,?)",
                (key, json.dumps(value), _now()),
            )

    @property
    def cache(self) -> _CacheView:
        return _CacheView(self)


class _CacheView:
    """Adapter exposing ``get``/``set`` for the parser cache protocol."""

    def __init__(self, store: Store) -> None:
        self._s = store

    def get(self, key: str) -> dict | None:
        return self._s.cache_get(key)

    def set(self, key: str, value: dict) -> None:
        self._s.cache_set(key, value)


def _decode(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in ("fit", "parsed", "brief"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    return d


def posting_from_row(row: dict) -> Posting:
    from datetime import date

    return Posting(
        source=row["source"],
        board=row["board"],
        company=row["company"],
        title=row["title"],
        url=row["url"],
        location=row.get("location") or "",
        description=row.get("description") or "",
        salary_text=row.get("salary_text") or "",
        posted_on=date.fromisoformat(row["posted_on"]) if row.get("posted_on") else None,
    )
