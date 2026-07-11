# FASE 1.1: Migración a httpOnly Cookies

**Fecha de implementación**: 2025-01-04
**Severidad corregida**: 🔴 CRÍTICA
**Referencia**: Auditoría de Seguridad 2025-01-03

## 📋 Resumen Ejecutivo

Se ha completado la migración del sistema de sesiones de encriptación desde localStorage (vulnerable a XSS) a httpOnly cookies (inmunes a XSS). Esta es una de las vulnerabilidades CRÍTICAS identificadas en la auditoría de seguridad.

### Vulnerabilidad Corregida

**Antes**:
- Session tokens almacenados en `localStorage`
- Accesibles desde JavaScript (vulnerable a XSS)
- Header `X-Encryption-Session` agregado manualmente por interceptor
- Si un atacante ejecutaba JavaScript malicioso, podía robar todos los tokens

**Después**:
- Session tokens en cookies `httpOnly`
- **INACCESIBLES** desde JavaScript (inmunes a XSS)
- Cookies enviadas automáticamente con cada request
- Incluso si hay XSS, el atacante NO puede leer los tokens

---

## 🔧 Cambios Implementados

### Backend

#### 1. `backend/app/routers/encryption.py`

**Endpoint `/verify` modificado**:
```python
@router.post("/{project_id}/encryption/verify")
async def verify_passphrase(...):
    # ... verificación de passphrase ...

    # 🔐 NUEVO: Establecer cookie httpOnly
    response = JSONResponse(content={
        "valid": True,
        "expires_in_seconds": timeout_seconds
    })

    cookie_name = f"enc_session_{project_id}"
    is_production = os.getenv("ENV", "development").lower() == "production"

    response.set_cookie(
        key=cookie_name,
        value=session_token,
        max_age=timeout_seconds,
        httponly=True,            # 🔐 CRÍTICO: No accesible desde JavaScript
        secure=is_production,     # 🔐 Solo HTTPS en producción
        samesite="strict",        # 🔐 Previene CSRF
        path="/",
    )

    return response
```

**Cookie establecida**:
- Nombre: `enc_session_{project_id}`
- HttpOnly: `True` ✅
- Secure: `True` (en producción) ✅
- SameSite: `Strict` ✅
- Max-Age: `timeout_seconds` (1-3 horas)
- Path: `/`

**Nuevo endpoint `/session-status`**:
```python
@router.get("/{project_id}/encryption/session-status")
async def get_session_status(...):
    # Lee la cookie httpOnly
    cookie_name = f"enc_session_{project_id}"
    session_token = request.cookies.get(cookie_name)

    # Valida sesión y ownership
    # Retorna estado SIN exponer el token

    return {
        "has_session": True/False,
        "expires_in_seconds": remaining,
        "project_id": project_id
    }
```

#### 2. `backend/app/middleware/encryption_session.py`

**Antes**:
```python
# Leía header X-Encryption-Session
session_token = request.headers.get("X-Encryption-Session")
```

**Después**:
```python
# Extrae project_id del path
project_id = extract_project_id_from_path(request.url.path)

# Lee cookie httpOnly
cookie_name = f"enc_session_{project_id}"
session_token = request.cookies.get(cookie_name)
```

**Nueva función helper**:
```python
def extract_project_id_from_path(path: str) -> str | None:
    """
    Extrae project_id de paths como:
    /api/projects/{uuid}/...
    """
    pattern = r'/projects/([a-f0-9-]{36})(?:/|$)'
    match = re.search(pattern, path, re.IGNORECASE)
    return match.group(1) if match else None
```

### Frontend

#### 3. `frontend/src/providers/EncryptionProvider.tsx`

**Cambios en el contexto**:

```typescript
// ❌ ELIMINADO: getSessionToken
// Ya no retornamos tokens (están en httpOnly cookies)

// ✅ NUEVO: checkSessionStatus
const checkSessionStatus = async (projectId: string): Promise<boolean> => {
    const response = await fetch(
        `/api/projects/${projectId}/encryption/session-status`,
        { credentials: 'include' }  // Envía cookies
    );
    // ...
}

// ✅ MODIFICADO: setSession (sin token)
const setSession = (projectId: string, expiresIn: number) => {
    // Solo guarda metadatos de expiración
    // El token ya está en cookie (inaccesible)
    setSessions(prev => new Map(prev).set(projectId, {
        hasSession: true,
        expiresAt: Date.now() + expiresIn * 1000
    }));
}
```

**Eliminado**:
- ❌ `localStorage.setItem(SESSION_KEY_PREFIX...)`
- ❌ `localStorage.getItem(SESSION_KEY_PREFIX...)`
- ❌ `getSessionToken()` method

**Agregado**:
- ✅ `checkSessionStatus()` method
- ✅ Solo metadatos en memoria (no tokens)

#### 4. `frontend/src/services/api.service.ts`

**Eliminado interceptor**:

```typescript
// ❌ ELIMINADO: Request interceptor que agregaba X-Encryption-Session
// Ya no necesario - las cookies se envían automáticamente

// Configuración existente ya tiene credentials: "include"
config = {
    ...fetchOptions,
    credentials: "include",  // ✅ Envía cookies automáticamente
}
```

---

## 🔒 Beneficios de Seguridad

### 1. Inmunidad a XSS

