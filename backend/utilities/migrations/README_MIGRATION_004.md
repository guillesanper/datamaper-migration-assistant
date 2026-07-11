# Migración 004: Fix Encryption Nullable Fields

## Problema

Cuando se activa el cifrado en un proyecto con datos existentes, el sistema intenta encriptar los datos y luego poner los campos originales (`name`, `data_type`, etc.) en `NULL`. Sin embargo, estos campos tienen restricciones `NOT NULL` en la base de datos, lo que causa el siguiente error:

```
el valor nulo en la columna «name» de la relación «tables» viola la restricción de no nulo
```

## Solución

Esta migración resuelve el problema permitiendo que los campos originales sean `NULL` cuando los datos están cifrados (`is_encrypted = TRUE`), y agrega constraints CHECK para garantizar la integridad de los datos.

### Cambios realizados:

1. **Tabla `tables`:**
   - `name` ahora puede ser NULL
   - Constraint CHECK: garantiza que `name` exista en texto plano O cifrado

2. **Tabla `columns`:**
   - `name` ahora puede ser NULL
   - `data_type` ahora puede ser NULL
   - Constraints CHECK: garantizan que ambos campos existan en texto plano O cifrados

3. **Tabla `mappings`:**
   - Constraints CHECK para todos los campos que se cifran

## Cómo ejecutar la migración

### Opción 1: Usando el script Python (Recomendado)

```bash
cd backend
python utilities/migrations/run_migration_004.py
```

El script:
- Conecta a la base de datos automáticamente
- Ejecuta la migración
- Verifica que los constraints fueron creados correctamente
- Muestra un resumen de los cambios

### Opción 2: Manualmente con psql

```bash
psql -U tu_usuario -d tu_database -f backend/utilities/migrations/004_fix_encryption_nullable_fields.sql
```

## Verificar que la migración se ejecutó correctamente

Después de ejecutar la migración, verifica que los constraints fueron creados:

```sql
SELECT constraint_name, table_name
FROM information_schema.table_constraints
WHERE constraint_name LIKE '%encrypted%'
  AND constraint_type = 'CHECK';
```

Deberías ver algo como:

```
 constraint_name                        | table_name
----------------------------------------+------------
 check_table_name_or_encrypted         | tables
 check_column_name_or_encrypted        | columns
 check_column_datatype_or_encrypted    | columns
 check_mapping_origin_table_or_encrypted | mappings
 check_mapping_origin_column_or_encrypted | mappings
 check_mapping_dest_table_or_encrypted | mappings
 check_mapping_dest_column_or_encrypted | mappings
```

## Probar el cifrado

Después de ejecutar la migración, puedes activar el cifrado en un proyecto:

1. Ve a la configuración del proyecto en el frontend
2. Activa el cifrado con una passphrase segura
3. El sistema debería cifrar todos los datos existentes sin errores

## Rollback (revertir la migración)

Si necesitas revertir esta migración (NO RECOMENDADO si ya tienes datos cifrados):

```sql
-- Revertir constraints CHECK
ALTER TABLE tables DROP CONSTRAINT IF EXISTS check_table_name_or_encrypted;
ALTER TABLE columns DROP CONSTRAINT IF EXISTS check_column_name_or_encrypted;
ALTER TABLE columns DROP CONSTRAINT IF EXISTS check_column_datatype_or_encrypted;
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS check_mapping_origin_table_or_encrypted;
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS check_mapping_origin_column_or_encrypted;
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS check_mapping_dest_table_or_encrypted;
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS check_mapping_dest_column_or_encrypted;

-- Revertir NOT NULL (SOLO SI NO HAY DATOS CIFRADOS)
ALTER TABLE tables ALTER COLUMN name SET NOT NULL;
ALTER TABLE columns ALTER COLUMN name SET NOT NULL;
ALTER TABLE columns ALTER COLUMN data_type SET NOT NULL;
```

**ADVERTENCIA:** NO ejecutes el rollback si ya tienes datos cifrados en la base de datos, ya que causará errores de integridad.

## Troubleshooting

### Error: "constraint... already exists"

Si ves este error, significa que la migración ya se ejecutó anteriormente. Puedes verificar con:

```sql
SELECT * FROM information_schema.table_constraints
WHERE constraint_name = 'check_table_name_or_encrypted';
```

### Error al conectar a la base de datos

Verifica que las variables de entorno estén configuradas correctamente:

```bash
# En .env o en tu entorno
export DATABASE_URL="postgresql://usuario:password@localhost:5432/tu_database"
```

### Los datos no se cifran después de la migración

Verifica que:
1. La migración se ejecutó correctamente
2. El proyecto tiene configuración de cifrado (tabla `project_encryption`)
3. La passphrase es correcta

## Más información

Para más detalles sobre el sistema de cifrado, consulta:
- `backend/app/services/encryption_service.py` - Lógica de cifrado
- `backend/app/routers/encryption.py` - Endpoints de cifrado
- `backend/utilities/migrations/003_encryption_infrastructure.sql` - Migración inicial de cifrado
