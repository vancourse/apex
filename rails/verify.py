"""The PR gate: does the head SHA carry a green `rails/<lane>` status for every lane its diff needs?

Runs inside GitHub Actions (``actions/verify-lanes``), stdlib only, no checkout
needed: the PR's changed files, the lanes file and the statuses all come from
the REST API. Billed time is the job's spin-up plus a few API calls.

**Which lanes.toml.** The BASE branch's copy when it has one, so a PR cannot
drop a lane from its own requirement by editing the file; the head's copy only
when the base has none (the adoption PR).

**Waiting.** `rails post` usually lands the statuses within seconds of the push,
before the runner starts. If one is still missing the gate polls for
``RAILS_WAIT_SECONDS`` (default 90), then fails naming the command that
discharges it. `rails post` re-runs a gate that finished early.

Exit 0 = every required lane is `success` on the head SHA with a tree that
matches the commit; 1 = something missing, failed or mismatched; 2 = could not look.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rails import lanes as lanes_mod  # noqa: E402

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
LANES_FILES = ("rails/lanes.toml", "lanes.toml")


class Api:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo

    def get(self, path: str):
        url = path if path.startswith("http") else f"{API}/repos/{self.repo}/{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def file_at(self, path: str, ref: str) -> str | None:
        try:
            body = self.get(f"contents/{path}?ref={ref}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        return base64.b64decode(body["content"]).decode("utf-8")

    def changed_files(self, number: int) -> list[str] | None:
        files: list[str] = []
        for page in range(1, 31):
            batch = self.get(f"pulls/{number}/files?per_page=100&page={page}")
            for item in batch:
                files.append(item["filename"])
                if item.get("previous_filename"):
                    files.append(item["previous_filename"])
            if len(batch) < 100:
                return files
        return None  # 3,000+ files: the API stops listing; treat as "every lane"

    def statuses(self, sha: str) -> dict[str, dict]:
        """Latest status per context (the API lists newest first)."""
        latest: dict[str, dict] = {}
        for page in range(1, 11):
            batch = self.get(f"commits/{sha}/statuses?per_page=100&page={page}")
            for item in batch:
                latest.setdefault(item["context"], item)
            if len(batch) < 100:
                break
        return latest

    def tree_of(self, sha: str) -> str:
        return self.get(f"git/commits/{sha}")["tree"]["sha"]


def required(
    config: lanes_mod.LaneConfig, changed: list[str] | None
) -> list[lanes_mod.Lane]:
    if changed is None:
        return list(config.lanes)
    return lanes_mod.select(config, changed).selected


def evaluate(config, needed, statuses, tree_sha) -> tuple[list[str], list[str]]:
    """(problems, satisfied) for the required lanes against the statuses seen."""
    problems, ok = [], []
    for lane in needed:
        ctx = config.context(lane)
        st = statuses.get(ctx)
        if st is None:
            problems.append(f"{ctx}: missing")
        elif st["state"] != "success":
            problems.append(f"{ctx}: {st['state']} ({st.get('description') or ''})")
        elif f"tree={tree_sha[:12]}" not in (st.get("description") or ""):
            problems.append(
                f"{ctx}: success, but for another tree ({st.get('description')})"
            )
        else:
            ok.append(ctx)
    return problems, ok


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("INPUT_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not (token and repo and event_path):
        print(
            "verify-lanes: GITHUB_TOKEN, GITHUB_REPOSITORY and GITHUB_EVENT_PATH are required"
        )
        return 2
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pr = event.get("pull_request")
    if not pr:
        print("verify-lanes: not a pull_request event; nothing to verify")
        return 0
    api = Api(token, repo)
    number = pr["number"]
    head_sha = pr["head"]["sha"]
    base_sha = pr["base"]["sha"]
    text, source = None, ""
    for rel in LANES_FILES:
        text = api.file_at(rel, base_sha)
        if text is not None:
            source = f"{rel}@base"
            break
    if text is None:
        for rel in LANES_FILES:
            text = api.file_at(rel, head_sha)
            if text is not None:
                source = f"{rel}@head (base has none: adoption PR)"
                break
    if text is None:
        print("verify-lanes: no lanes file on base or head; nothing can be verified")
        return 1
    config = lanes_mod.loads(text)
    changed = api.changed_files(number)
    needed = required(config, changed)
    tree_sha = api.tree_of(head_sha)
    print(
        f"verify-lanes: PR #{number} head {head_sha[:12]} tree {tree_sha[:12]}; lanes from {source}"
    )
    print(
        f"  {len(changed) if changed is not None else '3000+'} changed file(s); required: {', '.join(l.name for l in needed) or '(none)'}"
    )
    wait = float(os.environ.get("RAILS_WAIT_SECONDS", "90"))
    deadline = time.monotonic() + wait
    while True:
        statuses = api.statuses(head_sha)
        problems, ok = evaluate(config, needed, statuses, tree_sha)
        hard = [p for p in problems if not p.endswith(": missing")]
        if not problems or hard or time.monotonic() > deadline:
            break
        time.sleep(10)
    for ctx in ok:
        print(f"  ok       {ctx}")
    for problem in problems:
        print(f"  PROBLEM  {problem}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### rails lanes for {head_sha[:12]}\n\n")
            for ctx in ok:
                fh.write(f"- ok `{ctx}`\n")
            for problem in problems:
                fh.write(f"- **{problem}**\n")
    if problems:
        print()
        print("The laptop has not proven this commit. On the branch, run:")
        print(
            "    rails check --post        (or: python <rails>/bin/rails check --post)"
        )
        print(
            "A status for another tree means the commit changed after the check: re-run it."
        )
        return 1
    print("verify-lanes: every required lane is green on this commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
