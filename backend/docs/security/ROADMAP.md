# ROADMAP - Implementación de Correcciones de Seguridad

**Proyecto**: DataMap - Sistema de Encriptación
**Última actualización**: 2025-01-04
**Estado actual**: FASE 2.2 COMPLETADA

---

## 📊 Estado Global

### ✅ FASE 1: Vulnerabilidades CRÍTICAS (100% COMPLETADO)

| # | Vulnerabilidad | Estado | Fecha | Documentación |
|---|----------------|--------|-------|---------------|
| **1.1** | Session tokens en localStorage (XSS) | ✅ **CORREGIDA** | 2025-01-04 | [FASE_1.1_HTTPONLY_COOKIES.md](FASE_1.1_HTTPONLY_COOKIES.md) |
| **1.2** | User ID binding en sesiones | ✅ CORREGIDA | 2025-01-03 | [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) |
| **1.3** | Passphrase en logs de error | ✅ CORREGIDA | 2025-01-03 | [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) |
| **1.4** | Rotación de key incompleta | ✅ DESHABILITADA | 2025-01-03 | Feature flag en `security.py` |
| **1.5** | Rate limiting passphrase | ✅ CORREGIDA | 2025-01-03 | [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) |
| **1.6** | CSRF protection | ✅ VERIFICADA | 2025-01-04 | [FASE_1.6_CSRF_PROTECTION.md](FASE_1.6_CSRF_PROTECTION.md) |

**Resultado**: Sistema **NO VULNERABLE** a ataques CRÍTICOS ✅

---

### 🔄 FASE 2: Vulnerabilidades ALTAS (33% COMPLETADO - 2/6)

| # | Vulnerabilidad | Severidad | Estado | Prioridad | Estimación |
|---|----------------|-----------|--------|-----------|------------|
| **2.1** | Memory protection encryption keys | 🟠 ALTA | ✅ **CORREGIDA** | - | - |
| **2.2** | Session token rotation | 🟠 ALTA | ✅ **CORREGIDA** | - | - |
| **2.3** | Passphrase en memoria navegador | 🟠 ALTA | ⏳ **PENDIENTE** | 🔴 Alta | 3h |
| **2.4** | Cross-tab session sharing inseguro | 🟠 ALTA | ⏳ PENDIENTE | 🟡 Media | 3h |
| **2.5** | Validación de entropía tokens | 🟠 ALTA | ⏳ PENDIENTE | 🟡 Media | 2h |
| **2.6** | Project IDs en logs sin hash | 🟠 ALTA | ⏳ PENDIENTE | 🟡 Media | 2h |

**Próximo objetivo**: FASE 2.3 (Passphrase en Memoria del Navegador)

---

### ⏳ FASE 3: Vulnerabilidades MEDIAS (0% COMPLETADO - 0/7)

| # | Vulnerabilidad | Severidad | Prioridad | Estimación |
|---|----------------|-----------|-----------|------------|
| **3.1** | Sesiones sobreviven a logout | 🟡 MEDIA | 🟡 Media | 2h |
| **3.2** | Sin cleanup automático sesiones | 🟡 MEDIA | 🟢 Baja | 1h |
| **3.3** | Console logs exponen información | 🟡 MEDIA | 🟢 Baja | 1h |
| **3.4** | Timeout muy largo (3 horas) | 🟡 MEDIA | 🟡 Media | 1h |
| **3.5** | Sin associated data en GCM | 🟡 MEDIA | 🟡 Media | 2h |
| **3.6** | Nonces en misma DB que ciphertext | 🟡 MEDIA | 🟢 Baja | 3h |
| **3.7** | Validación solo en backend | 🟡 MEDIA | 🟢 Baja | 2h |

---

## 🎯 Detalles de Implementación

### ✅ FASE 2.1: Memory Protection (COMPLETADA)

**Archivos creados**:
- `backend/app/utils/secure_memory.py` (450 líneas) - Clase SecureBytes
- `docs/security/FASE_2.1_MEMORY_PROTECTION.md` (15KB)

**Archivos modificados**:
- `backend/app/utils/encryption_session_cache.py` - Uso de SecureBytes

**Características implementadas**:
- SecureBytes wrapper con memory scrubbing (5 passes)
- Auto-cleanup con `__del__`
- Context manager para uso seguro
- Sobrescritura automática al invalidar sesiones

**Testing**:
```bash
cd backend
python -m app.utils.secure_memory
```

---

### ✅ FASE 2.2: Session Token Rotation (COMPLETADA)

**Objetivo**: Prevenir session fixation attacks

**Fecha de completación**: 2025-01-04

**Archivos a modificar**:
- `backend/app/utils/encryption_session_cache.py` - Método `rotate_token()`
- `backend/app/routers/encryption.py` - Endpoint refresh con rotación
- Frontend: Manejo transparente de token rotation

**Implementación sugerida**:

