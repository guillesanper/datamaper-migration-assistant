"""
Tests de la propia infraestructura de tests.

Los tests unitarios que no usan la BD no deben depender de PostgreSQL.
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_pure_unit_tests_run_without_postgres():
    # Puerto 1: nada escucha, cualquier intento de conectar a PostgreSQL falla
    env = {**os.environ, "TEST_DB_HOST": "127.0.0.1", "TEST_DB_PORT": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "test/unit/test_sql_safety.py",
            "-q",
            "-n",
            "0",
            "-p",
            "no:cacheprovider",
            "-W",
            "ignore",
        ],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_external_db_missing_is_skipped_locally(monkeypatch, external_test_db_check):
    monkeypatch.delenv("REQUIRE_TEST_DATABASES", raising=False)

    with pytest.raises(pytest.skip.Exception, match="MySQL de test no disponible"):
        external_test_db_check("MySQL", "127.0.0.1", _closed_port())


def test_external_db_missing_fails_when_required(monkeypatch, external_test_db_check):
    monkeypatch.setenv("REQUIRE_TEST_DATABASES", "1")

    with pytest.raises(pytest.fail.Exception, match="MySQL de test no disponible"):
        external_test_db_check("MySQL", "127.0.0.1", _closed_port())


def test_external_db_listening_is_not_skipped(monkeypatch, external_test_db_check):
    monkeypatch.setenv("REQUIRE_TEST_DATABASES", "1")
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()

        external_test_db_check("MySQL", "127.0.0.1", server.getsockname()[1])
