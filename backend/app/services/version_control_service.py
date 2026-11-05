# services/version_control_service.py
"""
Business logic for version control operations
"""

import hashlib
import json
from typing import Any, Dict, List, Optional

from app.crud import activity_crud, mappings_crud, tags_crud, versions_crud


def generate_hash(snapshot: Dict[str, Any]) -> str:
    """Generate SHA-256 hash from snapshot for deduplication"""
    # Sort keys for consistent hashing
    snapshot_str = json.dumps(snapshot, sort_keys=True)
    return hashlib.sha256(snapshot_str.encode()).hexdigest()


def calculate_diff(old_snapshot: Dict[str, Any], new_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate differences between two snapshots.
    Returns a dict with added, modified, and removed keys.
    """
    diff: Dict[str, Dict[str, Any]] = {"added": {}, "modified": {}, "removed": {}}

    # Find added and modified keys
    for key, new_value in new_snapshot.items():
        if key not in old_snapshot:
            diff["added"][key] = new_value
        elif old_snapshot[key] != new_value:
            diff["modified"][key] = {"old": old_snapshot[key], "new": new_value}

    # Find removed keys
    for key in old_snapshot:
        if key not in new_snapshot:
            diff["removed"][key] = old_snapshot[key]

    return diff


def create_version(
    db,
    project_id: str,
    entity_id: str,
    entity_type: str,
    user_id: str,
    change_type: str,
    snapshot: Dict[str, Any],
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new version with automatic diff calculation and deduplication.
    """
    print(f"[VERSION SERVICE] create_version called")
    print(f"[VERSION SERVICE] - project_id: {project_id}")
    print(f"[VERSION SERVICE] - entity_id: {entity_id}")
    print(f"[VERSION SERVICE] - entity_type: {entity_type}")
    print(f"[VERSION SERVICE] - user_id: {user_id}")
    print(f"[VERSION SERVICE] - change_type: {change_type}")
    print(f"[VERSION SERVICE] - message: {message}")

    # Generate hash for deduplication
    snapshot_hash = generate_hash(snapshot)
    print(f"[VERSION SERVICE] Snapshot hash generated: {snapshot_hash[:16]}...")

    # Check if this exact snapshot already exists
    existing = versions_crud.get_version_by_hash_orm(db, snapshot_hash)
    if existing:
        # Return existing version instead of creating duplicate
        print(
            f"[VERSION SERVICE] ⚠ Duplicate snapshot detected, returning existing version: {existing['id']}"
        )
        return existing

    # Get the latest version to calculate diff
    print(f"[VERSION SERVICE] Fetching latest version for entity: {entity_id}")
    latest_version = versions_crud.get_latest_version_orm(db, entity_id)
    diff = None
    parent_version_id = None

    if latest_version:
        parent_version_id = latest_version["id"]
        print(f"[VERSION SERVICE] Found parent version: {parent_version_id}")
        # Calculate diff from latest version
        diff = calculate_diff(latest_version["snapshot"], snapshot)
        print(
            f"[VERSION SERVICE] Diff calculated: {len(diff.get('added', {}))} added, {len(diff.get('modified', {}))} modified, {len(diff.get('removed', {}))} removed"
        )
    else:
        print(f"[VERSION SERVICE] No previous version found (this is the first version)")

    # Get next version number
    version_number = versions_crud.get_next_version_number_orm(db, entity_id)
    print(f"[VERSION SERVICE] Next version number: {version_number}")

    # Create version
    print(f"[VERSION SERVICE] Creating version in database...")
    version = versions_crud.create_version_orm(
        db=db,
        project_id=project_id,
        entity_id=entity_id,
        entity_type=entity_type,
        user_id=user_id,
        version_number=version_number,
        change_type=change_type,
        snapshot=snapshot,
        hash=snapshot_hash,
        message=message,
        diff=diff,
        parent_version_id=parent_version_id,
    )

    print(f"[VERSION SERVICE] ✓ Version created successfully in database")
    print(f"[VERSION SERVICE] - Version ID: {version['id']}")
    print(f"[VERSION SERVICE] - Version Number: {version['version_number']}")

    # Log activity (done by trigger in database)
    return version


def get_version_history(
    db, entity_id: str, filters: Optional[Dict[str, Any]] = None, viewer_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get version history with optional filters (con viewer_id, solo de proyectos accesibles)"""
    filters = filters or {}

    return versions_crud.get_version_history_orm(
        db=db,
        entity_id=entity_id,
        limit=filters.get("limit", 50),
        offset=filters.get("offset", 0),
        change_type=filters.get("change_type"),
        user_id=filters.get("user_id"),
        viewer_id=viewer_id,
    )


def compare_versions(db, version_a_id: str, version_b_id: str) -> Dict[str, Any]:
    """
    Compare two versions and return detailed diff.
    Returns both versions and their differences.
    """
    version_a = versions_crud.get_version_by_id_orm(db, version_a_id)
    version_b = versions_crud.get_version_by_id_orm(db, version_b_id)

    if not version_a or not version_b:
        raise ValueError("One or both versions not found")

    if version_a["entity_id"] != version_b["entity_id"]:
        raise ValueError("Versions must belong to the same entity")

    # Calculate diff
    diff = calculate_diff(version_a["snapshot"], version_b["snapshot"])

    return {"version_a": version_a, "version_b": version_b, "diff": diff}


def restore_version(
    db,
    version_id: str,
    user_id: str,
    create_backup: bool = True,
    encryption_key: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    Restore a previous version.
    Optionally create a backup of current state before restoring.
    Returns the new version created from restoration.
    """
    print(f"[RESTORE] Starting restoration of version: {version_id}")

    # Get the version to restore
    version_to_restore = versions_crud.get_version_by_id_orm(db, version_id)
    if not version_to_restore:
        raise ValueError("Version not found")

    print(
        f"[RESTORE] Found version to restore: entity_type={version_to_restore['entity_type']}, entity_id={version_to_restore['entity_id']}"
    )
    print(f"[RESTORE] Snapshot keys: {list(version_to_restore['snapshot'].keys())}")

    # If backup requested, get current state
    if create_backup:
        current_version = versions_crud.get_latest_version_orm(db, version_to_restore["entity_id"])
        if current_version and current_version["id"] != version_id:
            print(f"[RESTORE] Creating backup of current state...")
            # Create backup version
            create_version(
                db=db,
                project_id=version_to_restore["project_id"],
                entity_id=version_to_restore["entity_id"],
                entity_type=version_to_restore["entity_type"],
                user_id=user_id,
                change_type="backup",
                snapshot=current_version["snapshot"],
                message=f"Backup before restoring to version {version_to_restore['version_number']}",
            )
            print(f"[RESTORE] Backup created successfully")

    # Apply changes to database based on entity type
    snapshot = version_to_restore["snapshot"]
    entity_type = version_to_restore["entity_type"]
    project_id = version_to_restore["project_id"]

    print(f"[RESTORE] Applying changes to database for entity_type: {entity_type}")

    if entity_type == "mapping":
        # Restore mappings
        _restore_mappings(db, project_id, snapshot, encryption_key)
    elif entity_type == "table":
        # Restore table structure
        _restore_table(db, project_id, snapshot)
    elif entity_type == "column":
        # Restore column
        _restore_column(db, project_id, snapshot)
    else:
        print(
            f"[RESTORE] Warning: Unknown entity_type '{entity_type}', skipping database restoration"
        )

    # Create new version from restored snapshot
    print(f"[RESTORE] Creating version record...")
    restored_version = create_version(
        db=db,
        project_id=version_to_restore["project_id"],
        entity_id=version_to_restore["entity_id"],
        entity_type=version_to_restore["entity_type"],
        user_id=user_id,
        change_type="restore",
        snapshot=version_to_restore["snapshot"],
        message=f"Restored from version {version_to_restore['version_number']}",
    )

    print(f"[RESTORE] Version record created: {restored_version['id']}")

    # Log restoration activity
    print(f"[RESTORE] Logging activity...")
    activity_crud.create_activity_log_orm(
        db=db,
        project_id=version_to_restore["project_id"],
        user_id=user_id,
        activity_type="version_restored",
        entity_id=version_to_restore["entity_id"],
        entity_type=version_to_restore["entity_type"],
        description=f"Restored to version {version_to_restore['version_number']}",
        metadata={"restored_version_id": version_id, "new_version_id": restored_version["id"]},
    )

    print(f"[RESTORE] Restoration complete!")
    return restored_version


def _restore_mappings(
    db, project_id: str, snapshot: Dict[str, Any], encryption_key: Optional[bytes] = None
):
    """Restore mappings from snapshot to database"""
    print(f"[RESTORE MAPPINGS] Starting restoration for project: {project_id}")

    try:
        # Delete all current mappings for this project using CRUD
        print(f"[RESTORE MAPPINGS] Deleting current mappings...")
        deleted_count = mappings_crud.delete_all_mappings_orm(db, project_id)
        print(f"[RESTORE MAPPINGS] Deleted {deleted_count} existing mappings")

        # Prepare mappings list from snapshot
        snapshot_mappings = snapshot.get("mappings", [])
        print(f"[RESTORE MAPPINGS] Inserting {len(snapshot_mappings)} mappings from snapshot...")

        # Format mappings for bulk_create_mappings_orm
        # Assume 'import' mode for legacy snapshots that don't have source_type
        mappings_to_create = []
        for mapping in snapshot_mappings:
            mappings_to_create.append(
                {
                    "origin_table": mapping.get("origin_table"),
                    "origin_column": mapping.get("origin_column"),
                    "destination_table": mapping.get("destination_table"),
                    "destination_column": mapping.get("destination_column"),
                    "origin_source_type": mapping.get("origin_source_type", "import"),
                    "destination_source_type": mapping.get("destination_source_type", "import"),
                }
            )

        # Insert mappings in bulk using CRUD
        if mappings_to_create:
            mappings_crud.bulk_create_mappings_orm(
                db,
                project_id=project_id,
                mappings=mappings_to_create,
                encryption_key=encryption_key,  # type: ignore[arg-type]
            )

        print(f"[RESTORE MAPPINGS] Mappings restored successfully")

    except Exception as e:
        print(f"[RESTORE MAPPINGS] Error: {str(e)}")
        raise


def _restore_table(db, project_id: str, snapshot: Dict[str, Any]):
    """Restore table structure from snapshot to database"""
    print(f"[RESTORE TABLE] Table restoration not yet implemented")
    # TODO: Implement table restoration logic
    pass


def _restore_column(db, project_id: str, snapshot: Dict[str, Any]):
    """Restore column from snapshot to database"""
    print(f"[RESTORE COLUMN] Column restoration not yet implemented")
    # TODO: Implement column restoration logic
    pass


def create_tag(
    db,
    version_id: str,
    project_id: str,
    name: str,
    created_by: str,
    description: Optional[str] = None,
    color: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a tag for a version"""
    # Check if tag name already exists in project
    if tags_crud.check_tag_exists_orm(db, project_id, name):
        raise ValueError(f"Tag '{name}' already exists in this project")

    # Verify version exists
    version = versions_crud.get_version_by_id_orm(db, version_id)
    if not version:
        raise ValueError("Version not found")

    if version["project_id"] != project_id:
        raise ValueError("Version does not belong to this project")

    return tags_crud.create_tag_orm(
        db=db,
        version_id=version_id,
        project_id=project_id,
        name=name,
        created_by=created_by,
        description=description,
        color=color,
    )


def get_project_versions(
    db, project_id: str, filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Get all versions for a project"""
    filters = filters or {}

    return versions_crud.get_project_versions_orm(
        db=db,
        project_id=project_id,
        limit=filters.get("limit", 100),
        offset=filters.get("offset", 0),
        entity_type=filters.get("entity_type"),
        change_type=filters.get("change_type"),
        user_id=filters.get("user_id"),
    )


def get_project_tags(db, project_id: str) -> List[Dict[str, Any]]:
    """Get all tags for a project"""
    return tags_crud.get_tags_by_project_orm(db, project_id)


def delete_tag(db, tag_id: str, user_id: str) -> bool:
    """Delete a tag"""
    # Verify tag exists and user has permission
    tag = tags_crud.get_tag_by_id_orm(db, tag_id)
    if not tag:
        return False

    # Only creator or project owner can delete tags
    # (Permission check should be done in router)

    return tags_crud.delete_tag_orm(db, tag_id)
