#!/usr/bin/env python3
"""
Script para ejecutar la migración 005: Mapping Source Types (Import + Connector)

Este script aplica la migración 005 que agrega soporte para modo híbrido en mappings,
permitiendo usar tanto esquemas importados (import) como conectores dinámicos (connector).

Uso:
    python run_migration_005.py
"""

import os
import sys
from pathlib import Path

import psycopg2

# Agregar el directorio raíz al path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database.database import get_db_connection_params


def run_migration():
    """Ejecuta la migración 005"""

    # Leer el archivo SQL
    migration_file = Path(__file__).parent / "005_mapping_source_types.sql"

    if not migration_file.exists():
        print(f"❌ Error: No se encontró el archivo {migration_file}")
        return False

    with open(migration_file, "r", encoding="utf-8") as f:
        migration_sql = f.read()

    # Conectar a la base de datos
    conn = None
    try:
        conn_params = get_db_connection_params()
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = False

        cursor = conn.cursor()

        print("🚀 Ejecutando migración 005: Mapping Source Types (Import + Connector)...")
        print("-" * 70)

        # Ejecutar la migración
        cursor.execute(migration_sql)

        # Commit
        conn.commit()

        print("✅ Migración 005 ejecutada exitosamente")
        print("-" * 70)

        # Verificar columnas creadas
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'mappings'
                AND column_name IN (
                    'origin_source_type', 'origin_table_hash', 'origin_column_hash',
                    'origin_session_id', 'origin_table_id',
                    'destination_source_type', 'destination_table_hash', 'destination_column_hash',
                    'destination_session_id', 'destination_table_id'
                )
            ORDER BY column_name
        """)

        columns = cursor.fetchall()
        print(f"\n📋 Columnas agregadas ({len(columns)} de 10 esperadas):")
        for col in columns:
            print(f"   - {col[0]:30} {col[1]:20} NULL={col[2]}")

        # Verificar constraints creados
        cursor.execute("""
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_name = 'mappings'
              AND (constraint_name LIKE 'chk_%_requirements'
                   OR constraint_name LIKE 'chk_%_source_type_values')
            ORDER BY constraint_name
        """)

        constraints = cursor.fetchall()
        print(f"\n🔒 Constraints de integridad creados ({len(constraints)}):")
        for constraint in constraints:
            print(f"   - {constraint[0]:50} [{constraint[1]}]")

        # Verificar índices creados
        cursor.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'mappings'
              AND indexname LIKE 'idx_mappings_%'
              AND indexname IN (
                  'idx_mappings_origin_source_type',
                  'idx_mappings_destination_source_type',
                  'idx_mappings_origin_session_id',
                  'idx_mappings_destination_session_id',
                  'idx_mappings_origin_table_id',
                  'idx_mappings_destination_table_id',
                  'idx_mappings_origin_hashes',
                  'idx_mappings_destination_hashes',
                  'idx_mappings_project_modes'
              )
            ORDER BY indexname
        """)

        indexes = cursor.fetchall()
        print(f"\n⚡ Índices creados ({len(indexes)} de 9 esperados):")
        for index in indexes:
            print(f"   - {index[0]}")

        # Verificar funciones creadas
        cursor.execute("""
            SELECT routine_name
            FROM information_schema.routines
            WHERE routine_schema = 'public'
              AND routine_type = 'FUNCTION'
              AND routine_name IN (
                  'get_project_mapping_mode_stats',
                  'check_mapping_sessions_valid',
                  'cleanup_orphaned_connector_mappings'
              )
            ORDER BY routine_name
        """)

        functions = cursor.fetchall()
        print(f"\n📈 Funciones creadas ({len(functions)} de 3 esperadas):")
        for func in functions:
            print(f"   - {func[0]}()")

        # Verificar vista creada
        cursor.execute("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
              AND table_name = 'v_mappings_with_modes'
        """)

        views = cursor.fetchall()
        print(f"\n👁️ Vistas creadas ({len(views)} de 1 esperada):")
        for view in views:
            print(f"   - {view[0]}")

        # Verificar migración de datos existentes
        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE origin_source_type = 'import') as origin_import,
                   COUNT(*) FILTER (WHERE destination_source_type = 'import') as dest_import
            FROM mappings
        """)

        stats = cursor.fetchone()
        if stats[0] > 0:
            print(f"\n🔄 Migración de datos existentes:")
            print(f"   - Total mappings: {stats[0]}")
            print(f"   - Origen modo import: {stats[1]}")
            print(f"   - Destino modo import: {stats[2]}")

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
    print("MIGRACIÓN 005: Sistema de Mappings Híbrido (Import + Connector)")
    print("=" * 70)
    print()
    print("Esta migración agrega soporte para:")
    print("  - Modo Import: Esquemas importados con cifrado AES-256-GCM")
    print("  - Modo Connector: Conexión dinámica con hashing SHA-256")
    print("  - Modo Híbrido: Combinaciones flexibles origen/destino")
    print()

    success = run_migration()

    if success:
        print()
        print("✅ Migración completada con éxito")
        print()
        print("Ahora puedes:")
        print("  1. Crear mappings con modo import (legacy)")
        print("  2. Crear mappings con modo connector (nuevo)")
        print("  3. Combinar ambos modos en un mismo mapping (híbrido)")
        print()
        print("Modos disponibles:")
        print("  - IMPORT → IMPORT")
        print("  - IMPORT → CONNECTOR")
        print("  - CONNECTOR → IMPORT")
        print("  - CONNECTOR → CONNECTOR")
        sys.exit(0)
    else:
        print()
        print("❌ La migración falló. Revisa los errores arriba.")
        sys.exit(1)
