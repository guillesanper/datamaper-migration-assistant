# TAREA 4 y 5: Generación de Scripts SQL - Resumen de Implementación

**Fecha:** 2025-12-09
**Estado:** ✅ COMPLETADA
**Archivos creados:**
- [backend/app/services/migration_script_service.py](backend/app/services/migration_script_service.py) (NUEVO)

**Archivos modificados:**
- [backend/app/routers/mappings.py](backend/app/routers/mappings.py) (líneas 21-41: imports, 2153-2403: endpoint)

---

## 📋 Resumen Ejecutivo

Se implementó exitosamente el **sistema de generación de scripts SQL de migración** que:
- Genera scripts `INSERT INTO ... SELECT` basados en mappings del proyecto
- Resuelve hashes SHA-256 consultando bases de datos externas en tiempo real
- Soporta mappings híbridos (import + connector)
- Maneja sesiones Redis con validación de expiración
- Incluye manejo robusto de errores (sesión expirada, hash no encontrado, BD no disponible)

---

## 🔧 TAREA 4: MigrationScriptService - COMPLETADA

### Archivo Creado
**Ubicación:** [backend/app/services/migration_script_service.py](backend/app/services/migration_script_service.py)

### Clases e Implementación

#### 1. Excepciones Personalizadas

```python
class MigrationScriptServiceError(Exception):
    """Base exception for MigrationScriptService"""
    pass

class HashNotFoundError(MigrationScriptServiceError):
    """Hash no se encontró en la base de datos"""
    def __init__(self, hash_value: str, side: str):
        self.hash_value = hash_value
        self.side = side
```

#### 2. Clase Principal: MigrationScriptService

**Método principal:**
```python
@staticmethod
def generate_insert_script(
    mappings: List[Dict[str, Any]],
    origin_adapter: Optional[BaseDBAdapter] = None,
    dest_adapter: Optional[BaseDBAdapter] = None,
    project_name: Optional[str] = None
) -> str
```

**Funcionalidades:**
- ✅ Itera sobre todos los mappings del proyecto
- ✅ Para cada mapping, detecta si es `import` o `connector`:
  - Si **import**: Usa nombres descifrados directamente (ya procesados por CRUD)
  - Si **connector**: Resuelve hashes SHA-256 consultando `adapter.get_tables()` y `adapter.get_columns()`
- ✅ Genera líneas SQL: `INSERT INTO {dest_table} ({dest_column}) SELECT {origin_column} FROM {origin_table};`
- ✅ Incluye comentarios descriptivos por cada mapping
- ✅ Header con metadata del script (fecha, proyecto, count)

#### 3. Métodos Helper

**_resolve_name():**
```python
@staticmethod
def _resolve_name(
    mapping: Dict[str, Any],
    side: str,
    adapter: Optional[BaseDBAdapter],
    is_column: bool = False
) -> str
```
- Resuelve nombres según modo (import vs connector)
- Llama a `_resolve_hash_from_adapter()` si es necesario

**_resolve_hash_from_adapter():**
```python
@staticmethod
def _resolve_hash_from_adapter(
    adapter: BaseDBAdapter,
    hash_value: str,
    is_column: bool,
    side: str
) -> str
```
- ✅ Obtiene todas las tablas del adapter usando `adapter.get_tables()`
- ✅ Calcula SHA-256 de cada nombre
- ✅ Retorna nombre que coincida con `hash_value`
- ✅ Lanza `HashNotFoundError` si no encuentra match

**Lógica de resolución:**
```python
# Para tablas
for table in adapter.get_tables():
    table_hash = hashlib.sha256(table.name.encode()).hexdigest()
    if table_hash == hash_value:
        return table.name

# Para columnas (busca en TODAS las tablas)
for table in adapter.get_tables():
    columns = adapter.get_columns(table.name)
    for column in columns:
        column_hash = hashlib.sha256(column.name.encode()).hexdigest()
        if column_hash == hash_value:
            return column.name
```

### Ejemplo de Script Generado

```sql
-- Migration Script
-- Generated at 2025-12-09 16:45:00 UTC
-- Project: Data Migration MySQL → PostgreSQL
-- Total mappings: 2

-- Mapping 1: users.email → customers.correo_electronico
INSERT INTO customers (correo_electronico) SELECT email FROM users;

-- Mapping 2: products.sku → inventory.product_code
INSERT INTO inventory (product_code) SELECT sku FROM products;

```

