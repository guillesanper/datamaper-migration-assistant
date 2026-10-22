# Plan de Implementación: Sistema de Mappings Híbrido (Import + Connector)

> Documento histórico: el SQL citado está archivado en `backend/docs/legacy_sql/`; el esquema sale de Alembic. El script `run_migration_005.py` citado se eliminó.

## 📊 Estado de Implementación

**Última actualización:** 2025-12-09 16:45

| Fase | Tareas | Completadas | Pendientes | Estado |
|------|--------|-------------|------------|--------|
| **Fase 1: Base de Datos** | 1 | ✅ 1 | ⏳ 0 | ✅ COMPLETADA |
| **Fase 2: Backend Core** | 3 | ✅ 3 | ⏳ 0 | ✅ COMPLETADA |
| **Fase 3: Generación Scripts** | 2 | ❌ 0 | ⏳ 2 | ⏳ PENDIENTE |
| **Fase 4: Testing** | 2 | ❌ 0 | ⏳ 2 | ⏳ PENDIENTE |
| **Fase 5: Documentación** | 1 | ❌ 0 | ⏳ 1 | ⏳ PENDIENTE |
| **TOTAL** | **9** | **4** | **5** | **44% Completado** |

**Archivos creados:**
- ✅ `backend/docs/legacy_sql/migrations/005_mapping_source_types.sql`
- ✅ `backend/utilities/migrations/run_migration_005.py` (eliminado)

**Archivos modificados:**
- ✅ `backend/app/crud/mappings_crud.py` (TAREA 2 y 3 completadas)
- ✅ `backend/app/routers/mappings.py` (TAREA 6 completada)

**Próximos pasos:**
1. ⏳ Ejecutar migración 005 en la base de datos (pendiente de usuario)
2. ✅ **COMPLETADO**: TAREA 6 - Endpoint POST /mappings actualizado
3. ⏳ Test manual con Postman/curl
4. ⏳ Implementar TAREA 4: MigrationScriptService
5. ⏳ Implementar TAREA 5: Endpoint POST /generate-migration-script

---

## Contexto del Proyecto

**Proyecto:** DataMap - Herramienta de migración de datos entre bases de datos
**Objetivo:** Permitir al usuario crear mappings entre campos de BD origen y destino, con dos modos de operación independientes por cada lado (origen/destino):

### Modo A: Import (Esquemas Importados)
- Usuario importa un dump/schema JSON de la BD
- Esquemas persistidos en tablas `tables` y `columns` de PostgreSQL
- Nombres de tablas/columnas cifrados con **AES-256-GCM** (reversible)
- Puede descifrar y ver nombres en cualquier momento

### Modo B: Connector (Conexión Dinámica)
- Usuario se conecta directamente a la BD externa usando adapters
- Metadata cargada temporalmente en **Redis** (TTL 3h máximo 24h)
- Nombres de tablas/columnas hasheados con **SHA-256** (irreversible, one-way)
- Requiere sesión activa para resolver hashes y ver nombres reales

### Modo Híbrido (La Clave)
**Cada lado del mapping (origen y destino) puede usar un modo diferente:**
- Origen Import + Destino Import
- Origen Import + Destino Connector
- Origen Connector + Destino Import
- Origen Connector + Destino Connector

---

## Estado Actual del Sistema

### ✅ Implementado y Funcionando

1. **Adapters de BD** ([backend/app/utils/db_adapters/](./app/utils/db_adapters/))
   - PostgreSQLAdapter, MySQLAdapter, SQLServerAdapter, OracleAdapter
   - Solo leen metadata (INFORMATION_SCHEMA, no datos de usuario)
   - Context managers, validación SQL injection, tests completos

2. **Sesiones en Redis** ([backend/app/services/db_connection_service.py](./app/services/db_connection_service.py))
   - Credenciales cifradas AES-256-GCM
   - TTL configurable (default 3h, máximo 24h)
   - Key pattern: `db_connection_session:{user_id}:{session_id}`

3. **Cifrado AES-256** ([backend/app/utils/encryption.py](./app/utils/encryption.py))
   - AES-256-GCM + Argon2id para derivación de claves
   - Cifrado de campos de mappings (solo modo import actualmente)

### 🚧 En Implementación (Este Plan)

1. ✅ **Columnas en tabla `mappings`** para diferenciar modos - **COMPLETADO**
   - Migración SQL 005 creada y lista para aplicar
   - Incluye constraints, índices, funciones y vista
2. ⏳ **Hashing SHA-256** para modo connector - **PENDIENTE**
   - Lógica a implementar en CRUD (TAREA 2)
3. ⏳ **CRUD actualizado** para soportar ambos modos - **PENDIENTE**
   - TAREA 2: `create_mapping`
   - TAREA 3: `get_mappings_by_project`
   - TAREA 6: Endpoint POST /mappings
