# TASALO — Prompt de Continuidad para Agente

> **Generado:** 2026-03-21
> **Última actualización:** 2026-03-22 (Fase 4 completada)
> **Estado del Ecosistema:** taso-api 100% ✅ | taso-bot 67% 🚧 | taso-miniapp 0% ⏳ | taso-extension 0% ⏳

---

## 🎯 Contexto del Proyecto

**TASALO** es una plataforma distribuida para consultar tasas de cambio del dólar en Cuba en tiempo real. El ecosistema tiene 4 repositorios:

1. **taso-api** — Backend FastAPI, única pieza que habla con fuentes externas ✅ **COMPLETADO**
2. **taso-bot** — Bot de Telegram (python-telegram-bot) ⏳ **EN DESARROLLO**
3. **taso-miniapp** — Mini App web dentro de Telegram (Flask + Tailwind) ⏳ **PENDIENTE**
4. **taso-extension** — Extensión de navegador (Manifest V3) ⏳ **PENDIENTE**

**Arquitectura:**
```
ElToque API ──┐
CADECA ───────┤
BCC ──────────├──> taso-api (FastAPI + PostgreSQL) ──> Bot, MiniApp, Extension
Binance ──────┘
```

---

## 📁 Estado Actual de los Repositorios

### taso-api ✅ COMPLETADO

**Directorio:** `/home/ersus/tasalo/taso-api`

**Estado:** Fase 6 ✅ COMPLETADA - PROYECTO 100% COMPLETADO

**Tags:** `v1.0.0-fase1` ✅, `v1.1.0-fase2` ✅, `v1.2.0-fase3` ✅, `v1.3.0-fase4` ✅, `v1.4.0-fase5` ✅, `v1.5.0-fase6` ✅

**Resumen:**
- ✅ 4 scrapers funcionando (ElToque, CADECA, BCC, Binance)
- ✅ Scheduler corriendo cada 5 minutos con trackeo de estado
- ✅ 7 endpoints API REST (5 públicos + 2 admin protegidos)
- ✅ 58 tests pasando
- ✅ Exception handlers globales
- ✅ Logging estructurado
- ✅ README completo con guía de producción

**Ver:** `PROGRESS.md` para detalles completos de taso-api.

---

### taso-bot 🚧 EN DESARROLLO (Fase 4 Completada)

**Directorio:** `/home/ersus/tasalo/taso-bot`

**Estado:** Fase 4 ✅ COMPLETADA | Implementación: 4/6 fases (67%)

**Tags:** `v0.1.0-fase1` ✅, `v0.2.0-fase2` ✅, `v0.3.0-fase3` ✅, `v0.4.0-fase4` ✅

**Documento de Diseño:** `2026-03-22-tasalo-bot-design.md`

**Stack:** Python 3.12 · python-telegram-bot v21 · httpx · Pillow · pydantic-settings · aiohttp

**Fase 1 Completada:**
- ✅ Project scaffold creado con `uv`
- ✅ Configuración con pydantic-settings (4 tests)
- ✅ Cliente HTTP asíncrono con httpx (4 tests)
- ✅ Entry point del bot con polling (3 handlers)
- ✅ README completo con setup instructions
- ✅ 8 tests passing en total

**Fase 2 Completada:**
- ✅ `formatters.py` con bloques modernizados (ElToque, CADECA, BCC, Footer)
- ✅ `handlers/tasalo.py` con comando /tasalo modernizado
- ✅ Separadores unicode (━, ┈) e indicadores (🔺, 🔻, ―)
- ✅ Emojis de banderas para monedas (🇺🇸, 🇪🇺, 🧾, ₮)
- ✅ 37 tests nuevos para formatters.py
- ✅ 45 tests passing en total

