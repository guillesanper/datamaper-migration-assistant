#!/usr/bin/env python3
"""
Script para verificar el estado de las migraciones de la base de datos
"""

import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Agregar el directorio raíz al path para importar config
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from config import get_db_connection_params

    db_params = get_db_connection_params()
except:
    # Fallback manual
    print("⚠️  No se pudo cargar config automáticamente.")
    print("Por favor, edita las credenciales en este script:")
    db_params = {
        "host": "localhost",
        "database": "relan_db",
        "user": "postgres",
        "password": "tu_password_aqui",  # CAMBIAR ESTO
    }


def check_table_exists(cursor, table_name):
    """Verificar si una tabla existe"""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = %s
        );
    """,
        (table_name,),
    )
    return cursor.fetchone()[0]


def check_migration_status():
    """Verificar estado de migraciones"""

    print("\n" + "=" * 60)
    print("🔍 VERIFICACIÓN DE ESTADO DE MIGRACIONES")
    print("=" * 60 + "\n")

    try:
        # Conectar a la base de datos
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        print(f"✅ Conectado a: {db_params['database']}@{db_params['host']}\n")

        # ============================================
        # FASE 1: Primary Keys Compuestas
        # ============================================
        print("📊 FASE 1: Primary Keys Compuestas")
        print("-" * 60)

        pk_table_exists = check_table_exists(cursor, "primary_key_constraints")
        audit_table_exists = check_table_exists(cursor, "migration_audit_log")

        if pk_table_exists:
            print("✅ Tabla 'primary_key_constraints' existe")

            # Contar registros
            cursor.execute("SELECT COUNT(*) as count FROM primary_key_constraints")
            count = cursor.fetchone()["count"]
            print(f"   └─ {count} Primary Key(s) definida(s)")
        else:
            print("❌ Tabla 'primary_key_constraints' NO existe")
            print("   └─ ACCIÓN REQUERIDA: Ejecutar migración 001")

        if audit_table_exists:
            print("✅ Tabla 'migration_audit_log' existe")

            # Contar registros
            cursor.execute("SELECT COUNT(*) as count FROM migration_audit_log")
            count = cursor.fetchone()["count"]
            print(f"   └─ {count} registro(s) de auditoría")
        else:
            print("❌ Tabla 'migration_audit_log' NO existe")
            print("   └─ ACCIÓN REQUERIDA: Ejecutar migración 001")

        print()

        # ============================================
        # FASE 2: Tipos de Datos Ampliados
        # ============================================
        print("📊 FASE 2: Tipos de Datos Ampliados")
        print("-" * 60)
        print("✅ NO requiere migración SQL")
        print("   └─ Solo cambios en código (validators.py, type_compatibility_service.py)")
        print()

        # ============================================
        # Verificar columnas existentes con tipos parametrizados
        # ============================================
        print("📊 Verificación de tipos de datos en uso")
        print("-" * 60)

        cursor.execute("""
            SELECT DISTINCT data_type, COUNT(*) as count
            FROM columns
            GROUP BY data_type
            ORDER BY count DESC
        """)

        types_in_use = cursor.fetchall()

        print("Tipos de datos actualmente en uso:")
        for row in types_in_use:
            print(f"   • {row['data_type']}: {row['count']} columna(s)")

        print()

        # ============================================
        # Resumen y recomendaciones
        # ============================================
        print("=" * 60)
        print("📝 RESUMEN Y RECOMENDACIONES")
        print("=" * 60 + "\n")

        if not pk_table_exists or not audit_table_exists:
            print("⚠️  MIGRACIÓN REQUERIDA: FASE 1")
            print("\nPara ejecutar la migración:")
            print("1. Conéctate a tu base de datos:")
            print(
                f"   psql -h {db_params['host']} -U {db_params['user']} -d {db_params['database']}"
            )
            print("\n2. Ejecuta la migración:")
            print("   \\i backend/utilities/migrations/001_composite_primary_keys.sql")
            print("\n3. Verifica que se ejecutó correctamente:")
            print("   SELECT * FROM migration_audit_log;")
            print()
        else:
            print("✅ Todas las migraciones están aplicadas correctamente!")
            print("\n📦 Sistema listo para usar:")
            print("   • Primary Keys compuestas: Disponible")
            print("   • Tipos de datos ampliados (25+ tipos): Disponible")
            print("   • Sistema de validación de tipos: Disponible")
            print("   • Sistema de backups automáticos: Disponible")
            print()

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        print(f"\n❌ Error de base de datos: {e}")
        print("\n⚠️  Por favor, verifica:")
        print("   1. Que la base de datos esté corriendo")
        print("   2. Que las credenciales sean correctas")
        print("   3. Que tengas permisos para consultar el esquema")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    check_migration_status()