```python
# En encryption_session_cache.py
def rotate_token(self, old_token: str, grace_period_seconds: int = 30) -> Optional[str]:
    """
    Rotar session token (anti-fixation)

    Args:
        old_token: Token actual
        grace_period_seconds: Período de gracia para race conditions

    Returns:
        new_token: Nuevo token generado
    """
    with self._lock:
        if old_token not in self._cache:
            return None

        # Obtener sesión actual
        session = self._cache[old_token]

        # Generar nuevo token
        new_token = secrets.token_urlsafe(32)

        # Copiar sesión al nuevo token
        self._cache[new_token] = session.copy()

        # Marcar token antiguo como "en rotación" (grace period)
        session['rotating'] = True
        session['rotated_to'] = new_token
        session['rotation_expires'] = datetime.now(timezone.utc) + timedelta(seconds=grace_period_seconds)

        return new_token
```

**Endpoint de refresh**:
```python
@router.post("/{project_id}/encryption/refresh-session")
async def refresh_session(project_id: str, request: Request, ...):
    # Leer token actual de cookie
    old_token = request.cookies.get(f"enc_session_{project_id}")

    # Rotar token
    new_token = cache.rotate_token(old_token)

    # Establecer nueva cookie
    response.set_cookie(
        key=f"enc_session_{project_id}",
        value=new_token,
        ...
    )

    return response
```

**Implementación realizada**:
- ✅ Método `rotate_token()` con grace period de 30s
- ✅ Endpoint `POST /refresh-session`
- ✅ Frontend `refreshSession()` en EncryptionProvider
- ✅ Logging completo de auditoría
- ✅ Thread-safe y memory-safe
- ✅ Documentación completa: [FASE_2.2_SESSION_TOKEN_ROTATION.md](FASE_2.2_SESSION_TOKEN_ROTATION.md)

**Tiempo real**: 4 horas

---

### ⏳ FASE 2.3: Passphrase en Memoria del Navegador (PENDIENTE)

**Objetivo**: Limpiar passphrase del estado de React después de uso

**Archivos a modificar**:
- Frontend: Componentes que manejan passphrase input

**Implementación sugerida**:

```typescript
// En modal de unlock
const [passphrase, setPassphrase] = useState('');

const handleUnlock = async () => {
    try {
        await verifyPassphrase(projectId, passphrase);

        // ✅ CRÍTICO: Limpiar passphrase de memoria
        setPassphrase('');

        // Opcional: Forzar garbage collection hint
        if (window.gc) window.gc();
    } finally {
        // Siempre limpiar
        setPassphrase('');
    }
};

// Limpiar al desmontar componente
useEffect(() => {
    return () => {
        setPassphrase('');
    };
}, []);
```

**Mejora adicional**: Usar Web Crypto API para derivar claves en el navegador (si aplica)

**Estimación**: 3 horas

---

### ⏳ FASE 2.4: Cross-Tab Session Sharing (PENDIENTE)

**Objetivo**: Firmar mensajes de BroadcastChannel con HMAC

**Archivos a modificar**:
- `frontend/src/providers/EncryptionProvider.tsx`

**Implementación sugerida**:

```typescript
// Generar signing key al iniciar app (derivado del user session)
const signingKey = await generateSigningKey(userSessionId);

// Al enviar mensaje
const message = {
    type: 'SESSION_CREATED',
    projectId,
    expiresIn,
    timestamp: Date.now()
};

const signature = await signMessage(message, signingKey);

channelRef.current.postMessage({
    ...message,
    signature
});

// Al recibir mensaje
channelRef.current.onmessage = async (event) => {
    const { signature, ...message } = event.data;

    // Verificar firma
    const isValid = await verifySignature(message, signature, signingKey);

    if (!isValid) {
        console.error('[EncryptionProvider] Invalid message signature');
        return;
    }

    // Procesar mensaje...
};
```

**Alternativa más simple**: Compartir secret en sessionStorage al login

**Estimación**: 3 horas

---

### ⏳ FASE 2.5: Validación de Entropía (PENDIENTE)

**Objetivo**: Validar calidad del RNG al generar tokens

**Archivos a modificar**:
- `backend/app/utils/encryption_session_cache.py`
- Crear: `backend/app/utils/entropy_validator.py`

**Implementación sugerida**:

```python
# entropy_validator.py
import secrets
import logging

logger = logging.getLogger(__name__)

def validate_entropy(data: bytes, min_entropy: float = 7.5) -> bool:
    """
    Valida entropía de datos aleatorios

    Args:
        data: Bytes a validar
        min_entropy: Entropía mínima esperada (bits por byte)

    Returns:
        True si entropía es suficiente
    """
    if len(data) == 0:
        return False

    # Calcular entropía de Shannon
    from collections import Counter
    import math

    counter = Counter(data)
    entropy = 0.0

    for count in counter.values():
        probability = count / len(data)
        entropy -= probability * math.log2(probability)

    if entropy < min_entropy:
        logger.warning(f"Low entropy detected: {entropy:.2f} bits/byte (expected >= {min_entropy})")
        return False

    return True

def generate_high_entropy_token(length: int = 32) -> str:
    """Generar token con validación de entropía"""
    max_attempts = 3

    for attempt in range(max_attempts):
        token_bytes = secrets.token_bytes(length)

        if validate_entropy(token_bytes):
            return secrets.token_urlsafe(length)

        logger.warning(f"Regenerating token due to low entropy (attempt {attempt + 1}/{max_attempts})")

    # Fallback: usar de todas formas pero loggear
    logger.error("Failed to generate high-entropy token after multiple attempts")
    return secrets.token_urlsafe(length)
```

