"""PreToolUse hook: route an artifact being authored to the template that shapes it.

One table, two moments. When a session creates a PRD, design, impl-plan, ADR or
recon brief, the matching skeleton is injected before the write. When a session
shells out to `gh pr create` / `gh issue create`, the repo's own `.github/`
template is checked against the body actually being submitted, and the *missing
sections are named*.

Skeletons resolve **repo first, plugin second**: a repo's own
`docs/templates/<name>` wins if it exists, otherwise apex's shipped
`templates/<name>` is used. So the hook is useful the moment apex is installed,
and a repo that has decided its own shape keeps it.

**Why the `gh` half exists at all.** GitHub applies `.github/` templates only in
its web UI. `gh pr create --body-file …` supplies the body directly and skips them
entirely — which is how an agent files nearly every PR and issue. So the templates
this repo already has are, for the one actor that files most of its artifacts,
decorative. That is the hole this closes.

Adding a new artifact type is one row in `DOC_RULES` plus a file in `templates/`.
That is the point: the shape of the repo's documents stops being something a human
has to restate per feature.

**Issue forms need no row at all.** `.github/ISSUE_TEMPLATE/` holds more than one —
a defect form and a work-item form, with different fields — and which one applies is
a property of the command, not of the repo. So the forms are discovered at run time
and selected by the `--template` / `--label` / title-prefix signals each one
*declares about itself*. A new form is routed the moment it is added.

That replaces a hardcoded `work-item.yml`, which checked every issue against the
work-item fields and so reported a correctly-formed **defect** as missing all seven
of them. The lesson generalises past the routing: the message now always names the
template it chose *and why*, because a check that is confidently wrong and cannot
be interrogated teaches the reader to ignore it — the same failure this hook's
`--body-file` handling was fixed for once already.

Advisory by construction — it injects context, never denies. It does not check the
*content* of a section, only that the section exists; a hook cannot judge whether a
threat model is any good, and pretending otherwise would trade a real signal for a
ceremonial one.
"""

from __future__ import annotations

import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hooklib import (  # noqa: E402
    command_key,
    emit,
    fail_open,
    find_repo_root,
    flag_values,
    headings,
    invocation_index,
    plugin_root,
    read_payload,
    relative_to_root,
    run,
    submitted_body,
    warn_once,
)


@dataclass(frozen=True)
class DocRule:
    """A document whose shape is decided, matched by where it lives and what it is called."""

    id: str
    #: Template filename, resolved repo-first then plugin — see `_resolve_template`.
    template: str
    #: Required leading path segments, e.g. ("docs", "adr").
    root: tuple[str, ...]
    #: Exact filenames; None means "any .md under root".
    names: frozenset[str] | None
    #: Filenames under root that are indexes or logs, never instances of the artifact.
    exclude: frozenset[str]
    why: str


DOC_RULES: tuple[DocRule, ...] = (
    DocRule(
        id="prd",
        template="prd.md",
        root=("docs",),
        names=frozenset({"prd.md"}),
        exclude=frozenset(),
        why="A PRD freezes at apex:prd-review Pass 7. Its numbered scenarios are what "
        "the impl-plan's integration tests mirror 1:1, so they are load-bearing, not prose.",
    ),
    DocRule(
        id="design",
        template="design.md",
        root=("docs",),
        names=frozenset({"design.md"}),
        exclude=frozenset(),
        why="A design must either USE the primitives recon found or justify why each "
        "cannot be extended. Record that verdict here — the PR template asks for it again.",
    ),
    DocRule(
        id="impl-plan",
        template="impl-plan.md",
        root=("docs",),
        names=frozenset({"impl-plan.md"}),
        exclude=frozenset(),
        why="A layered PR stack (one layer each, small), sequenced foundation -> UI, with "
        "a rollout and a rollback per layer.",
    ),
    DocRule(
        id="recon",
        template="recon.md",
        root=("docs",),
        names=frozenset({"recon.md"}),
        exclude=frozenset(),
        why="Every question the design must answer needs a verdict: an authoritative "
        "primitive with its CONTRACT, or a justified 'genuinely new'.",
    ),
    DocRule(
        id="adr",
        template="adr.md",
        root=("docs", "adr"),
        names=None,
        exclude=frozenset({"README.md", "DECISION_LOG.md"}),
        why="Five elements. Keep rejected ADRs in the tree, unedited, with a post-mortem "
        "rather than deleting them — a rejection is the record that an option was priced.",
    ),
)


