# 📋 Documentación de Tests Unitarios - Backend DataMap

Este documento describe la suite completa de tests unitarios desarrollados para el backend de DataMap.

## 📚 Índice

- [Resumen General](#resumen-general)
- [Estructura de Tests](#estructura-de-tests)
- [Tests Implementados](#tests-implementados)
- [Ejecutar Tests](#ejecutar-tests)
- [Cobertura](#cobertura)
- [Convenciones](#convenciones)

---

## 📊 Resumen General

### Estadísticas

- **Total de archivos de tests**: 17
- **Total de líneas de código de tests**: ~9,347 líneas
- **Módulos cubiertos**: 17 módulos críticos
- **Prioridad**: Seguridad, autenticación, cifrado, CRUD, validaciones

### Archivos de Tests Creados

| Archivo | Líneas | Módulo Testeado | Prioridad |
|---------|--------|----------------|-----------|
| `test_encryption.py` | 334 | `app.utils.encryption` | **CRÍTICA** |
| `test_encryption_service.py` | 396 | `app.services.encryption_service` | **CRÍTICA** |
| `test_auth_service.py` | 489 | `app.services.auth_service` | **CRÍTICA** |
| `test_project_crud.py` | 507 | `app.crud.project_crud` | **CRÍTICA** |
| `test_security.py` | 626 | `app.utils.security` | **ALTA** |
| `test_locks_crud.py` | 410 | `app.crud.locks_crud` | **ALTA** |
| `test_locking_service.py` | 417 | `app.services.locking_service` | **ALTA** |
| `test_master_key_crud.py` | 488 | `app.crud.master_key_crud` | **ALTA** |
| `test_email_verification.py` | 349 | `app.utils.email_verification` | **MEDIA** |
| `test_schema_service.py` | 429 | `app.services.schema_service` | **MEDIA** |
| `test_activity_crud.py` | 668 | `app.crud.activity_crud` | **ALTA** |
| `test_comments_crud.py` | 718 | `app.crud.comments_crud` | **ALTA** |
| `test_mappings_crud.py` | 731 | `app.crud.mappings_crud` | **CRÍTICA** |
| `test_pk_crud.py` | 685 | `app.crud.pk_crud` | **ALTA** |
| `test_schemas_crud.py` | 866 | `app.crud.schemas_crud` | **CRÍTICA** |
| `test_subscription_crud.py` | 584 | `app.crud.subscription_crud` | **MEDIA** |
| `test_versions_crud.py` | 650 | `app.crud.versions_crud` | **ALTA** |

---

## 🗂️ Estructura de Tests

### Organización de Directorios

```
backend/test/
├── conftest.py                      # Fixtures globales y configuración de pytest
├── fixtures/                        # Fixtures compartidos
│   └── database_fixtures.py         # Fixtures de base de datos
├── unit/                            # Tests unitarios
│   ├── test_encryption.py
│   ├── test_encryption_service.py
│   ├── test_auth_service.py
│   ├── test_project_crud.py
│   ├── test_security.py
│   ├── test_locks_crud.py
│   ├── test_locking_service.py
│   ├── test_master_key_crud.py
│   ├── test_email_verification.py
│   ├── test_schema_service.py
│   ├── test_activity_crud.py
│   ├── test_comments_crud.py
│   ├── test_mappings_crud.py
│   ├── test_pk_crud.py
│   ├── test_schemas_crud.py
│   ├── test_subscription_crud.py
│   └── test_versions_crud.py
├── integration/                     # Tests de integración
│   ├── test_database.py
│   ├── test_reactions_crud_integration.py
│   └── test_tags_crud_integration.py
└── readme_tests.md                  # Este archivo
```

### Estructura de Cada Test

Cada archivo de test sigue esta estructura:

```python
"""
Docstring describiendo el módulo de tests
"""

import pytest
from unittest.mock import MagicMock, patch
# Imports necesarios...

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    """Descripción del fixture"""
    pass

# ============================================================================
# NOMBRE DEL GRUPO DE TESTS
# ============================================================================

class TestNombreDelGrupo:
    """Descripción del grupo de tests"""

    def test_nombre_descriptivo(self):
        """Descripción de lo que testea"""
        # Arrange
        # Act
        # Assert
```

---

## 🧪 Tests Implementados

### 1. test_encryption.py

**Módulo**: `app.utils.encryption`
**Propósito**: Tests para el sistema de cifrado AES-256-GCM con derivación de claves Argon2id

#### Clases de Tests

- **TestSaltAndNonceGeneration**: Generación segura de salts y nonces
  - `test_generate_salt_default_length`: Salt por defecto (16 bytes)
  - `test_generate_salt_custom_length`: Salt con longitud personalizada
  - `test_generate_salt_uniqueness`: Unicidad de salts
  - `test_generate_nonce_length`: Nonce de 12 bytes para GCM
  - `test_generate_nonce_uniqueness`: Unicidad crítica de nonces

- **TestKeyDerivation**: Derivación de claves con Argon2id
  - `test_derive_master_key_hash_success`: Hash one-way de master key
  - `test_derive_master_key_hash_deterministic`: Mismos inputs = mismo hash
  - `test_derive_master_key_hash_different_salt`: Diferentes salts = diferentes hashes
  - `test_derive_master_key_hash_empty_passphrase`: Validación de passphrase vacía
  - `test_derive_master_key_hash_short_salt`: Validación de salt mínimo
  - `test_derive_encryption_key_success`: Derivación de clave AES-256
  - `test_derive_encryption_key_deterministic`: Determinismo

- **TestMasterKeyVerification**: Verificación de passphrases
  - `test_verify_master_key_correct_passphrase`: Verificación exitosa
  - `test_verify_master_key_wrong_passphrase`: Rechazo de passphrase incorrecta
  - `test_verify_master_key_wrong_salt`: Fallo con salt incorrecto

- **TestAESGCMEncryption**: Cifrado/descifrado AES-256-GCM
  - `test_encrypt_field_success`: Cifrado exitoso
  - `test_encrypt_field_with_custom_nonce`: Nonce personalizado
  - `test_encrypt_field_empty_string`: Manejo de string vacío
  - `test_decrypt_field_success`: Descifrado exitoso
  - `test_decrypt_field_wrong_key`: Fallo con clave incorrecta
  - `test_decrypt_field_tampered_ciphertext`: Detección de tampering
  - `test_encrypt_decrypt_roundtrip`: Roundtrip completo

- **TestBase64EncodingDecoding**: Codificación para almacenamiento
  - `test_encode_for_storage`: Codificación a base64
  - `test_decode_from_storage`: Decodificación desde base64
  - `test_encode_decode_roundtrip`: Roundtrip de codificación

- **TestHighLevelFunctions**: Funciones de conveniencia
  - `test_encrypt_text`: Función high-level de cifrado
  - `test_decrypt_text`: Función high-level de descifrado
  - `test_encrypt_decrypt_text_roundtrip`: Roundtrip completo

---

### 2. test_encryption_service.py

**Módulo**: `app.services.encryption_service`
**Propósito**: Tests para la lógica de negocio de cifrado de proyectos

#### Clases de Tests

- **TestPassphraseStrengthValidation**: Validación de fortaleza de passphrases
  - `test_strong_passphrase_valid`: Passphrase fuerte válida
  - `test_passphrase_too_short`: Rechazo de passphrase corta
  - `test_passphrase_no_uppercase`: Requiere mayúsculas
  - `test_passphrase_no_digit`: Requiere dígitos

- **TestUserPermissionVerification**: Verificación de permisos
  - `test_owner_has_permission`: Owner puede modificar cifrado
  - `test_editor_has_permission`: Editor puede modificar cifrado
  - `test_viewer_no_permission`: Viewer no puede modificar
  - `test_project_not_found`: Error con proyecto inexistente

- **TestSetupProjectEncryption**: Setup inicial de cifrado
  - `test_setup_encryption_success`: Setup exitoso
  - `test_setup_encryption_already_exists`: Error si ya existe
  - `test_setup_encryption_weak_passphrase`: Rechazo de passphrase débil

- **TestVerifyProjectPassphrase**: Verificación de passphrases
  - `test_verify_passphrase_correct`: Passphrase correcta
  - `test_verify_passphrase_incorrect`: Passphrase incorrecta

- **TestGetEncryptionKey**: Obtención de claves de cifrado
  - `test_get_encryption_key_success`: Obtención exitosa
  - `test_get_encryption_key_no_config`: Error sin configuración
  - `test_get_encryption_key_disabled`: Error si cifrado deshabilitado
  - `test_get_encryption_key_wrong_passphrase`: Fallo con passphrase incorrecta

- **TestRotateMasterKey**: Rotación de master keys
  - `test_rotate_master_key_success`: Rotación exitosa
  - `test_rotate_master_key_wrong_old_passphrase`: Fallo con passphrase antigua incorrecta
  - `test_rotate_master_key_same_passphrase`: Error si nueva = antigua

- **TestEnableDisableEncryption**: Habilitar/deshabilitar cifrado
  - `test_disable_encryption_success`: Deshabilitación exitosa
  - `test_enable_encryption_success`: Habilitación exitosa

- **TestEncryptExistingProjectData**: Cifrado de datos existentes
  - `test_encrypt_existing_data_success`: Cifrado masivo exitoso
  - `test_encrypt_existing_data_rollback_on_error`: Rollback en error

---

### 3. test_auth_service.py

**Módulo**: `app.services.auth_service`
**Propósito**: Tests para autenticación y gestión de usuarios

#### Clases de Tests

- **TestPasswordStrengthValidation**: Validación de contraseñas
  - `test_strong_password_valid`: Contraseña fuerte válida
  - `test_weak_password_invalid`: Contraseña débil rechazada

- **TestCreateUser**: Creación de usuarios
  - `test_create_user_success`: Registro exitoso
  - `test_create_user_weak_password`: Rechazo con contraseña débil
  - `test_create_user_duplicate_email`: Error con email duplicado

- **TestAuthenticateUser**: Autenticación de usuarios
  - `test_authenticate_user_success`: Login exitoso
  - `test_authenticate_user_not_found`: Error con usuario inexistente
  - `test_authenticate_user_wrong_password`: Fallo con contraseña incorrecta
  - `test_authenticate_user_not_verified`: Rechazo si email no verificado
  - `test_authenticate_user_account_locked`: Bloqueo temporal de cuenta

- **TestFailedLoginHandling**: Manejo de intentos fallidos
  - `test_handle_failed_login_increment`: Incremento de contador
  - `test_handle_failed_login_lockout`: Bloqueo después de intentos máximos

- **TestSuccessfulLoginHandling**: Manejo de login exitoso
  - `test_handle_successful_login`: Reset de intentos fallidos

- **TestVerifyEmailCode**: Verificación de email
  - `test_verify_email_code_success`: Verificación exitosa
  - `test_verify_email_code_invalid`: Código inválido
  - `test_verify_email_code_already_verified`: Error si ya verificado

- **TestResetPassword**: Reset de contraseñas
  - `test_reset_password_success`: Reset exitoso
  - `test_reset_password_user_not_found`: Error con usuario inexistente
  - `test_reset_password_invalid_code`: Código OTP inválido

---

### 4. test_project_crud.py

**Módulo**: `app.crud.project_crud`
**Propósito**: Tests para operaciones CRUD de proyectos

#### Clases de Tests

- **TestCreateProject**: Creación de proyectos
  - `test_create_project_success`: Creación exitosa
  - `test_create_project_with_defaults`: Valores por defecto

- **TestGetProjectById**: Obtención por ID
  - `test_get_project_by_id_exists`: Proyecto existente
  - `test_get_project_by_id_not_found`: Proyecto inexistente
  - `test_get_project_by_id_deleted`: Proyecto eliminado (soft delete)

- **TestGetUserProjects**: Listado de proyectos de usuario
  - `test_get_user_projects_basic`: Listado básico
  - `test_get_user_projects_with_status_filter`: Filtrado por estado
  - `test_get_user_projects_with_sorting`: Ordenamiento personalizado
  - `test_get_user_projects_invalid_sort_field`: Campo de ordenamiento inválido

- **TestUpdateProject**: Actualización de proyectos
  - `test_update_project_single_field`: Actualización de un campo
  - `test_update_project_multiple_fields`: Actualización múltiple
  - `test_update_project_no_changes`: Sin cambios
  - `test_update_project_disallowed_fields`: Campos no permitidos ignorados

- **TestDeleteProject**: Eliminación de proyectos
  - `test_delete_project_success`: Soft delete exitoso
  - `test_delete_project_not_found`: Proyecto inexistente

- **TestCountUserProjects**: Conteo de proyectos
  - `test_count_user_projects_with_projects`: Con proyectos
  - `test_count_user_projects_no_projects`: Sin proyectos

- **TestGetProjectMembers**: Miembros del proyecto
  - `test_get_project_members_with_members`: Con miembros
  - `test_get_project_members_no_members`: Sin miembros

- **TestCheckUserAccess**: Verificación de acceso
  - `test_check_user_access_owner`: Owner
  - `test_check_user_access_member`: Miembro
  - `test_check_user_access_no_access`: Sin acceso

---

### 5. test_security.py

**Módulo**: `app.utils.security`
**Propósito**: Tests para utilidades de seguridad

#### Clases de Tests

- **TestTokenGeneration**: Generación de tokens
  - `test_generate_secure_otp_default_length`: OTP por defecto
  - `test_generate_secure_otp_custom_length`: OTP personalizado
  - `test_generate_secure_otp_alphanumeric`: Charset alfanumérico
  - `test_generate_csrf_token_default_length`: Token CSRF
  - `test_generate_secure_token`: Token genérico

- **TestInputSanitization**: Sanitización de entradas
  - `test_sanitize_input_basic`: Sanitización básica
  - `test_sanitize_input_remove_html`: Remoción de HTML/XSS
  - `test_sanitize_input_remove_control_chars`: Caracteres de control
  - `test_sanitize_email_basic`: Normalización de email
  - `test_sanitize_username_basic`: Sanitización de username

- **TestClientIPDetection**: Detección de IP del cliente
  - `test_get_client_ip_x_forwarded_for`: Header X-Forwarded-For
  - `test_get_client_ip_x_real_ip`: Header X-Real-IP
  - `test_get_client_ip_direct`: Conexión directa
  - `test_hash_ip_address_enabled`: Hashing de IPs

- **TestUserAgentParsing**: Parsing de User-Agent
  - `test_get_user_agent_info_chrome`: Chrome desktop
  - `test_get_user_agent_info_mobile`: Móvil

- **TestHMACSignature**: Firmas HMAC
  - `test_create_hmac_signature`: Creación de firma
  - `test_verify_hmac_signature_valid`: Verificación válida
  - `test_verify_hmac_signature_invalid`: Firma inválida
  - `test_verify_hmac_signature_tampered_data`: Datos alterados

- **TestURLValidation**: Validación de URLs
  - `test_is_safe_redirect_url_relative`: URLs relativas
  - `test_is_safe_redirect_url_allowed_host`: Host permitido
  - `test_is_safe_redirect_url_disallowed_host`: Host no permitido

- **TestSensitiveDataMasking**: Enmascaramiento de datos
  - `test_mask_sensitive_data_basic`: Enmascaramiento básico
  - `test_mask_sensitive_data_custom_visible`: Caracteres visibles personalizados

- **TestPasswordStrengthValidation**: Validación de contraseñas
  - `test_validate_password_strength_strong`: Contraseña fuerte
  - `test_validate_password_strength_too_short`: Muy corta
  - `test_validate_password_strength_no_lowercase`: Sin minúsculas
  - `test_validate_password_strength_common_pattern`: Patrón común

---

### 6. test_locks_crud.py

**Módulo**: `app.crud.locks_crud`
**Propósito**: Tests para CRUD de bloqueo de entidades

#### Clases de Tests

- **TestAcquireLock**: Adquisición de locks
  - `test_acquire_lock_success_new_lock`: Nuevo lock
  - `test_acquire_lock_renew_existing_lock`: Renovación
  - `test_acquire_lock_blocked_by_other_user`: Bloqueado por otro usuario

- **TestReleaseLock**: Liberación de locks
  - `test_release_lock_success`: Liberación exitosa
  - `test_release_lock_not_found`: Lock inexistente

- **TestGetLockStatus**: Estado de locks
  - `test_get_lock_status_locked`: Entidad bloqueada
  - `test_get_lock_status_not_locked`: Entidad sin bloquear

- **TestRenewLock**: Renovación de locks (heartbeat)
  - `test_renew_lock_success`: Renovación exitosa
  - `test_renew_lock_not_found`: Lock inexistente

- **TestForceUnlock**: Desbloqueo forzado
  - `test_force_unlock_success`: Desbloqueo exitoso
  - `test_force_unlock_not_found`: Lock inexistente

- **TestGetActiveLocks**: Locks activos
  - `test_get_active_locks_with_locks`: Con locks activos
  - `test_get_active_locks_empty`: Sin locks

- **TestCleanupExpiredLocks**: Limpieza de locks expirados
  - `test_cleanup_expired_locks_with_expired`: Con locks expirados
  - `test_cleanup_expired_locks_none_expired`: Sin locks expirados

- **TestCheckLockOwner**: Verificación de propietario
  - `test_check_lock_owner_is_owner`: Es propietario
  - `test_check_lock_owner_not_owner`: No es propietario

---

### 7. test_locking_service.py

**Módulo**: `app.services.locking_service`
**Propósito**: Tests para lógica de negocio de locking

#### Clases de Tests

- **TestAcquireLock**: Adquisición con logging
  - `test_acquire_lock_success`: Adquisición exitosa con activity log
  - `test_acquire_lock_blocked`: Bloqueado por otro usuario

- **TestReleaseLock**: Liberación con logging
  - `test_release_lock_success`: Liberación con activity log
  - `test_release_lock_failed`: Liberación fallida

- **TestCheckLockStatus**: Estado de locks
  - `test_check_lock_status_unlocked`: Sin bloquear
  - `test_check_lock_status_locked_by_me`: Bloqueado por mí
  - `test_check_lock_status_locked_by_other`: Bloqueado por otro

- **TestRenewLock**: Renovación
  - `test_renew_lock_success`: Renovación exitosa

- **TestForceUnlock**: Desbloqueo forzado
  - `test_force_unlock_success`: Desbloqueo con logging
  - `test_force_unlock_no_lock`: Sin lock existente

- **TestCheckUserCanEdit**: Permisos de edición
  - `test_check_user_can_edit_unlocked`: Puede editar (sin lock)
  - `test_check_user_can_edit_locked_by_me`: Puede editar (mi lock)
  - `test_check_user_cannot_edit_locked_by_other`: No puede editar

- **TestColumnLockHelpers**: Helpers para locks de columnas
  - `test_make_column_entity_id`: Creación de entity_id
  - `test_parse_column_entity_id_valid`: Parsing válido
  - `test_parse_column_entity_id_invalid`: Parsing inválido

- **TestColumnLockOperations**: Operaciones de locks de columnas
  - `test_acquire_column_lock`: Adquisición de lock de columna
  - `test_release_column_lock`: Liberación de lock de columna
  - `test_get_column_lock_status`: Estado de lock de columna

---

### 8. test_master_key_crud.py

**Módulo**: `app.crud.master_key_crud`
**Propósito**: Tests para CRUD de claves maestras

#### Clases de Tests

- **TestCreateProjectEncryption**: Creación de configuración
  - `test_create_project_encryption_success`: Creación exitosa con salts y hash

- **TestGetProjectEncryption**: Obtención de configuración
  - `test_get_project_encryption_exists`: Configuración existente
  - `test_get_project_encryption_not_found`: Configuración inexistente

- **TestVerifyProjectPassphrase**: Verificación de passphrases
  - `test_verify_passphrase_correct`: Passphrase correcta
  - `test_verify_passphrase_no_config`: Sin configuración
  - `test_verify_passphrase_incorrect`: Passphrase incorrecta

- **TestDeriveEncryptionKey**: Derivación de claves
  - `test_derive_encryption_key_success`: Derivación exitosa
  - `test_derive_encryption_key_wrong_passphrase`: Passphrase incorrecta

- **TestUpdateEncryptionEnabled**: Habilitar/deshabilitar
  - `test_update_encryption_enabled_enable`: Habilitación
  - `test_update_encryption_enabled_disable`: Deshabilitación

- **TestDeleteProjectEncryption**: Eliminación de configuración
  - `test_delete_project_encryption_success`: Eliminación exitosa
  - `test_delete_project_encryption_not_found`: Configuración inexistente

- **TestFieldEncryption**: Helpers de cifrado de campos
  - `test_encrypt_table_name`: Cifrado de nombre de tabla
  - `test_decrypt_table_name`: Descifrado de nombre de tabla
  - `test_encrypt_column_name`: Cifrado de nombre de columna
  - `test_encrypt_column_type`: Cifrado de tipo de columna
  - `test_encrypt_mapping_field`: Cifrado de campo de mapping

- **TestEncryptMultipleFields**: Cifrado masivo
  - `test_encrypt_multiple_fields`: Múltiples campos a la vez
  - `test_decrypt_multiple_fields`: Descifrado de múltiples campos

- **TestRotateMasterKey**: Rotación de master key
  - `test_rotate_master_key_success`: Rotación exitosa
  - `test_rotate_master_key_wrong_old_password`: Passphrase antigua incorrecta

---

### 9. test_email_verification.py

**Módulo**: `app.utils.email_verification`
**Propósito**: Tests para verificación de email

#### Clases de Tests

- **TestGenerateNumericCode**: Generación de códigos OTP
  - `test_generate_numeric_code`: Generación básica
  - `test_generate_numeric_code_returns_string`: Tipo de retorno

- **TestSendVerificationCode**: Envío de códigos
  - `test_send_verification_code_success`: Envío exitoso por SMTP
  - `test_send_verification_code_no_smtp_config`: Modo desarrollo sin SMTP
  - `test_send_verification_code_smtp_error`: Manejo de errores SMTP
  - `test_send_verification_code_email_content`: Contenido del email
  - `test_send_verification_code_upsert_behavior`: Comportamiento UPSERT

- **TestCreateWelcomeNotification**: Notificaciones de bienvenida
  - `test_create_welcome_notification_success`: Creación exitosa
  - `test_create_welcome_notification_content`: Contenido de notificación
  - `test_create_welcome_notification_no_commit`: Sin commit (transacción)

- **TestEmailVerificationIntegration**: Tests de integración
  - `test_full_verification_flow`: Flujo completo
  - `test_user_registration_notifications`: Notificaciones de registro

---

### 10. test_schema_service.py

**Módulo**: `app.services.schema_service`
**Propósito**: Tests para servicio de esquemas (tablas y columnas)

#### Clases de Tests

- **TestValidateTableName**: Validación de nombres de tablas
  - `test_validate_table_name_valid`: Nombres válidos
  - `test_validate_table_name_empty`: Nombre vacío
  - `test_validate_table_name_invalid_characters`: Caracteres inválidos
  - `test_validate_table_name_too_long`: Excede 63 caracteres

- **TestValidateTableType**: Validación de tipos de tablas
  - `test_validate_table_type_origin`: Tipo 'origin'
  - `test_validate_table_type_destination`: Tipo 'destination'
  - `test_validate_table_type_case_insensitive`: Insensible a mayúsculas
  - `test_validate_table_type_invalid`: Tipo inválido

- **TestValidateColumnName**: Validación de nombres de columnas
  - `test_validate_column_name_valid`: Nombres válidos
  - `test_validate_column_name_empty`: Nombre vacío
  - `test_validate_column_name_invalid`: Caracteres inválidos

- **TestParseDataType**: Parsing de tipos de datos
  - `test_parse_data_type_simple`: Tipos simples
  - `test_parse_data_type_varchar_with_length`: VARCHAR(255)
  - `test_parse_data_type_numeric_with_precision`: NUMERIC(10,2)
  - `test_parse_data_type_case_insensitive`: Insensible a mayúsculas

- **TestValidateColumnType**: Validación de tipos de columnas
  - `test_validate_column_type_allowed_simple`: Tipos permitidos
  - `test_validate_column_type_varchar_with_params`: Con parámetros
  - `test_validate_column_type_invalid`: Tipo inválido

- **TestCanUserModifySchema**: Permisos de modificación
  - `test_can_user_modify_schema_owner`: Owner puede modificar
  - `test_can_user_modify_schema_editor`: Editor puede modificar
  - `test_can_user_modify_schema_viewer`: Viewer no puede
  - `test_can_user_modify_schema_no_access`: Sin acceso

- **TestCreateTableWithValidation**: Creación de tablas
  - `test_create_table_success`: Creación exitosa con validaciones
  - `test_create_table_no_permission`: Sin permisos
  - `test_create_table_invalid_name`: Nombre inválido

- **TestCreateColumnWithValidation**: Creación de columnas
  - `test_create_column_success`: Creación exitosa
  - `test_create_column_no_permission`: Sin permisos

---

### 11. test_activity_crud.py

**Módulo**: `app.crud.activity_crud`
**Propósito**: Tests para operaciones CRUD de logs de actividad del proyecto

#### Clases de Tests

- **TestCreateActivityLog**: Creación de logs de actividad
  - `test_create_activity_log_success`: Creación exitosa de log
  - `test_create_activity_log_without_entity`: Log sin entidad asociada
  - `test_create_activity_log_with_metadata`: Log con metadata compleja

- **TestGetProjectActivity**: Obtención de actividad del proyecto
  - `test_get_project_activity_basic`: Obtención básica
  - `test_get_project_activity_with_filters`: Con filtros de tipo y entidad
  - `test_get_project_activity_with_pagination`: Con paginación
  - `test_get_project_activity_empty`: Sin resultados

- **TestGetEntityActivity**: Actividad por entidad
  - `test_get_entity_activity_success`: Obtención exitosa
  - `test_get_entity_activity_with_limit`: Con límite personalizado
  - `test_get_entity_activity_empty`: Sin actividad

- **TestGetUserActivity**: Actividad por usuario
  - `test_get_user_activity_all_projects`: Across all projects
  - `test_get_user_activity_single_project`: Para proyecto específico
  - `test_get_user_activity_with_limit`: Con límite
  - `test_get_user_activity_empty`: Sin actividad

- **TestGetActivityStats**: Estadísticas de actividad
  - `test_get_activity_stats_success`: Estadísticas exitosas
  - `test_get_activity_stats_empty`: Sin datos
  - `test_get_activity_stats_single_type`: Un solo tipo de actividad

- **TestDeleteOldActivity**: Limpieza de actividad antigua
  - `test_delete_old_activity_default_days`: Con días por defecto (90)
  - `test_delete_old_activity_custom_days`: Con días personalizados
  - `test_delete_old_activity_no_records`: Sin registros antiguos
  - `test_delete_old_activity_large_batch`: Batch grande

---

### 12. test_comments_crud.py

**Módulo**: `app.crud.comments_crud`
**Propósito**: Tests para sistema de comentarios y resoluciones

#### Clases de Tests

- **TestCreateComment**: Creación de comentarios
  - `test_create_comment_success`: Creación exitosa con menciones
  - `test_create_comment_without_mentions`: Sin menciones
  - `test_create_reply_comment`: Respuesta a comentario (parent_id)

- **TestUpdateComment**: Actualización de comentarios
  - `test_update_comment_success`: Actualización por autor
  - `test_update_comment_not_author`: Fallo si no es autor
  - `test_update_comment_not_found`: Comentario inexistente

- **TestDeleteComment**: Eliminación de comentarios
  - `test_delete_comment_success`: Eliminación por autor
  - `test_delete_comment_not_author`: Fallo si no es autor
  - `test_delete_comment_not_found`: Comentario inexistente

- **TestResolveComment**: Resolución de comentarios
  - `test_resolve_comment_success`: Marcar como resuelto
  - `test_unresolve_comment_success`: Desmarcar resolución
  - `test_resolve_comment_not_found`: Comentario inexistente

- **TestGetCommentById**: Obtención por ID
  - `test_get_comment_by_id_success`: Con detalles de usuario
  - `test_get_comment_by_id_not_found`: No encontrado
  - `test_get_comment_by_id_with_reactions_and_replies`: Con contadores

- **TestGetComments**: Listado de comentarios
  - `test_get_comments_basic`: Listado básico
  - `test_get_comments_exclude_resolved`: Solo no resueltos
  - `test_get_comments_exclude_replies`: Solo top-level
  - `test_get_comments_specific_parent`: Respuestas a comentario
  - `test_get_comments_empty`: Sin comentarios

- **TestMarkAsRead**: Marcar como leído
  - `test_mark_as_read_success`: Marcar múltiples
  - `test_mark_as_read_empty_list`: Lista vacía
  - `test_mark_as_read_already_read`: ON CONFLICT DO NOTHING

- **TestGetUnreadCount**: Contador de no leídos
  - `test_get_unread_count_with_unread`: Con comentarios no leídos
  - `test_get_unread_count_no_unread`: Sin no leídos
  - `test_get_unread_count_no_result`: Sin resultado de DB

- **TestCheckCommentOwner**: Verificación de propietario
  - `test_check_comment_owner_is_owner`: Es propietario
  - `test_check_comment_owner_not_owner`: No es propietario
  - `test_check_comment_owner_comment_not_found`: Comentario no existe

---

### 13. test_mappings_crud.py

**Módulo**: `app.crud.mappings_crud`
**Propósito**: Tests para mappings de origen-destino con cifrado

#### Clases de Tests

- **TestCreateMapping**: Creación de mappings
  - `test_create_mapping_without_encryption`: Sin cifrado
  - `test_create_mapping_with_encryption`: Con cifrado AES-256-GCM
  - `test_create_mapping_encryption_required_no_key`: Error si requiere cifrado sin clave
  - `test_create_mapping_encryption_disabled`: Con cifrado deshabilitado

- **TestGetMappingsByProject**: Obtención por proyecto
  - `test_get_mappings_by_project_unencrypted`: Sin cifrado
  - `test_get_mappings_by_project_encrypted_with_key`: Con descifrado
  - `test_get_mappings_by_project_encrypted_without_key`: Sin clave de descifrado
  - `test_get_mappings_by_project_decryption_failure`: Fallo en descifrado
  - `test_get_mappings_by_project_empty`: Sin mappings

- **TestGetMappingById**: Obtención por ID
  - `test_get_mapping_by_id_unencrypted`: Sin cifrado
  - `test_get_mapping_by_id_encrypted_with_key`: Con descifrado
  - `test_get_mapping_by_id_not_found`: No encontrado
  - `test_get_mapping_by_id_decryption_failure`: Fallo en descifrado

- **TestDeleteMapping**: Eliminación de mappings
  - `test_delete_mapping_success`: Eliminación exitosa
  - `test_delete_mapping_not_found`: Mapping inexistente

- **TestUpdateMapping**: Actualización de mappings
  - `test_update_mapping_without_encryption`: Sin cifrado
  - `test_update_mapping_with_encryption`: Con cifrado
  - `test_update_mapping_not_found`: Mapping inexistente
  - `test_update_mapping_multiple_fields`: Actualización múltiple
  - `test_update_mapping_notes_only`: Solo notas

---

### 14. test_pk_crud.py

**Módulo**: `app.crud.pk_crud`
**Propósito**: Tests para constraints de Primary Keys

#### Clases de Tests

- **TestGetPkConstraintByTableId**: Obtención de PK constraint
  - `test_get_pk_constraint_exists`: Constraint existente
  - `test_get_pk_constraint_not_found`: No encontrado

- **TestGetLegacyPkColumns**: Columnas marcadas como PK (legacy)
  - `test_get_legacy_pk_columns_with_results`: Con columnas PK
  - `test_get_legacy_pk_columns_empty`: Sin columnas PK

- **TestGetColumnsByIds**: Obtención de columnas por IDs
  - `test_get_columns_by_ids_success`: Obtención exitosa
  - `test_get_columns_by_ids_empty_list`: Lista vacía
  - `test_get_columns_by_ids_preserves_order`: Preserva orden

- **TestGetTableById**: Obtención de tabla
  - `test_get_table_by_id_exists`: Tabla existente
  - `test_get_table_by_id_not_found`: Tabla no existe

- **TestGetColumnsForValidation**: Columnas para validación
  - `test_get_columns_for_validation_success`: Con table_id y is_nullable

- **TestCreatePkConstraint**: Creación de constraints
  - `test_create_pk_constraint_with_auto_id`: ID auto-generado
  - `test_create_pk_constraint_with_specific_id`: ID específico
  - `test_create_pk_constraint_without_name`: Sin nombre de constraint

- **TestUpdatePkConstraint**: Actualización de constraints
  - `test_update_pk_constraint_success`: Actualización exitosa
  - `test_update_pk_constraint_change_name`: Cambio de nombre

- **TestUpdateColumnsPrimaryFlag**: Actualización de flags is_primary
  - `test_update_columns_primary_flag_success`: Actualización exitosa
  - `test_update_columns_primary_flag_empty_list`: Lista vacía

- **TestDeletePkConstraint**: Eliminación de constraints
  - `test_delete_pk_constraint_success`: Eliminación exitosa
  - `test_delete_pk_constraint_multiple_calls`: Múltiples llamadas

- **TestClearAllPrimaryFlags**: Limpieza de flags
  - `test_clear_all_primary_flags_success`: Set is_primary = false para todas

- **TestInsertAuditLog**: Logs de auditoría
  - `test_insert_audit_log_pk_created`: Log de creación
  - `test_insert_audit_log_pk_updated`: Log de actualización
  - `test_insert_audit_log_pk_removed`: Log de eliminación

- **TestGetOriginTablesWithPks**: Tablas origen con PKs
  - `test_get_origin_tables_with_pks_success`: Listado exitoso
  - `test_get_origin_tables_with_pks_empty`: Sin tablas

- **TestCountColumnMappings**: Conteo de mappings
  - `test_count_column_mappings_with_results`: Con mappings
  - `test_count_column_mappings_no_mappings`: Sin mappings
  - `test_count_column_mappings_no_result`: Sin resultado DB

---

### 15. test_schemas_crud.py

**Módulo**: `app.crud.schemas_crud`
**Propósito**: Tests para operaciones de tablas y columnas (schemas)

#### Clases de Tests

- **TestCreateTable**: Creación de tablas
  - `test_create_table_without_encryption`: Sin cifrado
  - `test_create_table_with_encryption`: Con cifrado AES-256-GCM
  - `test_create_table_encryption_required_no_key`: Error si requiere cifrado
  - `test_create_table_duplicate_name`: Error con nombre duplicado

- **TestUpdateTable**: Actualización de tablas
  - `test_update_table_without_encryption`: Sin cifrado
  - `test_update_table_not_found`: Tabla no existe

- **TestDeleteTable**: Eliminación de tablas
  - `test_delete_table_success`: Con cascada de columnas y mappings
  - `test_delete_table_not_found`: Tabla no existe

- **TestGetTableById**: Obtención por ID
  - `test_get_table_by_id_unencrypted`: Sin cifrado
  - `test_get_table_by_id_not_found`: No existe

- **TestGetTableByName**: Obtención por nombre
  - `test_get_table_by_name_found`: Tabla encontrada
  - `test_get_table_by_name_not_found`: No encontrada

- **TestCheckTableLimits**: Límites de plan
  - `test_check_table_limits_free_plan`: Plan free (20 tablas)
  - `test_check_table_limits_pro_plan`: Plan pro (140 tablas)

- **TestGetTablesByProject**: Listado por proyecto
  - `test_get_tables_by_project_unencrypted`: Sin cifrado
  - `test_get_tables_by_project_empty`: Sin tablas

- **TestCreateColumn**: Creación de columnas
  - `test_create_column_without_encryption`: Sin cifrado
  - `test_create_column_table_not_found`: Tabla no existe
  - `test_create_column_origin_table_autogenerated_forced_false`: is_autogenerated = False para origin

- **TestUpdateColumn**: Actualización de columnas
  - `test_update_column_without_encryption`: Sin cifrado
  - `test_update_column_not_found`: Columna no existe

- **TestDeleteColumn**: Eliminación de columnas
  - `test_delete_column_success`: Con cascada de mappings
  - `test_delete_column_not_found`: Columna no existe

- **TestGetColumnById**: Obtención por ID
  - `test_get_column_by_id_found`: Con table info
  - `test_get_column_by_id_not_found`: No existe

- **TestCheckColumnLimits**: Límites de columnas
  - `test_check_column_limits_free_plan`: Free (60 columnas)
  - `test_check_column_limits_pro_plan`: Pro (200 columnas)

- **TestGetColumnsByTable**: Listado por tabla
  - `test_get_columns_by_table_success`: Con descifrado
  - `test_get_columns_by_table_empty`: Sin columnas

---

### 16. test_subscription_crud.py

**Módulo**: `app.crud.subscription_crud`
**Propósito**: Tests para planes y suscripciones de Stripe

#### Clases de Tests

- **TestGetSubscriptionPlanById**: Obtención de planes
  - `test_get_subscription_plan_by_id_exists`: Plan existente
  - `test_get_subscription_plan_by_id_not_found`: Plan no existe
  - `test_get_subscription_plan_by_id_exception`: Manejo de excepciones

- **TestGetSubscriptionPlans**: Listado de planes
  - `test_get_subscription_plans_success`: Todos los planes activos
  - `test_get_subscription_plans_empty`: Sin planes
  - `test_get_subscription_plans_exception`: Manejo de excepciones

- **TestGetUserSubscription**: Suscripción del usuario
  - `test_get_user_subscription_active`: Suscripción activa
  - `test_get_user_subscription_not_found`: Sin suscripción
  - `test_get_user_subscription_exception`: Manejo de excepciones

- **TestGetSubscriptionByStripeId**: Por ID de Stripe
  - `test_get_subscription_by_stripe_id_exists`: Suscripción existente
  - `test_get_subscription_by_stripe_id_not_found`: No existe
  - `test_get_subscription_by_stripe_id_exception`: Manejo de excepciones

- **TestCreateSubscription**: Creación de suscripciones
  - `test_create_subscription_success`: Creación exitosa con commit
  - `test_create_subscription_exception`: Rollback en error

- **TestUpdateSubscription**: Actualización de suscripciones
  - `test_update_subscription_success`: Actualización dinámica de campos
  - `test_update_subscription_not_found`: Suscripción no existe
  - `test_update_subscription_no_changes`: Sin datos para actualizar
  - `test_update_subscription_exception`: Rollback en error

- **TestGetCustomerByStripeId**: Cliente por ID de Stripe
  - `test_get_customer_by_stripe_id_from_metadata`: Desde metadata de Stripe
  - `test_get_customer_by_stripe_id_from_subscriptions`: Fallback a tabla subscriptions
  - `test_get_customer_by_stripe_id_not_found`: Cliente no existe
  - `test_get_customer_by_stripe_id_exception`: Manejo de excepciones

---

### 17. test_versions_crud.py

**Módulo**: `app.crud.versions_crud`
**Propósito**: Tests para control de versiones de entidades

#### Clases de Tests

- **TestCreateVersion**: Creación de versiones
  - `test_create_version_success`: Con snapshot y hash
  - `test_create_version_with_diff`: Con diff de cambios
  - `test_create_version_with_parent`: Con parent_version_id
  - `test_create_version_database_error`: Rollback en error

- **TestGetVersionById**: Obtención por ID
  - `test_get_version_by_id_exists`: Con detalles de usuario
  - `test_get_version_by_id_not_found`: Versión no existe

- **TestGetVersionByHash**: Por hash (deduplicación)
  - `test_get_version_by_hash_exists`: Para evitar duplicados
  - `test_get_version_by_hash_not_found`: Hash no existe

- **TestGetVersionHistory**: Historial de versiones
  - `test_get_version_history_basic`: Historial básico
  - `test_get_version_history_with_change_type_filter`: Filtro por change_type
  - `test_get_version_history_with_user_filter`: Filtro por user_id
  - `test_get_version_history_with_pagination`: Con paginación
  - `test_get_version_history_empty`: Sin versiones

- **TestGetProjectVersions**: Versiones del proyecto
  - `test_get_project_versions_basic`: Todas las versiones
  - `test_get_project_versions_with_entity_type_filter`: Filtro por entity_type
  - `test_get_project_versions_with_all_filters`: Todos los filtros
  - `test_get_project_versions_empty`: Sin versiones

- **TestGetNextVersionNumber**: Número de versión
  - `test_get_next_version_number_existing_entity`: Para entidad existente
  - `test_get_next_version_number_new_entity`: Primera versión = 1

- **TestGetLatestVersion**: Última versión
  - `test_get_latest_version_exists`: Versión más reciente
  - `test_get_latest_version_not_found`: Sin versiones

- **TestDeleteVersion**: Eliminación de versiones
  - `test_delete_version_success`: Eliminación exitosa
  - `test_delete_version_not_found`: Versión no existe

- **TestGetVersionsCount**: Conteo de versiones
  - `test_get_versions_count_with_versions`: Con versiones existentes
  - `test_get_versions_count_no_versions`: Sin versiones
  - `test_get_versions_count_no_result`: Sin resultado DB

---

## 🚀 Ejecutar Tests

### Requisitos Previos

```bash
# Instalar pytest y dependencias
pip install pytest pytest-cov pytest-mock

# O desde requirements.txt
pip install -r requirements.txt
```

### Comandos Básicos

```bash
# Ejecutar todos los tests
pytest

# Ejecutar con verbosidad
pytest -v

# Ejecutar con salida detallada
pytest -vv

# Ejecutar tests de un archivo específico
pytest backend/test/unit/test_encryption.py

# Ejecutar tests de una clase específica
pytest backend/test/unit/test_encryption.py::TestAESGCMEncryption

# Ejecutar un test específico
pytest backend/test/unit/test_encryption.py::TestAESGCMEncryption::test_encrypt_field_success
```

### Ejecución con Cobertura

```bash
# Ejecutar con reporte de cobertura
pytest --cov=app --cov-report=html

# Ver reporte en navegador
# Abrir: htmlcov/index.html

# Reporte en terminal
pytest --cov=app --cov-report=term-missing

# Cobertura de módulo específico
pytest --cov=app.utils.encryption backend/test/unit/test_encryption.py
```

### Ejecución por Marcadores (Tags)

```bash
# Ejecutar solo tests críticos (si se implementan marcadores)
pytest -m critical

# Ejecutar tests rápidos
pytest -m "not slow"

# Ejecutar tests de seguridad
pytest -m security
```

### Ejecución Paralela

```bash
# Instalar pytest-xdist
pip install pytest-xdist

# Ejecutar en paralelo con 4 workers
pytest -n 4

# Auto-detectar número de CPUs
pytest -n auto
```

---

## 📈 Cobertura

### Módulos con Cobertura Completa

Los siguientes módulos tienen cobertura completa de tests unitarios:

1. ✅ **app.utils.encryption** - Cifrado AES-256-GCM + Argon2id
2. ✅ **app.services.encryption_service** - Servicio de cifrado
3. ✅ **app.services.auth_service** - Autenticación
4. ✅ **app.crud.project_crud** - CRUD de proyectos
5. ✅ **app.utils.security** - Utilidades de seguridad
6. ✅ **app.crud.locks_crud** - CRUD de locks
7. ✅ **app.services.locking_service** - Servicio de locking
8. ✅ **app.crud.master_key_crud** - CRUD de master keys
9. ✅ **app.utils.email_verification** - Verificación de email
10. ✅ **app.services.schema_service** - Servicio de esquemas
11. ✅ **app.crud.activity_crud** - CRUD de logs de actividad
12. ✅ **app.crud.comments_crud** - CRUD de comentarios
13. ✅ **app.crud.mappings_crud** - CRUD de mappings con cifrado
14. ✅ **app.crud.pk_crud** - CRUD de Primary Keys
15. ✅ **app.crud.schemas_crud** - CRUD de tablas y columnas
16. ✅ **app.crud.subscription_crud** - CRUD de suscripciones
17. ✅ **app.crud.versions_crud** - CRUD de versiones

### Áreas Pendientes de Cobertura

Los siguientes módulos aún no tienen tests unitarios (48 módulos restantes):

#### CRUD Operations (2 módulos)
- `app.crud.reactions_crud`
- `app.crud.tags_crud`

#### Services (8 módulos)
- `app.services.activity_service`
- `app.services.comments_service`
- `app.services.data_retention_service`
- `app.services.pk_service`
- `app.services.project_service`
- `app.services.stripe_service`
- `app.services.type_compatibility_service`
- `app.services.version_control_service`

#### Utils (9 módulos)
- `app.utils.encryption_session_cache`
- `app.utils.redis_session_cache`
- `app.utils.redis_client`
- `app.utils.rate_limiter`
- `app.utils.i18n`
- `app.utils.secure_memory`
- `app.utils.security_logger`
- `app.utils.exception_sanitizer`

#### Middleware (4 módulos)
- `app.middleware.encryption_session`
- `app.middleware.csrf_protection`
- `app.middleware.rate_limiting`
- `app.middleware.security_headers`

---

## 📝 Convenciones

### Nomenclatura

- **Archivos de tests**: `test_<nombre_del_modulo>.py`
- **Clases de tests**: `Test<NombreDescriptivo>`
- **Métodos de tests**: `test_<descripcion_del_comportamiento>`

### Estructura de Tests (AAA Pattern)

```python
def test_example(self):
    """Test descriptivo de lo que se prueba"""
    # Arrange (preparar)
    data = {"key": "value"}

    # Act (actuar)
    result = function_to_test(data)

    # Assert (afirmar)
    assert result == expected_value
```

### Uso de Fixtures

- Fixtures se definen al inicio de cada archivo de test
- Fixtures globales en `conftest.py`
- Nombres descriptivos: `mock_db`, `test_user_data`, etc.

### Mocking

- Usar `unittest.mock.MagicMock` para objetos complejos
- Usar `@patch` para mockear módulos/funciones
- Mockear solo lo necesario, no sobre-mockear

### Aserciones

```python
# Usar aserciones descriptivas
assert result == expected, "El resultado no coincide con lo esperado"

# Usar pytest.raises para excepciones
with pytest.raises(HTTPException) as exc_info:
    function_that_raises()
assert exc_info.value.status_code == 400

# Usar aserciones múltiples cuando sea apropiado
assert result["status"] == "success"
assert result["data"] is not None
assert len(result["items"]) > 0
```

### Documentación

- Cada test tiene un docstring descriptivo
- Docstrings explican **qué** se testea, no **cómo**
- Comentarios inline solo cuando la lógica es compleja

---

## 🔧 Troubleshooting

### Problemas Comunes

#### Tests E2E de Encryption Fallan con "invalid_credentials"

**Síntoma**: Los tests en `test_encryption_full_flow.py` fallan con errores como:
```
AssertionError: Login failed: {'success': False, 'error': 'invalid_credentials', 'message': 'Credenciales inválidas', 'data': None}
```

**Causa**: Los tests están usando el fixture `client` del `conftest.py` principal en lugar de fixtures específicos de E2E que tienen Redis configurado correctamente.

**Problema Específico**:
- El fixture `client` del conftest principal usa Redis con `decode_responses=True`
- Los tests de encryption NECESITAN Redis con `decode_responses=False` (para coincidir con el cliente real de sessions)
- Esta diferencia causa que las sesiones de encryption no funcionen correctamente

**Solución**: Usar las fixtures correctas de E2E:
```python
# ❌ INCORRECTO - No usar el fixture client genérico
def test_encryption_flow(client, clean_db, test_project, test_user):
    pass

# ✅ CORRECTO - Usar fixtures específicas de E2E
def test_encryption_flow(e2e_encryption_setup):
    # e2e_encryption_setup proporciona: client, user, project, db, redis
    authenticated_client = e2e_encryption_setup['client']
    test_user = e2e_encryption_setup['user']
    test_project = e2e_encryption_setup['project']
    clean_db = e2e_encryption_setup['db']
    pass

# ✅ ALTERNATIVA - Usar test_environment_setup para configurar manualmente
def test_encryption_flow(test_environment_setup, worker_id):
    app = test_environment_setup['app']
    clean_db = test_environment_setup['db']
    # Crear usuarios y proyectos manualmente
    # Usar TestClient(app) para requests
    pass
```

**Fixtures Disponibles en test/e2e/conftest.py**:
- `test_environment_setup`: Setup base con Redis (decode_responses=False), DB y app configurados
- `authenticated_client_with_redis`: Cliente ya autenticado con Redis correcto
- `e2e_encryption_setup`: Setup completo para tests de encryption (incluye usuario, proyecto, cliente autenticado)
- `clean_redis`: Cliente Redis limpio con decode_responses=False

**Regla General**:
- Para tests de **encryption/sessions**, SIEMPRE usar fixtures del `test/e2e/conftest.py`
- Para tests normales, se puede usar el fixture `client` del conftest principal

#### ImportError de módulos

```bash
# Asegurarse de que PYTHONPATH incluye el directorio backend
export PYTHONPATH="${PYTHONPATH}:/path/to/backend"

# O ejecutar pytest desde el directorio backend
cd backend
pytest
```

#### Tests fallan por dependencias faltantes

```bash
# Verificar que todas las dependencias están instaladas
pip install -r requirements.txt

# Instalar dependencias de testing
pip install pytest pytest-cov pytest-mock
```

#### Errores de base de datos en tests

Los tests unitarios **NO** deben conectarse a la base de datos real. Verificar que:
- Se está usando mocking para `db` y `cursor`
- No hay imports que creen conexiones reales
- Los fixtures de DB son mocks

#### Advertencias de deprecación

```bash
# Ejecutar con advertencias filtradas
pytest -W ignore::DeprecationWarning

# Ver todas las advertencias
pytest -W all
```

---

## 📚 Recursos Adicionales

### Documentación

- [Pytest Documentation](https://docs.pytest.org/)
- [unittest.mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)

### Mejores Prácticas

- Tests deben ser **independientes** (no depender de otros tests)
- Tests deben ser **repetibles** (mismo resultado cada vez)
- Tests deben ser **rápidos** (mocking de I/O, DB, red)
- Tests deben ser **claros** (nombres descriptivos, aserciones explícitas)
- Tests deben ser **completos** (casos de éxito, error, edge cases)

### Herramientas Útiles

- **pytest-cov**: Cobertura de código
- **pytest-xdist**: Ejecución paralela
- **pytest-mock**: Helpers de mocking
- **pytest-watch**: Auto-ejecución en cambios
- **pytest-html**: Reportes HTML

---

## 📊 Métricas de Calidad

### Objetivos de Cobertura

- **Cobertura global**: > 80%
- **Módulos críticos** (seguridad, cifrado): > 95%
- **Líneas críticas**: 100%

### Indicadores de Calidad

- ✅ Todos los tests pasan
- ✅ No hay warnings críticos
- ✅ Tiempo de ejecución < 30s para suite completa
- ✅ Tests son mantenibles y legibles
- ✅ Mocking apropiado de dependencias externas

---

## 🔄 Mantenimiento

### Actualización de Tests

Cuando se modifica código de producción:

1. Actualizar tests afectados
2. Agregar nuevos tests para nueva funcionalidad
3. Verificar que tests antiguos aún pasan
4. Mantener cobertura > 80%

### Refactoring de Tests

- Extraer fixtures comunes a `conftest.py`
- Eliminar código duplicado
- Mantener tests simples y legibles
- Actualizar documentación

---

## ✅ Checklist de Tests

Antes de hacer commit de nuevo código:

- [ ] Tests escritos para nueva funcionalidad
- [ ] Tests para casos de error
- [ ] Tests para edge cases
- [ ] Todos los tests pasan
- [ ] Cobertura mantenida o mejorada
- [ ] Documentación de tests actualizada
- [ ] No hay código comentado en tests
- [ ] Fixtures reutilizables cuando sea apropiado

---

## 📞 Soporte

Para preguntas o issues con los tests:

1. Verificar esta documentación primero
2. Revisar logs de pytest con `-vv`
3. Consultar documentación de pytest
4. Crear issue en repositorio si persiste el problema

---

**Última actualización**: 2025-01-24
**Versión**: 2.1
**Autor**: DataMap Development Team

**Changelog v2.1**:
- ✅ Documentado problema común de fixtures en tests E2E de encryption
- ✅ Agregada sección de troubleshooting para errores de "invalid_credentials"
- ✅ Corregidos tests `test_multiple_users_same_project` y `test_session_hijacking_prevention`
- ✅ Explicación detallada de diferencia entre Redis `decode_responses=True` vs `False`

**Changelog v2.0**:
- ✅ Agregados 7 nuevos archivos de tests CRUD (~4,902 líneas)
- ✅ Total de archivos de tests: 17 (antes 10)
- ✅ Total de líneas: ~9,347 (antes ~4,445)
- ✅ Módulos con cobertura completa: 17 (antes 10)
- ✅ Cobertura CRUD significativamente ampliada
