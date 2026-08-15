"""
Document Manager MCP Server

Manages document workflows, file operations, and organization.
"""

import json
import os
import shutil
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Document Manager")


def _meta_path(path: Path) -> Path:
    """
    Sidecar metadata path for a document.

    Appends to the full filename rather than using with_suffix(): the latter
    maps report.pdf and report.txt onto the same report.meta.json, so one
    file's metadata would overwrite another's — and delete_document would
    remove a sidecar belonging to a different file.
    """
    return path.with_name(path.name + ".meta.json")


def _is_meta(path: Path) -> bool:
    """True if this path is a sidecar rather than a document."""
    return path.name.endswith(".meta.json")


def _category_for(path: Path, rules: dict) -> str:
    """
    Pick the destination category for a file.

    Returns the default when no rule matches. The previous implementation
    unpacked rules.items() into the same name that held the default, so an
    unmatched file was filed under whichever category happened to come last.
    """
    if not rules:
        return "documents"
    extension = path.suffix.lower()
    for ext, category in rules.items():
        ext = ext.lower()
        if extension == ext or extension == f".{ext.lstrip('.')}":
            return category
    return "documents"


@mcp.tool()
def upload_document(filepath: str, destination: str = None, tags: list = None) -> dict:
    """
    Upload a document to a destination.

    Args:
        filepath: Source file path
        destination: Destination path (default: root uploads directory)
        tags: Optional tags for organization

    Returns:
        dict with upload result
    """
    source_path = Path(filepath)

    if not source_path.exists():
        return {"success": False, "error": f"Source file not found: {filepath}"}

    # Determine destination
    if destination is None:
        # Default to uploads directory
        default_upload_dir = Path("./uploads")
        destination = default_upload_dir / source_path.name

    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy file (don't overwrite)
    unique_name = source_path.name
    counter = 1
    while destination_path.exists():
        name, ext = os.path.splitext(source_path.name)
        unique_name = f"{name}_{counter}{ext}"
        destination_path = destination_path.parent / unique_name
        counter += 1

    shutil.copy2(source_path, destination_path)

    # Add tags as metadata (stored in sidecar file)
    if tags:
        metadata_file = _meta_path(destination_path)
        metadata = {
            "tags": tags,
            "source": str(source_path),
            "uploaded": str(destination_path),
        }
        with open(metadata_file, "w") as f:
            json.dump(metadata, f)

    return {"success": True, "destination": str(destination_path), "tags": tags or []}


@mcp.tool()
def organize_documents(
    source_dir: str, destination_dir: str, rules: dict = None, dry_run: bool = True
) -> dict:
    """
    Organize documents into categories.

    This MOVES files. It previews by default: `dry_run=True` reports the
    moves it would make and touches nothing. Pass `dry_run=False` to
    actually move files.

    Args:
        source_dir: Source directory to scan
        destination_dir: Destination directory for organized files
        rules: Organization rules (e.g., {"pdf": "documents", "docx": "documents"}).
            Files matching no rule go to "documents".
        dry_run: Preview only. Defaults to True; set False to move files.

    Returns:
        dict with organization results
    """
    source_path = Path(source_dir)
    dest_path = Path(destination_dir)

    if not source_path.exists():
        return {"success": False, "error": f"Source directory not found: {source_dir}"}

    if not dry_run:
        dest_path.mkdir(parents=True, exist_ok=True)

    results = {
        "success": True,
        "dry_run": dry_run,
        "moved": 0,
        "skipped": 0,
        "files": [],
    }

    for file_path in sorted(source_path.iterdir()):
        if not file_path.is_file() or _is_meta(file_path):
            continue

        category = _category_for(file_path, rules)
        category_dir = dest_path / category
        dest_file = category_dir / file_path.name

        if dest_file.exists():
            results["skipped"] += 1
            continue

        if not dry_run:
            category_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file_path), str(dest_file))

        results["moved"] += 1
        results["files"].append(
            {
                "source": str(file_path),
                "destination": str(dest_file),
                "category": category,
            }
        )

    return results


@mcp.tool()
def list_documents(
    directory: str = None, tags: list = None, search: str = None
) -> dict:
    """
    List documents in a directory.

    Args:
        directory: Directory to list (default: current)
        tags: Filter by tags
        search: Search text in filenames

    Returns:
        dict with document list
    """
    directory_path = Path(directory) if directory else Path(".")

    if not directory_path.exists():
        return {"success": False, "error": f"Directory not found: {directory}"}

    files = []

    # Scan directory
    for file_path in sorted(directory_path.rglob("*")):
        # Sidecars describe documents; they are not documents themselves.
        if file_path.is_file() and not _is_meta(file_path):
            metadata_file = _meta_path(file_path)
            file_tags = None

            if metadata_file.exists():
                try:
                    with open(metadata_file) as f:
                        metadata = json.loads(f.read())
                        file_tags = metadata.get("tags", [])
                except (json.JSONDecodeError, OSError):
                    pass

            # Apply filters
            file_match = search is None or search.lower() in file_path.name.lower()
            tags_match = tags is None or bool(
                file_tags and any(t in file_tags for t in tags)
            )

            if file_match and tags_match:
                files.append(
                    {
                        "path": str(file_path),
                        "name": file_path.name,
                        "size": file_path.stat().st_size,
                        "tags": file_tags,
                    }
                )

    return {"success": True, "files": files, "count": len(files)}


@mcp.tool()
def delete_document(filepath: str) -> dict:
    """
    Delete a document.

    Args:
        filepath: Path to delete

    Returns:
        dict with deletion result
    """
    source_path = Path(filepath)

    if not source_path.exists():
        return {"success": False, "error": f"File not found: {filepath}"}

    try:
        # Delete main file
        source_path.unlink()

        # Delete metadata file if exists
        metadata_file = _meta_path(source_path)
        if metadata_file.exists():
            metadata_file.unlink()

        return {"success": True, "deleted": str(filepath)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def create_archive(
    directory: str, archive_path: str, file_pattern: str = "*.pdf"
) -> dict:
    """
    Create archive of documents.

    Args:
        directory: Source directory
        archive_path: Archive path
        file_pattern: File pattern to include

    Returns:
        dict with archive result
    """
    source_path = Path(directory)

    if not source_path.exists():
        return {"success": False, "error": f"Source directory not found: {directory}"}

    try:
        import tarfile

        archive_path = Path(archive_path)
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Create tar archive
        with tarfile.open(str(archive_path), "w") as tar:
            for file_path in source_path.glob(file_pattern):
                tar.add(file_path, arcname=str(file_path.relative_to(source_path)))

        return {"success": True, "archive_path": str(archive_path)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_file_metadata(filepath: str) -> dict:
    """
    Get metadata about a file.

    Args:
        filepath: File path

    Returns:
        dict with file metadata
    """
    source_path = Path(filepath)

    if not source_path.exists():
        return {"success": False, "error": f"File not found: {filepath}"}

    try:
        # Get metadata
        stat = source_path.stat()

        # Try to read metadata file
        metadata_file = _meta_path(source_path)
        file_metadata = {}

        if metadata_file.exists():
            try:
                with open(metadata_file) as f:
                    file_metadata = json.loads(f.read())
            except (json.JSONDecodeError, OSError):
                pass

        return {
            "success": True,
            "metadata": {
                "name": source_path.name,
                "size": stat.st_size,
                "created": source_path.stat().st_ctime,
                "modified": source_path.stat().st_mtime,
                "parent": str(source_path.parent),
                "file_metadata": file_metadata,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    mcp.run()