@dataclass(frozen=True)
class GhRule:
    """A `gh` subcommand that files an artifact and can silently skip its template."""

    id: str
    #: The exact consecutive tokens that invoke it, e.g. ("gh", "issue", "create").
    invocation: tuple[str, ...]
    template: str
    #: True when the template is a GitHub YAML issue form rather than markdown.
    is_form: bool
    why: str
    #: Directory of interchangeable forms, when the repo offers more than one and the
    #: command chooses between them. `template` is then only the fallback.
    form_dir: str | None = None


GH_RULES: tuple[GhRule, ...] = (
    GhRule(
        id="pr",
        invocation=("gh", "pr", "create"),
        template=".github/pull_request_template.md",
        is_form=False,
        why="`--body`/`--body-file` bypasses the PR template GitHub would have pre-filled.",
    ),
    GhRule(
        id="issue",
        invocation=("gh", "issue", "create"),
        template=".github/ISSUE_TEMPLATE/work-item.yml",
        is_form=True,
        why="`--body`/`--body-file` bypasses the issue form GitHub would have rendered.",
        form_dir=".github/ISSUE_TEMPLATE",
    ),
)

_FORM_LABEL = re.compile(r"^\s+label:\s*(?P<label>.+?)\s*$", re.MULTILINE)

#: Top-level keys of a GitHub issue form. Column 0 distinguishes them from the
#: per-field `label:` above, which is always indented under `body:`.
_FORM_NAME = re.compile(r"^name:\s*(?P<value>.+?)\s*$", re.MULTILINE)
_FORM_TITLE = re.compile(r"^title:\s*(?P<value>.+?)\s*$", re.MULTILINE)
_FORM_LABELS_INLINE = re.compile(r"^labels:\s*\[(?P<value>.*?)\]\s*$", re.MULTILINE)
_FORM_LABELS_BLOCK = re.compile(
    r"^labels:\s*$\n(?P<value>(?:\s+-\s*.+\n?)+)", re.MULTILINE
)


def _unquote(value: str) -> str:
    return value.strip().strip("\"'").strip()


@dataclass(frozen=True)
class IssueForm:
    """One `.github/ISSUE_TEMPLATE/*.yml`, plus the signals that select it.

    The selectors are read from the form itself rather than restated here, so a new
    form is routed correctly the moment it is added — no hook edit, which is the
    same bargain `DOC_RULES` makes for authored documents.
    """

    #: Repo-relative path, e.g. ".github/ISSUE_TEMPLATE/defect.yml".
    path: str
    #: File stem, which is what `gh issue create --template` names.
    filename: str
    #: The form's display name, e.g. "Defect".
    name: str
    #: Labels the form applies, e.g. {"defect"} — matched against `--label`.
    labels: frozenset[str]
    #: Title prefix the form seeds, e.g. "[defect] " — matched against `--title`.
    title_prefix: str


def _parse_issue_form(path: Path, relative: str) -> IssueForm | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not _FORM_LABEL.search(text):
        # No field labels means nothing to check a body against — `config.yml`.
        return None

    labels: set[str] = set()
    if inline := _FORM_LABELS_INLINE.search(text):
        labels = {_unquote(p) for p in inline.group("value").split(",") if p.strip()}
    elif block := _FORM_LABELS_BLOCK.search(text):
        labels = {
            _unquote(line.strip().lstrip("-"))
            for line in block.group("value").splitlines()
            if line.strip()
        }

    name = _FORM_NAME.search(text)
    title = _FORM_TITLE.search(text)
    return IssueForm(
        path=relative,
        filename=path.name,
        name=_unquote(name.group("value")) if name else path.stem,
        labels=frozenset(lab for lab in labels if lab),
        title_prefix=_unquote(title.group("value")) if title else "",
    )