4. ⏳ **Servicio de generación de scripts** SQL - **PENDIENTE**
   - TAREA 4: MigrationScriptService
   - TAREA 5: Endpoint POST /generate-migration-script
5. ⏳ **Tests y documentación** - **PENDIENTE**
   - TAREA 7: Tests unitarios
   - TAREA 8: Tests de integración
   - TAREA 9: Documentación API
6. ⏳ **Frontend** para visualizar y crear mappings híbridos - **FUERA DE ALCANCE**
   - No incluido en este plan (solo backend)

---

## Arquitectura de la Solución

### Tabla `mappings` - Nueva Estructura

```sql
CREATE TABLE mappings (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,

    -- DIFERENCIACIÓN POR MODO (NUEVO)
    origin_source_type VARCHAR(20) DEFAULT 'import',      -- 'import' o 'connector'
    destination_source_type VARCHAR(20) DEFAULT 'import', -- 'import' o 'connector'

    -- MODO IMPORT - ORIGEN
    origin_table VARCHAR(255),                   -- Plaintext (legacy)
    origin_column VARCHAR(255),
    origin_table_encrypted TEXT,                 -- AES-256-GCM ciphertext
    origin_table_nonce TEXT,                     -- 96-bit nonce
    origin_column_encrypted TEXT,
    origin_column_nonce TEXT,
    origin_table_id INTEGER REFERENCES tables(id),  -- FK a tabla importada

    -- MODO CONNECTOR - ORIGEN
    origin_table_hash VARCHAR(64),               -- SHA-256 hash (one-way)
    origin_column_hash VARCHAR(64),
    origin_session_id UUID,                      -- Referencia a Redis session

    -- MODO IMPORT - DESTINO
    destination_table VARCHAR(255),
    destination_column VARCHAR(255),
    destination_table_encrypted TEXT,
    destination_table_nonce TEXT,
    destination_column_encrypted TEXT,
    destination_column_nonce TEXT,
    destination_table_id INTEGER REFERENCES tables(id),

    -- MODO CONNECTOR - DESTINO
    destination_table_hash VARCHAR(64),
    destination_column_hash VARCHAR(64),
    destination_session_id UUID,

    -- METADATA
    transformation_logic TEXT,
    transformation_logic_encrypted TEXT,
    transformation_logic_nonce TEXT,
    notes TEXT,
    is_encrypted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

---

## Sub-Tareas de Implementación

---

## ✅ TAREA 1: Migración SQL (Prioridad: CRÍTICA) - COMPLETADA

**Estado:** ✅ COMPLETADA
**Archivo creado:** `backend/docs/legacy_sql/migrations/005_mapping_source_types.sql`
**Script de aplicación:** `backend/utilities/migrations/run_migration_005.py` (eliminado)

**Notas importantes:**
- Se creó como migración 005 (no 004) porque ya existía 004_fix_encryption_nullable_fields.sql
- ⚠️ **CORRECCIÓN:** Los campos `origin_table_id` y `destination_table_id` son tipo `INTEGER` (no UUID) para coincidir con el tipo de `tables.id` en la BD existente

**Lo implementado:**
- ✅ 10 columnas nuevas (origin y destination: source_type, table_hash, column_hash, session_id, table_id)
  - `origin_table_id` y `destination_table_id`: **INTEGER** (FK a tables.id)
  - `origin_session_id` y `destination_session_id`: UUID (referencia Redis)
- ✅ 6 constraints de integridad (validación por modo import/connector)
- ✅ 9 índices optimizados (source_type, session_id, table_id, hashes compuestos)
- ✅ 3 funciones auxiliares (get_project_mapping_mode_stats, check_mapping_sessions_valid, cleanup_orphaned_connector_mappings)
- ✅ 1 vista (v_mappings_with_modes)
- ✅ 1 trigger (prevent_mode_change)
- ✅ Migración automática de datos existentes a modo 'import'
- ✅ Comentarios SQL en todas las columnas

**Archivo original (referencia):** `backend/docs/legacy_sql/migrations/005_mapping_source_types.sql`

**Prompt para Claude:**
```
Crea la migración SQL 004_mapping_source_types.sql que agregue las siguientes columnas a la tabla `mappings`:

ORIGEN:
- origin_source_type VARCHAR(20) DEFAULT 'import'
- origin_table_hash VARCHAR(64)
- origin_column_hash VARCHAR(64)
- origin_session_id UUID
- origin_table_id INTEGER REFERENCES tables(id) ON DELETE CASCADE

DESTINO:
- destination_source_type VARCHAR(20) DEFAULT 'import'
- destination_table_hash VARCHAR(64)
- destination_column_hash VARCHAR(64)
- destination_session_id UUID
- destination_table_id INTEGER REFERENCES tables(id) ON DELETE CASCADE