**Fase 3 Completada:**
- ✅ `fonts/`: JetBrains Mono + Space Grotesk descargadas
- ✅ `image_generator.py`: Generador de imágenes con diseño TASALO (#5b8aff)
- ✅ Generación con timeout 5s + fallback a texto
- ✅ `handlers/tasalo.py`: Integración imagen + texto + botones
- ✅ Teclado inline con botones 🔄 Actualizar, 🗺 Ver provincias
- ✅ Callbacks: tasalo_refresh, tasalo_provincias, tasalo_back
- ✅ 24 tests nuevos para image_generator.py
- ✅ 69 tests passing en total

**Fase 4 Completada:**
- ✅ `api_client.get_history()` implementado (4 tests)
- ✅ `build_history_message()` formatter (6 tests)
- ✅ `history_callback()` handler (3 tests)
- ✅ `tasalo_refresh_callback()` con indicador visual
- ✅ `tasalo_back_callback()` navegación funcional
- ✅ 88 tests passing en total

**Próxima Acción:** Comenzar Fase 5 — Comandos Admin

---

### taso-miniapp ⏳ PENDIENTE

**Directorio:** `/home/ersus/tasalo/taso-miniapp`

**Estado:** No iniciado

**Documento de Diseño:** `2026-03-21-tasalo-miniapp-design.md`

**Stack:** Python 3.12 · Flask · Jinja2 · Tailwind CSS · Chart.js

---

### taso-extension ⏳ PENDIENTE

**Directorio:** `/home/ersus/tasalo/taso-extension`

**Estado:** No iniciado

**Documento de Diseño:** `2026-03-21-tasalo-extension-design.md`

**Stack:** JavaScript vanilla · Manifest V3 · CSS Variables

---

## 🎯 Próxima Acción Requerida

**IMPLEMENTAR TASO-BOT — FASE 5**

La Fase 4 del bot está completada (tag `v0.4.0-fase4`). Continuar con Fase 5:

1. **Fase 5:** Comandos Admin
   - Implementar `/refresh` y `/status` para administradores
   - Integrar con endpoints admin de taso-api
   - Agregar error handling global
   - Logging estructurado

2. **Fase 6:** Hardening y README
   - `.env.example` documentado
   - README completo con guía de producción

3. **Seguir TDD:** Tests primero (cuando aplique), implementación mínima, verificar, commit

4. **Actualizar PROGRESS.md** después de cada tarea completada

5. **Commits frecuentes** con mensajes descriptivos

---

## 📋 Documentos del Proyecto

Todos los documentos están en `/home/ersus/tasalo/plans/`:

### Diseño del Ecosistema
- `2026-03-21-tasalo-ecosystem-design.md` — Arquitectura general
- `2026-03-21-tasalo-api-design.md` — Diseño de taso-api
- `2026-03-22-tasalo-bot-design.md` — Diseño de taso-bot (nuevo ✅)
- `2026-03-21-tasalo-miniapp-design.md` — Diseño de taso-miniapp
- `2026-03-21-tasalo-extension-design.md` — Diseño de taso-extension

### Planes de Implementación
- `2026-03-21-taso-api-fase1.md` ✅
- `2026-03-21-taso-api-fase2-scrapers.md` ✅
- `2026-03-21-taso-api-fase3-scheduler.md` ✅
- `2026-03-22-taso-api-fase4-endpoints.md` ✅
- (Fases 5-6 completadas sin plan separado)

### Seguimiento
- `PROGRESS.md` — Progreso detallado por repositorio
- `CONTINUITY.md` — Este archivo

---

## 🚀 Comandos Útiles por Repositorio

### taso-api
```bash
cd /home/ersus/tasalo/taso-api
source .venv/bin/activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
pytest
```

### taso-bot (futuro)
```bash
cd /home/ersus/tasalo/taso-bot
uv venv
source .venv/bin/activate
python src/main.py
```

---

## 📊 Estado de Fases por Repositorio

| Repo | Fase 1 | Fase 2 | Fase 3 | Fase 4 | Fase 5 | Fase 6 | Total |
|------|--------|--------|--------|--------|--------|--------|-------|
| **taso-api** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 6/6 (100%) |
| **taso-bot** | ✅ | ✅ | ✅ | ✅ | ⏳ | ⏳ | 4/6 (67%) |
| **taso-miniapp** | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | 0/6 (0%) |
| **taso-extension** | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | — | 0/5 (0%) |

**Progreso Total del Ecosistema:** 10/23 fases (43%) 🚧

---

**Fin del documento de continuidad.**
