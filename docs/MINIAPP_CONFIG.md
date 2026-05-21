# TASALO Mini App - Configuración para Telegram BotFather

## 📋 Resumen de Configuración

### URL de la Mini App

| Entorno | URL |
|---------|-----|
| **Producción** | `https://tasalo.duckdns.org/miniapp` |
| Desarrollo local | `http://localhost:5040/miniapp` |

---

## 🤖 Configuración en BotFather

### Paso 1: Abrir BotFather

1. En Telegram, busca **@BotFather**
2. Inicia el bot si no lo has hecho

### Paso 2: Configurar Menu Button

```
/mybots → Selecciona tu bot → Bot Settings → Menu Button → Configure Menu Button
```

1. Envía la URL: `https://tasalo.duckdns.org/miniapp`
2. Envía el título: `📊 Ver Tasas`

### Paso 3: Configurar Bot Settings (opcional)

```
/mybots → Selecciona tu bot → Bot Settings
```

| Setting | Valor |
|---------|-------|
| **Description** | `📊 Tasas de cambio del dólar en Cuba - ElToque, CADECA, BCC` |
| **About** | `Bot oficial de TASALO para consultar tasas de cambio` |

---

## 🔘 Agregar Botón Inline en el Bot (Opcional)

Si quieres agregar un botón inline dentro de los mensajes del bot:

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

keyboard = [
    [InlineKeyboardButton("🌐 Abrir TASALO Web", web_app={"url": "https://tasalo.duckdns.org/miniapp"})]
]
reply_markup = InlineKeyboardMarkup(keyboard)
```

---

## 🧪 Testing

### Verificar que la Mini App es accesible

```bash
# Desde terminal
curl -I https://tasalo.duckdns.org/miniapp

# Debería responder:
# HTTP/2 200
# content-type: text/html; charset=utf-8
```

### Testing en Telegram

1. Abre tu bot en Telegram
2. Debería aparecer el botón **"📊 Ver Tasas"** junto al input de texto
3. Al presionar, se abre la Mini App dentro de Telegram

---

## 📊 Arquitectura Actual

```
┌─────────────────┐
│   Telegram App  │
│   (Mini App)    │
└────────┬────────┘
         │ HTTPS
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│     Caddy       │────▶│   taso-app      │
│  (Reverse Proxy)│     │  (Flask :5040)  │
│  :443 / :80     │     │  /miniapp/*     │
└────────┬────────┘     └─────────────────┘
         │
         │ /api/*
         ▼
┌─────────────────┐
│   taso-api      │
│  (FastAPI :8040)│
└─────────────────┘
```

---

## 🔗 Enlaces de Referencia

| Recurso | URL |
|---------|-----|
| Telegram BotFather | https://t.me/botfather |
| Telegram Web Apps Docs | https://core.telegram.org/bots/webapps |
| Telegram Web App JS | https://telegram.org/js/telegram-web-app.js |
| TASALO Mini App | https://tasalo.duckdns.org/miniapp |
| TASALO API Docs | https://tasalo.duckdns.org/docs |

---

## ✅ Checklist de Configuración

- [ ] Mini App URL configurada en BotFather
- [ ] Menu Button con título personalizado
- [ ] HTTPS válido en `tasalo.duckdns.org`
- [ ] taso-app corriendo en `localhost:5040`
- [ ] Caddy configurado con reverse proxy a `/miniapp/*`
- [ ] taso-api accesible en `/api/*`
- [ ] Testing en Telegram completado

---

**Fecha:** 2026-03-24  
**Autor:** TASALO Team
