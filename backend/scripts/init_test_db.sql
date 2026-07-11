-- Script de inicialización para base de datos de test
-- Ejecutar como superuser de PostgreSQL

-- Terminar conexiones activas a la base de datos de test si existe
SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE pg_stat_activity.datname = 'datamap_test'
  AND pid <> pg_backend_pid();

-- Eliminar base de datos de test si existe (para empezar limpio)
DROP DATABASE IF EXISTS datamap_test;

-- Crear base de datos de test
CREATE DATABASE datamap_test
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1
    IS_TEMPLATE = False;

COMMENT ON DATABASE datamap_test IS 'Base de datos para tests automatizados';

-- Conectar a la base de datos de test
\c datamap_test

-- Crear extensiones necesarias
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

-- Dar permisos al usuario postgres
GRANT ALL PRIVILEGES ON DATABASE datamap_test TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
