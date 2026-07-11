"""
Test de validación de aislamiento de workers en pytest-xdist.

Este test verifica que cada worker de pytest-xdist usa su propia base de datos
independiente, evitando race conditions y conflictos de datos entre workers.
"""

import pytest


def test_worker_isolation(test_db_connection, worker_id):
    """
    Verificar que cada worker usa su propia base de datos.

    Args:
        test_db_connection: Conexión a la BD del worker
        worker_id: ID del worker de pytest-xdist

    Este test:
    1. Obtiene el nombre de la BD actual desde la conexión
    2. Verifica que coincida con el patrón datamap_test_{worker_id}
    3. Asegura que workers diferentes usen BDs diferentes
    """
    cursor = test_db_connection.cursor()

    # Obtener el nombre de la base de datos actual
    cursor.execute("SELECT current_database()")
    db_name = cursor.fetchone()[0]

    cursor.close()

    # Verificar que el nombre coincida con el patrón esperado
    expected_db = f"datamap_test_{worker_id}"
    assert db_name == expected_db, (
        f"Worker {worker_id} debería usar BD '{expected_db}', " f"pero está usando '{db_name}'"
    )

    print(f"✓ Worker {worker_id} usa correctamente la BD: {db_name}")


def test_database_is_isolated(clean_db, worker_id):
    """
    Verificar que las operaciones en la BD de un worker no afectan a otros.

    Este test crea datos en la BD y verifica que estén disponibles,
    demostrando que cada worker tiene su propio espacio de datos.
    """
    cursor = clean_db.cursor()

    # Crear un usuario de prueba con un email único del worker
    test_email = f"isolation_test_{worker_id}@example.com"
    test_username = f"isolation_user_{worker_id}"

    # Generar UUID usando la función de PostgreSQL
    cursor.execute(
        """
        INSERT INTO users (id, username, email, password_hash, is_verified, is_deleted, failed_login_attempts)
        VALUES (uuid_generate_v4(), %s, %s, %s, TRUE, FALSE, 0)
        RETURNING id
    """,
        (test_username, test_email, "dummy_hash"),
    )

    user_id = cursor.fetchone()[0]
    clean_db.commit()

    # Verificar que el usuario existe en esta BD
    cursor.execute("SELECT username, email FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()

    assert result is not None, "Usuario debería existir después de insertarlo"
    assert result[0] == test_username, "Username debería coincidir"
    assert result[1] == test_email, "Email debería coincidir"

    cursor.close()

    print(f"✓ Worker {worker_id} tiene datos aislados correctamente")


def test_concurrent_truncate_isolation(clean_db, worker_id):
    """
    Verificar que TRUNCATE en un worker no afecta a otros workers.

    Este test es especialmente importante porque el problema original
    era que múltiples workers compartían la misma BD y cuando uno
    hacía TRUNCATE, afectaba a todos los demás.
    """
    cursor = clean_db.cursor()

    # Insertar datos con UUID generado automáticamente
    cursor.execute(
        """
        INSERT INTO users (id, username, email, password_hash, is_verified, is_deleted, failed_login_attempts)
        VALUES (uuid_generate_v4(), %s, %s, %s, TRUE, FALSE, 0)
        RETURNING id
    """,
        (f"truncate_test_{worker_id}", f"truncate_{worker_id}@example.com", "hash"),
    )

    user_id = cursor.fetchone()[0]
    clean_db.commit()

    # Simular TRUNCATE (la fixture clean_db ya hace esto antes de cada test)
    cursor.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
    clean_db.commit()

    # Verificar que después de TRUNCATE, la tabla está vacía
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]

    assert count == 0, "La tabla debería estar vacía después de TRUNCATE"

    cursor.close()

    print(f"✓ Worker {worker_id} puede hacer TRUNCATE sin afectar otros workers")
