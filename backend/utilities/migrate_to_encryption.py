#!/usr/bin/env python3
"""
Script de Migración a Cifrado
Cifra datos existentes en la base de datos con AES-256-GCM + Argon2id

Este script:
1. Se conecta a la base de datos
2. Para cada proyecto sin cifrado configurado:
   - Solicita passphrase al administrador
   - Crea la configuración de cifrado
   - Cifra todos los datos relacionados (tables, columns, mappings, versions, comments)
   - Marca los datos como cifrados

Uso:
    python migrate_to_encryption.py [--dry-run] [--project-id UUID] [--batch-size N]

Opciones:
    --dry-run       : No hace cambios reales, solo muestra qué se haría
    --project-id    : Migra solo un proyecto específico (por UUID)
    --batch-size    : Número de registros a procesar por lote (default: 100)
    --rollback      : Revierte el cifrado (PELIGROSO - solo para testing)

Autor: DataMap Security Team
Fecha: 2025-01-31
"""

import argparse
import getpass
import os
import sys
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Agregar directorio padre al path para imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.crud import master_key_crud
from app.database.database import get_db
from app.utils.encryption import EncryptionError, EncryptionManager


class MigrationStats:
    """Estadísticas de la migración"""

    def __init__(self):
        self.tables_encrypted = 0
        self.columns_encrypted = 0
        self.mappings_encrypted = 0
        self.versions_encrypted = 0
        self.comments_encrypted = 0
        self.errors = []

    def add_error(self, entity_type: str, entity_id: str, error: str):
        self.errors.append({"entity_type": entity_type, "entity_id": entity_id, "error": error})

    def print_summary(self):
        print("\n" + "=" * 70)
        print("📊 RESUMEN DE MIGRACIÓN")
        print("=" * 70)
        print(f"✅ Tablas cifradas:     {self.tables_encrypted}")
        print(f"✅ Columnas cifradas:   {self.columns_encrypted}")
        print(f"✅ Mappings cifrados:   {self.mappings_encrypted}")
        print(f"✅ Versiones cifradas:  {self.versions_encrypted}")
        print(f"✅ Comentarios cifrados: {self.comments_encrypted}")
        print(f"❌ Errores:             {len(self.errors)}")

        if self.errors:
            print("\n❌ ERRORES ENCONTRADOS:")
            for error in self.errors[:10]:  # Mostrar solo primeros 10
                print(f"   - {error['entity_type']} {error['entity_id']}: {error['error']}")
            if len(self.errors) > 10:
                print(f"   ... y {len(self.errors) - 10} errores más")
        print("=" * 70 + "\n")