Agrega los siguientes CONSTRAINTS:
1. Si origin_source_type='connector', debe tener origin_session_id y origin_table_hash NOT NULL
2. Si origin_source_type='import', debe tener origin_table_id o origin_table o origin_table_encrypted NOT NULL
3. Lo mismo para destination_source_type

Agrega índices para:
- origin_source_type, destination_source_type
- origin_session_id, destination_session_id (WHERE NOT NULL)
- origin_table_id, destination_table_id (WHERE NOT NULL)
- (origin_table_hash, origin_column_hash) WHERE origin_source_type='connector'
- (destination_table_hash, destination_column_hash) WHERE destination_source_type='connector'

Agrega COMMENT ON COLUMN para cada nueva columna explicando su propósito.

Usa `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para que sea idempotente.
```

**Archivos de referencia:**
- `backend/docs/legacy_sql/migrations/003_encryption_infrastructure.sql` - Estilo y formato
- `backend/docs/legacy_sql/schema.sql` (líneas 59-69) - Estructura actual de `mappings`

**Validación:**
```bash
# Aplicar migración en BD de desarrollo
psql -U postgres -d datamap_dev -f backend/docs/legacy_sql/migrations/005_mapping_source_types.sql

# Verificar columnas creadas
psql -U postgres -d datamap_dev -c "\d+ mappings"
```

---

## ✅ TAREA 2: Actualizar CRUD de Mappings (Prioridad: CRÍTICA) - COMPLETADA

**Estado:** ✅ COMPLETADA (2025-12-09)
**Archivo:** `backend/app/crud/mappings_crud.py` (MODIFICADO)
**Líneas modificadas:** 10, 13-187

**Prompt para Claude:**
```
Actualiza la función `create_mapping` en backend/app/crud/mappings_crud.py para soportar modo híbrido.

Agrega los siguientes parámetros:
- origin_source_type: str = 'import'
- destination_source_type: str = 'import'
- origin_session_id: Optional[str] = None
- destination_session_id: Optional[str] = None
- origin_table_id: Optional[str] = None
- destination_table_id: Optional[str] = None

Lógica de procesamiento:

1. PROCESAR ORIGEN:
   - Si origin_source_type == 'connector':
     * origin_table_hash = hashlib.sha256(origin_table.encode()).hexdigest()
     * origin_column_hash = hashlib.sha256(origin_column.encode()).hexdigest()
     * origin_table_enc = None (no cifrar)
   - Si origin_source_type == 'import':
     * Cifrar con AES-256-GCM usando master_key_crud.encrypt_mapping_field()
     * origin_table_hash = None (no hashear)

2. PROCESAR DESTINO:
   - Misma lógica que origen pero para campos de destino

3. INSERTAR EN BD:
   - INSERT INTO mappings con TODOS los nuevos campos
   - Usar valores condicionales según el source_type de cada lado

4. RETORNAR:
   - Agregar nombres descifrados al result_dict para uso inmediato si es 'import'

Mantén retrocompatibilidad: si no se pasan los nuevos parámetros, usa defaults ('import').

IMPORTANTE: No modifiques las funciones get_mappings_by_project, get_mapping_by_id, update_mapping, delete_mapping todavía.
```

**Archivos de referencia:**
- `backend/app/crud/mappings_crud.py` (líneas 12-126) - Implementación actual
- `backend/app/crud/master_key_crud.py` (líneas 421-454) - Funciones de cifrado

**Lo implementado:**
- ✅ Import `hashlib` agregado (línea 10)
- ✅ 6 nuevos parámetros agregados a la firma de la función (líneas 23-28)
- ✅ Lógica de procesamiento para origen según modo (líneas 72-83)
- ✅ Lógica de procesamiento para destino según modo (líneas 98-109)
- ✅ INSERT actualizado con TODOS los campos nuevos (líneas 119-158)
- ✅ Valores condicionales para plaintext vs encrypted vs hashed (líneas 144-147)
- ✅ Result dict con nombres descifrados para uso inmediato (líneas 165-170)
- ✅ Retrocompatibilidad mantenida con defaults 'import'

**Tests pendientes:**
```python
# Test 1: Mapping con ambos import (legacy)
mapping = create_mapping(
    db, project_id, 'users', 'email', 'customers', 'correo',
    notes=None, user_id=user_id, encryption_key=key,
    origin_source_type='import',
    destination_source_type='import'
)

# Test 2: Mapping con ambos connector
mapping = create_mapping(
    db, project_id, 'users', 'email', 'customers', 'email',
    notes=None, user_id=user_id,
    origin_source_type='connector',
    destination_source_type='connector',
    origin_session_id='session-123',
    destination_session_id='session-456'
)
assert mapping['origin_table_hash'] == hashlib.sha256(b'users').hexdigest()

# Test 3: Mapping híbrido (import → connector)
mapping = create_mapping(
    db, project_id, 'users', 'email', 'customers', 'email',
    notes=None, user_id=user_id, encryption_key=key,
    origin_source_type='import',
    destination_source_type='connector',
    origin_table_id=table_id,
    destination_session_id='session-456'
)
```

