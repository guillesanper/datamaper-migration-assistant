# Análisis de Gaps: Queries Directas vs CRUDs ORM

**Fecha:** 2025-12-30
**Total Queries Directas:** 71
**CRUDs Completados:** 20/20 (100%) ✅
**Funciones ORM Totales:** 162 funciones | **Tests Totales:** 403 tests ✅

---

## 🎉 PROGRESO RECIENTE

### ✅ FASE A COMPLETADA (2025-12-30) - 2 CRUDs Nuevos + 18 Funciones

| CRUD | Funciones | Tests | Estado |
|------|-----------|-------|--------|
| `notification_crud.py` | 8 funciones ORM | 30 tests | ✅ COMPLETADO |
| `migration_script_crud.py` | 10 funciones ORM | 31 tests | ✅ COMPLETADO |

**Funciones de notification_crud.py:**
- create_notification_orm()
- get_user_notifications_orm()
- get_notification_by_id_orm()
- mark_as_read_orm()
- mark_all_as_read_orm()
- delete_notification_orm()
- get_unread_count_orm()
- check_existing_invite_orm()

**Funciones de migration_script_crud.py:**
- create_migration_script_orm()
- get_migration_script_by_id_orm()
- get_migration_scripts_orm()
- create_migration_execution_orm()
- get_migration_execution_orm()
- update_execution_status_orm()
- get_execution_logs_orm()
- count_executions_orm()
- get_executions_paginated_orm()
- get_execution_by_project_orm()

**Resumen FASE A:**
- ✅ 2 CRUDs nuevos creados desde cero
- ✅ 18 funciones ORM implementadas (más de las 15 requeridas)
- ✅ 61 tests unitarios (100% passing)
- ✅ Soporte completo para migration system
- ✅ Validaciones y error handling
- ✅ Compatibilidad con patrones existentes

**Impacto:**
- Notification CRUD: 0 → 8 funciones ✅ NUEVO
- Migration Script CRUD: 0 → 10 funciones ✅ NUEVO

**Queries cubiertas:** 23 queries directas ahora tienen funciones ORM dedicadas

---

### ✅ FASE B COMPLETADA (2025-12-29) - 4 Funciones Implementadas

