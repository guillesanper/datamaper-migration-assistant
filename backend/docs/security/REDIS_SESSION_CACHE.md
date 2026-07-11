# Redis Session Cache - Arquitectura Técnica

**Subsistema**: Encryption Session Management
**Fecha de implementación**: 2025-01-06
**Estado**: ✅ PRODUCCIÓN
**Tipo**: Infraestructura de Seguridad

---

## 📋 Tabla de Contenidos

1. [Arquitectura General](#arquitectura-general)
2. [Estructura de Datos](#estructura-de-datos)
3. [Flujos de Operación](#flujos-de-operación)
4. [Connection Pooling](#connection-pooling)
5. [TTL y Expiración](#ttl-y-expiración)
6. [Token Rotation](#token-rotation)
7. [Indexación](#indexación)
8. [Serialización](#serialización)
9. [Performance](#performance)
10. [Security Considerations](#security-considerations)

---

## 🏗️ Arquitectura General

### Componentes del Sistema

```
┌────────────────────────────────────────────────────────┐
│                   Application Layer                    │
│                                                        │
│  ┌──────────────────────────────────────────────────┐│
│  │  RedisEncryptionSessionCache                     ││
│  │  (backend/app/utils/redis_session_cache.py)      ││
│  │                                                   ││
│  │  API:                                             ││
│  │  - create_session()                               ││
│  │  - get_session()                                  ││
│  │  - invalidate_session()                           ││
│  │  - rotate_token()                                 ││
│  │  - invalidate_project_sessions()                  ││
│  │  - invalidate_user_sessions()                     ││
│  └─────────────────────┬────────────────────────────┘│
│                        │                              │
└────────────────────────┼──────────────────────────────┘
                         │
                         │ Uses
                         ▼
┌────────────────────────────────────────────────────────┐
│              Redis Client Singleton                    │
│       (backend/app/utils/redis_client.py)              │
│                                                        │
│  ┌──────────────────────────────────────────────────┐│
│  │  Connection Pool (max 20 connections)            ││
│  │  - Exponential backoff retry                     ││
│  │  - Auto-reconnect                                ││
│  │  - Health checks                                 ││
│  │  - SSL/TLS support                               ││
│  └──────────────────────┬───────────────────────────┘│
│                         │                              │
└─────────────────────────┼──────────────────────────────┘
                          │
                          │ TCP/TLS
                          ▼
┌────────────────────────────────────────────────────────┐
│                  Redis Server                          │
│                                                        │
│  - Version: 7.x                                        │
│  - Persistence: AOF (appendonly yes)                   │
│  - Eviction: allkeys-lru                               │
│  - MaxMemory: 25MB (Starter) / 100MB+ (Prod)          │
│  - SSL: Required in production                         │
└────────────────────────────────────────────────────────┘
```

### Responsabilidades por Componente

| Componente | Responsabilidad |
|------------|-----------------|
| **RedisEncryptionSessionCache** | Lógica de negocio de sesiones, validación, indexación |
| **RedisClient** | Connection pooling, retry logic, health checks |
| **Redis Server** | Almacenamiento persistente, TTL automático, eviction |

---

## 🗄️ Estructura de Datos

### Redis Key Patterns

```
enc_session:{project_id}:{session_token}
├── Value: JSON serializado
├── Type: String
└── TTL: ENCRYPTION_SESSION_TIMEOUT (default: 10800s / 3h)

enc_session:project_index:{project_id}
├── Value: Set de session_tokens
├── Type: Set
└── TTL: SESSION_TIMEOUT + 60s (margen de 1 minuto)

enc_session:user_index:{user_id}
├── Value: Set de "project_id:session_token"
├── Type: Set
└── TTL: SESSION_TIMEOUT + 60s
```

### Ejemplo de Session Data

```json
{
  "project_id": "abc123-456-def-789",
  "encryption_key": "dGhpc19pc19hX2Jhc2U2NF9lbmNvZGVkX2tleQ==",
  "user_id": "user-xyz-123",
  "expires_at": "2025-01-06T18:00:00.000000+00:00",
  "created_at": "2025-01-06T15:00:00.000000+00:00"
}
```

### Ejemplo de Rotating Session

Durante token rotation (grace period):

```json
{
  "project_id": "abc123-456-def-789",
  "encryption_key": "dGhpc19pc19hX2Jhc2U2NF9lbmNvZGVkX2tleQ==",
  "user_id": "user-xyz-123",
  "expires_at": "2025-01-06T18:00:00.000000+00:00",
  "created_at": "2025-01-06T15:00:00.000000+00:00",
  "rotating": true,
  "rotated_to": "new-session-token-xyz",
  "rotation_expires": "2025-01-06T15:00:30.000000+00:00"
}
```

---

## 🔄 Flujos de Operación

### 1. Create Session

```python
# Input
project_id = "abc-123"
encryption_key = b"32_bytes_aes_key"
user_id = "user-456"
timeout = 10800  # 3 horas

# Flujo
session_token = secrets.token_urlsafe(32)  # CSPRNG
expires_at = now + timedelta(seconds=timeout)

session_data = {
    'project_id': project_id,
    'encryption_key': base64.b64encode(encryption_key).decode(),
    'user_id': user_id,
    'expires_at': expires_at.isoformat(),
    'created_at': now.isoformat()
}

session_json = json.dumps(session_data)
session_key = f"enc_session:{project_id}:{session_token}"

# Redis operations
redis.setex(session_key, timeout, session_json)  # Atomic set + TTL

# Indexación
redis.sadd(f"enc_session:project_index:{project_id}", session_token)
redis.expire(f"enc_session:project_index:{project_id}", timeout + 60)

redis.sadd(f"enc_session:user_index:{user_id}", f"{project_id}:{session_token}")
redis.expire(f"enc_session:user_index:{user_id}", timeout + 60)

# Output
return session_token
```

**Complejidad**: O(1)
**Redis commands**: 6 (1 SETEX + 2 SADD + 2 EXPIRE + 1 implícito)

### 2. Get Session

#### Caso 1: Con project_id (Búsqueda directa)

```python
# Input
session_token = "xyz789..."
project_id = "abc-123"

# Redis operation
session_key = f"enc_session:{project_id}:{session_token}"
session_json = redis.get(session_key)  # O(1)

if not session_json:
    return None

session = json.loads(session_json)

# Verificar expiración manual (redundante, Redis TTL ya lo hace)
if now > datetime.fromisoformat(session['expires_at']):
    return None

# Extraer encryption_key
encryption_key = base64.b64decode(session['encryption_key'])

return {
    'project_id': session['project_id'],
    'encryption_key': encryption_key,  # bytes
    'user_id': session['user_id'],
    'expires_at': datetime.fromisoformat(session['expires_at'])
}
```

**Complejidad**: O(1)
**Redis commands**: 1 GET

#### Caso 2: Sin project_id (Búsqueda por pattern)

```python
# Input
session_token = "xyz789..."

# Redis operation (menos eficiente)
pattern = f"enc_session:*:{session_token}"
keys = redis.scan_iter(match=pattern, count=100)  # O(N)

for key in keys:
    session_json = redis.get(key)
    # ... mismo flujo
```

**Complejidad**: O(N) donde N = número de keys en Redis
**Redis commands**: SCAN + GET

**Recomendación**: Siempre pasar `project_id` cuando sea posible.

### 3. Token Rotation

```python
# Input
old_token = "abc123..."
grace_period = 30  # segundos

# 1. Buscar sesión antigua
pattern = f"enc_session:*:{old_token}"
old_keys = list(redis.scan_iter(match=pattern, count=100))

if not old_keys:
    return None

old_key = old_keys[0]
project_id = old_key.split(':')[1]

# 2. Leer datos de sesión
session_json = redis.get(old_key)
session = json.loads(session_json)

# 3. Verificar si ya está rotando
if session.get('rotating'):
    return session.get('rotated_to')

# 4. Generar nuevo token
new_token = secrets.token_urlsafe(32)

# 5. Crear nueva sesión (sin marcar como rotating)
ttl = redis.ttl(old_key)  # TTL restante
new_key = f"enc_session:{project_id}:{new_token}"
redis.setex(new_key, ttl, session_json)

# 6. Marcar token viejo como rotating
session['rotating'] = True
session['rotated_to'] = new_token
session['rotation_expires'] = (now + timedelta(seconds=grace_period)).isoformat()

rotated_json = json.dumps(session)
redis.setex(old_key, grace_period, rotated_json)  # Sobrescribir con TTL corto

# 7. Actualizar índices
redis.sadd(f"enc_session:project_index:{project_id}", new_token)
redis.sadd(f"enc_session:user_index:{session['user_id']}", f"{project_id}:{new_token}")

# Output
return new_token
```

**Complejidad**: O(N) para SCAN, luego O(1)
**Redis commands**: SCAN + GET + TTL + 2 SETEX + 2 SADD

### 4. Invalidate Project Sessions

```python
# Input
project_id = "abc-123"

# 1. Leer índice de proyecto
index_key = f"enc_session:project_index:{project_id}"
tokens = redis.smembers(index_key)  # O(N) donde N = tokens del proyecto

# 2. Construir keys a eliminar
keys_to_delete = [
    f"enc_session:{project_id}:{token}"
    for token in tokens
]

# 3. Eliminar en batch
if keys_to_delete:
    deleted = redis.delete(*keys_to_delete)  # O(N)

# 4. Eliminar índice
redis.delete(index_key)

# Output
return len(keys_to_delete)
```

**Complejidad**: O(N) donde N = número de sesiones del proyecto
**Redis commands**: SMEMBERS + DELETE (batch) + DELETE

---

## 🔌 Connection Pooling

### Configuración del Pool

```python
# backend/app/utils/redis_client.py

ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True,          # Auto-decode bytes → str
    max_connections=20,              # Max connections en pool
    socket_timeout=5,                # Timeout por operación
    socket_connect_timeout=5,        # Timeout de conexión
    socket_keepalive=True,           # TCP keepalive
    retry_on_timeout=True,           # Retry automático
    connection_class=SSLConnection,  # SSL en producción
    retry=Retry(
        ExponentialBackoff(base=0.5, cap=3),  # 0.5s, 1s, 2s, 3s
        retries=3
    )
)
```

### Gestión de Conexiones

```
Pool State:
┌─────────────────────────────────┐
│  Connection Pool (20 max)       │
│                                 │
│  ┌───┐ ┌───┐ ┌───┐ ┌───┐      │
│  │ 1 │ │ 2 │ │ 3 │ │...│ ← Available
│  └───┘ └───┘ └───┘ └───┘      │
│                                 │
│  ┌───┐ ┌───┐                   │
│  │ 5 │ │ 6 │ ← In use          │
│  └───┘ └───┘                   │
└─────────────────────────────────┘

Request lifecycle:
1. get_connection() → Saca del pool
2. execute_command()
3. release() → Devuelve al pool
```

### Health Checks

```python
def health_check(max_retries=5, retry_delay=2):
    """Verifica conexión con retries"""
    for attempt in range(1, max_retries + 1):
        try:
            redis.ping()
            return True
        except RedisError:
            if attempt == max_retries:
                raise
            time.sleep(retry_delay)
    return False
```

---

## ⏰ TTL y Expiración

### TTL Automático con SETEX

```python
# Atomic set + expire
redis.setex(key, timeout_seconds, value)

# Equivalente a:
# redis.set(key, value)
# redis.expire(key, timeout_seconds)
# Pero SETEX es atómico (mejor)
```

### TTL de Índices

Los índices tienen TTL ligeramente mayor que las sesiones:

```python
session_ttl = 10800  # 3 horas
index_ttl = 10800 + 60  # 3 horas + 1 minuto

# Razón: Evitar race condition donde:
# - Sesión expira a las 18:00:00
# - Índice expira a las 17:59:59
# - GET session entre 17:59:59 y 18:00:00
#   → Sesión existe pero índice no
#   → Cleanup no puede encontrar sesión
```

### Verificación de Expiración

```python
# Redis TTL maneja expiración automáticamente
# Verificación manual es redundante pero prudente

session = json.loads(redis.get(key))
now = datetime.now(timezone.utc)

if now > datetime.fromisoformat(session['expires_at']):
    # Sesión expirada (Redis debería haberla eliminado)
    return None
```

### Cleanup Background Task

```python
# backend/app/tasks/encryption_cleanup.py

async def cleanup_encryption_sessions():
    """
    Cleanup de sesiones expiradas (redundante con Redis TTL)

    Redis TTL ya elimina sesiones automáticamente.
    Este task solo limpia índices huérfanos.
    """
    cache = get_encryption_session_cache()
    removed = cache.cleanup_expired()  # → Retorna 0 (Redis lo maneja)

# Ejecuta cada 15 minutos
ENCRYPTION_CLEANUP_INTERVAL = 15 * 60  # 900s
```

---

## 🔄 Token Rotation

### Grace Period Mechanism

```
Timeline:
───────────────────────────────────────────────────────────►
         t=0              t=30s            t=3h
         │                │                │
         Rotate           Grace            Old token
         token            expires          expires
         │                │                │
         ▼                ▼                ▼
    ┌────────┐       ┌────────┐      ┌────────┐
    │old_tok │       │old_tok │      │        │
    │new_tok │  →    │ (exp)  │  →   │        │
    │        │       │new_tok │      │new_tok │
    └────────┘       └────────┘      └────────┘
       BOTH             NEW              NEW
       valid            only             only
```

### Implementación

**Old token** (durante grace period):
```json
{
  "rotating": true,
  "rotated_to": "new-token",
  "rotation_expires": "2025-01-06T15:00:30Z",
  ... (resto de datos)
}
```

**New token**:
```json
{
  "rotating": false,  // Ausente
  ... (datos normales de sesión)
}
```

### Redirección Automática

```python
def get_session(session_token, project_id):
    session = redis.get(f"enc_session:{project_id}:{session_token}")

    if session.get('rotating'):
        # Token viejo, verificar grace period
        now = datetime.now(timezone.utc)
        rotation_expires = datetime.fromisoformat(session['rotation_expires'])

        if now > rotation_expires:
            # Grace period expiró
            return None

        # Redirigir al nuevo token
        new_token = session['rotated_to']
        return get_session(new_token, project_id)  # Recursivo

    return session
```

---

## 📑 Indexación

### Purpose

Los índices permiten **invalidación rápida** de múltiples sesiones:

```python
# Sin índice: O(N) SCAN de TODA la BD
for key in redis.scan_iter(match="enc_session:*"):
    session = redis.get(key)
    if session['project_id'] == project_id:
        redis.delete(key)

# Con índice: O(M) donde M = sesiones del proyecto
tokens = redis.smembers(f"enc_session:project_index:{project_id}")
keys = [f"enc_session:{project_id}:{token}" for token in tokens]
redis.delete(*keys)  # Batch delete
```

### Índice de Proyecto

```
enc_session:project_index:abc-123
├─> "token1"
├─> "token2"
├─> "token3"
└─> "token4"
```

**Uso**: Invalidar todas las sesiones de un proyecto (ej: al deshabilitar encriptación)

### Índice de Usuario

```
enc_session:user_index:user-456
├─> "project-a:token1"
├─> "project-b:token2"
└─> "project-c:token3"
```

**Uso**: Invalidar todas las sesiones de un usuario (ej: logout global, compromiso de cuenta)

### Mantenimiento de Índices

Índices se actualizan en:

- ✅ `create_session()` → SADD
- ✅ `rotate_token()` → SADD (nuevo token)
- ✅ `invalidate_session()` → SREM (implícito con DELETE del índice)
- ⚠️ TTL automático evita índices huérfanos

---

## 📦 Serialización

### JSON Serialization

```python
import json
import base64

# Serializar
session_data = {
    'project_id': project_id,
    'encryption_key': base64.b64encode(encryption_key).decode('utf-8'),
    'user_id': user_id,
    'expires_at': expires_at.isoformat(),
    'created_at': created_at.isoformat()
}
session_json = json.dumps(session_data)

# Deserializar
session = json.loads(session_json)
encryption_key = base64.b64decode(session['encryption_key'])
expires_at = datetime.fromisoformat(session['expires_at'])
```

### ¿Por qué JSON y no Pickle?

| Aspecto | JSON | Pickle |
|---------|------|--------|
| **Seguridad** | ✅ Seguro | ❌ Vulnerable (code execution) |
| **Interoperabilidad** | ✅ Cross-language | ❌ Python-only |
| **Legibilidad** | ✅ Human-readable | ❌ Binary |
| **Performance** | ⚠️ Más lento | ✅ Más rápido |
| **Tamaño** | ⚠️ Más grande | ✅ Más compacto |

**Decisión**: JSON por seguridad e interoperabilidad.

### Encoding de Encryption Key

```python
# encryption_key es bytes (32 bytes AES-256)
# JSON no soporta bytes directamente

# Opción 1: Base64 (elegida)
base64.b64encode(encryption_key).decode('utf-8')
# Pros: Estándar, compacto
# Size: 32 bytes → 44 chars

# Opción 2: Hex
encryption_key.hex()
# Pros: Más legible
# Size: 32 bytes → 64 chars

# Opción 3: Binary storage (bytes en Redis)
# Pros: Más eficiente
# Cons: Menos compatible con decode_responses=True
```

---

## ⚡ Performance

### Benchmarks

| Operación | Complejidad | Tiempo | Redis Commands |
|-----------|-------------|--------|----------------|
| `create_session()` | O(1) | ~2ms | 6 |
| `get_session()` (con project_id) | O(1) | ~1ms | 1 GET |
| `get_session()` (sin project_id) | O(N) | ~5-50ms | SCAN + GET |
| `rotate_token()` | O(1) | ~3ms | SCAN + 7 cmds |
| `invalidate_project_sessions()` | O(M) | ~M*0.5ms | SMEMBERS + DELETE |
| `cleanup_expired()` | O(1) | ~0ms | 0 (Redis TTL) |

**M** = número de sesiones del proyecto (típicamente < 10)
**N** = número total de keys en Redis

### Memory Usage

**Por sesión**:
```
Session Key: enc_session:{project_id}:{token}
  = ~70 bytes

Session Value (JSON):
  {
    "project_id": "36 chars",
    "encryption_key": "44 chars (base64)",
    "user_id": "36 chars",
    "expires_at": "32 chars (ISO)",
    "created_at": "32 chars (ISO)"
  }
  ≈ 300 bytes

Total per session: ~370 bytes
```

**Capacidad**:
- Render Starter (25MB): ~67,000 sesiones
- En práctica: ~5,000-10,000 sesiones activas (con índices y overhead)

### Optimizaciones

1. **Connection Pooling**: Reutiliza conexiones TCP
2. **Pipelining** (opcional): Batch commands
3. **Decode Responses**: Auto-decode en cliente (evita decode manual)
4. **TTL Automático**: Redis elimina expirados (no requiere cleanup)

---

## 🔐 Security Considerations

### 1. Encryption Key Storage

```python
# ✅ CORRECTO: Encryption key en Base64 en Redis
"encryption_key": "dGhpc19pc19hX2Jhc2U2NF9lbmNvZGVkX2tleQ=="

# ❌ INCORRECTO: Almacenar derivación en lugar de key directamente
# Obligaría a derivar en cada request (costoso)
```

**Justificación**: La encryption key ya fue derivada con Argon2id (costoso). Almacenarla directamente en Redis evita re-derivación constante.

**Mitigación**: Redis debe estar protegido (SSL, password, internal network only).

### 2. Transport Security

```python
# Producción
REDIS_SSL = True
connection_class = SSLConnection

# Desarrollo local
REDIS_SSL = False
connection_class = Connection
```

### 3. Network Isolation

**Render.com**:
```yaml
# render.yaml
- type: redis
  ipAllowList: []  # ← Vacío = solo conexiones internas
```

**Beneficio**: Redis NO es accesible desde internet público.

### 4. Password Protection

```python
# Opcional pero recomendado
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

ConnectionPool(
    password=REDIS_PASSWORD if REDIS_PASSWORD else None
)
```

### 5. Key Prefixing

```python
KEY_PREFIX = "enc_session"

# Previene colisiones con otras aplicaciones en mismo Redis
# Facilita SCAN pattern matching
# Mejora organización
```

### 6. TTL como Defense

**TTL automático** actúa como defense against:
- Memory leaks (keys expiradas se eliminan)
- Sesiones huérfanas (expiran automáticamente)
- Ataques de replay (sesión expira aunque cookie robada persista)

---

## 📚 Referencias

### Redis Documentation

- [Redis Commands](https://redis.io/commands/)
- [Redis Persistence](https://redis.io/docs/management/persistence/)
- [Redis Connection Pooling](https://redis-py.readthedocs.io/en/stable/connections.html)

### Librerías Utilizadas

- [`redis-py`](https://redis-py.readthedocs.io/) v5.0.1

### Documentación Relacionada

- [REDIS_MIGRATION.md](../REDIS_MIGRATION.md) - Guía de migración
- [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) - Deployment
- [FASE_1.2_USER_ID_BINDING.md](./FASE_1.2_USER_ID_BINDING.md) - Security fix

---

**Mantenido por**: DataMap Security Team
**Última actualización**: 2025-01-06
**Próxima revisión**: 2025-04-06
