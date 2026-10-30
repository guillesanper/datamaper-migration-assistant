# Auditoría de calidad y seguridad — DataMaper (oct. 2026)

Revisión de `backend/`, `frontend/`, CI (`.github/workflows`), Docker y despliegue (`backend/render.yaml`).
Partiendo del commit `ac3312b` (main).

## Lo que ya está bien

- Auth sólida: cookies httpOnly, CSRF en producción, rotación de sesión, OTP con límite de intentos,
  rate limiting por ruta, bloqueo de cuenta, validación de `SECRET_KEY`/`CSRF_SECRET_KEY` al arrancar.
- SQL generado con quoting por dialecto (`app/utils/sql_safety.py`) y `validate_sql_expression` en las
  transformaciones; origen en transacción de solo lectura.
- Política de red para conectores (`network_policy.py`) que bloquea IPs internas en producción.
- Cifrado por proyecto (Argon2 + master key), TLS verificado por defecto en los adaptadores.
- Contenedor no-root, CORS sin `*`, pre-commit con detect-secrets, Dependabot, ~170 ficheros de tests.

## Hallazgos de seguridad

### 🔴 Crítico — control de acceso roto (IDOR) en los routers de colaboración

Los endpoints sólo comprueban que el usuario esté **autenticado**, no que sea **miembro del proyecto**.
Cualquier usuario registrado que conozca/adivine un `project_id`, `version_id`, `entity_id`… puede:

| Router | Endpoint | Impacto |
|---|---|---|
| `locks.py:160` | `POST /locks/force-unlock` | Forzar desbloqueo en cualquier proyecto (hay un `TODO` explícito) |
| `locks.py` | `acquire`, `release`, `status`, `GET /locks/projects/{id}` | Ver/alterar bloqueos ajenos |
| `versions.py:116` | `GET /versions/{id}`, `/versions/compare`, `/versions/entity/{id}` | Leer snapshots de otros proyectos |
| `versions.py:157` | `POST /versions/{id}/restore` | **Modificar datos** de otro proyecto |
| `versions.py` | `GET /versions/projects/{id}`, `/tags`, `POST /versions/tags` | Leer/crear tags ajenos |
| `activity.py:17-122` | `/activity/projects/{id}`, `/entity/{id}`, `/users/{id}`, `/stats` | Fuga de actividad (nombres de tablas, usuarios) |
| `comments.py` | `GET /comments`, `POST /comments`, `/unread/{project_id}` | Leer/escribir comentarios en proyectos ajenos |

Además, el broadcast en tiempo real se dispara con el `project_id` de la petición, así que un atacante
puede inyectar eventos falsos en el WebSocket de otro proyecto.

**Arreglo:** crear una dependencia común `require_project_member(project_id, min_role=...)` en
`routers/dependencies.py` (reutilizando `ProjectCRUD.check_user_access_orm`, como ya hace
`migration.py:113 validate_project_access`) y aplicarla a **todos** los endpoints. Para los que reciben
`version_id`/`comment_id`/`lock_id`, resolver primero el `project_id` del recurso y verificar membresía.
Añadir tests de integración "usuario B no puede tocar el proyecto de A" por endpoint (patrón ya usado en
`test_schemas_cross_project.py`).

### 🟠 Alto

1. **Fuga de detalles internos en errores** — 52 sitios con `detail=f"...{str(e)}"` / `detail=str(e)`
   (`mappings`, `migration`, `encryption`, `versions`, `comments`, `activity`, `locks`). Pueden exponer
   SQL, rutas o mensajes de drivers. Ya existe `app/utils/exception_sanitizer.py` y `make_error(ErrorCode…)`:
   usarlos siempre y loggear el detalle en servidor.
2. **SSRF por DNS rebinding** en conectores — `validate_connection_host` resuelve el host y valida, pero
   luego el driver vuelve a resolver el nombre al conectar (TOCTOU). Conectar a la IP ya validada
   (`hostaddr` en psycopg2, IP + `server_hostname`/SNI para TLS en el resto) o revalidar la IP del socket
   tras conectar.
