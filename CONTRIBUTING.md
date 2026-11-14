# Contributing

Issues and pull requests are welcome.

- Run `pytest` and `ruff check . && ruff format --check .` before opening a PR.
  The test suite is fully offline; please keep it that way (use the fakes in
  `tests/conftest.py` rather than real HTTP).
- New sources go in `src/rozgaar/sources/`, subclass `Source`, and register in
  `sources/__init__.py`. Public, unauthenticated APIs only.
- Never commit personal data: real names, contact details, resumes, or a real
  `profile.yaml`. Use the fictional example profile in tests.
- Skill vocabulary changes go in `taxonomy.py`; add a test when you add an
  alias that could plausibly collide with an ordinary word.