---

## 🌐 TAREA 5: Endpoint POST /generate-migration-script - COMPLETADA

### Archivo Modificado
**Ubicación:** [backend/app/routers/mappings.py](backend/app/routers/mappings.py)

### Imports Agregados (líneas 21-41)

```python
# Imports para generación de scripts de migración
from app.services.migration_script_service import (
    MigrationScriptService,
    HashNotFoundError,
    MigrationScriptServiceError
)
from app.services.db_connection_service import (
    DBConnectionService,
    SessionNotFoundError,
    SessionExpiredError
)
from app.database.redis_client import get_redis_client
from app.utils.db_adapters import (
    PostgreSQLAdapter,
    MySQLAdapter,
    SQLServerAdapter,
    OracleAdapter,
    DBConnectionError
)
from app.models.db_connection import DBConnectionConfig
from config import Settings
```

### Función Helper: _create_adapter_from_config (líneas 2153-2177)

```python
def _create_adapter_from_config(config: DBConnectionConfig):
    """
    Crea un adapter de BD a partir de configuración descifrada.
    """
    adapter_config = config.to_adapter_config()

    if config.dialect == 'postgresql':
        return PostgreSQLAdapter(adapter_config)
    elif config.dialect == 'mysql':
        return MySQLAdapter(adapter_config)
    elif config.dialect == 'sqlserver':
        return SQLServerAdapter(adapter_config)
    elif config.dialect == 'oracle':
        return OracleAdapter(adapter_config)
    else:
        raise ValueError(f"Unsupported dialect: {config.dialect}")
```

### Endpoint Principal (líneas 2180-2403)

```python
@router.post("/projects/{project_id}/generate-migration-script")
async def generate_migration_script(
    project_id: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
)
```

### Flujo de Ejecución

#### 1. Obtener Mappings del Proyecto
```python
mappings = mappings_crud.get_mappings_by_project(
    db=db,
    project_id=project_id,
    encryption_key=encryption_key
)
```
- Obtiene todos los mappings con nombres descifrados (modo import) o hashes (modo connector)

#### 2. Identificar Sesiones Necesarias
```python
origin_session_ids = set()
dest_session_ids = set()

for mapping in mappings:
    if mapping.get('origin_source_type') == 'connector':
        origin_session_ids.add(mapping.get('origin_session_id'))
    if mapping.get('destination_source_type') == 'connector':
        dest_session_ids.add(mapping.get('destination_session_id'))
```
- Extrae `session_id` únicos de mappings con `source_type='connector'`

#### 3. Validar y Obtener Sesiones de Redis
```python
db_service = DBConnectionService(redis_client, settings.MASTER_KEY)
session = db_service.get_session(current_user['id'], session_id)

# Validar ownership
if session.user_id != current_user['id']:
    raise HTTPException(status_code=403, ...)
```

**Validaciones implementadas:**
- ✅ Sesión existe en Redis
- ✅ Sesión no ha expirado (TTL)
- ✅ Sesión pertenece al usuario actual (ownership)

#### 4. Crear Adapters y Conectar
```python
config = db_service.get_decrypted_config(session)
adapter = _create_adapter_from_config(config)
adapter.connect()
```
- Descifra credenciales de Redis usando AES-256-GCM
- Crea adapter según dialecto (PostgreSQL, MySQL, SQL Server, Oracle)
- Conecta a la base de datos externa

#### 5. Generar Script SQL
```python
script = MigrationScriptService.generate_insert_script(
    mappings=mappings,
    origin_adapter=origin_adapter,
    dest_adapter=dest_adapter,
    project_name=project_name
)
```

#### 6. Retornar Respuesta
```python
return {
    "script": script,
    "mappings_count": len(mappings),
    "generated_at": datetime.utcnow().isoformat()
}
```

#### 7. Cleanup (Finally Block)
```python
finally:
    if origin_adapter and origin_adapter.is_connected:
        origin_adapter.disconnect()
    if dest_adapter and dest_adapter.is_connected:
        dest_adapter.disconnect()
```
- Desconecta adapters **SIEMPRE**, incluso si hay errores