---

## ✅ TAREA 3: Actualizar get_mappings_by_project (Prioridad: ALTA) - COMPLETADA

**Estado:** ✅ COMPLETADA (2025-12-09)
**Archivo:** `backend/app/crud/mappings_crud.py` (MODIFICADO)
**Líneas modificadas:** 177-295

**Prompt para Claude:**
```
Actualiza la función `get_mappings_by_project` en backend/app/crud/mappings_crud.py para retornar TODOS los nuevos campos.

Cambios en el SELECT:
- Agregar: origin_source_type, destination_source_type
- Agregar: origin_table_hash, origin_column_hash, origin_session_id, origin_table_id
- Agregar: destination_table_hash, destination_column_hash, destination_session_id, destination_table_id

Lógica de descifrado:
- Si origin_source_type == 'import' y encryption_key provisto:
  * Descifrar origin_table_encrypted → origin_table
  * Descifrar origin_column_encrypted → origin_column
- Si origin_source_type == 'connector':
  * Dejar origin_table_hash y origin_column_hash tal cual (NO se pueden descifrar)
  * El frontend resolverá los hashes consultando la sesión

Aplica la misma lógica para el destino.

Retorna el result_dict con todos los campos disponibles.
```

**Lo implementado:**
- ✅ SELECT actualizado con TODOS los nuevos campos (líneas 197-229)
- ✅ 10 campos adicionales incluidos en el SELECT (source_types, hashes, session_ids, table_ids)
- ✅ Lógica de descifrado condicional para origen (líneas 237-258)
- ✅ Lógica de descifrado condicional para destino (líneas 264-285)
- ✅ Descifrado de transformation_logic preservado (líneas 290-299)
- ✅ Hashes se retornan sin modificación para resolución frontend
- ✅ Documentación actualizada en docstring

**Ejemplo de resultado obtenido:**
```python
# Mapping import → import
{
    'id': 'uuid-123',
    'origin_source_type': 'import',
    'origin_table': 'users',  # Descifrado ✅
    'origin_column': 'email',
    'origin_table_id': 'uuid-tabla-users',
    'destination_source_type': 'import',
    'destination_table': 'customers',
    'destination_column': 'correo_electronico'
}

# Mapping connector → connector
{
    'id': 'uuid-456',
    'origin_source_type': 'connector',
    'origin_table_hash': 'a1b2c3d4...',  # Hash SHA-256 ✅
    'origin_column_hash': 'e5f6g7h8...',
    'origin_session_id': 'session-mysql-123',
    'destination_source_type': 'connector',
    'destination_table_hash': 'x9y8z7...',
    'destination_session_id': 'session-postgres-456'
}
```

---

## 📋 TAREA 4: Servicio de Generación de Scripts SQL (Prioridad: MEDIA)

**Archivo:** `backend/app/services/migration_script_service.py` (CREAR)

**Prompt para Claude:**
```
Crea el servicio `MigrationScriptService` en backend/app/services/migration_script_service.py que genere scripts SQL de migración basados en mappings.

Clase principal:
class MigrationScriptService:
    @staticmethod
    def generate_insert_script(
        mappings: List[Dict],
        origin_adapter: Optional[BaseDBAdapter],
        dest_adapter: Optional[BaseDBAdapter]
    ) -> str:
        """
        Genera script SQL INSERT resolviendo hashes si es necesario
        """

Lógica:
1. Iterar sobre mappings
2. Para cada mapping, verificar origin_source_type y destination_source_type:
   - Si 'connector': Resolver hash usando adapter.get_tables() y comparar SHA-256
   - Si 'import': Usar nombres directamente (ya descifrados)
3. Generar línea SQL:
   INSERT INTO {dest_table} ({dest_column}) SELECT {origin_column} FROM {origin_table};

Métodos helper:
- _resolve_hash_from_adapter(adapter, hash_value) -> str
  * Obtener todas las tablas del adapter
  * Calcular SHA-256 de cada nombre
  * Retornar nombre que coincida con hash_value

Manejo de errores:
- Si hash no se encuentra → raise ValueError con mensaje claro
- Si adapter es None para source_type='connector' → raise ValueError

Retornar script completo con:
- Header: -- Migration Script Generated at {datetime}
- Comentarios explicativos por mapping
- Queries SQL ejecutables
```

**Archivos de referencia:**
- `backend/app/utils/db_adapters/base_adapter.py` - Interfaz BaseDBAdapter
- `backend/app/utils/db_adapters/postgres_adapter.py` - Ejemplo de uso

