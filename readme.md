# DataMap — Asistente de migración de bases de datos

[![PR Checks](https://github.com/guillesanper/datamaper-migration-assistant/actions/workflows/pr-checks.yml/badge.svg)](https://github.com/guillesanper/datamaper-migration-assistant/actions/workflows/pr-checks.yml)
[![Main CI/CD](https://github.com/guillesanper/datamaper-migration-assistant/actions/workflows/main.yml/badge.svg)](https://github.com/guillesanper/datamaper-migration-assistant/actions/workflows/main.yml)

Plataforma web para planificar y generar migraciones entre bases de datos relacionales. DataMap
inspecciona esquemas de **PostgreSQL, MySQL, SQL Server y Oracle** a través de sus catálogos,
permite mapear tablas y columnas de origen a destino en una interfaz de grafo y genera los scripts
`INSERT INTO ... SELECT` de la migración. El orden de ejecución sale de un orden topológico sobre el
grafo de claves foráneas, que falla de forma explícita si encuentra ciclos.

**Stack:** FastAPI · Python 3.11 · PostgreSQL · Redis · React 19 · TypeScript · Vite · Astro · Docker · GitHub Actions

## ✨ Funcionalidades principales

- **Conectores a BD externas** con TLS verificado por defecto, CA propia por conexión y credenciales
  que no se persisten en claro.
- **Introspección de esquemas** (tablas, columnas, claves primarias y foráneas) y mapeo visual
  origen → destino.
- **Generación de scripts de migración** ordenados por dependencias de claves foráneas.
- **Colaboración en tiempo real**: proyectos compartidos, comentarios, bloqueos de edición,
  notificaciones e historial de versiones.
- **Seguridad**: sesiones en cookies `HttpOnly`, protección CSRF, verificación de email por OTP,
  límites de peticiones por IP y por cuenta, cifrado AES-256-GCM con claves derivadas con Argon2id
  y registro de eventos de seguridad.
- **Calidad**: tests unitarios, de integración y end-to-end con pytest, linters y type checking en
  cada Pull Request, escaneo de dependencias e imagen Docker con Trivy.

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

Servicios que levanta [`docker-compose.yml`](docker-compose.yml):

| Servicio | Contenedor | Puerto en el host | Uso |
|----------|------------|-------------------|-----|
| backend | `datamap-backend` | 8000 | API FastAPI con hot reload |
| postgres | `datamap-postgres` | 5432 | Base de datos |
| redis | `datamap-redis` | 6379 | Caché de sesiones |
| mailpit | `datamap-mailpit` | 8025 (web), 1025 (SMTP) | Servidor SMTP de **desarrollo**, solo en `127.0.0.1` |

#### Correos de verificación en desarrollo (Mailpit)

En desarrollo el backend envía los correos a Mailpit, que no los reenvía a ningún buzón real: se leen en **http://localhost:8025**.

1. `docker-compose up -d`
2. Registrar un usuario (`POST /api/auth/register`, o desde el frontend).
3. Abrir http://localhost:8025 y copiar el código de 8 caracteres del correo «Tu código de verificación» (válido 10 minutos).
4. Introducirlo en la verificación (`POST /api/auth/verify-code`).

Cosas a tener en cuenta:

- Los correos son **efímeros**: Mailpit no tiene volumen y los pierde al parar, reiniciar o recrear el contenedor.
- El correo se entrega **en segundo plano**: el `201` del registro no garantiza que haya salido; el resultado del envío aparece en el log del backend unos segundos después.
- Si el envío falla (Mailpit parado, SMTP mal configurado) el registro no falla, pero el código solo aparece en el log del backend: `docker logs datamap-backend` (línea «Código de verificación para …»). Esto ocurre **solo con `ENV=development`** (lo que usa el compose): fuera de desarrollo el código no se imprime nunca.
- Un reenvío (`POST /api/auth/resend-code`) sustituye al código anterior y solo envía a cuentas sin verificar. El código de recuperación de contraseña se pide con `POST /api/auth/forgot` (API: el frontend aún no tiene pantalla) y se usa en `POST /api/auth/reset`.
- Cada código admite 5 comprobaciones erróneas (`OTP_MAX_ATTEMPTS`); al llegar se invalida y hay que pedir otro. Las rutas de autenticación tienen límite de peticiones (429 con `Retry-After`): en desarrollo es permisivo; valores y variables en [Autenticación: límites y variables](#autenticación-límites-y-variables).
- Mailpit solo es para desarrollo; en producción se usa un SMTP real (ver [`backend/docs/DEPLOYMENT_GUIDE.md`](backend/docs/DEPLOYMENT_GUIDE.md)).

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

Los conectores a bases de datos externas (PostgreSQL, MySQL, SQL Server, Oracle) exigen TLS y verifican el certificado del servidor por defecto; se puede subir una CA propia por conexión, y desactivar la verificación es un opt-out que exige confirmar el hostname y deja la conexión marcada como «Sin verificar». Ver [`backend/app/utils/db_adapters/README.md`](backend/app/utils/db_adapters/README.md#-tls-y-verificación-del-certificado).

En desarrollo con Docker Compose, el backend también envía los correos (códigos de verificación) a Mailpit (SMTP `:1025`, interfaz web `:8025`).

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

El pipeline de `main` está preparado para desplegar en Render.com (backend, frontend y landing);
la configuración está en [`backend/render.yaml`](backend/render.yaml).

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
SECRET_KEY=your-secret-key            # obligatorio fuera de development (≥ 32 caracteres)
ENCRYPTION_ENABLED=true
# Cifra las credenciales de conexiones a BDs externas: base64 de 32 bytes aleatorios
# python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
ENCRYPTION_MASTER_KEY=

# Seguridad HTTP
CORS_ALLOWED_ORIGINS=https://app.tudominio.com   # orígenes del frontend, separados por comas

# External Services
STRIPE_SECRET_KEY=your-stripe-key

# Email (desarrollo: Mailpit, ver «Correos de verificación en desarrollo»)
EMAIL_FROM=no-reply@datamap.local
# Con el backend fuera de Docker: SMTP_SERVER=localhost
SMTP_SERVER=mailpit
SMTP_PORT=1025
SMTP_USER=
SMTP_PASS=
SMTP_USE_STARTTLS=false
```

Con Docker Compose basta con no definir las variables `SMTP_*`: el compose ya usa `mailpit:1025` (no pongas `SMTP_SERVER=localhost` en el `.env` que lee el compose, porque dentro del contenedor `localhost` es el propio backend). Con el backend fuera de Docker, levanta solo Mailpit (`docker-compose up -d mailpit`) y exporta `SMTP_SERVER=localhost` en tu shell: `load_dotenv` no pisa las variables ya definidas.

Para un SMTP real (Gmail o ProtonMail con contraseña de aplicación) usa `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASS` y **`SMTP_USE_STARTTLS=true`**: el valor por defecto del compose es `false`. Los detalles están en [`.env.example`](.env.example) y en [`backend/docs/DEPLOYMENT_GUIDE.md`](backend/docs/DEPLOYMENT_GUIDE.md).

### Autenticación: límites y variables

Valores por defecto del código (todas opcionales; la tabla completa, la lectura de los logs y el troubleshooting están en [`backend/docs/DEPLOYMENT_GUIDE.md`](backend/docs/DEPLOYMENT_GUIDE.md#autenticación-límites-intentos-y-respuestas)):

| Variable | Por defecto | Efecto |
|----------|-------------|--------|
| `ENV` | sin definir = producción | Solo `development`/`dev`/`debug` activan el modo desarrollo (límites permisivos, OTP en el log si el envío falla) |
| `SESSION_LIFETIME_HOURS` | `24` | Vigencia de la sesión y de su cookie |
| `OTP_MAX_ATTEMPTS` | `5` | Comprobaciones erróneas por código |
| `TRUSTED_PROXY_HOPS` | `0` | Proxies de confianza delante de la app: IP del cliente = entrada N-ésima desde la derecha de `X-Forwarded-For` (con `0`, la IP del socket) |
| `RATE_LIMIT_<RUTA>_ATTEMPTS` / `_WINDOW` (s) | `LOGIN` 5/900, `REGISTER` 3/3600, `VERIFY` 10/3600, `RESEND` 3/600, `RESET` 5/3600, `FORGOT` 3/3600 | Límite por IP y por ruta; `register`, `resend-code` y `forgot` cuentan además por email. En `login` cuentan solo los **fallos** de credenciales (los logins correctos, el 423 y el 403 no) |

> ⚠️ **Despliegue**: `TRUSTED_PROXY_HOPS` no está en `backend/render.yaml` y su valor correcto **no se ha medido** (aún no hay despliegue). Con `0` detrás de un proxy todos los usuarios comparten IP y los límites por IP bloquean el sitio entero tras unos pocos intentos (5 logins fallidos en 15 minutos entre todos). La aplicación lo avisa (al arrancar en Render con `0` y con una línea de log `TRUSTED_PROXY_HOPS=0 pero llegan peticiones con X-Forwarded-For`, enmascarada y una vez por worker) y esa línea sirve para calibrarlo: el procedimiento está en la [guía](backend/docs/DEPLOYMENT_GUIDE.md#trusted_proxy_hops). Ante la duda, un valor menor es lo seguro: uno mayor que los proxies reales permite suplantar la IP.

Respuestas: `verify-code` y `reset` devuelven siempre `400 «Código inválido o expirado»`, y `resend-code` / `forgot` un `200` idéntico exista o no la cuenta (el motivo real queda en `security_logs`). `register` responde `201` con el mismo cuerpo exista o no una cuenta con ese email (a quien ya la tiene le llega un aviso «Ya tienes una cuenta», o un código nuevo si no la había verificado); solo el `409 username_taken` por un username ocupado es explícito. Riesgos residuales (enumeración de usernames y pre-secuestro de una cuenta sin verificar): ver la [guía](backend/docs/DEPLOYMENT_GUIDE.md#riesgos-residuales-decisiones-explícitas-no-defectos-pendientes-de-arreglar-en-esta-fase).

La migración `0003` (`email_otps.failed_attempts`) la aplica el compose al arrancar el backend; si la BD de desarrollo sigue en `0002`: `docker-compose exec backend alembic upgrade head`.

### Conectores a BDs externas: variables

| Variable | Por defecto | Efecto |
|----------|-------------|--------|
| `DB_CONNECTOR_ALLOW_PRIVATE_HOSTS` | `true` solo en development | Permite conectar a hosts que resuelven a IPs privadas, loopback o link-local; fuera de desarrollo solo IPs públicas (protección SSRF) |
| `DB_CONNECTOR_ALLOWED_NETWORKS` | vacío | Redes CIDR internas permitidas explícitamente, separadas por comas (ej. `10.20.0.0/16`) |
| `DB_CONNECTOR_RATE_LIMIT` / `DB_CONNECTOR_RATE_WINDOW_SECONDS` | `10` / `60` | Intentos de conexión (test y creación de sesión) por usuario y ventana |

Una sesión de conexión creada con `project_id` solo se puede usar desde ese proyecto (para los demás no existe: 404).

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

Guía de contribución, convenciones de código y flujo de ramas en [`CONTRIBUTING.md`](CONTRIBUTING.md).

## 👤 Autor

Guillermo Sánchez — [GitHub](https://github.com/guillesanper) · [Web](https://guillesanper.github.io)
