#!/usr/bin/env python3
"""
Script para Cifrar Datos Existentes
Cifra datos que ya existen en proyectos con configuración de cifrado

Este script es para proyectos que:
- YA tienen configuración de cifrado (project_encryption existe)
- Tienen datos sin cifrar (is_encrypted = FALSE o NULL)

Uso:
    python encrypt_existing_data.py --project-id <UUID> [--dry-run]

Opciones:
    --project-id    : ID del proyecto a cifrar (requerido)
    --dry-run       : No hace cambios reales, solo muestra qué se haría
    --skip-versions : No cifrar versiones (más rápido)

Autor: DataMap Security Team
"""

import argparse
import getpass
import os
import sys
from typing import Any, Dict

import psycopg2
from psycopg2.extras import RealDictCursor

# Agregar directorio padre al path para imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.crud import master_key_crud
from app.database.database import get_db
from app.utils.encryption import EncryptionManager


class EncryptionStats:
    """Estadísticas del cifrado"""

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
        print("📊 RESUMEN DE CIFRADO")
        print("=" * 70)
        print(f"✅ Tablas cifradas:     {self.tables_encrypted}")
        print(f"✅ Columnas cifradas:   {self.columns_encrypted}")
        print(f"✅ Mappings cifrados:   {self.mappings_encrypted}")
        print(f"✅ Versiones cifradas:  {self.versions_encrypted}")
        print(f"✅ Comentarios cifrados: {self.comments_encrypted}")
        print(f"❌ Errores:             {len(self.errors)}")

        if self.errors:
            print("\n❌ ERRORES ENCONTRADOS:")
            for error in self.errors[:10]:
                print(f"   - {error['entity_type']} {error['entity_id']}: {error['error']}")
            if len(self.errors) > 10:
                print(f"   ... y {len(self.errors) - 10} errores más")
        print("=" * 70 + "\n")


