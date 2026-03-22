# TASALO — Progreso de Implementación del Ecosistema

> **Última actualización:** 2026-03-22
> **Estado General:** taso-api 100% ✅ | taso-bot 17% 🚧 | taso-miniapp 0% ⏳ | taso-extension 0% ⏳

---

## 📋 Visión General del Proyecto

**Objetivo:** Implementar **TASALO** — una plataforma distribuida para consultar tasas de cambio del dólar en Cuba en tiempo real. El ecosistema tiene 4 repositorios:

1. **taso-api** — Backend FastAPI, única pieza que habla con fuentes externas
2. **taso-bot** — Bot de Telegram (python-telegram-bot)
3. **taso-miniapp** — Mini App web dentro de Telegram (Flask + Tailwind)
4. **taso-extension** — Extensión de navegador (Manifest V3)

**Arquitectura:**
```
ElToque API ──┐
CADECA ───────┤
BCC ──────────├──> taso-api (FastAPI + PostgreSQL) ──> Bot, MiniApp, Extension
Binance ──────┘
```

---

## 📊 Estado por Repositorio

| Repositorio | Estado | Progreso | Última Actualización |
|-------------|--------|----------|---------------------|
| **taso-api** | ✅ Completado | 6/6 fases (100%) | 2026-03-22 |
| **taso-bot** | 🚧 En Progreso | 1/6 fases (17%) | 2026-03-22 (Fase 1 ✅) |
| **taso-miniapp** | ⏳ Pendiente | 0/6 fases (0%) | — |
| **taso-extension** | ⏳ Pendiente | 0/5 fases (0%) | — |

---

## 🚀 taso-api — Progreso Detallado

**Repositorio:** `tasalo/taso-api`
**Stack:** Python 3.12 · FastAPI · PostgreSQL/SQLite · SQLAlchemy async · Alembic · APScheduler

---

## ✅ Fase 1 — Scaffold y Base de Datos
**Estado:** **COMPLETADA** ✅
**Iniciado:** 2026-03-21
**Completado:** 2026-03-21
**Tag:** `v1.0.0-fase1`

**Objetivo:** Repositorio funcional con conexión a base de datos y endpoint de health check.

**Resultados:**
- ✅ 11 tests pasando
- ✅ Servidor corre en `http://localhost:8000`
- ✅ `GET /api/v1/health` devuelve `{"ok": true, "db": "connected"}`
- ✅ Swagger UI disponible en `/docs`
- ✅ Alembic configurado con SQLite (dev) y PostgreSQL (prod)
- ✅ Tag `v1.0.0-fase1` creado

---

## ✅ Fase 2 — Scrapers
**Estado:** **COMPLETADA** ✅
**Iniciado:** 2026-03-21
**Completado:** 2026-03-21
**Tag:** `v1.1.0-fase2`

**Objetivo:** Los 4 scrapers/clientes funcionando como funciones independientes testeables.

**Resultados:**
- ✅ `scrapers/eltoque.py` — Cliente API ElToque con httpx y Bearer token (5 tests)
- ✅ `scrapers/binance.py` — Cliente API Binance para pares BTCUSDT, ETHUSDT, USDTUSDT (4 tests)
- ✅ `scrapers/cadeca.py` — Scraper CADECA con httpx + HTMLParser (4 tests)
- ✅ `scrapers/bcc.py` — Scraper BCC con httpx + HTMLParser (4 tests)
- ✅ 17 tests pasando en total
- ✅ Test manual de integración disponible en `scripts/test_scrapers_manual.py`

**Código migrado desde legacy:**
- Lógica de `obtener_tasas_eltoque()` → `fetch_eltoque()` (async)
- Estructura de datos normalizada
- Manejo de errores robustecido

---

## ✅ Fase 3 — Servicio de Tasas y Scheduler
**Estado:** **COMPLETADA** ✅
**Iniciado:** 2026-03-22
**Completado:** 2026-03-22
**Tag:** `v1.2.0-fase3`

**Objetivo:** El backend recoge datos automáticamente y los persiste en PostgreSQL.

