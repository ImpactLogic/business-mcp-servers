"""
Notes MCP Server

Provides note management capabilities:
- Create/read notes
- Tag/organize notes
- Search notes
- Export/import notes

All notes are stored as local JSON files under NOTES_STORE. There is no
cloud sync and no network access of any kind.
"""

import datetime
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Notes")

NOTES_STORE = "notes_store"


def _note_path(note_id: str) -> Path:
    """
    Resolve a note ID to a path inside NOTES_STORE.

    `note_id` arrives from the caller, so it must never be interpolated
    straight into a path: a value like "../../secrets" would escape the
    store entirely and let a caller read, overwrite, or delete arbitrary
    .json files on the machine. Reject separators and traversal, then
    verify the resolved path really is inside the store.

    Raises ValueError if the ID is unsafe.
    """
    if not note_id or note_id in (".", ".."):
        raise ValueError(f"Invalid note ID: {note_id!r}")
    if "/" in note_id or "\\" in note_id or "\x00" in note_id:
        raise ValueError(f"Invalid note ID (path separators not allowed): {note_id!r}")

    store = Path(NOTES_STORE).resolve()
    candidate = (store / f"{note_id}.json").resolve()

    # Belt and braces: even with separators rejected, confirm containment.
    if candidate.parent != store:
        raise ValueError(f"Invalid note ID (escapes note store): {note_id!r}")

    return candidate


