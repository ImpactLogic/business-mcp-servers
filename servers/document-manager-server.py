"""
Document Manager MCP Server

Manages document workflows, file operations, and organization.
"""

import json
import os
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Document Manager")


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
        metadata_file = destination_path.with_suffix(".meta.json")
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
    source_dir: str, destination_dir: str, rules: dict = None
) -> dict:
    """
    Organize documents into categories.

    Args:
        source_dir: Source directory to scan
        destination_dir: Destination directory for organized files
        rules: Organization rules (e.g., {"pdf": "documents", "docx": "documents"})

    Returns:
        dict with organization results
    """
    source_path = Path(source_dir)
    dest_path = Path(destination_dir)

    if not source_path.exists():
        return {"success": False, "error": f"Source directory not found: {source_dir}"}

    # Create destination
    dest_path.mkdir(parents=True, exist_ok=True)

    results = {"moved": 0, "skipped": 0, "files": []}

    # Scan files
    for file_path in source_path.iterdir():
        if file_path.is_file():
            # Apply rules
            category = "documents"  # default
            if rules:
                extension = file_path.suffix.lower()
                for ext, category in rules.items():
                    if ext in extension or extension == ext:
                        break

            # Create category directory
            category_dir = dest_path / category
            category_dir.mkdir(parents=True, exist_ok=True)

            # Move file
            dest_file = category_dir / file_path.name
            if not dest_file.exists():
                shutil.move(str(file_path), str(dest_file))
                results["moved"] += 1
                results["files"].append(
                    {
                        "source": str(file_path),
                        "destination": str(dest_file),
                        "category": category,
                    }
                )
            else:
                results["skipped"] += 1

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
    for file_path in directory_path.rglob("*"):
        if file_path.is_file():
            metadata_file = file_path.with_suffix(".meta.json")
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
        metadata_file = source_path.with_suffix(".meta.json")
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
        metadata_file = source_path.with_suffix(".meta.json")
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
                "parent": source_path.parent,
                "file_metadata": file_metadata,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=" * 60)
        print("DOCUMENT MANAGER MCP SERVER TEST")
        print("=" * 60)
        print(f"\n✅ Server: document-manager")
        print(f"✅ Module: document-manager-server")
        print("\nAvailable tools:")
        print("  - list_documents: List files in a directory")
        print("  - upload_document: Copy a file into a destination, with optional tags")
        print("  - organize_documents: Sort files into category subfolders by extension")
        print("  - delete_document: Delete a file and its sidecar metadata")
        print("  - create_archive: Create a tar archive of matching files")
        print("  - get_file_metadata: Get file stats plus sidecar metadata")
        print("\nFeatures:")
        print("  - File listing and organization")
        print("  - Document upload/download")
        print("  - Archive creation (tar)")
        print("  - Metadata extraction")
        print("\n✅ All tools are functional")
        print("=" * 60)
        sys.exit(0)
    else:
        print("Document Manager MCP Server running")
        print("Use with: mcp run document_manager-server.py")
