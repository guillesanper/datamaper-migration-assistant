# Plan: Migración a SQLAlchemy + Alembic

## Análisis del Problema Actual

### Flujo Actual Identificado

**Migraciones de Esquema:**
- Archivos SQL numerados en [backend/utilities/migrations/](../utilities/migrations/)
- Ejecución manual vía `psql` o scripts Python individuales
- Tracking en tablas `migration_audit_log` y `migration_scripts`/`migration_executions`
- Sistema de rollback disponible

**Base de Datos Principal:**
- PostgreSQL con psycopg2
- Schema definido en [backend/utilities/schema.sql](../utilities/schema.sql)
- Migraciones se aplican incrementalmente sobre la BD principal

**Base de Datos de Testing:**
- Se crea automáticamente por worker (datamap_test_gw0, datamap_test_gw1, etc.)
- Schema aplicado desde [backend/init-db/01_schema.sql](../init-db/01_schema.sql) (NO desde migraciones)
- Script de setup: [backend/scripts/setup_test_db.py](../scripts/setup_test_db.py)

### Problemas Identificados

1. **Desincronización entre BD principal y BD de testing:**
   - BD principal: schema base + migraciones incrementales
   - BD testing: schema.sql estático que debe actualizarse MANUALMENTE
   - Cuando haces una nueva migración, tienes que actualizar MANUALMENTE dos archivos

2. **Proceso manual y propenso a errores:**
   - Aplicar migración en BD principal
   - Recordar actualizar el schema.sql de testing
   - Mantener ambos sincronizados es tedioso

3. **Falta de automatización:**
   - No hay script único que aplique migraciones
   - Cada migración requiere su propio runner script o ejecución manual

## Decisión del Usuario

✅ **Opción Seleccionada: SQLAlchemy + Alembic (Migración Gradual)**

Basado en:
- Migraciones frecuentes (varias veces por semana)
- Prioridad: Automatización y conveniencia
- Dispuesto a invertir tiempo en refactorización

---

# Plan de Implementación

## Estrategia: Migración Gradual con Coexistencia

Durante la transición, psycopg2 y SQLAlchemy coexistirán usando la misma base de datos:
- **Código legacy**: Seguirá usando `get_db()` → psycopg2
- **Código nuevo/migrado**: Usará `get_db_session()` → SQLAlchemy
- **Sin riesgo**: Ambos comparten la misma base de datos PostgreSQL

## Fases de Implementación

### 📦 Fase 1: Fundación (Semana 1)

**Objetivo**: Configurar Alembic y SQLAlchemy sin romper código existente

**Tareas**:

1. ✅ **Instalar dependencias**
   - Agregadas a [backend/requirements.txt](../requirements.txt):
     - `sqlalchemy==2.0.35`
     - `alembic==1.13.1`

2. **Crear estructura de directorios**
   ```
   backend/
   ├── alembic/                    # Nuevo
   │   ├── env.py
   │   ├── script.py.mako
   │   └── versions/
   ├── alembic.ini                 # Nuevo
   └── app/
       ├── database/
       │   ├── database.py         # Existente (mantener)
       │   ├── base.py             # Nuevo - Declarative Base
       │   └── session.py          # Nuevo - Session factory
       └── models/
           ├── db_metadata/        # Existente (mantener Pydantic)
           └── orm/                # Nuevo - SQLAlchemy models
               ├── __init__.py
               ├── user.py
               ├── project.py
               ├── table.py
               └── ...
   ```

3. **Configurar Alembic**:
   - Ejecutar `alembic init alembic` desde directorio `backend/`
   - Configurar `alembic.ini`
   - Configurar `alembic/env.py` para cargar modelos ORM

4. **Crear modelos ORM iniciales**:
   - User, Project, Table, Column

5. **Crear migración baseline**:
   - `alembic revision -m "baseline_schema"`
   - Incluir estado actual (schema.sql + migraciones 001-006)
   - **NO aplicar**, solo crear el archivo

### 🧪 Fase 2: Infraestructura de Testing (Semana 1-2)

**Objetivo**: ✅ **RESOLVER PROBLEMA PRINCIPAL** - Sincronización automática de BD de testing

**Tareas**:

1. **Modificar script de setup de testing** ([backend/scripts/setup_test_db.py](../scripts/setup_test_db.py))
   - Reemplazar aplicación de schema.sql con `alembic upgrade head`

2. **Modificar fixtures de testing** ([backend/test/conftest.py](../test/conftest.py))
   - Función `create_worker_database()` usar Alembic

3. **Eliminar/archivar schema estático**:
   - [backend/init-db/01_schema.sql](../init-db/01_schema.sql) → Ya no se necesita

4. **Validar**:
   - `python backend/scripts/setup_test_db.py`
   - `pytest backend/test/`
   - `pytest -n auto`

**Beneficio inmediato**: 🎉 BD de testing sincronizada automáticamente con migraciones de Alembic

