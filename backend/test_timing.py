#!/usr/bin/env python3
"""Script para medir tiempos de importación y setup de tests"""

import sys
import time

print("Midiendo tiempos de importación...\n")

# Medir tiempo de imports básicos
start = time.time()
import psycopg2
import pytest
from fastapi.testclient import TestClient

basic_imports = time.time() - start
print(f"✓ Imports básicos: {basic_imports:.3f}s")

# Medir tiempo de cargar .env
start = time.time()
import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, encoding="utf-8")
env_loading = time.time() - start
print(f"✓ Carga de .env: {env_loading:.3f}s")

# Medir tiempo de importar main.app
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6380"
start = time.time()
from main import app

app_import = time.time() - start
print(f"✓ Import de main.app: {app_import:.3f}s")

# Medir tiempo de conexión a DB
start = time.time()
try:
    conn = psycopg2.connect(
        host=os.getenv("TEST_DB_HOST", "localhost"),
        database="datamap_test",
        user=os.getenv("TEST_DB_USER", "postgres"),
        password=os.getenv("TEST_DB_PASSWORD", "postgres"),
        client_encoding="UTF8",
        options="-c client_encoding=UTF8",
    )
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
    table_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    db_check = time.time() - start
    print(f"✓ Verificación DB ({table_count} tablas): {db_check:.3f}s")
except Exception as e:
    db_check = time.time() - start
    print(f"✗ Error en DB: {e}")

total = basic_imports + env_loading + app_import + db_check
print(f"\n📊 Tiempo total de setup: {total:.3f}s")
print(f"\n💡 El componente más lento es: ", end="")
if app_import > max(basic_imports, env_loading, db_check):
    print("import de main.app")
elif db_check > max(basic_imports, env_loading, app_import):
    print("verificación de base de datos")
else:
    print("imports básicos")
