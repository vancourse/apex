"""lanes.toml: which checks a diff needs, declared once, read by the laptop and by CI.

The same file answers two questions on two machines:

* on the laptop, ``rails check`` runs the lanes the diff selects;
* in CI, the verifier demands a ``success`` status for exactly those lanes on
  the head SHA.

So "what ran locally" and "what CI demands" cannot drift apart: they are one
function of one file. CI reads the file from the PR's BASE branch when it
exists there, so a PR cannot weaken its own requirement by editing it.

Schema::

    [settings]
    base = "origin/master"            # the diff is HEAD against merge-base(HEAD, base)
    status_prefix = "rails/"          # commit status context = prefix + lane name
    all_lanes_on = ["rails/lanes.toml"]   # a change here selects every lane
    gate_workflow = "pr-gate.yml"     # re-run by `rails post` if it finished before the statuses landed

    [[lane]]
    name = "suite"
    always = false                    # true: selected on every diff
    paths = ["apps/**", "*.py"]       # globs over repo-relative POSIX paths
    paths_ignore = ["**/*.md"]
    command = ["uv", "run", "pytest", "-q"]   # argv, never a shell string
    env = { DATABASE_URL = "..." }
    timeout_min = 20
    quick = false                     # included in `rails check --quick`
    needs = ["postgres"]              # prerequisites: docker | postgres | node | pnpm | uv
    advisory_until = "2026-10-20"     # optional: runs and reports, gates nothing, until this date
    lock = "suite"                    # optional: wait for this machine-wide lock first; the wait is outside timeout_min

Globs: ``**`` spans any number of path segments (including none), ``*`` and
``?`` stay inside one segment, a trailing ``/`` matches everything under that
directory. Stdlib only — this module is also run by the CI verifier.
"""

from __future__ import annotations

import datetime as _dt
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

#: A lane lock's name: it becomes a file name in the rails store, so a plain word only.
LOCK_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


@dataclass
class Lane:
    name: str
    command: list[str] = field(default_factory=list)
    always: bool = False
    paths: list[str] = field(default_factory=list)
    paths_ignore: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_min: float = 30
    quick: bool = False
    needs: list[str] = field(default_factory=list)
    advisory_until: str = ""  # ISO date: runs and reports, but gates nothing, until then
    # A machine-wide lock taken before the lane runs: every worktree and repo on the box
    # whose lane names the same lock runs it one at a time. Empty: no lock.
    lock: str = ""

    def advisory(self, today: "_dt.date | None" = None) -> bool:
        """True while this lane is advisory. A lane that has never been green on the
        machine that runs it reports before it gates, and only until a fixed date:
        an advisory lane with no date is a reporting job nobody reads."""
        if not self.advisory_until:
            return False
        today = today or _dt.date.today()
        try:
            return today < _dt.date.fromisoformat(self.advisory_until)
        except ValueError:
            return False


@dataclass
class LaneConfig:
    lanes: list[Lane]
    base: str = "origin/main"
    status_prefix: str = "rails/"
    all_lanes_on: list[str] = field(default_factory=list)
    gate_workflow: str = ""  # the PR workflow file `rails post` re-runs when it finished early

    def lane(self, name: str) -> Lane:
        for lane in self.lanes:
            if lane.name == name:
                return lane
        raise KeyError(name)

    def context(self, lane: Lane | str) -> str:
        return self.status_prefix + (lane if isinstance(lane, str) else lane.name)


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    pattern = pattern.strip().removeprefix("./")
    if pattern.endswith("/"):
        pattern += "**"
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)


def parse(data: dict[str, Any]) -> LaneConfig:
    settings = data.get("settings", {})
    lanes = []
    seen = set()
    for raw in data.get("lane", []):
        name = raw["name"]
        if name in seen:
            raise ValueError(f"lane {name!r} declared twice")
        seen.add(name)
        command = raw.get("command", [])
        if isinstance(command, str):
            raise ValueError(
                f"lane {name!r}: command must be an argv list, not a shell string"
            )
        lock = str(raw.get("lock", ""))
        if lock and not LOCK_NAME.fullmatch(lock):
            raise ValueError(
                f"lane {name!r}: lock {lock!r} must be a plain word "
                "(letters, digits, '.', '_' or '-', at most 64)"
            )
        lanes.append(
            Lane(
                name=name,
                command=[str(part) for part in command],
                always=bool(raw.get("always", False)),
                paths=list(raw.get("paths", [])),
                paths_ignore=list(raw.get("paths_ignore", [])),
                env={str(k): str(v) for k, v in raw.get("env", {}).items()},
                timeout_min=float(raw.get("timeout_min", 30)),
                quick=bool(raw.get("quick", False)),
                needs=list(raw.get("needs", [])),
                advisory_until=str(raw.get("advisory_until", "")),
                lock=lock,
            )
        )
    return LaneConfig(
        lanes=lanes,
        base=settings.get("base", "origin/main"),
        status_prefix=settings.get("status_prefix", "rails/"),
        all_lanes_on=list(settings.get("all_lanes_on", [])),
        gate_workflow=str(settings.get("gate_workflow", "")),
    )


def load(path: Path) -> LaneConfig:
    with open(path, "rb") as handle:
        return parse(tomllib.load(handle))


def loads(text: str) -> LaneConfig:
    return parse(tomllib.loads(text))


@dataclass
class Selection:
    selected: list[Lane]
    skipped: list[tuple[Lane, str]]  # (lane, reason)


def select(config: LaneConfig, changed: list[str], *, quick: bool = False) -> Selection:
    """The lanes a diff touching `changed` needs, with a reason for every skip."""
    changed = [p.replace("\\", "/") for p in changed]
    everything = any(_matches(p, config.all_lanes_on) for p in changed)
    selected: list[Lane] = []
    skipped: list[tuple[Lane, str]] = []
    for lane in config.lanes:
        if quick and not lane.quick:
            skipped.append((lane, "not a --quick lane"))
            continue
        if lane.always or everything:
            selected.append(lane)
            continue
        hits = [
            p
            for p in changed
            if _matches(p, lane.paths) and not _matches(p, lane.paths_ignore)
        ]
        if hits:
            selected.append(lane)
        else:
            skipped.append((lane, "no changed path matches its globs"))
    return Selection(selected=selected, skipped=skipped)