---

## 📊 Códigos de Error HTTP

| Código | Descripción | Cuándo ocurre |
|--------|-------------|---------------|
| `404 Not Found` | No se encontraron mappings | Proyecto sin mappings |
| `404 Not Found` | Hash no encontrado en BD | Hash no coincide con ninguna tabla/columna |
| `404 Not Found` | Sesión no encontrada | `session_id` no existe en Redis |
| `403 Forbidden` | Sesión no pertenece al usuario | `session.user_id != current_user['id']` |
| `410 Gone` | Sesión expiró | TTL de Redis expiró |
| `503 Service Unavailable` | No se puede conectar a BD | Credenciales inválidas o BD no alcanzable |
| `500 Internal Server Error` | Error inesperado | Excepción no capturada |

---

## 🧪 Ejemplos de Uso

### Request Exitoso (Mappings Import → Import)

```bash
curl -X POST "http://localhost:8000/api/mappings/projects/{project_id}/generate-migration-script" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json"
```

**Response (200 OK):**
```json
{
  "script": "-- Migration Script\n-- Generated at 2025-12-09 16:45:00 UTC\n-- Project: My Project\n-- Total mappings: 3\n\n-- Mapping 1: users.email → customers.correo_electronico\nINSERT INTO customers (correo_electronico) SELECT email FROM users;\n\n-- Mapping 2: products.sku → inventory.product_code\nINSERT INTO inventory (product_code) SELECT sku FROM products;\n\n-- Mapping 3: orders.total → sales.amount\nINSERT INTO sales (amount) SELECT total FROM orders;\n\n",
  "mappings_count": 3,
  "generated_at": "2025-12-09T16:45:00.123456"
}
```

### Request con Sesión Expirada

```bash
curl -X POST "http://localhost:8000/api/mappings/projects/{project_id}/generate-migration-script" \
  -H "Authorization: Bearer {token}"
```

**Response (410 Gone):**
```json
{
  "detail": "Origin session session-abc123 has expired. Please reconnect to the database."
}
```

### Request con Hash No Encontrado

**Response (404 Not Found):**
```json
{
  "detail": "Hash a1b2c3d4... not found in origin database. Table or column may have been renamed or deleted."
}
```

### Request con BD No Disponible

**Response (503 Service Unavailable):**
```json
{
  "detail": "Cannot connect to destination database: Connection refused"
}
```

---

## 🔐 Seguridad

### Validaciones Implementadas

1. **Sesión Ownership**: La sesión DEBE pertenecer al usuario actual
   ```python
   if session.user_id != current_user['id']:
       raise HTTPException(status_code=403, ...)
   ```

2. **Sesión Expirada**: No se permite generar scripts con sesiones vencidas
   ```python
   if session.is_expired():
       raise HTTPException(status_code=410, ...)
   ```

3. **Desconexión Segura**: Los adapters siempre se desconectan en el `finally` block

### Hashing vs Cifrado

| Modo | Técnica | Reversible | Resolución |
|------|---------|-----------|------------|
| **Import** | AES-256-GCM | ✅ Sí | Descifrado directo con clave |
| **Connector** | SHA-256 | ❌ No | Búsqueda exhaustiva comparando hashes |

**IMPORTANTE:** Los hashes SHA-256 son one-way (irreversibles). Solo se pueden resolver consultando la BD real y comparando el hash de cada nombre.

---

## 🚨 Casos de Error y Manejo

### 1. Sesión Expirada Durante Generación

**Problema:** Usuario creó mappings con sesión activa, pero al generar script la sesión ya expiró.

**Solución:**
- Retornar HTTP 410 Gone con mensaje claro
- Usuario debe reconectar a la BD externa
- Frontend puede mostrar botón "Reconectar"

### 2. Tabla Renombrada en BD Externa

**Problema:** Usuario creó mapping con tabla `users`, pero en BD externa fue renombrada a `usuarios`.

**Comportamiento:**
- El hash SHA-256 de `users` ≠ hash de `usuarios`
- `_resolve_hash_from_adapter()` no encuentra match
- Retorna HTTP 404 Not Found con detalle del hash

**Solución para usuario:**
- Eliminar mapping antiguo
- Crear nuevo mapping con nombre actualizado