**Ejemplo de salida:**
```sql
-- Migration Script
-- Generated at 2025-01-31 10:30:00 UTC
-- Project: Data Migration MySQL → PostgreSQL

-- Mapping 1: users.email → customers.correo_electronico
INSERT INTO customers (correo_electronico)
SELECT email FROM users;

-- Mapping 2: products.sku → inventory.product_code
INSERT INTO inventory (product_code)
SELECT sku FROM products;
```

---

## 📋 TAREA 5: Endpoint para Generar Scripts (Prioridad: MEDIA)

**Archivo:** `backend/app/routers/mappings.py` (AGREGAR endpoint)

**Prompt para Claude:**
```
Agrega un nuevo endpoint POST a backend/app/routers/mappings.py para generar scripts de migración.

Endpoint:
@router.post("/projects/{project_id}/generate-migration-script")
async def generate_migration_script(
    project_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    db_service: DBConnectionService = Depends(get_db_connection_service)
):

Lógica:
1. Obtener todos los mappings del proyecto usando mappings_crud.get_mappings_by_project()
2. Validar que haya al menos 1 mapping
3. Identificar qué sesiones se necesitan:
   - Extraer origin_session_id y destination_session_id únicos de los mappings
   - Solo para mappings con source_type='connector'
4. Obtener adapters para las sesiones necesarias:
   - session = db_service.get_session(user_id, session_id)
   - config = decrypt_session_config(session)
   - adapter = create_adapter_from_config(config)  # Helper a crear
5. Llamar a MigrationScriptService.generate_insert_script()
6. Retornar: {"script": script, "mappings_count": len(mappings)}

Validaciones:
- Si mapping tiene source_type='connector' pero sesión expiró → HTTP 410 Gone
- Si no se puede conectar a BD → HTTP 503 Service Unavailable
- Si hash no se encuentra en BD → HTTP 404 Not Found con detalle

Helper a crear:
def _create_adapter_from_config(config: DBConnectionConfig) -> BaseDBAdapter:
    if config.dialect == 'postgresql':
        return PostgreSQLAdapter(config)
    elif config.dialect == 'mysql':
        return MySQLAdapter(config)
    # ... etc
```

**Respuesta exitosa:**
```json
{
  "script": "-- Migration Script\n...",
  "mappings_count": 15,
  "generated_at": "2025-01-31T10:30:00Z"
}
```

**Errores posibles:**
```json
// 410 Gone - Sesión expirada
{
  "detail": "Session session-123 has expired. Please reconnect to the database."
}

// 404 Not Found - Hash no encontrado
{
  "detail": "Hash a1b2c3d4... not found in origin database. Table may have been renamed or deleted."
}

// 503 Service Unavailable - BD no alcanzable
{
  "detail": "Cannot connect to origin database: Connection refused"
}
```

---

## ✅ TAREA 6: Actualizar Router de Creación de Mappings (Prioridad: ALTA) - COMPLETADA

**Estado:** ✅ COMPLETADA (2025-12-09)
**Archivo:** `backend/app/routers/mappings.py` (MODIFICADO)
**Líneas modificadas:** 744-758, 871-1081

**Prompt para Claude:**
```
Actualiza el endpoint POST /projects/{project_id}/mappings en backend/app/routers/mappings.py para soportar los nuevos parámetros.

Cambios en el endpoint:
@router.post("/projects/{project_id}/mappings")
async def create_mapping(
    project_id: str,
    mapping: MappingCreate,
    # NUEVOS parámetros (query params opcionales)
    origin_source_type: str = 'import',
    destination_source_type: str = 'import',
    origin_session_id: Optional[str] = None,
    destination_session_id: Optional[str] = None,
    origin_table_id: Optional[str] = None,
    destination_table_id: Optional[str] = None,
    ...
):

Validaciones adicionales:
1. Si origin_source_type=='connector', verificar que origin_session_id esté presente
2. Si destination_source_type=='connector', verificar que destination_session_id esté presente
3. Validar que las sesiones existan y no hayan expirado usando db_service.get_session()
4. Si source_type=='import', validar que origin_table_id o destination_table_id existan en tabla `tables`

Pasar nuevos parámetros a mappings_crud.create_mapping():
new_mapping = mappings_crud.create_mapping(
    db=db,
    project_id=project_id,
    origin_table=mapping.origin_table,
    origin_column=mapping.origin_column,
    destination_table=mapping.destination_table,
    destination_column=mapping.destination_column,
    notes=None,
    user_id=current_user['id'],
    encryption_key=encryption_key,
    origin_source_type=origin_source_type,  # NUEVO
    destination_source_type=destination_source_type,  # NUEVO
    origin_session_id=origin_session_id,  # NUEVO
    destination_session_id=destination_session_id,  # NUEVO
    origin_table_id=origin_table_id,  # NUEVO
    destination_table_id=destination_table_id  # NUEVO
)

Mantener el resto de la lógica (version control, realtime broadcast, etc.).
```

