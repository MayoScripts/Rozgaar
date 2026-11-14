"""Where rozgaar keeps your data. Nothing personal is ever stored in the repo.

Everything lives under one directory, ``~/.rozgaar`` by default, overridable
with ``--home`` or the ``ROZGAAR_HOME`` environment variable:

    ~/.rozgaar/
        profile.yaml    your profile (created by `rozgaar init`)
        rozgaar.db      postings, grades, cached JD parses
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def profile(self) -> Path:
        return self.home / "profile.yaml"

    @property
    def db(self) -> Path:
        return self.home / "rozgaar.db"


def resolve_paths(home: str | None = None) -> Paths:
    root = home or os.getenv("ROZGAAR_HOME") or Path.home() / ".rozgaar"
    return Paths(Path(root).expanduser())


def example_profile_text() -> str:
    return resources.files("rozgaar").joinpath("data/profile.example.yaml").read_text("utf-8")