**Resultados:**
- ✅ `services/rates_service.py` — Servicio de negocio implementado
- ✅ `fetch_all_sources()` — Ejecuta los 4 scrapers en paralelo con timeouts individuales (2 tests)
- ✅ `save_snapshot()` — Persiste datos con normalización por fuente (2 tests)
- ✅ `get_latest_rates()` — Consulta últimos snapshots por fuente (2 tests)
- ✅ `calculate_change()` — Determina up/down/neutral con tolerancia 0.0001 (4 tests)
- ✅ `services/scheduler.py` — APScheduler configurado con job `refresh_all` (2 tests)
- ✅ Job `refresh_all` corre cada 5 minutos automáticamente
- ✅ Scheduler integrado en FastAPI lifespan (startup/shutdown)
- ✅ 12 tests nuevos pasando
- ✅ Tag `v1.2.0-fase3` creado

**Legacy patterns reutilizados:**
- Timeout individual por scraper (evita que uno lento bloquee todo)
- Tolerancia 0.0001 para calcular cambios 🔺/🔻
- Normalización de datos por fuente (ElToque vs CADECA vs BCC vs Binance)

---

## ✅ Fase 4 — Endpoints Públicos
**Estado:** **COMPLETADA** ✅
**Iniciado:** 2026-03-22
**Completado:** 2026-03-22
**Tag:** `v1.3.0-fase4`

**Objetivo:** API consumible por los servicios clientes.

**Resultados:**
- ✅ `schemas/rates.py` — 6 Pydantic schemas implementados (CurrencyRate, SourceRatesResponse, LatestRatesResponse, HistoryResponse, etc.)
- ✅ `routers/rates.py` — 5 endpoints públicos implementados:
  - `GET /api/v1/tasas/latest` — Tasas combinadas de todas las fuentes con indicadores de cambio
  - `GET /api/v1/tasas/eltoque` — Solo tasas de ElToque
  - `GET /api/v1/tasas/cadeca` — Solo tasas de CADECA
  - `GET /api/v1/tasas/bcc` — Solo tasas de BCC
  - `GET /api/v1/tasas/history` — Histórico con query params (source, currency, days)
- ✅ `services/rates_service.py` — Funciones `get_source_rates()` y `get_history()` agregadas
- ✅ `database.py` — Dependency provider `get_db()` agregado
- ✅ CORS middleware configurado en `main.py`
- ✅ 10 tests nuevos de integración para routers
- ✅ 50 tests pasando en total
- ✅ Tag `v1.3.0-fase4` creado

**Endpoints verificados:**
- Swagger UI disponible en `/docs`
- Respuestas JSON con estructura consistente `{ok, data, updated_at}`
- Indicadores de cambio (up/down/neutral) calculados con tolerancia 0.0001
- Query params validados (days: 1-365)

---

## ✅ Fase 5 — Endpoints Admin y Auth
**Estado:** **COMPLETADA** ✅
**Iniciado:** 2026-03-22
**Completado:** 2026-03-22
**Tag:** `v1.4.0-fase5`

**Objetivo:** Endpoints protegidos para operaciones privilegiadas.

**Resultados:**
- ✅ `middleware/auth.py` — Dependencia FastAPI que valida header `X-API-Key` (2 tests)
  - Retorna 401 si la key es inválida o faltante
  - Usa `APIKeyHeader` de FastAPI
- ✅ `routers/admin.py` — 2 endpoints admin implementados:
  - `POST /api/v1/admin/refresh` — Dispara fetch inmediato de todas las fuentes (1 test)
  - `GET /api/v1/admin/status` — Devuelve estado del scheduler desde `SchedulerStatus` (2 tests)
- ✅ `schemas/admin.py` — 5 Pydantic schemas implementados:
  - `SchedulerStatusResponse`, `AdminStatusResponse`, `RefreshResult`, `RefreshData`, `RefreshResponse`
- ✅ `services/scheduler.py` — Actualizado para trackear estado en `scheduler_status`:
  - Actualiza `last_run_at`, `last_success_at`, `error_count`, `last_error`
  - Manejo de errores con rollback y actualización de estado
- ✅ 8 tests nuevos pasando
- ✅ 58 tests pasando en total
- ✅ Tag `v1.4.0-fase5` creado