**Ubicación exacta:** `backend/app/routers/mappings.py` líneas 890-1030 (función actual `create_mapping`)

**Lo implementado:**

1. ✅ **Parámetros query opcionales agregados** (líneas 751-757):
   - `origin_source_type: str = 'import'` (default para retrocompatibilidad)
   - `destination_source_type: str = 'import'`
   - `origin_session_id: Optional[str] = None`
   - `destination_session_id: Optional[str] = None`
   - `origin_table_id: Optional[str] = None`
   - `destination_table_id: Optional[str] = None`

2. ✅ **Validaciones implementadas** (líneas 871-973):
   - **Validación 1**: Si `source_type == 'connector'`, `session_id` debe estar presente (HTTP 400 Bad Request)
   - **Validación 2**: Sesión existe y no ha expirado usando `DBConnectionService.get_session()`
     - HTTP 404 Not Found si sesión no existe
     - HTTP 410 Gone si sesión expiró
     - HTTP 403 Forbidden si sesión no pertenece al usuario actual
   - **Validación 3**: Si `source_type == 'import'` y `table_id` provisto, validar que existe en tabla `tables` (HTTP 404)

3. ✅ **Integración con CRUD** (líneas 1064-1081):
   - Llamada a `mappings_crud.create_mapping()` actualizada con 6 nuevos parámetros
   - Mantiene toda la lógica existente (version control, realtime broadcast, validaciones de tipo, etc.)

4. ✅ **Retrocompatibilidad garantizada**:
   - Todos los parámetros nuevos son **opcionales** con defaults seguros
   - Requests antiguos sin nuevos parámetros funcionan exactamente igual (modo import/import por defecto)
   - No se modificó el modelo `MappingCreate` (body request)
   - No se rompió ninguna funcionalidad existente

**Códigos de error implementados:**
- `400 Bad Request`: Connector mode sin session_id
- `404 Not Found`: Table_id o session_id no existe
- `410 Gone`: Sesión expiró
- `403 Forbidden`: Sesión no pertenece al usuario

**Ejemplo de uso:**

```bash
# Request antiguo (sigue funcionando sin cambios)
curl -X POST http://localhost:8000/api/mappings/projects/{project_id}/save \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "origin_table": "users",
    "origin_column": "email",
    "destination_table": "customers",
    "destination_column": "email"
  }'

# Request nuevo: Mapping connector → connector
curl -X POST "http://localhost:8000/api/mappings/projects/{project_id}/save?origin_source_type=connector&destination_source_type=connector&origin_session_id=session-123&destination_session_id=session-456" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "origin_table": "users",
    "origin_column": "email",
    "destination_table": "customers",
    "destination_column": "email"
  }'

# Request híbrido: import → connector
curl -X POST "http://localhost:8000/api/mappings/projects/{project_id}/save?origin_source_type=import&destination_source_type=connector&origin_table_id=uuid-table&destination_session_id=session-456" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "origin_table": "users",
    "origin_column": "email",
    "destination_table": "customers",
    "destination_column": "email"
  }'
```

**Dependencias agregadas:**
- Import de `DBConnectionService` de `app.services.db_connection_service`
- Import de excepciones `SessionNotFoundError`, `SessionExpiredError`
- Import de `get_redis_client()` de `app.database.redis_client`
- Import de `Settings` de `config`

**Impacto en frontend:**
- ✅ **NO REQUIERE CAMBIOS**: El frontend actual sigue funcionando sin modificaciones
- ⏳ **Futuro**: Para soportar modo connector, el frontend deberá:
  1. Agregar UI para seleccionar source_type (import/connector)
  2. Si connector: Mostrar selector de sesiones activas
  3. Pasar nuevos parámetros como query params en el POST

---

## 📋 TAREA 7: Tests Unitarios de Hashing (Prioridad: MEDIA)

**Archivo:** `backend/test/unit/test_mapping_hashing.py` (CREAR)

