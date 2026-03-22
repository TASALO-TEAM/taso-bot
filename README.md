# TASALO-Bot

Bot de Telegram para consultar las tasas de cambio de Cuba (ElToque, CADECA, BCC).

![Estado](https://img.shields.io/badge/estado-completado-success)
![Versión](https://img.shields.io/badge/versión-0.6.0-blue)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![Tests](https://img.shields.io/badge/tests-104%20passing-success)

## Estado

**Fase 6:** ✅ Hardening y README — **COMPLETADA**
**Tag:** `v0.6.0-fase6`

## Features

- ✅ Comando `/tasalo` con imagen + texto formateado + botones inline
- ✅ Botón 🔄 Actualizar para refresh inmediato
- ✅ Botón 🗺 Ver provincias (placeholder para datos futuros)
- ✅ Botón 🔙 Volver para navegación entre vistas
- ✅ Histórico de tasas por moneda y fuente
- ✅ Comandos admin `/refresh` y `/status` protegidos
- ✅ Fallback automático a texto si la imagen falla
- ✅ Timeouts configurables para todas las operaciones
- ✅ Error handling global con notificación al usuario
- ✅ Logging estructurado para debugging y producción

## Requisitos del Sistema

### Mínimos
- Python 3.12+
- 256 MB RAM
- 50 MB almacenamiento
- Conexión a Internet

### Recomendados
- Python 3.12+
- 512 MB RAM
- 100 MB almacenamiento
- Conexión estable a taso-api

## Instalación

### 1. Clonar el repositorio

```bash
cd /home/ersus/tasalo/taso-bot
```

### 2. Instalar uv (package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Crear entorno virtual e instalar dependencias

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 4. Descargar fuentes tipográficas

El bot usa JetBrains Mono y Space Grotesk para generar las imágenes.

```bash
python src/image_generator.py
```

### 5. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` con tus valores:

```bash
# Token del bot (obtenido de @BotFather)
TELEGRAM_BOT_TOKEN=1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw

# Tus IDs de administrador (obtener con @userinfobot)
ADMIN_CHAT_IDS=123456789

# URL de taso-api
TASALO_API_URL=http://localhost:8000

# API key admin (mismo valor que ADMIN_API_KEY en taso-api)
TASALO_ADMIN_KEY=your_secret_admin_key_here

# Timeouts y logging
API_TIMEOUT_SECONDS=15
LOG_LEVEL=INFO
```

### 6. Iniciar taso-api (requisito previo)

El bot requiere que `taso-api` esté corriendo:

```bash
# En otra terminal
cd /home/ersus/tasalo/taso-api
source .venv/bin/activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Correr el bot

```bash
python src/main.py
```

## Comandos Disponibles

| Comando | Descripción | Disponibilidad |
|---------|-------------|----------------|
| `/start` | Mensaje de bienvenida | Todos los usuarios |
| `/tasalo` | Ver tasas de cambio actuales | Todos los usuarios |
| `/health` | Verificar conexión con el backend | Solo administradores |
| `/refresh` | Forzar refresco inmediato en backend | Solo administradores |
| `/status` | Ver estado del scheduler | Solo administradores |

## Botones Inline

Cuando usas `/tasalo`, el bot envía una imagen con botones:

| Botón | Acción | Callback |
|-------|--------|----------|
| 🔄 Actualizar | Refresca datos y actualiza mensaje | `tasalo_refresh` |
| 🗺 Ver provincias | Muestra tasas por provincia | `tasalo_provincias` |
| 🔙 Volver | Vuelve a la vista principal | `tasalo_back` |

## Testing

```bash
# Todos los tests
pytest

# Tests con output detallado
pytest -v

# Tests específicos
pytest tests/test_config.py -v
pytest tests/test_api_client.py -v
pytest tests/test_formatters.py -v
pytest tests/test_image_generator.py -v
pytest tests/test_handlers.py -v
pytest tests/test_admin_handlers.py -v

# Con coverage
pytest --cov=src --cov-report=term-missing
```

## Estructura del Proyecto

```
taso-bot/
├── .env.example          # Template de variables de entorno
├── .gitignore
├── README.md
├── requirements.txt
├── fonts/                # Fuentes descargadas
│   ├── JetBrainsMono-Regular.ttf
│   └── SpaceGrotesk-Regular.ttf
├── docs/plans/           # Documentos de diseño y planes
└── src/
    ├── __init__.py
    ├── main.py           # Entry point, error handler global
    ├── config.py         # Configuración con pydantic-settings
    ├── api_client.py     # Cliente HTTP para taso-api
    ├── formatters.py     # Formateo de texto Markdown
    ├── image_generator.py # Generación de imágenes Pillow
    └── handlers/
        ├── tasalo.py     # Comando /tasalo y callbacks inline
        └── admin.py      # Comandos /refresh y /status
```

## Guía de Producción

### Opción 1: systemd (VPS/Linux)

1. **Crear servicio systemd:**

```bash
sudo nano /etc/systemd/system/tasalo-bot.service
```

```ini
[Unit]
Description=TASALO Telegram Bot
After=network.target taso-api.service

[Service]
Type=simple
User=tasalo
Group=tasalo
WorkingDirectory=/home/tasalo/taso-bot
Environment="PATH=/home/tasalo/taso-bot/.venv/bin"
ExecStart=/home/tasalo/taso-bot/.venv/bin/python src/main.py
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tasalo-bot

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

2. **Habilitar y iniciar:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable tasalo-bot
sudo systemctl start tasalo-bot
sudo systemctl status tasalo-bot
```

3. **Ver logs:**

```bash
sudo journalctl -u tasalo-bot -f
```

### Opción 2: Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copiar archivos
COPY requirements.txt .
COPY src/ src/
COPY fonts/ fonts/

# Instalar dependencias Python
RUN uv pip install -r requirements.txt

# Variables de entorno
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

CMD ["python", "src/main.py"]
```

```bash
docker build -t tasalo-bot .
docker run -d \
  --name tasalo-bot \
  --env-file .env \
  --network tasalo-network \
  tasalo-bot
```

### Opción 3: tmux/screen (Desarrollo)

```bash
# Con tmux
tmux new -s tasalo-bot
source .venv/bin/activate
python src/main.py
# Ctrl+B, D para detach

# Reattach
tmux attach -t tasalo-bot
```

## Solución de Problemas

### El bot no responde

1. Verifica que el token es correcto en `.env`
2. Revisa los logs en busca de errores
3. Verifica que el bot esté online con @BotFather

### Error de conexión con taso-api

```bash
# Verificar que taso-api está corriendo
curl http://localhost:8000/api/v1/health

# Debe responder: {"ok": true, "db": "connected"}
```

### Los comandos admin no funcionan

1. Verifica que tu `user_id` está en `ADMIN_CHAT_IDS`
2. Verifica que `TASALO_ADMIN_KEY` coincide con `ADMIN_API_KEY` en taso-api
3. Testea los endpoints admin directamente:

```bash
curl -H "X-API-Key: tu_clave" http://localhost:8000/api/v1/admin/status
```

### Las imágenes no se generan

1. Verifica que las fuentes existen en `fonts/`
2. Ejecuta `python src/image_generator.py` para descargar fuentes
3. Revisa permisos de escritura en el directorio

### Logs muy verbosos

Cambia `LOG_LEVEL` en `.env`:

```bash
LOG_LEVEL=WARNING  # Solo warnings y errores
```

## Enlaces

- **Diseño:** `/home/ersus/tasalo/plans/2026-03-22-tasalo-bot-design.md`
- **Progreso:** `/home/ersus/tasalo/plans/PROGRESS.md`
- **Continuidad:** `/home/ersus/tasalo/plans/CONTINUITY.md`
- **taso-api:** `/home/ersus/tasalo/taso-api/README.md`

## Licencia

MIT © 2026 TASALO