**Endpoints protegidos:**
- Todos los endpoints `/api/v1/admin/*` requieren header `X-API-Key`
- API key se configura vía `ADMIN_API_KEY` en `.env`
- Swagger UI muestra los endpoints protegidos con símbolo de candado

---

## ✅ Fase 6 — Hardening y README
**Estado:** **COMPLETADA** ✅
**Iniciado:** 2026-03-22
**Completado:** 2026-03-22
**Tag:** `v1.5.0-fase6`

**Objetivo:** El servicio está listo para producción básica.

**Resultados:**
- ✅ `main.py` — Exception handlers globales implementados (3 handlers)
  - `http_exception_handler` — Maneja HTTPException (4xx, 5xx) con logging warning
  - `validation_exception_handler` — Maneja RequestValidationError (422) con detalles formateados
  - `general_exception_handler` — Manejo Exception general (500) con stack trace en logs
- ✅ `main.py` — Logging estructurado configurado
  - Formato: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
  - Output: stdout con timestamps legibles
  - Nivel: INFO por defecto
  - logger dedicado para la aplicación
- ✅ `.env.example` — Documentación exhaustiva con comentarios
  - Secciones organizadas por categoría (Database, ElToque, Security, Scheduler, CORS)
  - Comentarios explicativos para cada variable
  - Valores por defecto y rangos válidos documentados
  - Ejemplos de uso para desarrollo y producción
- ✅ `README.md` — Documentación final completa
  - Requisitos del sistema (mínimos y recomendados)
  - Instalación paso a paso con uv y pip
  - Configuración de variables de entorno
  - 7 endpoints documentados con ejemplos de curl y respuestas JSON
  - Migraciones de base de datos explicadas
  - Testing y comandos útiles
  - Estructura del proyecto detallada
  - Guía de despliegue en producción (systemd, nginx)
  - Solución de problemas comunes
- ✅ Versión actualizada a `1.5.0` en main.py
- ✅ Tag `v1.5.0-fase6` creado

**Criterio de éxito:** ✅ Un desarrollador nuevo puede clonar el repo, copiar `.env`, correr migraciones y levantar el servidor siguiendo solo el README.

---

## 📊 Métricas

| Métrica | Valor |
|---------|-------|
| Total fases | 6 |
| Fases completadas | 6/6 ✅ |
| Progreso total | 100% 🎉 |
| Tests escritos | 58 (28 base + 12 services + 10 rates + 8 admin) |
| Endpoints implementados | 7/7 ✅ |
| Scrapers implementados | 4/4 ✅ |
| Servicio de negocio | ✅ Completo |
| Scheduler | ✅ Corriendo cada 5 min + trackeo de estado |
| Endpoints públicos | ✅ 5 endpoints |
| Endpoints admin | ✅ 2 endpoints (protegidos) |
| CORS configurado | ✅ |
| Auth middleware | ✅ Implementado |
| Exception handlers | ✅ 3 handlers globales |
| Logging estructurado | ✅ Configurado |
| README | ✅ Completo con ejemplos |

---

## 🐛 Issues y Bloqueos

| Fecha | Issue | Estado | Resolución |
|-------|-------|--------|------------|
| — | — | — | — |

---

## 📝 Notas de Desarrollo

### 2026-03-21 - Fase 1 Completada

- [x] Diseño de implementación aprobado
- [x] Plan de Fase 1 creado
- [x] Archivos de seguimiento creados: `PROGRESS.md`, `CONTINUITY.md`
- [x] **Task 1:** Estructura de directorios y archivos base completada
- [x] **Task 2:** Configuración con Pydantic Settings completada
- [x] **Task 3:** Modelos de Base de Datos completados
- [x] **Task 4:** Alembic configurado para migraciones async
- [x] **Task 5:** FastAPI app con endpoint /health completada
- [x] **Task 6:** README documentado
- [x] **Task 7:** Verificación final completada
  - 11 tests pasando
  - Servidor verificado en `http://localhost:8000`
  - Tag `v1.0.0-fase1` creado

**Próximos pasos:** Comenzar Fase 3 — Servicio de Tasas y Scheduler (orquestar scrapers, persistencia en PostgreSQL, APScheduler)

---

### 2026-03-21 - Fase 2 Completada