### 3. BD Externa No Disponible

**Problema:** BD externa apagada o credenciales cambiaron.

**Comportamiento:**
- `adapter.connect()` lanza `DBConnectionError`
- Retorna HTTP 503 Service Unavailable

---

## 📝 Próximos Pasos

### Completado en Esta Implementación
1. ✅ **TAREA 4**: MigrationScriptService creado
2. ✅ **TAREA 5**: Endpoint POST /generate-migration-script implementado
3. ✅ Helper `_create_adapter_from_config()` implementado
4. ✅ Validaciones de sesiones (expiración, ownership)
5. ✅ Resolución de hashes SHA-256
6. ✅ Manejo robusto de errores
7. ✅ Desconexión segura de adapters

### Pendiente (Fuera de Alcance)
8. ⏳ **TAREA 7**: Tests unitarios de hashing ([IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) líneas 669-727)
9. ⏳ **TAREA 8**: Tests de integración modo connector ([IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) líneas 731-762)
10. ⏳ **TAREA 9**: Documentación API ([IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) líneas 766-788)
11. ⏳ Test manual con Postman/curl

---

## 🎯 Arquitectura de la Solución

### Flujo Completo: Usuario → Script SQL

```
┌──────────────┐
│   Usuario    │
│   Frontend   │
└──────┬───────┘
       │ POST /generate-migration-script
       ▼
┌──────────────────────────────────────────────────┐
│  Endpoint (mappings.py)                          │
│  1. Obtiene mappings del proyecto                │
│  2. Identifica sesiones necesarias               │
│  3. Valida sesiones en Redis                     │
│  4. Crea adapters para BDs externas              │
│  5. Genera script con MigrationScriptService     │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│  MigrationScriptService                          │
│  - Itera sobre mappings                          │
│  - Resuelve nombres según modo:                  │
│    • Import: usa nombres descifrados             │
│    • Connector: resuelve hashes SHA-256          │
│  - Genera queries SQL                            │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│  BaseDBAdapter (PostgreSQL/MySQL/etc.)           │
│  - get_tables(): lista todas las tablas          │
│  - get_columns(table): lista columnas de tabla   │
│  - Permite comparación de hashes                 │
└──────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│  Base de Datos Externa (MySQL, PostgreSQL, etc.) │
│  - SOLO lectura de metadata (INFORMATION_SCHEMA) │
│  - NO accede a datos de usuario                  │
└──────────────────────────────────────────────────┘
```

---

## 📚 Referencias

- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) - Plan completo del proyecto (líneas 387-523)
- [TAREA_6_RESUMEN.md](TAREA_6_RESUMEN.md) - Endpoint POST /mappings actualizado
- [backend/app/utils/db_adapters/base_adapter.py](backend/app/utils/db_adapters/base_adapter.py) - Interfaz BaseDBAdapter
- [backend/app/utils/db_adapters/postgres_adapter.py](backend/app/utils/db_adapters/postgres_adapter.py) - Ejemplo de implementación
- [backend/app/services/db_connection_service.py](backend/app/services/db_connection_service.py) - Servicio de sesiones Redis

---

## ⚠️ Notas Importantes

1. **Hashes SHA-256 son irreversibles**:
   - NO se pueden descifrar
   - SOLO se pueden resolver consultando la BD real
   - Si una tabla fue renombrada, el hash no coincidirá

2. **Sesiones tienen TTL**:
   - Default: 3 horas
   - Máximo: 24 horas
   - Después del TTL, el endpoint retornará **410 Gone**

3. **Performance**:
   - Para tablas: O(n) donde n = número de tablas
   - Para columnas: O(n*m) donde n = tablas, m = columnas por tabla
   - Considerar cache LRU en futuras optimizaciones

4. **Compatibilidad con mappings híbridos**:
   - ✅ Origen Import + Destino Import
   - ✅ Origen Import + Destino Connector
   - ✅ Origen Connector + Destino Import
   - ✅ Origen Connector + Destino Connector

5. **ANTES de usar este endpoint**, el usuario DEBE:
   - ✅ Tener mappings creados en el proyecto
   - ✅ Si usa connector: tener sesión activa en Redis
   - ✅ Si usa import: tener encryption_key válida en sesión

---

**Fin del documento**