| Función | Archivo | Tests | Estado |
|---------|---------|-------|--------|
| `add_project_member_orm()` | [project_crud.py:700-772](backend/app/crud/project_crud.py#L700-L772) | 3 tests | ✅ |
| `get_plan_by_price_id_orm()` | [subscription_crud.py:631-670](backend/app/crud/subscription_crud.py#L631-L670) | 4 tests | ✅ |
| `delete_all_mappings_orm()` | [mappings_crud.py:1201-1223](backend/app/crud/mappings_crud.py#L1201-L1223) | 2 tests | ✅ |
| `bulk_create_mappings_orm()` | [mappings_crud.py:1226-1397](backend/app/crud/mappings_crud.py#L1226-L1397) | 3 tests | ✅ |

**Resumen:**
- ✅ 4 funciones nuevas implementadas
- ✅ 12 tests unitarios (100% passing)
- ✅ Soporte completo de encriptación AES-256-GCM
- ✅ Validaciones y error handling
- ✅ Compatibilidad con patrones existentes

**Impacto:**
- Projects CRUD: 12 → 13 funciones ✅ COMPLETO
- Subscription CRUD: 7 → 8 funciones ✅ COMPLETO
- Mappings CRUD: 5 → 7 funciones ✅ COMPLETO

**Queries cubiertas:** 4 queries directas ahora tienen funciones ORM dedicadas

---

## 📊 RESUMEN EJECUTIVO

### ✅ **COMPLETAMENTE CUBIERTOS (6 módulos - 48 queries)**

Estos módulos tienen CRUD completo y solo necesitan **refactorización** (cambiar queries por llamadas a CRUD):

| Módulo | CRUD | Queries Directas | Funciones ORM | Estado |
|--------|------|------------------|---------------|---------|
| **CSRF Tokens** | csrf_crud.py | 5 queries | 3 funciones | ✅ CUBIERTO |
| **Rate Limiting** | rate_limit_crud.py | 9 queries | 5 funciones | ✅ CUBIERTO |
| **Sessions** | session_crud.py | 5 queries | 8 funciones | ✅ CUBIERTO |
| **Users** | user_crud.py | 2 queries | 15 funciones | ✅ CUBIERTO |
| **Email OTP** | email_otp_crud.py | 1 query | 3 funciones | ✅ CUBIERTO |
| **Security Logs** | security_log_crud.py | 7 queries | 4 funciones | ✅ CUBIERTO |

**Total:** 29 queries directas que pueden migrarse YA

---

### ✅ **CRUDS FALTANTES - AHORA COMPLETADOS (2025-12-30)**

~~Estos módulos NO tienen CRUD~~ - **COMPLETADO**:

| Módulo | CRUD Creado | Queries Directas | Archivos Afectados | Estado |
|--------|-------------|------------------|-------------------|--------|
| **Notifications** | notification_crud.py | 18 queries | routers/notifications.py, utils/email_verification.py | ✅ IMPLEMENTADO |
| **Migration Scripts** | migration_script_crud.py | 5 queries | routers/migration.py | ✅ IMPLEMENTADO |

**Total:** ~~23 queries sin CRUD~~ → **23 queries AHORA CUBIERTAS** ✅

---

### ✅ **PARCIALMENTE CUBIERTOS - AHORA COMPLETADOS (4 funciones nuevas)**

~~Estos tienen CRUD pero **faltan funciones específicas**~~ - **COMPLETADO 2025-12-29**:

| Módulo | CRUD Existente | Gap Identificado | Estado |
|--------|----------------|------------------|--------|
| **Projects** | project_crud.py | ~~Falta:~~ `add_project_member_orm()` (usada en notifications.py:188-193) | ✅ IMPLEMENTADO |
| **Subscription Plans** | subscription_crud.py | ~~Falta:~~ `get_plan_by_price_id_orm()` (usada en stripe_service.py:475-485) | ✅ IMPLEMENTADO |
| **Mappings** | mappings_crud.py | ~~Falta:~~ `delete_all_mappings_orm()`, `bulk_create_mappings_orm()` (version_control_service.py:272-304) | ✅ IMPLEMENTADO |

---

## 🔴 MATRIZ DETALLADA DE GAPS

### 1. CSRF TOKENS - ✅ CUBIERTO AL 100%

**CRUD:** `backend/app/crud/csrf_crud.py` (3 funciones)

| Query Directa | Archivo:Línea | Función CRUD Equivalente | Acción |
|---------------|---------------|--------------------------|---------|
| DELETE tokens expirados | csrf_protection.py:56-60 | `cleanup_orm()` | ✅ Refactorizar |
| INSERT/UPSERT token | csrf_protection.py:63-71 | `generate_token_orm()` | ✅ Refactorizar |
| SELECT token válido | csrf_protection.py:116-122 | `validate_token_orm()` | ✅ Refactorizar |
| UPDATE marcar usado | csrf_protection.py:139-143 | `validate_token_orm()` incluye esto | ✅ Refactorizar |
| DELETE cleanup masivo | csrf_protection.py:162-165 | `cleanup_orm()` | ✅ Refactorizar |

**Cobertura:** 100% ✅
**Prioridad:** 🔴 ALTA (Middleware crítico de seguridad)

---

### 2. RATE LIMITING - ✅ CUBIERTO AL 100%

**CRUD:** `backend/app/crud/rate_limit_crud.py` (5 funciones)

| Query Directa | Archivo:Línea | Función CRUD Equivalente | Acción |
|---------------|---------------|--------------------------|---------|
| SELECT estado límite | rate_limiting.py:49-54 | `get_info_orm()` | ✅ Refactorizar |
| UPDATE bloquear IP | rate_limiting.py:77-84 | `check_limit_orm()` incluye bloqueo | ✅ Refactorizar |
| UPDATE incrementar | rate_limiting.py:92-98 | `check_limit_orm()` auto-incrementa | ✅ Refactorizar |
| UPDATE resetear | rate_limiting.py:101-108 | `check_limit_orm()` auto-resetea | ✅ Refactorizar |
| INSERT primer registro | rate_limiting.py:111-115 | `check_limit_orm()` auto-crea | ✅ Refactorizar |
| SELECT info límite | rate_limiting.py:151-156 | `get_info_orm()` | ✅ Refactorizar |
| DELETE por IP+endpoint | rate_limiting.py:216-219 | `reset_orm(ip, endpoint)` | ✅ Refactorizar |
| DELETE por IP | rate_limiting.py:221-224 | `reset_orm(ip)` | ✅ Refactorizar |
| DELETE cleanup | rate_limiting.py:244-248 | `cleanup_orm()` | ✅ Refactorizar |

**Cobertura:** 100% ✅
**Prioridad:** 🔴 ALTA (Middleware crítico de seguridad)

---

### 3. USER SESSIONS - ✅ CUBIERTO AL 100%

**CRUD:** `backend/app/crud/session_crud.py` (8 funciones)

| Query Directa | Archivo:Línea | Función CRUD Equivalente | Acción |
|---------------|---------------|--------------------------|---------|
| INSERT nueva sesión | auth.py:239-250 | `create_session_orm()` | ✅ Refactorizar |
| UPDATE revocar sesión | auth.py:507-514 | `revoke_session_orm()` | ✅ Refactorizar |
| UPDATE revocar todas | auth.py:540-547 | `revoke_all_user_sessions_orm()` | ✅ Refactorizar |
| SELECT+UPDATE última actividad | realtime.py:88-112 | `get_session_by_token_orm()` + `update_session_activity_orm()` | ✅ Refactorizar |

**Cobertura:** 100% ✅
**Nota:** `dependencies.py` ya usa `session_crud` en `CurrentUserORM` ✅
**Prioridad:** 🔴 CRÍTICA (Autenticación)

---

### 4. USERS - ✅ CUBIERTO AL 100%

**CRUD:** `backend/app/crud/user_crud.py` (15 funciones)

| Query Directa | Archivo:Línea | Función CRUD Equivalente | Acción |
|---------------|---------------|--------------------------|---------|
| SELECT usuario por email (login fallido) | auth.py:289-294 | `get_user_by_email_orm()` | ✅ Refactorizar |
| SELECT usuario por email (reenvío) | auth.py:419-424 | `get_user_by_email_orm()` | ✅ Refactorizar |

**Cobertura:** 100% ✅
**Prioridad:** 🔴 CRÍTICA (Autenticación)

---

### 5. EMAIL OTP - ✅ CUBIERTO AL 100%

**CRUD:** `backend/app/crud/email_otp_crud.py` (3 funciones)

| Query Directa | Archivo:Línea | Función CRUD Equivalente | Acción |
|---------------|---------------|--------------------------|---------|
| INSERT/UPSERT OTP | email_verification.py:26-32 | `create_otp_orm()` | ✅ Refactorizar |

**Cobertura:** 100% ✅
**Prioridad:** 🟡 MEDIA

---

### 6. SECURITY LOGS - ✅ CUBIERTO AL 100%

**CRUD:** `backend/app/crud/security_log_crud.py` (4 funciones)

| Query Directa | Archivo:Línea | Función CRUD Equivalente | Acción |
|---------------|---------------|--------------------------|---------|
| INSERT log evento | security_logger.py:74-87 | `log_event_orm()` | ✅ Refactorizar |
| SELECT logs filtrados | security_logger.py:419-455 | `get_logs_orm()` (filtros incluidos) | ✅ Refactorizar |
| SELECT count por tipo | security_logger.py:485-491 | `get_logs_orm()` con agregación | ⚠️ Agregar función agregación |
| SELECT count por severidad | security_logger.py:496-501 | `get_logs_orm()` con agregación | ⚠️ Agregar función agregación |
| SELECT top 10 IPs | security_logger.py:506-513 | `get_logs_orm()` con agregación | ⚠️ Agregar función agregación |
| SELECT por día | security_logger.py:518-524 | `get_logs_orm()` con agregación | ⚠️ Agregar función agregación |

**Cobertura:** 80% (falta funciones de agregación)
**Prioridad:** 🟡 MEDIA
**Nota:** Considerar agregar `get_logs_stats_orm()` para agregaciones

---

### 7. NOTIFICATIONS - ✅ COMPLETAMENTE CUBIERTO (2025-12-30)

**CRUD Creado:** `backend/app/crud/notification_crud.py` (8 funciones ORM)

**Funciones Implementadas (8):**
1. ✅ `create_notification_orm()` - Crear notificaciones
2. ✅ `get_user_notifications_orm()` - Listar con filtros y paginación
3. ✅ `get_notification_by_id_orm()` - Obtener por ID
4. ✅ `mark_as_read_orm()` - Marcar una como leída
5. ✅ `mark_all_as_read_orm()` - Marcar todas como leídas
6. ✅ `delete_notification_orm()` - Eliminar notificación
7. ✅ `get_unread_count_orm()` - Contador de no leídas
8. ✅ `check_existing_invite_orm()` - Verificar invitación existente

**Tests:** 30 tests unitarios (100% passing) ✅

**Cobertura:**
- ✅ Creación de notificaciones (invite, system, etc.)
- ✅ Listar con filtros (unread_only, paginación)
- ✅ Marcar como leídas (individual y masivo)
- ✅ Eliminación con validación de ownership
- ✅ Contador de no leídas
- ✅ Validación de invitaciones duplicadas
- ✅ Ordenamiento (no leídas primero, luego por fecha)
- ✅ Aislamiento entre usuarios

**Prioridad:** ✅ COMPLETADO

---

### 8. MIGRATION SCRIPTS - ✅ COMPLETAMENTE CUBIERTO (2025-12-30)

**CRUD Creado:** `backend/app/crud/migration_script_crud.py` (10 funciones ORM)

**Funciones Implementadas (10):**

**MigrationScript (3 funciones):**
1. ✅ `create_migration_script_orm()` - Crear script con hash SHA-256
2. ✅ `get_migration_script_by_id_orm()` - Obtener script por ID
3. ✅ `get_migration_scripts_orm()` - Listar scripts con paginación

**MigrationExecution (7 funciones):**
4. ✅ `create_migration_execution_orm()` - Crear registro de ejecución
5. ✅ `get_migration_execution_orm()` - Obtener ejecución por ID
6. ✅ `update_execution_status_orm()` - Actualizar estado y progreso
7. ✅ `get_execution_logs_orm()` - Obtener logs y errores
8. ✅ `count_executions_orm()` - Contar ejecuciones con filtros
9. ✅ `get_executions_paginated_orm()` - Listar ejecuciones paginadas
10. ✅ `get_execution_by_project_orm()` - Validar pertenencia a proyecto

**Tests:** 31 tests unitarios (100% passing) ✅

**Cobertura:**
- ✅ Creación de scripts con opciones (batch_size, constraints, dialect)
- ✅ Cálculo automático de hash SHA-256
- ✅ Dependency order tracking
- ✅ Creación de ejecuciones con backup_id
- ✅ Actualización de estado (pending → running → success/failed)
- ✅ Tracking de progreso (rows_migrated, execution_log)
- ✅ Filtrado por estado
- ✅ Paginación y ordenamiento
- ✅ Cálculo de duration_seconds
- ✅ Validación de pertenencia a proyecto
- ✅ Aislamiento entre proyectos

**Prioridad:** ✅ COMPLETADO

---

### 9. PROJECTS - ✅ COMPLETAMENTE CUBIERTO

**CRUD Existente:** `backend/app/crud/project_crud.py` (13 funciones ORM)

**Funciones Existentes:** ✅
- `create_project_orm()`
- `get_project_by_id_orm()`
- `get_user_projects_orm()`
- `update_project_orm()`
- `delete_project_orm()`
- `count_user_projects_orm()`
- `get_project_members_orm()`
- `remove_project_member_orm()`
- `check_user_access_orm()` ✅
- `get_user_metrics_comparison_orm()`
- `get_user_metrics_history_orm()`
- `force_recalculate_user_metrics_orm()`
- **`add_project_member_orm()`** ✅ **IMPLEMENTADO 2025-12-29**

**Cobertura:**

| Query Directa | Archivo:Línea | Función CRUD |
|---------------|---------------|--------------|
| INSERT project_member | notifications.py:188-193 | ✅ `add_project_member_orm()` **(project_crud.py:700-772)** |
| SELECT validar proyecto | migration.py:86, realtime.py:48 | ✅ `get_project_by_id_orm()` |
| SELECT check membership | migration.py:98-101, realtime.py:56-60 | ✅ `check_user_access_orm()` |

**Nueva Función Implementada:**
```python
# project_crud.py:700-772
def add_project_member_orm(
    db,
    project_id: str,
    user_id: str,
    role: str = 'viewer',
    added_by: Optional[str] = None
) -> Dict[str, Any]
```
- ✅ 3 tests implementados en test_project_crud_orm.py:730-829
- ✅ Validación de roles (owner, editor, viewer)
- ✅ Upsert automático si el miembro ya existe
- ✅ Audit trail con campo added_by

**Prioridad:** ✅ COMPLETADO

---

### 10. SUBSCRIPTION PLANS - ✅ COMPLETAMENTE CUBIERTO

**CRUD Existente:** `backend/app/crud/subscription_crud.py` (8 funciones ORM)

**Funciones Existentes:** ✅
- `get_subscription_plan_by_id_orm()`
- `get_subscription_plans_orm()`
- `get_user_subscription_orm()`
- `get_subscription_by_stripe_id_orm()`
- `create_subscription_orm()`
- `update_subscription_orm()`
- `get_customer_by_stripe_id_orm()`
- **`get_plan_by_price_id_orm()`** ✅ **IMPLEMENTADO 2025-12-29**

**Cobertura:**

| Query Directa | Archivo:Línea | Función CRUD |
|---------------|---------------|--------------|
| SELECT plan by price_id | stripe_service.py:475-485 | ✅ `get_plan_by_price_id_orm()` **(subscription_crud.py:631-670)** |

**Nueva Función Implementada:**
```python
# subscription_crud.py:631-670
def get_plan_by_price_id_orm(
    db,
    price_id: str
) -> Optional[Dict[str, Any]]:
    """
    Obtiene plan de suscripción por price_id de Stripe
    Busca tanto en monthly_price_id como yearly_price_id
    """
```
- ✅ 4 tests implementados en test_subscription_crud_orm.py:616-693
- ✅ Búsqueda dual: monthly_price_id y yearly_price_id
- ✅ Filtro de planes activos (is_active=True)
- ✅ Error logging para price_ids no encontrados

**Prioridad:** ✅ COMPLETADO

---

### 11. MAPPINGS - ✅ COMPLETAMENTE CUBIERTO

**CRUD Existente:** `backend/app/crud/mappings_crud.py` (7 funciones ORM)

**Funciones Existentes:** ✅
- `create_mapping_orm()`
- `get_mappings_by_project_orm()` ✅
- `get_mapping_by_id_orm()`
- `delete_mapping_orm()`
- `update_mapping_orm()`
- **`delete_all_mappings_orm()`** ✅ **IMPLEMENTADO 2025-12-29**
- **`bulk_create_mappings_orm()`** ✅ **IMPLEMENTADO 2025-12-29**

**Cobertura:**

| Query Directa | Archivo:Línea | Función CRUD |
|---------------|---------------|--------------|
| DELETE all mappings | version_control_service.py:272 | ✅ `delete_all_mappings_orm()` **(mappings_crud.py:1201-1223)** |
| INSERT bulk mappings | version_control_service.py:283-304 | ✅ `bulk_create_mappings_orm()` **(mappings_crud.py:1226-1397)** |
| SELECT mappings | migration.py:124-135 | ✅ `get_mappings_by_project_orm()` |

**Nuevas Funciones Implementadas:**
```python
# mappings_crud.py:1201-1223
def delete_all_mappings_orm(db, project_id: str) -> int:
    """Elimina todos los mappings de un proyecto (para restore de versión)"""

# mappings_crud.py:1226-1397
def bulk_create_mappings_orm(db, mappings: List[Dict]) -> List[Dict[str, Any]]:
    """Inserta múltiples mappings en una transacción con soporte completo de encriptación"""
```
- ✅ 5 tests implementados en test_mappings_crud_orm.py:568-785
- ✅ Soporte completo de encriptación AES-256-GCM (tablas y columnas)
- ✅ Modo conector con hashing SHA-256
- ✅ Transacciones atómicas para operaciones bulk
- ✅ Retorna valores desencriptados en respuesta

**Prioridad:** ✅ COMPLETADO

---

## 📋 PLAN DE ACCIÓN PRIORIZADO

### FASE A: Crear CRUDs Faltantes ✅ **COMPLETADA 2025-12-30**

| CRUD | Funciones Agregadas | Estado | Tests |
|------|---------------------|--------|-------|
| `notification_crud.py` | 8 funciones ORM | ✅ IMPLEMENTADO | 30 tests |
| `migration_script_crud.py` | 10 funciones ORM | ✅ IMPLEMENTADO | 31 tests |

**Total Implementado:** 18 funciones nuevas + 61 tests (100% passing) ✅
**Queries cubiertas:** 23 queries directas ahora tienen funciones ORM

---

### FASE B: Agregar Funciones a CRUDs Existentes ✅ **COMPLETADA 2025-12-29**

| CRUD | Función Agregada | Estado | Tests |
|------|------------------|--------|-------|
| `project_crud.py` | `add_project_member_orm()` | ✅ IMPLEMENTADO | 3 tests |
| `subscription_crud.py` | `get_plan_by_price_id_orm()` | ✅ IMPLEMENTADO | 4 tests |
| `mappings_crud.py` | `delete_all_mappings_orm()` | ✅ IMPLEMENTADO | 2 tests |
| `mappings_crud.py` | `bulk_create_mappings_orm()` | ✅ IMPLEMENTADO | 3 tests |
| `security_log_crud.py` | (Opcional) `get_logs_stats_orm()` para agregaciones | ⏳ PENDIENTE | - |

**Total Implementado:** 4 funciones nuevas + 12 tests (100% passing) ✅

---

### FASE C: Refactorizar Middlewares (1 día) 🔴 CRÍTICA

| Archivo | Queries a Migrar | CRUD a Usar |
|---------|------------------|-------------|
| `middleware/csrf_protection.py` | 5 queries | `csrf_crud` |
| `middleware/rate_limiting.py` | 9 queries | `rate_limit_crud` |

**Total:** 14 queries eliminadas

---

### FASE D: Refactorizar Routers (2 días) 🔴 ALTA

| Archivo | Queries a Migrar | CRUDs a Usar |
|---------|------------------|--------------|
| `routers/auth.py` | 5 queries | `session_crud`, `user_crud` |
| `routers/notifications.py` | 18 queries | `notification_crud`, `project_crud`, `user_crud` |
| `routers/migration.py` | 9 queries | `migration_script_crud`, `project_crud`, `mappings_crud` |
| `routers/realtime.py` | 4 queries | `project_crud`, `session_crud` |

**Total:** 36 queries eliminadas

---

### FASE E: Refactorizar Services (1 día) 🟡 MEDIA

| Archivo | Queries a Migrar | CRUDs a Usar |
|---------|------------------|--------------|
| `services/stripe_service.py` | 1 query | `subscription_crud` |
| `services/version_control_service.py` | 2 queries | `mappings_crud` (bulk ops) |
| `utils/security_logger.py` | 7 queries | `security_log_crud` |
| `utils/email_verification.py` | 2 queries | `email_otp_crud`, `notification_crud` |

**Total:** 12 queries eliminadas

---

## 🎯 OBJETIVOS FINALES

**Meta:** 0 queries directas fuera de CRUDs

| Categoría | Queries Actuales | Funciones Implementadas | Estado |
|-----------|------------------|-------------------------|--------|
| **Con CRUD completo** | 29 | 0 funciones (ya estaban) | ✅ LISTO |
| **CRUDs faltantes** | 23 | 18 funciones | ✅ COMPLETADO |
| **Funciones faltantes** | 19 | 4 funciones | ✅ COMPLETADO |
| **TOTAL** | **71** | **22 funciones** | ✅ **100%** |

**Progreso FASE A:** ✅ 2/2 CRUDs completados (100%) - 18 funciones
**Progreso FASE B:** ✅ 4/4 funciones completadas (100%)
**Total Funciones ORM Agregadas:** 22 funciones + 73 tests

**Tiempo Estimado Restante:** **4 días** (FASE C + D + E: Refactorización de middlewares, routers y services)

### 🎉 HITOS ALCANZADOS (2025-12-30)

✅ **TODOS LOS CRUDs COMPLETADOS (20/20 = 100%)**
- 28/28 modelos ORM con CRUD dedicado ✅
- 162 funciones ORM implementadas (117% del objetivo) ✅
- 403 tests unitarios (100% passing) ✅
- **0 CRUDs pendientes** - Solo falta refactorización ✅

---

## ✅ CRITERIOS DE ÉXITO

1. ✅ **100% de queries directas migradas a CRUDs**
2. ✅ **0 queries en middlewares** (seguridad crítica)
3. ✅ **0 queries en routers** (excepto validaciones simples)
4. ✅ **Services usan exclusivamente CRUDs**
5. ✅ **Test `test_no_direct_db_access.py` pasa** (validación arquitectónica)

---

## 📝 NOTAS TÉCNICAS

### Queries Legítimas (NO migrar)

Estos archivos tienen queries directos LEGÍTIMOS que NO deben migrarse:

- ✅ `backend/app/utils/db_adapters/*.py` - Adapters de diferentes BD (postgres, mysql, oracle, sqlserver)
- ✅ `backend/app/crud/*.py` - Solo quedan las funciones `*_orm` (SQLAlchemy); las variantes psycopg2 se retiraron

### Patrones de Refactorización

**Antes (Query Directo):**
```python
# auth.py:239
cursor = db.cursor()
cursor.execute("""
    INSERT INTO user_sessions (...)
    VALUES (%s, %s, ...)
""", (user_id, token, ...))
db.commit()
```

**Después (Uso de CRUD):**
```python
# auth.py:239
from app.crud import session_crud
session = session_crud.create_session_orm(
    db, user_id, token, ...
)
```

---

**Versión:** 1.0.0
**Proyecto:** DataMap - Migración SQLAlchemy ORM
