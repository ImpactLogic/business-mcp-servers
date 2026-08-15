"""
Notes server.

The write-then-read-back tests are the point: a tool that reports success
but does not persist is the failure mode this repo exists to catch, and
asserting on `success` alone would not have caught any of these.
"""

import json

import pytest


def test_create_then_read_back(notes):
    created = notes.create_note(title="Alpha", content="first body")
    assert created["success"]

    fetched = notes.get_note(created["note_id"])
    assert fetched["success"]
    assert fetched["note"]["title"] == "Alpha"
    assert fetched["note"]["content"] == "first body"


def test_created_note_appears_in_list(notes):
    notes.create_note(title="Alpha", content="body")
    listed = notes.list_notes()
    assert listed["count"] == 1
    assert listed["notes"][0]["title"] == "Alpha"


def test_export_returns_the_notes_that_exist(notes):
    """Regression: export_notes returned count 0 with notes on disk."""
    notes.create_note(title="Alpha", content="a")
    notes.create_note(title="Beta", content="b")

    exported = notes.export_notes()

    assert exported["success"]
    assert exported["count"] == 2, "export reported success while returning nothing"
    assert {n["title"] for n in exported["notes"]} == {"Alpha", "Beta"}


def test_export_specific_ids(notes):
    first = notes.create_note(title="Alpha", content="a")["note_id"]
    notes.create_note(title="Beta", content="b")

    exported = notes.export_notes(note_ids=[first])

    assert exported["count"] == 1
    assert exported["notes"][0]["title"] == "Alpha"


def test_export_markdown_renders_content(notes):
    """Regression: the markdown branch was a stub returning an empty list."""
    notes.create_note(title="Alpha", content="the body text", tags=["x"])

    exported = notes.export_notes(format="markdown")

    assert exported["success"]
    assert exported["count"] == 1
    assert "# Alpha" in exported["markdown"]
    assert "the body text" in exported["markdown"]


def test_export_rejects_unknown_format(notes):
    assert not notes.export_notes(format="pdf")["success"]


def test_export_rejects_traversal(notes):
    """The path-traversal fix must cover export too."""
    result = notes.export_notes(note_ids=["../../etc/passwd"])
    assert not result["success"]


@pytest.mark.parametrize("note_id", ["../secrets", "..", "a/b", "a\\b", ""])
def test_traversal_is_rejected_everywhere(notes, note_id):
    for tool in (notes.get_note, notes.delete_note):
        assert not tool(note_id)["success"]


def test_tags_persist_to_disk(notes):
    """add_tags must survive a re-read, not just echo the tags back."""
    note_id = notes.create_note(title="Alpha", content="a")["note_id"]

    notes.add_tags(note_id, ["architecture"])

    assert notes.get_note(note_id)["note"]["tags"] == ["architecture"]


def test_tags_persist_when_note_has_no_tags_key(notes):
    """A note written without a "tags" key must still accept tags."""
    note_id = notes.create_note(title="Alpha", content="a")["note_id"]
    path = notes.NOTES_STORE / f"{note_id}.json"
    stored = json.loads(path.read_text())
    del stored["tags"]
    path.write_text(json.dumps(stored))

    notes.add_tags(note_id, ["recovered"])

    assert notes.get_note(note_id)["note"]["tags"] == ["recovered"]


def test_tags_are_not_duplicated(notes):
    note_id = notes.create_note(title="Alpha", content="a", tags=["x"])["note_id"]
    notes.add_tags(note_id, ["x", "y"])
    assert notes.get_note(note_id)["note"]["tags"] == ["x", "y"]


def test_limit_applies_after_sorting(notes):
    """Regression: limit truncated before sorting, so sort_by ordered a slice."""
    for title in ("Alpha", "Beta", "Gamma"):
        notes.create_note(title=title, content="x")

    listed = notes.list_notes(limit=1, sort_by="title")

    assert listed["count"] == 1
    assert listed["notes"][0]["title"] == "Gamma", "sorted only a truncated slice"


def test_rapid_creates_do_not_overwrite_each_other(notes):
    """
    Regression: note IDs used second-resolution timestamps, so notes created
    in the same second collided and the later one silently overwrote the
    earlier. Found by this suite, not by inspection.
    """
    ids = {
        notes.create_note(title=f"n{i}", content=str(i))["note_id"] for i in range(25)
    }

    assert len(ids) == 25, "note IDs collided; earlier notes were overwritten"
    assert notes.list_notes(limit=100)["count"] == 25


def test_delete_removes_the_note(notes):
    note_id = notes.create_note(title="Alpha", content="a")["note_id"]
    assert notes.delete_note(note_id)["success"]
    assert not notes.get_note(note_id)["success"]
    assert notes.list_notes()["count"] == 0


def test_search_finds_content(notes):
    notes.create_note(title="Alpha", content="database schema notes")
    notes.create_note(title="Beta", content="unrelated")

    found = notes.search_notes("schema")

    assert found["count"] == 1
    assert found["notes"][0]["title"] == "Alpha"


def test_get_tags_counts_across_notes(notes):
    notes.create_note(title="A", content="a", tags=["x", "y"])
    notes.create_note(title="B", content="b", tags=["x"])

    assert notes.get_tags()["tags"] == {"x": 2, "y": 1}


def test_import_note_round_trips(notes):
    imported = notes.import_note(content="imported body", title="Imported")
    assert imported["success"]
    assert notes.get_note(imported["note_id"])["note"]["content"] == "imported body"


def test_store_is_not_the_working_directory(notes, tmp_path):
    """Regression: NOTES_STORE was a bare relative path against the CWD."""
    assert notes.NOTES_STORE.is_absolute()
    assert notes.NOTES_STORE == tmp_path / "notes"
