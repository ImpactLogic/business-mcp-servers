"""
Document manager server.

organize_documents moves real files, so the rule-matching and dry_run tests
matter most: the miscategorisation bug was silent and irreversible.
"""

import json

import pytest


@pytest.fixture
def tree(tmp_path):
    """A source directory with one file per rule outcome."""
    source = tmp_path / "src"
    source.mkdir()
    for name in ("a.pdf", "b.txt", "c.zzz"):
        (source / name).write_text(name)
    return tmp_path


RULES = {"pdf": "pdfs", "txt": "texts"}


def test_unmatched_file_goes_to_default_category(docs, tree):
    """
    Regression: rules.items() was unpacked into the same variable holding
    the default, so a file matching no rule was filed under whichever
    category happened to be last — and moved there.
    """
    result = docs.organize_documents(
        str(tree / "src"), str(tree / "dst"), RULES, dry_run=False
    )

    assert (tree / "dst" / "documents" / "c.zzz").exists(), (
        "unmatched file was filed under the last rule's category"
    )
    assert result["moved"] == 3


def test_matched_files_go_to_their_rule_category(docs, tree):
    docs.organize_documents(str(tree / "src"), str(tree / "dst"), RULES, dry_run=False)

    assert (tree / "dst" / "pdfs" / "a.pdf").exists()
    assert (tree / "dst" / "texts" / "b.txt").exists()


def test_dry_run_is_the_default(docs, tree):
    result = docs.organize_documents(str(tree / "src"), str(tree / "dst"), RULES)
    assert result["dry_run"] is True


def test_dry_run_touches_nothing(docs, tree):
    """A preview must not create, move, or delete anything."""
    before = sorted(p.name for p in (tree / "src").iterdir())

    result = docs.organize_documents(str(tree / "src"), str(tree / "dst"), RULES)

    assert sorted(p.name for p in (tree / "src").iterdir()) == before
    assert not (tree / "dst").exists(), "dry run created the destination"
    assert result["moved"] == 3, "dry run should still report what it would do"


def test_dry_run_predicts_the_real_run(docs, tree):
    preview = docs.organize_documents(str(tree / "src"), str(tree / "dst"), RULES)
    actual = docs.organize_documents(
        str(tree / "src"), str(tree / "dst"), RULES, dry_run=False
    )

    assert [f["destination"] for f in preview["files"]] == [
        f["destination"] for f in actual["files"]
    ]


def test_organize_with_no_rules_uses_default(docs, tree):
    docs.organize_documents(str(tree / "src"), str(tree / "dst"), dry_run=False)

    assert (tree / "dst" / "documents" / "a.pdf").exists()


def test_organize_missing_source_fails(docs, tmp_path):
    result = docs.organize_documents(str(tmp_path / "nope"), str(tmp_path / "dst"))
    assert not result["success"]


def test_upload_then_list(docs, tmp_path):
    source = tmp_path / "f.txt"
    source.write_text("body")

    docs.upload_document(str(source), str(tmp_path / "up" / "f.txt"), tags=["tagged"])

    listed = docs.list_documents(str(tmp_path / "up"))
    assert [f["name"] for f in listed["files"]] == ["f.txt"]
    assert listed["files"][0]["tags"] == ["tagged"]


def test_sidecars_are_not_listed_as_documents(docs, tmp_path):
    """Regression: rglob("*") listed .meta.json sidecars as documents."""
    source = tmp_path / "f.txt"
    source.write_text("body")
    docs.upload_document(str(source), str(tmp_path / "up" / "f.txt"), tags=["t"])

    listed = docs.list_documents(str(tmp_path / "up"))

    assert not any(f["name"].endswith(".meta.json") for f in listed["files"])


def test_sidecars_do_not_collide_across_extensions(docs, tmp_path):
    """
    Regression: with_suffix(".meta.json") mapped report.pdf and report.txt
    onto one report.meta.json, so one file's tags overwrote the other's.
    """
    for name, tag in (("report.pdf", "pdf-tag"), ("report.txt", "txt-tag")):
        source = tmp_path / f"src-{name}"
        source.write_text("x")
        docs.upload_document(str(source), str(tmp_path / "up" / name), tags=[tag])

    listed = docs.list_documents(str(tmp_path / "up"))
    tags_by_name = {f["name"]: f["tags"] for f in listed["files"]}

    assert tags_by_name["report.pdf"] == ["pdf-tag"]
    assert tags_by_name["report.txt"] == ["txt-tag"]


def test_delete_does_not_remove_another_files_sidecar(docs, tmp_path):
    for name in ("report.pdf", "report.txt"):
        source = tmp_path / f"src-{name}"
        source.write_text("x")
        docs.upload_document(str(source), str(tmp_path / "up" / name), tags=["t"])

    docs.delete_document(str(tmp_path / "up" / "report.pdf"))

    assert (tmp_path / "up" / "report.txt.meta.json").exists(), (
        "deleting one document removed another document's metadata"
    )


def test_delete_removes_its_own_sidecar(docs, tmp_path):
    source = tmp_path / "f.txt"
    source.write_text("x")
    docs.upload_document(str(source), str(tmp_path / "up" / "f.txt"), tags=["t"])

    docs.delete_document(str(tmp_path / "up" / "f.txt"))

    assert not (tmp_path / "up" / "f.txt").exists()
    assert not (tmp_path / "up" / "f.txt.meta.json").exists()


def test_upload_does_not_overwrite(docs, tmp_path):
    source = tmp_path / "f.txt"
    source.write_text("first")
    target = tmp_path / "up" / "f.txt"

    docs.upload_document(str(source), str(target))
    second = docs.upload_document(str(source), str(target))

    assert second["destination"] != str(target)
    assert target.read_text() == "first"


def test_get_file_metadata_is_json_serializable(docs, tmp_path):
    """Regression: returned a Path, which fails at the JSON transport."""
    source = tmp_path / "f.txt"
    source.write_text("body")

    result = docs.get_file_metadata(str(source))

    json.dumps(result)
    assert result["metadata"]["size"] == len("body")


def test_create_archive(docs, tree, tmp_path):
    result = docs.create_archive(str(tree / "src"), str(tmp_path / "out.tar.gz"))

    assert result["success"]
    assert (tmp_path / "out.tar.gz").exists()
    assert (tmp_path / "out.tar.gz").stat().st_size > 0


def test_missing_file_reports_failure(docs, tmp_path):
    assert not docs.get_file_metadata(str(tmp_path / "nope.txt"))["success"]
    assert not docs.delete_document(str(tmp_path / "nope.txt"))["success"]
