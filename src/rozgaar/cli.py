"""Command-line interface.

rozgaar init                      create ~/.rozgaar/profile.yaml from the example
rozgaar scrape                    fetch, filter and grade every board in your profile
rozgaar jobs                      list open postings, best fit first
rozgaar show <id>                 full detail for one posting
rozgaar mark <id> <status>        new | shortlisted | applied | dismissed
rozgaar regrade                   re-grade stored postings after editing your profile
rozgaar discover <company>...     find a company's Greenhouse / Lever / Ashby board
rozgaar stats                     totals by grade, status and board
rozgaar export                    CSV of postings to stdout
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import textwrap
from collections.abc import Sequence

from rozgaar import __version__
from rozgaar.config import Paths, example_profile_text, resolve_paths
from rozgaar.discover import find_boards
from rozgaar.fit import make_parser
from rozgaar.pipeline import BoardResult, regrade, scrape
from rozgaar.profile import SUPPORTED_BOARDS, Profile, ProfileError, load_profile
from rozgaar.store import STATUSES, Store

# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------


def _cut(text: str, width: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _table(rows: list[list[str]], headers: list[str], widths: list[int]) -> str:
    def line(cells: Sequence[str]) -> str:
        return "  ".join(_cut(c, w).ljust(w) for c, w in zip(cells, widths, strict=False)).rstrip()

    out = [line(headers), line(["-" * w for w in widths])]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


def _csv_arg(value: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    return tuple(v.strip() for v in value.split(",") if v.strip())


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace, paths: Paths) -> int:
    target = paths.profile
    if target.exists() and not args.force:
        print(f"Profile already exists at {target} (use --force to overwrite).")
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(example_profile_text(), encoding="utf-8")
    print(
        f"Created {target}\nEdit it with your skills, target roles and boards, "
        f"then run `rozgaar scrape`."
    )
    return 0


def _report(res: BoardResult) -> None:
    label = f"{res.source}:{res.board}"
    if res.error:
        print(f"  {label:<32} ERROR  {res.error}")
        return
    grades = " ".join(f"{g}={n}" for g, n in sorted(res.grades.items()))
    print(
        f"  {label:<32} {res.fetched:>4} fetched  {res.added:>3} new  "
        f"{res.filtered:>4} filtered  {res.closed:>3} closed  {grades}"
    )


def cmd_scrape(args: argparse.Namespace, paths: Paths, profile: Profile) -> int:
    boards = None
    if args.board:
        boards = []
        for spec in args.board:
            source, _, slug = spec.partition(":")
            if not slug:
                print(f"--board expects ats:slug (e.g. greenhouse:stripe), got {spec!r}")
                return 2
            if source.lower() not in SUPPORTED_BOARDS:
                print(f"Unknown board type {source!r}; use one of {', '.join(SUPPORTED_BOARDS)}")
                return 2
            boards.append((source.lower(), slug.lower()))
    if boards is None and not profile.boards:
        print(
            "Your profile lists no boards. Add some under `boards:` "
            "(find slugs with `rozgaar discover`)."
        )
        return 1
    store = Store(paths.db)
    parser = make_parser(profile.llm_model, store.cache, use_llm=not args.no_llm)
    print(f"Scraping with the {parser.name} parser…")
    results = scrape(profile, store, parser, boards=boards, on_board=_report)
    added = sum(r.added for r in results)
    errors = sum(1 for r in results if r.error)
    print(f"\n{added} new posting(s) stored." + (f" {errors} board(s) failed." if errors else ""))
    return 1 if errors and errors == len(results) else 0


def cmd_jobs(args: argparse.Namespace, paths: Paths) -> int:
    store = Store(paths.db)
    if args.all:
        grades, statuses = None, None
    else:
        grades = _csv_arg(args.grade) or ("A", "B", "?")
        statuses = _csv_arg(args.status) or ("new", "shortlisted")
    rows = store.query(
        grades=grades,
        statuses=statuses,
        company=args.company,
        include_closed=args.closed,
        limit=args.limit,
    )
    if not rows:
        print("No postings match. Try `rozgaar jobs --all`, or run `rozgaar scrape`.")
        return 0
    table = [
        [
            r["id"][:8],
            r["grade"] or "?",
            f"{r['fit_score']:.2f}" if r["fit_score"] is not None else "",
            r["status"],
            r["company"],
            r["title"],
            r["location"] or "",
            r["posted_on"] or "",
        ]
        for r in rows
    ]
    print(
        _table(
            table,
            ["ID", "FIT", "SCORE", "STATUS", "COMPANY", "TITLE", "LOCATION", "POSTED"],
            [8, 3, 5, 11, 18, 44, 22, 10],
        )
    )
    print(f"\n{len(rows)} posting(s). `rozgaar show <id>` for details.")
    return 0


def cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    row = Store(paths.db).get(args.id)
    if row is None:
        print(f"No unique posting matches {args.id!r}.")
        return 1
    fit = row["fit"] or {}
    brief = row["brief"] or {}
    parsed = row["parsed"] or {}
    print(f"{row['title']}  @  {row['company']}")
    print(
        f"{row['location'] or 'location n/a'}  ·  posted {row['posted_on'] or 'n/a'}  ·  "
        f"{row['source']}:{row['board']}  ·  status: {row['status']}"
        + ("  ·  CLOSED" if row["closed_at"] else "")
    )
    print(row["url"])
    print(
        f"\nFit: {row['grade'] or '?'}"
        + (f" ({row['fit_score']:.2f})" if row["fit_score"] is not None else "")
        + f"  {fit.get('reason', '')}"
    )
    if fit.get("covered"):
        print("  covered: " + ", ".join(fit["covered"]))
    if fit.get("missing"):
        print("  missing: " + ", ".join(fit["missing"]))
    if parsed:
        facts = [f"seniority {parsed.get('seniority')}", f"work mode {parsed.get('work_mode')}"]
        if parsed.get("min_years") is not None:
            facts.insert(0, f"{parsed['min_years']}+ yrs")
        print(f"  parsed by {parsed.get('parser')}: " + ", ".join(facts))
    if brief.get("lead_with"):
        print("\nLead with:")
        for item in brief["lead_with"]:
            print("  - " + textwrap.shorten(item, 110))
    if brief.get("salary_band"):
        print(f"\nPosted salary: {brief['salary_band']}")
    if row["notes"]:
        print(f"\nNotes: {row['notes']}")
    return 0


def cmd_mark(args: argparse.Namespace, paths: Paths) -> int:
    row = Store(paths.db).set_status(args.id, args.status, args.note)
    if row is None:
        print(f"No unique posting matches {args.id!r}.")
        return 1
    print(f"{row['id'][:8]}  {row['company']} — {row['title']}  ->  {row['status']}")
    return 0


def cmd_regrade(args: argparse.Namespace, paths: Paths, profile: Profile) -> int:
    store = Store(paths.db)
    parser = make_parser(profile.llm_model, store.cache, use_llm=not args.no_llm)
    counts = regrade(profile, store, parser, include_closed=args.closed)
    total = sum(counts.values())
    summary = ", ".join(f"{g}={n}" for g, n in sorted(counts.items())) or "nothing to do"
    print(f"Re-graded {total} posting(s) with {parser.name}: {summary}")
    return 0


def cmd_discover(args: argparse.Namespace, _paths: Paths) -> int:
    found: dict[str, list[str]] = {}
    for company in args.companies:
        hits = find_boards(company)
        if not hits:
            print(f"  {company:<28} no Greenhouse / Lever / Ashby board found")
        for h in hits:
            print(f"  {company:<28} {h.source}:{h.slug}  ({h.open_jobs} open)")
            found.setdefault(h.source, []).append(h.slug)
    if found:
        print("\nAdd to your profile under `boards:`")
        for source, slugs in found.items():
            print(f"  {source}: [{', '.join(slugs)}]")
    return 0


def cmd_stats(_args: argparse.Namespace, paths: Paths) -> int:
    s = Store(paths.db).stats()
    print(f"{s['open']} open posting(s), {s['total']} seen in total")
    order = ["A", "B", "?", "C"]
    print("  fit:    " + "  ".join(f"{g}={s['grades'].get(g, 0)}" for g in order))
    print("  status: " + "  ".join(f"{st}={s['statuses'].get(st, 0)}" for st in STATUSES))
    if s["boards"]:
        print("  boards: " + ", ".join(f"{src}:{b} ({n})" for src, b, n in s["boards"][:12]))
    return 0


def cmd_export(args: argparse.Namespace, paths: Paths) -> int:
    rows = Store(paths.db).query(
        grades=_csv_arg(args.grade), statuses=_csv_arg(args.status), include_closed=args.closed
    )
    fields = [
        "id",
        "grade",
        "fit_score",
        "status",
        "company",
        "title",
        "location",
        "posted_on",
        "url",
        "source",
        "board",
        "closed_at",
        "notes",
    ]
    w = csv.writer(sys.stdout)
    w.writerow([*fields, "missing"])
    for r in rows:
        w.writerow(
            [r.get(f) if r.get(f) is not None else "" for f in fields]
            + ["; ".join((r["fit"] or {}).get("missing", []))]
        )
    return 0


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rozgaar",
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"rozgaar {__version__}")
    p.add_argument("--home", help="data directory (default: $ROZGAAR_HOME or ~/.rozgaar)")
    p.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    s = sub.add_parser("init", help="create your profile from the example")
    s.add_argument("--force", action="store_true", help="overwrite an existing profile")

    s = sub.add_parser("scrape", help="fetch, filter and grade postings")
    s.add_argument(
        "--board",
        action="append",
        metavar="ATS:SLUG",
        help="scrape only this board (repeatable), e.g. greenhouse:stripe",
    )
    s.add_argument("--no-llm", action="store_true", help="use the heuristic parser only")

    s = sub.add_parser("jobs", help="list postings, best fit first")
    s.add_argument("--grade", help="comma list of A,B,C,? (default A,B,?)")
    s.add_argument("--status", help=f"comma list of {','.join(STATUSES)} (default new,shortlisted)")
    s.add_argument("--company", help="filter by company name (substring)")
    s.add_argument("--all", action="store_true", help="every grade and status")
    s.add_argument("--closed", action="store_true", help="include postings no longer listed")
    s.add_argument("-n", "--limit", type=int, default=50)

    s = sub.add_parser("show", help="details for one posting")
    s.add_argument("id", help="posting id or unique prefix")

    s = sub.add_parser("mark", help="set a posting's status")
    s.add_argument("id")
    s.add_argument("status", choices=STATUSES)
    s.add_argument("--note", help="attach a note (e.g. who referred you)")

    s = sub.add_parser("regrade", help="re-grade stored postings with your current profile")
    s.add_argument("--no-llm", action="store_true")
    s.add_argument("--closed", action="store_true", help="include closed postings")

    s = sub.add_parser("discover", help="find companies' ATS boards")
    s.add_argument("companies", nargs="+", metavar="company")

    sub.add_parser("stats", help="summary counts")

    s = sub.add_parser("export", help="CSV to stdout")
    s.add_argument("--grade")
    s.add_argument("--status")
    s.add_argument("--closed", action="store_true")
    return p


NEEDS_PROFILE = {"scrape": cmd_scrape, "regrade": cmd_regrade}
NO_PROFILE = {
    "init": cmd_init,
    "jobs": cmd_jobs,
    "show": cmd_show,
    "mark": cmd_mark,
    "discover": cmd_discover,
    "stats": cmd_stats,
    "export": cmd_export,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    paths = resolve_paths(args.home)
    try:
        if args.command in NEEDS_PROFILE:
            return NEEDS_PROFILE[args.command](args, paths, load_profile(paths.profile))
        return NO_PROFILE[args.command](args, paths)
    except ProfileError as e:
        print(f"Profile error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
