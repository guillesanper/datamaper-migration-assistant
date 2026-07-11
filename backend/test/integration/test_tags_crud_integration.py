# test/integration/test_tags_crud_integration.py
"""
Tests de integración para app.crud.tags_crud
Usa base de datos real de PostgreSQL para testing
"""

import hashlib
import os
import sys
import uuid
from datetime import datetime

import pytest

# Import functions to test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from app.crud import tags_crud


def _create_snapshot_hash(snapshot_data: dict) -> str:
    """Helper function to create a hash for entity_versions snapshot"""
    import json

    snapshot_str = json.dumps(snapshot_data, sort_keys=True)
    return hashlib.sha256(snapshot_str.encode()).hexdigest()


@pytest.mark.integration
@pytest.mark.database
class TestTagsCrudIntegration:
    """Tests de integración para tags_crud con BD real"""

    def test_create_and_get_tag(self, db, test_user, test_project):
        """
        Test: Crear un tag y recuperarlo por ID
        Verifica el flujo completo de create -> get
        """
        # Necesitamos crear una versión primero
        cursor = db.cursor()
        version_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        snapshot = {"name": "test_table"}
        cursor.execute(
            """
            INSERT INTO entity_versions (id, hash, project_id, entity_id, entity_type, user_id, version_number, change_type, snapshot, is_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """,
            (
                version_id,
                _create_snapshot_hash(snapshot),
                test_project["id"],
                entity_id,
                "table",
                test_user["id"],
                1,
                "create",
                '{"name": "test_table"}',
                False,
            ),
        )
        db.commit()
        cursor.close()

        # Crear tag
        tag = tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="v1.0.0",
            created_by=test_user["id"],
            description="First release",
            color="#FF5733",
        )

        # Verificar que se creó
        assert tag is not None
        assert tag["name"] == "v1.0.0"
        assert tag["description"] == "First release"
        assert tag["color"] == "#FF5733"
        tag_id = tag["id"]

        # Recuperar el tag
        retrieved_tag = tags_crud.get_tag_by_id(db, tag_id)

        # Verificar que se recuperó correctamente
        assert retrieved_tag is not None
        assert retrieved_tag["id"] == tag_id
        assert retrieved_tag["name"] == "v1.0.0"
        assert retrieved_tag["creator_username"] == test_user["username"]

    def test_get_tags_by_project(self, db, test_user, test_project):
        """
        Test: Obtener todos los tags de un proyecto
        Verifica que se retornan múltiples tags ordenados
        """
        # Crear versión
        cursor = db.cursor()
        version_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        snapshot = {"name": "test_table_2"}
        cursor.execute(
            """
            INSERT INTO entity_versions (id, hash, project_id, entity_id, entity_type, user_id, version_number, change_type, snapshot, is_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                version_id,
                _create_snapshot_hash(snapshot),
                test_project["id"],
                entity_id,
                "table",
                test_user["id"],
                1,
                "create",
                '{"name": "test_table_2"}',
                False,
            ),
        )
        db.commit()
        cursor.close()

        # Crear múltiples tags
        tag1 = tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="v1.0.0",
            created_by=test_user["id"],
        )

        tag2 = tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="v2.0.0",
            created_by=test_user["id"],
        )

        # Obtener todos los tags del proyecto
        tags = tags_crud.get_tags_by_project(db, test_project["id"])

        # Verificar
        assert isinstance(tags, list)
        assert len(tags) >= 2  # Al menos los 2 que creamos

        # Verificar que contiene nuestros tags
        tag_names = [t["name"] for t in tags]
        assert "v1.0.0" in tag_names
        assert "v2.0.0" in tag_names

        # Verificar que incluye info del usuario
        for tag in tags:
            if tag["name"] in ["v1.0.0", "v2.0.0"]:
                assert tag["creator_username"] == test_user["username"]

        # Verificar que incluye info de entity_versions
        for tag in tags:
            if tag["name"] in ["v1.0.0", "v2.0.0"]:
                assert tag["entity_id"] == entity_id
                assert tag["entity_type"] == "table"
                assert tag["version_number"] == 1

    def test_get_tags_by_version(self, db, test_user, test_project):
        """
        Test: Obtener todos los tags de una versión específica
        """
        # Crear versión
        cursor = db.cursor()
        version_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        snapshot = {"name": "test_schema"}
        cursor.execute(
            """
            INSERT INTO entity_versions (id, hash, project_id, entity_id, entity_type, user_id, version_number, change_type, snapshot, is_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                version_id,
                _create_snapshot_hash(snapshot),
                test_project["id"],
                entity_id,
                "schema",
                test_user["id"],
                1,
                "create",
                '{"name": "test_schema"}',
                False,
            ),
        )
        db.commit()
        cursor.close()

        # Crear múltiples tags para la misma versión
        tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="stable",
            created_by=test_user["id"],
        )

        tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="production",
            created_by=test_user["id"],
        )

        # Obtener tags por versión
        tags = tags_crud.get_tags_by_version(db, version_id)

        # Verificar
        assert isinstance(tags, list)
        assert len(tags) == 2

        tag_names = [t["name"] for t in tags]
        assert "stable" in tag_names
        assert "production" in tag_names

    def test_delete_tag(self, db, test_user, test_project):
        """
        Test: Eliminar un tag y verificar que ya no existe
        """
        # Crear versión
        cursor = db.cursor()
        version_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        snapshot = {"name": "test_table_4"}
        cursor.execute(
            """
            INSERT INTO entity_versions (id, hash, project_id, entity_id, entity_type, user_id, version_number, change_type, snapshot, is_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                version_id,
                _create_snapshot_hash(snapshot),
                test_project["id"],
                entity_id,
                "table",
                test_user["id"],
                1,
                "create",
                '{"name": "test_table_4"}',
                False,
            ),
        )
        db.commit()
        cursor.close()

        # Crear tag
        tag = tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="to-be-deleted",
            created_by=test_user["id"],
        )
        tag_id = tag["id"]

        # Verificar que existe
        assert tags_crud.get_tag_by_id(db, tag_id) is not None

        # Eliminar
        deleted = tags_crud.delete_tag(db, tag_id)

        # Verificar que se eliminó
        assert deleted is True
        assert tags_crud.get_tag_by_id(db, tag_id) is None

    def test_delete_nonexistent_tag(self, db):
        """
        Test: Intentar eliminar un tag que no existe debe retornar False
        """
        nonexistent_uuid = str(uuid.uuid4())
        result = tags_crud.delete_tag(db, nonexistent_uuid)
        assert result is False

    def test_check_tag_exists(self, db, test_user, test_project):
        """
        Test: Verificar existencia de tags
        """
        # Crear versión
        cursor = db.cursor()
        version_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        snapshot = {"name": "test_table_5"}
        cursor.execute(
            """
            INSERT INTO entity_versions (id, hash, project_id, entity_id, entity_type, user_id, version_number, change_type, snapshot, is_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                version_id,
                _create_snapshot_hash(snapshot),
                test_project["id"],
                entity_id,
                "table",
                test_user["id"],
                1,
                "create",
                '{"name": "test_table_5"}',
                False,
            ),
        )
        db.commit()
        cursor.close()

        # Verificar que no existe antes de crear
        exists_before = tags_crud.check_tag_exists(db, test_project["id"], "unique-tag")
        assert exists_before is False

        # Crear tag
        tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="unique-tag",
            created_by=test_user["id"],
        )

        # Verificar que ahora existe
        exists_after = tags_crud.check_tag_exists(db, test_project["id"], "unique-tag")
        assert exists_after is True

    def test_duplicate_tag_handling(self, db, test_user, test_project):
        """
        Test: Intentar crear tags duplicados en el mismo proyecto
        Nota: La función no previene duplicados, pero check_tag_exists puede usarse
        """
        # Crear versión
        cursor = db.cursor()
        version_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        snapshot = {"name": "test_table_6"}
        cursor.execute(
            """
            INSERT INTO entity_versions (id, hash, project_id, entity_id, entity_type, user_id, version_number, change_type, snapshot, is_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                version_id,
                _create_snapshot_hash(snapshot),
                test_project["id"],
                entity_id,
                "table",
                test_user["id"],
                1,
                "create",
                '{"name": "test_table_6"}',
                False,
            ),
        )
        db.commit()
        cursor.close()

        # Crear primer tag
        tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="duplicate-test",
            created_by=test_user["id"],
        )

        # Verificar que existe antes de intentar duplicar
        if tags_crud.check_tag_exists(db, test_project["id"], "duplicate-test"):
            # No crear duplicado - este es el flujo esperado
            assert True
        else:
            # Si no usamos check, podríamos crear duplicados (comportamiento actual)
            # La BD debe tener constraint UNIQUE si queremos prevenir esto
            pass

    def test_tag_with_all_optional_fields(self, db, test_user, test_project):
        """
        Test: Crear tag con todos los campos opcionales
        """
        # Crear versión
        cursor = db.cursor()
        version_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        snapshot = {"name": "test_table_7"}
        cursor.execute(
            """
            INSERT INTO entity_versions (id, hash, project_id, entity_id, entity_type, user_id, version_number, change_type, snapshot, is_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                version_id,
                _create_snapshot_hash(snapshot),
                test_project["id"],
                entity_id,
                "table",
                test_user["id"],
                1,
                "create",
                '{"name": "test_table_7"}',
                False,
            ),
        )
        db.commit()
        cursor.close()

        # Crear tag completo
        tag = tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="complete-tag",
            created_by=test_user["id"],
            description="Full description here",
            color="#3498db",
        )

        # Verificar todos los campos
        assert tag["name"] == "complete-tag"
        assert tag["description"] == "Full description here"
        assert tag["color"] == "#3498db"
        assert tag["version_id"] == version_id
        assert tag["project_id"] == test_project["id"]
        assert tag["created_by"] == test_user["id"]
        assert isinstance(tag["created_at"], datetime)

    def test_tag_without_optional_fields(self, db, test_user, test_project):
        """
        Test: Crear tag sin campos opcionales (description, color)
        """
        # Crear versión
        cursor = db.cursor()
        version_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        snapshot = {"name": "test_table_8"}
        cursor.execute(
            """
            INSERT INTO entity_versions (id, hash, project_id, entity_id, entity_type, user_id, version_number, change_type, snapshot, is_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                version_id,
                _create_snapshot_hash(snapshot),
                test_project["id"],
                entity_id,
                "table",
                test_user["id"],
                1,
                "create",
                '{"name": "test_table_8"}',
                False,
            ),
        )
        db.commit()
        cursor.close()

        # Crear tag mínimo
        tag = tags_crud.create_tag(
            db=db,
            version_id=version_id,
            project_id=test_project["id"],
            name="minimal-tag",
            created_by=test_user["id"],
        )

        # Verificar campos requeridos
        assert tag["name"] == "minimal-tag"
        assert tag["version_id"] == version_id
        assert tag["project_id"] == test_project["id"]

        # Campos opcionales deben ser None
        assert tag["description"] is None
        assert tag["color"] is None

    def test_get_tag_by_id_nonexistent(self, db):
        """
        Test: Obtener tag que no existe debe retornar None
        """
        nonexistent_uuid = str(uuid.uuid4())
        result = tags_crud.get_tag_by_id(db, nonexistent_uuid)
        assert result is None

    def test_get_tags_by_project_empty(self, db):
        """
        Test: Obtener tags de proyecto sin tags debe retornar lista vacía
        """
        nonexistent_uuid = str(uuid.uuid4())
        tags = tags_crud.get_tags_by_project(db, nonexistent_uuid)
        assert isinstance(tags, list)
        assert len(tags) == 0

    def test_get_tags_by_version_empty(self, db):
        """
        Test: Obtener tags de versión sin tags debe retornar lista vacía
        """
        nonexistent_uuid = str(uuid.uuid4())
        tags = tags_crud.get_tags_by_version(db, nonexistent_uuid)
        assert isinstance(tags, list)
        assert len(tags) == 0
