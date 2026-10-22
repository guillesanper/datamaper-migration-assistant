-- Migración 002B: Agregar secuencia de auto-incremento a primary_key_constraints
-- Fecha: 2025-01-30
-- Descripción: Si la tabla usa INTEGER sin auto-incremento, agregar secuencia

DO $$
BEGIN
    -- Crear secuencia si no existe
    CREATE SEQUENCE IF NOT EXISTS primary_key_constraints_id_seq;

    -- Obtener el máximo ID actual y configurar la secuencia
    PERFORM setval('primary_key_constraints_id_seq', COALESCE((SELECT MAX(id) FROM primary_key_constraints), 0) + 1, false);

    -- Configurar la columna id para usar la secuencia
    ALTER TABLE primary_key_constraints ALTER COLUMN id SET DEFAULT nextval('primary_key_constraints_id_seq');

    -- Asociar la secuencia con la columna
    ALTER SEQUENCE primary_key_constraints_id_seq OWNED BY primary_key_constraints.id;

    RAISE NOTICE 'Secuencia de auto-incremento agregada a primary_key_constraints.id';
END $$;
