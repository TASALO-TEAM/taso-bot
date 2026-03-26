# TASALO Bot — Image Generator Redesign

**Fecha:** 2026-03-26  
**Estado:** Diseño aprobado ✅  
**Componente:** taso-bot — `src/image_generator.py`

---

## 🎯 Objetivo

Rediseñar la generación de imágenes del bot TASALO para crear tablas horizontales compactas, profesionales y optimizadas para compartir en redes sociales, con marca de agua @tasalobot discreta.

---

## 📋 Requisitos

### Funcionales

1. **Comando /tasalo**: Imagen con tabla horizontal de 3 columnas (ElToque | BCC | CADECA)
2. **Comando /toque**: Imagen individual solo de ElToque
3. **Comando /bcc**: Imagen individual solo del BCC
4. **Comando /cadeca**: Imagen individual solo de CADECA
5. **Marca de agua**: @tasalobot discreta, detrás de las tasas (sin interferir lectura)
6. **Formato**: PNG optimizado para Telegram (1200×630px, ratio 1.91:1)

### No Funcionales

- **Diseño limpio**: Minimalista, profesional, legible en móvil
- **Colores**: Alto contraste texto/fondo (accesibilidad WCAG AA)
- **Compacto**: Máximo 8-10 filas por columna
- **Indicadores**: 🔺 (sube), 🔻 (baja), ― (neutral) integrados
- **Timestamp**: Fecha/hora discreta en footer

---

## 🎨 Diseño Visual

### Dimensiones y Layout

```
┌─────────────────────────────────────────────────────────┐
│  1200px                                                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │                                                    │  │
│  │  📊 TASALO — Tasas de Cambio                      │  │ H
│  │  Cuba · {fecha}                                   │  │
│  │                                                    │  │
│  ├───────────────────────────────────────────────────┤  │
│  │                                                    │  │
│  │  ┌─────────────┬─────────────┬─────────────┐     │  │
│  │  │  🏠 informal│  🏛 BCC     │  🏢 CADECA  │     │  │
│  │  │  ElToque    │  Oficial    │  Exchange   │     │  │
│  │  ├─────────────┼─────────────┼─────────────┤     │  │
│  │  │ EUR 580 🔺  │ EUR 551 🔺  │ EUR 531/584 │     │  │
│  │  │ USD 515 🔺  │ USD 478 ―   │ USD 461/506 │     │  │
│  │  │ MLC 420 ―   │ MLC 390 ―   │ MLC  ---/--- │     │  │
│  │  │ BTC 52M 🔺  │ CAD 348 🔻  │ CAD  ---/--- │     │  │
│  │  │ TRX 185 🔻  │ ...         │ ...         │     │  │
│  │  │ USDT 560 🔺 │             │             │     │  │
│  │  └─────────────┴─────────────┴─────────────┘     │  │
│  │                                                    │  │
│  │                          @tasalobot (marca de agua)│  │
│  │  Actualizado: 26/03/2026 14:30 · elToque·BCC·CADECA│  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Especificaciones Técnicas

| Parámetro | Valor |
|-----------|-------|
| **Dimensiones** | 1200×630px (ratio 1.91:1, óptimo para redes) |
| **Formato** | PNG con compresión optimizada |
| **Modo color** | RGB (sRGB para web) |
| **Fuentes** | Space Grotesk (títulos), JetBrains Mono (datos) |
| **Tamaño base** | 24px (cuerpo), 32px (headers), 16px (footer) |

### Paleta de Colores (TASALO Design System)

| Elemento | Color | Uso |
|----------|-------|-----|
| **Fondo** | `#F8FAFC` | Fondo principal (gris azulado muy claro) |
| **Superficie** | `#FFFFFF` | Tarjetas/tablas con sombra suave |
| **Texto primario** | `#0F172A` | Títulos, datos principales |
| **Texto secundario** | `#64748B` | Subtítulos, labels, footer |
| **Acento primario** | `#3B82F6` | Headers de columna, bordes activos |
| **Subida (🔺)** | `#DC2626` | Rojo para indicadores positivos |
| **Bajada (🔻)** | `#16A34A` | Verde para indicadores negativos |
| **Neutral (―)** | `#94A3B8` | Gris para sin cambios |
| **Marca de agua** | `#E2E8F0` | @tasalobot discreto (10% opacity) |

