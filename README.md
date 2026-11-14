# rozgaar

*rozgaar (रोज़गार): Hindi/Urdu for "employment".*

rozgaar watches the job boards of companies you care about, drops the
postings you can't realistically land, and grades the rest on how well **you**
fit them. You end up with a short, ranked list of openings worth a tailored
application or a referral ask, instead of a firehose.

Real output from a run with the fictional example profile:

```
$ rozgaar scrape
Scraping with the heuristic-v1 parser…
  greenhouse:stripe                 766 fetched    2 new   764 filtered    0 closed  A=2
  lever:spotify                      85 fetched    0 new    85 filtered    0 closed
  ashby:ramp                        169 fetched    0 new   169 filtered    0 closed

$ rozgaar jobs
ID        FIT  SCORE  STATUS  COMPANY  TITLE                 LOCATION                 POSTED
--------  ---  -----  ------  -------  --------------------  -----------------------  ----------
b879f928  A    1.00   new     Stripe   Data Analyst, SF      San Francisco            2026-11-04
2852b4ec  A    0.85   new     Stripe   Data Analyst, Intern  New York, Seattle, So…   2026-10-29

$ rozgaar show b879
Data Analyst, SF  @  Stripe
Fit: A (1.00)  4/4 must-haves covered
  covered: stakeholder management, SQL, dashboards, ETL
Lead with:
  - Northwind Logistics: Built 12 Tableau dashboards used weekly by operations leadership
  - Northwind Logistics: Rewrote nightly SQL reporting jobs as dbt models, cutting runtime from 3h to 25m
```

## Why

Applying through aggregators means stale links, login walls, and resume
filters that never show a human your application. rozgaar goes straight to
the source: the public job-board APIs that Greenhouse, Lever and Ashby
expose for every company that uses them. Those APIs return the full job
description, so every posting can be judged on what it actually asks for.

## How it works

```
 profile.yaml ──┐
                ▼
 boards ──► fetch ──► gates ──► dedup ──► parse JD ──► grade ──► SQLite ──► jobs / show / export
          (public   (free,     (skip     (heuristic   (A/B/C/?
           APIs)    regex)     known)    or LLM,      vs your
                                         cached)      skills)
```

1. **Fetch.** Pull every open posting from each board in your profile.
2. **Gate.** Cheap, deterministic filters: target titles, seniority,
   stated years of experience, posting age, excluded phrases, blocked
   companies, and an optional US-only location check that also reads the JD
   body ("this role is based in Bengaluru").
3. **Dedup.** Postings already in the database are only marked as still
   open, and per-city reposts of the same role are stored once. Postings
   that disappear from their board are flagged closed.
4. **Parse.** Extract must-haves, nice-to-haves, years, seniority, salary
   and work mode from the JD, using either a built-in heuristic parser or a
   small Claude model. LLM results are cached by content hash, so each
   posting is paid for at most once.
5. **Grade.** Score the share of must-haves your profile covers, plus a
   small bonus for nice-to-haves:
   **A** ≥ 0.72, **B** ≥ 0.45, **C** below that or out-of-reach level, and
   **?** when there isn't enough information to grade. rozgaar never guesses
   a middling grade for a posting it couldn't read.

The ordering is deliberate: everything free runs on every posting, and the
(possibly paid) parser only sees postings that are new and pass every gate.

## Quickstart

```bash
pip install git+https://github.com/MayoScripts/rozgaar      # or: pip install -e .
rozgaar init                 # writes ~/.rozgaar/profile.yaml from the example
$EDITOR ~/.rozgaar/profile.yaml
rozgaar discover "Figma" "Datadog"  # find companies' board slugs
rozgaar scrape
rozgaar jobs
```

Optional LLM parsing (more accurate on requirements outside the built-in
skill taxonomy):

```bash
pip install 'rozgaar[llm]'
export ANTHROPIC_API_KEY=...
rozgaar scrape            # or `--no-llm` to force the heuristic parser
```

## Your profile

Everything personal lives in one YAML file **outside the repository**
(`~/.rozgaar/profile.yaml`, or `$ROZGAAR_HOME`). See
[`profile.example.yaml`](src/rozgaar/data/profile.example.yaml) for a
fictional, annotated example. It holds:

| section      | used for                                                                 |
|--------------|--------------------------------------------------------------------------|
| `skills`     | fit grading. Free text, resolved through a shared [taxonomy](src/rozgaar/taxonomy.py), so "Postgres" covers "PostgreSQL" |
| `experience` | true facts tagged with skills; `show` suggests which ones to lead with   |
| `search`     | target titles, max years, posting age, US-only, excluded phrases, blocked companies |
| `boards`     | which Greenhouse / Lever / Ashby boards to watch                         |
| `llm`        | model for optional LLM parsing                                           |

After editing your skills, `rozgaar regrade` re-scores everything already
stored. With the LLM parser, that is served from the cache.

## Commands

| command | what it does |
|---|---|
| `init` | create your profile from the example |
| `scrape [--board ats:slug] [--no-llm]` | fetch, gate, parse, grade and store |
| `jobs [--grade A,B] [--status new] [--company X] [--all] [--closed]` | ranked list (default: A, B and ungraded; new and shortlisted) |
| `show <id>` | posting detail, covered and missing requirements, what to lead with |
| `mark <id> new\|shortlisted\|applied\|dismissed [--note ...]` | track your own progress |
| `regrade [--no-llm]` | re-grade stored postings against your current profile |
| `discover <company>...` | find a company's board slug; prints a snippet for your profile |
| `stats` | counts by grade, status and board |
| `export` | CSV to stdout |

IDs accept unique prefixes, like git hashes.

## Design notes

- **Whole-word skill matching.** Substring matching makes "git" cover
  "digital", "excel" cover "excellent" and "aws" cover "laws". Every match
  in rozgaar is whole-word, symbol-aware ("c++", "a/b testing", "node.js"),
  and ambiguous names like Go and R only match through unambiguous aliases.
- **Honest grades.** No JD text or no stated requirements means `?`, not a
  default B.
- **Works without an API key.** The heuristic parser is free, offline and
  deterministic. The LLM parser is a drop-in upgrade behind the same
  interface, and it fails soft.
- **Polite by construction.** Only official public JSON endpoints are used:
  no HTML scraping, no logins, an honest User-Agent.
- **Nothing personal in code.** No names, contact details, skills or company
  preferences are hard-coded. They all come from your profile.

## Project layout

```
src/rozgaar/
  cli.py            command-line interface
  pipeline.py       fetch → gate → parse → grade → store
  filters.py        free, deterministic gates
  fit/              parsers (heuristic, Anthropic), skill matcher, grading
  sources/          Greenhouse, Lever, Ashby API clients
  discover.py       company → board slug discovery
  store.py          SQLite persistence + AI cache
  profile.py        profile schema and validation
  taxonomy.py       shared skill vocabulary + whole-word matching
tests/              offline test suite (no network, no API key needed)
```

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check . && ruff format --check .
```

## Roadmap

See [ROADMAP.md](ROADMAP.md). In short: more sources, then application
assistance, added piece by piece and only once each piece is reliable.

## License

[MIT](LICENSE)
