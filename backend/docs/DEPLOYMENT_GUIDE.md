# DataMap Backend - Deployment Guide

**Última actualización**: 2025-01-06
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
- **SMTP Server** - Email notifications (Gmail, Protonmail, etc.)

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

#### 5. Ejecutar Migraciones (si existen)

```bash
# Aplicar migraciones de BD
python migrations/run_migrations.py  # Si aplica
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
SMTP_PASS=<app_password>
CSRF_SECRET_KEY=<another_random_key>
IP_HASH_SALT=<random_salt>
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
- ✅ SMTP credentials válidas
- ✅ `DB_PASSWORD` fuerte

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

**Última revisión**: 2025-01-06
**Mantenido por**: DataMap DevOps Team