def get_projects_without_encryption(db) -> List[Dict[str, Any]]:
    """
    Obtiene lista de proyectos que no tienen cifrado configurado
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            SELECT p.id, p.name, p.owner_id, p.created_at
            FROM projects p
            LEFT JOIN project_encryption pe ON p.id = pe.project_id
            WHERE pe.project_id IS NULL
            ORDER BY p.created_at ASC
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def encrypt_project_tables(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: MigrationStats
):
    """
    Cifra todos los nombres de tablas de un proyecto
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        # Obtener tablas del proyecto que NO están cifradas
        cursor.execute(
            """
            SELECT id, name, type
            FROM tables
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )

        tables = cursor.fetchall()
        print(f"   🗂️  Cifrando {len(tables)} tablas...")

        for table in tables:
            try:
                # Cifrar nombre
                ciphertext, nonce = manager.encrypt_field(table["name"], encryption_key)
                name_encrypted = manager.encode_for_storage(ciphertext)
                name_nonce = manager.encode_for_storage(nonce)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE tables
                        SET name_encrypted = %s,
                            name_nonce = %s,
                            is_encrypted = TRUE
                        WHERE id = %s
                    """,
                        (name_encrypted, name_nonce, table["id"]),
                    )

                stats.tables_encrypted += 1
            except Exception as e:
                stats.add_error("table", table["id"], str(e))
                print(f"      ❌ Error en tabla {table['id']}: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def encrypt_project_columns(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: MigrationStats
):
    """
    Cifra todos los nombres y tipos de columnas de un proyecto
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        # Obtener columnas del proyecto que NO están cifradas
        cursor.execute(
            """
            SELECT c.id, c.name, c.data_type
            FROM columns c
            INNER JOIN tables t ON c.table_id = t.id
            WHERE t.project_id = %s AND (c.is_encrypted = FALSE OR c.is_encrypted IS NULL)
        """,
            (project_id,),
        )

        columns = cursor.fetchall()
        print(f"   📋 Cifrando {len(columns)} columnas...")

        for column in columns:
            try:
                # Cifrar nombre
                name_ciphertext, name_nonce = manager.encrypt_field(column["name"], encryption_key)
                name_encrypted = manager.encode_for_storage(name_ciphertext)
                name_nonce_encoded = manager.encode_for_storage(name_nonce)

                # Cifrar tipo de dato
                type_ciphertext, type_nonce = manager.encrypt_field(
                    column["data_type"], encryption_key
                )
                type_encrypted = manager.encode_for_storage(type_ciphertext)
                type_nonce_encoded = manager.encode_for_storage(type_nonce)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE columns
                        SET name_encrypted = %s,
                            name_nonce = %s,
                            data_type_encrypted = %s,
                            data_type_nonce = %s,
                            is_encrypted = TRUE
                        WHERE id = %s
                    """,
                        (
                            name_encrypted,
                            name_nonce_encoded,
                            type_encrypted,
                            type_nonce_encoded,
                            column["id"],
                        ),
                    )

                stats.columns_encrypted += 1
            except Exception as e:
                stats.add_error("column", column["id"], str(e))
                print(f"      ❌ Error en columna {column['id']}: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def encrypt_project_mappings(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: MigrationStats
):
    """
    Cifra todos los mapeos de un proyecto
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        # Obtener mappings del proyecto que NO están cifrados
        cursor.execute(
            """
            SELECT id, origin_table, origin_column,
                   destination_table, destination_column,
                   transformation_logic
            FROM mappings
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )

        mappings = cursor.fetchall()
        print(f"   🔗 Cifrando {len(mappings)} mappings...")

        for mapping in mappings:
            try:
                encrypted_fields = {}

                # Cifrar cada campo
                fields = [
                    ("origin_table", mapping["origin_table"]),
                    ("origin_column", mapping["origin_column"]),
                    ("destination_table", mapping["destination_table"]),
                    ("destination_column", mapping["destination_column"]),
                ]

                # Agregar transformation_logic si no es NULL
                if mapping["transformation_logic"]:
                    fields.append(("transformation_logic", mapping["transformation_logic"]))

                for field_name, field_value in fields:
                    ciphertext, nonce = manager.encrypt_field(field_value, encryption_key)
                    encrypted_fields[field_name + "_encrypted"] = manager.encode_for_storage(
                        ciphertext
                    )
                    encrypted_fields[field_name + "_nonce"] = manager.encode_for_storage(nonce)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE mappings
                        SET origin_table_encrypted = %(origin_table_encrypted)s,
                            origin_table_nonce = %(origin_table_nonce)s,
                            origin_column_encrypted = %(origin_column_encrypted)s,
                            origin_column_nonce = %(origin_column_nonce)s,
                            destination_table_encrypted = %(destination_table_encrypted)s,
                            destination_table_nonce = %(destination_table_nonce)s,
                            destination_column_encrypted = %(destination_column_encrypted)s,
                            destination_column_nonce = %(destination_column_nonce)s,
                            transformation_logic_encrypted = %(transformation_logic_encrypted)s,
                            transformation_logic_nonce = %(transformation_logic_nonce)s,
                            is_encrypted = TRUE
                        WHERE id = %(id)s
                    """,
                        {**encrypted_fields, "id": mapping["id"]},
                    )

                stats.mappings_encrypted += 1
            except Exception as e:
                stats.add_error("mapping", mapping["id"], str(e))
                print(f"      ❌ Error en mapping {mapping['id']}: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def encrypt_project_versions(
    db,
    project_id: str,
    encryption_key: bytes,
    dry_run: bool,
    stats: MigrationStats,
    limit: int = 1000,
):
    """
    Cifra snapshots de versiones (limitado para no saturar memoria)
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        # Obtener versiones recientes (últimas 1000 por defecto)
        cursor.execute(
            """
            SELECT id, snapshot, diff
            FROM entity_versions
            WHERE project_id = %s
              AND (is_encrypted = FALSE OR is_encrypted IS NULL)
            ORDER BY created_at DESC
            LIMIT %s
        """,
            (project_id, limit),
        )

        versions = cursor.fetchall()
        print(f"   📜 Cifrando {len(versions)} versiones (últimas {limit})...")

        for version in versions:
            try:
                # Cifrar snapshot (siempre existe)
                import json

                snapshot_str = json.dumps(version["snapshot"])
                snapshot_ciphertext, snapshot_nonce = manager.encrypt_field(
                    snapshot_str, encryption_key
                )

                diff_encrypted = None
                diff_nonce = None

                # Cifrar diff si existe
                if version["diff"]:
                    diff_str = json.dumps(version["diff"])
                    diff_ciphertext, diff_nonce = manager.encrypt_field(diff_str, encryption_key)
                    diff_encrypted = manager.encode_for_storage(diff_ciphertext)
                    diff_nonce = manager.encode_for_storage(diff_nonce)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE entity_versions
                        SET snapshot_encrypted = %s,
                            snapshot_nonce = %s,
                            diff_encrypted = %s,
                            diff_nonce = %s,
                            is_encrypted = TRUE
                        WHERE id = %s
                    """,
                        (
                            manager.encode_for_storage(snapshot_ciphertext),
                            manager.encode_for_storage(snapshot_nonce),
                            diff_encrypted,
                            diff_nonce,
                            version["id"],
                        ),
                    )

                stats.versions_encrypted += 1
            except Exception as e:
                stats.add_error("version", version["id"], str(e))
                print(f"      ❌ Error en versión {version['id']}: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def encrypt_project_comments(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: MigrationStats
):
    """
    Cifra contenido de comentarios
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        cursor.execute(
            """
            SELECT id, content
            FROM comments
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )

        comments = cursor.fetchall()
        print(f"   💬 Cifrando {len(comments)} comentarios...")

        for comment in comments:
            try:
                ciphertext, nonce = manager.encrypt_field(comment["content"], encryption_key)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE comments
                        SET content_encrypted = %s,
                            content_nonce = %s,
                            is_encrypted = TRUE
                        WHERE id = %s
                    """,
                        (
                            manager.encode_for_storage(ciphertext),
                            manager.encode_for_storage(nonce),
                            comment["id"],
                        ),
                    )

                stats.comments_encrypted += 1
            except Exception as e:
                stats.add_error("comment", comment["id"], str(e))
                print(f"      ❌ Error en comentario {comment['id']}: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def migrate_project(db, project: Dict[str, Any], passphrase: str, dry_run: bool) -> MigrationStats:
    """
    Migra un proyecto completo al cifrado
    """
    stats = MigrationStats()
    project_id = project["id"]

    print(
        f"\n{'[DRY RUN] ' if dry_run else ''}🔐 Migrando proyecto: {project['name']} ({project_id})"
    )

    try:
        # 1. Crear configuración de cifrado
        print("   1️⃣  Creando configuración de cifrado...")
        if not dry_run:
            master_key_crud.create_project_encryption(db, project_id, passphrase)

        # Derivar clave de cifrado
        encryption_key = master_key_crud.derive_encryption_key_for_project(
            db, project_id, passphrase
        )

        if not encryption_key:
            raise EncryptionError("No se pudo derivar la clave de cifrado")

        # 2. Cifrar tablas
        print("   2️⃣  Cifrando tablas...")
        encrypt_project_tables(db, project_id, encryption_key, dry_run, stats)

        # 3. Cifrar columnas
        print("   3️⃣  Cifrando columnas...")
        encrypt_project_columns(db, project_id, encryption_key, dry_run, stats)

        # 4. Cifrar mappings
        print("   4️⃣  Cifrando mappings...")
        encrypt_project_mappings(db, project_id, encryption_key, dry_run, stats)

        # 5. Cifrar versiones
        print("   5️⃣  Cifrando versiones...")
        encrypt_project_versions(db, project_id, encryption_key, dry_run, stats)

        # 6. Cifrar comentarios
        print("   6️⃣  Cifrando comentarios...")
        encrypt_project_comments(db, project_id, encryption_key, dry_run, stats)

        print(f"   ✅ Proyecto migrado exitosamente")

    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        if not dry_run:
            db.rollback()
        stats.add_error("project", project_id, str(e))

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Migra proyectos existentes a cifrado AES-256-GCM + Argon2id"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="No hace cambios reales, solo muestra qué se haría"
    )
    parser.add_argument("--project-id", type=str, help="Migra solo un proyecto específico (UUID)")
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Número de registros a procesar por lote"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("🔐 MIGRACIÓN A CIFRADO ENTERPRISE (AES-256-GCM + Argon2id)")
    print("=" * 70)

    if args.dry_run:
        print("⚠️  MODO DRY-RUN: No se harán cambios reales en la base de datos")

    # Conectar a la base de datos
    try:
        db = get_db()
        print("✅ Conexión a base de datos establecida")
    except Exception as e:
        print(f"❌ Error conectando a la base de datos: {e}")
        sys.exit(1)

    try:
        # Obtener proyectos sin cifrado
        if args.project_id:
            cursor = db.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT id, name, owner_id, created_at
                FROM projects WHERE id = %s
            """,
                (args.project_id,),
            )
            projects = [dict(row) for row in cursor.fetchall()]
            cursor.close()
        else:
            projects = get_projects_without_encryption(db)

        if not projects:
            print(
                "\n✅ No hay proyectos que migrar. Todos los proyectos ya tienen cifrado configurado."
            )
            sys.exit(0)

        print(f"\n📋 Se encontraron {len(projects)} proyecto(s) sin cifrado:")
        for i, proj in enumerate(projects, 1):
            print(f"   {i}. {proj['name']} ({proj['id']})")

        # Procesar cada proyecto
        all_stats = MigrationStats()

        for project in projects:
            print(f"\n{'='*70}")

            # Solicitar passphrase para este proyecto
            while True:
                passphrase = getpass.getpass(f"\n🔑 Ingresa passphrase para '{project['name']}': ")
                passphrase_confirm = getpass.getpass("🔑 Confirma passphrase: ")

                if passphrase == passphrase_confirm:
                    break
                else:
                    print("❌ Las passphrases no coinciden. Intenta nuevamente.")

            # Migrar proyecto
            stats = migrate_project(db, project, passphrase, args.dry_run)

            # Acumular estadísticas
            all_stats.tables_encrypted += stats.tables_encrypted
            all_stats.columns_encrypted += stats.columns_encrypted
            all_stats.mappings_encrypted += stats.mappings_encrypted
            all_stats.versions_encrypted += stats.versions_encrypted
            all_stats.comments_encrypted += stats.comments_encrypted
            all_stats.errors.extend(stats.errors)

        # Mostrar resumen final
        all_stats.print_summary()

        if args.dry_run:
            print("ℹ️  Esta fue una ejecución DRY-RUN. No se hicieron cambios reales.")
            print("   Ejecuta sin --dry-run para aplicar los cambios.")

    except KeyboardInterrupt:
        print("\n\n⚠️  Migración cancelada por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error durante la migración: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        if db:
            db.close()
            print("\n✅ Conexión a base de datos cerrada")


if __name__ == "__main__":
    main()
