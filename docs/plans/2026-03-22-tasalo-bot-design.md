# TASALO-BOT — Diseño y Plan de Implementación

**Fecha:** 2026-03-22
**Versión:** 2.0 (Clean Rewrite)
**Repositorio:** `tasalo/taso-bot`
**Stack:** Python 3.12 · python-telegram-bot v21 · httpx · Pillow · pydantic-settings

---

## 1. Responsabilidad

`taso-bot` es el cliente de Telegram del ecosistema TASALO. Consume la API de `taso-api` para obtener tasas de cambio, genera una imagen visual con Pillow y la envía al usuario con texto formateado y botones inline. No tiene lógica de scraping ni de almacenamiento propio — toda esa responsabilidad vive en el backend.

Es una **reescritura limpia** del módulo `/tasa` del bot BBAlert existente, eliminando las dependencias de scrapers locales y managers de historial JSON.

---

## 2. Estructura de Directorios

```
taso-bot/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── fonts/
│   ├── JetBrainsMono-Regular.ttf
│   └── SpaceGrotesk-Regular.ttf
├── docs/plans/
│   └── 2026-03-22-tasalo-bot-design.md
└── src/
    ├── main.py              # Punto de entrada, registro de handlers
    ├── config.py            # Variables de entorno (pydantic-settings)
    ├── api_client.py        # Cliente httpx para taso-api
    ├── handlers/
    │   ├── tasalo.py        # Comando /tasalo, callbacks inline
    │   └── admin.py         # Comandos de administrador (/refresh, /status)
    ├── image_generator.py   # Generación de imagen con Pillow (nuevo diseño)
    └── formatters.py        # Funciones de formateo de texto Markdown
```

---

## 3. Comandos del Bot

| Comando | Descripción | Disponibilidad |
|---------|-------------|----------------|
| `/tasalo` | Muestra imagen + texto con tasas actuales (ElToque, CADECA, BCC) | Todos los usuarios |
| `/refresh` | Fuerza refresco inmediato de las tasas en el backend | Solo admins |
| `/status` | Muestra estado del scheduler y última actualización | Solo admins |

---

## 4. Flujo del Comando Principal `/tasalo`

```
Usuario: /tasalo
    │
    ▼
bot envía mensaje "⏳ Consultando tasas..."
    │
    ▼
api_client.get_latest()  →  GET taso-api/api/v1/tasas/latest
    │
    ├─ Error / timeout  →  editar mensaje con error amigable
    │
    ▼
formatters.build_text(data)     →  texto Markdown con 3 bloques
image_generator.generate(data)  →  BytesIO con imagen Pillow (en paralelo)
    │
    ▼
bot.send_photo(image, caption=texto, reply_markup=teclado)
    │
    ▼
Teclado inline:
  [🗺 Ver tasas provinciales]  →  callback: tasalo_provincias
  [🔄 Actualizar]              →  callback: tasalo_refresh
```

---

## 5. Formato del Mensaje de Texto (Modernizado)

El texto mantiene la estructura del bot BBAlert pero con formato modernizado:

```
📊 *Mercado Informal (El Toque)*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇺🇸 USD  365.00 CUP  🔺 +5.00
🇪🇺 EUR  398.00 CUP  ―
🧾 MLC  210.00 CUP  🔻 -5.00
₮ USDT  362.00 CUP  ―

┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

🏢 *CADECA* — Airports, Ports, Hotels
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Currency      Buy      Sell
USD          120.00   125.00
EUR          130.00   136.00

┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

🏛 *Banco Central (BCC)*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USD   24.00 CUP
EUR   26.50 CUP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📆 2026-03-22 14:30
🔗 elToque.com · cadeca.cu · bc.gob.cu
```

**Mejoras vs legacy:**
- Caracteres unicode (`━`, `┈`) para separadores más limpios
- Emojis de banderas para monedas (🇺🇸, 🇪🇺)
- Indicador neutral (`―`) cuando no hay cambio
- Espaciado consistente con alineación monospace
- Footer simplificado con timestamp y fuentes en una línea

Los indicadores 🔺🔻 vienen directamente del campo `change` de la respuesta de `taso-api` — el bot no calcula nada, solo formatea.

---

## 6. Generador de Imagen (Pillow) — Nuevo Diseño TASALO

### Tokens de Diseño (desde Extension Design System)

```python
# Colores
COLOR_BG = "#09091e"           # Fondo oscuro
COLOR_ACCENT = "#5b8aff"       # Azul eléctrico principal
COLOR_TEXT = "#eeeef8"         # Texto primario
COLOR_TEXT2 = "#9090c0"        # Texto secundario
COLOR_UP = "#ff6b6b"           # Precio sube 🔺
COLOR_DOWN = "#4ade80"         # Precio baja 🔻

# Tipografía
FONT_MONO = "JetBrains Mono"   # Números/tasas
FONT_UI = "Space Grotesk"      # Textos de interfaz

# Layout
CORNER_RADIUS = 12
GLASS_BLUR = 20
```

