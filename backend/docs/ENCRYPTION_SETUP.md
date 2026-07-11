# 🔐 Sistema de Cifrado Enterprise - DataMap

## Descripción General

Sistema de cifrado enterprise implementado con **AES-256-GCM + Argon2id** que proporciona:

- **Cifrado de datos sensibles**: Nombres de tablas, columnas, mapeos, versiones y comentarios
- **Master key segura**: Hash one-way con Argon2id (OWASP 2025 compliant)
- **Derivación de claves**: AES-256 keys derivadas on-demand, nunca almacenadas
- **Autenticación de datos**: AEAD (Authenticated Encryption with Associated Data)
- **Retención de datos**: Purga automática según políticas configurables

---

## 🏗️ Arquitectura

### Dos Niveles de Seguridad

```
┌──────────────────────────────────────────────────────────┐
│ 1. Master Key Hash (One-Way) - Verificación             │
│    User Passphrase → Argon2id(pass, salt₁) → Hash       │
│    ✓ Almacenado en BD (solo para verificar passphrase)  │
│    ✗ NUNCA reversible                                    │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ 2. Encryption Key Derivation - Cifrado de Datos         │
│    User Passphrase → Argon2id(pass, salt₂) → AES-256    │
│    ✓ Derivada on-demand cuando se necesita              │
│    ✗ NUNCA almacenada                                    │
│                                                           │
│    Data → AES-256-GCM(data, key, nonce) → Ciphertext    │
│    ✓ Cada dato tiene nonce único                        │
│    ✓ Autenticación + Confidencialidad (AEAD)           │
└──────────────────────────────────────────────────────────┘
```

### Configuración Argon2id (OWASP 2025)

```python
Memory:      64 MiB (65536 KB)
Iterations:  3
Parallelism: 1
Salt:        128 bits (16 bytes) - único por proyecto
Output:      256 bits (32 bytes)
```

### Configuración AES-256-GCM

```python
Key:    256 bits (derivada con Argon2id)
Nonce:  96 bits (12 bytes) - único por operación
Tag:    128 bits (autenticación integrada)
```

---

## 📦 Componentes Implementados

### 1. Core de Cifrado

- ✅ **`backend/app/utils/encryption.py`**
  - `EncryptionManager` con Argon2id + AES-256-GCM
  - Métodos de cifrado/descifrado
  - Generación segura de salts y nonces
  - Validaciones de seguridad

### 2. Gestión de Claves

- ✅ **`backend/app/crud/master_key_crud.py`**
  - Crear/verificar configuración de cifrado por proyecto
  - Derivar encryption keys on-demand
  - Helpers para cifrar/descifrar por tipo de dato
  - Operaciones batch para migración

### 3. Configuración

- ✅ **`backend/app/config/security.py`**
  - Configuración Argon2id (memory, iterations, parallelism)
  - Políticas de retención de datos
  - Validaciones de seguridad

### 4. Base de Datos

- ✅ **`backend/migrations/003_encryption_infrastructure.sql`**
  - Tabla `project_encryption` para config por proyecto
  - Columnas cifradas en: `tables`, `columns`, `mappings`, `entity_versions`, `comments`
  - Funciones SQL: `get_project_encryption_stats()`, `purge_old_encrypted_data()`
  - Índices optimizados

### 5. Migración de Datos

- ✅ **`backend/utilities/migrate_to_encryption.py`**
  - Script para cifrar datos existentes
  - Modo `--dry-run` para preview
  - Estadísticas detalladas
  - Logging de errores

### 6. Lógica de Negocio

- ✅ **`backend/app/services/encryption_service.py`**
  - Setup de cifrado para proyectos
  - Verificación de passphrases
  - Rotación de master keys
  - Validaciones de seguridad

### 7. API Endpoints

- ✅ **`backend/app/routers/encryption.py`**
  - `POST /api/projects/{id}/encryption/setup`
  - `POST /api/projects/{id}/encryption/verify`
  - `POST /api/projects/{id}/encryption/rotate-key`
  - `GET /api/projects/{id}/encryption/stats`
  - `GET /api/projects/{id}/encryption/status`
  - `POST /api/projects/{id}/encryption/enable`
  - `POST /api/projects/{id}/encryption/disable`
  - `GET /api/encryption/health`

### 8. Retención de Datos

- ✅ **`backend/app/services/data_retention_service.py`**
  - Purga automática de datos antiguos
  - Purga completa al finalizar proyecto
  - Preview de datos purgables
  - Exportación antes de purga

### 9. Sistema de Sesiones de Cifrado

