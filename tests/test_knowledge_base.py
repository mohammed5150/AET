"""Structural checks for the agent knowledge base in ``knowledge-base/``.

The knowledge base is how one working session hands its lessons to the next.
These tests keep it navigable: every note has complete frontmatter, a stable
unique id, controlled tags, a registry entry and a topic-map entry, and every
link points at a file that exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KB = Path(__file__).resolve().parent.parent / "knowledge-base"
INDEX = KB / "INDEX.md"
REQUIRED = ("id", "title", "tags", "created", "updated", "related", "summary")
ID_RE = re.compile(r"^\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REGISTRY_RE = re.compile(r"^- `([^`]+)` — \*\*(.+?)\*\* — `([^`]+)` — (.+)$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _notes() -> list[Path]:
    return sorted(p for p in (KB / "topics").rglob("*.md") if p.name != "_topic.md")


def _frontmatter(path: Path) -> dict[str, str | list[str]]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path}: missing frontmatter block"
    data: dict[str, str | list[str]] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        assert sep, f"{path}: frontmatter line without a colon: {line!r}"
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            data[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            data[key.strip()] = value
    return data


def _controlled_tags() -> set[str]:
    text = INDEX.read_text(encoding="utf-8")
    section = text.split("## Controlled tags", 1)[1].split("##", 1)[0]
    return set(re.findall(r"`([^`]+)`", section))


def _registry() -> dict[str, tuple[str, str]]:
    entries: dict[str, tuple[str, str]] = {}
    section = INDEX.read_text(encoding="utf-8").split("## Registry", 1)[1]
    for line in section.splitlines():
        match = REGISTRY_RE.match(line)
        if match:
            note_id, title, rel, _ = match.groups()
            assert note_id not in entries, f"registry lists {note_id} twice"
            entries[note_id] = (title, rel)
    return entries


def test_index_exists_and_has_entries() -> None:
    assert INDEX.is_file()
    assert _registry(), "INDEX.md registry is empty or malformed"


@pytest.mark.parametrize("path", _notes(), ids=lambda p: p.stem)
def test_note_frontmatter_is_complete(path: Path) -> None:
    meta = _frontmatter(path)
    missing = [k for k in REQUIRED if not meta.get(k) and k != "related"]
    assert not missing, f"{path.name}: missing {missing}"
    note_id = str(meta["id"])
    assert ID_RE.match(note_id), f"{path.name}: id {note_id!r} is not YYYYMMDD-slug"
    assert note_id.split("-", 1)[1] == path.stem, f"{path.name}: slug != filename"
    assert DATE_RE.match(str(meta["created"]))
    assert DATE_RE.match(str(meta["updated"]))
    assert str(meta["updated"]) >= str(meta["created"])
    unknown = set(meta["tags"]) - _controlled_tags()
    assert not unknown, f"{path.name}: tags not in INDEX.md: {sorted(unknown)}"
    body = path.read_text(encoding="utf-8")
    assert f"\n# {meta['title']}\n" in body, f"{path.name}: H1 must match title"


def test_ids_are_unique() -> None:
    ids = [str(_frontmatter(p)["id"]) for p in _notes()]
    assert len(ids) == len(set(ids))


def test_registry_matches_notes_on_disk() -> None:
    registry = _registry()
    for _, rel in registry.values():
        assert (KB / rel).is_file(), f"registry path missing: {rel}"
    by_path = {rel: note_id for note_id, (_, rel) in registry.items()}
    for path in _notes():
        rel = path.relative_to(KB).as_posix()
        assert rel in by_path, f"{rel} is not registered in INDEX.md"
        meta = _frontmatter(path)
        assert by_path[rel] == meta["id"], f"{rel}: registry id != frontmatter id"
        assert registry[by_path[rel]][0] == meta["title"], f"{rel}: title differs"


def test_related_ids_exist() -> None:
    ids = {str(_frontmatter(p)["id"]) for p in _notes()}
    for path in _notes():
        unknown = set(_frontmatter(path)["related"]) - ids
        assert not unknown, f"{path.name}: unknown related ids {sorted(unknown)}"


def test_every_note_is_in_its_topic_map() -> None:
    for path in _notes():
        topic_map = path.parent / "_topic.md"
        assert topic_map.is_file(), f"{path.parent.name}: missing _topic.md"
        text = topic_map.read_text(encoding="utf-8")
        assert f"({path.name})" in text, f"{path.name} not linked from _topic.md"


def test_relative_links_resolve() -> None:
    for path in sorted(KB.rglob("*.md")):
        for target in LINK_RE.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path.relative_to(KB)}: broken link {target}"