def _discover_issue_forms(root: Path, rule: GhRule) -> list[IssueForm]:
    if rule.form_dir is None:
        return []
    directory = root / rule.form_dir
    forms = []
    for path in sorted(directory.glob("*.y*ml")):
        form = _parse_issue_form(path, f"{rule.form_dir}/{path.name}")
        if form is not None:
            forms.append(form)
    return forms


def _select_issue_form(
    tokens: list[str], start: int, forms: list[IssueForm], rule: GhRule
) -> tuple[str, str]:
    """Which form this command is really filing: `(repo-relative path, why)`.

    The reason is returned, not discarded, because it is what makes a wrong route
    self-diagnosing. This check once reported a correctly-formed **defect** as
    missing all seven *work-item* fields, and the message gave no clue it had
    picked the wrong form — a false positive that reads as the author's mistake
    trains the reader to ignore the check, which is worse than not checking.

    Precedence follows how strongly the signal states intent: `--template` is an
    explicit choice, a label is a deliberate classification, a title prefix is a
    convention. Nothing matching falls back to the rule's default, said out loud.
    """
    by_file = {form.filename: form for form in forms}

    for value in flag_values(tokens, start, ("--template", "-T")):
        candidate = Path(value).name
        for filename, form in by_file.items():
            if candidate in (filename, Path(filename).stem):
                return form.path, f"`--template {value}` names it"

    requested = {
        value.strip().lower() for value in flag_values(tokens, start, ("--label", "-l"))
    }
    for form in forms:
        if hit := sorted(lab for lab in form.labels if lab.lower() in requested):
            return form.path, f"`--label {hit[0]}` is the label this form applies"

    for value in flag_values(tokens, start, ("--title", "-t")):
        for form in forms:
            if form.title_prefix and value.startswith(form.title_prefix):
                return form.path, f"the title starts with `{form.title_prefix}`"

    others = [form.path for form in forms if form.path != rule.template]
    hint = f" (the other forms here: {', '.join(others)})" if others else ""
    return (
        rule.template,
        "no `--template`, `--label` or title prefix matched, so this is the default"
        + hint,
    )


def _resolve_template(root: Path, name: str) -> tuple[Path, str] | None:
    """Locate a doc skeleton: `(path, repo-relative-or-plugin label)`.

    Repo first, plugin second. A repo that has decided its own shape for an
    artifact keeps it; every other repo gets apex's the moment the plugin is
    installed. Returning the label as well as the path matters because the
    injected message names where the shape came from — a reader who disagrees
    with it needs to know which file to edit.
    """
    local = root / "docs" / "templates" / name
    if local.is_file():
        return local, f"docs/templates/{name}"
    shipped = plugin_root() / "templates" / name
    if shipped.is_file():
        return shipped, f"apex's templates/{name}"
    return None


def _matching_doc_rule(rel: Path) -> DocRule | None:
    for rule in DOC_RULES:
        if rel.parts[: len(rule.root)] != rule.root:
            continue
        if rel.name in rule.exclude:
            continue
        if rule.names is None:
            if rel.suffix == ".md" and len(rel.parts) == len(rule.root) + 1:
                return rule
        elif rel.name in rule.names:
            return rule
    return None


def _required_sections(root: Path, relative: str, is_form: bool) -> list[str]:
    """The section names the given template asks for.

    Takes the resolved template rather than the rule, because for issues *which*
    template applies is a per-command decision (see `_select_issue_form`).
    """
    path = root / relative
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if is_form:
        return [m.group("label") for m in _FORM_LABEL.finditer(text)]
    return [
        line.strip().lstrip("#").strip()
        for line in text.splitlines()
        if line.strip().startswith("#")
    ]


def _render_doc(rel: Path, rule: DocRule, template: str, source: str) -> str:
    return "\n".join(
        [
            f"ARTIFACT TEMPLATE — you are creating a {rule.id.upper()}: {rel.as_posix()}",
            "",
            f"There is a decided shape for it, at {source}. Use these headings",
            "so the freeze chain and its reviews line up across features:",
            "",
            template.rstrip(),
            "",
            "-" * 74,
            rule.why,
            "",
            "Fill every section or delete it with a reason. An empty heading is worse than",
            "an absent one — it reads as answered.",
        ]
    )