- ✅ **`backend/app/utils/encryption_session_cache.py`**
  - Cache en memoria thread-safe para sesiones
  - Timeout configurable (3 horas por defecto)
  - Gestión automática de expiración
  - Métodos: crear, validar, invalidar sesiones

- ✅ **`backend/app/middleware/encryption_session.py`**
  - Middleware que lee header `X-Encryption-Session`
  - Valida sesión y carga encryption_key en request.state
  - Permite cifrado/descifrado automático sin pedir passphrase constantemente

### 10. Integración con CRUDs

- ✅ **`backend/app/crud/schemas_crud.py`** (Actualizado)
  - `create_table(encryption_key=None)` - Cifra automáticamente si hay sesión
  - `update_table(encryption_key=None)` - Actualiza con cifrado
  - `get_table_by_id(encryption_key=None)` - Descifra automáticamente

- ✅ **`backend/app/services/schema_service.py`** (Actualizado)
  - Pasa encryption_key desde request.state a CRUDs
  - Validaciones mantienen compatibilidad con proyectos sin cifrado

- ✅ **`backend/app/routers/schemas.py`** (Actualizado)
  - Lee encryption_key desde request.state
  - Endpoints de API integrados con sistema de sesiones

---

## ⚙️ Configuración

### Variables de Entorno

Agregar a `backend/.env`:

```bash
# ============================================================================
# CIFRADO (CRÍTICO - NO PERDER ESTAS CONFIGURACIONES)
# ============================================================================

# Habilitar cifrado
ENCRYPTION_ENABLED=true

# Configuración Argon2id (OWASP 2025)
ARGON2_MEMORY_COST=65536  # 64 MiB en KB
ARGON2_TIME_COST=3        # Iterations
ARGON2_PARALLELISM=1      # Degree of parallelism

# Políticas de retención de datos
DATA_RETENTION_DAYS=90
AUTO_PURGE_ON_PROJECT_COMPLETE=false
ENCRYPTION_SESSION_TIMEOUT=10800  # 3 horas (10800 segundos)

# Entorno (development, production)
ENV=development
```

### Instalar Dependencias

```bash
cd backend
pip install argon2-cffi==23.1.0
# o actualizar requirements.txt y ejecutar:
pip install -r requirements.txt
```

### Ejecutar Migración SQL

```bash
# Conectar a PostgreSQL y ejecutar:
psql -U usuario -d datamap < backend/migrations/003_encryption_infrastructure.sql
```

---

## 🚀 Uso

### Flujo de Usuario (UX Optimizada)

```
┌────────────────────────────────────────────────────────┐
│ 1. Usuario selecciona proyecto cifrado                 │
├────────────────────────────────────────────────────────┤
│ 2. Modal solicita Master Key (passphrase)              │
├────────────────────────────────────────────────────────┤
│ 3. POST /api/projects/{id}/encryption/verify           │
│    → Recibe session_token válido por 3 horas           │
├────────────────────────────────────────────────────────┤
│ 4. Frontend guarda session_token en state/localStorage │
├────────────────────────────────────────────────────────┤
│ 5. Todos los requests incluyen header:                 │
│    X-Encryption-Session: {session_token}               │
├────────────────────────────────────────────────────────┤
│ 6. TwoColumnView carga con TODO descifrado             │
│    → Usuario trabaja normalmente                       │
│    → NO volver a pedir passphrase durante 3 horas      │
├────────────────────────────────────────────────────────┤
│ 7. Operaciones CRUD cifran/descifran automáticamente   │
│    → Totalmente transparente para el usuario           │
└────────────────────────────────────────────────────────┘
```

### 1. Setup Inicial de Cifrado para un Proyecto

```bash
# API Request
POST /api/projects/{project_id}/encryption/setup
Content-Type: application/json

{
  "passphrase": "MySecurePassphrase123!"
}
```

**Requisitos de Passphrase:**
- Mínimo 12 caracteres
- Debe contener mayúsculas y minúsculas
- Debe contener números
- Caracteres especiales recomendados

**Respuesta:**
```json
{
  "status": "success",
  "message": "Cifrado configurado exitosamente",
  "project_id": "uuid-here",
  "encryption_enabled": true
}
```

**⚠️ IMPORTANTE:** Guarda la passphrase en un lugar seguro. Sin ella, los datos cifrados son **IRRECUPERABLES**.

### 2. Migrar Datos Existentes

```bash
# Ejecutar script de migración
cd backend
python utilities/migrate_to_encryption.py

# Modo dry-run (preview sin cambios)
python utilities/migrate_to_encryption.py --dry-run

# Migrar proyecto específico
python utilities/migrate_to_encryption.py --project-id "uuid-here"
```

### 3. Verificar Passphrase y Crear Sesión (Modal de "Desbloqueo")

