# Contributing to DataMap

¡Gracias por tu interés en contribuir a DataMap! Este documento proporciona guías y mejores prácticas para contribuir al proyecto.

## 🚀 Getting Started

### 1. Configurar el Entorno de Desarrollo

```bash
# Clonar el repositorio
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git
cd YOUR-REPO

# Instalar todas las dependencias y pre-commit hooks
make install

# O manualmente:
cd backend && pip install -r requirements.txt
cd ../frontend && npm ci
cd ../landing && npm ci
pip install pre-commit && pre-commit install
```

### 2. Configurar Variables de Entorno

```bash
# Backend
cp backend/.env.example backend/.env
# Editar backend/.env con tus valores

# Frontend
cp frontend/.env.example frontend/.env
# Editar frontend/.env con tus valores
```

### 3. Iniciar los Servicios

```bash
# Con Docker (recomendado)
docker-compose up -d

# O manualmente:
# Terminal 1 - Backend
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 - Frontend
cd frontend
npm run dev
```

## 📋 Workflow de Contribución

### 1. Crear una Feature Branch

```bash
# Actualizar main
git checkout main
git pull origin main

# Crear feature branch
git checkout -b feature/nombre-descriptivo

# O para bugs:
git checkout -b fix/nombre-del-bug
```

### 2. Hacer Cambios

- Escribe código limpio y bien documentado
- Sigue las convenciones de estilo del proyecto
- Añade tests para nuevas funcionalidades
- Actualiza documentación si es necesario

### 3. Verificar Cambios Localmente

```bash
# Ejecutar linters
make lint

# Formatear código
make format

# Ejecutar tests
make test

# O ejecutar todo el CI localmente (requiere act)
make ci-local
```

### 4. Commit Changes

Los commits son validados por pre-commit hooks:

```bash
git add .
git commit -m "feat: descripción corta del cambio"
```

**Convenciones de commit** (seguimos Conventional Commits):

- `feat:` - Nueva funcionalidad
- `fix:` - Corrección de bug
- `docs:` - Solo cambios en documentación
- `style:` - Formateo, punto y coma faltante, etc.
- `refactor:` - Refactorización de código
- `test:` - Añadir o modificar tests
- `chore:` - Tareas de mantenimiento

Ejemplos:
```bash
git commit -m "feat: add user authentication endpoint"
git commit -m "fix: resolve database connection timeout"
git commit -m "docs: update API documentation"
git commit -m "test: add unit tests for mapping service"
```

### 5. Push y Crear Pull Request

```bash
git push origin feature/nombre-descriptivo
```

Luego ve a GitHub y crea un Pull Request:

1. Asegúrate de que todos los checks de CI pasen
2. Describe qué cambios realizaste y por qué
3. Vincula issues relacionados si aplica
4. Solicita review de al menos un miembro del equipo

## 🧪 Testing Guidelines

### Backend Testing

```bash
# Ejecutar todos los tests
cd backend
pytest

# Tests por categoría
pytest -m unit          # Tests unitarios
pytest -m integration   # Tests de integración
pytest -m e2e          # Tests end-to-end

# Con coverage
pytest --cov=app --cov-report=html

# Ver reporte de coverage
open htmlcov/index.html
```

**Escribir buenos tests:**

```python
# test/unit/test_example.py
import pytest

@pytest.mark.unit
def test_function_name():
    """Test description"""
    # Arrange
    input_data = {...}

    # Act
    result = function_to_test(input_data)

    # Assert
    assert result == expected_output
```

### Frontend Testing

*(Pendiente - actualmente no hay tests configurados)*

## 🎨 Estándares de Código

### Python (Backend)

- **Formateo**: Black con línea máxima de 100 caracteres
- **Import sorting**: isort con perfil "black"
- **Linting**: flake8
- **Type hints**: mypy (recomendado pero no obligatorio)

```python
# Ejemplo de código bien formateado
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


router = APIRouter()


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Retrieve a user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### TypeScript (Frontend)

- **Formateo**: ESLint con configuración del proyecto
- **Type safety**: TypeScript estricto
- **Naming**: camelCase para variables/funciones, PascalCase para componentes

```typescript
// Ejemplo de componente React
import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';

interface UserFormProps {
  onSubmit: (data: UserData) => void;
}

