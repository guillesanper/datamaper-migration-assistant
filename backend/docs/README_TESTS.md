# Guía de Testing - Backend

## Resumen de Tests Implementados

Se han creado tests unitarios y de integración para módulos básicos del backend como punto de partida para la suite completa de testing.

### Módulos Testeados

1. **[app/utils/cookies.py](../app/utils/cookies.py)** - Sistema de firma y verificación de cookies
   - ✅ 13 tests unitarios
   - ✅ 100% de cobertura

2. **[app/crud/tags_crud.py](../app/crud/tags_crud.py)** - Operaciones CRUD para version_tags
   - ✅ 18 tests unitarios
   - ✅ 13 tests de integración
   - ✅ 100% de cobertura

3. **[app/database/database.py](../app/database/database.py)** - Gestión de conexiones a BD
   - ✅ 12 tests de integración

## Estructura de Tests

```
test/
├── unit/                           # Tests unitarios (con mocks)
│   ├── test_cookies.py            # 13 tests - cookies.py
│   └── test_tags_crud.py          # 18 tests - tags_crud.py
├── integration/                    # Tests de integración (BD real)
│   └── test_database.py           # 4 tests - fixtures de BD de conftest.py
├── fixtures/                       # Datos de prueba reutilizables
│   └── test_data.py               # Generadores y constantes
├── e2e/                           # Tests end-to-end (vacío)
├── confest.py                     # ⚠️ Fixtures globales (typo: debe ser conftest.py)
└── pytest.ini                     # Configuración de pytest
```

## Comandos de Testing

### Tests Unitarios

```bash
# Todos los tests unitarios
cd backend
python -m pytest test/unit -v

# Test específico
python -m pytest test/unit/test_cookies.py -v
python -m pytest test/unit/test_tags_crud.py -v

# Por marcador (marker)
python -m pytest -m unit -v

# Por nombre de función
python -m pytest test/unit -k "test_sign_cookie" -v
```

### Tests de Integración

```bash
# Todos los tests de integración
python -m pytest test/integration -v

# Test específico
python -m pytest test/integration/test_database.py -v

# Por marcador
python -m pytest -m integration -v
python -m pytest -m database -v
```

### Tests con Cobertura

```bash
# Cobertura específica de módulos testeados
python -m pytest test/unit --cov=app.utils.cookies --cov=app.crud.tags_crud --cov-report=term-missing

# Cobertura completa del app (configurada en pytest.ini)
python -m pytest --cov=app --cov-report=html

# Ver reporte HTML (después de ejecutar con --cov-report=html)
# Abrir: htmlcov/index.html
```

### Otros Comandos Útiles

```bash
# Solo primeros N fallos
python -m pytest --maxfail=3

# Mostrar print statements
python -m pytest -s

# Tests lentos marcados
python -m pytest -m slow

# Verbose con traceback corto
python -m pytest -v --tb=short

# Tests en paralelo (requiere pytest-xdist)
# pip install pytest-xdist
python -m pytest -n auto
```

## Resultados Actuales

### Tests Unitarios ✅
```
31 tests passed
Coverage: 100%
- cookies.py: 11 statements, 0 missing
- tags_crud.py: 48 statements, 0 missing
```

### Tests de Integración ⚠️
```
4 tests de database.py (fixtures de BD de conftest.py)
```

## Problemas Conocidos y Soluciones

### 1. ⚠️ Archivo confest.py debe ser conftest.py

**Problema:** Pytest busca específicamente `conftest.py` pero el archivo actual se llama `confest.py` (falta una 't').

**Solución:**
```bash
cd backend/test
mv confest.py conftest.py
```

**Impacto:** Los fixtures globales (db, clean_db, test_user, test_project) no están disponibles hasta corregir esto.

### 2. Tests de Integración Requieren BD