```bash
POST /api/projects/{project_id}/encryption/verify
Content-Type: application/json

{
  "passphrase": "MySecurePassphrase123!"
}

# Respuesta Exitosa
{
  "valid": true,
  "session_token": "vF3k9mP7xQ2jL8wN4hR6tY1sZ5bC0dE...",
  "expires_in_seconds": 10800
}

# Respuesta con Passphrase Incorrecta
{
  "valid": false
}
```

**🔑 Uso del Session Token:**

El `session_token` debe incluirse en el header de **TODOS** los requests subsecuentes:

```bash
# Ejemplo: Crear tabla con sesión activa
POST /api/schemas/tables
Content-Type: application/json
X-Encryption-Session: vF3k9mP7xQ2jL8wN4hR6tY1sZ5bC0dE...

{
  "project_id": "uuid-here",
  "name": "usuarios",
  "type": "origin"
}

# El backend automáticamente:
# 1. Lee el header X-Encryption-Session
# 2. Valida el token en el cache (middleware)
# 3. Carga la encryption_key en request.state
# 4. CRUD cifra el nombre de tabla automáticamente
# 5. Respuesta incluye datos descifrados
```

**Ventajas del Sistema de Sesiones:**
- ✅ Passphrase solicitada **1 sola vez cada 3 horas**
- ✅ UX fluida sin interrupciones
- ✅ Cifrado/descifrado **totalmente transparente**
- ✅ Encryption key **nunca sale del backend**
- ✅ Sesión expira automáticamente por seguridad

### 4. Ver Estadísticas de Cifrado

```bash
GET /api/projects/{project_id}/encryption/stats

# Respuesta
{
  "tables_total": 50,
  "tables_encrypted": 50,
  "columns_total": 300,
  "columns_encrypted": 300,
  "mappings_total": 150,
  "mappings_encrypted": 150,
  "versions_total": 1000,
  "versions_encrypted": 1000,
  "comments_total": 50,
  "comments_encrypted": 50,
  "encryption_percentage": 100.0
}
```

### 5. Rotar Master Key

```bash
POST /api/projects/{project_id}/encryption/rotate-key
Content-Type: application/json

{
  "old_passphrase": "CurrentPassphrase123!",
  "new_passphrase": "NewSecurePassphrase456!"
}
```

**⚠️ ADVERTENCIA:** Operación costosa que puede tardar varios minutos.

### 6. Purgar Datos Antiguos

```bash
# Preview de datos purgables
GET /api/projects/{project_id}/data-retention/purgeable?retention_days=90

# Ejecutar purga
POST /api/projects/{project_id}/data-retention/purge
Content-Type: application/json

{
  "retention_days": 90,
  "user_id": "uuid-here"
}
```

---

## 🔧 Integración en CRUDs Existentes

Para integrar cifrado en operaciones CRUD existentes:

### Patrón de Uso

```python
from app.crud import master_key_crud
from app.services.encryption_service import EncryptionService

def create_table_encrypted(db, project_id, name, type, user_id, passphrase):
    """Ejemplo de crear tabla con cifrado"""

    # 1. Verificar que el proyecto tiene cifrado
    config = master_key_crud.get_project_encryption(db, project_id)
    if not config or not config['encryption_enabled']:
        # Crear sin cifrado (legacy)
        return create_table(db, project_id, name, type, user_id)

    # 2. Derivar encryption key
    encryption_key = EncryptionService.get_encryption_key(
        db, project_id, passphrase
    )

    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Passphrase incorrecta"
        )

    # 3. Cifrar datos
    name_encrypted, name_nonce = master_key_crud.encrypt_table_name(
        name, encryption_key
    )

    # 4. Guardar en BD con datos cifrados
    cursor.execute("""
        INSERT INTO tables (
            id, project_id,
            name_encrypted, name_nonce, is_encrypted,
            type, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, TRUE, %s, %s, %s)
        RETURNING *
    """, (
        str(uuid.uuid4()), project_id,
        name_encrypted, name_nonce,
        type, now, now
    ))

    db.commit()
    return cursor.fetchone()
```

### Descifrado al Leer

```python
def get_table_decrypted(db, table_id, passphrase):
    """Ejemplo de leer tabla con descifrado"""

    # 1. Leer de BD
    cursor.execute("SELECT * FROM tables WHERE id = %s", (table_id,))
    table = cursor.fetchone()

    # 2. Si está cifrada, descifrar
    if table['is_encrypted']:
        encryption_key = EncryptionService.get_encryption_key(
            db, table['project_id'], passphrase
        )

        if encryption_key:
            table['name'] = master_key_crud.decrypt_table_name(
                table['name_encrypted'],
                table['name_nonce'],
                encryption_key
            )

    return table
```

