# Database Adapters

Sistema de conectores para bases de datos externas con introspección de metadata.

## 🔒 Seguridad

**IMPORTANTE**: Los adapters solo leen **METADATA** (estructura), NO datos de usuario.

- ✅ Queries solo a `information_schema`, `pg_catalog`, `sys` views
- ✅ Usuario de conexión con permisos limitados a metadata
- ❌ NO ejecuta `SELECT * FROM user_tables`
- ❌ NO ejecuta `COUNT(*)` sobre datos

## 📦 Instalación de Dependencias

```bash
# PostgreSQL (ya está instalado)
pip install psycopg2-binary==2.9.10

# MySQL/MariaDB
pip install pymysql==1.1.0

# SQL Server
pip install pyodbc==5.1.0

# Oracle
pip install cx_Oracle==8.3.0
```

## 🎯 Uso Básico

### PostgreSQL

```python
from app.utils.db_adapters import PostgreSQLAdapter

config = {
    'host': 'localhost',
    'port': 5432,
    'database': 'mydb',
    'user': 'datamap_readonly',  # Usuario con permisos limitados
    'password': 'secure_password',
}

# Usar context manager (recomendado)
with PostgreSQLAdapter(config) as adapter:
    # Listar schemas
    schemas = adapter.get_schemas()
    print(f"Schemas: {schemas}")

    # Listar tablas
    tables = adapter.get_tables(schema='public')
    for table in tables:
        print(f"\nTable: {table.name}")

        # Obtener columnas
        columns = adapter.get_columns(table.name, schema='public')
        for col in columns:
            print(f"  - {col.name}: {col.data_type} ({'NULL' if col.is_nullable else 'NOT NULL'})")

        # Obtener primary keys
        pks = adapter.get_primary_keys(table.name, schema='public')
        if pks:
            print(f"  PK: {pks[0].columns}")

        # Obtener foreign keys
        fks = adapter.get_foreign_keys(table.name, schema='public')
        for fk in fks:
            print(f"  FK: {fk.columns} → {fk.get_full_referenced_table()}.{fk.referenced_columns}")

        # Obtener estadísticas (aproximadas)
        stats = adapter.get_table_statistics(table.name, schema='public')
        print(f"  Rows (approx): {stats.row_count}, Size: {stats.size_mb} MB")
```

### Introspección Completa de un Schema

```python
with PostgreSQLAdapter(config) as adapter:
    # Obtener metadata completa de un schema
    schema_metadata = adapter.get_full_schema_metadata(schema='public')

    print(f"Schema: {schema_metadata.name}")
    print(f"Tables: {len(schema_metadata.tables)}")
    print(f"Total columns: {schema_metadata.get_column_count()}")
    print(f"Foreign keys: {len(schema_metadata.foreign_keys)}")
    print(f"Indexes: {len(schema_metadata.indexes)}")

    # Exportar a dict para serialización/API response
    schema_dict = schema_metadata.to_dict()
```

### Comparar Schemas entre Diferentes BDs

```python
# Obtener schema de origen (PostgreSQL)
with PostgreSQLAdapter(source_config) as adapter:
    source_schema = adapter.get_full_schema_metadata()

# Obtener schema de destino (MySQL)
with MySQLAdapter(target_config) as adapter:
    target_schema = adapter.get_full_schema_metadata()

# Comparar (implementar en SchemaIntrospectionService)
differences = compare_schemas(source_schema, target_schema)
```

## 🔐 Crear Usuario Read-Only

### PostgreSQL

```sql
-- Crear usuario específico para DataMap
CREATE USER datamap_readonly WITH PASSWORD 'secure_password_here';

-- REVOCAR todos los permisos por defecto
REVOKE ALL ON DATABASE your_database FROM datamap_readonly;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM datamap_readonly;

-- OTORGAR solo acceso a metadata
GRANT CONNECT ON DATABASE your_database TO datamap_readonly;
GRANT SELECT ON information_schema.tables TO datamap_readonly;
GRANT SELECT ON information_schema.columns TO datamap_readonly;
GRANT SELECT ON information_schema.table_constraints TO datamap_readonly;
GRANT SELECT ON information_schema.key_column_usage TO datamap_readonly;
GRANT SELECT ON information_schema.referential_constraints TO datamap_readonly;
GRANT SELECT ON pg_catalog.pg_indexes TO datamap_readonly;
GRANT SELECT ON pg_catalog.pg_class TO datamap_readonly;
GRANT SELECT ON pg_catalog.pg_namespace TO datamap_readonly;

-- IMPORTANTE: NO otorgar SELECT en tablas de usuario
-- Resultado: Usuario puede ver estructura pero NO datos
```

