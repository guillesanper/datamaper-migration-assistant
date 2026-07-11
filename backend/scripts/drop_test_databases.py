#!/usr/bin/env python3
"""Drop all test databases to force recreation with Alembic migrations"""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, encoding="utf-8")


def drop_test_databases():
    """Drop all datamap_test* databases"""
    try:
        conn = psycopg2.connect(
            host=os.getenv("TEST_DB_HOST", "localhost"),
            user=os.getenv("TEST_DB_USER", "postgres"),
            password=os.getenv("TEST_DB_PASSWORD", "postgres"),
            database="postgres",
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Get list of test databases
        cursor.execute("SELECT datname FROM pg_database WHERE datname LIKE 'datamap_test%'")
        databases = [row[0] for row in cursor.fetchall()]

        print(f"Found {len(databases)} test databases: {databases}")

        for db_name in databases:
            print(f"\nDropping {db_name}...")

            # Terminate active connections
            cursor.execute(
                """
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = %s
                  AND pid <> pg_backend_pid();
            """,
                (db_name,),
            )

            # Drop database
            cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
            print(f"✓ Dropped {db_name}")

        cursor.close()
        conn.close()

        print(
            f"\n✓ All test databases dropped. They will be recreated with Alembic migrations on next test run."
        )
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys

    sys.exit(0 if drop_test_databases() else 1)