### 🔄 Fase 3: Migración Incremental de CRUDs (Semanas 2-6)

**Estrategia**: Migrar 2-3 módulos CRUD por semana

**Orden recomendado**:

**Semana 2-3: Módulos simples**
- subscription_crud.py
- pk_crud.py
- activity_crud.py

**Semana 3-4: Módulos core**
- project_crud.py
- tags_crud.py
- locks_crud.py

**Semana 5: Módulos con encriptación**
- schemas_crud.py
- mappings_crud.py

**Semana 6: Módulos avanzados**
- versions_crud.py
- comments_crud.py
- reactions_crud.py

**Patrón por cada CRUD**:
1. Crear modelos ORM correspondientes
2. Reescribir funciones CRUD usando SQLAlchemy
3. Actualizar rutas para usar `Depends(get_db_session)`
4. Ejecutar tests específicos del módulo
5. Commit

### 🧹 Fase 4: Cleanup (Semana 7+)

**Tareas**:
1. Remover código psycopg2
2. Renombrar `get_db_session()` → `get_db()`
3. Archivar migraciones SQL antiguas
4. Actualizar documentación
5. Revisión final de código

---

## Workflow de Migraciones Futuras

**Antes (actual)** 😫:
1. Escribir migración SQL manualmente
2. Ejecutar `psql -f 00X_nombre.sql`
3. **MANUALMENTE** actualizar schema de testing
4. Recordar aplicar en BD de testing
5. Propenso a errores

**Después (con Alembic)** 😊:
1. Modificar modelos ORM en `app/models/orm/`
2. `alembic revision --autogenerate -m "descripción"`
3. Revisar migración generada
4. `alembic upgrade head`
5. ✅ **BD de testing se actualiza automáticamente**
6. Sin trabajo manual adicional

---

## Archivos Críticos para Implementar

1. **backend/app/database/session.py** - Core SQLAlchemy session factory
2. **backend/app/database/base.py** - Declarative Base para modelos
3. **backend/alembic/env.py** - Configuración Alembic
4. **backend/test/conftest.py** - Modificar para usar Alembic (⚠️ RESUELVE PROBLEMA PRINCIPAL)
5. **backend/app/models/orm/project.py** - Modelo ORM de referencia

---

## Manejo de Casos Especiales

### Encriptación (AES-256-GCM)

Los campos encriptados se manejan en la capa de servicio, no en ORM:

```python
# Modelo ORM incluye ambos campos:
class Table(Base):
    __tablename__ = "tables"
    name = Column(String(255))              # Plaintext (nullable)
    name_encrypted = Column(Text)            # Encrypted
    name_nonce = Column(Text)                # Nonce
    is_encrypted = Column(Boolean)

# Lógica de encriptación en CRUD/Service (sin cambios):
if encryption_enabled:
    name_enc, nonce = encrypt_table_name(name, key)
    table = Table(name=None, name_encrypted=name_enc, name_nonce=nonce, is_encrypted=True)
else:
    table = Table(name=name, is_encrypted=False)
```

### Queries Complejas

Para queries analíticas complejas, SQLAlchemy permite raw SQL:

```python
from sqlalchemy import text

result = db.execute(text("""
    SELECT p.*, COUNT(t.id) as table_count
    FROM projects p
    LEFT JOIN tables t ON t.project_id = p.id
    GROUP BY p.id
"""))
```

---

## Riesgos y Mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Performance degradation | Baja | Benchmarking, usar `.options(joinedload())` para N+1 queries |
| Breaking changes en rutas | Media | Retornar dicts desde CRUD (backward compatible), migrar gradualmente |
| Errores en autogeneración de Alembic | Media | Revisar SIEMPRE migraciones generadas antes de aplicar |
| Complejidad en encriptación | Media | Migrar CRUDs con encriptación al final, testing exhaustivo |
| Curva de aprendizaje del equipo | Media | Documentación interna, pair programming |

---

## Criterios de Éxito

✅ Fase 1 completa cuando:
- Alembic configurado y baseline migration creado
- Modelos ORM core creados
- `alembic upgrade head` funciona en BD de desarrollo

✅ Fase 2 completa cuando:
- Tests ejecutan sin tocar schema estático
- BD de testing usa `alembic upgrade head`
- Todos los tests existentes pasan

✅ Fase 3 completa cuando:
- Todos los ~13 CRUDs migrados a SQLAlchemy
- Todos los tests pasan
- Sin dependencias de psycopg2 en CRUDs

✅ Proyecto completo cuando:
- Código psycopg2 legacy removido
- Documentación actualizada
- Equipo entrenado en nuevos patrones
- **Migraciones futuras toman 1 comando en lugar de 3+ pasos manuales**

---

## Próximos Pasos

1. ✅ Instalar dependencias: `pip install -r requirements.txt`
2. Crear archivos base (base.py, session.py)
3. Inicializar Alembic
4. Crear modelos ORM
5. Crear migración baseline
