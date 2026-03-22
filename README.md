# TASALO-Bot

Bot de Telegram para consultar las tasas de cambio de Cuba (ElToque, CADECA, BCC).

## Estado

**Fase 4:** ✅ Callbacks Inline (Mejoras) — **COMPLETADA**
**Tag:** `v0.4.0-fase4`

## Features

- ✅ Comando `/tasalo` con imagen + texto formateado + botones inline
- ✅ Botón 🔄 Actualizar para refresh inmediato
- ✅ Botón 🗺 Ver provincias (placeholder para datos futuros)
- ✅ Botón 🔙 Volver para navegación entre vistas
- ✅ Histórico de tasas por moneda y fuente (Fase 4 ✅)
- ✅ Comandos admin `/refresh` y `/status` (Fase 5 ⏳)
- ✅ Fallback automático a texto si la imagen falla
- ✅ Timeouts configurables para todas las operaciones

## Requisitos

- Python 3.12+
- uv (package manager)
- Token de Telegram (@BotFather)
- taso-api corriendo en localhost:8000 (o URL accesible)

## Instalación

### 1. Clonar el repositorio

```bash
cd /home/ersus/tasalo/taso-bot
```

### 2. Instalar uv (si no está instalado)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Crear entorno virtual e instalar dependencias

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` con tus valores:

```bash
# Token del bot (obtenido de @BotFather)
TELEGRAM_BOT_TOKEN=1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw

# Tus IDs de administrador (puedes obtener tu ID con @userinfobot)
ADMIN_CHAT_IDS=123456789

# URL de taso-api
TASALO_API_URL=http://localhost:8000

# API key admin (mismo valor que ADMIN_API_KEY en taso-api)
TASALO_ADMIN_KEY=your_secret_admin_key_here
```

### 5. Iniciar taso-api (requisito previo)

El bot requiere que `taso-api` esté corriendo. Si no lo está:

```bash
cd /home/ersus/tasalo/taso-api
source .venv/bin/activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Correr el bot

```bash
python src/main.py
```

## Comandos Disponibles

| Comando | Descripción | Disponibilidad |
|---------|-------------|----------------|
| `/start` | Mensaje de bienvenida | Todos los usuarios |
| `/tasalo` | Ver tasas de cambio actuales | Todos los usuarios |
| `/health` | Verificar conexión con el backend | Solo administradores |

## Testing

```bash
# Todos los tests
pytest

# Tests específicos
pytest tests/test_config.py -v
pytest tests/test_api_client.py -v
pytest tests/test_main.py -v

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
├── docs/plans/           # Documentos de diseño y planes
└── src/
    ├── __init__.py
    ├── main.py           # Entry point del bot
    ├── config.py         # Configuración con pydantic-settings
    └── api_client.py     # Cliente HTTP para taso-api
```

## Próximos Pasos (Fase 5)

- [ ] Implementar comandos admin `/refresh` y `/status`
- [ ] Agregar error handling global
- [ ] Logging estructurado
- [ ] Documentación `.env.example`

## Enlaces

- **Diseño:** `/home/ersus/tasalo/plans/2026-03-22-tasalo-bot-design.md`
- **Plan Fase 1:** `/home/ersus/tasalo/plans/2026-03-22-taso-bot-fase1-scaffold.md`
- **Progreso:** `/home/ersus/tasalo/plans/PROGRESS.md`