**Antes**:
```javascript
// Código XSS malicioso PODÍA hacer esto:
const stolen = localStorage.getItem('encryption_session_123');
sendToAttacker(stolen); // ⚠️ Token robado
```

**Después**:
```javascript
// Código XSS malicioso NO PUEDE hacer esto:
document.cookie // ❌ HttpOnly cookies no aparecen aquí
localStorage.getItem(...) // ❌ Ya no hay tokens ahí
// 🔐 Token es INACCESIBLE desde JavaScript
```

### 2. Envío Automático

**Antes**:
```typescript
// Interceptor manual necesario
headers.set('X-Encryption-Session', token);
```

**Después**:
```typescript
// Cookies van automáticamente con credentials: "include"
// Sin código manual
```

### 3. Protección CSRF

**Cookies con `SameSite=Strict`**:
- Solo se envían en requests del mismo origin
- Previene CSRF attacks

### 4. Expiración Automática

**El navegador maneja**:
- Limpieza automática de cookies expiradas
- No memory leaks en el frontend

---

## 📊 Testing

### Test 1: Verificar que cookies son httpOnly

```bash
# Request de verificación
curl -X POST http://localhost:8000/api/projects/{id}/encryption/verify \
  -H "Content-Type: application/json" \
  -d '{"passphrase": "TestPassword123"}' \
  -c cookies.txt

# Verificar cookies.txt
cat cookies.txt | grep enc_session
# Debe mostrar: #HttpOnly_localhost ... enc_session_{id} ...
```

### Test 2: JavaScript no puede leer cookies

```javascript
// En consola del navegador
console.log(document.cookie);
// ❌ NO debe mostrar enc_session_*
```

### Test 3: Cookies se envían automáticamente

```bash
# Request subsecuente con cookies
curl http://localhost:8000/api/projects/{id}/schemas \
  -b cookies.txt

# Backend middleware debe leer la cookie y validar sesión
```

### Test 4: Endpoint /session-status

```bash
curl http://localhost:8000/api/projects/{id}/encryption/session-status \
  -b cookies.txt

# Response esperada:
{
  "has_session": true,
  "expires_in_seconds": 2847,
  "project_id": "..."
}
```

---

## 🔄 Migración para Usuarios Existentes

### Limpieza de localStorage antiguo

Los tokens antiguos en localStorage quedarán huérfanos pero son inofensivos.

**Opcional**: Agregar código de limpieza en frontend:

```typescript
// En EncryptionProvider useEffect
useEffect(() => {
    // Limpiar tokens antiguos de localStorage
    for (let i = localStorage.length - 1; i >= 0; i--) {
        const key = localStorage.key(i);
        if (key?.startsWith('encryption_session_') ||
            key?.startsWith('encryption_expiry_')) {
            localStorage.removeItem(key);
        }
    }
}, []);
```

---

## 🚨 Breaking Changes

### Backend

**Ninguno** - El endpoint `/verify` sigue aceptando la misma request, solo cambia la response.

### Frontend

#### 1. EncryptionContext API

**Método eliminado**:
```typescript
// ❌ Ya no existe
const token = getSessionToken(projectId);
```

**Reemplazo**:
```typescript
// ✅ Usar en su lugar
const isValid = isSessionValid(projectId);
// o
const hasSession = await checkSessionStatus(projectId);
```

#### 2. setSession signature

**Antes**:
```typescript
setSession(projectId, token, expiresIn)
```

**Después**:
```typescript
setSession(projectId, expiresIn) // Sin token
```

**Actualizar llamadas**:
```typescript
// Después de recibir response de /verify
if (data.valid) {
    setSession(projectId, data.expires_in_seconds);
}
```

---

## 📈 Métricas de Seguridad

### Antes (localStorage)

| Métrica | Valor |
|---------|-------|
| **Vulnerable a XSS** | ✅ Sí |
| **Token accesible desde JS** | ✅ Sí |
| **Requiere código manual** | ✅ Sí (interceptors) |
| **CSRF protection** | ❌ Solo con headers custom |
| **Expiración** | ⚠️ Manual (frontend) |

### Después (httpOnly Cookies)

| Métrica | Valor |
|---------|-------|
| **Vulnerable a XSS** | ❌ **NO** |
| **Token accesible desde JS** | ❌ **NO** |
| **Requiere código manual** | ❌ NO (automático) |
| **CSRF protection** | ✅ **SameSite=Strict** |
| **Expiración** | ✅ Automática (navegador) |

**Mejora de seguridad**: 🔴 **CRÍTICA** → ✅ **HARDENED**

---

## 🎯 Siguiente Fase

Con la Fase 1.1 completada, el próximo paso es:

**FASE 2.1**: Memory Protection para Encryption Keys
- Proteger encryption keys en memoria del backend
- Implementar secure memory wiping
- Referencia: Auditoría, Vulnerabilidad ALTA #1

---

## 📚 Referencias

- [OWASP: HttpOnly Cookie Attribute](https://owasp.org/www-community/HttpOnly)
- [MDN: Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [SameSite Cookies Explained](https://web.dev/samesite-cookies-explained/)
- Auditoría de Seguridad DataMap 2025-01-03
- FastAPI Cookie Documentation
- RFC 6265 (HTTP State Management Mechanism)

---

**Implementado por**: DataMap Security Team
**Revisado por**: [Pendiente review]
**Fecha de deployment**: [Pendiente]
