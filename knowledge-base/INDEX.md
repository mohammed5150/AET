# Knowledge Base — Index

Agent knowledge base for AET. It records how the repository works and what
earlier sessions learned, so each session starts from the last one.

## How to use this KB (for agents)
1. Read this index first. Pick notes by their descriptions; open only those.
2. Before changing an area, open the lesson notes tagged for it.
3. Cite the note `id` when you rely on it in a PR description or report.
4. The design documents in `docs/SDS` and `docs/ADR` govern. A note that
   disagrees with them is wrong: fix the note.

## How to update this KB (for agents)
- New idea → new atomic note. Same idea changed → edit in place and bump `updated`.
- Any create / rename / delete MUST update this registry and the topic's `_topic.md` in the same change.
- Use only tags from the controlled vocabulary below; add a new tag here before using it.
- A lesson states what happened, the evidence (file, test, PR, command output) and the rule that follows.
- Append one entry per session to `WORKLOG.md` (newest first).
- `tests/test_knowledge_base.py` enforces frontmatter, ids, tags, registry and links.

## Controlled tags
`orientation`, `process`, `tooling`, `architecture`, `engineering`, `docs`, `lesson`

## Registry
### log
- `worklog` — **Worklog** — `WORKLOG.md` — One entry per session: what changed, verification, open follow-ups.

### orientation
- `20261030-repo-map` — **Repository map** — `topics/orientation/repo-map.md` — Where each pipeline stage, model and service lives, with its governing SDS.
- `20261030-run-checks` — **Running the checks** — `topics/orientation/run-checks.md` — The one command that reproduces CI locally, and the baseline it should report.
- `20261030-session-protocol` — **Session protocol** — `topics/orientation/session-protocol.md` — What to read at the start of a session and what to record before finishing.

### lessons
- `20261030-agents-md-drift` — **AGENTS.md drifted from the code** — `topics/lessons/agents-md-drift.md` — AGENTS.md described an app/ package and a develop branch that no longer exist; which files govern instead.
- `20261030-no-shipped-limits` — **No engineering limit is shipped** — `topics/lessons/no-shipped-limits.md` — Never hardcode a spacing, loading or photometric value; why, and where criteria belong.
- `20261030-editable-install` — **Editable install is required** — `topics/lessons/editable-install.md` — The src/ layout means tests and the CLI need `pip install -e ".[dev]"` first.
- `20261030-reference-documents` — **Reference documents are never committed** — `topics/lessons/reference-documents.md` — AET records where a standard is, never the document itself.
