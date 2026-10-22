-- Migración 002: Corregir tipo de ID en primary_key_constraints
-- Fecha: 2025-01-30
-- Descripción: Cambia el ID de UUID a SERIAL para auto-incremento

-- Si la tabla usa UUID, necesitamos recrearla con SERIAL
-- SOLO ejecutar esto si la tabla está usando UUID

-- Primero, verificar si necesitamos cambiar el tipo de dato
DO $$
BEGIN
    -- Verificar si id es de tipo UUID
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'primary_key_constraints'
        AND column_name = 'id'
        AND data_type = 'uuid'
    ) THEN
        -- Recrear la tabla con SERIAL

        -- 1. Crear tabla temporal con estructura correcta
        CREATE TABLE primary_key_constraints_new (
            id SERIAL PRIMARY KEY,
            table_id INTEGER NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
            column_ids INTEGER[] NOT NULL,
            constraint_name VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

            -- Constraints
            CONSTRAINT pk_at_least_one_column_new CHECK (array_length(column_ids, 1) >= 1),
            CONSTRAINT pk_unique_per_table_new UNIQUE (table_id)
        );

        -- 2. Copiar datos existentes (el ID se regenerará automáticamente)
        INSERT INTO primary_key_constraints_new (table_id, column_ids, constraint_name, created_at, updated_at)
        SELECT table_id, column_ids, constraint_name, created_at, updated_at
        FROM primary_key_constraints;

        -- 3. Eliminar tabla vieja y renombrar la nueva
        DROP TABLE primary_key_constraints CASCADE;
        ALTER TABLE primary_key_constraints_new RENAME TO primary_key_constraints;

        -- 4. Recrear índices
        CREATE INDEX idx_pk_constraints_table_id ON primary_key_constraints(table_id);
        CREATE INDEX idx_pk_constraints_column_ids ON primary_key_constraints USING GIN(column_ids);

        -- 5. Renombrar constraints
        ALTER TABLE primary_key_constraints RENAME CONSTRAINT pk_at_least_one_column_new TO pk_at_least_one_column;
        ALTER TABLE primary_key_constraints RENAME CONSTRAINT pk_unique_per_table_new TO pk_unique_per_table;

        RAISE NOTICE 'Tabla primary_key_constraints actualizada de UUID a SERIAL';
    ELSE
        RAISE NOTICE 'La tabla primary_key_constraints ya usa INTEGER, no se requiere migración';
    END IF;
END $$;