3. **Imagen Docker de producción arranca con `--reload`** (`backend/Dockerfile`, último `CMD`) y se publica
   en GHCR como `latest`. Usar gunicorn+uvicorn workers (como `render.yaml`) y dejar `--reload` sólo en
   `docker-compose.yml`.
4. **Escaneos de seguridad que nunca fallan**: `safety check --continue-on-error`, `npm audit` con
   `continue-on-error: true`, Trivy sin `exit-code`/`severity` y fijado a `@master`. Hacer que fallen en
   High/Critical (con allowlist documentada) y cambiar `safety` por `pip-audit`.

### 🟡 Medio

1. **Subida de avatar** (`user_settings.py:147`): `await file.read()` lee el fichero entero antes de
   comprobar el tamaño (DoS de memoria) y confía en `content_type` del cliente. Leer con límite
   (`file.read(MAX+1)`), fijar `Image.MAX_IMAGE_PIXELS` y llamar a `img.verify()`.
2. **Ficheros estáticos sin auth**: `/api/uploads` sirve avatares públicamente por `user_id` (enumerable).
   Aceptable si es intencional; si no, nombre aleatorio o servir vía endpoint autenticado.
3. **Redis con `allkeys-lru`** (`render.yaml`) y 25 MB: bajo presión puede **expulsar contadores de rate
   limiting y sesiones de cifrado**, reabriendo fuerza bruta. Usar `noeviction` o `volatile-lru` y TTL en
   todas las claves.
4. **Secretos por defecto en `docker-compose.yml`** (`SECRET_KEY: ${SECRET_KEY:-eWG%...}`,
   `DB_PASSWORD: DataMap1234`) y `URLSafeSerializer(SECRET_KEY or "")` en `utils/cookies.py`. Sólo dev, pero
   mejor fallar si falta en vez de usar un valor fijo.
5. **GitHub Actions sin fijar a SHA** (`actions/*@v4`, `trivy-action@master`) y sin bloque `permissions:`
   por defecto en `pr-checks.yml`. Fijar a SHA (Dependabot los mantiene) y `permissions: contents: read`.
6. **IDs de sesión de conectores en `localStorage`** (`ProjectMapping.tsx:134`). Están ligados al usuario
   en backend, pero cualquier XSS los roba; valorar `sessionStorage` o cookie httpOnly.
7. CSP con `'unsafe-inline'` en `script-src` (`.env.example`). Revisar si la API realmente necesita
   servir HTML; si no, una CSP `default-src 'none'` para la API.

### 🟢 Bajo

- `X-XSS-Protection: 1; mode=block` está obsoleto; mejor `0`.
- `oracledb>=2.0.0` sin fijar en `requirements.txt` (rompe reproducibilidad).
- `__import__("asyncio").create_task(...)` en `locks.py` sin guardar referencia (la tarea puede ser recolectada).

## Hallazgos de calidad de código

1. **Ficheros enormes**: `routers/mappings.py` (2 908 líneas), `migration.py` (1 156), `schemas.py`
   (1 096), `encryption.py` (1 047); en frontend `TwoColumnView.tsx` (1 221) y `MigrationModal.tsx` (976).
   Lógica de negocio dentro de los routers. Dividir por subrecurso y mover lógica a `services/`.
2. **Autorización dispersa** — cada router lo hace a su manera (o no lo hace). Centralizarla (ver crítico).
3. **Manejo de excepciones**: `ruff` reporta 293 `except Exception` genéricos (BLE001), 208 `raise` sin
   `from` (B904), 14 `try/except/pass`, 3 `except:` desnudos. Crear excepciones de dominio y un
   `exception_handler` global que las traduzca a `ErrorCode`.
4. **Linting muy laxo en CI**: `flake8 --select=E9,F63,F7,F82` sólo detecta errores de sintaxis. Migrar a
   `ruff` (sustituye flake8+isort, y black con `ruff format`) con reglas `E,F,B,S,BLE,UP,SIM` y
   baseline progresiva. `mypy` con `--ignore-missing-imports` y 93 `# type: ignore`.
