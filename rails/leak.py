"""Does text about to leave the box hold one of the household's REAL values? (design R31)

Generalised from Purser's `leak_check` (#2527), which found what a `$`-shaped
scanner missed: amounts without a `$`, a `.mjs` file nobody opened, and names.
This module keeps that matcher and changes two things:

* **The values are a snapshot, not a live query.** ``rails snapshot`` (run from
  the operator's own shell) reads the store once and writes SALTED HASHES of the
  distinctive values to ``<store>/<repo>/snapshot/snapshot.json``. Checking needs
  no database, so a dead Docker never stops a push, and the snapshot file holds
  no plaintext value.
* **It is keyed on destination, not verb.** The same check runs on pushed lines
  and commit messages (pre-push), on any `gh` call carrying a body or title, and
  on subagent prompts (the dispatcher's ``leak_dispatch`` gate).

Exit codes, distinct on purpose:

====  ==========================================================
0     looked, nothing found
3     FOUND (a value matched) - the code every caller refuses on
4     could not look: no snapshot, or one older than 14 days
====  ==========================================================

Output never contains a value: ``path:line kind line_id`` only.

Matching (unchanged from Purser): an **amount** is 100 or more with cents,
plain (``1234.56``) or grouped (``1,234.56``); a **word** (booking id or
descriptor) is matched whole on token boundaries after squashing to upper-case
letters and digits, inside a run that a quote, comma, bracket, colon or pipe
ends — so ``SQ *SOME PLACE`` matches the key ``SOMEPLACE`` and
``SOMEPLACEHOLDER`` does not.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import secrets
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator

from rails import store

EXIT_CLEAN, EXIT_USAGE, EXIT_FOUND, EXIT_COULD_NOT_LOOK = 0, 2, 3, 4
MAX_AGE_DAYS = 14

_TOKEN = re.compile(r"[A-Za-z0-9]+")
_GROUPED = re.compile(r"(?<=\d),(?=\d{3})")
_BREAK = re.compile(r"[\"`,;:=()\[\]{}<>|\\]")
_AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+\.\d\d|\d{3,}\.\d\d)(?!\d)")
MIN_WORD = 6
MAX_TOKENS_PER_RUN = 48

Line = tuple[str, int, str]


def squash(text: str) -> str:
    return "".join(_TOKEN.findall(text)).upper()


def _h(salt: str, value: str) -> str:
    return hashlib.sha256((salt + "\0" + value).encode("utf-8")).hexdigest()[:24]


def line_id(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:12]


@dataclass
class Snapshot:
    salt: str
    amounts: frozenset[str]  # hashes of plain-form amounts ("1234.56")
    words: dict[str, str]  # hash of squashed word -> kind
    created: float
    read_as: str = ""

    @property
    def age_days(self) -> float:
        return (time.time() - self.created) / 86400

    def has_amount(self, plain: str) -> bool:
        return _h(self.salt, plain) in self.amounts

    def word_kind(self, squashed: str) -> str | None:
        return self.words.get(_h(self.salt, squashed))


def snapshot_path(repo: store.RepoId) -> Path:
    return repo.dir / "snapshot" / "snapshot.json"


def load_snapshot(repo: store.RepoId) -> Snapshot | None:
    data = store.read_json(snapshot_path(repo))
    if not isinstance(data, dict):
        return None
    try:
        return Snapshot(
            salt=data["salt"],
            amounts=frozenset(data["amounts"]),
            words=dict(data["words"]),
            created=float(data["created"]),
            read_as=str(data.get("read_as", "")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def build_snapshot(amounts: Iterable[str], words: dict[str, str], read_as: str) -> dict:
    salt = secrets.token_hex(16)
    plain_amounts = set()
    for raw in amounts:
        try:
            value = abs(Decimal(str(raw))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except InvalidOperation:
            continue
        if value >= 100 and value % 1 != 0:
            plain_amounts.add(str(value))
    return {
        "salt": salt,
        "created": time.time(),
        "read_as": read_as,
        "amounts": sorted(_h(salt, a) for a in plain_amounts),
        "words": {_h(salt, w): kind for w, kind in words.items()},
        "counts": {"amount": len(plain_amounts), **_count(words)},
    }


def _count(words: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for kind in words.values():
        out[kind] = out.get(kind, 0) + 1
    return out


def scan(lines: Iterable[Line], snap: Snapshot) -> list[tuple[str, int, str, str]]:
    """Every (path, line, kind, line_id) whose text holds a snapshot value."""
    hits = []
    for path, number, text in lines:
        kinds: set[str] = set()
        for m in _AMOUNT.finditer(text):
            if snap.has_amount(m.group(1).replace(",", "")):
                kinds.add("amount")
        for run in _BREAK.split(_GROUPED.sub("", text)):
            tokens = [t.upper() for t in _TOKEN.findall(run)][:MAX_TOKENS_PER_RUN]
            if not tokens:
                continue
            bounds = [0]
            for token in tokens:
                bounds.append(bounds[-1] + len(token))
            joined = "".join(tokens)
            for i in range(len(tokens)):
                for j in range(i + 1, len(tokens) + 1):
                    width = bounds[j] - bounds[i]
                    if width < MIN_WORD:
                        continue
                    if width > 64:
                        break
                    kind = snap.word_kind(joined[bounds[i] : bounds[j]])
                    if kind:
                        kinds.add(kind)
        for kind in sorted(kinds):
            hits.append((path, number, kind, line_id(text)))
    return hits


@dataclass
class Allowance:
    path: str
    kind: str
    lines: tuple[str, ...]
    why: str

    def covers(self, path: str, kind: str, ident: str) -> bool:
        return (
            kind == self.kind
            and fnmatch.fnmatchcase(path, self.path)
            and (not self.lines or ident in self.lines)
        )


def load_allowlist(path: Path | None) -> list[Allowance]:
    if path is None or not path.is_file():
        return []
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("allow", [])
    return [
        Allowance(e["path"], e["kind"], tuple(e.get("lines", ())), e["why"])
        for e in entries
    ]


def text_lines(label: str, text: str) -> Iterator[Line]:
    for number, line in enumerate(text.splitlines(), 1):
        yield label, number, line


# --- what a push sends -------------------------------------------------------

_ZERO = "0" * 40
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _git(top: Path, *args: str) -> str | None:
    done = subprocess.run(
        ["git", "-C", str(top), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return done.stdout if done.returncode == 0 else None


def added_lines(top: Path, base: str, head: str) -> Iterator[Line]:
    diff = (
        _git(
            top,
            "-c",
            "core.quotepath=off",
            "diff",
            "-U0",
            "--no-color",
            "--no-ext-diff",
            base,
            head,
        )
        or ""
    )
    path: str | None = None
    number = 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:].rstrip("\t") if line.startswith("+++ b/") else None
        elif (hunk := _HUNK.match(line)) is not None:
            number = int(hunk.group(1))
        elif line.startswith("+") and path is not None:
            yield path, number, line[1:]
            number += 1


def commit_messages(top: Path, base: str, head: str) -> Iterator[Line]:
    log = _git(top, "log", "--format=%H%x00%B%x01", f"{base}..{head}") or ""
    for chunk in log.split("\x01"):
        if "\x00" not in chunk:
            continue
        sha, body = chunk.split("\x00", 1)
        yield from text_lines(f"commit {sha.strip()[:12]} message", body)


def pushed_lines(
    top: Path, ref_lines: Iterable[str], default_base: str
) -> Iterator[Line]:
    for ref_line in ref_lines:
        parts = ref_line.split()
        if len(parts) != 4 or parts[1] == _ZERO:
            continue
        local_sha, remote_sha = parts[1], parts[3]
        known = (
            remote_sha != _ZERO and _git(top, "cat-file", "-e", remote_sha) is not None
        )
        base = (
            remote_sha
            if known
            else (_git(top, "merge-base", default_base, local_sha) or "").strip()
        )
        if not base:
            continue
        yield from added_lines(top, base, local_sha)
        yield from commit_messages(top, base, local_sha)


# --- the one entry every caller uses ----------------------------------------


@dataclass
class Result:
    code: int
    hits: list[tuple[str, int, str, str]]
    why: str = ""

    def report(self) -> str:
        if self.code == EXIT_COULD_NOT_LOOK:
            return f"leak check could not look: {self.why}\n  refresh it from YOUR shell: rails snapshot"
        if self.code == EXIT_FOUND:
            rows = "\n".join(
                f"  {p}:{n} {k} (line {i})" for p, n, k, i in self.hits[:40]
            )
            return (
                "leak check FOUND household values (the values are never printed):\n"
                f"{rows}\n"
                "Replace them with invented values. A genuine coincidence (a national brand, an English word)\n"
                "goes in the allowlist with path, kind, line id and why - never the value."
            )
        return "leak check: clean"


def check_lines(
    repo: store.RepoId, lines: Iterable[Line], allowlist: Path | None = None
) -> Result:
    snap = load_snapshot(repo)
    if snap is None:
        return Result(EXIT_COULD_NOT_LOOK, [], "no snapshot for this repo")
    if snap.age_days > MAX_AGE_DAYS:
        return Result(
            EXIT_COULD_NOT_LOOK,
            [],
            f"the snapshot is {snap.age_days:.0f} days old (max {MAX_AGE_DAYS})",
        )
    allow = load_allowlist(allowlist)
    hits = [
        h
        for h in scan(lines, snap)
        if not any(a.covers(h[0], h[2], h[3]) for a in allow)
    ]
    return Result(EXIT_FOUND if hits else EXIT_CLEAN, hits)


def config_for(top: Path) -> dict:
    path = top / "rails" / "leak.toml"
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def allowlist_for(top: Path) -> Path | None:
    rel = config_for(top).get("allowlist")
    return (top / rel) if rel else None


# --- rails snapshot (operator shell only) -----------------------------------


def _fetcher(spec: str):
    if spec.startswith("docker://"):
        container, _, rest = spec.removeprefix("docker://").partition("/")
        user, _, database = rest.partition("/")

        def fetch(sql: str) -> list[str]:
            done = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "psql",
                    "-U",
                    user,
                    "-d",
                    database,
                    "-At",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-c",
                    sql,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
            if done.returncode != 0:
                raise RuntimeError(f"psql in {container} exited {done.returncode}")
            return [line for line in done.stdout.splitlines() if line.strip()]

        return fetch

    def fetch_dsn(sql: str) -> list[str]:
        code = (
            "import sys,psycopg\n"
            "with psycopg.connect(sys.argv[1]) as c:\n"
            "    for r in c.execute(sys.argv[2]):\n"
            "        print('' if r[0] is None else r[0])\n"
        )
        done = subprocess.run(
            [
                "uv",
                "run",
                "--quiet",
                "--no-project",
                "--with",
                "psycopg[binary]",
                "python",
                "-c",
                code,
                spec,
                sql,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        if done.returncode != 0:
            raise RuntimeError(
                "could not read the store through psycopg (DSN unreachable?)"
            )
        return [line for line in done.stdout.splitlines() if line.strip()]

    return fetch_dsn


def snapshot_main(top: Path, repo: store.RepoId, out=sys.stdout) -> int:
    from rails.gitutil import in_agent

    if in_agent():
        print(
            "rails snapshot reads the household store and runs only from YOUR shell, not an agent's.",
            file=out,
        )
        return EXIT_USAGE
    cfg = config_for(top).get("snapshot", {})
    env_name = cfg.get("store_env", "RAILS_LEAK_STORE")
    import os

    spec = os.environ.get(env_name)
    if not spec:
        print(
            f"rails snapshot: set {env_name} to the store (DSN or docker://<container>/<user>/<db>)",
            file=out,
        )
        return EXIT_USAGE
    fetch = _fetcher(spec)
    exclude = {squash(w) for w in cfg.get("exclude_words", [])}
    amounts: list[str] = []
    words: dict[str, str] = {}
    try:
        for q in cfg.get("query", []):
            rows = fetch(q["sql"])
            kind = q["kind"]
            if kind == "amount":
                amounts.extend(rows)
                continue
            for raw in rows:
                key = squash(raw)
                if (
                    len(key) < int(q.get("min_len", MIN_WORD))
                    or key in exclude
                    or key.isdigit()
                ):
                    continue
                if q.get("need_digit") and not any(c.isdigit() for c in key):
                    continue
                if words.get(key) and q.get("rank", 0) <= 0:
                    continue
                words[key] = kind
        read_as = (
            (fetch(cfg["identity_sql"]) or ["?"])[0] if cfg.get("identity_sql") else "?"
        )
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"rails snapshot: could not read the store: {exc}", file=out)
        return EXIT_COULD_NOT_LOOK
    if not amounts and not words:
        print(
            "rails snapshot: the store returned no rows (RLS with no tenant bound?) - refusing to write an empty snapshot",
            file=out,
        )
        return EXIT_COULD_NOT_LOOK
    body = build_snapshot(amounts, words, read_as)
    store.write_json(snapshot_path(repo), body)
    print(
        f"rails snapshot: wrote {body['counts']} (hashed; read as {read_as})", file=out
    )
    return EXIT_CLEAN


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="rails leak-check")
    ap.add_argument(
        "--file", action="append", default=[], help="check this file's contents"
    )
    ap.add_argument("--stdin", action="store_true", help="check text on stdin")
    ap.add_argument(
        "--pre-push", action="store_true", help="read git's pre-push ref lines on stdin"
    )
    args = ap.parse_args(argv)
    top = Path.cwd()
    repo = store.find_repo(top)
    if repo is None:
        print("rails leak-check: not inside a git checkout")
        return EXIT_USAGE
    lines: list[Line] = []
    for f in args.file:
        lines.extend(
            text_lines(f, Path(f).read_text(encoding="utf-8", errors="replace"))
        )
    if args.stdin:
        lines.extend(text_lines("<stdin>", sys.stdin.read()))
    if args.pre_push:
        from rails.check import find_lanes_file
        from rails import lanes as lanes_mod

        lanes_file = find_lanes_file(repo.top)
        base = lanes_mod.load(lanes_file).base if lanes_file else "origin/main"
        lines.extend(pushed_lines(repo.top, sys.stdin.read().splitlines(), base))
    result = check_lines(repo, lines, allowlist_for(repo.top))
    print(result.report())
    return result.code