**Prompt para Claude:**
```
Crea tests unitarios en backend/test/unit/test_mapping_hashing.py para verificar el hashing de mappings.

Tests a implementar:

1. test_hash_table_name_deterministic():
   - Hashear 'users' dos veces
   - Verificar que los hashes sean idénticos
   - Verificar longitud del hash (64 caracteres hex)

2. test_hash_different_tables_different_hashes():
   - Hashear 'users' y 'products'
   - Verificar que los hashes sean diferentes

3. test_hash_case_sensitive():
   - Hashear 'Users' y 'users'
   - Verificar que los hashes sean diferentes

4. test_create_mapping_connector_mode_generates_hashes():
   - Crear mapping con origin_source_type='connector'
   - Verificar que origin_table_hash y origin_column_hash existan
   - Verificar que coincidan con SHA-256 manual

5. test_create_mapping_import_mode_no_hashes():
   - Crear mapping con origin_source_type='import'
   - Verificar que origin_table_hash sea NULL
   - Verificar que origin_table_encrypted exista

6. test_hybrid_mapping_origin_connector_dest_import():
   - Crear mapping híbrido
   - Verificar origen tiene hashes
   - Verificar destino tiene cifrado

Usar pytest con fixtures para:
- db: Conexión a BD de test
- project_id: UUID de proyecto test
- encryption_key: Clave de cifrado
```

**Estructura del archivo:**
```python
import pytest
import hashlib
from app.crud import mappings_crud

class TestMappingHashing:
    def test_hash_table_name_deterministic(self):
        hash1 = hashlib.sha256('users'.encode()).hexdigest()
        hash2 = hashlib.sha256('users'.encode()).hexdigest()
        assert hash1 == hash2
        assert len(hash1) == 64

    # ... resto de tests
```

---

## 📋 TAREA 8: Tests de Integración Modo Conector (Prioridad: BAJA)

**Archivo:** `backend/test/integration/test_connector_mappings.py` (CREAR)

**Prompt para Claude:**
```
Crea tests de integración en backend/test/integration/test_connector_mappings.py que verifiquen el flujo completo de mappings con conectores.

Test scenario 1: Crear mapping connector → connector con PostgreSQL real
1. Conectar a PostgreSQL de test (puerto 5433)
2. Crear sesión con DBConnectionService
3. Crear mapping usando session_id
4. Verificar que hashes se almacenaron correctamente
5. Generar script de migración
6. Verificar que script resuelve hashes consultando BD real

Test scenario 2: Mapping híbrido (import → connector)
1. Importar schema a tabla `tables`
2. Crear sesión con conector para destino
3. Crear mapping híbrido
4. Generar script
5. Verificar resolución correcta de hashes del lado conector

Test scenario 3: Sesión expirada al generar script
1. Crear mapping con connector
2. Forzar expiración de sesión (TTL = 0)
3. Intentar generar script
4. Verificar error HTTP 410 Gone

Usar Docker Compose para levantar PostgreSQL y MySQL de test.
```

---

## 📋 TAREA 9: Documentación API (Prioridad: BAJA)

**Archivo:** `backend/docs/API_MAPPINGS.md` (CREAR)

**Prompt para Claude:**
```
Crea documentación de API en backend/docs/API_MAPPINGS.md para los nuevos endpoints de mappings.

Secciones:
1. Introducción al sistema de mappings híbrido
2. Modos de operación (import vs connector)
3. Endpoint POST /projects/{project_id}/mappings
   - Parámetros nuevos
   - Ejemplos de request para cada combinación
   - Respuestas y códigos de error
4. Endpoint POST /projects/{project_id}/generate-migration-script
   - Descripción
   - Ejemplos de respuesta
   - Manejo de errores (sesión expirada, hash no encontrado, etc.)
5. Diagramas de flujo (formato Mermaid)
6. Ejemplos de uso con curl

Formato: Markdown con bloques de código JSON.
```

---

## Orden de Ejecución Recomendado

### Fase 1: Base de Datos (Día 1) - ✅ COMPLETADA
1. ✅ **TAREA 1: Migración SQL** - **COMPLETADA** ✨
   - Archivo: `backend/docs/legacy_sql/migrations/005_mapping_source_types.sql`
   - Script: `backend/utilities/migrations/run_migration_005.py` (eliminado)
2. ⏳ Verificar con `psql -c "\d+ mappings"` (Pendiente de ejecutar por el usuario)

### Fase 2: Backend Core (Día 1-2) - 🚧 EN PROGRESO (67% completado)
3. ✅ **TAREA 2: Actualizar create_mapping en CRUD** - **COMPLETADA** ✨
   - Archivo: `backend/app/crud/mappings_crud.py` líneas 10, 13-187
   - Import hashlib agregado
   - 6 parámetros nuevos con defaults
   - Lógica híbrida implementada (hash SHA-256 + cifrado AES-256)
4. ✅ **TAREA 3: Actualizar get_mappings_by_project** - **COMPLETADA** ✨
   - Archivo: `backend/app/crud/mappings_crud.py` líneas 177-295
   - SELECT ampliado con 10 campos nuevos
   - Descifrado condicional por modo
5. ⏳ TAREA 6: Actualizar endpoint POST /mappings
6. ⏳ Test manual con Postman/curl

### Fase 3: Generación de Scripts (Día 2-3) - ⏳ PENDIENTE
7. ⏳ TAREA 4: Servicio MigrationScriptService
8. ⏳ TAREA 5: Endpoint POST /generate-migration-script
9. ⏳ Test manual generando script