def get_project_info(db, project_id: str) -> Dict[str, Any]:
    """Obtiene información del proyecto"""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT p.id, p.name, p.owner_id,
                   pe.encryption_enabled, pe.created_at as encryption_created_at
            FROM projects p
            LEFT JOIN project_encryption pe ON p.id = pe.project_id
            WHERE p.id = %s
        """,
            (project_id,),
        )

        result = cursor.fetchone()
        return dict(result) if result else None
    finally:
        cursor.close()


def count_unencrypted_data(db, project_id: str) -> Dict[str, int]:
    """Cuenta cuántos datos sin cifrar tiene el proyecto"""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    counts = {}

    try:
        # Tablas sin cifrar
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM tables
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )
        counts["tables"] = cursor.fetchone()["count"]

        # Columnas sin cifrar
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM columns c
            INNER JOIN tables t ON c.table_id = t.id
            WHERE t.project_id = %s AND (c.is_encrypted = FALSE OR c.is_encrypted IS NULL)
        """,
            (project_id,),
        )
        counts["columns"] = cursor.fetchone()["count"]

        # Mappings sin cifrar
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM mappings
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )
        counts["mappings"] = cursor.fetchone()["count"]

        # Versiones sin cifrar
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM entity_versions
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )
        counts["versions"] = cursor.fetchone()["count"]

        # Comentarios sin cifrar
        cursor.execute(
            """
            SELECT COUNT(*) as count FROM comments
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )
        counts["comments"] = cursor.fetchone()["count"]

        return counts
    finally:
        cursor.close()


def encrypt_tables(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: EncryptionStats
):
    """Cifra tablas sin cifrar"""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        cursor.execute(
            """
            SELECT id, name FROM tables
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )

        tables = cursor.fetchall()
        if not tables:
            print("   ✅ No hay tablas para cifrar")
            return

        print(f"   🗂️  Cifrando {len(tables)} tablas...")

        for table in tables:
            try:
                ciphertext, nonce = manager.encrypt_field(table["name"], encryption_key)
                name_encrypted = manager.encode_for_storage(ciphertext)
                name_nonce = manager.encode_for_storage(nonce)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE tables
                        SET name_encrypted = %s, name_nonce = %s, is_encrypted = TRUE
                        WHERE id = %s
                    """,
                        (name_encrypted, name_nonce, table["id"]),
                    )

                stats.tables_encrypted += 1
            except Exception as e:
                stats.add_error("table", table["id"], str(e))
                print(f"      ❌ Error: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def encrypt_columns(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: EncryptionStats
):
    """Cifra columnas sin cifrar"""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
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
        if not columns:
            print("   ✅ No hay columnas para cifrar")
            return

        print(f"   📋 Cifrando {len(columns)} columnas...")

        for column in columns:
            try:
                # Cifrar nombre
                name_ciphertext, name_nonce = manager.encrypt_field(column["name"], encryption_key)
                name_encrypted = manager.encode_for_storage(name_ciphertext)
                name_nonce_encoded = manager.encode_for_storage(name_nonce)

                # Cifrar tipo
                type_ciphertext, type_nonce = manager.encrypt_field(
                    column["data_type"], encryption_key
                )
                type_encrypted = manager.encode_for_storage(type_ciphertext)
                type_nonce_encoded = manager.encode_for_storage(type_nonce)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE columns
                        SET name_encrypted = %s, name_nonce = %s,
                            data_type_encrypted = %s, data_type_nonce = %s,
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
                print(f"      ❌ Error: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def encrypt_mappings(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: EncryptionStats
):
    """Cifra mappings sin cifrar"""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        cursor.execute(
            """
            SELECT id, origin_table, origin_column, destination_table, destination_column, transformation_logic
            FROM mappings
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )

        mappings = cursor.fetchall()
        if not mappings:
            print("   ✅ No hay mappings para cifrar")
            return

        print(f"   🔗 Cifrando {len(mappings)} mappings...")

        for mapping in mappings:
            try:
                encrypted_fields = {}

                fields = [
                    ("origin_table", mapping["origin_table"]),
                    ("origin_column", mapping["origin_column"]),
                    ("destination_table", mapping["destination_table"]),
                    ("destination_column", mapping["destination_column"]),
                ]

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
                print(f"      ❌ Error: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def encrypt_versions(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: EncryptionStats
):
    """Cifra versiones sin cifrar"""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        cursor.execute(
            """
            SELECT id, snapshot, diff FROM entity_versions
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
            ORDER BY created_at DESC
            LIMIT 1000
        """,
            (project_id,),
        )

        versions = cursor.fetchall()
        if not versions:
            print("   ✅ No hay versiones para cifrar")
            return

        print(f"   📜 Cifrando {len(versions)} versiones...")

        for version in versions:
            try:
                import json

                snapshot_str = json.dumps(version["snapshot"])
                snapshot_ciphertext, snapshot_nonce = manager.encrypt_field(
                    snapshot_str, encryption_key
                )

                diff_encrypted = None
                diff_nonce = None

                if version["diff"]:
                    diff_str = json.dumps(version["diff"])
                    diff_ciphertext, diff_nonce_raw = manager.encrypt_field(
                        diff_str, encryption_key
                    )
                    diff_encrypted = manager.encode_for_storage(diff_ciphertext)
                    diff_nonce = manager.encode_for_storage(diff_nonce_raw)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE entity_versions
                        SET snapshot_encrypted = %s, snapshot_nonce = %s,
                            diff_encrypted = %s, diff_nonce = %s, is_encrypted = TRUE
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
                print(f"      ❌ Error: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def encrypt_comments(
    db, project_id: str, encryption_key: bytes, dry_run: bool, stats: EncryptionStats
):
    """Cifra comentarios sin cifrar"""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        cursor.execute(
            """
            SELECT id, content FROM comments
            WHERE project_id = %s AND (is_encrypted = FALSE OR is_encrypted IS NULL)
        """,
            (project_id,),
        )

        comments = cursor.fetchall()
        if not comments:
            print("   ✅ No hay comentarios para cifrar")
            return

        print(f"   💬 Cifrando {len(comments)} comentarios...")

        for comment in comments:
            try:
                ciphertext, nonce = manager.encrypt_field(comment["content"], encryption_key)

                if not dry_run:
                    cursor.execute(
                        """
                        UPDATE comments
                        SET content_encrypted = %s, content_nonce = %s, is_encrypted = TRUE
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
                print(f"      ❌ Error: {e}")

        if not dry_run:
            db.commit()

    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser(
        description="Cifra datos existentes en un proyecto con configuración de cifrado"
    )
    parser.add_argument(
        "--project-id", type=str, required=True, help="ID del proyecto a cifrar (UUID)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="No hace cambios reales, solo muestra qué se haría"
    )
    parser.add_argument(
        "--skip-versions", action="store_true", help="No cifrar versiones (más rápido)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("🔐 CIFRADO DE DATOS EXISTENTES")
    print("=" * 70)

    if args.dry_run:
        print("⚠️  MODO DRY-RUN: No se harán cambios reales")

    # Conectar a BD
    try:
        db = get_db()
        print("✅ Conexión establecida")
    except Exception as e:
        print(f"❌ Error conectando: {e}")
        sys.exit(1)

    try:
        # Obtener info del proyecto
        project = get_project_info(db, args.project_id)
        if not project:
            print(f"❌ Proyecto {args.project_id} no encontrado")
            sys.exit(1)

        print(f"\n📋 Proyecto: {project['name']}")

        # Verificar que tiene cifrado configurado
        if not project["encryption_enabled"]:
            print("❌ Este proyecto no tiene cifrado habilitado")
            print("   Primero activa el cifrado desde la interfaz web")
            sys.exit(1)

        # Contar datos sin cifrar
        counts = count_unencrypted_data(db, args.project_id)
        total = sum(counts.values())

        if total == 0:
            print("✅ Todos los datos ya están cifrados")
            sys.exit(0)

        print(f"\n📊 Datos sin cifrar:")
        print(f"   - Tablas: {counts['tables']}")
        print(f"   - Columnas: {counts['columns']}")
        print(f"   - Mappings: {counts['mappings']}")
        print(f"   - Versiones: {counts['versions']}")
        print(f"   - Comentarios: {counts['comments']}")
        print(f"   TOTAL: {total} registros")

        # Solicitar passphrase
        print("\n🔑 Necesitas la passphrase del proyecto para continuar")
        passphrase = getpass.getpass("Passphrase: ")

        # Verificar passphrase
        is_valid = master_key_crud.verify_project_passphrase(db, args.project_id, passphrase)
        if not is_valid:
            print("❌ Passphrase incorrecta")
            sys.exit(1)

        print("✅ Passphrase verificada")

        # Derivar encryption key
        encryption_key = master_key_crud.derive_encryption_key_for_project(
            db, args.project_id, passphrase
        )

        if not encryption_key:
            print("❌ No se pudo derivar la clave de cifrado")
            sys.exit(1)

        # Cifrar datos
        stats = EncryptionStats()

        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}🔐 Iniciando cifrado...")

        encrypt_tables(db, args.project_id, encryption_key, args.dry_run, stats)
        encrypt_columns(db, args.project_id, encryption_key, args.dry_run, stats)
        encrypt_mappings(db, args.project_id, encryption_key, args.dry_run, stats)

        if not args.skip_versions:
            encrypt_versions(db, args.project_id, encryption_key, args.dry_run, stats)

        encrypt_comments(db, args.project_id, encryption_key, args.dry_run, stats)

        # Resumen
        stats.print_summary()

        if args.dry_run:
            print("ℹ️  Esta fue una ejecución DRY-RUN")
            print("   Ejecuta sin --dry-run para aplicar los cambios")
        else:
            print("✅ Cifrado completado exitosamente")

    except KeyboardInterrupt:
        print("\n\n⚠️  Operación cancelada")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        if db:
            db.close()
            print("\n✅ Conexión cerrada")


if __name__ == "__main__":
    main()
