"""
Clipboard server.

History is exercised against a tmp_path file. The OS clipboard round-trip
is skipped rather than failed when no clipboard binary is present, since
headless Linux and CI runners genuinely have none.
"""

import json

import pytest


def _has_system_clipboard(clipboard) -> bool:
    return clipboard.get_clipboard().get("success") is True


def test_save_then_read_back(clipboard):
    saved = clipboard.save_to_history("hello world", label="greeting")
    assert saved["success"]

    history = clipboard.get_history()
    assert history["count"] == 1
    assert history["history"][0]["text"] == "hello world"


def test_history_persists_across_reload(clipboard, tmp_path, monkeypatch):
    """A restart must not lose history — this is the write-then-read-back test."""
    from conftest import load_server

    clipboard.save_to_history("survives restart", label="persistent")

    reloaded = load_server("clipboard")
    assert reloaded.get_by_label("persistent")["entry"]["text"] == "survives restart"


def test_get_by_label(clipboard):
    clipboard.save_to_history("api notes body", label="api-notes")
    clipboard.save_to_history("other", label="other")

    found = clipboard.get_by_label("api-notes")

    assert found["success"]
    assert found["entry"]["text"] == "api notes body"


def test_get_by_missing_label_fails(clipboard):
    assert not clipboard.get_by_label("nope")["success"]


def test_find_in_history(clipboard):
    clipboard.save_to_history("notes about the database schema")
    clipboard.save_to_history("unrelated text")

    found = clipboard.find_in_history("schema")

    assert len(found["results"]) == 1
    assert "schema" in found["results"][0]["text"]


def test_delete_from_history(clipboard):
    entry_id = clipboard.save_to_history("temporary")["entry_id"]

    assert clipboard.delete_from_history(entry_id)["success"]
    assert clipboard.get_history()["count"] == 0


def test_clear_history(clipboard):
    clipboard.save_to_history("a")
    clipboard.save_to_history("b")

    clipboard.clear_history()

    assert clipboard.get_history()["count"] == 0


def test_rapid_saves_get_unique_ids(clipboard):
    ids = {clipboard.save_to_history(str(i))["entry_id"] for i in range(25)}
    assert len(ids) == 25


def test_stats_reflect_history(clipboard):
    clipboard.save_to_history("abcd")
    clipboard.save_to_history("efgh")

    stats = clipboard.get_stats()

    assert stats["total_entries"] == 2
    assert stats["average_length"] == 4


def test_markdown_format_does_not_discard_text(clipboard):
    """
    Regression: the markdown branch was f"## {t[:50]}...", which truncated
    at 50 characters and appended an ellipsis even to short input, so a
    formatting tool silently destroyed the caller's text.
    """
    long_text = "w" * 200

    result = clipboard.format_text(long_text, format_type="markdown")

    assert long_text in result["text"], "formatter discarded input"


def test_markdown_format_of_short_text_has_no_ellipsis(clipboard):
    assert clipboard.format_text("Hi", format_type="markdown")["text"] == "## Hi"


def test_markdown_keeps_body_after_heading(clipboard):
    result = clipboard.format_text("Title\nthe body", format_type="markdown")
    assert result["text"] == "## Title\n\nthe body"


@pytest.mark.parametrize(
    "fmt,text,expected",
    [
        ("html", "x", "<p>x</p>"),
        ("bold", "x", "<b>x</b>"),
        ("italic", "x", "<i>x</i>"),
        ("uppercase", "aB", "AB"),
        ("lowercase", "aB", "ab"),
    ],
)
def test_format_variants(clipboard, fmt, text, expected):
    assert clipboard.format_text(text, format_type=fmt)["text"] == expected


def test_clean_text_collapses_whitespace(clipboard):
    assert clipboard.clean_text("  a   b\n\n\n c  ")["text"] == "a b c"


def test_merge_clips(clipboard):
    result = clipboard.merge_clips(["one", "two"], separator=" | ")
    assert result["text"] == "one | two"
    assert result["item_count"] == 2


def test_history_is_json_serializable(clipboard):
    clipboard.save_to_history("x", label="y")
    json.dumps(clipboard.get_history())


def test_missing_clipboard_tool_is_reported_honestly(clipboard):
    """
    With no clipboard binary the server must say so, not return a
    plausible-looking empty string. This server previously returned the
    literal "Sample clipboard text" for every read.
    """
    result = clipboard.get_clipboard()
    if not result["success"]:
        assert "clipboard tool" in result["error"].lower()
    else:
        assert result["text"] != "Sample clipboard text"


def test_system_clipboard_round_trip(clipboard):
    """The real write->read test, where a real clipboard exists."""
    if not _has_system_clipboard(clipboard):
        pytest.skip("no system clipboard available (headless environment)")

    clipboard.set_clipboard("round trip value")

    assert clipboard.get_clipboard()["text"].strip() == "round trip value"