export const UserForm: React.FC<UserFormProps> = ({ onSubmit }) => {
  const [name, setName] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ name });
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* ... */}
    </form>
  );
};
```

## 🔒 Seguridad

### Secretos y Credenciales

- **NUNCA** commitear secretos, API keys, o contraseñas
- Usar variables de entorno para configuración sensible
- El pre-commit hook `detect-secrets` ayuda a prevenir esto

### Manejo de Datos Sensibles

- Sanitizar inputs del usuario
- Validar y escapar datos antes de usar en queries
- Seguir principios de OWASP Top 10

## 📝 Documentación

### Documentar Código

```python
# Backend - Docstrings
def process_mapping(mapping_id: int, data: dict) -> dict:
    """
    Process a data mapping transformation.

    Args:
        mapping_id: The ID of the mapping configuration
        data: The input data to transform

    Returns:
        The transformed data

    Raises:
        ValueError: If mapping_id is invalid
        TransformationError: If transformation fails
    """
    # Implementation
```

```typescript
// Frontend - JSDoc
/**
 * Fetch user data from the API
 * @param userId - The unique identifier of the user
 * @returns Promise resolving to user data
 * @throws {Error} If user not found or network error
 */
async function fetchUser(userId: string): Promise<User> {
  // Implementation
}
```

### Actualizar README

Si añades nuevas funcionalidades importantes, actualiza el README.md:
- Nuevos scripts/comandos
- Nuevas variables de entorno
- Cambios en la arquitectura

## 🚫 Anti-Patterns a Evitar

### Backend

❌ **NO hacer:**
```python
# Código sin tipo de retorno
def get_data(id):
    return db.query(Model).filter(Model.id == id).first()

# Query vulnerable a SQL injection
db.execute(f"SELECT * FROM users WHERE id = {user_id}")

# Contraseñas hardcodeadas
api_key = "sk_test_123456789"
```

✅ **SÍ hacer:**
```python
# Código con tipos
def get_data(id: int) -> Optional[Model]:
    return db.query(Model).filter(Model.id == id).first()

# Query seguro con ORM
db.query(User).filter(User.id == user_id).first()

# Usar variables de entorno
api_key = os.getenv("STRIPE_API_KEY")
```

### Frontend

❌ **NO hacer:**
```typescript
// Props sin tipo
const Component = (props) => { ... }

// Estado sin tipo inicial claro
const [data, setData] = useState();

// API URL hardcodeada
fetch('http://localhost:8000/api/users')
```

✅ **SÍ hacer:**
```typescript
// Props con tipo
interface ComponentProps {
  userId: string;
}
const Component: React.FC<ComponentProps> = ({ userId }) => { ... }

// Estado con tipo
const [data, setData] = useState<User | null>(null);

// API URL desde env
fetch(`${import.meta.env.VITE_API_URL}/api/users`)
```

## 🔄 CI/CD Process

### Checks Automáticos en PR

Cuando creas un Pull Request, GitHub Actions ejecuta:

1. **Linting**: flake8, black, isort, ESLint
2. **Type Checking**: mypy, TypeScript
3. **Tests**: pytest (unit + integration)
4. **Security**: safety check, npm audit
5. **Build**: Docker, frontend build

**Todos estos checks deben pasar antes de mergear.**

### Mergear a Main

1. Todos los checks de CI deben estar ✅
2. Al menos 1 aprobación de code review
3. Branch actualizada con main
4. No merge conflicts

Después del merge:
- CI ejecuta el pipeline completo
- Docker image se construye y se sube a GHCR
- Render.com auto-despliega automáticamente

## 🆘 Ayuda y Soporte

### Problemas Comunes

**Pre-commit hooks fallan:**
```bash
# Re-instalar hooks
pre-commit uninstall
pre-commit install
pre-commit run --all-files
```

**Tests fallan localmente pero no en CI:**
```bash
# Asegurar que las dependencias están actualizadas
cd backend
pip install -r requirements.txt --upgrade

# Limpiar cache
make clean
```

**Docker build falla:**
```bash
# Limpiar containers y volúmenes
docker-compose down -v
docker system prune -af
docker-compose up -d --build
```

### Contacto

- **Issues**: Abre un issue en GitHub para bugs o feature requests
- **Discusiones**: Usa GitHub Discussions para preguntas generales
- **Email**: [tu-email@example.com]

## 📜 Code of Conduct

- Sé respetuoso y profesional
- Valora la diversidad de opiniones
- Acepta críticas constructivas
- Enfócate en lo que es mejor para el proyecto

---

¡Gracias por contribuir a DataMap! 🎉