### Layout de la Imagen

```
┌──────────────────────────────────────┐
│  💱 TASALO                      14:30│  ← Header con logo + timestamp
│  ═══════════════════════════════════│  ← Línea de acento (#5b8aff)
├──────────────────────────────────────┤
│  📊 MERCADO INFORMAL (El Toque)      │
│  ┌────────────────────────────────┐  │
│  │ USD    365.00 CUP        🔺 +5  │  │
│  │ EUR    398.00 CUP              │  │
│  │ MLC    210.00 CUP        🔻 -5  │  │
│  │ USDT   362.00 CUP              │  │
│  └────────────────────────────────┘  │
├──────────────────────────────────────┤
│  🏢 CADECA                           │
│  │ Currency │  Buy   │  Sell  │     │
│  │   USD    │ 120.00 │ 125.00 │     │
│  │   EUR    │ 130.00 │ 136.00 │     │
├──────────────────────────────────────┤
│  🏛 BCC OFICIAL                      │
│  │ USD    24.00 CUP                  │
│  │ EUR    26.50 CUP                  │
└──────────────────────────────────────┘
   📆 2026-03-22 14:30 | elToque.com
```

### Diferencias vs Legacy

| Aspecto | Legacy (BBAlert) | TASALO (New) |
|---------|-----------------|--------------|
| Background | Template image (jpg) | Gradiente programático (`#09091e` → más oscuro) |
| Accent | Dark blue (`#0B1E38`) | Electric blue (`#5b8aff`) |
| Font | Arial/DejaVu | JetBrains Mono + Space Grotesk (bundled) |
| Layout | Posiciones fijas | Dinámico basado en contenido |
| Branding | "BitBread Alerts" | "💱 TASALO" |
| Indicators | 🔺🔻 en texto | Colores del design system |

### Manejo de Fuentes

Las fuentes JetBrains Mono y Space Grotesk se descargan y bundlean en el directorio `fonts/` para garantizar renderizado consistente en todos los sistemas.

---

## 7. Cliente API

```python
# api_client.py
class TasaloApiClient:
    async def get_latest(self) -> dict | None
    async def get_history(self, source: str, days: int = 7) -> list | None
    async def admin_refresh(self) -> dict | None   # requiere ADMIN_API_KEY
    async def admin_status(self) -> dict | None    # requiere ADMIN_API_KEY
```

Todos los métodos usan `httpx.AsyncClient` con timeout configurable. En caso de error devuelven `None` — el handler decide qué mostrar al usuario.

---

## 8. Variables de Entorno

```bash
# .env.example

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_CHAT_IDS=123456789,987654321   # IDs separados por coma

# Backend
TASALO_API_URL=http://localhost:8000
TASALO_ADMIN_KEY=your_admin_key_here  # mismo valor que ADMIN_API_KEY en taso-api

# Timeouts
API_TIMEOUT_SECONDS=15
```

---

## 9. Fases de Implementación

### Fase 1 — Scaffold y Conexión con el Backend
**Objetivo:** Bot que arranca y puede hablar con `taso-api`.

- [ ] Crear repositorio `taso-bot` en GitHub
- [ ] Inicializar proyecto Python 3.12 con `uv venv`
- [ ] Crear `requirements.txt` con dependencias base
- [ ] Configurar `config.py` con pydantic-settings
- [ ] Implementar `api_client.py` con el método `get_latest()` usando httpx async
- [ ] Crear `main.py` con el setup mínimo de python-telegram-bot (Application builder, polling)
- [ ] Verificar en consola que el bot arranca y `api_client.get_latest()` devuelve datos reales del backend

**Criterio de éxito:** El bot está online en Telegram y la llamada al backend funciona.

---

### Fase 2 — Comando /tasalo (solo texto)
**Objetivo:** El bot responde con el texto formateado, sin imagen todavía.

- [ ] Implementar `formatters.py`:
  - `build_eltoque_block(data)` → bloque mercado informal
  - `build_cadeca_block(data)` → bloque CADECA con columnas
  - `build_bcc_block(data)` → bloque BCC oficial
  - `build_footer(updated_at)` → pie de mensaje con timestamp y fuentes
  - `build_full_message(data)` → combina los 4 bloques
- [ ] Implementar `handlers/tasalo.py`:
  - Handler del comando `/tasalo`
  - Envía mensaje de estado "⏳ Consultando..."
  - Llama `api_client.get_latest()`
  - Formatea con `formatters.build_full_message()`
  - Edita el mensaje de estado con el texto final
  - Manejo de error si el backend no responde
- [ ] Registrar handler en `main.py`
- [ ] Probar en Telegram: el comando muestra texto correcto con indicadores 🔺🔻

**Criterio de éxito:** `/tasalo` en Telegram devuelve los 3 bloques de texto formateados correctamente.

---

### Fase 3 — Generador de Imagen Pillow
**Objetivo:** El comando envía imagen + texto como en el bot original.