### Tipografía

| Elemento | Fuente | Tamaño | Peso |
|----------|--------|--------|------|
| **Título principal** | Space Grotesk | 32px | Bold (700) |
| **Subtítulo** | Space Grotesk | 18px | Regular (400) |
| **Header columna** | Space Grotesk | 20px | SemiBold (600) |
| **Datos (moneda)** | JetBrains Mono | 22px | Medium (500) |
| **Datos (valor)** | JetBrains Mono | 24px | Bold (700) |
| **Footer** | Space Grotesk | 14px | Regular (400) |
| **Marca de agua** | Space Grotesk | 48px | Bold (700) |

---

## 🏗️ Arquitectura

### Estructura del Módulo

```
src/image_generator.py
├── Constantes de diseño
│   ├── Colores (COLOR_BG, COLOR_TEXT, COLOR_UP, etc.)
│   ├── Dimensiones (IMG_WIDTH, IMG_HEIGHT, PADDING, etc.)
│   └── Fuentes (FONT_PATHS, FONT_SIZES)
├── Funciones auxiliares
│   ├── get_font_path() → str
│   ├── load_fonts() → tuple[ImageFont]
│   ├── get_change_emoji(change) → str
│   ├── get_change_color(change) → str
│   └── format_rate_value(rate) → str
├── Funciones de dibujo por sección
│   ├── draw_header(draw, W, H, fonts) → y_position
│   ├── draw_eltoque_column(draw, data, x, y, width, fonts) → None
│   ├── draw_bcc_column(draw, data, x, y, width, fonts) → None
│   ├── draw_cadeca_column(draw, data, x, y, width, fonts) → None
│   ├── draw_watermark(draw, W, H, fonts) → None
│   └── draw_footer(draw, W, H, data, fonts) → None
├── Funciones principales
│   ├── generate_image(data) → BytesIO (async, uso general)
│   ├── generate_tasalo_image(data) → BytesIO (tabla triple)
│   ├── generate_eltoque_image(data) → BytesIO (individual)
│   ├── generate_bcc_image(data) → BytesIO (individual)
│   ├── generate_cadeca_image(data) → BytesIO (individual)
│   └── generate_image_sync(data) → BytesIO (testing)
└── Script de prueba (__main__)
```

### Flujo de Generación

```
1. Extraer datos del API response
   ↓
2. Crear imagen RGBA (1200×630)
   ↓
3. Dibujar fondo (color sólido #F8FAFC)
   ↓
4. Dibujar header (título + subtítulo + fecha)
   ↓
5. Dibujar superficie de tabla (rectángulo blanco con sombra)
   ↓
6. Dibujar headers de columnas (ElToque | BCC | CADECA)
   ↓
7. Dibujar datos por columna (monedas + valores + indicadores)
   ↓
8. Dibujar marca de agua (@tasalobot, 10% opacity, detrás de datos)
   ↓
9. Dibujar footer (timestamp + fuentes)
   ↓
10. Guardar como PNG optimizado → BytesIO
```

---

## 📊 Estructura de Datos

### Input (API Response)

```python
{
    "ok": True,
    "data": {
        "eltoque": {
            "EUR": {"rate": 580.00, "change": "up", "prev_rate": 575.00},
            "USD": {"rate": 515.00, "change": "up", "prev_rate": 512.00},
            "MLC": {"rate": 420.00, "change": None, "prev_rate": 420.00},
            "BTC": {"rate": 52000000, "change": "up", "prev_rate": 51500000},
            "TRX": {"rate": 185.00, "change": "down", "prev_rate": 190.00},
            "USDT": {"rate": 560.00, "change": "up", "prev_rate": 558.00},
        },
        "bcc": {
            "EUR": {"rate": 551.23, "change": "up", "prev_rate": 548.00},
            "USD": {"rate": 478.00, "change": None, "prev_rate": 478.00},
            "CAD": {"rate": 348.17, "change": "down", "prev_rate": 352.00},
        },
        "cadeca": {
            "EUR": {"buy": 531.94, "sell": 584.30},
            "USD": {"buy": 461.27, "sell": 506.68},
        },
        "updated_at": "2026-03-26T14:30:00Z"
    }
}
```