- [x] Plan de Fase 2 creado: `2026-03-21-taso-api-fase2-scrapers.md`
- [x] **Task 1:** Directorio de scrapers y test utils completado
- [x] **Task 2:** Scraper ElToque completado (5 tests passing)
- [x] **Task 3:** Scraper Binance completado (4 tests passing)
- [x] **Task 4:** Scraper CADECA completado (4 tests passing)
- [x] **Task 5:** Scraper BCC completado (4 tests passing)
- [x] **Task 6:** Test manual y PROGRESS.md actualizado
- [x] 17 tests nuevos pasando
- [x] Tag `v1.1.0-fase2` creado

**Próximos pasos:** Comenzar Fase 3 — Servicio de Tasas y Scheduler (orquestar scrapers, persistencia en PostgreSQL, APScheduler)

---

### 2026-03-22 - Fase 3 Completada

- [x] Plan de Fase 3 creado: `2026-03-21-taso-api-fase3-scheduler.md`
- [x] **Task 1:** Directorio services/ creado
- [x] **Task 2:** `fetch_all_sources()` implementado con paralelismo y timeouts (2 tests)
- [x] **Task 3:** `save_snapshot()` implementado con normalización por fuente (2 tests)
- [x] **Task 4:** `get_latest_rates()` implementado con subquery max(fetched_at) (2 tests)
- [x] **Task 5:** `calculate_change()` implementado con tolerancia 0.0001 (4 tests)
- [x] **Task 6:** `scheduler.py` configurado con APScheduler (2 tests)
- [x] **Task 7:** Scheduler integrado en FastAPI lifespan
- [x] **Task 8:** Verificación final completada
  - 40 tests pasando
  - Scheduler corriendo cada 5 minutos
  - DB con registros de eltoque y cadeca
  - Tag `v1.2.0-fase3` creado y pusheado
- [x] PROGRESS.md actualizado

