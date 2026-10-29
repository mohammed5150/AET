---
id: 20261030-session-protocol
title: Session protocol
tags: [orientation, process]
created: 2026-10-30
updated: 2026-10-30
related: [20261030-run-checks, 20261030-repo-map]
summary: What to read at the start of a session and what to record before finishing.
---

# Session protocol

> Summary: What to read at the start of a session and what to record before finishing.

## Context
The repository improves from one session to the next only if each session
leaves behind what it learned. This routine is short so that it gets followed.

## Start
1. Read `knowledge-base/INDEX.md` (CLAUDE.md loads it automatically).
2. Read the newest two or three entries in `WORKLOG.md`, including their
   **Open** items.
3. Open the lesson notes for the area you will change.
4. Run `scripts/check.sh` once to confirm the baseline before editing.

## Finish
1. Run `scripts/check.sh`; do not report work as done unless it passes.
2. Add a `WORKLOG.md` entry at the top: changed, verified (command and
   result), open items, lessons.
3. Record a lesson note when something surprised you, cost time, broke, or
   contradicted the docs. One lesson per note, with the evidence and the rule.
4. If a module was added, moved or renamed, update the
   [repository map](repo-map.md).
5. If a lesson shows that AGENTS.md, README or CONTRIBUTING is wrong, fix that
   file in the same change and say so in the lesson.
6. Register every new note in `INDEX.md` and its `_topic.md`.

## What makes a good lesson
- **What happened**, in one or two sentences.
- **Evidence**: file and line, test name, PR number, or command output.
- **Rule**: what to do next time, stated as an instruction.

## Related
- [Running the checks](run-checks.md) — prerequisite: steps 4 and Finish 1 use it.
- [Repository map](repo-map.md) — see-also: updated at Finish 4.
