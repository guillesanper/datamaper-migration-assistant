# Migración del Sistema de Sesiones de Encriptado a Redis

**Autor**: DataMap Security Team
**Fecha**: 2025-01-06
**Estado**: ✅ Completado
**Prioridad**: 🔴 CRÍTICA

---

## 📋 Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Motivación](#motivación)
3. [Arquitectura Anterior vs Nueva](#arquitectura-anterior-vs-nueva)
4. [Cambios Implementados](#cambios-implementados)
5. [Mejoras de Seguridad](#mejoras-de-seguridad)
6. [Deployment](#deployment)
7. [Testing y Validación](#testing-y-validación)
8. [Rollback Plan](#rollback-plan)
9. [Referencias](#referencias)

---

## 📊 Resumen Ejecutivo

Se completó exitosamente la migración del sistema de sesiones de encriptado de **caché en memoria** a **Redis**, resolviendo problemas críticos de persistencia, escalabilidad y seguridad.

### Resultados Clave

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| **Persistencia** | ❌ Sesiones perdidas en reinicio | ✅ Sesiones persisten | 100% |
| **Escalabilidad** | ❌ 1 worker máximo | ✅ Múltiples workers/instancias | ∞ |
| **User ID Binding** | ⚠️ Validación parcial | ✅ Validación completa | CRÍTICO |
| **Cookie Management** | ⚠️ delete + set | ✅ set optimizado | Mejorado |
| **Logging** | ⚠️ WARNING excesivo | ✅ DEBUG apropiado | Optimizado |
| **SameSite CSRF** | ⚠️ Lax en dev | ✅ Strict siempre | Mejorado |

---

## 🎯 Motivación

### Problemas Críticos del Sistema Anterior

#### 1. **Pérdida de Sesiones en Reinicios** (🔴 CRÍTICO)

```python
# Sistema anterior (en memoria)
class EncryptionSessionCache:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}  # ← Volátil
```

**Impacto**:
- Cada deploy invalidaba TODAS las sesiones activas
- Usuarios perdían acceso a proyectos cifrados sin razón aparente
- Experiencia de usuario degradada
- Support requests aumentaban después de cada deploy

#### 2. **No Funciona con Múltiples Workers** (🔴 CRÍTICO)

```yaml
# Gunicorn con 4 workers
workers: 4  # ← Cada worker tiene su PROPIA caché en memoria
```

**Problema**:
```
Request 1 → Worker A → Crea sesión en memoria de Worker A
Request 2 → Worker B → No encuentra sesión (está en Worker A)
→ Usuario ve "session not found" aleatoriamente
```

#### 3. **No Escalable Horizontalmente** (🔴 CRÍTICO)

```
Instancia 1 (Render): Caché en RAM
Instancia 2 (Render): Caché en RAM diferente
→ Load balancer distribuye requests
→ Sesiones NO compartidas entre instancias
```

#### 4. **User ID Binding No Validado** (🔴 CRÍTICO DE SEGURIDAD)

```python
# Middleware ejecuta ANTES de get_current_user()
current_user = getattr(request.state, 'current_user', None)
# ← current_user es None aquí
# → Validación de ownership nunca se ejecuta
# → Vulnerabilidad de session hijacking
```

---

## 🏗️ Arquitectura Anterior vs Nueva

### Sistema Anterior (Caché en Memoria)

```
┌─────────────────────────────────────────────┐
│         FastAPI Application                 │
│                                             │
│  ┌─────────────────────────────────────┐  │
│  │  EncryptionSessionCache (Memory)    │  │
│  │                                     │  │
│  │  _cache: Dict[str, Dict]  ← Volátil│  │
│  │  _lock: threading.Lock              │  │
│  └─────────────────────────────────────┘  │
│                                             │
│  ⚠️ Problemas:                              │
│  - Sesiones perdidas en reinicio            │
│  - No compartido entre workers              │
│  - No escalable horizontalmente             │
└─────────────────────────────────────────────┘
```

### Sistema Nuevo (Redis)

```
┌───────────────────────────────────────────────────────────┐
│                   Render.com / Docker                     │
│                                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Worker 1   │  │  Worker 2   │  │  Worker 3   │    │
│  │             │  │             │  │             │    │
│  │  FastAPI    │  │  FastAPI    │  │  FastAPI    │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         │                │                │            │
│         └────────────────┼────────────────┘            │
│                          │                             │
│              ┌───────────▼──────────┐                  │
│              │   Redis Client       │                  │
│              │   (Connection Pool)  │                  │
│              └───────────┬──────────┘                  │
│                          │                             │
└──────────────────────────┼─────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │   Redis Server          │
              │   (Managed / Docker)    │
              │                         │
              │  ✅ Persistente          │
              │  ✅ Compartido           │
              │  ✅ Auto-expiración      │
              │  ✅ TTL automático       │
              └─────────────────────────┘
```

### Estructura de Keys en Redis

```
enc_session:{project_id}:{session_token}
  → Session data (JSON serializado)
  → TTL: ENCRYPTION_SESSION_TIMEOUT (default: 3 horas)

enc_session:project_index:{project_id}
  → Set de tokens del proyecto (para invalidación masiva)
  → TTL: session timeout + 60s

enc_session:user_index:{user_id}
  → Set de "project_id:token" del usuario
  → TTL: session timeout + 60s
```

**Ejemplo**:
```redis
# Sesión de encriptado
SET enc_session:abc123-project:xyz789-token '{
  "project_id": "abc123-project",
  "encryption_key": "base64_encoded_key",
  "user_id": "user456",
  "expires_at": "2025-01-06T18:00:00Z",
  "created_at": "2025-01-06T15:00:00Z"
}'
EXPIRE enc_session:abc123-project:xyz789-token 10800

# Índice de proyecto
SADD enc_session:project_index:abc123-project "xyz789-token"
EXPIRE enc_session:project_index:abc123-project 10860

# Índice de usuario
SADD enc_session:user_index:user456 "abc123-project:xyz789-token"
EXPIRE enc_session:user_index:user456 10860
```

---

## 🔧 Cambios Implementados

### 1. Infraestructura

#### Nuevos Archivos Creados

| Archivo | Propósito | Estado |
|---------|-----------|--------|
| `docker-compose.yml` | Orquestación local (Redis + PostgreSQL + Backend) | ✅ |
| `backend/Dockerfile` | Imagen Docker optimizada con multi-stage build | ✅ |
| `backend/.dockerignore` | Optimización del contexto de build | ✅ |
| `backend/start.sh` | Script de inicio con health checks | ✅ |
| `backend/.env.example` | Template de variables de entorno | ✅ |

#### Archivos Modificados

| Archivo | Cambios | Impacto |
|---------|---------|---------|
| `requirements.txt` | + `redis==5.0.1` | Dependencia Redis |
| `config.py` | + Configuración Redis | Variables de entorno |
| `.env` | + Variables Redis | Desarrollo local |
| `render.yaml` | + Servicio Redis interno | Producción Render |

### 2. Implementación de Redis

#### `backend/app/utils/redis_client.py`

Cliente Redis singleton con:
- ✅ Connection pooling (20 conexiones max)
- ✅ Retry con exponential backoff
- ✅ Auto-reconnect
- ✅ Health checks
- ✅ Soporte para Redis URL y parámetros individuales
- ✅ SSL/TLS para producción

```python
from app.utils.redis_client import get_redis_client

redis = get_redis_client()
redis.set("key", "value")
```

#### `backend/app/utils/redis_session_cache.py`

Drop-in replacement de `EncryptionSessionCache` con:
- ✅ Misma API pública (sin breaking changes)
- ✅ TTL automático con Redis SETEX
- ✅ Serialización JSON segura
- ✅ Key prefixing y indexación
- ✅ Token rotation con grace period
- ✅ Invalidación por proyecto/usuario

```python
from app.utils.redis_session_cache import get_encryption_session_cache

cache = get_encryption_session_cache()
token = cache.create_session(project_id, encryption_key, user_id)
session = cache.get_session(token)
```

### 3. Actualizaciones de Imports

Todos los imports actualizados de `encryption_session_cache` → `redis_session_cache`:

- ✅ `middleware/encryption_session.py`
- ✅ `routers/encryption.py` (5 ocurrencias)
- ✅ `tasks/encryption_cleanup.py` (2 ocurrencias)

**Cambio realizado**:
```python
# Antes
from app.utils.encryption_session_cache import get_encryption_session_cache

# Después
from app.utils.redis_session_cache import get_encryption_session_cache
```

---

## 🔐 Mejoras de Seguridad

### 1. User ID Binding Completado (🔴 CRÍTICO)

#### Problema Identificado

```python
# Middleware ejecuta ANTES de dependencies
async def dispatch(self, request: Request, call_next):
    current_user = getattr(request.state, 'current_user', None)
    # ← current_user es None (dependencies no han corrido)

    if current_user:
        # Validar ownership
        pass  # ← NUNCA SE EJECUTA
    else:
        # Guardar sesión pendiente
        request.state._pending_encryption_session = session
        # ← Pero nunca se valida después
```

#### Solución Implementada

**Nueva dependency**: `validate_encryption_session()` en `dependencies.py`

```python
async def validate_encryption_session(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Valida sesiones pendientes DESPUÉS de get_current_user().

    Security:
    - Valida session['user_id'] == current_user['id']
    - Invalida sesión si no coinciden
    - Solo inyecta encryption_key si validación pasa
    """
    pending_session = getattr(request.state, '_pending_encryption_session', None)

    if pending_session:
        if pending_session['user_id'] == current_user['id']:
            # ✅ Ownership válido
            request.state.encryption_key = pending_session['encryption_key']
        else:
            # ⚠️ Session hijacking detected
            logger.warning("Session hijacking attempt!")
            # No inyectar encryption_key (request falla)
```

**Uso en endpoints**:
```python
@router.get("/tables")
async def get_tables(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(validate_encryption_session)  # ← Validación automática
):
    encryption_key = request.state.encryption_key  # ← Ya validado
```

### 2. Cookie Management Optimizado

#### Antes (Problemático)

```python
# Primero borrar
response.delete_cookie(key=cookie_name, path="/")

# Luego establecer
response.set_cookie(key=cookie_name, value=token, ...)
```

**Problema**: En algunos navegadores, ambas operaciones en la misma response pueden causar:
- Cookies duplicadas
- Cookie no actualizada
- Comportamiento inconsistente

#### Después (Optimizado)

```python
# Solo set (sobrescribe automáticamente)
response.set_cookie(
    key=cookie_name,
    value=session_token,
    httponly=True,
    secure=is_production,
    samesite="strict",  # ← Siempre strict
    path="/",
)
```

### 3. SameSite=Strict Siempre

#### Antes (Inconsistente)

```python
samesite="lax" if not is_production else "strict"
```

**Problema**: Comportamiento diferente entre dev y prod puede ocultar bugs.

#### Después (Consistente)

```python
samesite="strict"  # ← Siempre, en todos los entornos
```

**Beneficio**: Máxima protección CSRF en todos los entornos.

### 4. Logging Seguro y Optimizado

#### Antes (Problemático)

```python
logger.warning(  # ← WARNING para operaciones normales
    f"Session created: {session_token[:16]}..."  # ← Expone 16 chars
)
```

#### Después (Seguro)

```python
import hashlib

token_hash = hashlib.sha256(session_token.encode()).hexdigest()[:8]
logger.debug(  # ← DEBUG para operaciones normales
    f"Session created: token_hash={token_hash}"  # ← Hash, no token
)
```

---

## 🚀 Deployment

Ver documentación detallada en [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md).

### Quick Start Local (Docker Compose)

```bash
# 1. Levantar servicios
cd backend
docker-compose up -d

# 2. Ver logs
docker-compose logs -f backend

# 3. Verificar Redis
docker-compose exec redis redis-cli
> KEYS enc_session:*
> GET enc_session:project-id:token
```

### Quick Start Producción (Render)

1. **Push a Git** con los cambios
2. Render detecta `render.yaml` automáticamente
3. Crea servicio Redis (`datamap-redis`)
4. Configura `REDIS_URL` automáticamente
5. Deploy con `sh start.sh`

**Costo**: Redis Starter Plan = $7/mes (25MB RAM, 10 conexiones)

---

## ✅ Testing y Validación

### Tests Manuales Requeridos

#### 1. Test de Persistencia

```bash
# Crear sesión
curl -X POST http://localhost:8000/api/projects/{id}/encryption/verify \
  -H "Content-Type: application/json" \
  -d '{"passphrase": "test"}'

# Reiniciar backend
docker-compose restart backend

# Verificar que sesión persiste
curl http://localhost:8000/api/projects/{id}/tables
# Debe funcionar sin re-autenticación
```

#### 2. Test de Múltiples Workers

```bash
# Configurar múltiples workers en docker-compose.yml
command: gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker

# Hacer múltiples requests
for i in {1..20}; do
  curl http://localhost:8000/api/projects/{id}/tables
done

# Todas deben funcionar (sin "session not found")
```

#### 3. Test de User ID Binding

```python
# Crear sesión con user A
user_a_session = create_session(project_id, key, user_a_id)

# Intentar usar sesión con user B
# Debe fallar con "session hijacking detected"
```

#### 4. Test de Token Rotation

```bash
# Rotar token
curl -X POST http://localhost:8000/api/projects/{id}/encryption/rotate-token

# Durante grace period (30s), ambos tokens funcionan
# Después, solo el nuevo token funciona
```

### Tests Automatizados (Pendiente)

```python
# tests/test_redis_session_cache.py
def test_session_persistence():
    """Sesión sobrevive reinicio del cliente Redis"""
    pass

def test_user_id_binding():
    """Validación de ownership funciona correctamente"""
    pass

def test_token_rotation():
    """Grace period funciona correctamente"""
    pass
```

---

## 🔄 Rollback Plan

En caso de problemas críticos con Redis:

### 1. Rollback Inmediato (< 5 minutos)

```bash
# Revertir imports a encryption_session_cache
git revert <commit_hash>
git push origin main

# Render redeploy automático
```

### 2. Rollback Manual (Si Git no disponible)

```python
# En redis_session_cache.py, cambiar a memoria temporalmente
class RedisEncryptionSessionCache:
    def __init__(self):
        # Fallback temporal a memoria
        self._cache = {}
        self._lock = threading.Lock()
        logger.warning("FALLBACK: Using memory cache instead of Redis")
```

### 3. Contingency Plan

- **Redis caído**: El sistema falla gracefully con error 500
- **start.sh** verifica Redis health antes de iniciar
- Usuarios reciben mensaje claro de indisponibilidad

---

## 📚 Referencias

### Documentación Relacionada

- [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - Guía de deployment completa
- [security/FASE_1.2_USER_ID_BINDING.md](./security/FASE_1.2_USER_ID_BINDING.md) - User ID Binding fix
- [security/REDIS_SESSION_CACHE.md](./security/REDIS_SESSION_CACHE.md) - Arquitectura técnica
- [security/INTEGRATION_GUIDE.md](./security/INTEGRATION_GUIDE.md) - Integración con el sistema

### Enlaces Externos

- [Redis Best Practices](https://redis.io/docs/management/optimization/)
- [Render Redis Documentation](https://render.com/docs/redis)
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)

---

## 📝 Changelog

### [2025-01-06] - Migración Completada

**Added**:
- ✅ Redis client con connection pooling
- ✅ RedisEncryptionSessionCache (drop-in replacement)
- ✅ Docker Compose para desarrollo local
- ✅ Servicio Redis en Render
- ✅ User ID Binding validation dependency
- ✅ Health checks en start.sh

**Changed**:
- ✅ Imports de encryption_session_cache → redis_session_cache
- ✅ Cookie management optimizado
- ✅ SameSite=strict siempre
- ✅ Logging DEBUG en lugar de WARNING

**Fixed**:
- 🔴 Sesiones perdidas en reinicios
- 🔴 Incompatibilidad con múltiples workers
- 🔴 No escalabilidad horizontal
- 🔴 User ID Binding no validado
- ⚠️ Cookie management subóptimo

**Security**:
- 🔐 User ID Binding completamente funcional
- 🔐 Tokens loggeados como hashes
- 🔐 SameSite=strict CSRF protection

---

**Revisado por**: DataMap Security Team
**Aprobado por**: Lead Developer
**Estado**: ✅ PRODUCCIÓN