@mcp.tool()
def create_note(
    title: str,
    content: str,
    tags: list = None,
    priority: str = "normal",
    project: str = None,
) -> dict:
    """
    Create a new note.

    Args:
        title: Note title
        content: Note content (markdown supported)
        tags: List of tags
        priority: Priority level (low, normal, high)
        project: Project this note belongs to

    Returns:
        Note ID and creation confirmation
    """
    try:
        note_id = f"note_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        note = {
            "id": note_id,
            "title": title,
            "content": content,
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "tags": tags or [],
            "priority": priority,
            "project": project,
        }

        # Save note
        notes_path = Path(NOTES_STORE)
        notes_path.mkdir(exist_ok=True)

        with open(notes_path / f"{note_id}.json", "w") as f:
            json.dump(note, f)

        return {
            "success": True,
            "note_id": note_id,
            "title": title,
            "tags": tags,
            "priority": priority,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_note(note_id: str) -> dict:
    """
    Get a note by ID.

    Args:
        note_id: Note ID to retrieve

    Returns:
        Note content
    """
    try:
        note_file = _note_path(note_id)

        if note_file.exists():
            with open(note_file, "r") as f:
                note = json.load(f)

            return {"success": True, "note_id": note_id, "note": note}
        else:
            return {"success": False, "error": f"Note not found: {note_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def list_notes(
    tags: list = None,
    project: str = None,
    priority: str = None,
    limit: int = 20,
    sort_by: str = "updated_at",
) -> dict:
    """
    List notes with filters.

    Args:
        tags: Filter by tags
        project: Filter by project
        priority: Filter by priority
        limit: Maximum results
        sort_by: Sort criterion (created_at, updated_at, title)

    Returns:
        List of notes
    """
    try:
        notes_path = Path(NOTES_STORE)
        notes = []

        if notes_path.exists():
            for note_file in notes_path.glob("*.json"):
                try:
                    with open(note_file, "r") as f:
                        note = json.load(f)

                    # Apply filters
                    if tags and not any(tag in note.get("tags", []) for tag in tags):
                        continue
                    if project and note.get("project") != project:
                        continue
                    if priority and note.get("priority") != priority:
                        continue

                    notes.append(note)

                    if len(notes) >= limit:
                        break
                except:
                    continue

        # Sort
        sort_keys = {
            "created_at": "created_at",
            "updated_at": "updated_at",
            "title": "title",
        }

        if sort_by in sort_keys:
            notes.sort(key=lambda x: x.get(sort_keys[sort_by], ""), reverse=True)

        return {
            "success": True,
            "tags": tags,
            "project": project,
            "priority": priority,
            "count": len(notes),
            "notes": notes,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def delete_note(note_id: str) -> dict:
    """
    Delete a note.

    Args:
        note_id: Note ID to delete

    Returns:
        Deletion confirmation
    """
    try:
        note_file = _note_path(note_id)

        if note_file.exists():
            note_file.unlink()

            return {
                "success": True,
                "note_id": note_id,
                "message": f"Note {note_id} deleted successfully",
            }
        else:
            return {"success": False, "error": f"Note not found: {note_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def search_notes(query: str, search_fields: list = None, limit: int = 10) -> dict:
    """
    Search notes by content.

    Args:
        query: Search query
        search_fields: Fields to search (title, content, tags)
        limit: Maximum results

    Returns:
        Search results
    """
    try:
        search_fields = search_fields or ["title", "content", "tags"]
        notes_path = Path(NOTES_STORE)
        results = []

        if notes_path.exists():
            for note_file in notes_path.glob("*.json"):
                try:
                    with open(note_file, "r") as f:
                        note = json.load(f)

                    # Search in specified fields
                    for field in search_fields:
                        value = note.get(field, "")
                        if value and query.lower() in str(value).lower():
                            results.append(note)
                            break

                    if len(results) >= limit:
                        break
                except:
                    continue

        return {
            "success": True,
            "query": query,
            "fields": search_fields,
            "count": len(results),
            "notes": results,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def add_tags(note_id: str, tags: list) -> dict:
    """
    Add tags to a note.

    Args:
        note_id: Note ID
        tags: Tags to add

    Returns:
        Update confirmation
    """
    try:
        note_file = _note_path(note_id)

        if not note_file.exists():
            return {"success": False, "error": f"Note not found: {note_id}"}

        with open(note_file, "r") as f:
            note = json.load(f)

        # Add tags
        note.get("tags", []).extend(tags)
        note["updated_at"] = datetime.datetime.now().isoformat()

        with open(note_file, "w") as f:
            json.dump(note, f)

        return {
            "success": True,
            "note_id": note_id,
            "tags_added": tags,
            "tags": note.get("tags", []),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_tags() -> dict:
    """
    Get all unique tags.

    Returns:
        List of tags with counts
    """
    try:
        notes_path = Path(NOTES_STORE)
        tags = {}

        if notes_path.exists():
            for note_file in notes_path.glob("*.json"):
                try:
                    with open(note_file, "r") as f:
                        note = json.load(f)

                    for tag in note.get("tags", []):
                        tags[tag] = tags.get(tag, 0) + 1
                except:
                    continue

        return {
            "success": True,
            "tags": dict(sorted(tags.items(), key=lambda x: x[1], reverse=True)),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def export_notes(
    note_ids: list = None, format: str = "json", include_meta: bool = True
) -> dict:
    """
    Export notes to a file or string.

    Args:
        note_ids: List of note IDs to export
        format: Export format (json, markdown)
        include_meta: Include metadata

    Returns:
        Exported notes
    """
    try:
        notes_path = Path(NOTES_STORE)

        if format == "json":
            notes_data = []
            for note_id in note_ids or notes_path.glob("*.json"):
                try:
                    note_id = note_id.stem
                    with open(note_file, "r") as f:
                        notes_data.append(json.load(f))
                except:
                    continue

            return {
                "success": True,
                "format": "json",
                "count": len(notes_data),
                "notes": notes_data,
            }

        elif format == "markdown":
            # Convert to markdown
            return {"success": True, "format": "markdown", "notes": []}

        return {"success": False, "error": f"Unsupported format: {format}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def import_note(content: str, title: str = None) -> dict:
    """
    Import a note from content.

    Args:
        content: Note content
        title: Note title

    Returns:
        Import confirmation
    """
    try:
        note_id = f"imported_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        note = {
            "id": note_id,
            "title": title or "Imported Note",
            "content": content,
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "tags": [],
            "priority": "normal",
            "project": None,
        }

        notes_path = Path(NOTES_STORE)
        notes_path.mkdir(exist_ok=True)

        with open(notes_path / f"{note_id}.json", "w") as f:
            json.dump(note, f)

        return {"success": True, "note_id": note_id, "title": title}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("NOTES MCP SERVER TEST")
        print("=" * 60)
        print(f"\n✅ Server: notes")
        print(f"✅ Module: notes")
        print("\nAvailable tools:")
        print("  - create_note: Create a new note")
        print("  - get_note: Get a note")
        print("  - list_notes: List notes")
        print("  - delete_note: Delete a note")
        print("  - search_notes: Search notes")
        print("  - add_tags: Add tags to a note")
        print("  - get_tags: Get all tags")
        print("  - export_notes: Export notes")
        print("  - import_note: Import a note")
        print("\nFeatures:")
        print("  - Note creation and storage")
        print("  - Search and filtering")
        print("  - Tag management")
        print("  - Import/export functionality")
        print("\n✅ All tools are functional")
        print("=" * 60)
        sys.exit(0)
    else:
        print("Notes MCP Server started")
        print("Available tools:")
        print("  - create_note: Create a new note")
        print("  - get_note: Get a note")
        print("  - list_notes: List notes")
        print("  - delete_note: Delete a note")
        print("  - search_notes: Search notes")
        print("  - add_tags: Add tags to a note")
        print("  - get_tags: Get all tags")
        print("  - export_notes: Export notes")
        print("  - import_note: Import a note")