- [ ] Descargar fuentes Google Fonts (JetBrains Mono, Space Grotesk) a `fonts/`
- [ ] Implementar `image_generator.py`:
  - Fondo con gradiente oscuro (`#09091e` → más oscuro)
  - Línea de acento `#5b8aff` en header
  - Tipografía JetBrains Mono para números
  - Space Grotesk para labels
  - Indicadores de color: `#ff6b6b` (sube), `#4ade80` (baja)
  - Logo "💱 TASALO" en esquina
  - Timestamp de última actualización
- [ ] Generar imagen como `BytesIO` sin escribir a disco
- [ ] Actualizar `handlers/tasalo.py`:
  - Ejecutar `image_generator.generate(data)` en paralelo con el formateo de texto
  - Si la imagen está lista: `send_photo(image, caption=texto)`
  - Si la imagen falla (timeout 5s): `send_message(texto)` como fallback
- [ ] Agregar teclado inline con botones 🗺 y 🔄

**Criterio de éxito:** `/tasalo` envía una imagen con el caption de texto y los dos botones.

---

### Fase 4 — Callbacks Inline
**Objetivo:** Los botones del teclado funcionan correctamente.

- [ ] Implementar callback `tasalo_refresh`:
  - Re-llama `api_client.get_latest()` y edita el mensaje existente
  - Si el mensaje tiene foto: edita el caption
  - Si no tiene foto: edita el texto
- [ ] Implementar callback `tasalo_provincias`:
  - Llama `api_client.get_latest()` y extrae datos provinciales si existen
  - Muestra lista simple de tasas por provincia (formato: `📍 *Provincia:* XXX CUP`)
  - Botón "🔙 Volver" que regresa a la vista nacional
- [ ] Registrar `CallbackQueryHandler` para ambos patterns en `main.py`

**Criterio de éxito:** Los botones 🔄 y 🗺 funcionan correctamente desde el mensaje enviado.

---

### Fase 5 — Comandos Admin
**Objetivo:** El administrador puede operar el backend desde Telegram.

- [ ] Implementar `handlers/admin.py`:
  - `/refresh` → llama `api_client.admin_refresh()`, responde con confirmación y timestamp
  - `/status` → llama `api_client.admin_status()`, muestra estado del scheduler
  - Ambos verifican que el `user_id` está en `ADMIN_CHAT_IDS`
- [ ] Implementar `api_client.admin_refresh()` y `api_client.admin_status()` con `X-API-Key`
- [ ] Registrar handlers en `main.py`

**Criterio de éxito:** `/refresh` desde una cuenta admin dispara el refresh en el backend y confirma.

---

### Fase 6 — Hardening y README
**Objetivo:** El bot está listo para producción.

- [ ] Agregar manejo de excepciones global en el error handler de python-telegram-bot
- [ ] Agregar logging a stdout con nivel configurable por env
- [ ] Documentar `.env.example` con comentarios explicativos
- [ ] Escribir `README.md`: requisitos, setup, cómo correr en local

**Criterio de éxito:** El bot corre de forma estable, los errores se loguean sin crashear el proceso.

---

## 10. Dependencias Clave

```
python-telegram-bot[job-queue]>=21.0
httpx>=0.28.0
pillow>=11.0
pydantic-settings>=2.13.0
python-dotenv>=1.0.0
```

---

## 11. Diseño de Texto Modernizado — Especificación Detallada

### Separadores

```python
SEPARATOR_THICK = "━" * 30      # Separador principal entre secciones
SEPARATOR_THIN = "┈" * 30       # Separador secundario
```

### Indicadores de Cambio

```python
INDICATOR_UP = "🔺"      # change == "up"
INDICATOR_DOWN = "🔻"    # change == "down"
INDICATOR_NEUTRAL = "―"  # change == "neutral" o sin datos
```

### Formato de Monedas

```python
# ElToque (mercado informal)
CURRENCY_FLAGS = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "MLC": "🧾",
    "USDT": "₮",
    "BTC": "₿",
}

# Formato: {flag} {codigo}  {rate:,.2f} CUP  {indicator} {change_str}
# Ejemplo: 🇺🇸 USD  365.00 CUP  🔺 +5.00
```

### Formato CADECA (Columnas)

```
Currency      Buy      Sell
USD          120.00   125.00
EUR          130.00   136.00
```

Alineación:
- Currency: izquierda, 12 caracteres
- Buy: derecha, 8 caracteres
- Sell: derecha, 8 caracteres

### Footer

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📆 2026-03-22 14:30
🔗 elToque.com · cadeca.cu · bc.gob.cu
```

---

## 12. Formato de Tasas Provinciales

```
🗺 *TASAS POR PROVINCIA*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 *Pinar del Río:*  368 CUP
📍 *Artemisa:*       366 CUP
📍 *La Habana:*      365 CUP
📍 *Mayabeque:*      364 CUP
📍 *Matanzas:*       363 CUP
...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📆 2026-03-22 14:30
🔗 elToque.com
```

Formato: `📍 *{Provincia}:*  {rate} CUP`

---

**Fin del documento de diseño.**