### MySQL

```sql
CREATE USER 'datamap_readonly'@'%' IDENTIFIED BY 'secure_password_here';
GRANT SELECT ON information_schema.* TO 'datamap_readonly'@'%';
GRANT SHOW DATABASES ON *.* TO 'datamap_readonly'@'%';
FLUSH PRIVILEGES;
```

## 📊 Modelos de Metadata

Todos los modelos son Pydantic BaseModel con validaciones:

- **TableMetadata**: Información de tabla (nombre, schema, tipo, columnas)
- **ColumnMetadata**: Información de columna (nombre, tipo, nullable, PK, FK, default, etc.)
- **PrimaryKeyMetadata**: Primary keys (puede ser compuesta)
- **ForeignKeyMetadata**: Foreign keys con ON DELETE/UPDATE
- **UniqueConstraintMetadata**: Constraints UNIQUE
- **IndexMetadata**: Índices (tipo, unique, parcial, etc.)
- **TableStatistics**: Estadísticas aproximadas (row_count, size_bytes)
- **SchemaMetadata**: Agrupa toda la metadata de un schema
- **DatabaseMetadata**: Agrupa múltiples schemas

### Tipos de Datos Genéricos

Los tipos SQL nativos se mapean a tipos genéricos (independientes del dialecto):

- `DataType.STRING` → VARCHAR, NVARCHAR, CHARACTER VARYING
- `DataType.INTEGER` → INT, INTEGER, NUMBER(10)
- `DataType.DECIMAL` → DECIMAL, NUMERIC, NUMBER
- `DataType.TIMESTAMP` → TIMESTAMP, DATETIME2, TIMESTAMP WITH TIME ZONE
- `DataType.JSON` → JSON, JSONB, NVARCHAR(MAX)
- etc.

Ver `column.py` para la lista completa.

## 🛠️ Type Mappers

Cada dialecto tiene su propio mapper:

- **PostgreSQLTypeMapper**: 40+ tipos soportados
- **MySQLTypeMapper**: 30+ tipos soportados
- **SQLServerTypeMapper**: 25+ tipos soportados
- **OracleTypeMapper**: 20+ tipos soportados

```python
from app.utils.db_adapters.type_mappers import PostgreSQLTypeMapper

# Convertir tipo nativo a genérico
generic_type = PostgreSQLTypeMapper.map_to_generic('VARCHAR')
# Returns: DataType.STRING
```

## 🔍 Validadores de Seguridad

Todos los nombres de tablas/columnas/schemas se validan automáticamente:

```python
from app.utils.db_adapters import validate_table_name

# Válido
validate_table_name('users')  # OK
validate_table_name('user_profiles')  # OK

# Inválido (lanza DBValidationError)
validate_table_name("users'; DROP TABLE users;--")  # SQL injection
validate_table_name('SELECT')  # Reserved keyword
validate_table_name('123table')  # Debe empezar con letra
```

## 🧪 Testing

```bash
# Tests unitarios
pytest backend/test/unit/test_db_adapters.py -v

# Tests de integración (requiere Docker)
docker-compose -f docker-compose.test.yml up -d
pytest backend/test/integration/test_db_connection_flow.py -v
```

## 🔄 Próximos Pasos

1. ✅ PostgreSQLAdapter implementado
2. ⏳ MySQLAdapter
3. ⏳ SQLServerAdapter
4. ⏳ OracleAdapter
5. ⏳ DBConnectionService (gestión de sesiones en Redis)
6. ⏳ API Endpoints
7. ⏳ MigrationGeneratorService (genera scripts DDL/DML)
8. ⏳ SQLTranslatorService (traduce queries entre dialectos)

## 📚 Referencias

- [PLAN_FASE_2_CONEXION_LOCAL.md](../../../docs/PLAN_FASE_2_CONEXION_LOCAL.md)
- [PostgreSQL Information Schema](https://www.postgresql.org/docs/current/information-schema.html)
- [MySQL Information Schema](https://dev.mysql.com/doc/refman/8.0/en/information-schema.html)
- [SQL Server System Views](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-objects-transact-sql)
