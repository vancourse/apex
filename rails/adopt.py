"""`rails adopt` (a repo) and `rails enable` (the operator's machine).

rails adopt [--retire-push-consent]
    In the current repo: point core.hooksPath at the plugin's git-hooks and record
    the previous hooks directory in rails.chainHooksPath, so the repo's own hooks
    keep running; add `.rails/` to .git/info/exclude. With --retire-push-consent,
    a local pre-push that refuses every push without JARVIS_PUSH_OK is renamed
    aside (decision 13.2: `hold` is the only push word). Idempotent.

rails enable
    Once per machine, from the operator's shell: register this checkout as the
    `rails` plugin marketplace (directory source: it loads in place for every
    worktree), enable `rails@rails`, disable the old `apex@apex`, record the
    plugin home, install `rails` / `rails.cmd` shims into ~/.local/bin, then
    adopt the current repo. Backs up ~/.claude/settings.json first. Refuses
    inside an agent's tool call: it changes what every session loads.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = PLUGIN_ROOT / "git-hooks"


def _git(top: Path, *args: str, check: bool = False) -> str:
    done = subprocess.run(
        ["git", "-C", str(top), *args], capture_output=True, text=True
    )
    if check and done.returncode != 0:
        raise RuntimeError(done.stderr.strip())
    return done.stdout.strip()


def adopt(top: Path, *, retire_push_consent: bool = False, out=sys.stdout) -> int:
    current = _git(top, "config", "--get", "core.hooksPath")
    ours = str(HOOKS_DIR).replace("\\", "/")
    if current and Path(current).resolve() != HOOKS_DIR.resolve():
        prev = (
            current if Path(current).is_absolute() else str((top / current).resolve())
        )
        _git(top, "config", "rails.chainHooksPath", prev.replace("\\", "/"), check=True)
        print(
            f"  chained: the repo's previous hooks ({prev}) still run after rails's",
            file=out,
        )
    elif not current:
        common = _git(top, "rev-parse", "--git-common-dir")
        common_path = Path(common) if Path(common).is_absolute() else (top / common)
        _git(
            top,
            "config",
            "rails.chainHooksPath",
            str((common_path / "hooks").resolve()).replace("\\", "/"),
            check=True,
        )
    _git(top, "config", "core.hooksPath", ours, check=True)
    print(f"  core.hooksPath -> {ours}", file=out)
    common = _git(top, "rev-parse", "--git-common-dir")
    common_path = Path(common) if Path(common).is_absolute() else (top / common)
    exclude = common_path / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if ".rails/" not in existing.splitlines():
        with open(exclude, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(
                ("\n" if existing and not existing.endswith("\n") else "") + ".rails/\n"
            )
        print("  .rails/ added to .git/info/exclude", file=out)
    if retire_push_consent:
        main_root = common_path.parent
        for hook in (
            main_root / ".githooks" / "pre-push",
            common_path / "hooks" / "pre-push",
        ):
            try:
                text = hook.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "JARVIS_PUSH_OK" in text:
                aside = hook.with_name(
                    f"pre-push.retired-by-rails-{time.strftime('%Y%m%d')}"
                )
                hook.rename(aside)
                print(
                    f"  push consent retired: {hook} -> {aside.name} (decision 13.2: `hold` is the only word)",
                    file=out,
                )
    print("rails adopt: done", file=out)
    return 0


def _settings_path() -> Path:
    return (
        Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
        / "settings.json"
    )


def enable(top: Path | None, *, out=sys.stdout) -> int:
    if os.environ.get("CLAUDECODE") == "1":
        print(
            "rails enable changes what every session loads; run it from YOUR shell, not an agent's.",
            file=out,
        )
        return 2
    settings_path = _settings_path()
    settings = (
        json.loads(settings_path.read_text(encoding="utf-8"))
        if settings_path.exists()
        else {}
    )
    backup = settings_path.with_name(
        f"settings.json.before-rails-{time.strftime('%Y%m%d-%H%M%S')}"
    )
    if settings_path.exists():
        shutil.copy2(settings_path, backup)
        print(f"  backed up {settings_path.name} -> {backup.name}", file=out)
    markets = settings.setdefault("extraKnownMarketplaces", {})
    markets["rails"] = {"source": {"source": "directory", "path": str(PLUGIN_ROOT)}}
    plugins = settings.setdefault("enabledPlugins", {})
    plugins["rails@rails"] = True
    if "apex@apex" in plugins:
        plugins["apex@apex"] = False
        print("  apex@apex disabled (rails replaces it)", file=out)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"  rails@rails enabled from {PLUGIN_ROOT}", file=out)
    home = Path.home() / ".claude" / "rails"
    home.mkdir(parents=True, exist_ok=True)
    (home / "home").write_text(str(PLUGIN_ROOT), encoding="utf-8")
    bindir = Path.home() / ".local" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    rails_py = (PLUGIN_ROOT / "bin" / "rails").as_posix()
    (bindir / "rails").write_text(
        f'#!/bin/sh\nexec python3 "{rails_py}" "$@"\n', encoding="utf-8", newline="\n"
    )
    (bindir / "rails.cmd").write_text(
        f'@echo off\r\npython3 "{PLUGIN_ROOT / "bin" / "rails"}" %*\r\n',
        encoding="utf-8",
        newline="",
    )
    try:
        os.chmod(bindir / "rails", 0o755)
    except OSError:
        pass
    print(f"  shims: {bindir / 'rails'} and rails.cmd", file=out)
    if top is not None:
        adopt(top, retire_push_consent=True, out=out)
    print(
        "rails enable: done. Restart Claude Code sessions to load the plugin.", file=out
    )
    return 0


def main(argv: list[str], *, command: str) -> int:
    ap = argparse.ArgumentParser(prog=f"rails {command}")
    if command == "adopt":
        ap.add_argument("--retire-push-consent", action="store_true")
    args = ap.parse_args(argv)
    top_out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    ).stdout.strip()
    top = Path(top_out) if top_out else None
    if command == "enable":
        return enable(top)
    if top is None:
        print("rails adopt: not inside a git checkout")
        return 2
    return adopt(top, retire_push_consent=args.retire_push_consent)
