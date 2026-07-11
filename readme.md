# DataMap - Platform

[![PR Checks](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/pr-checks.yml/badge.svg)](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/pr-checks.yml)
[![Main CI/CD](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/main.yml/badge.svg)](https://github.com/YOUR-USERNAME/YOUR-REPO/actions/workflows/main.yml)
[![codecov](https://codecov.io/gh/YOUR-USERNAME/YOUR-REPO/branch/main/graph/badge.svg)](https://codecov.io/gh/YOUR-USERNAME/YOUR-REPO)

Plataforma de mapeo y transformación de datos con backend FastAPI y frontend React.

## 🚀 Quick Start

### Desarrollo Local

```bash
# Instalar todas las dependencias
make install

# Lanzar backend (con hot reload)
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Lanzar frontend (en otra terminal)
cd frontend
npm run dev

# Lanzar landing (opcional)
cd landing
npm run dev
```

### Docker (Desarrollo)

```bash
# Iniciar todos los servicios
docker-compose up -d

# Ver logs
docker-compose logs -f

# Detener servicios
docker-compose down
```

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────┐
│  Frontend (React + Vite + TypeScript)   │
│  http://localhost:5173                  │
└──────────────┬──────────────────────────┘
               │ API calls
               ▼
┌─────────────────────────────────────────┐
│  Backend (FastAPI + Python 3.11)        │
│  http://localhost:8000                  │
└──────────┬─────────────┬────────────────┘
           │             │
           ▼             ▼
    ┌──────────┐   ┌──────────┐
    │PostgreSQL│   │  Redis   │
    │  :5432   │   │  :6379   │
    └──────────┘   └──────────┘
```

## 🧪 Testing

```bash
# Run all tests
make test

# Backend tests only
make test-backend

# Run tests with coverage
cd backend
pytest --cov=app --cov-report=html

# Run specific test markers
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m e2e          # End-to-end tests
```

## 🔍 Linting & Formatting

```bash
# Check linting
make lint

# Auto-format code
make format

# Backend specific
make lint-backend
make format-backend

# Frontend specific
make lint-frontend
make format-frontend
```

## 🔄 CI/CD Pipeline

Este proyecto utiliza GitHub Actions para CI/CD:

### PR Workflow (`.github/workflows/pr-checks.yml`)
Se ejecuta en cada Pull Request:
- ✅ Linting (flake8, ESLint)
- ✅ Type checking (mypy, TypeScript)
- ✅ Tests (pytest con coverage)
- ✅ Security scanning (safety, npm audit)
- ✅ Build validation (Docker, frontend, landing)
- ⚡ Path filtering para optimizar tiempos

### Main Workflow (`.github/workflows/main.yml`)
Se ejecuta en cada push a `main`:
- ✅ Full test suite con coverage
- ✅ Docker build & push a GitHub Container Registry
- ✅ Security scan con Trivy
- ✅ Validación de builds (frontend + landing)
- 🚀 Auto-deploy a Render.com

### E2E Workflow (`.github/workflows/e2e.yml`)
Se ejecuta diariamente a las 2 AM UTC:
- ✅ Tests end-to-end con docker-compose
- ✅ Validación de todas las integraciones

### Dependabot
Actualiza dependencias automáticamente cada lunes:
- 📦 Backend (pip)
- 📦 Frontend (npm)
- 📦 Landing (npm)
- 📦 GitHub Actions

## 📦 Deployment

### Render.com (Producción)

El proyecto se despliega automáticamente en Render.com desde la rama `main`:

- **Backend**: https://datamap-backend.onrender.com
- **Frontend**: https://datamap-frontend.onrender.com
- **Landing**: https://datamap-landing.onrender.com

La configuración está en [`backend/render.yaml`](backend/render.yaml).

### Despliegue Manual

```bash
# Build Docker image
make docker-build

# Run E2E tests with docker-compose
make docker-test
```

## 🛠️ Stack Tecnológico

### Backend
- **Framework**: FastAPI 0.116.1
- **Language**: Python 3.11
- **Database**: PostgreSQL 17
- **Cache**: Redis 7
- **Server**: Uvicorn + Gunicorn
- **Testing**: pytest, pytest-asyncio, pytest-cov

### Frontend
- **Framework**: React 19.1.1
- **Language**: TypeScript 5.9.3
- **Build Tool**: Vite 7.1.7
- **UI**: Radix UI, Tailwind CSS 4.1.14
- **State**: TanStack Query, React Context
- **Routing**: React Router DOM 7.9.4

### Landing
- **Framework**: Astro 5.14.7
- **Styling**: Tailwind CSS 4.1.15

### DevOps
- **CI/CD**: GitHub Actions
- **Container Registry**: GitHub Container Registry (GHCR)
- **Deployment**: Render.com
- **Security**: Trivy, Safety, npm audit
- **Coverage**: Codecov

## 📝 Scripts Disponibles

### Makefile Commands

```bash
make help          # Mostrar ayuda
make install       # Instalar dependencias
make test          # Ejecutar tests
make lint          # Ejecutar linters
make format        # Formatear código
make ci-local      # Ejecutar CI localmente (requiere act)
make clean         # Limpiar artefactos
make docker-build  # Build Docker image
make docker-test   # Ejecutar E2E con docker
```

## 🔒 Pre-commit Hooks

El proyecto usa pre-commit hooks para validar código antes de commits:

```bash
# Instalar hooks
pip install pre-commit
pre-commit install

# Ejecutar manualmente
pre-commit run --all-files
```

Hooks configurados:
- ✅ black (formatting)
- ✅ isort (import sorting)
- ✅ flake8 (linting)
- ✅ ESLint (frontend linting)
- ✅ TypeScript check
- ✅ Trailing whitespace
- ✅ Secrets detection

## 🌍 Variables de Entorno

### Backend (`.env`)
```env
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=datamap_dev
DB_USER=datamaper_user_local
DB_PASSWORD=DataMap1234

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_SSL=false

# App
ENV=development
SECRET_KEY=your-secret-key
ENCRYPTION_ENABLED=true

# External Services
STRIPE_SECRET_KEY=your-stripe-key
EMAIL_FROM=your-email@example.com
```

### Frontend (`.env`)
```env
VITE_API_URL=http://localhost:8000
DEV=true
```

## 📊 Coverage Reports

Los reportes de cobertura se generan automáticamente en CI y se suben a Codecov.

Ver localmente:
```bash
cd backend
pytest --cov=app --cov-report=html
# Abrir: backend/htmlcov/index.html
```

## 🤝 Contributing

1. Crear una feature branch: `git checkout -b feature/amazing-feature`
2. Hacer commits: `git commit -m 'Add amazing feature'`
3. Push a la branch: `git push origin feature/amazing-feature`
4. Abrir un Pull Request
5. Esperar que pasen los checks de CI
6. Obtener code review y merge

## 📄 License

[Tu licencia aquí]

## 👥 Team

[Tu equipo aquí]

---

**Nota**: Reemplaza `YOUR-USERNAME` y `YOUR-REPO` en los badges con tus valores reales de GitHub.
