# Línea base de tests (Fase 0)

Resultado de la suite sobre el código original (tag `pre-alembic-baseline`, commit `de5a54b`),
cuyo esquema de test se crea con `Base.metadata.create_all`. Sirve como referencia para el
criterio A7 del plan: ningún test que pasaba aquí puede fallar tras el cambio a Alembic.

| Fichero | Contenido |
|---|---|
| `baseline_before.xml` | JUnit XML completo |
| `baseline_before_summary.txt` | Totales y lista de fallados/errores/saltados con su causa |
| `baseline_before_passed.txt` | Los 1495 tests que pasan (para comparar con `baseline_after`) |

## Cómo se generó

```bash
git worktree add --detach <dir>/wt-baseline pre-alembic-baseline
backend/scripts/run_tests_in_container.sh <dir>/wt-baseline/backend <dir_salida> baseline_before
```

Ejecuta `pytest test/unit test/integration -m "not slow" --maxfail=0 -p no:cacheprovider` en la
imagen del backend (Python 3.11), con un Redis en el puerto 6380 y el Postgres de docker-compose.

## Resultado

`19 failed, 1495 passed, 1 skipped, 31 errors` (1546 tests). Dos pasadas seguidas dieron el mismo
conjunto de tests pasados y de fallados (solo cambia el sufijo aleatorio del username en un mensaje).

Los 50 fallos/errores ya existían antes de tocar nada y no tienen que ver con el esquema:

| Grupo | Nº | Causa |
|---|---|---|
| `test_db_connection_flow` (13 fallos + 17 errores) | 30 | Necesitan un Postgres en `localhost:5433` y un MySQL en `localhost` (según los errores de conexión; ver `docker-compose.test.yml`), que el arnés no levanta |
| `test_migration_api` (14 errores) | 14 | `from conftest import ...` falla con `--import-mode=importlib` (que fija `pytest.ini`) |
| `test_schema_service` | 2 | El test espera un texto en español y el servicio devuelve `{'code': 'schema.…'}` (refactor i18n) |
| `test_csrf_protection_middleware` | 1 | Igual: espera texto y recibe `{'code': 'security.csrf_token_invalid'}` |
| `test_tags_crud_integration` | 2 | `creator_username` no coincide con el usuario del fixture |
| `test_project_service` | 1 | `delete_project` no lanza `HTTPException` con miembros |

## Después del cambio (Fase 4)

Misma suite y mismo arnés sobre el código con la cadena Alembic nueva (`0001_baseline` + `0002_db_functions`),
con el esquema de test creado por `alembic upgrade head`.

| Fichero | Contenido |
|---|---|
| `baseline_after.xml` | JUnit XML completo |
| `baseline_after_summary.txt` | Totales y lista de fallados/errores/saltados con su causa |
| `baseline_after_passed.txt` | Los 1510 tests que pasan |

```bash
backend/scripts/run_tests_in_container.sh <dir>/backend <dir_salida> baseline_after
diff baseline_before_passed.txt baseline_after_passed.txt   # solo líneas ">" (nuevos)
```

Resultado: `19 failed, 1510 passed, 1 skipped, 31 errors` (1561 tests). Frente a la línea base:

- **0 tests que pasaban antes y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+15 pasados**, todos de `test_alembic_migrations.py` (no existían antes).
- Los mismos 50 fallos/errores, uno a uno (`test_tags_crud_integration` incluido: sus 2 tests pasan si el
  fichero se ejecuta solo, 12/12, pero fallan dentro de la suite completa igual que en la línea base).

## Después de retirar los CRUD psycopg2 (Fase B de la retirada de psycopg2)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código sin las variantes psycopg2 de `app/crud/*`, sin `get_db` ni
`data_retention_service`, y con `mappings.py`, `stripe_service`, `execution_service` y
`BackupManager` migrados a sesiones SQLAlchemy.

Resultado: `17 failed, 1532 passed, 1 skipped, 31 errors` (1581 tests). Frente a la línea base anterior (1510 pasados):

- **0 tests que pasaban y fallan ahora**, salvo los **18 retirados** porque su único sujeto era código retirado:
  - `test_tags_crud_integration` (10 pasados): probaba `tags_crud` crudo; el equivalente `_orm` lo cubre `test_tags_crud_orm`.
  - `test_database.TestGetDb` (8): probaba `app.database.database.get_db`.
- **+40 pasados** nuevos: `test_mappings_router_endpoints.py` (34, endpoints `export`, `tables`, `validate`,
  `import_structure`, `generate-migration-script` y permisos de `save`/`delete`, que no tenían tests) y
  `test_execution_service_db.py` (6, SQL real de `ExecutionService`, `BackupManager` y `MigrationValidator`).