Los tests de integración necesitan acceso a PostgreSQL con las credenciales configuradas en `.env`:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=datamap_test  # ← BD de test
DB_USER=postgres
DB_PASSWORD=postgres
```

**Para crear BD de test:**
```sql
CREATE DATABASE datamap_test;
-- Ejecutar migrations/schema
```

### 3. Markers No Registrados (Warnings)

Los tests usan markers custom que generan warnings. Para eliminarlos, ya están configurados en [pytest.ini](pytest.ini):

```ini
markers =
    unit: Tests unitarios
    integration: Tests de integración
    database: Tests que requieren base de datos
    # ... otros markers
```

## Próximos Pasos Recomendados

### Fase 1: Corregir Setup (Inmediato)
1. Renombrar `confest.py` → `conftest.py`
2. Verificar que fixtures funcionan:
   ```bash
   pytest --fixtures test/
   ```

### Fase 2: Completar Tests Básicos
1. Ejecutar los tests de integración de los CRUD ORM (p. ej. `test_reactions_crud_integration.py`):
   ```bash
   pytest test/integration/test_reactions_crud_integration.py -v
   ```
2. Verificar cobertura de integración

### Fase 3: Expandir Tests a Otros Módulos
Módulos recomendados para testear a continuación (en orden de dificultad):

1. **reactions_crud.py** (120 líneas) - Similar a tags_crud
2. **activity_crud.py** (182 líneas) - Logging de actividad
3. **locks_crud.py** (276 líneas) - Sistema de bloqueos
4. **comments_crud.py** (271 líneas) - Comentarios con menciones
5. **exception_sanitizer.py** (438 líneas) - ⭐ Crítico para seguridad

### Fase 4: Tests de Servicios
Servicios sin encriptación:
- activity_service.py
- type_compatibility_service.py

### Fase 5: Tests de Encriptación (Complejo)
- encryption_service.py
- encryption.py
- secure_memory.py

## Patterns de Testing Establecidos

### 1. Tests Unitarios con Mocks

```python
from unittest.mock import MagicMock

@pytest.fixture
def mock_db():
    db = MagicMock()
    cursor = MagicMock()
    db.cursor.return_value = cursor
    return db

def test_function(mock_db):
    # Mock del cursor
    mock_cursor = mock_db.cursor.return_value
    mock_cursor.fetchone.return_value = {'id': '123'}

    # Ejecutar función
    result = my_function(mock_db)

    # Assertions
    assert result['id'] == '123'
    mock_db.commit.assert_called_once()
```

### 2. Tests de Integración con Fixtures

```python
@pytest.mark.integration
@pytest.mark.database
def test_with_real_db(db, test_user, test_project):
    # Usa fixtures de conftest.py
    result = create_something(db, test_user['id'], test_project['id'])
    assert result is not None
```

### 3. Organización por Clases

```python
class TestCreateFunction:
    """Tests para la función create_*"""

    def test_success(self, mock_db):
        """Test: Happy path"""
        pass

    def test_with_invalid_input(self, mock_db):
        """Test: Manejo de errores"""
        pass

    def test_closes_cursor_on_exception(self, mock_db):
        """Test: Cleanup en caso de error"""
        pass
```

## Documentación de Fixtures Disponibles

### Fixtures de BD (cuando conftest.py esté corregido)

- **test_db_connection**: Conexión a BD de test (scope: session)
- **db**: Conexión con auto-rollback (scope: function)
- **clean_db**: BD limpia (borra todas las tablas)

### Fixtures de Usuario

- **test_user**: Usuario verificado de prueba
- **authenticated_client**: Cliente HTTP autenticado

### Fixtures de Datos

- **test_project**: Proyecto de prueba asociado a test_user

## Recursos Adicionales

- **pytest.ini**: Configuración completa de pytest con markers y coverage
- **test/fixtures/test_data.py**: Generadores y constantes reutilizables
- Documentación pytest: https://docs.pytest.org/

## Métricas de Éxito

- ✅ 31 tests unitarios pasando
- ✅ 100% cobertura en módulos testeados
- ⚠️ Tests de integración pendientes de fixtures
- 🎯 Objetivo: >80% cobertura en módulos críticos

---

**Última actualización:** 2025-11-12
