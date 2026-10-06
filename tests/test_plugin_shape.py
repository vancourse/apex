"""What the plugin may carry (design R1, R20, section 10). Each assertion is a deletion that must stay deleted
or a budget that must stay under its ceiling."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEPT_SKILLS = {
    "rails",
    "release",
    "fix",
    "retro",
    "adversarial-pair",
    "design-review",
    "python-review",
    "typescript-review",
    "postgres-review",
    "security-review",
}
SKILL_LISTING_BUDGET = (
    1536  # characters across every skill description the session lists
)


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path} has no frontmatter"
    out = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def test_plugin_is_named_rails():
    assert (
        json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["name"]
        == "rails"
    )
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert [p["name"] for p in market["plugins"]] == ["rails"]


def test_commands_and_rules_are_gone():
    assert not (ROOT / "commands").exists(), (
        "0 of 17 commands were typed in 241 sessions"
    )
    assert not (ROOT / "rules").exists(), (
        "rules load every session; judgment lives in the contract"
    )


def test_skills_are_exactly_the_kept_set():
    present = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
    assert present == KEPT_SKILLS


def test_skill_listing_fits_its_budget():
    total = sum(
        len(_frontmatter(ROOT / "skills" / name / "SKILL.md")["description"])
        for name in KEPT_SKILLS
    )
    assert total <= SKILL_LISTING_BUDGET, (
        f"skill descriptions total {total} chars > {SKILL_LISTING_BUDGET}"
    )


def test_only_the_dispatcher_is_registered():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    commands = [
        h["command"]
        for entries in hooks.values()
        for entry in entries
        for h in entry["hooks"]
    ]
    assert commands and all("rails_hook.py" in c for c in commands)
    shell_matchers = [e.get("matcher", "") for e in hooks["PreToolUse"]]
    assert any("Bash" in m and "PowerShell" in m for m in shell_matchers), (
        "a Bash-only matcher misses PowerShell"
    )


def test_deleted_hooks_stay_deleted():
    gone = [
        "apex-primer.sh",
        "suggest-skill-on-prompt.sh",
        "suggest-skill-on-edit.sh",
        "guard-security-paths.sh",
        "scan-secrets-on-edit.sh",
        "session-baseline.sh",
        "run-python-hook.sh",
        "session_output_gate.py",
    ]
    for name in gone:
        assert not (ROOT / "hooks" / name).exists(), name


def test_review_and_recon_agents_cannot_write():
    for name in ("recon", "reviewer-coop", "reviewer-adversary"):
        tools = _frontmatter(ROOT / "agents" / f"{name}.md")["tools"]
        assert set(t.strip() for t in tools.split(",")) == {"Read", "Grep", "Glob"}, (
            name
        )


def test_templates_are_exactly_the_five_plus_pr_and_contract():
    names = {p.name for p in (ROOT / "templates").iterdir()}
    assert names == {
        "intent.md",
        "spec.md",
        "adr.md",
        "milestone.md",
        "rulebook.md",
        "pull_request_template.md",
        "session-contract.md",
    }


def test_spec_has_the_five_sections():
    heads = re.findall(r"^## (.+)$", (ROOT / "templates" / "spec.md").read_text(), re.M)
    assert heads == ["Scenarios", "Seams", "Failure modes", "Premises", "Amendments"]


def test_milestone_step_zero_is_the_operator_using_it():
    assert (
        "**Step 0 (the operator):** the operator did"
        in (ROOT / "templates" / "milestone.md").read_text()
    )


def test_session_contract_fits_600_words_and_every_rule_names_its_enforcer():
    text = (ROOT / "templates" / "session-contract.md").read_text()
    assert len(text.split()) <= 600, len(text.split())
    body = text.split("## Judgment")[0]
    for para in [
        p for p in body.split("\n\n") if p.startswith("**") and "never" in p.lower()
    ]:
        assert "enforced by" in para or "advisory" in para, para[:80]


def test_every_git_hook_wrapper_points_at_the_dispatcher_entry():
    for hook in (ROOT / "git-hooks").iterdir():
        text = hook.read_text()
        assert (
            text.startswith("#!/bin/sh")
            and "bin/rails-githook" in text
            and f" {hook.name} " in text
        ), hook.name
