// src/types/db_connection_types.ts

/**
 * Tipos de dialectos SQL soportados
 */
export type DBDialect = 'postgresql' | 'mysql' | 'sqlserver' | 'oracle';

/**
 * Configuración de conexión a base de datos
 */
export interface DBConnectionConfig {
  dialect: DBDialect;
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
  timeout?: number;
  // Oracle específico
  service_name?: string;
  sid?: string;
  // TLS: el cifrado es siempre obligatorio; esto solo controla la verificación del certificado
  /** false salta la verificación del certificado (exige confirm_hostname). Por defecto true */
  tls_verify?: boolean;
  /** CA propia en PEM (solo certificados). No soportada en SQL Server */
  tls_ca_pem?: string;
  /** Debe coincidir con host cuando tls_verify es false; el backend lo exige */
  confirm_hostname?: string;
}

/**
 * Resultado de test de conexión
 */
export interface DBConnectionTestResult {
  success: boolean;
  dialect: string;
  host: string;
  database: string;
  error_message?: string | null;
  /** authentication | connection | timeout | tls | unknown */
  error_type?: string | null;
  /** false si la prueba no verificó el certificado del servidor */
  tls_verified: boolean;
}

/**
 * Respuesta al crear una sesión de conexión
 */
export interface DBConnectionSessionResponse {
  session_id: string;
  dialect: string;
  host: string;
  database: string;
  expires_at: string;
  /** false si la conexión se creó sin verificar el certificado; no cambia en toda la sesión */
  tls_verified: boolean;
}

/**
 * Metadata de columna de BD externa
 */
export interface ColumnMetadata {
  name: string;
  data_type: string;
  native_type: string;
  is_nullable: boolean;
  is_auto_increment: boolean;
  is_primary_key: boolean;
  default_value: string | null;
  max_length: number | null;
  ordinal_position: number;
}

/**
 * Metadata de tabla de BD externa
 */
export interface TableMetadata {
  name: string;
  schema: string;
  table_type: string;
  columns: ColumnMetadata[];
}

/**
 * Metadata de primary key
 */
export interface PrimaryKeyMetadata {
  constraint_name: string;
  column_name: string;
  ordinal_position: number;
}

/**
 * Metadata de foreign key
 */
export interface ForeignKeyMetadata {
  constraint_name: string;
  column_name: string;
  referenced_table_schema: string;
  referenced_table_name: string;
  referenced_column_name: string;
  update_rule: string;
  delete_rule: string;
}

/**
 * Metadata de índice
 */
export interface IndexMetadata {
  index_name: string;
  column_name: string;
  is_unique: boolean;
  index_type: string;
  ordinal_position: number;
}

/**
 * Metadata completa de un schema
 */
export interface SchemaMetadata {
  name: string;
  tables: TableMetadata[];
  primary_keys: PrimaryKeyMetadata[];
  foreign_keys: ForeignKeyMetadata[];
  indexes: IndexMetadata[];
}

/**
 * Tabla externa de BD (solo en memoria del frontend)
 */
export interface ExternalDBTable {
  // Pseudo-ID generado en frontend
  id: string;                      // `${sessionId}:${schema}:${table}`
  name: string;
  schema: string;
  type: 'origin' | 'destination';  // Según la pestaña seleccionada
  is_external_db: true;            // Flag para diferenciar de tablas del proyecto
  session_id: string;              // Referencia a la sesión de Redis
  columns: ExternalDBColumn[];
  created_at: string;              // Timestamp de carga
}

/**
 * Columna externa de BD (solo en memoria del frontend)
 */
export interface ExternalDBColumn {
  id: string;                      // `${sessionId}:${schema}:${table}:${column}`
  table_id: string;                // Referencia al ID de la tabla externa
  name: string;
  data_type: string;
  native_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
  is_auto_increment: boolean;
  default_value: string | null;
  max_length: number | null;
  table_type: 'origin' | 'destination';
}

/**
 * Puertos por defecto según dialecto
 */
export const DEFAULT_PORTS: Record<DBDialect, number> = {
  postgresql: 5432,
  mysql: 3306,
  sqlserver: 1433,
  oracle: 1521,
};

/**
 * Nombres amigables de dialectos
 */
export const DIALECT_NAMES: Record<DBDialect, string> = {
  postgresql: 'PostgreSQL',
  mysql: 'MySQL / MariaDB',
  sqlserver: 'SQL Server',
  oracle: 'Oracle',
};

/**
 * Columna de BD externa con hash para mappings (modo connector)
 */
export interface ConnectorColumn {
  name: string;         // Nombre real visible al usuario
  column_hash: string;  // SHA-256(name) — solo para identificar en mappings
  data_type: string;
  native_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
  is_auto_increment: boolean;
  default_value: string | null;
  max_length: number | null;
  ordinal_position: number;
}

/**
 * Tabla de BD externa con hash para mappings (modo connector).
 * La estructura NO se guarda en la BD local — solo los mappings usan los hashes.
 */
export interface ConnectorTable {
  name: string;       // Nombre real visible al usuario
  table_hash: string; // SHA-256(name) — solo para identificar en mappings
  schema: string;
  table_type: string;
  columns: ConnectorColumn[];
  // Campos añadidos en el frontend para integración con la vista
  id: string;                      // `connector:${session_id}:${schema}:${name}`
  type: 'origin' | 'destination';  // Según la pestaña seleccionada al conectar
  session_id: string;
  is_connector: true;
}

/**
 * Respuesta del endpoint /sessions/{id}/connector-tables
 */
export interface ConnectorTablesResponse {
  session_id: string;
  tables: Array<Omit<ConnectorTable, 'id' | 'type' | 'session_id' | 'is_connector'>>;
}

/**
 * Errores de validación
 */
export interface ValidationErrors {
  host?: string;
  port?: string;
  database?: string;
  user?: string;
  password?: string;
  service_name?: string;
  sid?: string;
  timeout?: string;
  tls_ca_pem?: string;
}
