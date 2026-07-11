# Inicialización de Base de Datos

Este directorio contiene los archivos SQL que se ejecutarán automáticamente cuando se inicie el contenedor de PostgreSQL por primera vez.

## Cómo exportar tu base de datos desde pgAdmin

1. **Abre pgAdmin** y conéctate a tu base de datos local
2. Haz clic derecho sobre la base de datos que quieres exportar
3. Selecciona **"Backup..."**
4. En la pestaña "General":
   - **Filename**: Elige la ruta y nombre del archivo (por ejemplo: `datamap_dump.sql`)
   - **Format**: Selecciona **"Plain"** (archivo SQL de texto plano)
5. En la pestaña "Dump options":
   - Sección "Data/Objects":
     - Marca: **"Pre-data"** (estructura de la base de datos)
     - Marca: **"Data"** (datos de las tablas)
     - Marca: **"Post-data"** (índices, constraints, etc.)
   - Sección "Type of objects":
     - Marca: **"Only data"** si solo quieres los datos
     - O deja todas las opciones por defecto para exportar todo
6. Haz clic en **"Backup"**

## Cómo usar el dump con Docker Compose

1. **Coloca el archivo SQL exportado** en este directorio (`backend/init-db/`)
   - Ejemplo: `backend/init-db/dump.sql`
   - **IMPORTANTE**: Nómbralo con un prefijo numérico mayor a `00_` para que se ejecute después del script de inicialización
   - Ejemplo: `01_dump.sql` o simplemente `dump.sql`

2. **Elimina el volumen de PostgreSQL existente** (si existe):
   ```bash
   docker-compose down -v
   ```
   Esto eliminará todos los volúmenes, incluyendo los datos de la base de datos.

3. **Inicia los contenedores**:
   ```bash
   docker-compose up -d
   ```

4. El contenedor de PostgreSQL ejecutará automáticamente todos los archivos `.sql` en orden alfabético al iniciar por primera vez:
   - Primero: `00_init_user.sql` (crea el usuario postgres necesario)
   - Después: Tu dump SQL con los datos

## Notas importantes

- Los archivos en este directorio **solo se ejecutan la primera vez** que se inicia el contenedor (cuando el volumen está vacío)
- Si necesitas reinicializar la base de datos, debes eliminar el volumen con `docker-compose down -v`
- Los archivos se ejecutan en **orden alfabético**, por lo que puedes usar prefijos numéricos si tienes múltiples archivos:
  - `01_schema.sql`
  - `02_data.sql`
  - `03_indexes.sql`
- También puedes usar archivos `.sql.gz` (comprimidos) para dumps grandes
- Los archivos `.sh` también se ejecutarán si necesitas scripts de shell personalizados

## Ejemplo de comandos rápidos

```bash
# Exportar usando pg_dump (alternativa a pgAdmin)
pg_dump -U datamaper_user_local -h localhost -p 5432 datamap_dev > backend/init-db/dump.sql

# Reiniciar la base de datos con el dump
docker-compose down -v
docker-compose up -d postgres

# Ver logs del proceso de inicialización
docker-compose logs -f postgres
```