def _render_gh(
    rule: GhRule,
    template: str,
    chosen_because: str,
    required: list[str],
    submitted: tuple[str, str] | None,
) -> str | None:
    if submitted is None:
        # No body flag: gh opens an editor pre-filled with the template. Nothing to say.
        return None

    kind, value = submitted
    lines = [
        f"TEMPLATE CHECK — `gh {rule.id} create` with an explicit body.",
        "",
        rule.why,
        # Always name the template AND why it was picked. When the route is wrong,
        # this line is the whole difference between "the check is broken" and a
        # reader silently concluding their correct body was malformed.
        f"Checked against {template} — {chosen_because}.",
        "",
    ]

    if kind == "unreadable":
        # Say what is not known. Never guess the sections are absent.
        return "\n".join(
            lines
            + [
                f"Could not read the body file ({value}) — most likely the path contains a",
                "shell variable, which is still unexpanded when a hook sees the command.",
                "",
                "So this is NOT a report that anything is missing. Confirm yourself that the",
                "body carries these sections:",
                *(f"  - {name}" for name in required),
            ]
        )

    present = set(headings(value))
    missing = [s for s in required if s.strip().rstrip(":").lower() not in present]

    if not missing:
        lines += [
            "Your body already carries every section it asks for. Nothing to change —",
            "this is confirmation, not a request.",
        ]
    else:
        lines += [
            f"Sections in the template that your body does NOT have ({len(missing)}):"
        ]
        lines += [f"  - {name}" for name in missing]
        lines += [
            "",
            "Add them, or drop the ones that genuinely do not apply and say why. The",
            "template exists so a reviewer is told the intent instead of reconstructing",
            "it from the diff.",
        ]
    return "\n".join(lines)


def _handle_write(payload: dict, session: str) -> None:
    raw_path = payload.get("tool_input", {}).get("file_path")
    if not raw_path:
        fail_open()

    target = Path(str(raw_path))
    if target.suffix != ".md" or target.exists():
        fail_open()

    root = find_repo_root(target.parent)
    if root is None:
        fail_open()
    rel = relative_to_root(target, root)
    if rel is None:
        fail_open()

    rule = _matching_doc_rule(rel)
    if rule is None or warn_once(session, f"doc-{rule.id}-{rel.as_posix()}"):
        fail_open()

    resolved = _resolve_template(root, rule.template)
    if resolved is None:
        fail_open()
    path, source = resolved

    try:
        template = path.read_text(encoding="utf-8")
    except OSError:
        fail_open()

    emit(_render_doc(rel, rule, template, source))


def _handle_bash(payload: dict, session: str) -> None:
    command = str(payload.get("tool_input", {}).get("command", ""))
    if not command:
        fail_open()

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        fail_open()

    match = next(
        (
            (rule, index)
            for rule in GH_RULES
            if (index := invocation_index(tokens, rule.invocation)) is not None
        ),
        None,
    )
    if match is None:
        fail_open()
    rule, start = match

    root = find_repo_root(Path(str(payload.get("cwd") or Path.cwd())))
    if root is None:
        fail_open()

    forms = _discover_issue_forms(root, rule)
    if forms:
        template, chosen_because = _select_issue_form(tokens, start, forms, rule)
    else:
        template, chosen_because = rule.template, "the only template for this artifact"

    required = _required_sections(root, template, rule.is_form)
    if not required:
        fail_open()

    context = _render_gh(
        rule, template, chosen_because, required, submitted_body(command, root, start)
    )
    # Keyed on the command so a corrected retry is checked again rather than muted.
    if context is None or warn_once(session, f"gh-{rule.id}-{command_key(command)}"):
        fail_open()
    emit(context)


def main() -> None:
    payload = read_payload()
    session = str(payload.get("session_id", "nosession"))
    tool = payload.get("tool_name")

    if tool == "Write":
        _handle_write(payload, session)
    elif tool == "Bash":
        _handle_bash(payload, session)
    fail_open()


if __name__ == "__main__":
    run(main)
