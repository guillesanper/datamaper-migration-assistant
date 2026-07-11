"""
Script para diagnosticar el estado de la sesión de encriptación
"""

import requests

# Configuración
BASE_URL = "http://localhost:8000"  # Ajusta según tu setup
PROJECT_ID = "50369e15-943a-4d50-a3a8-f25a9cd13297"

# Cookies que tienes (copia del navegador)
cookies = {
    "csrftoken": "TVC9lPhxbzrOxg5P7mGnEbLwHE1qrmP7",
    "session": "IjVYMXkzbEVTMnF4NFAzcmJMT0ExZUdmWWVSWlVsRTFvamttQXROZXg4T1Ui.PwByNDtyUAzt8Tu10agAJLQoSk0",
    f"enc_session_{PROJECT_ID}": "zGotJR6XplJvLRBO6o7VHF-RSvi2xR9L-LTsXYV8VI0",
}

print("=" * 80)
print("DIAGNÓSTICO DE SESIÓN DE ENCRIPTACIÓN")
print("=" * 80)

# 1. Verificar estado de la sesión específica del proyecto
print("\n1. Verificando sesión del proyecto...")
response = requests.get(
    f"{BASE_URL}/api/projects/{PROJECT_ID}/encryption/debug/session-check", cookies=cookies
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"  - Cookie existe: {data.get('cookie_exists')}")
    print(f"  - Status: {data.get('status')}")
    print(f"  - Sesión encontrada: {data.get('session_found', False)}")
    if data.get("session_token_preview"):
        print(f"  - Token preview: {data.get('session_token_preview')}")
    if data.get("session_user_id"):
        print(f"  - User ID de sesión: {data.get('session_user_id')}")
    print(f"  - Tiene encryption_key: {data.get('has_encryption_key')}")
    print(f"  - Segundos restantes: {data.get('remaining_seconds')}")
    print(f"  - Mensaje: {data.get('message', 'N/A')}")
    print("\nRespuesta completa:")
    import json

    print(json.dumps(data, indent=2))
else:
    print(f"  ERROR: {response.text}")

# 2. Verificar estadísticas generales del caché
print("\n2. Verificando estadísticas del caché...")
response = requests.get(f"{BASE_URL}/api/encryption/debug/cache-stats", cookies=cookies)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    stats = data.get("stats", {})
    print(f"  - Sesiones totales: {stats.get('total_sessions')}")
    print(f"  - Sesiones activas: {stats.get('active_sessions')}")
    print(f"  - Sesiones expiradas: {stats.get('expired_sessions')}")
    print(f"  - User ID actual: {data.get('user_id', 'N/A')[:8]}...")
else:
    print(f"  ERROR: {response.text}")

# 3. Verificar estado general del proyecto
print("\n3. Verificando estado de encriptación del proyecto...")
response = requests.get(
    f"{BASE_URL}/api/projects/{PROJECT_ID}/encryption/session-status", cookies=cookies
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"  - Tiene sesión: {data.get('has_session')}")
    print(f"  - Project ID: {data.get('project_id')}")
    print(f"  - Expira en: {data.get('expires_in_seconds')} segundos")
    if "reason" in data:
        print(f"  - Razón: {data.get('reason')}")
else:
    print(f"  ERROR: {response.text}")


print("\n" + "=" * 80)
print("DIAGNÓSTICO COMPLETADO")
print("=" * 80)