**Uso en cache**:
```python
session_token = generate_high_entropy_token(32)
```

**Estimación**: 2 horas

---

### ⏳ FASE 2.6: Project IDs en Logs (PENDIENTE)

**Objetivo**: Hashear project_ids en logs para prevenir correlación

**Archivos a modificar**:
- `backend/app/utils/security_logger.py`

**Implementación sugerida**:

```python
# En security_logger.py
import hmac
import hashlib
import os

_LOG_HASH_SECRET = os.getenv("LOG_HASH_SECRET", "default-log-secret")

def hash_project_id(project_id: str) -> str:
    """
    Hash project ID para logs

    Returns:
        Hash truncado (primeros 12 caracteres)
    """
    h = hmac.new(
        _LOG_HASH_SECRET.encode(),
        project_id.encode(),
        hashlib.sha256
    )
    return h.hexdigest()[:12]

# Uso
logger.info(f"Session created for project {hash_project_id(project_id)}")
```

**Configuración**:
```bash
# .env
LOG_HASH_SECRET=<generate-random-secret>
```

**Estimación**: 2 horas

---

## 📚 Archivos Creados/Modificados

### Backend

**Nuevos**:
- `backend/app/utils/secure_memory.py` ✅
- `backend/app/utils/exception_sanitizer.py` ✅
- `backend/app/utils/rate_limiter.py` ✅
- `backend/app/tasks/encryption_cleanup.py` ✅

**Modificados**:
- `backend/app/config/security.py` ✅
- `backend/app/routers/encryption.py` ✅
- `backend/app/middleware/encryption_session.py` ✅
- `backend/app/utils/encryption_session_cache.py` ✅
- `backend/app/services/encryption_service.py` ✅

### Frontend

**Modificados**:
- `frontend/src/providers/EncryptionProvider.tsx` ✅
- `frontend/src/services/api.service.ts` ✅

### Documentación

**Creados**:
- `docs/security/FASE_1.1_HTTPONLY_COOKIES.md` ✅
- `docs/security/FASE_1.6_CSRF_PROTECTION.md` ✅
- `docs/security/FASE_2.1_MEMORY_PROTECTION.md` ✅
- `docs/security/INTEGRATION_GUIDE.md` ✅
- `docs/security/ROADMAP.md` ✅ (este archivo)

---

## 🚀 Cómo Continuar

### Paso 1: Validar Estado Actual

```bash
# Backend
cd backend
python -m app.utils.secure_memory  # Tests de SecureBytes

# Verificar imports
python -c "from app.utils.encryption_session_cache import get_encryption_session_cache; print('OK')"
```

### Paso 2: Elegir Siguiente Fase

**Recomendación**: FASE 2.2 (Session Token Rotation)
- Mayor impacto en seguridad
- Relativamente simple de implementar
- 3-4 horas de trabajo

### Paso 3: Implementar

Seguir la guía de implementación en este roadmap para la fase elegida.

### Paso 4: Documentar

Crear `FASE_X.X_NOMBRE.md` siguiendo el formato de fases anteriores.

---

## 📈 Métricas de Progreso

### Vulnerabilidades Corregidas

```
Total: 19 vulnerabilidades identificadas
- CRÍTICAS: 6/6 (100%) ✅
- ALTAS: 1/6 (17%) 🔄
- MEDIAS: 0/7 (0%) ⏳

Total completado: 7/19 (37%)
```

### Tiempo Invertido vs Estimado

```
FASE 1 (CRÍTICAS): ~20 horas
FASE 2.1: ~6 horas

Total: ~26 horas
Pendiente estimado: ~27 horas
```

### Nivel de Riesgo

```
Antes: 🔴 CRÍTICO
Ahora: 🟡 MEDIO
Meta: 🟢 BAJO
```

---

## 🎯 Objetivos Finales

### Corto Plazo (1-2 semanas)
- ✅ Completar FASE 1 (CRÍTICAS)
- ✅ Completar FASE 2.1
- ⏳ Completar FASE 2 (ALTAS) - 5 pendientes

### Medio Plazo (1 mes)
- Completar FASE 3 (MEDIAS)
- Implementar FASE 4 (rotación completa de master key)
- Security audit externo

### Largo Plazo (3 meses)
- HSM integration para máxima seguridad
- Implementar MFA para operaciones críticas
- Key escrow seguro
- Envelope encryption con KMS

---

**Última actualización**: 2025-01-04 por DataMap Security Team
