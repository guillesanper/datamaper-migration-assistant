# Query para Continuar con Fases de Seguridad

**Fecha**: 2025-01-04
**Estado actual**: FASE 1 (100% ✅) + FASE 2.1 (100% ✅)
**Próximo objetivo**: FASE 2.2 - Session Token Rotation

---

## 📋 Query para Copiar en Nuevo Chat

Copia el siguiente texto completo y pégalo en un nuevo chat con Claude Code:

```
Hola, necesito continuar con la implementación de mejoras de seguridad en el proyecto DataMap.

CONTEXTO DEL PROYECTO:
- Backend: FastAPI (Python) con sistema de encriptación AES-256-GCM + Argon2id
- Frontend: React + TypeScript
- Sistema: Encriptación de datos sensibles con passphrases de usuario

ESTADO ACTUAL DE SEGURIDAD:
✅ FASE 1 COMPLETADA (6/6 vulnerabilidades CRÍTICAS corregidas):
  - 1.1: Session tokens migrados a httpOnly cookies (antes: localStorage)
  - 1.2: User ID binding en sesiones (previene session hijacking)
  - 1.3: Exception sanitization (passphrases no van a logs)
  - 1.4: Key rotation deshabilitada (incompleta)
  - 1.5: Rate limiting implementado (5 intentos/10 min)
  - 1.6: CSRF protection verificado (SameSite=Strict cookies)

✅ FASE 2.1 COMPLETADA (1/6 vulnerabilidades ALTAS corregidas):
  - Memory protection: SecureBytes con 5-pass memory scrubbing
  - Archivo creado: backend/app/utils/secure_memory.py (450 líneas)
  - Archivo modificado: backend/app/utils/encryption_session_cache.py

📋 DOCUMENTACIÓN DISPONIBLE:
Lee estos archivos para entender el contexto completo:
1. docs/security/ROADMAP.md - Roadmap completo con estado de todas las fases
2. docs/security/FASE_1.1_HTTPONLY_COOKIES.md - Migración a httpOnly cookies
3. docs/security/FASE_1.6_CSRF_PROTECTION.md - Análisis CSRF protection
4. docs/security/FASE_2.1_MEMORY_PROTECTION.md - Memory protection con SecureBytes

ARQUITECTURA DE SEGURIDAD:
- Configuración: backend/app/config/security.py
- Middlewares: backend/app/middleware/ (csrf, encryption_session, rate_limiting)
- Utilidades: backend/app/utils/ (encryption_session_cache.py, secure_memory.py, rate_limiter.py, security_logger.py)

🎯 PRÓXIMA TAREA: FASE 2.2 - Session Token Rotation

OBJETIVO: Implementar rotación de session tokens para prevenir session fixation attacks.

ESTIMACIÓN: 3-4 horas

ARCHIVOS A MODIFICAR:
1. backend/app/utils/encryption_session_cache.py - Añadir método rotate_token()
2. backend/app/routers/encryption.py - Crear endpoint /refresh-session
3. frontend/src/providers/EncryptionProvider.tsx - Manejo transparente de rotación

IMPLEMENTACIÓN SUGERIDA:
Ver docs/security/ROADMAP.md líneas 80-151 para código de referencia.

Funcionalidades clave:
- rotate_token(old_token, grace_period_seconds=30) → new_token
- Grace period de 30s para manejar race conditions
- Token antiguo marcado como "rotating" con redirección al nuevo
- Rotación automática después de autenticación exitosa
- Endpoint POST /projects/{id}/encryption/refresh-session

REQUISITOS:
1. Mantener la arquitectura existente (usar security.py y middleware/)
2. Thread-safe (usar locks)
3. Backward compatible (no romper código existente)
4. Documentar en docs/security/FASE_2.2_SESSION_TOKEN_ROTATION.md
5. Incluir tests y ejemplos de uso
6. Logging adecuado (usando security_logger.py)

¿Puedes implementar la FASE 2.2 (Session Token Rotation) siguiendo estos lineamientos y documentándolo profesionalmente?
```

---

## 🎯 Instrucciones de Uso

1. **Copia** todo el texto entre las marcas de código (desde "Hola, necesito..." hasta "...documentándolo profesionalmente?")

2. **Pega** en un nuevo chat con Claude Code

3. Claude tendrá todo el contexto necesario para:
   - Entender el estado actual del proyecto
   - Saber qué archivos leer primero (ROADMAP.md, etc.)
   - Conocer la arquitectura de seguridad existente
   - Implementar la FASE 2.2 correctamente

4. **Validación previa** (opcional pero recomendado):
   ```bash
   cd backend
   python -m app.utils.secure_memory  # Verificar que SecureBytes funciona
   ```

---

## 📚 Fases Pendientes (Referencia Rápida)

Después de FASE 2.2, continuar con:

| Fase | Vulnerabilidad | Prioridad | Estimación |
|------|----------------|-----------|------------|
| **2.2** | Session token rotation | 🔴 Alta | 3-4h |
| **2.3** | Passphrase en memoria navegador | 🔴 Alta | 3h |
| **2.4** | Cross-tab session sharing inseguro | 🟡 Media | 3h |
| **2.5** | Validación de entropía tokens | 🟡 Media | 2h |
| **2.6** | Project IDs en logs sin hash | 🟡 Media | 2h |

Todas las fases tienen implementación sugerida en `ROADMAP.md`.

---

## 🔄 Modificaciones de la Query

Si necesitas ajustar la query para fases posteriores:

**Para FASE 2.3** (Passphrase cleanup):
Cambia la sección "PRÓXIMA TAREA" por:
```
🎯 PRÓXIMA TAREA: FASE 2.3 - Passphrase en Memoria del Navegador

OBJETIVO: Limpiar passphrase del estado de React después de uso.

ARCHIVOS A MODIFICAR:
- frontend/src/components/dashboard/modals/CreateProjectModal.tsx
- frontend/src/components/dashboard/modals/EditProjectModal.tsx
- frontend/src/components/mapping/modals/ColumnModal.tsx

Ver ROADMAP.md líneas 154-193 para implementación.
```

**Para FASE 2.4** (Cross-tab):
```
🎯 PRÓXIMA TAREA: FASE 2.4 - Cross-Tab Session Sharing

OBJETIVO: Firmar mensajes de BroadcastChannel con HMAC.

ARCHIVOS A MODIFICAR:
- frontend/src/providers/EncryptionProvider.tsx

Ver ROADMAP.md líneas 196-243 para implementación.
```

---

## ✅ Checklist de Continuación

Antes de empezar nuevo chat:

- [ ] ROADMAP.md está actualizado con el estado actual
- [ ] Todas las fases completadas tienen su FASE_X.X_NOMBRE.md
- [ ] Código actual funciona (tests pasando)
- [ ] Git commit de cambios actuales (opcional pero recomendado)
- [ ] Copiar query de arriba

---

**Creado por**: DataMap Security Team
**Última actualización**: 2025-01-04