**Próximos pasos:** Comenzar Fase 4 — Endpoints Públicos (GET /api/v1/tasas/*)

---

### 2026-03-22 - Fase 4 Completada

- [x] Plan de Fase 4 creado: `2026-03-22-taso-api-fase4-endpoints.md`
- [x] **Task 1:** Schemas Pydantic completados (6 schemas en `schemas/rates.py`)
- [x] **Task 2:** Router de Tasas completado (5 endpoints en `routers/rates.py`)
- [x] **Task 3:** CORS configurado en `main.py`
- [x] **Task 4:** Tests de endpoints completados (10 tests nuevos)
- [x] **Task 5:** Verificación final completada
  - 50 tests pasando
  - Endpoints verificados manualmente con curl
  - Swagger UI disponible en `/docs`
  - Tag `v1.3.0-fase4` creado
- [x] PROGRESS.md y CONTINUITY.md actualizados

**Próximos pasos:** Comenzar Fase 5 — Endpoints Admin y Auth (POST /api/v1/admin/refresh, GET /api/v1/admin/status)

---

### 2026-03-22 - Fase 5 Completada

- [x] **Task 1:** `middleware/auth.py` implementado con validación X-API-Key (2 tests)
- [x] **Task 2:** `schemas/admin.py` con 5 schemas Pydantic
- [x] **Task 3:** `routers/admin.py` con 2 endpoints admin (POST /refresh, GET /status)
- [x] **Task 4:** `services/scheduler.py` actualizado para trackear estado en DB
- [x] **Task 5:** Router admin registrado en `main.py` con dependencia de auth
- [x] **Task 6:** 8 tests nuevos escritos y pasando
- [x] **Task 7:** Verificación final completada
  - 58 tests pasando en total
  - Endpoints admin protegidos con API key
  - Scheduler status se actualiza en cada ejecución
  - Tag `v1.4.0-fase5` creado
- [x] PROGRESS.md y CONTINUITY.md actualizados

**Próximos pasos:** Comenzar Fase 6 — Hardening y README (exception handlers, logging, documentación)

---

### 2026-03-22 - Fase 6 Completada

- [x] **Task 1:** Exception handlers globales implementados en `main.py` (3 handlers)
  - `http_exception_handler` — Maneja HTTPException con logging warning
  - `validation_exception_handler` — Maneja RequestValidationError con detalles formateados
  - `general_exception_handler` — Maneja Exception general con stack trace
- [x] **Task 2:** Logging estructurado configurado
  - Formato estructurado con timestamp, nivel, logger y mensaje
  - Output a stdout
  - logger dedicado para la aplicación
- [x] **Task 3:** `.env.example` documentado con comentarios exhaustivos
  - Secciones por categoría (Database, ElToque, Security, Scheduler, CORS)
  - Comentarios explicativos por variable
  - Ejemplos de desarrollo y producción
- [x] **Task 4:** README final completado
  - Requisitos del sistema
  - Instalación paso a paso
  - 7 endpoints documentados con ejemplos
  - Guía de despliegue en producción
  - Solución de problemas comunes
- [x] **Task 5:** Verificación final completada
  - 58 tests pasando
  - Versión actualizada a 1.5.0
  - Tag `v1.5.0-fase6` creado
  - **Push a GitHub completado:** `origin/dev` + tags `v1.4.0-fase5`, `v1.5.0-fase6`
  - PROGRESS.md y CONTINUITY.md actualizados

**Próximos pasos:** Proyecto completado (6/6 fases). Listo para producción.

---

## 🔗 Enlaces Relacionados

- **Plan de Implementación:** `/home/ersus/tasalo/plans/2026-03-21-taso-api-fase1.md`
- **Diseño Original:** `/home/ersus/tasalo/plans/2026-03-21-tasalo-api-design.md`
- **Continuidad del Agente:** `/home/ersus/tasalo/plans/CONTINUITY.md`
- **Repositorio GitHub:** https://github.com/tasalo/taso-api

---

## 🤖 taso-bot — Progreso Detallado

**Repositorio:** `tasalo/taso-bot`
**Stack:** Python 3.12 · python-telegram-bot v21 · httpx · Pillow · pydantic-settings

### ✅ Fase 1 — Diseño Aprobado
**Estado:** **COMPLETADA** ✅
**Fecha:** 2026-03-22

**Objetivo:** Documento de diseño completo con especificaciones visuales y de formato.

**Resultados:**
- ✅ Diseño visual modernizado alineado con TASALO design system
- ✅ Formato de texto mejorado (unicode separators, flag emojis, consistent spacing)
- ✅ Especificación de imagen con colores del design system (`#5b8aff` accent)
- ✅ Fuentes bundeadas: JetBrains Mono + Space Grotesk
- ✅ Diseño de comandos y callbacks definido
- ✅ Documento: `2026-03-22-tasalo-bot-design.md`

**Próximos pasos:** Comenzar Fase 1 de implementación — Scaffold y conexión con taso-api

---

### ✅ Fase 1 — Scaffold y Conexión con el Backend
**Estado:** **COMPLETADA** ✅
**Iniciado:** 2026-03-22
**Completado:** 2026-03-22
**Tag:** `v0.1.0-fase1`

**Objetivo:** Bot que arranca y puede hablar con `taso-api`.

**Resultados:**
- ✅ Project scaffold creado con `uv`
- ✅ Configuración con pydantic-settings (4 tests passing)
- ✅ Cliente HTTP asíncrono con httpx (4 tests passing)
- ✅ Entry point del bot con polling (3 handlers: start, tasalo, health)
- ✅ README completo con setup instructions
- ✅ 8 tests passing en total
- ✅ Tag `v0.1.0-fase1` creado y pusheado

**Criterio de éxito:** ✅ El bot está online y la llamada al backend funciona.

**Próximos pasos:** Comenzar Fase 2 — Comando /tasalo con formato de texto modernizado

---

### ✅ Fase 2 — Comando /tasalo (solo texto)
**Estado:** **COMPLETADA** ✅
**Iniciado:** 2026-03-22
**Completado:** 2026-03-22
**Tag:** `v0.2.0-fase2`

**Objetivo:** El bot responde con el texto formateado con diseño modernizado.

**Resultados:**
- ✅ `formatters.py` implementado con 5 funciones principales
  - `build_eltoque_block()`: Bloque mercado informal con emojis de banderas (🇺🇸, 🇪🇺, 🧾, ₮)
  - `build_cadeca_block()`: Bloque CADECA con formato de columnas (Buy/Sell)
  - `build_bcc_block()`: Bloque BCC oficial
  - `build_footer()`: Footer con timestamp y fuentes
  - `build_full_message()`: Combina todos los bloques
- ✅ Separadores unicode modernizados (━, ┈)
- ✅ Indicadores de cambio (🔺 up, 🔻 down, ― neutral)
- ✅ `handlers/tasalo.py`: Handler del comando /tasalo modernizado
- ✅ `main.py` actualizado para usar handler desde handlers/
- ✅ 37 tests nuevos para formatters.py
- ✅ 45 tests passing en total
- ✅ Tag `v0.2.0-fase2` creado y pusheado

**Criterio de éxito:** ✅ `/tasalo` devuelve los 3 bloques de texto formateados correctamente.

**Próximos pasos:** Comenzar Fase 3 — Generador de Imagen Pillow

---

### ⏳ Fase 3 — Generador de Imagen Pillow
**Estado:** ⏳ Pendiente

- [ ] Descargar fuentes Google Fonts a `fonts/`
- [ ] Implementar `image_generator.py` con diseño TASALO
- [ ] Integrar con handler (generación en paralelo)
- [ ] Fallback a texto si imagen falla
- [ ] Agregar teclado inline

**Criterio de éxito:** `/tasalo` envía imagen + texto + botones.

---

### ⏳ Fase 4 — Callbacks Inline
**Estado:** ⏳ Pendiente

- [ ] Implementar callback `tasalo_refresh`
- [ ] Implementar callback `tasalo_provincias`
- [ ] Registrar `CallbackQueryHandler`

**Criterio de éxito:** Botones 🔄 y 🗺 funcionan correctamente.

---

### ⏳ Fase 5 — Comandos Admin
**Estado:** ⏳ Pendiente

- [ ] Implementar `handlers/admin.py`
- [ ] Implementar métodos admin en `api_client.py`
- [ ] Registrar handlers

**Criterio de éxito:** `/refresh` y `/status` funcionan para admins.

---

### ⏳ Fase 6 — Hardening y README
**Estado:** ⏳ Pendiente

- [ ] Error handling global
- [ ] Logging estructurado
- [ ] `.env.example` documentado
- [ ] README completo

**Criterio de éxito:** Bot estable con errores logueados.

---

## 📝 Notas de Desarrollo — taso-bot

### 2026-03-22 - TASALO-Bot Fase 2 Completada

- [x] Diseño de TASALO-Bot aprobado (2026-03-22)
- [x] Plan de Fase 2 completado
- [x] **Task 1:** `formatters.py` implementado con bloques modernizados
- [x] **Task 2:** `handlers/tasalo.py` implementado
- [x] **Task 3:** Handler registrado en `main.py`
- [x] **Task 4:** 37 tests para formatters.py (todos passing)
- [x] **Task 5:** Commit `faf4a7e` creado y pusheado
- [x] Tag `v0.2.0-fase2` creado
- [x] PROGRESS.md y CONTINUITY.md actualizados
- [x] 45 tests passing en total

**Próximos pasos:** Comenzar Fase 3 — Generador de Imagen Pillow (JetBrains Mono + Space Grotesk, diseño TASALO con accent #5b8aff)

---

### 2026-03-22 - TASALO-Bot Fase 1 Completada

- [x] Diseño de TASALO-Bot aprobado (2026-03-22)
- [x] Plan de Fase 1 creado: `2026-03-22-taso-bot-fase1-scaffold.md`
- [x] **Task 1:** Estructura de directorios y archivos base completada (commit `45ee5c8`)
- [x] **Task 2:** Configuración con Pydantic Settings completada (commit `2287b28`, 4 tests)
- [x] **Task 3:** Cliente HTTP Asíncrono completado (commit `46c2e1c`, 4 tests)
- [x] **Task 4:** Entry Point del Bot completado (commit `cd6fff6`)
- [x] **Task 5:** README y Verificación Final completados (commit `f458afa`)
- [x] 8 tests pasando en total
- [x] Tag `v0.1.0-fase1` creado
- [x] PROGRESS.md y CONTINUITY.md actualizados

**Próximos pasos:** Comenzar Fase 2 — Comando /tasalo con formato de texto modernizado