- Los mismos 48 fallos/errores ajenos; desaparecen los 2 de `test_tags_crud_integration` junto con el fichero.
- `test_t3_extractor_reads_every_raw_insert`: el umbral pasó de `>= 19` a `>= 1`, porque los 18 INSERT crudos
  restantes pertenecían a los CRUD retirados; solo queda el de `ExecutionService`.

Fuera de esta suite (la línea base solo ejecuta `test/unit` y `test/integration`), `test/e2e` y
`test/test_worker_isolation.py` dan 36 pasados antes y después de la retirada (y los mismos 44 fallos de
conexión a BD de usuario).

Los ficheros se generan desde el JUnit XML: pasados como `classname::name` ordenado con LF, y el resumen con
los totales y la lista de fallados/errores/saltados (primera línea del mensaje).

## Después del SMTP de desarrollo (Mailpit) y la corrección de verify-code

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código con el envío de verificación configurable (STARTTLS y credenciales
opcionales, `timeout`; commits `f9fa28b` y `c984305`) y la corrección de `POST /api/auth/verify-code`
(commit `363f2ad`).

Resultado: `17 failed, 1569 passed, 1 skipped, 31 errors` (1618 tests). Frente a la línea base anterior (1532 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+37 pasados**, todos nuevos: `test_email_verification.py` (22: `TestSmtpUseStarttlsEnvironment` 15 y
  `TestSendVerificationCodeSmtpModes` 7), `test_auth_router_serialize_user.py` (9) y
  `test_auth_verify_code_api.py` (6, ruta real contra la BD de test).
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje.

## Después de revocar sesiones en logout y reset

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código en el que `POST /api/auth/logout` revoca la sesión de la cookie
recibida y `POST /api/auth/reset` revoca las sesiones previas del usuario.

Resultado: `17 failed, 1576 passed, 1 skipped, 31 errors` (1625 tests). Frente a la línea base anterior (1569 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+7 pasados**, todos nuevos: `test_auth_session_revocation_api.py` (logout revoca la sesión en BD, la misma
  cookie da 401, solo se revoca la sesión actual, `/me` no expone identificadores de sesión, y reset revoca las
  sesiones previas, permite entrar con la contraseña nueva y no revoca con un código erróneo).
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje.

## Después de la sesión, la cookie y la contraseña (P1 de la deuda de autenticación)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código con la vigencia única de sesión y cookie (`SESSION_LIFETIME_HOURS`),
el helper `get_session_token_hash`, la revocación de sesiones en `PUT /api/settings/password`,
`password_changed_at` en el reset y el 423 (en vez de 500) al entrar en una cuenta bloqueada.

Resultado: `17 failed, 1589 passed, 1 skipped, 31 errors` (1638 tests). Frente a la línea base anterior (1576 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+13 pasados**, todos nuevos: `test_auth_session_revocation_api.py` (10: change-password revoca las otras
  sesiones y conserva la actual, no revoca con la contraseña actual errónea, con API key revoca todas,
  permite entrar con la nueva; `password_changed_at` se actualiza en el reset y un `DatabaseError` del reset
  responde 500 con el formato estándar; `Max-Age` de la cookie igual a
  24 h y a la vigencia de la sesión; login con bloqueo activo y con bloqueo por intentos da 423 y con bloqueo
  vencido entra) y `test_cookies.py::TestGetSessionTokenHash` (3).
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje.

El generador de `*_passed.txt` y `*_summary.txt` se validó antes de usarlo: sobre el `baseline_after.xml`
anterior reproduce los dos ficheros byte a byte (pasados ordenados con LF; resumen con la cabecera
`total=… passed=… failed=… error=… skipped=…` y, por sección, `classname::name  | primera línea del mensaje`).

## Después de sacar el OTP del log fuera de desarrollo (P2 de la deuda de autenticación)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código en el que el código de verificación solo se imprime con
`DEVELOPMENT_MODE` (fuera de él se registra un `ERROR` sin código y con el email enmascarado) y en el que
`validate_security_config` avisa si faltan `SMTP_SERVER`/`EMAIL_FROM`.

Resultado: `17 failed, 1613 passed, 1 skipped, 31 errors` (1662 tests). Frente a la línea base anterior (1589 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+24 pasados**, todos nuevos, en `test_email_verification.py`: `TestOtpNotLoggedOutsideDevelopment` (19: el
  código no aparece en stdout, stderr ni logging fuera de desarrollo en 5 escenarios de fallo; el fallo se
  registra con el email enmascarado; en desarrollo se conserva el fallback; el envío correcto nunca lo
  registra; el helper sigue a `DEVELOPMENT_MODE`) y `TestSmtpStartupWarning` (5: aviso de arranque).
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje.

El generador se validó antes de usarlo: sobre el `baseline_after.xml` anterior reproduce
`baseline_after_passed.txt` y `baseline_after_summary.txt` byte a byte.

## Después de sacar el envío del correo del event loop (P3 de la deuda de autenticación)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código en el que `register` y `resend-code` entregan el correo en segundo
plano (`BackgroundTasks`, sin sesión de BD) y los servicios síncronos de login, register, verify-code y
reset se ejecutan en el threadpool.

Resultado: `17 failed, 1639 passed, 1 skipped, 31 errors` (1688 tests). Frente a la línea base anterior (1613 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+26 pasados**, todos nuevos: `test_auth_background_delivery_api.py` (11: la respuesta de register y
  resend-code sale mientras el SMTP lento sigue en curso, el cuerpo nunca contiene el código, el código
  entregado es el guardado, el event loop sigue atendiendo durante el envío, `create_user` entrega por
  `deliver` y no devuelve el código, y los 4 servicios pesados corren fuera del hilo del loop) y
  `test_email_verification.py::TestIssueAndDeliverSplit` (15: emisión y entrega por separado, la entrega
  no recibe `db`, conserva la política del OTP en 5 escenarios × 2 entornos, `send_verification_code` =
  emisión + entrega).
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje.

El generador se validó antes de usarlo: sobre el `baseline_after.xml` anterior reproduce
`baseline_after_passed.txt` y `baseline_after_summary.txt` byte a byte.

## Después de unificar el rate limiting, fijar la IP del cliente y limitar los intentos por OTP (P4 de la deuda de autenticación)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código en el que `@rate_limit` honra sus argumentos y lo llevan login,
register, verify-code, resend-code y reset (el middleware global y su tabla de rutas cortas se retiran),
`get_client_ip` solo confía en `X-Forwarded-For` según `TRUSTED_PROXY_HOPS` (0 por defecto), `resend-code`
cuenta además por email, y cada OTP admite `OTP_MAX_ATTEMPTS` fallos (columna `email_otps.failed_attempts`,
migración 0003).

Resultado: `17 failed, 1699 passed, 1 skipped, 31 errors` (1748 tests). Frente a la línea base anterior (1639 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+60 pasados**, todos nuevos: `test_rate_limiting.py` (21: la regla explícita manda, la ventana se
  reinicia, aislamiento por IP y por cuenta, contadores de IP y de cuenta que conviven, X-Forwarded-For
  falsificado no cambia la clave, configuración permisiva en desarrollo, fail-open, 429 con
  `Retry-After`), `test_auth_rate_limits_api.py` (20: 429 por ruta e IP, aislamiento, límite por email entre
  IPs, 5 fallos invalidan el OTP en verify-code y reset, el reenvío da otra tanda),
  `test_email_otp_crud_orm.py` (10: contador, invalidación, reinicio, atomicidad) y
  `test_security.py::TestTrustedProxyHops` (9).
- Tres tests existentes de `TestClientIPDetection` cambian de aserción a propósito
  (`test_get_client_ip_x_forwarded_for`, `…_x_real_ip`, `…_x_forwarded`: fijaban que la IP la elige el
  cliente) y siguen pasando; por nombre no hay diferencias en el resto.
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje.

El generador se validó antes de usarlo: sobre el `baseline_after.xml` anterior reproduce
`baseline_after_passed.txt` y `baseline_after_summary.txt` byte a byte.

## Después de las respuestas uniformes y POST /api/auth/forgot (P5 de la deuda de autenticación)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código en el que verify-code y reset responden siempre 400 «Código inválido
o expirado» (el motivo real va al log de seguridad), resend-code y forgot responden 200 con el mismo
cuerpo exista o no la cuenta, existe `POST /api/auth/forgot`, y los caminos «sin cuenta» gastan el mismo
bcrypt que los reales (`email_otp_crud.simulate_otp_check`).

Resultado: `17 failed, 1737 passed, 1 skipped, 31 errors` (1786 tests). Frente a la línea base anterior (1699 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+38 pasados**, todos nuevos y de `test_auth_uniform_responses_api.py`: los seis fallos de
  verify-code y de reset (cuenta inexistente, borrada, ya verificada, código erróneo, sin OTP, OTP
  caducado) devuelven el mismo estado y cuerpo; el motivo real queda en el log de seguridad; resend-code
  y forgot son 200 e idénticos exista o no la cuenta y solo entregan a las cuentas que toca (resend: no
  verificadas; forgot: verificadas y no borradas); forgot + reset cambia la contraseña; el 429 por cuenta y
  por IP de forgot no depende de que la cuenta exista; el camino «sin cuenta» gasta el bcrypt simulado;
  los cuerpos de éxito y el 409 de register no cambian.
- Un test existente cambia de aserción a propósito: `test_auth_verify_code_api.py::test_verify_code_cannot_be_replayed`
  (esperaba «Email ya verificado»; ahora «Código inválido o expirado») y sigue pasando; por nombre no hay
  diferencias en el resto.
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje (el resumen solo cambia en la cabecera).

El generador se validó antes de usarlo: sobre el `baseline_after.xml` anterior reproduce
`baseline_after_passed.txt` y `baseline_after_summary.txt` byte a byte.

## Documentación de la deuda de autenticación (P6): sin cambios de código desde P5; baseline vigente

La fase P6 solo toca documentación (`backend/docs/DEPLOYMENT_GUIDE.md` y `readme.md`): variables y límites
de autenticación, respuestas uniformes, `POST /api/auth/forgot`, `TRUSTED_PROXY_HOPS`, migración `0003` y
riesgos residuales. `git diff --name-only 771a7b8` (el commit de código de P5) solo lista ficheros `.md` y
los de esta carpeta: ningún `.py`, `.yml` ni `.env*` ha cambiado desde la suite de P5.

Por eso **no se regeneró** `baseline_after*` ni se lanzó la suite: los ficheros de esta carpeta siguen siendo
los de P5 y son la línea base vigente: `17 failed, 1737 passed, 1 skipped, 31 errors` (1786 tests).

Resumen de la deuda de autenticación (P0–P6): `1576 passed` al empezar → `1737 passed` al terminar
(+161 tests nuevos), con los mismos 48 fallos/errores ajenos (17 failed + 31 errors) y 0 tests que pasaban
y dejan de pasar en ninguna fase.

## Avisos de TRUSTED_PROXY_HOPS y variables de `.env.example` (R1 de la mitigación de riesgos abiertos)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código en el que `get_client_ip` avisa (una vez por proceso, con IPs
enmascaradas y sin cambiar la IP devuelta) cuando llega `X-Forwarded-For` con `TRUSTED_PROXY_HOPS=0`
fuera de desarrollo, y `validate_security_config` avisa al arrancar con `RENDER=true` y 0 saltos o con
`FORWARDED_ALLOW_IPS=*`. `.env.example` y la documentación no afectan a la suite.

Resultado: `17 failed, 1778 passed, 1 skipped, 31 errors` (1827 tests). Frente a la línea base anterior (1737 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+41 pasados**, todos nuevos y de `test_security.py`: `TestProxyHeaderTripwire` (16: una vez por
  proceso, IPs enmascaradas y sin la cabecera completa, ni con saltos de confianza, ni sin cabecera, ni
  en desarrollo, y el valor devuelto no cambia), `TestMaskIp` (11) y `TestProxyStartupWarnings` (14).
- `TestTrustedProxyHops`, `TestClientIPDetection` y `TestSmtpStartupWarning` pasan sin haberse tocado.
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje (el resumen solo cambia en la cabecera).

El generador se validó antes de usarlo: sobre el `baseline_after.xml` anterior reproduce
`baseline_after_passed.txt` y `baseline_after_summary.txt` byte a byte.

## El login cuenta solo los fallos (R2 de la mitigación de riesgos abiertos)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código en el que el límite por IP de `login` cuenta solo los fallos de
credenciales (usuario inexistente o contraseña errónea): `check_rate_limit_only` comprueba al entrar sin
contar y `record_failure` anota el fallo en la rama 401; el fallo número `RATE_LIMIT_LOGIN_ATTEMPTS` ya
bloquea (`record_failure_orm`, `>=`). El resto de rutas conserva su contador por petición.

Resultado: `17 failed, 1801 passed, 1 skipped, 31 errors` (1850 tests). Frente a la línea base anterior (1778 pasados):

- **0 tests que pasaban y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+23 pasados**, todos nuevos: `test_auth_rate_limits_api.py` (13: logins correctos que no gastan cupo, 429
  con `Retry-After` tras los fallos aunque el login sea correcto, la cuenta atrás no se reinicia con un
  acierto, ventana que vence, aislamiento por IP, `X-Forwarded-For` falsificado, el 423 y el 403 no
  cuentan, permisivo en desarrollo, fail-open y compatibilidad con `resend-code`) y
  `test_rate_limit_crud_orm.py` (10: `peek_limit_orm` y `record_failure_orm`).
- Ningún test existente cambia de aserción: los de límites de login enviaban usuarios inexistentes (401), que
  siguen contando como fallo.
- Los mismos 48 fallos/errores ajenos, uno a uno y con el mismo mensaje (el resumen solo cambia en la cabecera).

El generador se validó antes de usarlo: sobre el `baseline_after.xml` anterior reproduce
`baseline_after_passed.txt` y `baseline_after_summary.txt` byte a byte.