5. **`print()` en vez de logging**: 267 `print(` en `app/` y `main.py`. Sustituir por `logging` estructurado
   (y nunca loggear credenciales/claves).
6. **Respuestas inconsistentes**: unos endpoints devuelven `{"success", "data", "message"}`, otros el objeto
   plano; unos errores usan `make_error(ErrorCode…)` y otros texto en inglés. Definir `response_model`
   Pydantic en todos los endpoints (también mejora OpenAPI).
7. **Frontend sin tests** (no hay vitest/jest ni script `test`), 93 `console.log`. Añadir Vitest +
   Testing Library para servicios y hooks críticos (`AuthProvider`, `EncryptionProvider`, `api.service`).
8. **Repo con ruido**: `backend/coverage.json` y `docs/baseline/*.xml` versionados, mocks de varios MB,
   ~30 documentos de "FASE_x / FIX_SUMMARY" en `backend/docs/` y `MIGRATION_GAPS_ANALYSIS.md`. Mover lo
   histórico a `docs/archive/` o al wiki, y añadir `coverage.*` al `.gitignore`.
9. **Pequeños**: `main.py` crea `uploads/` en import; `ENV`/`IS_DEVELOPMENT` se calculan en varios sitios
   (centralizar en un `Settings` de `pydantic-settings`); `Dockerfile` usa Python 3.11 — valorar 3.12/3.13.

## Plan de mejora por fases

### Fase 0 — Urgente (1–3 días)
- [ ] `require_project_member` en `dependencies.py` y aplicarlo a `locks`, `versions`, `activity`, `comments`
      (incluido `force-unlock` con rol owner/admin y `restore` con rol editor).
- [ ] Tests de integración cross-project para cada endpoint de esos 4 routers.
- [ ] Sustituir los 52 `str(e)` en respuestas por `make_error(...)` + `logger.exception`.
- [ ] Quitar `--reload` del `Dockerfile` (CMD con gunicorn).

### Fase 1 — Endurecimiento (1–2 semanas)
- [ ] Mitigar DNS rebinding conectando a la IP validada.
- [ ] Avatar: lectura con límite, `MAX_IMAGE_PIXELS`, `verify()`.
- [ ] Redis `noeviction`/`volatile-lru`.
- [ ] CI: `pip-audit` y `npm audit` bloqueantes en High+, Trivy con `exit-code: 1`, actions fijadas a SHA,
      `permissions: contents: read`.
- [ ] Quitar secretos por defecto de `docker-compose.yml`; `cookies.py` falla si no hay `SECRET_KEY`.
- [ ] Fijar `oracledb`; añadir `bandit`/`ruff -S` al pre-commit.

### Fase 2 — Calidad (2–4 semanas)
- [ ] Migrar a `ruff` (lint + format) con reglas ampliadas y baseline; activar `B904`, `BLE001`, `T20`.
- [ ] Handler global de excepciones de dominio; eliminar `except Exception` genéricos por router.
- [ ] `print` → `logging`; `console.log` → logger con nivel por entorno.
- [ ] `response_model` en todos los endpoints y formato de respuesta único.
- [ ] Vitest en frontend con tests de servicios/providers; añadir a `pr-checks.yml`.

### Fase 3 — Mantenibilidad (continuo)
- [ ] Partir `mappings.py` y demás routers >1 000 líneas; mover lógica a servicios.
- [ ] Partir `TwoColumnView.tsx` / `MigrationModal.tsx` en subcomponentes + hooks.
- [ ] `Settings` único con `pydantic-settings`.
- [ ] Limpiar docs históricas, `coverage.json` y mocks pesados (Git LFS si hacen falta).
- [ ] Subir `mypy` a modo estricto por módulos y reducir `# type: ignore`.

## Alcance y límites

Revisión estática; no se ha ejecutado la app ni los tests. `schemas`, `mappings`, `projects`,
`db_connections`, `notifications`, `billing` y `admin` se revisaron por muestreo y sí aplican
comprobaciones de acceso; conviene confirmarlo endpoint a endpoint con los tests cross-project de la Fase 0.