### Output

- `BytesIO` con PNG optimizado (listo para `bot.send_photo()`)

---

## 🔧 Implementación

### Paso 1: Constantes de Diseño

```python
# Dimensiones
IMG_WIDTH = 1200
IMG_HEIGHT = 630
PADDING = 40
COLUMN_GAP = 20

# Colores (TASALO Design System)
COLOR_BG = "#F8FAFC"
COLOR_SURFACE = "#FFFFFF"
COLOR_TEXT = "#0F172A"
COLOR_TEXT_MUTED = "#64748B"
COLOR_ACCENT = "#3B82F6"
COLOR_UP = "#DC2626"
COLOR_DOWN = "#16A34A"
COLOR_NEUTRAL = "#94A3B8"
COLOR_WATERMARK = "rgba(226, 232, 240, 0.10)"

# Layout de columnas
COLUMN_WIDTHS = {
    "eltoque": (PADDING, PADDING + 380),      # Columna 1: 380px
    "bcc": (PADDING + 400, PADDING + 780),    # Columna 2: 380px
    "cadeca": (PADDING + 800, PADDING + 1180) # Columna 3: 380px
}
```

### Paso 2: Funciones de Dibujo

```python
def draw_header(draw, W, H, fonts):
    """Dibujar header con título y subtítulo."""
    y = PADDING
    
    # Título principal
    draw.text((PADDING, y), "📊 TASALO — Tasas de Cambio", 
              fill=COLOR_TEXT, font=fonts.title)
    y += 45
    
    # Subtítulo con fecha
    date_str = datetime.now().strftime("%d/%m/%Y · Cuba")
    draw.text((PADDING, y), date_str, 
              fill=COLOR_TEXT_MUTED, font=fonts.subtitle)
    
    return y + 60  # Retornar Y para contenido principal


def draw_eltoque_column(draw, data, x_start, x_end, y_start, fonts):
    """Dibujar columna de ElToque con tasas."""
    # Header de columna
    draw.text((x_start, y_start), "🏠 informal", 
              fill=COLOR_ACCENT, font=fonts.column_header)
    draw.text((x_start, y_start + 24), "ElToque", 
              fill=COLOR_TEXT_MUTED, font=fonts.column_subheader)
    
    y = y_start + 60
    
    # Dibujar línea separadora
    draw.line((x_start, y, x_end, y), fill=COLOR_TEXT_MUTED, width=2)
    y += 20
    
    # Ordenar monedas por prioridad
    priority = ["EUR", "USD", "MLC", "USDT", "BTC", "TRX"]
    sorted_currencies = sorted(
        data.keys(),
        key=lambda x: priority.index(x) if x in priority else 99
    )
    
    for currency in sorted_currencies[:8]:  # Máximo 8 filas
        currency_info = data[currency]
        rate = currency_info.get("rate", 0)
        change = currency_info.get("change")
        
        # Emoji de bandera
        flag = get_currency_flag(currency)
        
        # Dibujar moneda
        draw.text((x_start, y), f"{flag} {currency}", 
                  fill=COLOR_TEXT, font=fonts.currency)
        
        # Dibujar valor con indicador
        rate_str = format_rate_value(rate)
        indicator = get_change_emoji(change)
        indicator_color = get_change_color(change)
        
        # Valor alineado a derecha
        draw.text((x_end, y), f"{rate_str}", 
                  fill=COLOR_TEXT, anchor="rm", font=fonts.rate_value)
        
        # Indicador alineado a derecha (después del valor)
        draw.text((x_end + 15, y), indicator, 
                  fill=indicator_color, anchor="lm", font=fonts.rate_value)
        
        y += 42  # Altura de fila


def draw_watermark(draw, W, H, fonts):
    """Dibujar marca de agua @tasalobot discreta."""
    watermark_text = "@tasalobot"
    
    # Calcular posición (esquina inferior derecha, antes del footer)
    bbox = draw.textbbox((0, 0), watermark_text, font=fonts.watermark)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = W - PADDING - text_width
    y = H - 80  # 80px desde el fondo (antes del footer)
    
    # Dibujar con transparencia (usar color RGBA)
    draw.text((x, y), watermark_text, 
              fill=COLOR_WATERMARK, font=fonts.watermark)
```

