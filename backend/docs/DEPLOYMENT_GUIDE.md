# DataMap Backend - Deployment Guide

**Última actualización**: 2026-10-11
**Versión**: 2.0 (con Redis)

---

## 📋 Tabla de Contenidos

1. [Requisitos Previos](#requisitos-previos)
2. [Desarrollo Local](#desarrollo-local)
3. [Desarrollo con Docker Compose](#desarrollo-con-docker-compose)
4. [Staging/Testing](#stagingtesting)
5. [Producción en Render](#producción-en-render)
6. [Variables de Entorno](#variables-de-entorno)
7. [Troubleshooting](#troubleshooting)
8. [Monitoring y Logs](#monitoring-y-logs)

---

## 🔧 Requisitos Previos

### Software Necesario

| Herramienta | Versión | Propósito |
|-------------|---------|-----------|
| **Python** | 3.11+ | Runtime del backend |
| **PostgreSQL** | 15+ | Base de datos principal |
| **Redis** | 7+ | Session cache |
| **Docker** | 24+ | Containerización (opcional) |
| **Docker Compose** | 2.0+ | Orquestación local (opcional) |

### Servicios Externos

- **Stripe** - Payment gateway (test keys para desarrollo)
- **SMTP Server** - Email notifications (Gmail, Protonmail, etc.). En desarrollo con Docker Compose no hace falta: se usa Mailpit (ver [Correos de verificación en desarrollo](#7-correos-de-verificación-en-desarrollo-mailpit))

---

## 💻 Desarrollo Local

### Opción 1: Sin Docker (Más rápido para desarrollo)

#### 1. Instalar Dependencias

```bash
cd backend

# Crear virtual environment
python -m venv venv

# Activar
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

#### 2. Configurar PostgreSQL Local

```bash
# Conectar a PostgreSQL
psql -U postgres

# Crear base de datos
CREATE DATABASE datamap_dev;
CREATE USER datamaper_user_local WITH PASSWORD 'DataMap1234';
GRANT ALL PRIVILEGES ON DATABASE datamap_dev TO datamaper_user_local;
```

#### 3. Configurar Redis Local

**Windows** (usando WSL o Windows Subsystem for Linux):
```bash
wsl
sudo apt update
sudo apt install redis-server
redis-server --daemonize yes
```

**Linux/Mac**:
```bash
# Instalar Redis
# Ubuntu/Debian:
sudo apt install redis-server

# Mac:
brew install redis

# Iniciar
redis-server --daemonize yes
```

#### 4. Configurar Variables de Entorno

```bash
# Copiar template
cp .env.example .env

# Editar .env
nano .env
```

**Configuración mínima para desarrollo local**:
```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=datamap_dev
DB_USER=datamaper_user_local
DB_PASSWORD=DataMap1234

# Redis
REDIS_HOST=localhost  # ← Cambiar de "redis" a "localhost"
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_SSL=false

# App
SECRET_KEY=dev_secret_key_change_in_production
ENV=development
ENCRYPTION_ENABLED=true
```

**Correo (opcional)**: sin variables `SMTP_*` el backend no envía nada: simula el envío e imprime el código de verificación en la consola (`Código de verificación para <email>: <código>`). Esto ocurre **solo con `ENV=development`** (también `dev` o `debug`); con cualquier otro valor, o sin `ENV` (el valor por defecto es producción), el código no se imprime nunca y el fallo se registra sin él. Para ver los correos en una bandeja, levanta solo Mailpit y apunta el backend a él:

```bash
docker-compose up -d mailpit

# En el shell que arranca uvicorn (o en backend/.env)
export EMAIL_FROM=no-reply@datamap.local
export SMTP_SERVER=localhost   # NO "mailpit": ese nombre solo existe dentro de la red de Docker
export SMTP_PORT=1025
export SMTP_USE_STARTTLS=false
```

Los correos se leen en http://localhost:8025. Más detalles en [Correos de verificación en desarrollo](#7-correos-de-verificación-en-desarrollo-mailpit).

#### 5. Aplicar el esquema de la BD

```bash
# Crea/actualiza el esquema con Alembic
alembic upgrade head
```

#### 6. Iniciar Servidor

```bash
# Modo desarrollo con hot reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# O usando el script de inicio
chmod +x start.sh
./start.sh
```

#### 7. Verificar

```bash
# Health check
curl http://localhost:8000/health

# Redis stats
curl http://localhost:8000/api/encryption/debug/cache-stats

# Ver logs
tail -f logs/app.log  # Si logs están configurados
```

---

## 🐳 Desarrollo con Docker Compose

### Ventajas

- ✅ No necesitas instalar PostgreSQL ni Redis localmente
- ✅ Mismo entorno que producción
- ✅ Fácil de compartir con el equipo
- ✅ Networking automático entre servicios

### 1. Verificar Docker

```bash
docker --version
docker-compose --version
```

### 2. Configurar .env para Docker

```bash
# Copiar template
cp .env.example .env

# Editar para Docker Compose
nano .env
```

**Configuración para Docker Compose**:
```bash
# Database (usar nombres de servicio de Docker)
DB_HOST=postgres  # ← Nombre del servicio en docker-compose.yml
DB_PORT=5432
DB_NAME=datamap_dev
DB_USER=datamaper_user_local
DB_PASSWORD=DataMap1234

# Redis (usar nombre de servicio)
REDIS_HOST=redis  # ← Nombre del servicio en docker-compose.yml
REDIS_PORT=6379
REDIS_PASSWORD=  # Vacío para desarrollo
REDIS_SSL=false

# App
SECRET_KEY=dev_secret_key
ENV=development
ENCRYPTION_ENABLED=true
```

### 3. Levantar Servicios

```bash
# Construir imágenes y levantar servicios
docker-compose up -d

# Ver logs en tiempo real
docker-compose logs -f

# Ver logs solo del backend
docker-compose logs -f backend

# Ver estado de servicios
docker-compose ps
```

**Output esperado**:
```
NAME                    STATUS        PORTS
datamap-backend         Up            0.0.0.0:8000->8000/tcp
datamap-postgres        Up (healthy)  0.0.0.0:5432->5432/tcp
datamap-redis           Up (healthy)  0.0.0.0:6379->6379/tcp
datamap-mailpit         Up (healthy)  127.0.0.1:1025->1025/tcp, 127.0.0.1:8025->8025/tcp
```

### 4. Comandos Útiles

```bash
# Reiniciar un servicio
docker-compose restart backend

# Reconstruir imagen del backend
docker-compose build backend

# Ejecutar comando en contenedor
docker-compose exec backend python --version

# Ver logs de Redis
docker-compose exec redis redis-cli
> KEYS enc_session:*
> DBSIZE
> INFO

# Detener servicios (mantiene volúmenes)
docker-compose stop

# Detener y eliminar contenedores (mantiene volúmenes)
docker-compose down

# Eliminar TODO (contenedores + volúmenes + imágenes)
docker-compose down -v --rmi all
```

### 5. Hot Reload en Docker

El `docker-compose.yml` está configurado con volúmenes para hot reload:

```yaml
volumes:
  - ./backend:/app  # ← Código local montado en contenedor
```

**Beneficio**: Cambios en código Python se recargan automáticamente.

### 6. Debugging en Docker

```bash
# Entrar al contenedor del backend
docker-compose exec backend bash

# Dentro del contenedor:
python
>>> from app.utils.redis_client import get_redis_client
>>> redis = get_redis_client()
>>> redis.ping()
True
```

### 7. Correos de verificación en desarrollo (Mailpit)

`docker-compose.yml` incluye [Mailpit](https://mailpit.axllent.org/) (`axllent/mailpit:v1.31.4`, contenedor `datamap-mailpit`) como servidor SMTP de **desarrollo**. Recoge los correos con códigos de verificación que envía el backend (registro y reenvío de código) y los muestra en una interfaz web; no los entrega a ningún buzón real.

> ⚠️ **Mailpit es solo para desarrollo.** No cifra ni reenvía nada y acepta cualquier usuario y contraseña. En producción se usa un SMTP real (ver [Correo (SMTP) en producción](#correo-smtp-en-producción)).

**Flujo**:

```bash
# 1. Levantar los servicios (el backend espera a que Mailpit esté healthy)
docker-compose up -d

# 2. Registrar un usuario (o desde el frontend)
# POST http://localhost:8000/api/auth/register

# 3. Abrir http://localhost:8025 y copiar el código del correo
#    "Tu código de verificación" (8 caracteres alfanuméricos, válido 10 minutos)

# 4. Verificarlo
# POST http://localhost:8000/api/auth/verify-code
```

- Un reenvío (`POST /api/auth/resend-code`) **sustituye** al código anterior y le da otra tanda de intentos; `verify-code` consume el código. `resend-code` solo envía a cuentas **sin verificar**: a una cuenta ya verificada (o inexistente) responde igual y no manda nada.
- Reintentar `POST /api/auth/register` con el email de una cuenta **sin verificar** también emite un código nuevo (201 con el mismo cuerpo que un alta); con el de una cuenta **verificada** no llega ningún código, sino el aviso «Ya tienes una cuenta en DataMap Assistant» (ver [Respuestas uniformes](#respuestas-uniformes)).
- El código del reset (`POST /api/auth/reset`) se pide con `POST /api/auth/forgot` (solo cuentas verificadas). Respuestas, límites y variables: [Autenticación: límites, intentos y respuestas](#autenticación-límites-intentos-y-respuestas).
- API de Mailpit (útil en scripts): `curl http://localhost:8025/api/v1/messages`.

**Configuración** (valores por defecto del compose; todos se pueden sobrescribir en el `.env`):

| Variable | Valor por defecto | Significado |
|----------|-------------------|-------------|
| `EMAIL_FROM` | `no-reply@datamap.local` | Remitente |
| `SMTP_SERVER` | `mailpit` | Host SMTP (nombre del servicio en la red de Docker) |
| `SMTP_PORT` | `1025` | Puerto SMTP |
| `SMTP_USER` / `SMTP_PASS` | vacíos | Credenciales: ambas o ninguna (a medias se simula el envío) |
| `SMTP_USE_STARTTLS` | `false` | Mailpit no ofrece TLS. El valor por defecto del **código** es `true`: solo `0/false/no/off` lo desactivan |

**Limitaciones y detalles**:

- Los puertos `8025` (web) y `1025` (SMTP) se publican **solo en `127.0.0.1`**: la interfaz muestra los códigos de verificación y no debe exponerse a la red.
- Los correos son **efímeros**: sin volumen, se pierden al parar, reiniciar o recrear `datamap-mailpit` (`docker-compose stop/restart/up --force-recreate`). Guarda como máximo 500 mensajes (`MP_MAX_MESSAGES`).
- Las dos variables `MP_SMTP_AUTH_ACCEPT_ANY` y `MP_SMTP_AUTH_ALLOW_INSECURE` del compose van **juntas**: con solo la primera Mailpit no arranca.
- Si ya tienes un `.env` con un SMTP real, añade `SMTP_USE_STARTTLS=true`: el compose lo pone a `false` por defecto.
- Ejecutando el backend fuera de Docker, usa `SMTP_SERVER=localhost` (ver [Desarrollo Local](#4-configurar-variables-de-entorno)) y no lo dejes en un `.env` compartido con el compose: dentro del contenedor `localhost` es el propio backend.

---

## 🧪 Staging/Testing

### Configuración de Staging

```bash
# .env.staging
ENV=staging
DB_HOST=staging-db.internal
REDIS_URL=redis://staging-redis.internal:6379/0
REDIS_SSL=true
ENCRYPTION_ENABLED=true
SECURE_COOKIES=true

# Gunicorn para staging
WEB_CONCURRENCY=2
GUNICORN_TIMEOUT=120
```

### Iniciar en Staging

```bash
# Cargar variables de staging
export $(cat .env.staging | xargs)

# Iniciar con Gunicorn
sh start.sh
```

---

## 🚀 Producción en Render

### Arquitectura en Render

```
┌─────────────────────────────────────────┐
│           Render.com                    │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │   Web Service (datamap-backend)   │ │
│  │                                   │ │
│  │   - Docker runtime                │ │
│  │   - 2-4 workers (auto-scaling)    │ │
│  │   - Health checks                 │ │
│  │   - Auto-deploy on push           │ │
│  └─────────────┬─────────────────────┘ │
│                │                        │
│  ┌─────────────▼─────────────────────┐ │
│  │  Redis Service (datamap-redis)    │ │
│  │  - Plan: Starter ($7/mo)          │ │
│  │  - 25MB RAM, 10 connections       │ │
│  │  - Internal only (ipAllowList:[]) │ │
│  └───────────────────────────────────┘ │
│                                         │
│  External PostgreSQL (managed)          │
└─────────────────────────────────────────┘
```

### 1. Preparar Repositorio

```bash
# Asegurarse de que todos los archivos están en Git
git add .
git commit -m "Add Redis migration and deployment config"
git push origin main
```

### 2. Crear Servicio en Render

#### Opción A: Usando render.yaml (Recomendado)

1. **En Render Dashboard**:
   - Click en "New" → "Blueprint"
   - Conectar tu repositorio de GitHub
   - Render detecta `backend/render.yaml` automáticamente

2. **Render creará automáticamente**:
   - Web Service: `datamap-backend`
   - Redis Service: `datamap-redis`

3. **Configurar variables secretas** (en Dashboard):
   ```
   SECRET_KEY=<genera_una_clave_segura>
   DB_PASSWORD=<tu_password_de_postgresql>
   STRIPE_SECRET_KEY=<tu_stripe_key>
   SMTP_USER=<tu_smtp_usuario>
   SMTP_PASS=<tu_smtp_password>
   ```

#### Opción B: Manual

1. **Crear Redis Service**:
   - New → Redis
   - Name: `datamap-redis`
   - Plan: Starter ($7/mo)
   - maxmemoryPolicy: `allkeys-lru`
   - ipAllowList: Dejar vacío (solo interno)

2. **Crear Web Service**:
   - New → Web Service
   - Connect Repository
   - Runtime: Docker
   - Build Command: (automático con Dockerfile)
   - Start Command: `sh start.sh`

3. **Configurar Environment Variables** (ver sección Variables de Entorno)

### 3. Variables de Entorno en Render

**Críticas (configurar manualmente)**:
```bash
SECRET_KEY=<strong_random_key_64_chars>
DB_PASSWORD=<secure_postgresql_password>
STRIPE_SECRET_KEY=sk_live_...
SMTP_USER=<smtp_user>
SMTP_PASS=<app_password>
CSRF_SECRET_KEY=<another_random_key>
IP_HASH_SALT=<random_salt>
TRUSTED_PROXY_HOPS=<saltos_de_proxy_de_confianza>  # no está en render.yaml; sin él los límites por IP son globales (ver "Autenticación")
```

**Auto-configuradas por render.yaml**:
```bash
REDIS_URL=<auto_from_redis_service>
REDIS_SSL=true
ENV=production
ENCRYPTION_ENABLED=true
WEB_CONCURRENCY=2
```

### 4. Conectar Redis Internal

En `render.yaml`, ya está configurado:

```yaml
- key: REDIS_URL
  fromService:
    type: redis
    name: datamap-redis  # ← Debe coincidir con el nombre del servicio
    property: connectionString
```

Render inyectará automáticamente la URL interna: `rediss://red-xxxxx.internal:6379`

### 5. Deploy

```bash
# Push a main
git push origin main

# Render detecta el push y hace deploy automático
```

**Monitorear deploy**:
- Dashboard → datamap-backend → Logs
- Ver health checks
- Verificar Redis connection

### 6. Verificar Deployment

```bash
# Health check
curl https://your-app.onrender.com/health

# Redis stats (requiere autenticación)
curl https://your-app.onrender.com/api/encryption/debug/cache-stats \
  -H "Cookie: session=..."

# Verificar logs en Render Dashboard
```

### 7. Custom Domain (Opcional)

1. Dashboard → datamap-backend → Settings → Custom Domains
2. Agregar dominio: `api.yourdomain.com`
3. Configurar DNS:
   ```
   CNAME api.yourdomain.com → your-app.onrender.com
   ```
4. Render configurará SSL automáticamente (Let's Encrypt)

---

## 🔐 Variables de Entorno

### Desarrollo Local

Ver [.env.example](../.env.example) para lista completa.

**Mínimas requeridas**:
```bash
DB_HOST=localhost
DB_NAME=datamap_dev
DB_USER=datamaper_user_local
DB_PASSWORD=DataMap1234
SECRET_KEY=dev_key
REDIS_HOST=localhost
ENCRYPTION_ENABLED=true
```

### Producción

**Generación segura de secrets**:
```python
import secrets

# SECRET_KEY (64 chars)
secrets.token_urlsafe(48)

# CSRF_SECRET_KEY
secrets.token_urlsafe(48)

# IP_HASH_SALT
secrets.token_hex(32)
```

**Checklist de producción**:
- ✅ `SECRET_KEY` único y aleatorio
- ✅ `REDIS_URL` apuntando al servicio interno
- ✅ `REDIS_SSL=true`
- ✅ `ENV=production`
- ✅ `SECURE_COOKIES=true`
- ✅ Stripe keys de producción (si aplica)
- ✅ SMTP real con credenciales válidas (`SMTP_USER`, `SMTP_PASS`) y STARTTLS sin desactivar (ver [Correo (SMTP) en producción](#correo-smtp-en-producción))
- ✅ Un registro de prueba entrega el correo y no deja líneas «Código de verificación para …» en el log
- ✅ `TRUSTED_PROXY_HOPS` fijado al número de proxies de confianza delante de la app: con `0` (el valor por defecto) todos los usuarios detrás del proxy comparten IP y los límites por IP dejan de ser por usuario (ver [Autenticación](#autenticación-límites-intentos-y-respuestas))
- ✅ Migración `0003` aplicada (`alembic current` → `0003 (head)`); `render.yaml` ejecuta `alembic upgrade head` antes de gunicorn
- ✅ `DB_PASSWORD` fuerte

### Correo (SMTP) en producción

Mailpit **no se despliega en producción**. El backend necesita un SMTP real con STARTTLS y credenciales:

```bash
EMAIL_FROM=<remitente_autorizado_por_el_proveedor>
SMTP_SERVER=smtp.protonmail.ch   # o smtp.gmail.com, etc.
SMTP_PORT=587
SMTP_USER=<smtp_user>
SMTP_PASS=<app_password>         # secreto: solo en el panel del proveedor, nunca en Git
SMTP_USE_STARTTLS=true
```

- `backend/render.yaml` ya define `EMAIL_FROM`, `SMTP_SERVER` (`smtp.protonmail.ch`) y `SMTP_PORT` (`587`); `SMTP_USER` y `SMTP_PASS` son secretos que se rellenan en el Dashboard. `SMTP_USE_STARTTLS` no está en `render.yaml`: si no se define, el código usa `true`. No la pongas a `false` en producción (puedes fijarla a `true` en el Dashboard para dejarlo explícito).
- `SMTP_USER` y `SMTP_PASS` van **ambas o ninguna**. Con una sola (o sin `SMTP_SERVER`/`EMAIL_FROM`) el backend **simula** el envío: no manda ningún correo.
- Las operaciones SMTP tienen un timeout de 10 s (`SMTP_TIMEOUT_SECONDS`).
- Al arrancar fuera de desarrollo, si faltan `SMTP_SERVER` o `EMAIL_FROM`, el backend avisa: `SMTP_SERVER/EMAIL_FROM no configurados: los códigos de verificación no se entregarán`. Es un aviso, no impide arrancar (con credenciales a medias no avisa: solo se detecta al enviar).
- ⚠️ **El código OTP nunca se imprime fuera de desarrollo.** Si el envío falla (credenciales erróneas, proveedor caído) o la configuración está incompleta, el registro sigue respondiendo 201, el OTP queda guardado (solo su hash) pero **el usuario no recibe el código**, y el backend registra un `ERROR` **sin el código** y con el email enmascarado (`u***@dominio`):
  - `Error enviando el email de verificación a u***@dominio: <detalle>`
  - `Configuración SMTP incompleta: no se entregó el código de verificación a u***@dominio`

  Cualquiera de las dos líneas en producción es un fallo de configuración o del proveedor: busca esas cadenas en el log. La salida correcta es `Email de verificación enviado exitosamente a <email>`. Solo con `ENV=development` el fallo conserva el comportamiento de desarrollo (`Error enviando email: …` + `Código de verificación para <email>: <código>` en la consola).
- El envío es **asíncrono respecto a la petición**: `register` y `resend-code` crean el OTP, responden y entregan el correo después (tarea de fondo, en un hilo, sin sesión de BD). Con el SMTP caído o lento la respuesta no espera y el resto de peticiones no se bloquean; el fallo solo aparece en el log (las dos líneas de arriba). Consecuencias: la respuesta 201/200 **no garantiza** que el correo haya salido, y si el proceso se reinicia entre la respuesta y el envío, ese correo se pierde (no hay cola persistente: el usuario puede pedir otro código con reenviar). Además, si `create_otp_orm` falla después de confirmar el usuario, la cuenta queda creada sin código (se resuelve con `resend-code` o reintentando `register` con el mismo email, que emite uno nuevo).

### Autenticación: límites, intentos y respuestas

Valores por defecto **del código** (`backend/config.py` y `backend/app/config/security.py`); todas son opcionales:

| Variable | Por defecto | Efecto |
|----------|-------------|--------|
| `ENV` | sin definir = producción | Solo `development`, `dev` o `debug` activan el modo desarrollo: límites permisivos (1000 peticiones / 60 s), el OTP puede salir en el log si el envío falla y las cookies no llevan `Secure`. |
| `SESSION_LIFETIME_HOURS` | `24` | Vigencia única de la sesión (`expires_at`) y de la cookie (`Max-Age`). |
| `OTP_MAX_ATTEMPTS` | `5` | Comprobaciones erróneas que admite cada código (`verify-code` y `reset`); al llegar, se borra y hay que pedir otro. |
| `MAX_FAILED_LOGIN_ATTEMPTS` / `ACCOUNT_LOCKOUT_DURATION` | `5` / `1800` | Fallos de login antes del bloqueo y duración del bloqueo (s). |
| `TRUSTED_PROXY_HOPS` | `0` | Proxies de confianza delante de la app (ver abajo). |
| `RATE_LIMIT_<RUTA>_ATTEMPTS` / `_WINDOW` | ver tabla | Límite por IP y por ruta; `_WINDOW` en segundos. En `login` el máximo es de **fallos** por ventana, en el resto de peticiones. |

Límites por defecto (`POST /api/auth/...`; cada ruta tiene su propio contador por IP):

| Ruta | Variables | Máximo / ventana | Además, por cuenta |
|------|-----------|------------------|--------------------|
| `login` | `RATE_LIMIT_LOGIN_*` | 5 **fallos** / 900 s | no (la cuenta tiene su propio bloqueo) |
| `register` | `RATE_LIMIT_REGISTER_*` | 3 / 3600 s | sí, por email (mismo límite) |
| `verify-code` | `RATE_LIMIT_VERIFY_*` | 10 / 3600 s | no |
| `resend-code` | `RATE_LIMIT_RESEND_*` | 3 / 600 s | sí, por email (mismo límite) |
| `reset` | `RATE_LIMIT_RESET_*` | 5 / 3600 s | no |
| `forgot` | `RATE_LIMIT_FORGOT_*` | 3 / 3600 s | sí, por email (mismo límite) |

- Al superar el límite: **429** con `Retry-After` (segundos hasta que termina el bloqueo, mínimo 1) y `detail.code = rate_limit.exceeded`. El bloqueo dura una ventana.
- El contador por cuenta (`register`, `resend-code`, `forgot`) cuenta el email pedido, exista o no, con un identificador `acct:` + sha256 con sal (`IP_HASH_SALT`); no guarda el email en claro. Efecto secundario: tres peticiones con el email de otra persona bastan para que esa persona no pueda pedir un reenvío (o registrarse) durante la ventana.
- El límite de `login` cuenta **solo los fallos**: usuario inexistente o contraseña errónea (los `401 invalid_credentials`). Los logins correctos no gastan cupo ni reinician el contador, así que una IP compartida (campus, oficina) puede iniciar sesión tantas veces como haga falta; los fallos de todos sus usuarios suman. El fallo número `RATE_LIMIT_LOGIN_ATTEMPTS` (5) ya bloquea la IP la ventana completa: la siguiente petición, **aunque lleve la contraseña correcta**, recibe 429 con `Retry-After` (la comprobación va antes de autenticar, sin gastar bcrypt).
  - El `423 account_locked` (el bloqueo de cuenta se comprueba **antes** de la contraseña) y el `403 email_not_verified` (solo ocurre con la contraseña **acertada**) no cuentan: no son intentos de adivinarla. Un atacante que solo reciba 423 o 403 no avanza en ningún sentido (no hay contraseña que probar contra una cuenta bloqueada, y el 403 ya es una contraseña correcta). La contrapartida: esas respuestas, y los logins correctos, ya no tienen techo por IP; cada uno de los que llegan a comprobar la contraseña (200 y 403) gasta un bcrypt. Quien tenga una cuenta propia puede pedir logins sin límite desde su IP; el techo es la capacidad del servidor (sin medir), no un contador.
  - La comprobación (al entrar) y el registro del fallo (al terminar) son dos operaciones distintas y el contador no es atómico (lee, suma y escribe): varias peticiones concurrentes de una misma IP pueden pasar la comprobación antes de que se anote el fallo que bloquea, así que el cupo real puede excederse en tantos intentos como peticiones simultáneas. Límite conocido; la atomicidad del contador es el riesgo 6 de los riesgos abiertos.
- El contador trabaja en minutos enteros (`ventana // 60`, `rate_limiting.py`): usa ventanas múltiplos de 60 s. Una ventana de menos de 60 s da 0 minutos (no probado).
- Si la base de datos del limitador falla, la petición se **permite** (fail-open) y el error solo se imprime en el log.
- Con `ENV=development` todo es permisivo (1000 / 60 s); para probar los límites hay que ejecutar con `ENV=production`, y entonces el arranque exige `CSRF_SECRET_KEY` e `IP_HASH_SALT` (o `SECRET_KEY`, de la que heredan si no se definen). Los tests parchean `security_settings.DEVELOPMENT_MODE`.

#### `TRUSTED_PROXY_HOPS`

`get_client_ip` solo confía en `X-Forwarded-For` según este valor; `X-Real-IP` y `X-Forwarded` ya no se leen.

- `0` (por defecto): la IP es la del socket y la cabecera se ignora.
- `N > 0`: la IP es la entrada N-ésima **desde la derecha** de `X-Forwarded-For` (la que añadió el primer proxy de confianza; lo que hay a su izquierda lo escribe el cliente). Con menos entradas que `N`, o sin cabecera, se usa la IP del socket.

> ⚠️ **Antes de desplegar.** `backend/render.yaml` **no** lo define y el valor correcto **no se ha medido**: todavía no hay despliegue en Render y Render no documenta la estructura de `X-Forwarded-For` que recibe la aplicación. Con `0` detrás del proxy de Render todos los usuarios comparten IP y los límites por IP pasan a ser del sitio entero (5 fallos de login en 15 minutos entre todos, y 3 altas por hora). El valor no se adivina: se calibra en el primer despliegue (procedimiento abajo) y, mientras tanto, la aplicación avisa de la configuración peligrosa.

**Avisos de la aplicación** (solo fuera de desarrollo; ninguno cambia la IP que se usa ni el comportamiento):

- **Al arrancar**: `TRUSTED_PROXY_HOPS=0 en Render: …` si `RENDER=true` y el valor es `0`, y `FORWARDED_ALLOW_IPS=*: …` si esa variable vale `*`. Render fija `RENDER=true` en todos sus servicios ([variables de entorno de Render](https://render.com/docs/environment-variables); no comprobado en un despliegue propio); fuera de Render el primer aviso no sale.
- **En ejecución**: una línea de log de nivel `WARNING` que empieza por `TRUSTED_PROXY_HOPS=0 pero llegan peticiones con X-Forwarded-For` y sigue con `entradas=<n>`, `últimas=[<ip>, <ip>]` (las dos últimas entradas, enmascaradas: `203.0.113.x`, o `***` si no son una IP) y `socket=<ip>` (enmascarada). Sale **una vez por proceso**: con varios workers de gunicorn, una línea por worker. Nunca registra la cabecera completa ni IPs completas. Es a la vez la herramienta de calibración y un guardarraíl permanente (úsala como cadena de alerta de log).

**Calibración en el primer despliegue** (procedimiento previsto; no se ha ejecutado):

1. Despliega un servicio de staging con el mismo blueprint **sin** `TRUSTED_PROXY_HOPS`. Para que los límites por IP no bloqueen las pruebas mientras mides, sube temporalmente `RATE_LIMIT_LOGIN_ATTEMPTS`, `RATE_LIMIT_REGISTER_ATTEMPTS`, `RATE_LIMIT_VERIFY_ATTEMPTS`, `RATE_LIMIT_RESEND_ATTEMPTS`, `RATE_LIMIT_RESET_ATTEMPTS` y `RATE_LIMIT_FORGOT_ATTEMPTS` (solo en staging; se revierten en el paso 5).
2. Con el servicio recién arrancado, haz **una** petición de autenticación desde una IP pública que conozcas, sin cabecera `X-Forwarded-For` propia (por ejemplo, un intento de login con credenciales falsas desde el frontend de staging) y lee la línea del log. Si la IP que aparece no es la tuya, la línea corresponde a otra petición (una comprobación de salud, por ejemplo): reinicia el servicio y repite. Si no aparece ninguna línea, la petición no llegó a `get_client_ip` (por ejemplo, rechazada antes por CSRF): repítela desde el frontend.
3. Deduce el valor. Cada proxy de confianza añade una entrada con la IP del par que le habló, así que, con una petición sin cabecera propia, `entradas` es el número de proxies de confianza y tu IP es la entrada N-ésima desde la derecha. La línea solo muestra las dos últimas: con `entradas` mayor que 2 tu IP no aparece y hay que decidir con `entradas` y con lo que el proveedor documente. Las IPs a la derecha de la tuya son proxies del proveedor, no usuarios.
4. Comprueba la deducción con una segunda IP distinta (otra red o el móvil): al fijar el valor, deben aparecer dos filas distintas en `security_rate_limits` (consulta del [Troubleshooting](#problema-429-rate_limitexceeded-en-el-login-de-varios-usuarios-a-la-vez-producción)) y no la IP de un proxy.
5. Fija `TRUSTED_PROXY_HOPS` en el Dashboard y, después, en `render.yaml` con un comentario con la evidencia y la fecha; revierte los límites temporales del paso 1 y revisa `FORWARDED_ALLOW_IPS`.

**Dirección peligrosa del valor.** Un valor **menor** que los saltos reales de confianza degrada a límites compartidos (molesto, no peligroso: `entries[-1]` es la IP de un proxy del proveedor, común a muchos usuarios). Un valor **mayor** hace que `entries[-N]` caiga en una entrada que escribe el cliente y es **suplantable**: con un solo proxy real y `TRUSTED_PROXY_HOPS=2`, el cliente envía `1.2.3.4`, el proxy añade la IP del cliente y `entries[-2]` es `1.2.3.4`. Regla: **ante la duda, quédate corto.**

**`FORWARDED_ALLOW_IPS` y lo no medido.**

- Leído en el código de uvicorn 0.35 (contenedor del backend), **no probado en Render**: `UvicornWorker` pasa a uvicorn el `forwarded_allow_ips` de gunicorn (por defecto `127.0.0.1`); si el par inmediato no está en esa lista, uvicorn no reescribe `request.client` a partir de `X-Forwarded-For`. Con `FORWARDED_ALLOW_IPS=*` se confiaría en cualquier cliente y `request.client` pasaría a ser la primera entrada de la cabecera, que escribe el cliente: no lo uses. `render.yaml` no define esta variable.
- Si se listaran IPs concretas y uvicorn reescribiera `request.client`, la aplicación vería la IP real con `TRUSTED_PROXY_HOPS=0` y el aviso de ejecución podría salir igualmente (la cabecera sigue llegando): no medido, y las IPs de los proxies de Render no están documentadas.
- No medido: la estructura de `X-Forwarded-For` en Render. Hilos de su comunidad sugieren que puede haber un CDN delante con cabeceras propias (`cf-connecting-ip`, `true-client-ip`), que esta aplicación **no** lee: si fuese el caso, solo cuenta `X-Forwarded-For`.

#### Intentos por código (OTP)

Cada OTP admite `OTP_MAX_ATTEMPTS` comprobaciones erróneas (5). El intento se reserva **antes** de comprobar el código (incremento atómico), así que peticiones simultáneas no obtienen intentos de más. Al llegar al máximo el OTP se borra y el código correcto posterior tampoco vale: hay que pedir otro (`resend-code` o `forgot`). Un reenvío reinicia el contador. Se guarda en `email_otps.failed_attempts` (migración `0003`). El código caduca a los 10 minutos (fijados en el código: `OTP_EXPIRY_MINUTES` existe en la configuración pero no se usa).

#### Respuestas uniformes

| Ruta | Respuesta | Motivo real |
|------|-----------|-------------|
| `verify-code` | **400** `Código inválido o expirado` (`verification_failed`) ante cuenta inexistente, borrada, ya verificada, OTP ausente, caducado o erróneo | `security_logs.event_type = email_verification_failed`, `details.failure_reason` |
| `reset` | **400** `Código inválido o expirado` (`reset_failed`), mismos casos | `password_reset_reset_failed`, `details.failure_reason` |
| `register` | **201** `Usuario registrado exitosamente` con las mismas claves (`user_id`, `username`, `email`) tanto para un email nuevo como para uno con cuenta verificada, sin verificar o borrada. En las ramas «existente» `user_id` es aleatorio y `username`/`email` son los de la petición. Cambia solo el correo: verificada → aviso «Ya tienes una cuenta» (sin código); sin verificar → código nuevo; borrada → nada | `registration_duplicate_email`, `details.reason` (`account_already_verified` / `account_unverified_reissued` / `account_deleted`) |
| `register` con un username ocupado | **409** `username_taken` con independencia de que el email exista | `registration_failed`, `details.failure_reason = username_taken` |
| `resend-code` | **200** `Código reenviado correctamente` exista o no la cuenta; solo envía a cuentas existentes, no borradas y **sin verificar** | `resend_code_ignored`, `details.reason` (`user_not_found` / `account_already_verified`) |
| `forgot` | **200** `Si la cuenta existe y está verificada, recibirás un código en tu correo`; solo emite a cuentas existentes, verificadas y no borradas | `password_reset_request_failed`, `details.failure_reason` |
| `login` con la cuenta bloqueada | **423** `account_locked` | `login_failed`, `details.failure_reason` |

Para ver por qué falló una petición concreta:

```sql
SELECT created_at, event_type, details->>'failure_reason' AS motivo, details->>'reason' AS reason
FROM security_logs
WHERE event_type IN ('email_verification_failed', 'password_reset_reset_failed',
                     'password_reset_request_failed', 'resend_code_ignored',
                     'registration_duplicate_email', 'registration_failed')
ORDER BY created_at DESC LIMIT 20;
```

**`register` en detalle** (el 409 por email desaparece):

- Orden de comprobaciones: primero el username y después el email. Si el username es de **otra** cuenta (viva o borrada) que la del email, o el email no existe, la respuesta es el 409 `username_taken` aunque el email exista; si el username es libre (o de la misma cuenta), el email existente da el 201 uniforme. Así elegir un username ocupado no sirve para preguntar por emails: `(username_ocupado, X)` da siempre 409 y `(username_libre, X)` da siempre 201.
- Una cuenta **sin verificar** reintenta el alta con sus mismos datos (lo normal tras perder el correo) y recibe un código nuevo: el anterior deja de valer, `failed_attempts` vuelve a 0 y no se cambia ni la contraseña ni el username guardados. Esto repara también una cuenta que se quedó sin código (riesgo 5).
- Una cuenta **borrada** (`is_deleted`) sigue ocupando su email y su username (los índices únicos `ix_users_email` / `ix_users_username` cubren también las filas borradas): su email recibe el 201 uniforme sin intentar el `INSERT` y **sin ningún correo** (el aviso «inicia sesión» sería falso), y su username da 409. Efecto: ese email no puede volver a registrarse y el interesado no recibe ninguna explicación. La aplicación no borra cuentas (`is_deleted` solo lo fija un proceso externo), así que hoy no se da.
- Carreras: si otra petición da de alta el email o el username entre la consulta previa y el `INSERT`, el `IntegrityError` se resuelve volviendo a consultar y aplicando las mismas reglas (no depende del nombre de la restricción).
- Contador por email: `register` cuenta además por email (3 / 3600 s, el mismo límite), exista o no la cuenta, para que nadie llene de correos a una víctima. Efecto: tres peticiones con el email de otra persona le impiden registrarse durante la ventana.
- El tiempo de respuesta es de **mejor esfuerzo**: todas las ramas pagan el bcrypt de la contraseña y la rama «existente verificada» gasta además `simulate_otp_check` donde el alta nueva emite el OTP. No se ha medido ni se promete la igualdad.

`POST /api/auth/forgot` existe solo como API: el frontend no tiene pantalla de recuperación (`Login.tsx` enlaza a `/forgot-password`, que no tiene ruta).

#### Sesiones y contraseña

- `PUT /api/settings/password` revoca las **demás** sesiones del usuario (motivo `password_change`) y conserva la actual; con API key, sin cookie, las revoca todas.
- `reset` revoca todas las sesiones (motivo `password_reset`) y fija `password_changed_at`.
- Las cookies de 7 días emitidas antes de `SESSION_LIFETIME_HOURS` conservan su `Max-Age`; pero su sesión en BD dura 24 h: pasado ese tiempo, la cookie responde `auth.session_expired` y el usuario vuelve a entrar con login. No hay migración de cookies.

#### Migración `0003`

Añade `email_otps.failed_attempts INTEGER NOT NULL DEFAULT 0`: aditiva y reversible (`alembic downgrade -1`). `docker-compose.yml` la aplica al arrancar el backend (`alembic upgrade head && uvicorn …`) y `render.yaml` ejecuta `alembic upgrade head` antes de gunicorn. Un backend con el código nuevo sobre una BD en `0002` falla en cualquier consulta a `email_otps` (`UndefinedColumn`): aplica la migración (`docker-compose exec backend alembic upgrade head`, o reinicia el contenedor). No se ha probado en Render ni con tráfico concurrente.

#### Riesgos residuales (decisiones explícitas, no defectos pendientes de arreglar en esta fase)

- **`register` ya no enumera emails, pero sí usernames.** El 409 `username_taken` confirma que un username existe (cuenta viva o borrada); es la única respuesta que distingue, porque uniformarla rompería el alta. Lo frenan el límite por IP (3 por hora) y el contador por email.
- **Residuo del orden de comprobaciones.** `(username_de_A, email_de_A)` da 201 y `(username_de_A, otro_email)` da 409: quien conozca un username puede confirmar si un email concreto es el de esa cuenta. Es el precio de que una cuenta sin verificar pueda reintentar el alta con sus mismos datos; la alternativa (409 también para el mismo par) rompe el reenvío al reintentar.
- **Pre-secuestro de una cuenta sin verificar (decisión pendiente).** Quien registra el email de otra persona antes que ella fija la contraseña y el username de esa cuenta sin verificar; si la persona se registra después, el reintento no cambia nada guardado, recibe un código nuevo, lo verifica (`verify-code` abre sesión) y queda dentro de una cuenta cuya contraseña conoce otro. Antes de R3 el reintento recibía 409 y no había nada que verificar. Requiere que la víctima se registre después y verifique; el atacante no puede verificar por su cuenta (no ve el correo). Opciones: sobrescribir contraseña y username en el reintento de una cuenta sin verificar (gana el último registro) o no abrir sesión al verificar tras un reintento. No se ha aplicado ninguna: el diseño de R3 pedía conservar la contraseña guardada.
- **La igualación de tiempos es de mejor esfuerzo.** Los caminos «sin cuenta» gastan un bcrypt simulado (`simulate_otp_check`). Medido (n=7, contenedor de test): sin él 20–30 ms frente a 310–440 ms; con él 310–410 ms con rangos solapados. No es una garantía: no se descartan diferencias de decenas de ms ni se midió con carga o por red.
- **El 201 de `register` no garantiza que el correo salga** (entrega en segundo plano, sin cola persistente; ver arriba).
- **Frontend (sin cambios en esta fase)**: la UI muestra el `message` del servidor, así que `VerifyEmail` mostrará «Código inválido o expirado» donde antes decía «Usuario no encontrado» o «Email ya verificado»; `resend-code` da éxito aunque no envíe nada (cuenta inexistente o ya verificada); y el 429 se lee de `detail.code` (`rate_limit.exceeded`, locales `es`/`en`) sin usar `Retry-After`.

---

## 🛠️ Troubleshooting

### Problema: "Redis connection failed"

**Síntomas**:
```
RedisError: Error connecting to Redis
```

**Diagnóstico**:
```bash
# 1. Verificar que Redis está corriendo
docker-compose ps redis
# O en local:
redis-cli ping  # Debe retornar PONG

# 2. Verificar variables de entorno
echo $REDIS_HOST
echo $REDIS_PORT

# 3. Test de conexión
python
>>> from app.utils.redis_client import redis_health_check
>>> redis_health_check()
```

**Soluciones**:
- Verificar `REDIS_HOST` (debe ser `redis` en Docker, `localhost` en local)
- Verificar que Redis está corriendo: `docker-compose up -d redis`
- Revisar firewall/networking

### Problema: "Session not found" después de crear sesión

**Síntomas**:
Usuario crea sesión de encriptado pero siguiente request dice "session not found".

**Causa común**: Múltiples workers sin Redis compartido.

**Diagnóstico**:
```bash
# Ver si hay múltiples workers
ps aux | grep gunicorn

# Ver configuración de workers
echo $WEB_CONCURRENCY
```

**Solución**:
- Asegurarse de que Redis está configurado y funcionando
- Verificar que imports usan `redis_session_cache` (no `encryption_session_cache`)

### Problema: "Session hijacking detected" en logs

**Síntomas**:
```
WARNING: Session hijacking attempt detected!
  Session user_id: abc123...
  Current user_id: def456...
```

**Causa**: Sesión pertenece a un usuario diferente del autenticado.

**Diagnóstico**:
1. Verificar que no se están compartiendo cookies entre usuarios
2. Revisar lógica de creación de sesión
3. Validar que `user_id` se está pasando correctamente

**Solución normal**: Esto es un **comportamiento esperado** si detecta un intento real de hijacking. La sesión se invalida automáticamente.

### Problema: No llega el correo de verificación (desarrollo)

**Síntomas**:
- El registro responde 201 pero no hay correo en http://localhost:8025 (la entrega es en segundo plano: el 201 no garantiza que el correo haya salido; el resultado del envío aparece en el log del backend unos segundos después).

**Diagnóstico**:
```bash
# 1. Mailpit levantado y healthy
docker-compose ps mailpit
curl http://localhost:8025/api/v1/info

# 2. Qué dice el backend (en desarrollo el código aparece aquí si el envío falló)
docker logs datamap-backend 2>&1 | grep -E "Error enviando email|Código de verificación para|Email de verificación enviado"

# 3. Variables SMTP que ve el backend (sin SMTP_PASS, para no volcar la contraseña)
docker-compose exec backend env | grep -E "^(SMTP_SERVER|SMTP_PORT|SMTP_USER|SMTP_USE_STARTTLS|EMAIL_FROM)="
```

**Soluciones**:
- `Error enviando email: … Name or service not known` o `Connection refused`: Mailpit parado o `SMTP_SERVER` incorrecto. `docker-compose up -d mailpit`. El registro responde igual de rápido (el envío va en segundo plano); el error aparece en el log cuando termina el intento de envío (hasta ~10 s, el timeout, con el contenedor pausado). El código del log sirve igualmente para verificar la cuenta.
- `Configuración SMTP incompleta, simulando envío`: falta `SMTP_SERVER` o `EMAIL_FROM`, o solo hay una de `SMTP_USER`/`SMTP_PASS`.
- No aparece el código en el log ni hay correo, y el log solo dice `Error enviando el email de verificación a u***@dominio: …` o `Configuración SMTP incompleta: no se entregó …`: el backend **no está en modo desarrollo** (`ENV` distinto de `development`/`dev`/`debug`, o sin definir; por defecto es producción) y por eso no imprime el código. Define `ENV=development` en tu `.env` local; en producción corrige la configuración SMTP (ver [Correo (SMTP) en producción](#correo-smtp-en-producción)) y pide otro código con `POST /api/auth/resend-code`.
- `STARTTLS extension not supported by server`: `SMTP_USE_STARTTLS` no está en `false` (típico de un `.env` antiguo que sobrescribe el valor del compose). Mailpit no ofrece TLS.
- El correo estaba y desapareció: Mailpit es efímero y se vació al reiniciar el contenedor. Pide otro código con `POST /api/auth/resend-code`.
- Mailpit no arranca tras tocar el compose: `MP_SMTP_AUTH_ACCEPT_ANY` y `MP_SMTP_AUTH_ALLOW_INSECURE` deben definirse juntas.

### Problema: 429 `rate_limit.exceeded` en el login de varios usuarios a la vez (producción)

**Síntomas**: usuarios distintos reciben `429` en `login`, `register` o `verify-code` casi a la vez, con `Retry-After` de minutos.

**Causa habitual**: `TRUSTED_PROXY_HOPS` sin fijar (`0`) detrás del proxy: todos los usuarios llegan con la IP del proxy y comparten el contador por IP (ver [Autenticación](#autenticación-límites-intentos-y-respuestas)). El log lo avisa con la línea `TRUSTED_PROXY_HOPS=0 pero llegan peticiones con X-Forwarded-For` (ver el problema siguiente).

**Diagnóstico**:
```sql
-- Contadores por IP (los de cuenta empiezan por "acct:"): una sola fila con un request_count
-- alto en /api/auth/login indica una IP compartida
SELECT endpoint, identifier, request_count, blocked_until
FROM security_rate_limits
WHERE identifier NOT LIKE 'acct:%'
ORDER BY request_count DESC LIMIT 10;
```

**Solución**: calibra `TRUSTED_PROXY_HOPS` con el procedimiento de [`TRUSTED_PROXY_HOPS`](#trusted_proxy_hops). Si el 429 es de verdad de una sola IP (campus, oficina), ten en cuenta que en `login` solo cuentan los fallos: los logins correctos no lo causan. Lo causan 5 contraseñas erróneas o usuarios inexistentes en 15 minutos entre todos los usuarios de esa IP; sube `RATE_LIMIT_LOGIN_ATTEMPTS` si es tráfico legítimo (usuarios que olvidaron la contraseña). En el `request_count` de la consulta anterior, para `/api/auth/login` el valor es de fallos.

### Problema: aviso `TRUSTED_PROXY_HOPS=0 pero llegan peticiones con X-Forwarded-For` en el log

**Síntomas**: una línea `WARNING` como `TRUSTED_PROXY_HOPS=0 pero llegan peticiones con X-Forwarded-For: entradas=2, últimas=[198.51.100.x, 203.0.113.x], socket=10.0.0.x. …` (valores de ejemplo; una por worker de gunicorn), y/o al arrancar `TRUSTED_PROXY_HOPS=0 en Render: …` o `FORWARDED_ALLOW_IPS=*: …`.

**Causa**: hay un proxy delante de la aplicación y `TRUSTED_PROXY_HOPS` no está fijado: la aplicación ignora la cabecera y usa la IP del socket, que es la del proxy; todos los usuarios comparten los contadores por IP (ver el problema anterior). En desarrollo (`ENV=development`) el aviso no sale.

**Qué hacer**: calibra el valor con el procedimiento de [`TRUSTED_PROXY_HOPS`](#trusted_proxy_hops) (cuenta las entradas que añaden proxies **de confianza**; ante la duda, un valor menor). Para `FORWARDED_ALLOW_IPS=*`, sustituye el comodín por las IPs de los proxies de confianza o quita la variable.

### Problema: `verify-code` o `reset` responden siempre «Código inválido o expirado»

Es el comportamiento esperado: cuenta inexistente, ya verificada, código erróneo, caducado o agotado (`OTP_MAX_ATTEMPTS`) dan la misma respuesta. El motivo real está en `security_logs` (consulta de [Respuestas uniformes](#respuestas-uniformes)). Si el código se agotó, pide otro con `resend-code` (cuenta sin verificar) o `forgot` (cuenta verificada).

### Problema: `UndefinedColumn … failed_attempts` en `email_otps`

El backend lleva el modelo con `failed_attempts` y la BD sigue en `0002`. Aplica la migración: `docker-compose exec backend alembic upgrade head` (o reinicia el contenedor del backend: el compose la ejecuta al arrancar). Comprueba con `alembic current`.

### Problema: login con `423 account_locked`

`MAX_FAILED_LOGIN_ATTEMPTS` (5) logins erróneos bloquean la cuenta `ACCOUNT_LOCKOUT_DURATION` segundos (1800). El bloqueo se levanta solo al vencer; en desarrollo puedes limpiarlo con `UPDATE users SET locked_until = NULL, failed_login_attempts = 0 WHERE email = '<email>';`.

### Problema: Docker Compose no inicia

**Síntomas**:
```
ERROR: Couldn't connect to Docker daemon
```

**Soluciones**:
```bash
# Windows
# Asegurarse de que Docker Desktop está corriendo

# Linux
sudo systemctl start docker

# Verificar
docker ps
```

### Problema: "Port 8000 already in use"

**Solución**:
```bash
# Encontrar proceso usando el puerto
# Windows:
netstat -ano | findstr :8000
taskkill /PID <pid> /F

# Linux/Mac:
lsof -ti:8000 | xargs kill -9

# O cambiar puerto en docker-compose.yml:
ports:
  - "8001:8000"  # Host:Container
```

### Problema: Migraciones de BD fallan

**Diagnóstico**:
```bash
# Conectar a PostgreSQL directamente
docker-compose exec postgres psql -U datamaper_user_local -d datamap_dev

# Verificar tablas
\dt

# Ver última migración aplicada
SELECT * FROM migrations ORDER BY applied_at DESC LIMIT 1;
```

---

## 📊 Monitoring y Logs

### Logs en Docker Compose

```bash
# Ver logs en tiempo real
docker-compose logs -f backend

# Filtrar por nivel
docker-compose logs backend | grep ERROR
docker-compose logs backend | grep WARNING

# Últimas 100 líneas
docker-compose logs --tail=100 backend
```

### Logs en Render

1. Dashboard → datamap-backend → Logs
2. Real-time streaming
3. Filtros por nivel (INFO, WARNING, ERROR)

### Métricas de Redis

```bash
# Stats de sesiones
curl http://localhost:8000/api/encryption/debug/cache-stats

# Redis CLI
docker-compose exec redis redis-cli

# Dentro de Redis CLI:
> INFO stats
> DBSIZE
> KEYS enc_session:*
> MEMORY USAGE enc_session:project:token
```

### Health Checks

**Endpoint principal**:
```bash
GET /health
→ 200 OK: {"status": "healthy"}
```

**Redis health**:
```python
from app.utils.redis_client import redis_health_check
redis_health_check()  # True si Redis está disponible
```

### Alertas Recomendadas

Configurar alertas para:
- ❌ Redis connection errors (crítico)
- ⚠️ Session hijacking attempts (seguridad)
- ⚠️ High memory usage en Redis (>80%)
- ⚠️ Response time > 2s (performance)

---

## 🔄 Rollback y Disaster Recovery

### Rollback de Código

```bash
# Git rollback
git revert <commit_hash>
git push origin main

# Render redeploy automático en ~2-3 minutos
```

### Backup de Redis (Producción)

Render hace backups automáticos del Redis, pero para backup manual:

```bash
# En Render Shell (si disponible)
redis-cli --rdb /tmp/dump.rdb

# O configurar snapshots
CONFIG SET save "900 1 300 10"
```

### Disaster Recovery Plan

1. **Redis caído**: Sistema falla con error claro, usuarios no pueden acceder a proyectos cifrados
2. **PostgreSQL caído**: Sistema completamente down
3. **Backend crashed**: Render reinicia automáticamente

**Recovery Time Objective (RTO)**: < 5 minutos
**Recovery Point Objective (RPO)**: < 1 minuto (Redis snapshots)

---

## 📚 Recursos Adicionales

- [Render Documentation](https://render.com/docs)
- [Redis Documentation](https://redis.io/docs/)
- [Docker Compose Reference](https://docs.docker.com/compose/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)

---

**Última revisión**: 2026-10-11
**Mantenido por**: DataMap DevOps Team