### Fase 4: Testing (Día 3-4) - ⏳ PENDIENTE
10. ⏳ TAREA 7: Tests unitarios
11. ⏳ TAREA 8: Tests de integración
12. ⏳ Ejecutar `pytest` y verificar cobertura

### Fase 5: Documentación (Día 4) - ⏳ PENDIENTE
13. ⏳ TAREA 9: Documentación API

---

## Comandos Útiles

### Aplicar migraciones
```bash
cd backend
psql -U postgres -d datamap_dev -f docs/legacy_sql/migrations/005_mapping_source_types.sql
```

### Ejecutar tests
```bash
cd backend
pytest test/unit/test_mapping_hashing.py -v
pytest test/integration/test_connector_mappings.py -v
```

### Verificar estructura de BD
```bash
psql -U postgres -d datamap_dev -c "\d+ mappings"
psql -U postgres -d datamap_dev -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mappings';"
```

### Test manual con curl
```bash
# Crear mapping connector → connector
curl -X POST http://localhost:8000/api/projects/{project_id}/mappings \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "origin_table": "users",
    "origin_column": "email",
    "destination_table": "customers",
    "destination_column": "email"
  }' \
  -G \
  --data-urlencode "origin_source_type=connector" \
  --data-urlencode "destination_source_type=connector" \
  --data-urlencode "origin_session_id=session-123" \
  --data-urlencode "destination_session_id=session-456"

# Generar script
curl -X POST http://localhost:8000/api/projects/{project_id}/generate-migration-script \
  -H "Authorization: Bearer {token}"
```

---

## Archivos Críticos a Revisar

### Backend Core
- `backend/app/crud/mappings_crud.py` - CRUD de mappings
- `backend/app/routers/mappings.py` - Endpoints API
- `backend/app/utils/encryption.py` - Cifrado AES-256
- `backend/app/crud/master_key_crud.py` - Funciones de cifrado

### Adapters
- `backend/app/utils/db_adapters/base_adapter.py` - Clase base
- `backend/app/utils/db_adapters/postgres_adapter.py` - PostgreSQL
- `backend/app/services/db_connection_service.py` - Gestión sesiones

### Schema y Migraciones
- `backend/docs/legacy_sql/schema.sql` - Schema inicial
- `backend/docs/legacy_sql/migrations/003_encryption_infrastructure.sql` - Última migración

### Tests
- `backend/test/unit/db_connectors/test_postgres_adapter.py` - Ejemplo de tests
- `backend/test/integration/test_db_connection_flow.py` - Tests de sesiones

---

## Consideraciones Importantes

### Seguridad
1. **NUNCA** almacenar hashes MD5 o SHA-1 (usar SHA-256)
2. **SIEMPRE** validar session_id contra Redis antes de usar
3. **SIEMPRE** validar ownership (user_id) al acceder sesiones
4. **NUNCA** exponer hashes completos en logs (truncar a 8 chars)

### Performance
1. Cachear resolución de hashes (LRU cache) en MigrationScriptService
2. Usar batch inserts si proyecto tiene 1000+ mappings
3. Índices en (origin_table_hash, origin_column_hash) para búsquedas rápidas

### Retrocompatibilidad
1. Mantener compatibilidad con mappings legacy (sin source_type)
2. Migrar automáticamente mappings existentes a origin_source_type='import'
3. No romper endpoints existentes del frontend

---

## Preguntas Frecuentes

### ¿Qué pasa si la sesión expira mientras se generan scripts?
- Retornar HTTP 410 Gone con mensaje claro
- Frontend debe mostrar opción de reconectar

### ¿Se pueden mezclar import y connector en el mismo mapping?
- Sí, es el modo híbrido. Cada lado (origen/destino) es independiente.

### ¿Los hashes se pueden revertir?
- NO. SHA-256 es one-way. Solo se pueden resolver consultando la BD real.

### ¿Qué pasa si renombran una tabla en la BD externa?
- El hash cambiará y no se encontrará. Retornar error 404 con detalle.

### ¿Cómo se visualizan los hashes en el frontend?
- Con sesión activa: Resolver consultando metadata de Redis
- Sin sesión: Mostrar hash truncado (primeros 8 chars)

---

## Contacto y Soporte

**Documentación adicional:**
- Plan completo: `C:\Users\guill\.claude\plans\dynamic-wandering-pelican.md`
- Reporte de exploración: Ver mensajes de agentes de exploración

**Para continuar el desarrollo:**
1. Leer este documento completo
2. Verificar que la migración SQL (TAREA 1) esté aplicada
3. Ejecutar tests existentes para validar que nada se rompió
4. Proceder con las tareas en orden según la fase actual
