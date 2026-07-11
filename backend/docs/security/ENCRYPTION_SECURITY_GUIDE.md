# GU

ÍA DE SEGURIDAD DEL SISTEMA DE ENCRIPTACIÓN
## DataMap - Arquitectura y Mejores Prácticas

**Versión:** 2.0.0 (Post-hardening)
**Fecha:** 2025-01-03
**Autor:** DataMap Security Team
**Clasificación:** CONFIDENCIAL

---

## 📋 TABLA DE CONTENIDOS

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura de Seguridad](#arquitectura-de-seguridad)
3. [Flujo de Encriptación](#flujo-de-encriptación)
4. [Medidas de Seguridad Implementadas](#medidas-de-seguridad-implementadas)
5. [Mejores Prácticas](#mejores-prácticas)
6. [Gestión de Claves](#gestión-de-claves)
7. [Auditoría y Logging](#auditoría-y-logging)
8. [Respuesta a Incidentes](#respuesta-a-incidentes)
9. [Compliance y Certificaciones](#compliance-y-certificaciones)

---

## 🎯 RESUMEN EJECUTIVO

### Tecnologías Utilizadas

| Componente | Tecnología | Estándar |
|------------|------------|----------|
| **Cifrado Simétrico** | AES-256-GCM | NIST FIPS 197 |
| **Derivación de Claves** | Argon2id | OWASP 2025 |
| **Generación de Nonces** | CSPRNG (secrets.token_bytes) | NIST SP 800-90A |
| **Session Tokens** | CSPRNG (secrets.token_urlsafe) | NIST SP 800-90A |
| **Hashing de IPs** | SHA-256 | NIST FIPS 180-4 |

### Principios de Seguridad

1. **Zero-Knowledge:** Encryption keys NUNCA se almacenan en disco
2. **Defense in Depth:** Múltiples capas de seguridad
3. **Least Privilege:** Sesiones vinculadas a usuarios específicos
4. **Fail-Safe:** Errores no exponen información sensible
5. **Auditability:** Todas las operaciones se loggean

---

## 🏗️ ARQUITECTURA DE SEGURIDAD

### Capas de Seguridad

```
┌─────────────────────────────────────────────────────────────┐
│ CAPA 1: AUTENTICACIÓN DE USUARIO                           │
│ - JWT tokens (session cookies)                             │
│ - get_current_user dependency                              │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ CAPA 2: AUTORIZACIÓN DE PROYECTO                           │
│ - Verificar ownership o rol de editor                      │
│ - _verify_user_can_modify_encryption()                     │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ CAPA 3: RATE LIMITING                                      │
│ - Max 5 intentos / 10 minutos                              │
│ - Lockout 15 minutos después de exceder                    │
│ - Key: user_id + project_id                                │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ CAPA 4: VERIFICACIÓN DE PASSPHRASE                         │
│ - Argon2id (memory: 64MiB, iterations: 3)                  │
│ - Constant-time comparison                                 │
│ - Logging de intentos (sin exponer passphrase)             │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ CAPA 5: SESIÓN DE ENCRIPTACIÓN                             │
│ - Session token (32 bytes CSPRNG)                          │
│ - Vinculado a user_id (previene hijacking)                 │
│ - Timeout configurable (default: 3 horas)                  │
│ - Encryption key en memoria (NUNCA en disco)               │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ CAPA 6: OPERACIONES DE CIFRADO                             │
│ - AES-256-GCM con nonces únicos                            │
│ - AEAD (autenticidad + confidencialidad)                   │
│ - Base64 encoding para almacenamiento                      │
└─────────────────────────────────────────────────────────────┘
```

### Componentes Principales

#### 1. EncryptionManager (backend/app/utils/encryption.py)

**Responsabilidades:**
- Derivación de claves con Argon2id
- Operaciones de cifrado/descifrado con AES-256-GCM
- Generación de nonces y salts seguros
- Validación de passphrases

**Parámetros de Argon2id:**
```python
ARGON2_MEMORY_COST = 64 * 1024  # 64 MiB (OWASP 2025)
ARGON2_TIME_COST = 3             # 3 iteraciones
ARGON2_PARALLELISM = 1           # Single-threaded
ARGON2_HASH_LENGTH = 32          # 256 bits
ARGON2_SALT_LENGTH = 16          # 128 bits
```

**¿Por qué estos parámetros?**
- **64 MiB de memoria:** Dificulta ataques con GPU/ASIC
- **3 iteraciones:** Balance entre seguridad y performance
- **Argon2id:** Híbrido resistente a side-channel y tradeoff attacks

#### 2. EncryptionSessionCache (backend/app/utils/encryption_session_cache.py)

**Responsabilidades:**
- Almacenamiento en memoria de encryption keys (NUNCA en disco)
- Gestión de sesiones con timeout automático
- Thread-safety con locks
- Invalidación de sesiones (por token, proyecto o usuario)

**Estructura de sesión:**
```python
{
    'project_id': UUID,
    'encryption_key': bytes(32),  # AES-256 key
    'user_id': UUID,              # 🔐 Vinculado al usuario
    'expires_at': datetime,
    'created_at': datetime
}
```

**Ciclo de vida:**
```
1. Usuario verifica passphrase
   ↓
2. Se deriva encryption_key on-demand
   ↓
3. Se crea sesión con timeout
   ↓
4. Session token se retorna al frontend
   ↓
5. Frontend incluye token en cada request
   ↓
6. Middleware valida token + user_id
   ↓
7. Encryption_key se inyecta en request.state
   ↓
8. CRUDs usan encryption_key automáticamente
   ↓
9. Después de timeout: sesión expira y se elimina
```

#### 3. EncryptionSessionMiddleware (backend/app/middleware/encryption_session.py)

**Responsabilidades:**
- Leer header `X-Encryption-Session`
- Validar ownership de sesión (user_id binding)
- Inyectar encryption_key en `request.state`
- Detectar intentos de session hijacking

**Flujo de validación:**
```python
session = cache.get_session(token)

if session.user_id != current_user.id:
    # 🚨 SECURITY VIOLATION
    logger.warning("Session hijacking attempt!")
    cache.invalidate_session(token)
    # Request continúa SIN encryption_key
else:
    # ✅ Sesión válida
    request.state.encryption_key = session.encryption_key
```

#### 4. RateLimiter (backend/app/utils/rate_limiter.py)

**Responsabilidades:**
- Prevenir ataques de fuerza bruta
- Sliding window para contar intentos
- Lockout temporal después de exceder límite
- Logging de eventos de seguridad

**Algoritmo:**
```
Key: "passphrase:user:{user_id}:project:{project_id}"

Ventana deslizante de 10 minutos:
[──────────────────────────]
   ↑     ↑     ↑     ↑     ↑
  Int1  Int2  Int3  Int4  Int5

Intento 6 en ventana → LOCKOUT 15 minutos

Después del lockout:
- Contador se resetea
- Usuario puede reintentar
```

---

## 🔄 FLUJO DE ENCRIPTACIÓN

### 1. Setup Inicial de Encriptación

```
┌─────────────────────────────────────────────────────────────┐
│ Usuario: POST /api/projects/{id}/encryption/setup          │
│ Body: { "passphrase": "..." }                              │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │ Validar passphrase:   │
         │ - Min 12 caracteres   │
         │ - Mayúsculas/minúsc.  │
         │ - Números             │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │ Generar 2 salts:      │
         │ - salt_verification   │
         │ - salt_key_derivation │
         └───────────┬───────────┘
                     │
         ┌───────────▼──────────────────┐
         │ Derivar master_key_hash:     │
         │ Argon2id(passphrase, salt1)  │
         │ → Guardar en BD (one-way)    │
         └───────────┬──────────────────┘
                     │
         ┌───────────▼──────────────────┐
         │ Derivar encryption_key:      │
         │ Argon2id(passphrase, salt2)  │
         │ → Usar inmediatamente        │
         │ → NO guardar                 │
         └───────────┬──────────────────┘
                     │
         ┌───────────▼──────────────────┐
         │ Cifrar datos existentes:     │
         │ - Tables (name)              │
         │ - Columns (name, type)       │
         │ - Mappings (fields)          │
         └───────────┬──────────────────┘
                     │
         ┌───────────▼──────────────────┐
         │ Retornar estadísticas:       │
         │ {                            │
         │   tables_encrypted: 10,      │
         │   columns_encrypted: 50,     │
         │   mappings_encrypted: 15     │
         │ }                             │
         └──────────────────────────────┘
```

### 2. Desbloqueo de Proyecto (Unlock)

```
┌─────────────────────────────────────────────────────────────┐
│ Usuario: POST /api/projects/{id}/encryption/verify         │
│ Body: { "passphrase": "..." }                              │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │ Rate Limiting Check:  │
         │ ¿Está bloqueado?      │
         └───────────┬───────────┘
                     │ No
         ┌───────────▼─────────────────┐
         │ Verificar passphrase:       │
         │ - Derivar hash con salt1    │
         │ - Compare constant-time     │
         └───────────┬─────────────────┘
                     │ ✅ Válida
         ┌───────────▼─────────────────┐
         │ Derivar encryption_key:     │
         │ - Argon2id con salt2        │
         └───────────┬─────────────────┘
                     │
         ┌───────────▼─────────────────┐
         │ Crear sesión en caché:      │
         │ - Token CSPRNG (32 bytes)   │
         │ - Vincular a user_id 🔐     │
         │ - Timeout: 3 horas          │
         └───────────┬─────────────────┘
                     │
         ┌───────────▼─────────────────┐
         │ Retornar al frontend:       │
         │ {                           │
         │   valid: true,              │
         │   session_token: "...",     │
         │   expires_in_seconds: 10800 │
         │ }                            │
         └─────────────────────────────┘
```

### 3. Operaciones con Datos Cifrados

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend: GET /api/projects/{id}/tables                    │
│ Headers: { "X-Encryption-Session": "token..." }            │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────▼───────────────┐
         │ Middleware:               │
         │ 1. Leer header token      │
         │ 2. Obtener sesión caché   │
         │ 3. Validar user_id 🔐     │
         │ 4. Inyectar key en state  │
         └───────────┬───────────────┘
                     │
         ┌───────────▼───────────────┐
         │ Endpoint handler:         │
         │ get_current_user()        │
         │ verify_project_access()   │
         └───────────┬───────────────┘
                     │
         ┌───────────▼───────────────┐
         │ CRUD operation:           │
         │ encryption_key = request  │
         │   .state.encryption_key   │
         └───────────┬───────────────┘
                     │
         ┌───────────▼───────────────┐
         │ Para cada campo cifrado:  │
         │ 1. Decrypt ciphertext     │
         │ 2. Verify auth tag        │
         │ 3. Return plaintext       │
         └───────────┬───────────────┘
                     │
         ┌───────────▼───────────────┐
         │ Retornar datos al frontend│
         └───────────────────────────┘
```

---

## 🛡️ MEDIDAS DE SEGURIDAD IMPLEMENTADAS

### 1. Sanitización de Excepciones

**Módulo:** `backend/app/utils/exception_sanitizer.py`

**Problema solucionado:**
Previene exposición de passphrases en logs de error y tracebacks de Python.

**Implementación:**

```python
@dataclass
class SanitizedException:
    user_message: str      # Seguro para mostrar al usuario
    internal_message: str  # Sanitizado para logs
    original_type: str
    error_code: str

def sanitize_exception(exception: Exception) -> SanitizedException:
    # 1. Detectar keywords sensibles
    sensitive_patterns = ['passphrase', 'password', 'secret', 'token']

    # 2. Enmascarar valores
    # "passphrase='SecretPass'" → "passphrase=***REDACTED***"

    # 3. Sanitizar traceback
    # Eliminar argumentos de función de la pila

    # 4. Retornar versión segura
    return SanitizedException(...)
```

**Uso:**

```python
try:
    setup_encryption(project_id, passphrase)
except Exception as e:
    safe_exc = safe_log_exception(e, logger)
    logger.error(safe_exc.internal_message)  # ✅ Sanitizado
    raise HTTPException(detail=safe_exc.user_message)  # ✅ Genérico
```

### 2. User ID Binding en Sesiones

**Módulos afectados:**
- `encryption_session_cache.py`
- `encryption_session.py` (middleware)
- `encryption.py` (router)

**Problema solucionado:**
Previene session hijacking. Incluso si un atacante roba un token, no puede usarlo.

**Validación:**

```python
# Middleware
session = cache.get_session(token)
current_user = request.state.current_user

if session['user_id'] != current_user['id']:
    # 🚨 ATTACK DETECTED
    logger.warning(
        f"Session hijacking: token belongs to {session['user_id']} "
        f"but request from {current_user['id']}"
    )
    cache.invalidate_session(token)
    # NO inyectar encryption_key
```

**Beneficios:**
- ✅ Un token solo funciona para el usuario que lo creó
- ✅ Tokens robados son inútiles para otros usuarios
- ✅ Intentos de hijacking se loggean y detectan

### 3. Rate Limiting

**Módulo:** `backend/app/utils/rate_limiter.py`

**Problema solucionado:**
Previene ataques de fuerza bruta ilimitada en verificación de passphrase.

**Algoritmo: Sliding Window**

```python
class RateLimiter:
    def __init__(self, max_attempts=5, window_seconds=600):
        self.max_attempts = max_attempts
        self.window = window_seconds

    def record_attempt(self, key: str, success: bool):
        # 1. Cleanup intentos fuera de ventana
        cutoff = now - timedelta(seconds=self.window)
        attempts = [a for a in attempts if a.timestamp > cutoff]

        # 2. Agregar nuevo intento
        attempts.append((now, success))

        # 3. Si éxito → resetear contador
        if success:
            attempts = []
            return {"allowed": True}

        # 4. Contar fallos
        failed = sum(1 for _, s in attempts if not s)

        # 5. Si excede límite → LOCKOUT
        if failed >= self.max_attempts:
            lock_until = now + timedelta(seconds=lockout_time)
            return {"allowed": False, "locked": True}

        return {"allowed": True, "remaining": max - failed}
```

**Ventajas del Sliding Window:**
- ✅ No hay "reset" abrupto cada N minutos
- ✅ Más justo para usuarios legítimos
- ✅ Más difícil de explotar para atacantes

**Configuración recomendada:**

```bash
# Strict (alta seguridad)
PASSPHRASE_MAX_ATTEMPTS=3
PASSPHRASE_WINDOW_SECONDS=600   # 10 min
PASSPHRASE_LOCKOUT_SECONDS=1800 # 30 min

# Balanced (default)
PASSPHRASE_MAX_ATTEMPTS=5
PASSPHRASE_WINDOW_SECONDS=600
PASSPHRASE_LOCKOUT_SECONDS=900  # 15 min

# Lenient (desarrollo)
PASSPHRASE_MAX_ATTEMPTS=10
PASSPHRASE_WINDOW_SECONDS=300   # 5 min
PASSPHRASE_LOCKOUT_SECONDS=300
```

### 4. Deshabilitación de Rotación Incompleta

**Módulo modificado:** `backend/app/routers/encryption.py`

**Problema solucionado:**
Previene pérdida de datos por rotación de master key sin re-cifrado.

**Feature Flag:**

```python
ENABLE_KEY_ROTATION = os.getenv("ENABLE_KEY_ROTATION", "false")

if ENABLE_KEY_ROTATION != "true":
    raise HTTPException(
        status_code=501,
        detail="Feature deshabilitada hasta implementación completa"
    )
```

**Implementación completa requerida:**

```python
def rotate_master_key_complete(old_pass, new_pass):
    # 1. Verificar old_passphrase
    if not verify(old_pass):
        raise Exception("Passphrase incorrecta")

    # 2. Derivar claves
    old_key = derive_key(old_pass, old_salt)
    new_salt = generate_salt()
    new_key = derive_key(new_pass, new_salt)

    # 3. RE-CIFRAR TODOS LOS DATOS (CRÍTICO)
    with transaction():
        for table in get_encrypted_tables():
            # Descifrar con clave antigua
            plaintext = decrypt(table.name_encrypted, old_key, table.nonce)

            # Cifrar con clave nueva
            new_nonce = generate_nonce()
            ciphertext = encrypt(plaintext, new_key, new_nonce)

            # Actualizar BD
            update(table, ciphertext, new_nonce)

        # 4. Actualizar configuración
        update_config(new_salt, derive_hash(new_pass))

        # 5. Commit transaccional
        commit()
```

---

## 🔑 GESTIÓN DE CLAVES

### Jerarquía de Claves

```
User Passphrase (memorizada por usuario)
         │
         ├─→ Salt 1 (salt_verification, 16 bytes random)
         │         ↓
         │   Master Key Hash (Argon2id, 32 bytes)
         │   ✅ Stored in DB
         │   ✅ One-way (no se puede revertir)
         │   ✅ Para verificación solamente
         │
         └─→ Salt 2 (salt_key_derivation, 16 bytes random)
                   ↓
             Encryption Key (Argon2id, 32 bytes)
             ❌ NEVER stored
             ✅ Derived on-demand
             ✅ Cached en memoria (temporal)
             ✅ Para cifrado/descifrado real
```

### Almacenamiento de Claves

| Clave | Ubicación | Tiempo de vida |
|-------|-----------|----------------|
| **User Passphrase** | Memoria del usuario | Permanente |
| **Salt Verification** | BD (tabla `project_encryption`) | Permanente |
| **Salt KDF** | BD (tabla `project_encryption`) | Permanente |
| **Master Key Hash** | BD (tabla `project_encryption`) | Permanente |
| **Encryption Key** | Memoria (EncryptionSessionCache) | 3 horas (sesión) |
| **Session Token** | Frontend localStorage* | 3 horas (sesión) |

*Nota: localStorage es vulnerable a XSS. Se recomienda migrar a httpOnly cookies.

### Rotación de Claves

**Estado actual:** ⚠️ DESHABILITADO

**Cuando esté implementado:**

```python
# Rotación recomendada cada:
- Cambio de personal con acceso: INMEDIATO
- Sospecha de compromiso: INMEDIATO
- Rotación preventiva: CADA 90 DÍAS
```

**Proceso de rotación:**

1. Usuario proporciona passphrase actual y nueva
2. Sistema verifica passphrase actual
3. Deriva encryption key con passphrase actual
4. Descifra TODOS los datos
5. Genera nuevos salts para nueva passphrase
6. Deriva nueva encryption key
7. Re-cifra TODOS los datos
8. Actualiza configuración en BD
9. Invalida todas las sesiones existentes
10. Usuario debe desbloquear con nueva passphrase

---

## 📊 AUDITORÍA Y LOGGING

### Eventos Loggeados

| Evento | Severidad | Información Incluida |
|--------|-----------|---------------------|
| `encryption_setup` | INFO | user_id, project_id, timestamp |
| `passphrase_verification` | INFO/WARNING | user_id, project_id, valid (bool), remaining_attempts |
| `passphrase_verification_blocked` | WARNING | user_id, project_id, retry_after_seconds |
| `passphrase_verification_locked` | ERROR | user_id, project_id, reason |
| `session_hijacking_detected` | CRITICAL | session_user_id, request_user_id, token (parcial) |
| `master_key_rotation` | WARNING | user_id, project_id, status |
| `encryption_enabled` | INFO | user_id, project_id |
| `encryption_disabled` | WARNING | user_id, project_id |

### Seguridad de Logs

**✅ QUÉ SE LOGGEA:**
- IDs de usuarios (hasheados opcionalmente)
- IDs de proyectos (hasheados opcionalmente)
- Timestamps
- Direcciones IP (hasheadas con SHA-256)
- User agents
- Resultado de operaciones (éxito/fallo)
- Intentos restantes (rate limiting)

**❌ QUÉ NO SE LOGGEA:**
- Passphrases (NUNCA)
- Encryption keys (NUNCA)
- Session tokens completos (solo primeros 16 chars)
- Contenido descifrado
- Datos de usuario sensibles

**Ejemplo de log seguro:**

```python
logger.info(
    "Passphrase verification",
    extra={
        "user_id": hash_id(user_id),  # Opcional: hashear
        "project_id": hash_id(project_id),
        "valid": True,
        "ip_address": hash_ip(request.client.host),
        "user_agent": request.headers.get("User-Agent"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
)
```

### Hashing de IPs

```python
def hash_ip(ip_address: str) -> str:
    """
    Hashea una IP para logging preservando privacidad

    Args:
        ip_address: IP a hashear

    Returns:
        SHA-256 hash de la IP
    """
    import hashlib
    import os

    # Usar un salt del servidor para prevenir rainbow tables
    salt = os.getenv("IP_HASH_SALT", "default-salt-change-me")

    return hashlib.sha256(
        f"{salt}:{ip_address}".encode()
    ).hexdigest()
```

---

## 🚨 RESPUESTA A INCIDENTES

### Tipos de Incidentes

#### 1. Session Hijacking Detectado

**Indicador:** Middleware detecta session.user_id ≠ current_user.id

**Respuesta automática:**
1. Loggear evento con severidad CRITICAL
2. Invalidar sesión comprometida
3. Request continúa sin encryption_key (denegado)

**Acciones manuales:**
1. Revisar logs de security_events
2. Identificar usuario afectado
3. Invalidar todas sus sesiones:
   ```python
   cache.invalidate_user_sessions(user_id)
   ```
4. Notificar al usuario
5. Investigar origen del token robado (XSS, network sniffing, etc.)

#### 2. Ataque de Fuerza Bruta Detectado

**Indicador:** Múltiples usuarios bloqueados por rate limiting

**Respuesta automática:**
1. Lockout temporal (15 minutos)
2. Logging de todos los intentos

**Acciones manuales:**
1. Revisar logs para identificar patrón
2. Si es ataque distribuido: implementar WAF rules
3. Considerar aumentar lockout time temporalmente
4. Notificar a usuarios afectados

#### 3. Exposición de Passphrase en Logs

**Indicador:** Revisión de logs encuentra texto plano de passphrase

**Respuesta:**
1. CRÍTICO: Rotar inmediatamente todas las passphrases afectadas
2. Purgar logs comprometidos
3. Investigar causa raíz
4. Verificar que sanitización esté funcionando
5. Implementar alertas para detectar patterns

#### 4. Compromiso de Servidor (Memory Dump)

**Indicador:** Evidencia de acceso no autorizado al proceso del servidor

**Respuesta:**
1. CRÍTICO: Invalidar TODAS las sesiones:
   ```python
   for token in cache._cache.keys():
       cache.invalidate_session(token)
   ```
2. Forzar re-autenticación de todos los usuarios
3. Investigar alcance del compromiso
4. Considerar rotación de master keys (cuando esté implementado)
5. Implementar memory protection (mlock, secure wiping)

---

## ✅ MEJORES PRÁCTICAS

### Para Desarrolladores

1. **NUNCA loggear información sensible:**
   ```python
   # ❌ MAL
   logger.debug(f"Passphrase: {passphrase}")

   # ✅ BIEN
   logger.debug("Passphrase verification attempt")
   ```

2. **Siempre usar sanitización de excepciones:**
   ```python
   # ❌ MAL
   except Exception as e:
       raise HTTPException(detail=str(e))

   # ✅ BIEN
   except Exception as e:
       safe_exc = safe_log_exception(e, logger)
       raise HTTPException(detail=safe_exc.user_message)
   ```

3. **Validar ownership antes de operaciones sensibles:**
   ```python
   # ✅ Siempre verificar
   _verify_user_can_modify_encryption(db, project_id, user_id)
   ```

4. **No almacenar encryption keys:**
   ```python
   # ❌ MAL
   encryption_key = derive_key(...)
   save_to_database(encryption_key)  # ¡NUNCA!

   # ✅ BIEN
   encryption_key = derive_key(...)
   # Usar inmediatamente
   encrypt(data, encryption_key)
   # Dejar que Python GC lo limpie
   ```

### Para Administradores

1. **Configurar variables de entorno apropiadas:**
   ```bash
   # Producción: Strict
   PASSPHRASE_MAX_ATTEMPTS=3
   PASSPHRASE_LOCKOUT_SECONDS=1800  # 30 min

   # Desarrollo: Lenient
   PASSPHRASE_MAX_ATTEMPTS=10
   PASSPHRASE_LOCKOUT_SECONDS=60    # 1 min
   ```

2. **Monitorear logs de seguridad:**
   ```bash
   # Revisar eventos críticos diariamente
   grep "CRITICAL" /var/log/datamap/security.log

   # Alertar en múltiples fallos
   grep "passphrase_verification_locked" /var/log/datamap/security.log | wc -l
   ```

3. **Implementar rotación periódica:**
   - Encryption session cleanup: Cada 15 minutos
   - Rate limiter cleanup: Cada hora
   - Security logs rotation: Cada 7 días

4. **Backups seguros:**
   - ✅ Backup de salts (necesarios para derivación)
   - ✅ Backup de master_key_hash
   - ✅ Backup de datos cifrados
   - ❌ NUNCA backup de encryption keys o sessions

### Para Usuarios

1. **Passphrase fuerte:**
   - Mínimo 12 caracteres
   - Mezcla de mayúsculas, minúsculas, números
   - Considerar uso de password manager
   - NUNCA reutilizar passphrases de otros servicios

2. **Guardar passphrase de forma segura:**
   - ✅ Password manager (1Password, Bitwarden, etc.)
   - ✅ Papel en caja fuerte física
   - ❌ NUNCA en archivos de texto plano
   - ❌ NUNCA en emails o chats

3. **Reconocer señales de compromiso:**
   - Sesiones expiradas inesperadamente
   - Mensajes de "session hijacking"
   - Bloqueos de rate limiting sin haber fallado

4. **Reportar incidentes inmediatamente:**
   - Email: security@datamap.com
   - No compartir detalles públicamente

---

## 📜 COMPLIANCE Y CERTIFICACIONES

### Estándares Cumplidos

| Estándar | Estado | Notas |
|----------|--------|-------|
| **NIST SP 800-63B** | ✅ Parcial | Derivación de claves, autenticación |
| **OWASP ASVS 4.0** | ✅ Nivel 2 | Mayoría de controles implementados |
| **OWASP Top 10 2021** | ✅ Mitigado | A02 (Crypto Failures), A07 (Auth) |
| **GDPR** | ✅ Parcial | Encriptación, logging minimizado |
| **HIPAA** | ⏸️ En progreso | Requiere httpOnly cookies, MFA |
| **PCI DSS** | ⏸️ En progreso | Requiere HSM para claves |

### Recomendaciones para Compliance Completo

1. **Implementar MFA:**
   - Para operaciones críticas (setup, rotate)
   - Especialmente para HIPAA/PCI DSS

2. **Implementar Key Escrow:**
   - Recuperación de proyectos si passphrase se pierde
   - Split-knowledge (múltiples partes requeridas)

3. **Usar HSM (Hardware Security Module):**
   - Para master keys del sistema
   - Requerido para PCI DSS Level 1

4. **Implementar inmutabilidad en audit logs:**
   - Write-only log storage
   - Firmas digitales en entries

5. **Penetration testing regular:**
   - Mínimo anual para compliance
   - Recomendado trimestral

---

## 📞 CONTACTO Y SOPORTE

**Equipo de Seguridad DataMap:**
- Email: security@datamap.com
- Reportes de vulnerabilidades: security-reports@datamap.com
- PGP Key: [disponible en keyserver.pgp.com]

**Auditoría:**
- Última auditoría: 2025-01-03
- Próxima programada: 2025-02-01
- Auditor: DataMap Security Team

---

**Fin del documento**
Versión 2.0.0 - Post-Security Hardening
2025-01-03
