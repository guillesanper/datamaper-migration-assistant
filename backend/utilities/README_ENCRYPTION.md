# 🔐 Guía de Cifrado de Datos

## Escenarios

### Escenario 1: Proyecto NUEVO con Cifrado
✅ **No necesitas hacer nada extra**
- Activa el cifrado desde la UI al crear el proyecto
- Todos los datos se cifrarán automáticamente

### Escenario 2: Proyecto EXISTENTE - Activar Cifrado
⚠️ **Necesitas cifrar los datos existentes manualmente**

Este es tu caso actual. Los pasos son:

## 📋 Pasos para Cifrar Datos Existentes

### 1. Activar Cifrado en la UI
- Edita el proyecto
- Marca el checkbox de "Activar cifrado"
- Ingresa una passphrase fuerte (mín. 12 caracteres, mayúsculas, minúsculas y números)
- Guarda

**IMPORTANTE**: Guarda la passphrase en un lugar seguro. Sin ella los datos son irrecuperables.

### 2. Ejecutar el Script de Migración

#### Opción A: Dry-Run (Prueba sin hacer cambios)
```bash
cd backend
python utilities/encrypt_existing_data.py --project-id <TU_PROJECT_ID> --dry-run
```

Esto te mostrará cuántos datos se cifrarían sin hacer cambios reales.

#### Opción B: Cifrar Realmente
```bash
cd backend
python utilities/encrypt_existing_data.py --project-id <TU_PROJECT_ID>
```

El script te pedirá la passphrase y cifrará:
- ✅ Tablas (nombres)
- ✅ Columnas (nombres y tipos de datos)
- ✅ Mappings (tablas, columnas, lógica de transformación)
- ✅ Versiones (snapshots y diffs)
- ✅ Comentarios (contenido)

#### Opción C: Cifrar SIN Versiones (Más Rápido)
```bash
python utilities/encrypt_existing_data.py --project-id <TU_PROJECT_ID> --skip-versions
```

### 3. Verificar en PostgreSQL

Después de ejecutar el script, verifica en PostgreSQL:

```sql
-- Ver tablas cifradas
SELECT id, name, name_encrypted, is_encrypted
FROM tables
WHERE project_id = '<TU_PROJECT_ID>';

-- Si is_encrypted = TRUE, los datos están cifrados
-- name debería estar NULL y name_encrypted debería tener datos

-- Ver columnas cifradas
SELECT c.id, c.name, c.name_encrypted, c.is_encrypted
FROM columns c
JOIN tables t ON c.table_id = t.id
WHERE t.project_id = '<TU_PROJECT_ID>';
```

## 🔍 Cómo Funciona el Cifrado

### En la Base de Datos
```
Antes del cifrado:
- name = "users"          (texto plano)
- name_encrypted = NULL
- name_nonce = NULL
- is_encrypted = FALSE

Después del cifrado:
- name = NULL
- name_encrypted = "a8f3h2..."  (datos cifrados en base64)
- name_nonce = "k9d2l1..."      (nonce único en base64)
- is_encrypted = TRUE
```

### En la Aplicación
Cuando lees datos:
1. Middleware verifica si hay `X-Encryption-Session` header
2. Si hay sesión, carga el `encryption_key`
3. El CRUD detecta `is_encrypted = TRUE`
4. Desencripta automáticamente usando `name_encrypted` + `name_nonce`
5. Devuelve el texto plano a la aplicación

**Por eso nunca ves datos cifrados en la UI** - se desencriptan automáticamente cuando tienes una sesión activa.

## 🛠️ Comandos Útiles

### Encontrar tu Project ID
Desde la UI: El ID aparece en la URL cuando editas un proyecto
```
/project_detail/238ef9be-244f-49e8-a861-3cb7e3e56109/schemas
                 ↑ Este es tu project_id
```

O desde PostgreSQL:
```sql
SELECT id, name FROM projects WHERE name = 'Tu Proyecto';
```

### Ver Estado de Cifrado
```sql
-- Contar datos sin cifrar
SELECT
    'tables' as entity,
    COUNT(*) as unencrypted
FROM tables
WHERE project_id = '<PROJECT_ID>'
  AND (is_encrypted = FALSE OR is_encrypted IS NULL)

UNION ALL

SELECT
    'columns' as entity,
    COUNT(*) as unencrypted
FROM columns c
JOIN tables t ON c.table_id = t.id
WHERE t.project_id = '<PROJECT_ID>'
  AND (c.is_encrypted = FALSE OR c.is_encrypted IS NULL);
```

### Verificar Configuración de Cifrado
```sql
SELECT * FROM project_encryption WHERE project_id = '<PROJECT_ID>';
```

## ⚠️ Advertencias Importantes

1. **Guarda la Passphrase**: Sin ella, los datos son IRRECUPERABLES
2. **Backup Primero**: Haz un backup de la BD antes de cifrar datos masivos
3. **Sesión Activa**: Para ver datos cifrados en la UI necesitas una sesión activa (ingresa la passphrase cuando lo pida)
4. **Rendimiento**: Cifrar muchos datos puede tardar varios minutos
5. **Rollback**: No hay rollback automático. El backup es tu única opción de recuperación

## 🚀 Ejemplo Completo

```bash
# 1. Ir al directorio backend
cd c:\Users\guill\Desktop\Proyecto Relan\dev\backend

# 2. Activar entorno virtual (si usas uno)
# .venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Ejecutar dry-run para ver qué se haría
python utilities/encrypt_existing_data.py \
    --project-id 238ef9be-244f-49e8-a861-3cb7e3e56109 \
    --dry-run

# 4. Si todo se ve bien, ejecutar realmente
python utilities/encrypt_existing_data.py \
    --project-id 238ef9be-244f-49e8-a861-3cb7e3e56109

# Te pedirá la passphrase:
# 🔑 Passphrase: **************

# 5. Ver resumen:
# ✅ Tablas cifradas: 5
# ✅ Columnas cifradas: 23
# ✅ Mappings cifrados: 8
# ...
```

## ❓ FAQ

**P: ¿Por qué veo datos en texto plano en la BD después de activar el cifrado?**
R: Porque solo activaste la CONFIGURACIÓN de cifrado. Los datos existentes no se cifran automáticamente. Necesitas ejecutar el script `encrypt_existing_data.py`.

**P: ¿Los nuevos datos se cifrarán automáticamente?**
R: Sí, después de activar el cifrado, todos los nuevos datos se cifrarán automáticamente.

**P: ¿Puedo ver los datos cifrados en la UI?**
R: Sí, pero necesitas una sesión activa. La UI te pedirá la passphrase cuando accedas al proyecto.

**P: ¿Qué pasa si olvido la passphrase?**
R: Los datos son IRRECUPERABLES. No hay forma de recuperarlos sin la passphrase. Por eso es crítico guardarla en un lugar seguro.

**P: ¿Puedo cambiar la passphrase después?**
R: Sí, usa el endpoint `/api/projects/{id}/encryption/rotate-key`, pero esto re-cifra TODOS los datos, lo que puede tardar mucho tiempo.

## 📞 Soporte

Si tienes problemas:
1. Verifica que la passphrase sea correcta
2. Verifica que el proyecto tenga cifrado habilitado en la UI
3. Revisa los logs del script para ver errores específicos
4. Haz un dry-run primero para detectar problemas sin hacer cambios