### Paso 3: Función Principal

```python
async def generate_image(data: dict, image_type: str = "tasalo") -> Optional[io.BytesIO]:
    """Generar imagen con tasas de cambio.
    
    Args:
        data: Datos de la API (campo 'data' del response)
        image_type: Tipo de imagen ("tasalo", "eltoque", "bcc", "cadeca")
    
    Returns:
        BytesIO con PNG optimizado, o None si hay error
    """
    try:
        # 1. Crear imagen
        img = Image.new("RGBA", (IMG_WIDTH, IMG_HEIGHT), COLOR_BG)
        draw = ImageDraw.Draw(img)
        
        # 2. Cargar fuentes
        fonts = load_fonts()
        
        # 3. Dibujar fondo de superficie (tabla blanca)
        surface_rect = (
            PADDING - 10, 
            100,  # y_start después del header
            IMG_WIDTH - PADDING + 10, 
            IMG_HEIGHT - 70  # antes del footer
        )
        draw.rounded_rectangle(surface_rect, radius=12, fill=COLOR_SURFACE)
        
        # 4. Dibujar header
        y_content = draw_header(draw, IMG_WIDTH, IMG_HEIGHT, fonts)
        
        # 5. Dibujar columnas según tipo
        if image_type == "tasalo":
            # Tabla triple
            draw_eltoque_column(
                draw, 
                data.get("eltoque", {}),
                COLUMN_WIDTHS["eltoque"][0],
                COLUMN_WIDTHS["eltoque"][1],
                y_content,
                fonts
            )
            draw_bcc_column(
                draw,
                data.get("bcc", {}),
                COLUMN_WIDTHS["bcc"][0],
                COLUMN_WIDTHS["bcc"][1],
                y_content,
                fonts
            )
            draw_cadeca_column(
                draw,
                data.get("cadeca", {}),
                COLUMN_WIDTHS["cadeca"][0],
                COLUMN_WIDTHS["cadeca"][1],
                y_content,
                fonts
            )
        elif image_type == "eltoque":
            draw_eltoque_column(
                draw,
                data.get("eltoque", {}),
                PADDING,
                IMG_WIDTH - PADDING,
                y_content,
                fonts
            )
        # ... similar para bcc y cadeca
        
        # 6. Dibujar marca de agua
        draw_watermark(draw, IMG_WIDTH, IMG_HEIGHT, fonts)
        
        # 7. Dibujar footer
        draw_footer(draw, IMG_WIDTH, IMG_HEIGHT, data, fonts)
        
        # 8. Guardar como PNG optimizado
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True, compress_level=6)
        buffer.seek(0)
        
        logger.info(f"✅ Imagen generada: {IMG_WIDTH}x{IMG_HEIGHT}px ({image_type})")
        return buffer
        
    except Exception as e:
        logger.error(f"❌ Error generando imagen: {e}", exc_info=True)
        return None
```

---

## ✅ Criterios de Aceptación

### Funcionales

- [ ] `/tasalo` genera imagen con 3 columnas (ElToque | BCC | CADECA)
- [ ] `/toque` genera imagen individual de ElToque
- [ ] `/bcc` genera imagen individual del BCC
- [ ] `/cadeca` genera imagen individual de CADECA
- [ ] Marca de agua @tasalobot visible pero discreta (10% opacity)
- [ ] Indicadores 🔺🔻― con colores correctos (rojo/verde/gris)
- [ ] Timestamp en footer con formato `DD/MM/YYYY HH:MM`

### No Funcionales

- [ ] Imagen 1200×630px (ratio 1.91:1)
- [ ] PNG optimizado (<500KB idealmente)
- [ ] Alto contraste texto/fondo (WCAG AA ≥4.5:1)
- [ ] Legible en móvil (texto ≥22px)
- [ ] Máximo 8-10 filas por columna
- [ ] Generación <5 segundos (timeout actual)