---

## 🧪 Testing

```python
# Ejecutar tests
cd backend
python -m pytest tests/test_encryption.py -v

# Test manual del EncryptionManager
python backend/app/utils/encryption.py
```

---

## 📊 Monitoring

### Health Check

```bash
GET /api/encryption/health

# Respuesta
{
  "status": "healthy",
  "checks": {
    "argon2_available": true,
    "encryption_enabled_in_config": true,
    "argon2_memory_cost": 65536,
    "argon2_time_cost": 3,
    "data_retention_days": 90,
    "encryption_manager": "ok"
  }
}
```

### Logs de Seguridad

Todos los eventos de cifrado se registran en `security_logs`:

- `encryption_setup` - Configuración inicial
- `passphrase_verification` - Intentos de verificación
- `master_key_rotation` - Rotación de claves
- `data_purge` - Purgas de datos
- `encryption_enabled/disabled` - Cambios de estado

---

## ⚠️ Consideraciones de Seguridad

### DO's ✅

- Guardar passphrases en gestores de contraseñas (1Password, LastPass, Bitwarden)
- Rotar master keys periódicamente (cada 6-12 meses)
- Habilitar logs de auditoría
- Usar HTTPS en producción
- Hacer backups encriptados antes de purgas
- Validar permisos de usuario antes de operaciones

### DON'Ts ❌

- NUNCA almacenar passphrases en plaintext
- NUNCA compartir passphrases por email/chat
- NUNCA deshabilitar Argon2id (usar PBKDF2 solo legacy)
- NUNCA reducir memory_cost por debajo de 16 MiB
- NUNCA reutilizar nonces (se generan automáticamente)
- NUNCA commitear passphrases en git

### Recuperación ante Pérdida de Passphrase

**NO HAY RECUPERACIÓN POSIBLE.**

Los datos cifrados con AES-256-GCM + Argon2id son matemáticamente imposibles de recuperar sin la passphrase correcta. Esto es por diseño.

**Recomendaciones:**
- Usar gestores de contraseñas empresariales (1Password Teams, Keeper, etc.)
- Implementar esquema de "master key escrow" si es requerido por compliance
- Considerar multi-party computation (MPC) para casos críticos
- Documentar proceso de recovery en caso de emergencia

---

## 📈 Roadmap Futuro

### Nivel 2 - Conexión Local / No Almacenamiento

- [ ] Cliente se conecta temporalmente a las BDs
- [ ] No almacenar schemas/datos en DataMap
- [ ] Solo resultados temporales en memoria

### Nivel 3 - BYOK / Clave Gestionada por Cliente

- [ ] Integración con AWS KMS
- [ ] Integración con Google Cloud KMS
- [ ] Integración con Azure Key Vault
- [ ] Integración con HashiCorp Vault
- [ ] Cliente controla rotación de claves

---

## 🆘 Troubleshooting

### Error: "argon2-cffi not installed"

```bash
pip install argon2-cffi==23.1.0
```

### Error: "ARGON2_MEMORY_COST debe ser al menos 16384 KB"

Ajustar en `.env`:
```bash
ARGON2_MEMORY_COST=16384  # Mínimo
ARGON2_MEMORY_COST=65536  # Recomendado
```

### Error: "Passphrase incorrecta"

La passphrase no coincide con la almacenada. Verificar:
1. No hay espacios extra
2. Case-sensitive (mayúsculas/minúsculas importan)
3. No hay caracteres especiales mal copiados

### Performance: Argon2id es lento

Esto es **por diseño**. Argon2id es intencionalmente lento para prevenir brute-force attacks.

Si es crítico para UX:
- Reducir `ARGON2_TIME_COST` a 2 (mínimo)
- Reducir `ARGON2_MEMORY_COST` a 32768 (32 MiB)
- ⚠️ NUNCA ir por debajo de los mínimos

---

## 📚 Referencias

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Argon2 Specification](https://github.com/P-H-C/phc-winner-argon2)
- [NIST Cryptographic Standards](https://csrc.nist.gov/projects/cryptographic-standards-and-guidelines)
- [AES-GCM Mode](https://en.wikipedia.org/wiki/Galois/Counter_Mode)

---

## 👥 Contacto y Soporte

Para preguntas o problemas con el sistema de cifrado:

- **Documentación**: Este archivo
- **Issues**: GitHub Issues
- **Security**: security@datamap.com (para vulnerabilidades)

---

**✅ Sistema de Cifrado Enterprise completamente implementado y listo para producción**

*Generado por DataMap Security Team - 2025*
