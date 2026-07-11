#!/usr/bin/env python3
"""
Script para ejecutar la migración 004: Fix Encryption Nullable Fields

Este script aplica la migración 004 que permite que los campos name, data_type, etc.
sean NULL cuando están cifrados.

Uso:
    python run_migration_004.py
"""

import os
import sys
from pathlib import Path

import psycopg2

# Agregar el directorio raíz al path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database.database import get_db_connection_params


def run_migration():
    """Ejecuta la migración 004"""

    # Leer el archivo SQL
    migration_file = Path(__file__).parent / "004_fix_encryption_nullable_fields.sql"

    if not migration_file.exists():
        print(f"❌ Error: No se encontró el archivo {migration_file}")
        return False

    with open(migration_file, "r", encoding="utf-8") as f:
        migration_sql = f.read()

    # Conectar a la base de datos
    try:
        conn_params = get_db_connection_params()
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = False

        cursor = conn.cursor()

        print("🚀 Ejecutando migración 004: Fix Encryption Nullable Fields...")
        print("-" * 70)

        # Ejecutar la migración
        cursor.execute(migration_sql)

        # Commit
        conn.commit()

        print("✅ Migración 004 ejecutada exitosamente")
        print("-" * 70)

        # Verificar que los constraints fueron creados
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name IN ('tables', 'columns', 'mappings')
              AND constraint_type = 'CHECK'
              AND constraint_name LIKE '%encrypted%'
            ORDER BY constraint_name
        """)

        constraints = cursor.fetchall()
        print(f"\n📋 Constraints CHECK creados ({len(constraints)}):")
        for constraint in constraints:
            print(f"   - {constraint[0]}")

        cursor.close()
        conn.close()

        return True

    except psycopg2.Error as e:
        print(f"❌ Error ejecutando migración: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("MIGRACIÓN 004: Fix Encryption Nullable Fields")
    print("=" * 70)
    print()

    success = run_migration()

    if success:
        print()
        print("✅ Migración completada con éxito")
        print()
        print("Ahora puedes activar el cifrado en tus proyectos sin errores.")
        sys.exit(0)
    else:
        print()
        print("❌ La migración falló. Revisa los errores arriba.")
        sys.exit(1)