### Visuales

- [ ] Fondo gris azulado claro (#F8FAFC)
- [ ] Superficie blanca para tabla (#FFFFFF)
- [ ] Headers de columna en azul (#3B82F6)
- [ ] Texto principal oscuro (#0F172A)
- [ ] Texto secundario gris (#64748B)
- [ ] Bordes redondeados (12px radius)
- [ ] Sombra suave en superficie

---

## 🧪 Testing

### Test de Prueba

```python
if __name__ == "__main__":
    test_data = {
        "eltoque": {
            "EUR": {"rate": 580.00, "change": "up", "prev_rate": 575.00},
            "USD": {"rate": 515.00, "change": "up", "prev_rate": 512.00},
            "MLC": {"rate": 420.00, "change": None, "prev_rate": 420.00},
            "BTC": {"rate": 52000000, "change": "up", "prev_rate": 51500000},
            "TRX": {"rate": 185.00, "change": "down", "prev_rate": 190.00},
            "USDT": {"rate": 560.00, "change": "up", "prev_rate": 558.00},
        },
        "bcc": {
            "EUR": {"rate": 551.23, "change": "up", "prev_rate": 548.00},
            "USD": {"rate": 478.00, "change": None, "prev_rate": 478.00},
        },
        "cadeca": {
            "EUR": {"buy": 531.94, "sell": 584.30},
            "USD": {"buy": 461.27, "sell": 506.68},
        },
        "updated_at": datetime.now().isoformat(),
    }
    
    print("🧪 Generando imagen de prueba...")
    
    # Probar imagen triple
    img_tasalo = generate_image_sync(test_data, image_type="tasalo")
    if img_tasalo:
        with open("test_tasalo.png", "wb") as f:
            f.write(img_tasalo.read())
        print("✅ test_tasalo.png generada")
    
    # Probar imagen individual ElToque
    img_eltoque = generate_image_sync(test_data, image_type="eltoque")
    if img_eltoque:
        with open("test_eltoque.png", "wb") as f:
            f.write(img_eltoque.read())
        print("✅ test_eltoque.png generada")
    
    print("🎨 Pruebas completadas")
```

---

## 📦 Dependencias

- `Pillow>=10.0.0` — Generación de imágenes (ya instalada)
- `Pillow>=10.2.0` — Soporte para `draw.rounded_rectangle()`

---

## 🚀 Integración con Handlers

### Cambios en `handlers/tasalo.py`

```python
# En send_tasalo_response():
image_bytes = await asyncio.wait_for(
    generate_image(api_data, image_type="tasalo"),  # ← Agregar image_type
    timeout=IMAGE_GENERATION_TIMEOUT,
)

# En toque_command():
# Llamar a generate_image(api_data, image_type="eltoque")

# En bcc_command():
# Llamar a generate_image(api_data, image_type="bcc")

# En cadeca_command():
# Llamar a generate_image(api_data, image_type="cadeca")
```

---

## 📝 Notas de Implementación

1. **Fuentes**: Si no hay Space Grotesk/JetBrains Mono, fallback a DejaVu Sans
2. **Marca de agua**: Dibujar ANTES de los datos (primero fondo, luego watermark, luego datos)
3. **Indicadores**: Usar emojis unicode (🔺🔻―) en lugar de texto
4. **CADECA**: Mostrar formato `buy/sell` en una sola celda (ej: `461/506`)
5. **Espaciado**: Usar grid de 8px para márgenes y paddings
6. **Optimización**: PNG con `compress_level=6` (balance calidad/tamaño)

---

## 🔗 Referencias

- [Telegram Image Best Practices](https://core.telegram.org/bots/api#sendphoto)
- [Social Media Image Sizes 2026](https://www.sproutsocial.com/insights/social-media-image-sizes-guide/)
- [WCAG Contrast Checker](https://webaim.org/resources/contrastchecker/)
- [Pillow Documentation](https://pillow.readthedocs.io/)
