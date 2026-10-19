# 🚀 PLAN FASE 2: Sistema de Conexión Local con Bases de Datos

> **Documento histórico.** Lo que dice sobre SSL/TLS está **obsoleto**: `ssl_enabled`, el diccionario `ssl={'ssl': {'ca': ...}}` de MySQL y `TrustServerCertificate=yes` (justificado aquí «para conexiones sin SSL validado») ya no existen. Ahora toda conexión usa TLS con verificación por defecto; ver [`app/utils/db_adapters/README.md`](../app/utils/db_adapters/README.md#-tls-y-verificación-del-certificado).

## 📋 Tabla de Contenidos

1. [Visión General](#visión-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [FASE 1: Conectores de Bases de Datos](#fase-1-conectores-de-bases-de-datos)
4. [FASE 2: Sistema de Sesiones de Conexión](#fase-2-sistema-de-sesiones-de-conexión)
5. [FASE 3: Introspección de Schemas](#fase-3-introspección-de-schemas)
6. [FASE 4: Generador de Scripts de Migración](#fase-4-generador-de-scripts-de-migración)
7. [FASE 5: Traductor de Consultas SQL](#fase-5-traductor-de-consultas-sql)
8. [FASE 6: Testing y Seguridad](#fase-6-testing-y-seguridad)
9. [Roadmap de Implementación](#roadmap-de-implementación)
10. [Consideraciones de Seguridad](#consideraciones-de-seguridad)

---

## Visión General

### Objetivo Principal

Implementar un sistema de **conexión temporal** a bases de datos externas que permita:

1. **NO almacenar schemas/datos** permanentemente en DataMap
2. **Conexiones temporales** con credenciales cifradas en Redis
3. **Resultados en memoria** con TTL automático
4. **Generación de scripts de migración** usando metadatos almacenados
5. **Traducción de consultas SQL** entre dialectos

### 🔒 Seguridad Crítica: Solo Metadata, NO Datos

**IMPORTANTE**: Los conectores de DataMap tienen permisos **ÚNICAMENTE** de lectura de **METADATA** (estructura de BDs).

**DataMap NUNCA accede a datos sensibles del usuario:**

| Permitido ✅ | NO Permitido ❌ |
|--------------|-----------------|
| `SELECT * FROM information_schema.tables` | `SELECT * FROM users` |
| `SHOW TABLES` | `SELECT COUNT(*) FROM orders` |
| `DESCRIBE users` | `SELECT email FROM customers` |
| `SELECT * FROM pg_catalog.pg_indexes` | Cualquier query a tablas de usuario |

**Permisos de usuario DB:**
- ✅ Lectura de `information_schema.*`
- ✅ Lectura de `pg_catalog.*` (PostgreSQL)
- ✅ Lectura de `sys.*` views (SQL Server)
- ❌ **NO** lectura de tablas/datos de usuario

**Row counts son aproximados:**
- Obtenidos de `pg_stat_user_tables` (PostgreSQL)
- Obtenidos de `information_schema.tables` (MySQL)
- **NO** se ejecuta `SELECT COUNT(*) FROM table`

### Diferencia con Nivel 1 (Actual)

| Aspecto | Nivel 1 (Actual) | Nivel 2 (Fase 2) |
|---------|-----------------|-----------------|
| **Storage** | Schemas almacenados en DataMap | Solo conexión temporal |
| **Persistencia** | Datos cifrados en PostgreSQL | Datos en Redis (TTL 3h) |
| **Workflow** | Usuario ingresa manualmente | Usuario conecta su BD directamente |
| **Migración** | Basado en metadatos guardados | Generación desde metadatos + introspección |

### Principios de Diseño

- ✅ **Zero Trust**: Nunca confiar en datos del cliente
- ✅ **Least Privilege**: Permisos SOLO de metadata, NO datos
- ✅ **Metadata Only**: Solo `information_schema` y vistas de sistema
- ✅ **Defense in Depth**: Múltiples capas de seguridad
- ✅ **Fail Secure**: En caso de error, cerrar conexiones
- ✅ **Audit Everything**: Log de todas las conexiones e introspecciones

---

## Arquitectura del Sistema

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │ Connection Form  │  │ Schema Explorer  │                   │
│  └──────────────────┘  └──────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTPS
┌─────────────────────────────▼─────────────────────────────────────┐
│                    BACKEND (FastAPI)                              │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              Middleware Layer                               │ │
│  │  - Rate Limiting (10 req/min)                              │ │
│  │  - Authentication (httpOnly cookies)                        │ │
│  │  - DB Session Validation                                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                    │
│  ┌───────────────────────────▼─────────────────────────────────┐ │
│  │                    Router Layer                             │ │
│  │  /api/db-connections/                                       │ │
│  │    - POST /test-connection                                  │ │
│  │    - POST /connect                                          │ │
│  │    - GET /schemas                                           │ │
│  │    - DELETE /disconnect                                     │ │
│  │  /api/migration-scripts/                                    │ │
│  │    - POST /generate                                         │ │
│  │    - GET /preview                                           │ │
│  │  /api/sql-translator/                                       │ │
│  │    - POST /translate                                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                    │
│  ┌───────────────────────────▼─────────────────────────────────┐ │
│  │                   Service Layer                             │ │
│  │  - DBConnectionService                                      │ │
│  │  - SchemaIntrospectionService                              │ │
│  │  - MigrationGeneratorService                               │ │
│  │  - SQLTranslatorService                                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                    │
│  ┌───────────────────────────▼─────────────────────────────────┐ │
│  │                  DB Adapter Layer                           │ │
│  │  - PostgreSQLAdapter                                        │ │
│  │  - MySQLAdapter                                             │ │
│  │  - SQLServerAdapter                                         │ │
│  │  - OracleAdapter                                            │ │
│  │  (BaseAdapter con interfaz común)                          │ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐    ┌───────▼────────┐    ┌──────▼──────┐
│ Redis Session  │    │   PostgreSQL   │    │ External DB │
│     Cache      │    │   (DataMap)    │    │  (Cliente)  │
│                │    │                │    │             │
│ - Credentials  │    │ - Projects     │    │ - Schemas   │
│ - Query cache  │    │ - Mappings     │    │ - Datos     │
│ - TTL 3h       │    │ - Metadata     │    │             │
└────────────────┘    └────────────────┘    └─────────────┘
```

### Flujo de Datos

```
1. Usuario → Form de conexión (host, port, user, password, database)
   ↓
2. POST /api/db-connections/test-connection
   ↓
3. Backend valida credenciales (sin guardar)
   ↓
4. Si válido → POST /api/db-connections/connect
   ↓
5. Credenciales cifradas con AES-256-GCM → Redis (TTL 3h)
   ↓
6. Retorna connection_session_token al frontend
   ↓
7. Frontend incluye header: X-DB-Connection-Session: {token}
   ↓
8. GET /api/db-connections/schemas?connection_session={token}
   ↓
9. Backend:
   - Recupera credenciales de Redis
   - Descifra credenciales
   - Conecta a BD externa
   - Ejecuta queries de introspección
   - Retorna schemas (NO los guarda)
   - Cierra conexión
   ↓
10. Frontend muestra schemas en tiempo real
```

---

## FASE 1: Conectores de Bases de Datos

### 📦 Dependencias Necesarias

```bash
# PostgreSQL (ya instalado)
psycopg2-binary==2.9.10

# MySQL/MariaDB
pymysql==1.1.0
cryptography>=45.0.5  # Ya instalado (para pymysql con SSL)

# SQL Server
pyodbc==5.1.0  # Requiere Microsoft ODBC Driver 18

# Oracle
cx_Oracle==8.3.0  # Requiere Oracle Instant Client

# Pool de conexiones
DBUtils==3.1.0

# Parsing y traducción SQL
sqlglot==25.34.3
sqlparse==0.5.3
```

### 🎯 Tarea 1.1: Implementar BaseAdapter Abstracto

**Prompt Específica:**

```
Crea un archivo `backend/app/utils/db_adapters/base_adapter.py` que defina:

1. Clase abstracta `BaseDBAdapter` con métodos:
   - `__init__(connection_config: dict)` - Recibe config de conexión
   - `connect()` - Establece conexión
   - `disconnect()` - Cierra conexión
   - `test_connection()` - Valida credenciales sin mantener conexión
   - `get_tables()` - Lista todas las tablas
   - `get_columns(table_name: str)` - Lista columnas de una tabla
   - `get_primary_keys(table_name: str)` - Obtiene PKs
   - `get_foreign_keys(table_name: str)` - Obtiene FKs
   - `get_indexes(table_name: str)` - Obtiene índices
   - `get_table_statistics(table_name: str)` - Obtiene estadísticas (row_count aproximado, size_bytes)

2. Propiedades:
   - `is_connected` (bool)
   - `connection_info` (dict con metadata de conexión)
   - `dialect` (str: 'postgresql', 'mysql', 'sqlserver', 'oracle')

3. Context manager support:
   ```python
   with adapter:
       results = adapter.get_tables()
   # Conexión automáticamente cerrada
   ```

4. Exception handling:
   - `ConnectionError` para errores de conexión
   - `QueryExecutionError` para errores de queries
   - `AuthenticationError` para credenciales inválidas

CONTEXTO:
- El proyecto ya usa psycopg2 para PostgreSQL
- El sistema de cifrado AES-256-GCM está en `backend/app/utils/encryption.py`
- Redis session cache está en `backend/app/utils/redis_session_cache.py`
- Seguir convenciones del proyecto (snake_case, type hints, docstrings)

CONSIDERACIONES DE SEGURIDAD:
- NUNCA loggear passwords o connection strings
- Usar prepared statements para prevenir SQL injection
- Timeout de 30 segundos para conexiones
- Read-only mode por defecto (cuando la BD lo soporte)
```

**Archivo:** `backend/app/utils/db_adapters/base_adapter.py`

**Código Esperado:**

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

class DBConnectionError(Exception):
    """Error de conexión a base de datos"""
    pass

class DBQueryExecutionError(Exception):
    """Error al ejecutar query"""
    pass

class DBAuthenticationError(Exception):
    """Error de autenticación"""
    pass

class BaseDBAdapter(ABC):
    """
    Adapter base para conexiones a bases de datos externas.

    Todos los adapters específicos (PostgreSQL, MySQL, etc.) deben heredar de esta clase.
    """

    def __init__(self, connection_config: Dict[str, Any]):
        """
        Inicializa el adapter con configuración de conexión.

        Args:
            connection_config: Dict con keys:
                - host: str
                - port: int
                - database: str
                - user: str
                - password: str
                - ssl_enabled: bool (opcional)
                - timeout: int (opcional, default 30)
        """
        self.connection_config = connection_config
        self.connection = None
        self._is_connected = False
        self.timeout = connection_config.get('timeout', 30)

    @property
    @abstractmethod
    def dialect(self) -> str:
        """Retorna el dialecto SQL: 'postgresql', 'mysql', 'sqlserver', 'oracle'"""
        pass

    @property
    def is_connected(self) -> bool:
        """Retorna True si hay una conexión activa"""
        return self._is_connected and self.connection is not None

    @property
    def connection_info(self) -> Dict[str, Any]:
        """Retorna metadata de la conexión (sin credenciales sensibles)"""
        return {
            'host': self.connection_config.get('host'),
            'port': self.connection_config.get('port'),
            'database': self.connection_config.get('database'),
            'dialect': self.dialect,
            'is_connected': self.is_connected
        }

    @abstractmethod
    def connect(self) -> None:
        """Establece conexión con la base de datos"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Cierra la conexión con la base de datos"""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Valida credenciales sin mantener conexión abierta.

        Returns:
            True si las credenciales son válidas, False en caso contrario

        Raises:
            DBAuthenticationError: Si las credenciales son inválidas
            DBConnectionError: Si no se puede conectar
        """
        pass

    @abstractmethod
    def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista todas las tablas de la base de datos.

        Args:
            schema: Nombre del schema (opcional, para BDs que lo soportan)

        Returns:
            Lista de dicts con keys: name, schema, type, row_count
        """
        pass

    @abstractmethod
    def get_columns(self, table_name: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista todas las columnas de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema (opcional)

        Returns:
            Lista de dicts con keys: name, data_type, is_nullable, is_primary_key,
            is_foreign_key, default_value, max_length, numeric_precision, numeric_scale
        """
        pass

    @abstractmethod
    def get_primary_keys(self, table_name: str, schema: Optional[str] = None) -> List[str]:
        """
        Obtiene las columnas que son primary key.

        Returns:
            Lista de nombres de columnas
        """
        pass

    @abstractmethod
    def get_foreign_keys(self, table_name: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Obtiene las foreign keys de una tabla.

        Returns:
            Lista de dicts con keys: column_name, referenced_table, referenced_column
        """
        pass

    @abstractmethod
    def get_indexes(self, table_name: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Obtiene los índices de una tabla.

        Returns:
            Lista de dicts con keys: name, columns, is_unique, type
        """
        pass

    @abstractmethod
    def get_table_statistics(self, table_name: str, schema: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene estadísticas de una tabla (solo metadata, NO lee datos).

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema (opcional)

        Returns:
            Dict con keys: row_count (aproximado), size_bytes, last_vacuum, last_analyze

        NOTE: row_count es una aproximación obtenida de pg_stat_user_tables (PostgreSQL)
              o information_schema.tables (MySQL), NO ejecuta COUNT(*) sobre datos reales.
        """
        pass

    def __enter__(self):
        """Context manager: conecta al entrar"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: desconecta al salir"""
        self.disconnect()
        return False

    def _sanitize_for_logging(self, message: str) -> str:
        """Remueve información sensible antes de loggear"""
        # Remover passwords, tokens, etc.
        sensitive_patterns = ['password', 'pwd', 'token', 'secret', 'key']
        # Implementar sanitización
        return message
```

---

### 🔒 PERMISOS MÍNIMOS: Solo Lectura de Metadata (NO Datos)

**PRINCIPIO DE SEGURIDAD:**
Los conectores de DataMap solo necesitan leer **ESTRUCTURA** (metadata) de las bases de datos, **NO DATOS**.

#### PostgreSQL - Usuario Read-Only de Metadata

```sql
-- Crear usuario específico para DataMap
CREATE USER datamap_readonly WITH PASSWORD 'secure_password_here';

-- REVOCAR todos los permisos por defecto
REVOKE ALL ON DATABASE your_database FROM datamap_readonly;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM datamap_readonly;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM datamap_readonly;

-- OTORGAR solo acceso a metadata (information_schema y pg_catalog)
GRANT CONNECT ON DATABASE your_database TO datamap_readonly;

-- Acceso a vistas de sistema (contienen solo metadata)
GRANT SELECT ON information_schema.tables TO datamap_readonly;
GRANT SELECT ON information_schema.columns TO datamap_readonly;
GRANT SELECT ON information_schema.table_constraints TO datamap_readonly;
GRANT SELECT ON information_schema.key_column_usage TO datamap_readonly;
GRANT SELECT ON information_schema.referential_constraints TO datamap_readonly;
GRANT SELECT ON information_schema.constraint_column_usage TO datamap_readonly;

-- Acceso a pg_catalog para índices y estadísticas (metadata solamente)
GRANT SELECT ON pg_catalog.pg_indexes TO datamap_readonly;
GRANT SELECT ON pg_catalog.pg_class TO datamap_readonly;
GRANT SELECT ON pg_catalog.pg_namespace TO datamap_readonly;

-- IMPORTANTE: NO otorgar SELECT en tablas de usuario
-- RESULTADO: Usuario puede ver estructura pero NO puede hacer SELECT * FROM user_tables
```

#### MySQL - Usuario Read-Only de Metadata

```sql
-- Crear usuario
CREATE USER 'datamap_readonly'@'%' IDENTIFIED BY 'secure_password_here';

-- OTORGAR solo acceso a information_schema
GRANT SELECT ON information_schema.* TO 'datamap_readonly'@'%';

-- OTORGAR permisos de SHOW (para metadata)
GRANT SHOW DATABASES ON *.* TO 'datamap_readonly'@'%';

-- IMPORTANTE: NO otorgar SELECT en databases de usuario
-- RESULTADO: Usuario puede hacer SHOW TABLES pero NO SELECT * FROM tables
FLUSH PRIVILEGES;
```

#### SQL Server - Usuario Read-Only de Metadata

```sql
-- Crear login y usuario
CREATE LOGIN datamap_readonly WITH PASSWORD = 'SecurePassword123!';
USE your_database;
CREATE USER datamap_readonly FOR LOGIN datamap_readonly;

-- Otorgar permisos VIEW DEFINITION (ver metadata)
GRANT VIEW DEFINITION TO datamap_readonly;
GRANT VIEW ANY DEFINITION TO datamap_readonly;

-- Acceso a vistas de sistema
GRANT SELECT ON INFORMATION_SCHEMA.TABLES TO datamap_readonly;
GRANT SELECT ON INFORMATION_SCHEMA.COLUMNS TO datamap_readonly;
GRANT SELECT ON INFORMATION_SCHEMA.TABLE_CONSTRAINTS TO datamap_readonly;
GRANT SELECT ON INFORMATION_SCHEMA.KEY_COLUMN_USAGE TO datamap_readonly;
GRANT SELECT ON INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS TO datamap_readonly;

-- Acceso a sys views (metadata)
GRANT SELECT ON sys.tables TO datamap_readonly;
GRANT SELECT ON sys.columns TO datamap_readonly;
GRANT SELECT ON sys.indexes TO datamap_readonly;
GRANT SELECT ON sys.foreign_keys TO datamap_readonly;

-- IMPORTANTE: NO agregar a db_datareader role
-- RESULTADO: Usuario puede ver estructura pero NO datos
```

#### Oracle - Usuario Read-Only de Metadata

```sql
-- Crear usuario
CREATE USER datamap_readonly IDENTIFIED BY secure_password_here;

-- Otorgar permisos de conexión
GRANT CREATE SESSION TO datamap_readonly;

-- Otorgar acceso a vistas de metadata (ALL_* views)
GRANT SELECT ON DBA_TABLES TO datamap_readonly;     -- o ALL_TABLES
GRANT SELECT ON DBA_TAB_COLUMNS TO datamap_readonly; -- o ALL_TAB_COLUMNS
GRANT SELECT ON DBA_CONSTRAINTS TO datamap_readonly; -- o ALL_CONSTRAINTS
GRANT SELECT ON DBA_CONS_COLUMNS TO datamap_readonly;
GRANT SELECT ON DBA_INDEXES TO datamap_readonly;     -- o ALL_INDEXES
GRANT SELECT ON DBA_IND_COLUMNS TO datamap_readonly;

-- IMPORTANTE: NO otorgar SELECT en tablas de usuario
-- RESULTADO: Usuario puede ver estructura pero NO datos
```

#### Verificación de Permisos

**Test en PostgreSQL:**
```sql
-- Como datamap_readonly, esto debe FUNCIONAR:
SELECT * FROM information_schema.tables WHERE table_schema = 'public';
SELECT * FROM information_schema.columns WHERE table_name = 'users';

-- Como datamap_readonly, esto debe FALLAR con "permission denied":
SELECT * FROM users;
SELECT count(*) FROM orders;
```

**Test en MySQL:**
```sql
-- Debe FUNCIONAR:
SHOW TABLES;
DESCRIBE users;
SELECT * FROM information_schema.columns WHERE table_name = 'users';

-- Debe FALLAR:
SELECT * FROM users;
```

---

### 🎯 Tarea 1.2: Implementar PostgreSQLAdapter

**Prompt Específica:**

```
Implementa `backend/app/utils/db_adapters/postgres_adapter.py` que extienda `BaseDBAdapter`.

REQUISITOS:
1. Usar psycopg2 (ya está instalado: psycopg2-binary==2.9.10)
2. Usar RealDictCursor para retornar rows como dicts (ya se usa en el proyecto)
3. Queries de introspección usando information_schema ÚNICAMENTE
4. Soporte para schemas (public por defecto)
5. Timeout de conexión: 30 segundos
6. Connection pooling NO necesario (conexiones temporales)

IMPORTANTE - SOLO METADATA:
El adapter debe conectarse con un usuario que tenga SOLO permisos de lectura en information_schema.
NO debe intentar leer datos de tablas de usuario.

QUERIES DE INTROSPECCIÓN (SOLO METADATA):
- Tablas: SELECT * FROM information_schema.tables WHERE table_schema = %s
- Columnas: SELECT * FROM information_schema.columns WHERE table_name = %s AND table_schema = %s
- Primary Keys: SELECT * FROM information_schema.table_constraints + key_column_usage
- Foreign Keys: SELECT * FROM information_schema.referential_constraints
- Índices: SELECT * FROM pg_indexes WHERE schemaname = %s AND tablename = %s
- Estadísticas: SELECT * FROM pg_stat_user_tables (aproximación de row_count)

VALIDACIONES:
- Validar que table_name no contenga SQL injection (usar regex: ^[a-zA-Z0-9_]+$)
- Usar prepared statements SIEMPRE
- NUNCA ejecutar DDL/DML (solo SELECT)
- Detectar queries peligrosas: DROP, DELETE, UPDATE, INSERT, TRUNCATE

MANEJO DE ERRORES:
- psycopg2.OperationalError → DBConnectionError
- psycopg2.ProgrammingError → DBQueryExecutionError
- psycopg2.errors.InvalidPassword → DBAuthenticationError

CONTEXTO:
- El proyecto ya tiene lógica de conexión a PostgreSQL en `backend/app/database.py`
- Seguir el mismo patrón de manejo de excepciones del proyecto
```

**Archivo:** `backend/app/utils/db_adapters/postgres_adapter.py`

---

### 🎯 Tarea 1.3: Implementar MySQLAdapter

**Prompt Específica:**

```
Implementa `backend/app/utils/db_adapters/mysql_adapter.py` que extienda `BaseDBAdapter`.

NUEVA DEPENDENCIA:
pip install pymysql==1.1.0

CONFIGURACIÓN:
- Usar pymysql con cursor=pymysql.cursors.DictCursor
- Soporte para MySQL 5.7+ y MariaDB 10.3+
- SSL opcional: ssl={'ssl': {'ca': '/path/to/ca.pem'}} si connection_config['ssl_enabled']
- charset='utf8mb4' por defecto
- autocommit=True (solo lectura)

QUERIES DE INTROSPECCIÓN:
- Tablas: SHOW TABLES / SELECT * FROM information_schema.tables WHERE table_schema = %s
- Columnas: DESCRIBE table_name / SELECT * FROM information_schema.columns
- Primary Keys: SHOW KEYS FROM table_name WHERE Key_name = 'PRIMARY'
- Foreign Keys: SELECT * FROM information_schema.key_column_usage WHERE referenced_table_name IS NOT NULL
- Índices: SHOW INDEX FROM table_name

DIFERENCIAS CON POSTGRESQL:
- MySQL no tiene schemas en el mismo sentido (usar databases)
- Usar ` (backticks) para escapar nombres de tablas/columnas
- LIMIT syntax diferente
- Tipos de datos diferentes (VARCHAR vs TEXT, INT vs INTEGER, etc.)

VALIDACIONES:
- Validar database name (^[a-zA-Z0-9_]+$)
- Bloquear comandos peligrosos
- Timeout de conexión: connect_timeout=30

MANEJO DE ERRORES:
- pymysql.err.OperationalError → DBConnectionError
- pymysql.err.ProgrammingError → DBQueryExecutionError
- pymysql.err.InternalError → DBAuthenticationError (código 1045)
```

---

### 🎯 Tarea 1.4: Implementar SQLServerAdapter

**Prompt Específica:**

```
Implementa `backend/app/utils/db_adapters/sqlserver_adapter.py` que extienda `BaseDBAdapter`.

NUEVA DEPENDENCIA:
pip install pyodbc==5.1.0

REQUISITO PREVIO:
Usuario debe instalar Microsoft ODBC Driver 18 for SQL Server:
https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

CONFIGURACIÓN:
- Connection string: Driver={ODBC Driver 18 for SQL Server};Server=host,port;Database=db;UID=user;PWD=password
- Timeout: timeout=30
- TrustServerCertificate=yes (para conexiones sin SSL validado)
- Cursor: as_dict=True para retornar rows como dicts

QUERIES DE INTROSPECCIÓN:
- Tablas: SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_CATALOG = ?
- Columnas: SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?
- Primary Keys: SELECT * FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS + KEY_COLUMN_USAGE WHERE CONSTRAINT_TYPE = 'PRIMARY KEY'
- Foreign Keys: SELECT * FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
- Índices: sp_helpindex 'schema.table_name'

DIFERENCIAS CON POSTGRESQL/MYSQL:
- SQL Server usa schemas (dbo por defecto)
- TOP N en lugar de LIMIT N
- [] para escapar identificadores
- NOLOCK hints para queries de solo lectura
- Tipos de datos: NVARCHAR, BIGINT, DATETIME2, etc.

VALIDACIONES:
- Validar connection string para prevenir injection
- Uso de parametrized queries con ?
- Bloquear xp_ stored procedures (peligrosos)

MANEJO DE ERRORES:
- pyodbc.InterfaceError → DBConnectionError
- pyodbc.ProgrammingError → DBQueryExecutionError
- pyodbc.Error con código 18456 → DBAuthenticationError
```

---

### 🎯 Tarea 1.5: Implementar OracleAdapter

**Prompt Específica:**

```
Implementa `backend/app/utils/db_adapters/oracle_adapter.py` que extienda `BaseDBAdapter`.

NUEVA DEPENDENCIA:
pip install cx_Oracle==8.3.0

REQUISITO PREVIO:
Usuario debe instalar Oracle Instant Client:
https://www.oracle.com/database/technologies/instant-client/downloads.html

CONFIGURACIÓN:
- DSN: cx_Oracle.makedsn(host, port, service_name=database)
- Connection: cx_Oracle.connect(user, password, dsn, encoding='UTF-8')
- Timeout: No soportado directamente, usar SQL*Net timeout en tnsnames.ora

QUERIES DE INTROSPECCIÓN:
- Tablas: SELECT * FROM all_tables WHERE owner = :owner
- Columnas: SELECT * FROM all_tab_columns WHERE table_name = :table_name AND owner = :owner
- Primary Keys: SELECT * FROM all_constraints WHERE constraint_type = 'P'
- Foreign Keys: SELECT * FROM all_constraints WHERE constraint_type = 'R'
- Índices: SELECT * FROM all_indexes WHERE table_name = :table_name

DIFERENCIAS CON OTROS DIALECTOS:
- Oracle usa SCHEMAS=USERS
- Identificadores en mayúsculas por defecto
- ROWNUM en lugar de LIMIT
- :param para bind variables
- Tipos de datos: VARCHAR2, NUMBER, DATE, TIMESTAMP, CLOB, etc.
- Sequences para auto-increment

VALIDACIONES:
- Validar owner/schema name
- Usar bind variables SIEMPRE
- Prevenir PL/SQL injection

MANEJO DE ERRORES:
- cx_Oracle.DatabaseError → DBConnectionError
- cx_Oracle.InterfaceError → DBConnectionError
- ORA-01017 (invalid username/password) → DBAuthenticationError
```

---

### 🎯 Tarea 1.6: Implementar DBConnectionService

**Prompt Específica:**

```
Crea `backend/app/services/db_connection_service.py` que:

1. GESTIÓN DE CONEXIONES:
   - `test_connection(db_type: str, config: dict) -> bool`
   - `create_connection_session(project_id: str, user_id: str, db_type: str, config: dict) -> str`
   - `get_adapter(connection_session_token: str) -> BaseDBAdapter`
   - `close_connection(connection_session_token: str) -> None`
   - `list_user_connections(user_id: str) -> List[dict]`

2. ALMACENAMIENTO TEMPORAL EN REDIS:
   - Key pattern: `db_connection:{project_id}:{user_id}`
   - Value: JSON cifrado con AES-256-GCM
   ```json
   {
     "db_type": "postgresql",
     "host": "localhost",
     "port": 5432,
     "database": "mydb",
     "user": "myuser",
     "password_encrypted": "...",
     "password_nonce": "...",
     "ssl_enabled": false,
     "created_at": "2025-01-24T10:30:00Z",
     "expires_at": "2025-01-24T13:30:00Z"
   }
   ```
   - TTL: 3 horas (10800 segundos) - configurable via ENCRYPTION_SESSION_TIMEOUT

3. CIFRADO DE CREDENCIALES:
   - Reutilizar `EncryptionManager` de `backend/app/utils/encryption.py`
   - Derivar encryption_key con Argon2id desde project master key
   - Cifrar solo el password (host, user, database NO son tan sensibles)
   - Guardar nonce junto al password cifrado

4. VALIDACIONES:
   - Validar que el usuario tenga permisos en el proyecto
   - Validar que no exceda límite de conexiones simultáneas (5 por usuario)
   - Rate limiting: 10 intentos de conexión por hora
   - Validar formato de connection config (Pydantic schemas)

5. LOGGING:
   - Log todos los intentos de conexión en security_logs
   - Log eventos: connection_created, connection_failed, connection_closed
   - NUNCA loggear passwords

CONTEXTO:
- Reutilizar `RedisSessionCache` de `backend/app/utils/redis_session_cache.py`
- Seguir patrón de `EncryptionService` en `backend/app/services/encryption_service.py`
- Integrar con sistema de permisos existente

CONSIDERACIONES DE SEGURIDAD:
- NUNCA retornar password en responses
- Validar ownership del proyecto antes de crear conexión
- Invalidar sesiones al logout del usuario
- Cleanup automático de conexiones expiradas
```

---

### 🎯 Tarea 1.7: Implementar API Endpoints de Conexión

**Prompt Específica:**

```
Crea `backend/app/routers/database_connections.py` con endpoints:

1. POST /api/db-connections/test
   - Body: {db_type, host, port, database, user, password, ssl_enabled}
   - Valida credenciales SIN crear sesión
   - Rate limit: 5 requests/min por usuario
   - Response: {valid: bool, message: str, connection_time_ms: int}

2. POST /api/db-connections/connect
   - Body: {project_id, db_type, host, port, database, user, password, ssl_enabled, label}
   - Crea sesión de conexión en Redis
   - Retorna connection_session_token
   - Rate limit: 10 requests/hour por usuario
   - Response: {connection_session_token: str, expires_at: str}

3. GET /api/db-connections
   - Query: ?project_id={uuid}
   - Lista conexiones activas del usuario en ese proyecto
   - Response: [{connection_id, label, db_type, host, database, created_at, expires_at}]

4. DELETE /api/db-connections/{connection_session_token}
   - Cierra conexión y elimina de Redis
   - Response: {success: bool}

5. POST /api/db-connections/refresh
   - Body: {connection_session_token}
   - Extiende TTL de la sesión (3h más)
   - Response: {expires_at: str}

VALIDACIONES:
- Dependency: `current_user = Depends(get_current_user)`
- Validar ownership/membership del proyecto
- Sanitizar connection strings antes de loggear
- Pydantic schemas para request/response

SCHEMAS PYDANTIC:
```python
class DBConnectionConfig(BaseModel):
    db_type: Literal['postgresql', 'mysql', 'sqlserver', 'oracle']
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., gt=0, lt=65536)
    database: str = Field(..., min_length=1, max_length=128)
    user: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1)
    ssl_enabled: bool = False
    label: Optional[str] = Field(None, max_length=100)

class ConnectionTestResponse(BaseModel):
    valid: bool
    message: str
    connection_time_ms: int
```

CONTEXTO:
- Reutilizar patrón de `backend/app/routers/encryption.py`
- Usar `DBConnectionService` para lógica de negocio
- Rate limiting con `slowapi` (ya está en el proyecto)
```

---

## FASE 2: Sistema de Sesiones de Conexión

### 🎯 Tarea 2.1: Extender RedisSessionCache para Conexiones DB

**Prompt Específica:**

```
Modifica `backend/app/utils/redis_session_cache.py` para agregar:

1. NUEVOS MÉTODOS ESPECÍFICOS PARA DB CONNECTIONS:
   ```python
   def create_db_connection_session(
       self,
       project_id: str,
       user_id: str,
       connection_data: dict,
       ttl_seconds: int = 10800
   ) -> str:
       """Crea sesión de conexión a BD externa"""
       pass

   def get_db_connection_session(
       self,
       connection_token: str
   ) -> Optional[dict]:
       """Recupera datos de conexión desde Redis"""
       pass

   def list_user_db_connections(
       self,
       user_id: str
   ) -> List[dict]:
       """Lista todas las conexiones activas de un usuario"""
       pass

   def refresh_db_connection_ttl(
       self,
       connection_token: str,
       ttl_seconds: int = 10800
   ) -> bool:
       """Extiende TTL de una conexión"""
       pass
   ```

2. KEY PATTERNS:
   - Conexión específica: `db_conn:{token}`
   - Índice por usuario: `db_conn_user:{user_id}` (SET con tokens)
   - Índice por proyecto: `db_conn_project:{project_id}` (SET con tokens)

3. ESTRUCTURA DE DATOS:
   ```json
   {
     "project_id": "uuid",
     "user_id": "uuid",
     "db_type": "postgresql",
     "config_encrypted": "base64...",
     "config_nonce": "base64...",
     "label": "Production DB",
     "created_at": "ISO8601",
     "last_used_at": "ISO8601",
     "use_count": 42
   }
   ```

4. CLEANUP AUTOMÁTICO:
   - Usar Redis KEY EXPIRATION para TTL automático
   - Al expirar una key, Redis automáticamente la elimina
   - Background task para limpiar índices huérfanos (cada 1 hora)

CONTEXTO:
- Ya existe `RedisSessionCache` con métodos de sesiones de cifrado
- Mantener compatibilidad con código existente
- Usar el mismo connection pool de Redis
```

---

### 🎯 Tarea 2.2: Implementar Middleware de DB Session

**Prompt Específica:**

```
Crea `backend/app/middleware/db_connection_session.py` que:

1. INTERCEPTAR REQUESTS CON HEADER:
   - `X-DB-Connection-Session: {connection_token}`
   - Validar que el token existe en Redis
   - Validar que el user_id del token coincide con current_user
   - Inyectar datos de conexión en `request.state.db_connection`

2. ACTUALIZAR LAST_USED_AT:
   - Cada vez que se usa el token, actualizar timestamp
   - Incrementar use_count

3. MANEJO DE ERRORES:
   - Token inválido → 401 Unauthorized
   - Token expirado → 401 Unauthorized + sugerencia de reconectar
   - User ID mismatch → 403 Forbidden

4. LOGGING:
   - Log cada uso de conexión (con rate limiting para no saturar logs)
   - Log solo: timestamp, user_id, project_id, db_type, action

PATRÓN DE USO EN ENDPOINTS:
```python
@router.get("/api/db-connections/schemas")
async def get_schemas(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    # Middleware ya validó el token
    db_connection = request.state.db_connection

    # Recuperar adapter
    adapter = DBConnectionService.get_adapter(db_connection)

    with adapter:
        schemas = adapter.get_tables()

    return schemas
```

CONTEXTO:
- Seguir patrón de `EncryptionSessionMiddleware` en `backend/app/middleware/encryption_session.py`
- Integrar con sistema de autenticación existente
```

---

### 🎯 Tarea 2.3: Implementar Connection Pooling (Opcional)

**Prompt Específica:**

```
DECISIÓN: ¿Necesitamos connection pooling para conexiones temporales?

ANÁLISIS:
- PRO: Reduce latencia al reutilizar conexiones
- CON: Mayor complejidad, mayor uso de memoria
- CON: Las conexiones son temporales (3h max)

RECOMENDACIÓN:
- NO implementar pooling inicialmente
- Cada request abre/cierra su propia conexión
- Medir performance antes de optimizar

SI EVENTUALMENTE SE NECESITA POOLING:
- Usar DBUtils==3.1.0 (ya en requirements)
- Pool size: 2-5 conexiones por usuario
- Max idle time: 10 minutos
- Total max connections: 50 (límite del servidor)

```python
from DBUtils.PooledDB import PooledDB

class ConnectionPoolManager:
    def __init__(self):
        self.pools = {}  # {connection_token: PooledDB}

    def get_or_create_pool(self, connection_token: str, adapter_class, config):
        if connection_token not in self.pools:
            self.pools[connection_token] = PooledDB(
                creator=adapter_class,
                maxconnections=5,
                mincached=1,
                maxcached=3,
                blocking=True,
                **config
            )
        return self.pools[connection_token]
```

DECISIÓN FINAL: Implementar SOLO si profiling muestra que es necesario.
```

---

## FASE 3: Introspección de Schemas

### 🎯 Tarea 3.1: Implementar SchemaIntrospectionService

**Prompt Específica:**

```
Crea `backend/app/services/schema_introspection_service.py` que:

1. MÉTODOS PRINCIPALES:
   ```python
   @staticmethod
   def introspect_full_schema(
       adapter: BaseDBAdapter,
       schema_name: Optional[str] = None
   ) -> dict:
       """
       Retorna estructura completa de la BD:
       {
         "tables": [...],
         "relationships": [...],
         "statistics": {...}
       }
       """
       pass

   @staticmethod
   def introspect_table(
       adapter: BaseDBAdapter,
       table_name: str,
       schema_name: Optional[str] = None
   ) -> dict:
       """
       Retorna metadata detallada de una tabla:
       {
         "name": "users",
         "schema": "public",
         "columns": [...],
         "primary_keys": [...],
         "foreign_keys": [...],
         "indexes": [...],
         "row_count": 1000,
         "size_mb": 2.5
       }
       """
       pass

   @staticmethod
   def compare_schemas(
       source_schema: dict,
       target_schema: dict
   ) -> dict:
       """
       Compara dos schemas y retorna diferencias:
       {
         "missing_tables": [...],
         "missing_columns": [...],
         "type_mismatches": [...],
         "constraint_differences": [...]
       }
       """
       pass
   ```

2. CACHE DE RESULTADOS EN REDIS:
   - Key: `schema_cache:{connection_token}:{table_name}`
   - TTL: 30 minutos (los schemas no cambian tan rápido)
   - Invalidar cache al cerrar conexión

3. FORMATO DE SALIDA UNIFICADO:
   - Independiente del dialecto SQL
   - Usar tipos de datos estándar (string, integer, decimal, boolean, datetime, text, binary)
   - Mapear tipos específicos a tipos genéricos

4. MANEJO DE ERRORES:
   - Timeout de introspección: 60 segundos
   - Si falla una tabla, continuar con las demás
   - Retornar errores en campo "errors" del resultado

CONTEXTO:
- Los adapters ya tienen métodos get_tables(), get_columns(), etc.
- Este servicio orquesta llamadas a múltiples métodos del adapter
- Los resultados NO se guardan en DataMap (solo en Redis temporalmente)
```

---

### 🎯 Tarea 3.2: Implementar Endpoints de Introspección

**Prompt Específica:**

```
Agrega a `backend/app/routers/database_connections.py`:

1. GET /api/db-connections/schemas
   - Header: X-DB-Connection-Session
   - Query: ?schema={name}&include_stats=true
   - Retorna lista de schemas disponibles
   - Response: [{name, table_count, total_size_mb}]

2. GET /api/db-connections/tables
   - Header: X-DB-Connection-Session
   - Query: ?schema={name}
   - Retorna lista de tablas con metadata básica
   - Response: [{name, schema, type, row_count, columns_count}]

3. GET /api/db-connections/tables/{table_name}
   - Header: X-DB-Connection-Session
   - Query: ?schema={name}&include_relationships=true
   - Retorna metadata completa de una tabla
   - Response: {name, columns, primary_keys, foreign_keys, indexes, statistics}

4. POST /api/db-connections/introspect-full
   - Header: X-DB-Connection-Session
   - Body: {schema_name, include_stats, include_relationships}
   - Introspección completa de la BD
   - IMPORTANTE: Puede tardar varios minutos en BDs grandes
   - Usar background task si tarda más de 30 segundos
   - Response: {task_id} o {schema_data} (si es rápido)

VALIDACIONES:
- Rate limit: 30 requests/min para introspección
- Timeout: 60 segundos para queries de introspección
- Validar que table_name no tenga SQL injection

CACHE:
- Cache resultados de introspección en Redis (30 min)
- Header `X-Cache: HIT|MISS` en response
```

---

### 🎯 Tarea 3.3: Implementar Comparador de Schemas

**Prompt Específica:**

```
Implementa lógica de comparación entre schemas en `SchemaIntrospectionService.compare_schemas()`.

CASOS DE USO:
1. Comparar BD origen vs BD destino (para migración)
2. Comparar schema actual vs snapshot anterior (para detectar cambios)
3. Comparar diferentes dialectos SQL (PostgreSQL vs MySQL)

TIPOS DE DIFERENCIAS A DETECTAR:

1. TABLAS:
   - Tablas faltantes en target
   - Tablas extras en target
   - Diferencias en row_count

2. COLUMNAS:
   - Columnas faltantes
   - Columnas extras
   - Orden diferente (warning, no error)
   - Diferencias en nullable
   - Diferencias en default value

3. TIPOS DE DATOS:
   - Incompatibilidad total (string vs integer)
   - Diferencias de precisión (VARCHAR(50) vs VARCHAR(100))
   - Diferencias de escala (DECIMAL(10,2) vs DECIMAL(10,4))

4. CONSTRAINTS:
   - Primary keys diferentes
   - Foreign keys faltantes
   - Unique constraints diferentes
   - Check constraints diferentes

5. ÍNDICES:
   - Índices faltantes
   - Índices con columnas diferentes

FORMATO DE OUTPUT:
```json
{
  "summary": {
    "total_differences": 15,
    "severity_breakdown": {
      "critical": 2,
      "warning": 8,
      "info": 5
    },
    "compatibility_score": 85
  },
  "differences": [
    {
      "type": "missing_table",
      "severity": "critical",
      "source_table": "users",
      "target_table": null,
      "description": "Table 'users' exists in source but not in target",
      "suggestion": "CREATE TABLE users (...)"
    },
    {
      "type": "column_type_mismatch",
      "severity": "warning",
      "source": {"table": "orders", "column": "total", "type": "DECIMAL(10,2)"},
      "target": {"table": "orders", "column": "total", "type": "DECIMAL(12,2)"},
      "description": "Column 'total' has different precision",
      "suggestion": "ALTER TABLE orders ALTER COLUMN total TYPE DECIMAL(10,2)"
    }
  ]
}
```

SEVERITY LEVELS:
- CRITICAL: Impide migración (tabla/columna faltante, tipo incompatible)
- WARNING: Puede causar problemas (precisión diferente, índices faltantes)
- INFO: Diferencias menores (orden de columnas, comentarios)

ENDPOINT:
POST /api/db-connections/compare
Body: {
  source_connection_token: str,
  target_connection_token: str,
  source_schema: Optional[str],
  target_schema: Optional[str]
}
Response: ComparisonResult
```

---

## FASE 4: Generador de Scripts de Migración

### 🎯 Tarea 4.1: Implementar MigrationGeneratorService

**Prompt Específica:**

```
Crea `backend/app/services/migration_generator_service.py` que genere scripts DDL para migración.

OBJETIVO:
Usar los METADATOS almacenados en DataMap (tablas, columnas, mappings) para generar scripts SQL que creen el schema de destino.

FLUJO:
1. Usuario ya mapeó schemas en DataMap (Nivel 1 - actual)
2. Tiene project con:
   - Tablas origin y destination
   - Columnas con tipos de datos
   - Mappings entre columnas
3. Usuario pide generar script de migración
4. Sistema genera DDL para crear schema destination en la BD destino

MÉTODOS PRINCIPALES:
```python
@staticmethod
def generate_ddl_script(
    db: Connection,
    project_id: str,
    target_dialect: str,
    encryption_key: Optional[bytes] = None,
    options: dict = {}
) -> str:
    """
    Genera script DDL completo para crear schema de destino.

    Args:
        db: Conexión a DataMap (PostgreSQL)
        project_id: ID del proyecto
        target_dialect: 'postgresql', 'mysql', 'sqlserver', 'oracle'
        encryption_key: Si el proyecto tiene cifrado
        options: {
            include_drop: bool (default False),
            include_comments: bool (default True),
            include_indexes: bool (default True),
            transaction_wrap: bool (default True)
        }

    Returns:
        Script SQL completo como string
    """
    pass

@staticmethod
def generate_table_ddl(
    table: dict,
    columns: List[dict],
    target_dialect: str
) -> str:
    """Genera DDL para una sola tabla"""
    pass

@staticmethod
def generate_data_migration_script(
    db: Connection,
    project_id: str,
    source_connection_token: str,
    target_connection_token: str,
    encryption_key: Optional[bytes] = None
) -> str:
    """
    Genera script para copiar datos de origen a destino.
    Usa los mappings definidos en DataMap.
    """
    pass
```

ESTRUCTURA DEL SCRIPT GENERADO:

```sql
-- ============================================================================
-- Migration Script
-- Generated by DataMap
-- Project: {project_name}
-- Target Database: {target_dialect}
-- Generated at: {timestamp}
-- ============================================================================

-- IMPORTANT: Review this script before executing!
-- Backup your database before running this migration.

BEGIN TRANSACTION;

-- ============================================================================
-- 1. DROP EXISTING OBJECTS (if include_drop=true)
-- ============================================================================

DROP TABLE IF EXISTS destination_table_1 CASCADE;
DROP TABLE IF EXISTS destination_table_2 CASCADE;

-- ============================================================================
-- 2. CREATE TABLES
-- ============================================================================

CREATE TABLE destination_table_1 (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE destination_table_1 IS 'Users table';
COMMENT ON COLUMN destination_table_1.email IS 'User email address';

-- ============================================================================
-- 3. CREATE INDEXES
-- ============================================================================

CREATE INDEX idx_destination_table_1_email ON destination_table_1(email);
CREATE INDEX idx_destination_table_1_created_at ON destination_table_1(created_at);

-- ============================================================================
-- 4. CREATE FOREIGN KEYS
-- ============================================================================

ALTER TABLE orders ADD CONSTRAINT fk_orders_user_id
    FOREIGN KEY (user_id) REFERENCES destination_table_1(id)
    ON DELETE CASCADE ON UPDATE CASCADE;

COMMIT;

-- ============================================================================
-- Migration completed successfully!
-- ============================================================================
```

MAPEO DE TIPOS DE DATOS ENTRE DIALECTOS:

```python
TYPE_MAPPING = {
    'postgresql': {
        'string': 'VARCHAR({length})',
        'text': 'TEXT',
        'integer': 'INTEGER',
        'bigint': 'BIGINT',
        'decimal': 'DECIMAL({precision},{scale})',
        'boolean': 'BOOLEAN',
        'datetime': 'TIMESTAMP',
        'date': 'DATE',
        'time': 'TIME',
        'binary': 'BYTEA',
        'json': 'JSONB',
        'uuid': 'UUID'
    },
    'mysql': {
        'string': 'VARCHAR({length})',
        'text': 'TEXT',
        'integer': 'INT',
        'bigint': 'BIGINT',
        'decimal': 'DECIMAL({precision},{scale})',
        'boolean': 'TINYINT(1)',
        'datetime': 'DATETIME',
        'date': 'DATE',
        'time': 'TIME',
        'binary': 'BLOB',
        'json': 'JSON',
        'uuid': 'CHAR(36)'
    },
    'sqlserver': {
        'string': 'NVARCHAR({length})',
        'text': 'NVARCHAR(MAX)',
        'integer': 'INT',
        'bigint': 'BIGINT',
        'decimal': 'DECIMAL({precision},{scale})',
        'boolean': 'BIT',
        'datetime': 'DATETIME2',
        'date': 'DATE',
        'time': 'TIME',
        'binary': 'VARBINARY(MAX)',
        'json': 'NVARCHAR(MAX)',
        'uuid': 'UNIQUEIDENTIFIER'
    },
    'oracle': {
        'string': 'VARCHAR2({length})',
        'text': 'CLOB',
        'integer': 'NUMBER(10)',
        'bigint': 'NUMBER(19)',
        'decimal': 'NUMBER({precision},{scale})',
        'boolean': 'NUMBER(1)',
        'datetime': 'TIMESTAMP',
        'date': 'DATE',
        'time': 'TIMESTAMP',
        'binary': 'BLOB',
        'json': 'CLOB',
        'uuid': 'VARCHAR2(36)'
    }
}
```

CONTEXTO:
- Leer tablas y columnas de DataMap usando schemas_crud.py
- Si el proyecto tiene cifrado, descifrar nombres
- Validar que las tablas destination estén completas
```

---

### 🎯 Tarea 4.2: Implementar Generador de Scripts de Datos (DML)

**Prompt Específica:**

```
Implementa generación de scripts INSERT para copiar datos de origen a destino.

RETOS:
1. Las columnas de origen y destino pueden tener nombres diferentes
2. Los tipos de datos pueden requerir transformación
3. Pueden haber transformation_logic personalizadas en mappings
4. Datasets grandes requieren batch processing

ESTRATEGIA:
```python
@staticmethod
def generate_data_migration_script(
    db: Connection,
    project_id: str,
    source_connection_token: str,
    target_connection_token: str,
    encryption_key: Optional[bytes] = None,
    options: dict = {}
) -> str:
    """
    Genera script para copiar datos usando mappings.

    options: {
        batch_size: int (default 1000),
        include_validation: bool (default True),
        handle_conflicts: 'ignore' | 'update' | 'error' (default 'error')
    }
    """

    # 1. Obtener mappings del proyecto
    mappings = get_project_mappings(db, project_id, encryption_key)

    # 2. Agrupar mappings por tabla
    tables_to_migrate = group_mappings_by_table(mappings)

    # 3. Para cada tabla, generar INSERTs
    script_parts = []

    for dest_table, column_mappings in tables_to_migrate.items():
        # 3.1. Obtener adapter de origen
        source_adapter = DBConnectionService.get_adapter(source_connection_token)

        # 3.2. Construir SELECT de origen
        origin_columns = [m['origin_column'] for m in column_mappings]
        select_query = f"SELECT {', '.join(origin_columns)} FROM {origin_table}"

        # 3.3. Obtener datos (con batching)
        with source_adapter:
            data_iterator = source_adapter.execute_query_batched(
                select_query,
                batch_size=options.get('batch_size', 1000)
            )

            # 3.4. Para cada batch, generar INSERTs
            for batch in data_iterator:
                insert_statements = generate_insert_batch(
                    dest_table,
                    column_mappings,
                    batch,
                    target_dialect
                )
                script_parts.append(insert_statements)

    return '\n'.join(script_parts)
```

TRANSFORMACIONES DE DATOS:

```python
def apply_transformation(value: Any, transformation_logic: str, source_type: str, target_type: str):
    """
    Aplica transformation_logic a un valor.

    transformation_logic puede ser:
    - 'direct': Copia directa (default)
    - 'uppercase': value.upper()
    - 'lowercase': value.lower()
    - 'trim': value.strip()
    - 'concat:prefix:suffix': f'{prefix}{value}{suffix}'
    - 'default:value': value or 'default_value'
    - SQL expression: CAST(value AS INTEGER)
    """

    if transformation_logic == 'direct' or not transformation_logic:
        return convert_type(value, source_type, target_type)

    # Implementar transformaciones comunes
    # ...
```

SCRIPT GENERADO (EJEMPLO):

```sql
-- Data Migration Script
-- Source: PostgreSQL (production_db)
-- Target: MySQL (analytics_db)

START TRANSACTION;

-- Migrate table: users → customers
-- Mappings: 3 columns
INSERT INTO customers (customer_id, full_name, email_address)
VALUES
    (1, 'John Doe', 'john@example.com'),
    (2, 'Jane Smith', 'jane@example.com'),
    (3, 'Bob Johnson', 'bob@example.com')
-- ... (batch of 1000 rows)
;

-- Validation query (run after migration):
-- SELECT COUNT(*) FROM customers; -- Expected: 1000

COMMIT;
```

IMPORTANTE:
- Para datasets grandes (>100k rows), NO generar script completo
- En su lugar, generar script de Python/procedimiento almacenado
- O usar herramientas nativas (pg_dump, mysqldump, bcp)

ENDPOINT:
POST /api/migration-scripts/generate-data
Body: {
  project_id: str,
  source_connection_token: str,
  target_connection_token: str,
  tables: Optional[List[str]],  // null = todas
  options: {
    batch_size: 1000,
    include_validation: true,
    format: 'sql' | 'python_script' | 'native_tool'
  }
}
```

---

### 🎯 Tarea 4.3: Implementar Endpoints de Generación de Scripts

**Prompt Específica:**

```
Crea `backend/app/routers/migration_scripts.py` con endpoints:

1. POST /api/migration-scripts/generate-ddl
   - Body: {project_id, target_dialect, options}
   - Genera script DDL para crear schema
   - Response: {script: str, tables_count: int, estimated_size_kb: int}

2. POST /api/migration-scripts/generate-dml
   - Body: {project_id, source_connection_token, target_connection_token, tables, options}
   - Genera script de migración de datos
   - Response: {script: str, rows_count: int, estimated_time_minutes: int}

3. POST /api/migration-scripts/generate-full
   - Body: {project_id, source_connection_token, target_connection_token, target_dialect, options}
   - Genera script completo (DDL + DML)
   - IMPORTANTE: Operación pesada, usar background task
   - Response: {task_id: str} → Consultar progreso con GET /api/tasks/{task_id}

4. POST /api/migration-scripts/validate
   - Body: {script: str, dialect: str}
   - Valida sintaxis SQL (sin ejecutar)
   - Response: {valid: bool, errors: List[str]}

5. GET /api/migration-scripts/{script_id}
   - Recupera script generado previamente (almacenado temporalmente)
   - Response: {script: str, created_at: str, metadata: dict}

CONSIDERACIONES:
- Scripts DDL: Generar inmediatamente (< 1 segundo)
- Scripts DML: Background task si >10k rows
- Almacenar scripts generados en Redis (TTL 24h)
- Límite de tamaño de script: 10 MB

BACKGROUND TASKS:
```python
from fastapi import BackgroundTasks

@router.post("/api/migration-scripts/generate-full")
async def generate_full_migration_script(
    request: GenerateFullScriptRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Crear task ID
    task_id = str(uuid.uuid4())

    # Inicializar progreso en Redis
    redis_cache.set(f"task:{task_id}", {
        "status": "pending",
        "progress": 0,
        "created_at": datetime.utcnow().isoformat()
    }, ttl=86400)

    # Ejecutar en background
    background_tasks.add_task(
        generate_script_background,
        task_id,
        request,
        current_user['id']
    )

    return {"task_id": task_id, "status": "pending"}

def generate_script_background(task_id: str, request: dict, user_id: str):
    try:
        # Actualizar progreso: 0% - 10%
        update_task_progress(task_id, 10, "Generating DDL...")
        ddl_script = MigrationGeneratorService.generate_ddl_script(...)

        # Actualizar progreso: 10% - 90%
        update_task_progress(task_id, 50, "Generating DML...")
        dml_script = MigrationGeneratorService.generate_data_migration_script(...)

        # Combinar scripts
        update_task_progress(task_id, 95, "Finalizing...")
        full_script = f"{ddl_script}\n\n{dml_script}"

        # Guardar resultado
        script_id = str(uuid.uuid4())
        redis_cache.set(f"script:{script_id}", full_script, ttl=86400)

        # Completar task
        update_task_progress(task_id, 100, "Completed", {
            "script_id": script_id,
            "size_bytes": len(full_script)
        })

    except Exception as e:
        update_task_progress(task_id, -1, f"Error: {str(e)}")
```

ENDPOINT PARA CONSULTAR PROGRESO:
GET /api/tasks/{task_id}
Response: {
  status: 'pending' | 'running' | 'completed' | 'error',
  progress: 0-100,
  message: str,
  result: Optional[dict]
}
```

---

## FASE 5: Traductor de Consultas SQL

### 🎯 Tarea 5.1: Instalar y Configurar SQLGlot

**Prompt Específica:**

```
Instala sqlglot para traducción de consultas SQL entre dialectos.

INSTALACIÓN:
pip install sqlglot==25.34.3

CAPACIDADES DE SQLGLOT:
- Parse SQL queries de múltiples dialectos
- Transpile (traducir) queries entre dialectos
- Validar sintaxis SQL
- Optimizar queries

EJEMPLO DE USO:
```python
import sqlglot

# Parse query de PostgreSQL
parsed = sqlglot.parse_one("SELECT * FROM users WHERE id = 1", read="postgres")

# Transpile a MySQL
mysql_query = parsed.sql(dialect="mysql")
# Output: SELECT * FROM users WHERE id = 1

# Ejemplo más complejo
pg_query = """
SELECT
    u.id,
    u.name,
    COUNT(*) OVER (PARTITION BY u.department) as dept_count,
    NOW() as current_time
FROM users u
WHERE u.created_at > NOW() - INTERVAL '30 days'
LIMIT 10
"""

# Transpile a SQL Server
sqlserver_query = sqlglot.transpile(pg_query, read="postgres", write="tsql")[0]
# Output: SELECT ... WHERE u.created_at > DATEADD(day, -30, GETDATE()) ...
```

DIALECTOS SOPORTADOS:
- postgres, postgresql
- mysql, mariadb
- tsql (SQL Server)
- oracle
- sqlite
- redshift, snowflake, bigquery, etc.

LIMITACIONES:
- No soporta todas las funciones específicas de cada dialecto
- Puede requerir ajustes manuales para queries muy complejas
- NO traduce stored procedures ni funciones UDF

DOCUMENTACIÓN:
https://github.com/tobymao/sqlglot
```

---

### 🎯 Tarea 5.2: Implementar SQLTranslatorService

**Prompt Específica:**

```
Crea `backend/app/services/sql_translator_service.py` que:

1. TRADUCIR QUERIES SIMPLES:
```python
@staticmethod
def translate_query(
    query: str,
    source_dialect: str,
    target_dialect: str
) -> dict:
    """
    Traduce una query SQL de un dialecto a otro.

    Returns:
        {
            "translated_query": str,
            "warnings": List[str],
            "unsupported_features": List[str]
        }
    """
    try:
        # Parse query
        parsed = sqlglot.parse_one(query, read=source_dialect)

        # Transpile
        translated = parsed.sql(dialect=target_dialect, pretty=True)

        # Detectar features no soportadas
        warnings = detect_unsupported_features(parsed, target_dialect)

        return {
            "translated_query": translated,
            "warnings": warnings,
            "unsupported_features": []
        }

    except Exception as e:
        raise SQLTranslationError(f"Error translating query: {str(e)}")
```

2. APLICAR MAPPINGS DE COLUMNAS:
```python
@staticmethod
def translate_query_with_mappings(
    query: str,
    source_dialect: str,
    target_dialect: str,
    column_mappings: List[dict]
) -> str:
    """
    Traduce query Y aplica mappings de columnas.

    Ejemplo:
    - Query origen: SELECT user_id, full_name FROM users
    - Mappings: {user_id → customer_id, full_name → name}
    - Query traducida: SELECT customer_id, name FROM customers
    """

    # 1. Traducir dialecto
    translated = translate_query(query, source_dialect, target_dialect)['translated_query']

    # 2. Aplicar mappings (replace column names)
    for mapping in column_mappings:
        origin_col = mapping['origin_column']
        dest_col = mapping['destination_column']
        origin_table = mapping['origin_table']
        dest_table = mapping['destination_table']

        # Replace column names en la query
        translated = translated.replace(f"{origin_table}.{origin_col}", f"{dest_table}.{dest_col}")
        translated = translated.replace(origin_col, dest_col)
        translated = translated.replace(origin_table, dest_table)

    return translated
```

3. VALIDAR SINTAXIS:
```python
@staticmethod
def validate_query(query: str, dialect: str) -> dict:
    """
    Valida sintaxis SQL sin ejecutar.

    Returns:
        {
            "valid": bool,
            "errors": List[str],
            "parsed_tree": Optional[dict]
        }
    """
    try:
        parsed = sqlglot.parse_one(query, read=dialect)
        return {
            "valid": True,
            "errors": [],
            "parsed_tree": parsed.dump() if parsed else None
        }
    except Exception as e:
        return {
            "valid": False,
            "errors": [str(e)],
            "parsed_tree": None
        }
```

4. MAPEO DE FUNCIONES ESPECÍFICAS:
```python
FUNCTION_MAPPING = {
    'postgresql': {
        'NOW()': {
            'mysql': 'NOW()',
            'sqlserver': 'GETDATE()',
            'oracle': 'SYSDATE'
        },
        "INTERVAL '30 days'": {
            'mysql': 'INTERVAL 30 DAY',
            'sqlserver': 'DATEADD(day, 30, GETDATE())',
            'oracle': 'INTERVAL \'30\' DAY'
        },
        'STRING_AGG': {
            'mysql': 'GROUP_CONCAT',
            'sqlserver': 'STRING_AGG',
            'oracle': 'LISTAGG'
        }
    }
}
```

CASOS DE USO:
1. Usuario escribe query para BD origen
2. Sistema traduce a dialecto de BD destino
3. Aplica mappings de columnas automáticamente
4. Retorna query lista para ejecutar

ENDPOINT:
POST /api/sql-translator/translate
Body: {
  query: str,
  source_dialect: str,
  target_dialect: str,
  project_id: Optional[str],  // Para usar mappings
  apply_mappings: bool
}
Response: {
  translated_query: str,
  warnings: List[str],
  execution_ready: bool
}
```

---

### 🎯 Tarea 5.3: Validador de Queries SQL (Sin Ejecución)

**Prompt Específica:**

```
OBJETIVO: Permitir al usuario escribir queries y traducirlas entre dialectos, pero SIN EJECUTARLAS.

IMPORTANTE: NO se ejecutan queries sobre datos reales. Solo validación de sintaxis y traducción.

COMPONENTES NECESARIOS:

1. BACKEND ENDPOINT:
POST /api/sql-translator/validate-and-translate
Body: {
  query: str,
  source_dialect: str,
  target_dialect: str,
  project_id: Optional[str],
  apply_mappings: bool
}
Response: {
  valid: bool,
  translated_query: str,
  warnings: List[str],
  column_mappings_applied: int,
  syntax_errors: List[str]
}

2. VALIDACIONES:
- Validar sintaxis SQL usando sqlglot
- NO ejecutar la query en ninguna base de datos
- Detectar comandos peligrosos (DDL/DML) y advertir
- Validar que los nombres de tablas existan en el proyecto (si project_id proporcionado)

3. FRONTEND (FUTURO):
- Monaco Editor para syntax highlighting
- Autocomplete de tablas y columnas del proyecto
- Botón "Translate to {target_dialect}"
- Vista de query traducida lado a lado
- NO hay botón "Execute" o "Preview" - solo traducción

FLUJO DE USO:
1. Usuario escribe query en dialecto origen
2. Sistema valida sintaxis
3. Sistema traduce a dialecto destino
4. Sistema aplica column mappings si project_id proporcionado
5. Usuario copia query traducida para ejecutar en su entorno

LIMITACIÓN IMPORTANTE:
DataMap NO ejecuta queries sobre datos de usuario. Solo provee:
- Introspección de estructura (metadata)
- Traducción de queries entre dialectos
- Generación de scripts de migración
```

---

## FASE 6: Testing y Seguridad

### 🎯 Tarea 6.1: Tests Unitarios de Adapters

**Prompt Específica:**

```
Crea `backend/test/unit/test_db_adapters.py` con tests para cada adapter.

ESTRUCTURA DE TESTS:
```python
import pytest
from unittest.mock import Mock, patch
from app.utils.db_adapters.postgres_adapter import PostgreSQLAdapter
from app.utils.db_adapters.base_adapter import DBConnectionError, DBAuthenticationError

class TestPostgreSQLAdapter:

    def test_init_with_valid_config(self):
        config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'testdb',
            'user': 'testuser',
            'password': 'testpass'
        }
        adapter = PostgreSQLAdapter(config)
        assert adapter.dialect == 'postgresql'
        assert adapter.is_connected == False

    def test_connect_success(self):
        # Mock psycopg2.connect
        with patch('psycopg2.connect') as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            adapter = PostgreSQLAdapter({...})
            adapter.connect()

            assert adapter.is_connected == True
            mock_connect.assert_called_once()

    def test_connect_invalid_credentials(self):
        with patch('psycopg2.connect', side_effect=psycopg2.OperationalError("invalid password")):
            adapter = PostgreSQLAdapter({...})

            with pytest.raises(DBAuthenticationError):
                adapter.connect()

    def test_test_connection_success(self):
        with patch('psycopg2.connect') as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            adapter = PostgreSQLAdapter({...})
            result = adapter.test_connection()

            assert result == True
            mock_conn.close.assert_called_once()

    def test_get_tables(self):
        # Mock cursor y resultados
        with patch('psycopg2.connect'):
            adapter = PostgreSQLAdapter({...})
            adapter.connect()

            # Mock cursor.fetchall()
            with patch.object(adapter.connection, 'cursor') as mock_cursor:
                mock_cursor.return_value.fetchall.return_value = [
                    {'table_name': 'users', 'table_schema': 'public'},
                    {'table_name': 'orders', 'table_schema': 'public'}
                ]

                tables = adapter.get_tables()

                assert len(tables) == 2
                assert tables[0]['name'] == 'users'

    def test_get_table_statistics(self):
        with patch('psycopg2.connect'):
            adapter = PostgreSQLAdapter({...})
            adapter.connect()

            # Mock pg_stat_user_tables query
            with patch.object(adapter.connection, 'cursor') as mock_cursor:
                mock_cursor.return_value.fetchone.return_value = {
                    'n_live_tup': 1000,
                    'table_size_bytes': 8192000,
                    'last_vacuum': '2025-01-20',
                    'last_analyze': '2025-01-21'
                }

                stats = adapter.get_table_statistics('users')

                assert stats['row_count'] == 1000
                assert stats['size_bytes'] == 8192000

    def test_context_manager(self):
        with patch('psycopg2.connect') as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            with PostgreSQLAdapter({...}) as adapter:
                assert adapter.is_connected == True

            # Verificar que disconnect fue llamado
            mock_conn.close.assert_called_once()
```

CASOS DE TEST POR ADAPTER:
- ✅ Conexión exitosa
- ✅ Credenciales inválidas
- ✅ Host no alcanzable
- ✅ Timeout de conexión
- ✅ get_tables() - solo metadata
- ✅ get_columns() - solo metadata
- ✅ get_primary_keys() - solo metadata
- ✅ get_foreign_keys() - solo metadata
- ✅ get_indexes() - solo metadata
- ✅ get_table_statistics() - solo metadata (row_count aproximado)
- ✅ SQL injection en nombres de tablas
- ✅ Context manager

USAR FIXTURES:
```python
@pytest.fixture
def valid_postgres_config():
    return {
        'host': 'localhost',
        'port': 5432,
        'database': 'testdb',
        'user': 'testuser',
        'password': 'testpass'
    }

@pytest.fixture
def mock_postgres_connection():
    with patch('psycopg2.connect') as mock:
        yield mock
```

EJECUTAR TESTS:
```bash
pytest backend/test/unit/test_db_adapters.py -v --cov=app/utils/db_adapters
```
```

---

### 🎯 Tarea 6.2: Tests de Integración con Bases de Datos Reales

**Prompt Específica:**

```
Crea `backend/test/integration/test_db_connection_flow.py` para tests E2E.

REQUISITOS:
- Docker Compose para levantar BDs de prueba
- PostgreSQL, MySQL, SQL Server containers
- Datos de prueba (schema + datos)

DOCKER COMPOSE:
```yaml
version: '3.8'

services:
  postgres_test:
    image: postgres:17
    environment:
      POSTGRES_DB: testdb
      POSTGRES_USER: testuser
      POSTGRES_PASSWORD: testpass
    ports:
      - "5433:5432"
    volumes:
      - ./test_data/postgres_init.sql:/docker-entrypoint-initdb.d/init.sql

  mysql_test:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: testdb
      MYSQL_USER: testuser
      MYSQL_PASSWORD: testpass
      MYSQL_ROOT_PASSWORD: rootpass
    ports:
      - "3307:3306"
    volumes:
      - ./test_data/mysql_init.sql:/docker-entrypoint-initdb.d/init.sql

  sqlserver_test:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      ACCEPT_EULA: Y
      SA_PASSWORD: TestPass123!
    ports:
      - "1434:1433"
```

TESTS E2E:
```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.mark.integration
class TestDBConnectionFlow:

    def test_full_flow_postgres(self, authenticated_user):
        """Test completo: connect → introspect → disconnect"""

        # 1. Test connection
        response = client.post('/api/db-connections/test', json={
            'db_type': 'postgresql',
            'host': 'localhost',
            'port': 5433,
            'database': 'testdb',
            'user': 'testuser',
            'password': 'testpass'
        }, headers=authenticated_user['headers'])

        assert response.status_code == 200
        assert response.json()['valid'] == True

        # 2. Connect (crear sesión)
        response = client.post('/api/db-connections/connect', json={
            'project_id': authenticated_user['project_id'],
            'db_type': 'postgresql',
            'host': 'localhost',
            'port': 5433,
            'database': 'testdb',
            'user': 'testuser',
            'password': 'testpass',
            'label': 'Test DB'
        }, headers=authenticated_user['headers'])

        assert response.status_code == 200
        connection_token = response.json()['connection_session_token']

        # 3. Get tables
        response = client.get('/api/db-connections/tables', headers={
            **authenticated_user['headers'],
            'X-DB-Connection-Session': connection_token
        })

        assert response.status_code == 200
        tables = response.json()
        assert len(tables) > 0
        assert 'users' in [t['name'] for t in tables]

        # 4. Get columns
        response = client.get('/api/db-connections/tables/users', headers={
            **authenticated_user['headers'],
            'X-DB-Connection-Session': connection_token
        })

        assert response.status_code == 200
        columns = response.json()['columns']
        assert 'id' in [c['name'] for c in columns]
        assert 'email' in [c['name'] for c in columns]

        # 5. Disconnect
        response = client.delete(f'/api/db-connections/{connection_token}',
                                 headers=authenticated_user['headers'])

        assert response.status_code == 200

    def test_connection_with_invalid_credentials(self):
        """Test con credenciales incorrectas"""

        response = client.post('/api/db-connections/test', json={
            'db_type': 'postgresql',
            'host': 'localhost',
            'port': 5433,
            'database': 'testdb',
            'user': 'testuser',
            'password': 'wrongpassword'
        })

        assert response.status_code == 401
        assert 'authentication' in response.json()['detail'].lower()
```

EJECUTAR TESTS:
```bash
# Levantar containers de test
docker-compose -f docker-compose.test.yml up -d

# Ejecutar tests
pytest backend/test/integration/test_db_connection_flow.py -v -m integration

# Detener containers
docker-compose -f docker-compose.test.yml down
```
```

---

### 🎯 Tarea 6.3: Auditoría de Seguridad

**Prompt Específica:**

```
Realiza auditoría de seguridad completa del sistema de conexiones.

CHECKLIST DE SEGURIDAD:

1. AUTENTICACIÓN Y AUTORIZACIÓN:
   - [ ] Solo usuarios autenticados pueden crear conexiones
   - [ ] Validación de ownership/membership del proyecto
   - [ ] Sesiones de conexión asociadas a user_id
   - [ ] Middleware valida user_id en cada request

2. CIFRADO DE CREDENCIALES:
   - [ ] Passwords cifrados con AES-256-GCM antes de guardar en Redis
   - [ ] Nonces únicos por cada cifrado
   - [ ] Encryption key derivada con Argon2id (nunca almacenada)
   - [ ] TTL automático de 3 horas

3. SQL INJECTION PREVENTION:
   - [ ] Prepared statements en todos los adapters (queries de information_schema)
   - [ ] Validación de table/column names (regex: ^[a-zA-Z0-9_]+$)
   - [ ] SOLO queries a information_schema/pg_catalog/sys views (metadata)
   - [ ] Sanitización de connection strings

4. PERMISOS DE BASE DE DATOS:
   - [ ] Usuario de conexión con permisos SOLO de lectura de metadata
   - [ ] NO permisos de SELECT en tablas de usuario
   - [ ] Documentar scripts de creación de usuarios read-only por BD
   - [ ] Validar que queries NO accedan a datos de usuario

5. RATE LIMITING:
   - [ ] Test connection: 5 req/min
   - [ ] Create connection: 10 req/hour
   - [ ] Introspection: 30 req/min
   - [ ] SQL translation: 50 req/min

6. LOGGING Y AUDITORÍA:
   - [ ] Log todos los intentos de conexión (exitosos y fallidos)
   - [ ] Log introspecciones realizadas (tablas consultadas)
   - [ ] NUNCA loggear passwords o datos sensibles
   - [ ] Security events en tabla security_logs

7. TIMEOUT Y RESOURCE LIMITS:
   - [ ] Connection timeout: 30 segundos
   - [ ] Introspection timeout: 60 segundos
   - [ ] Max concurrent connections per user: 5
   - [ ] Max schemas to introspect: 50 tablas por request

8. ERROR HANDLING:
   - [ ] Mensajes de error genéricos (no revelar detalles internos)
   - [ ] Exception sanitization
   - [ ] Stack traces solo en development

9. NETWORK SECURITY:
   - [ ] HTTPS obligatorio en producción
   - [ ] SSL/TLS para conexiones a BDs externas (opcional pero recomendado)
   - [ ] Validación de certificados SSL

HERRAMIENTAS DE TESTING:

1. OWASP ZAP:
   - Escanear endpoints con ZAP Proxy
   - Detectar vulnerabilidades comunes

2. SQL Injection Tests:
```python
@pytest.mark.security
class TestSQLInjection:

    def test_sql_injection_in_table_name(self):
        malicious_input = "users'; DROP TABLE users;--"

        # Debe fallar validación de nombre de tabla
        with pytest.raises(ValueError):
            adapter.get_columns(malicious_input)

    def test_sql_injection_in_schema_name(self):
        malicious_input = "public; DELETE FROM users;--"

        # Debe fallar validación de schema
        with pytest.raises(ValueError):
            adapter.get_tables(schema=malicious_input)

    def test_metadata_only_queries(self):
        """Verificar que SOLO se consultan vistas de metadata"""
        adapter = PostgreSQLAdapter({...})
        adapter.connect()

        # Obtener tablas - debe usar information_schema
        tables = adapter.get_tables()

        # Verificar que NO se accedió a tablas de usuario
        # Mock debe confirmar que solo se hicieron queries a information_schema
        assert all('information_schema' in query or 'pg_catalog' in query
                   for query in adapter._executed_queries)
```

3. PENETRATION TESTING:
   - Intentar session hijacking
   - Intentar acceder a conexiones de otros usuarios
   - Intentar leer datos de tablas (debe fallar con "permission denied")
   - Verificar que usuario DB tiene SOLO permisos de metadata

REPORTE DE SEGURIDAD:
Documentar hallazgos en `docs/security/FASE_2_CONNECTION_SECURITY_AUDIT.md`
```

---

## 🗓️ Roadmap de Implementación

### Semana 1-2: Conectores de Bases de Datos

**Día 1-2:**
- ✅ Tarea 1.1: BaseAdapter abstracto
- ✅ Tarea 1.2: PostgreSQLAdapter

**Día 3-4:**
- ✅ Tarea 1.3: MySQLAdapter
- ✅ Tarea 1.4: SQLServerAdapter

**Día 5:**
- ✅ Tarea 1.5: OracleAdapter

**Día 6-7:**
- ✅ Tarea 1.6: DBConnectionService
- ✅ Tarea 1.7: API Endpoints

**Día 8-10:**
- ✅ Tests unitarios de adapters
- ✅ Tests de integración básicos

### Semana 3: Sistema de Sesiones de Conexión

**Día 1-2:**
- ✅ Tarea 2.1: Extender RedisSessionCache

**Día 3-4:**
- ✅ Tarea 2.2: Middleware de DB Session
- ✅ Integración con endpoints existentes

**Día 5:**
- ✅ Tests de sesiones
- ✅ Documentación

### Semana 4: Introspección de Schemas

**Día 1-3:**
- ✅ Tarea 3.1: SchemaIntrospectionService
- ✅ Tarea 3.2: Endpoints de introspección

**Día 4-5:**
- ✅ Tarea 3.3: Comparador de schemas
- ✅ Tests de introspección

### Semana 5-6: Generador de Scripts de Migración

**Día 1-3:**
- ✅ Tarea 4.1: MigrationGeneratorService (DDL)
- ✅ Mapeo de tipos de datos

**Día 4-6:**
- ✅ Tarea 4.2: Generador de scripts DML
- ✅ Background tasks

**Día 7-8:**
- ✅ Tarea 4.3: Endpoints de generación
- ✅ Tests de generación

**Día 9-10:**
- ✅ Integración E2E: Desde conexión hasta script generado

### Semana 7-8: Traductor de Consultas SQL

**Día 1-2:**
- ✅ Tarea 5.1: Instalar y configurar SQLGlot

**Día 3-5:**
- ✅ Tarea 5.2: SQLTranslatorService
- ✅ Mapeo de funciones específicas

**Día 6-8:**
- ✅ Tarea 5.3: Validador de queries SQL (sin ejecución)
- ✅ Tests de traducción y validación

**Día 9-10:**
- ✅ Integración con mappings de DataMap
- ✅ Validación de queries complejas

### Semana 9: Testing y Seguridad

**Día 1-3:**
- ✅ Tarea 6.1: Tests unitarios completos
- ✅ Tarea 6.2: Tests de integración E2E

**Día 4-5:**
- ✅ Tarea 6.3: Auditoría de seguridad
- ✅ Penetration testing

**Día 6-7:**
- ✅ Performance testing
- ✅ Load testing
- ✅ Optimizaciones

**Día 8-10:**
- ✅ Documentación completa
- ✅ Guía de deployment
- ✅ Troubleshooting guide

---

## 🔒 Consideraciones de Seguridad

### 1. Principio de Mínimo Privilegio

**Conexiones Read-Only:**
```python
# PostgreSQL
connection_string += " options='-c default_transaction_read_only=on'"

# MySQL
connection_config['autocommit'] = True
# Ejecutar: SET SESSION TRANSACTION READ ONLY;

# SQL Server
# Usar db_datareader role

# Oracle
# GRANT SELECT ON schema.* TO user;
```

### 2. Cifrado de Credenciales

**Flujo de Cifrado:**
```
1. Usuario envía password en HTTPS
2. Backend deriva encryption_key con Argon2id
3. Cifra password con AES-256-GCM
4. Guarda en Redis: {password_encrypted, nonce}
5. TTL automático de 3 horas
6. Al recuperar: descifra on-demand
```

**Código:**
```python
from app.utils.encryption import EncryptionManager

def store_connection_credentials(connection_config: dict, encryption_key: bytes) -> dict:
    """Cifra password antes de guardar en Redis"""

    password = connection_config['password']

    # Cifrar password
    encrypted_password, nonce = EncryptionManager.encrypt(password, encryption_key)

    # Guardar config sin password en plaintext
    safe_config = {
        **connection_config,
        'password_encrypted': base64.b64encode(encrypted_password).decode(),
        'password_nonce': base64.b64encode(nonce).decode()
    }
    del safe_config['password']

    return safe_config
```

### 3. Validación de Inputs

**Whitelist de Nombres:**
```python
import re

def validate_identifier(name: str) -> bool:
    """Valida que nombre de tabla/columna sea seguro"""

    # Solo alfanuméricos y underscore
    pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'

    if not re.match(pattern, name):
        raise ValueError(f"Invalid identifier: {name}")

    # Max length
    if len(name) > 128:
        raise ValueError("Identifier too long")

    # Reserved words (depende del dialecto)
    reserved = ['SELECT', 'FROM', 'WHERE', 'DROP', 'CREATE', ...]
    if name.upper() in reserved:
        raise ValueError(f"Reserved keyword: {name}")

    return True
```

### 4. Rate Limiting Granular

**Configuración:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Por endpoint
@router.post("/api/db-connections/test")
@limiter.limit("5/minute")
async def test_connection(...):
    pass

@router.post("/api/db-connections/connect")
@limiter.limit("10/hour")
async def create_connection(...):
    pass

@router.post("/api/sql-translator/validate-and-translate")
@limiter.limit("50/minute")
async def validate_and_translate(...):
    pass
```

### 5. Logging Seguro

**Sanitización:**
```python
import logging
import re

logger = logging.getLogger(__name__)

def sanitize_for_logging(data: dict) -> dict:
    """Remueve información sensible antes de loggear"""

    sensitive_keys = ['password', 'pwd', 'token', 'secret', 'key', 'passphrase']

    sanitized = {}
    for key, value in data.items():
        if any(s in key.lower() for s in sensitive_keys):
            sanitized[key] = '***REDACTED***'
        else:
            sanitized[key] = value

    return sanitized

# Uso
logger.info(f"Connection attempt: {sanitize_for_logging(connection_config)}")
```

### 6. Timeout y Circuit Breaker

**Timeout:**
```python
import signal
from contextlib import contextmanager

@contextmanager
def timeout(seconds: int):
    """Context manager para timeout de operaciones"""

    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")

    # Set timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)

    try:
        yield
    finally:
        signal.alarm(0)

# Uso
with timeout(30):
    adapter.connect()
    results = adapter.get_tables()
```

### 7. Auditoría y Compliance

**Eventos a Loggear:**
```python
# Tabla security_logs (ya existe)
def log_security_event(db, user_id: str, event_type: str, details: dict):
    """Log evento de seguridad"""

    sanitized_details = sanitize_for_logging(details)

    cursor.execute("""
        INSERT INTO security_logs (
            id, user_id, event_type, event_data,
            ip_address, user_agent, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        str(uuid.uuid4()),
        user_id,
        event_type,
        json.dumps(sanitized_details),
        request.client.host,
        request.headers.get('user-agent'),
        datetime.utcnow()
    ))

    db.commit()

# Eventos a loggear:
# - db_connection_created
# - db_connection_failed
# - db_connection_closed
# - query_executed
# - introspection_performed
# - migration_script_generated
```

---

## 📚 Referencias y Recursos

### Documentación de Bibliotecas

1. **psycopg2**: https://www.psycopg.org/docs/
2. **pymysql**: https://pymysql.readthedocs.io/
3. **pyodbc**: https://github.com/mkleehammer/pyodbc
4. **cx_Oracle**: https://cx-oracle.readthedocs.io/
5. **sqlglot**: https://github.com/tobymao/sqlglot
6. **Redis**: https://redis-py.readthedocs.io/

### Drivers de Bases de Datos

1. **PostgreSQL**: Built-in
2. **MySQL**: Built-in
3. **SQL Server**: Requiere Microsoft ODBC Driver 18
   - Windows: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
   - Linux: `sudo apt-get install unixodbc-dev`
4. **Oracle**: Requiere Oracle Instant Client
   - Download: https://www.oracle.com/database/technologies/instant-client/downloads.html

### Mejores Prácticas

1. **OWASP Top 10**: https://owasp.org/www-project-top-ten/
2. **SQL Injection Prevention**: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
3. **API Security**: https://owasp.org/www-project-api-security/
4. **Redis Security**: https://redis.io/docs/management/security/

---

## 📝 Actualizaciones del Plan

### Versión 1.1 - Restricción de Permisos a Solo Metadata (2025-01-24)

**Cambios de Seguridad Críticos:**

1. **Permisos de Usuario DB Restringidos:**
   - ❌ ELIMINADO: Permisos de lectura a tablas de usuario
   - ✅ AGREGADO: Scripts SQL para crear usuarios con permisos SOLO de metadata
   - ✅ AGREGADO: Documentación de permisos por cada dialecto (PostgreSQL, MySQL, SQL Server, Oracle)

2. **Métodos del Adapter Modificados:**
   - ❌ ELIMINADO: `execute_query(query, params)` - ejecutaba queries arbitrarias
   - ❌ ELIMINADO: `get_table_row_count(table_name)` - ejecutaba `SELECT COUNT(*)`
   - ❌ ELIMINADO: Endpoint `GET /api/db-connections/tables/{table_name}/data`
   - ✅ AGREGADO: `get_table_statistics(table_name)` - usa solo `pg_stat_user_tables` (aproximación)

3. **Frontend/API Modificado:**
   - ❌ ELIMINADO: Tarea 5.3 "Editor de queries con preview" (ejecutaba queries)
   - ✅ AGREGADO: Tarea 5.3 "Validador de queries SQL" (solo validación, sin ejecución)
   - ❌ ELIMINADO: Endpoint `POST /api/sql-translator/execute-preview`
   - ✅ AGREGADO: Endpoint `POST /api/sql-translator/validate-and-translate`

4. **Tests Actualizados:**
   - ✅ AGREGADO: `test_metadata_only_queries()` - verifica que solo se consulta `information_schema`
   - ✅ AGREGADO: Penetration test para verificar que usuario DB NO puede leer datos

**Razón del Cambio:**
DataMap es una herramienta de **mapeo y migración de schemas**, NO una herramienta de exploración de datos.
Limitar permisos a solo metadata reduce significativamente la superficie de ataque y protege los datos sensibles del cliente.

---

## 🎉 Conclusión

Este plan detalla la implementación completa de la **Fase 2: Sistema de Conexión Local con Bases de Datos** para DataMap.

### Características Principales Implementadas:

1. ✅ **Conectores Multi-BD**: PostgreSQL, MySQL, SQL Server, Oracle (solo metadata)
2. ✅ **Sesiones Temporales**: Credenciales cifradas en Redis (TTL 3h)
3. ✅ **Introspección de Schemas**: Sin almacenar permanentemente, SOLO metadata
4. ✅ **Generador de Scripts**: DDL y DML basados en metadatos
5. ✅ **Traductor SQL**: Conversión entre dialectos con sqlglot (validación, no ejecución)
6. ✅ **Seguridad Enterprise**: Cifrado, rate limiting, auditoría, permisos mínimos

### Próximos Pasos:

- **Nivel 3**: BYOK (Bring Your Own Key) con AWS KMS, Azure Key Vault, etc.
- **Nivel 4**: Integración con herramientas ETL (Airflow, dbt, Fivetran)
- **Nivel 5**: ML-powered query optimization y schema recommendations

### Tiempo Estimado de Implementación:

- **9 semanas** para desarrollo completo
- **2 semanas adicionales** para QA y deployment

**Total: 11 semanas (~2.5 meses)**

---

**Generado por**: DataMap Engineering Team
**Fecha Original**: 2025-01-24
**Última Actualización**: 2025-01-24
**Versión**: 1.1 (Metadata-Only Security Update)
