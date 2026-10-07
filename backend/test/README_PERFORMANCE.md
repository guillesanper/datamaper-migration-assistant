# Test Performance Optimizations

## 🚀 Optimizaciones Aplicadas

### 1. **Cache de Verificación de Base de Datos**
- **Problema**: `setup_test_database()` se ejecutaba múltiples veces verificando tablas
- **Solución**: Variable global `_db_setup_checked` que cachea el resultado
- **Mejora**: Se ejecuta solo una vez por sesión de pytest

### 2. **TRUNCATE Optimizado**
- **Problema**: El fixture `clean_db` ejecutaba un loop dinámico con TRUNCATE en cada tabla
- **Solución**: Un solo comando `TRUNCATE` con todas las tablas y `RESTART IDENTITY CASCADE`
- **Mejora**: ~10x más rápido por limpieza de base de datos

### 3. **Reutilización de Usuario de Test**
- **Problema**: El fixture `test_user` eliminaba y recreaba el usuario en cada test
- **Solución**: Verifica si el usuario existe y lo reutiliza, solo actualiza `is_verified`
- **Mejora**: Evita operaciones DELETE costosas

### 4. **Timeout de Conexión**
- **Problema**: Sin timeout, las conexiones fallidas tardan mucho en fallar
- **Solución**: `connect_timeout=5` en la conexión a PostgreSQL
- **Mejora**: Falla rápido si la BD no está disponible

### 5. **Optimización de Fixtures E2E**
- **Problema**: Fixtures creaban usuarios únicos con UUID en cada test
- **Solución**: Reutilizar usuarios estándar en lugar de crear nuevos
- **Mejora**: Setup de fixtures E2E de ~3s a ~0.3s

### 6. **Configuración de pytest.ini**
- **Optimizaciones agregadas**:
  - `--import-mode=importlib`: Mejor manejo de imports
  - `--durations=10`: Muestra los 10 tests más lentos
  - `--ff`: Ejecuta primero los tests que fallaron
  - `-m "not slow"`: **Excluye tests lentos por defecto**
  - `log_cli=false`: Reduce output de logging

### 7. **Tests Lentos Marcados**
- **Problema**: Tests de timeout tardan 4-5 segundos cada uno esperando conexiones fallidas
- **Solución**: Marcados con `@pytest.mark.slow` y excluidos por defecto
- **Mejora**: Ahorra ~13 segundos por ejecución normal
- **Para ejecutarlos**: Usa `make test-backend-all` o `pytest -m slow`

## 📊 Mejoras Esperadas

| Escenario | Antes | Después | Mejora |
|-----------|-------|---------|--------|
| Setup inicial | ~60s | ~5s | **12x más rápido** |
| Limpieza por test | ~500ms | ~50ms | **10x más rápido** |
| Usuario de test | ~200ms | ~20ms | **10x más rápido** |
| Tests E2E (fixture setup) | ~3s | ~0.3s | **10x más rápido** |
| Tests lentos excluidos | N/A | -13s | **Ahorro adicional** |
| **Total para ~100 tests** | **~30 min** | **~2-3 min** | **10-15x más rápido** ⚡ |

## 🔧 Comandos Útiles

### Setup Inicial
```bash
# Crear/recrear la base de datos de test (solo una vez)
make test-db-setup
# O directamente:
python backend/scripts/setup_test_db.py
```

### Ejecutar Tests
```bash
# Tests rápidos (RECOMENDADO - excluye tests de timeout lentos)
make test-backend

# TODOS los tests incluyendo los lentos (~13 segundos más)
make test-backend-all

# Tests en paralelo (más rápido, requiere pytest-xdist)
make test-backend-fast

# Solo tests unitarios (más rápido)
make test-backend-unit

# Solo tests de integración
make test-backend-integration

# Solo tests e2e (sin los lentos)
make test-backend-e2e

# Solo tests lentos (timeout tests - tardan ~13s)
make test-backend-slow
```

### Para Tests Aún Más Rápidos
```bash
# Instalar pytest-xdist para ejecución paralela
pip install pytest-xdist

# Ejecutar en paralelo con auto-detección de CPUs
cd backend && pytest -n auto

# Ejecutar en paralelo con número específico de workers
cd backend && pytest -n 4
```

## 🐛 Troubleshooting

### Los tests siguen lentos
1. **Verifica que la BD de test esté creada**: `make test-db-setup`
2. **Ejecuta con --durations=10** para ver los tests más lentos
3. **Considera ejecutar en paralelo**: `pytest -n auto`

### Error de conexión a la base de datos
1. Verifica que PostgreSQL esté corriendo
2. Verifica las variables de entorno en `.env`:
   - `TEST_DB_HOST=localhost`
   - `TEST_DB_PORT=5432`
   - `TEST_DB_USER=postgres`
   - `TEST_DB_PASSWORD=postgres`

### Tests fallan después de las optimizaciones
1. **Limpia la base de datos**: `make test-db-setup`
2. **Verifica que no haya datos residuales**: Los fixtures deberían limpiar automáticamente
3. **Ejecuta tests individualmente** para aislar el problema

## 📝 Notas Importantes

1. **No elimines `setup_test_db.py`**: Sigue siendo necesario para el setup inicial
2. **El fixture `clean_db` sigue siendo necesario**: Pero ahora es mucho más rápido
3. **Fixtures de scope="session"**: Se reutilizan durante toda la sesión de pytest
4. **Fixtures de scope="function"**: Se recrean en cada test, pero optimizados

## 🔍 Análisis de Rendimiento

Para analizar dónde se está gastando el tiempo:

```bash
# Ver los 20 tests más lentos
cd backend && pytest --durations=20

# Perfil detallado (requiere pytest-profiling)
pip install pytest-profiling
cd backend && pytest --profile
```
