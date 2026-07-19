# Plan: Rotación de múltiples API keys de Groq (taso-bot)

## Contexto

`GROQ_API_KEY` en `src/config.py` acepta hoy un solo valor, y
`src/core/ai_logic.py` (`_call_groq_async`) lo usa directo sin ningún
mecanismo de rotación ni reintento ante 429. Es el único cliente de IA
de taso-bot sin este patrón — `CoinGeckoClient` ya lo tiene
(`docs/plans/2026-07-14-coingecko-key-rotation.md`), y taso-gcg ya lo
implementó de forma independiente para su propio uso de Groq
(`core/ai_client.py`: `GROQ_API_KEYS` + `itertools.cycle` + reintento
en 429). Ese es el patrón exacto a portar aquí.

Esto afecta a los tres consumidores de Groq en taso-bot:
`get_groq_crypto_analysis` (/ta), `get_groq_price_spotlight` (/p) y
`get_groq_market_spotlight` (/spl) — los tres llaman a
`_call_groq_async`, así que el fix es único y beneficia a los tres.

**Importante — límite de este fix:** la rotación solo ayuda cuando el
fallo es 429 (rate limit). Si la causa real de que /spl falle es un
400 (bad request), rotar de key no lo arregla — un 400 se repetiría
igual con cualquier key. Por eso este plan además añade logging del
cuerpo de la respuesta de error (hoy solo se loguea el status code),
para poder diagnosticar con certeza qué está pasando la próxima vez
que ocurra. Esto es relevante porque en taso-gcg (que ya tiene
rotación) se están viendo justamente errores 400 repetidos de Groq —
consistente con que la rotación no sea la solución completa ahí, y un
indicio de que /spl podría tener la misma causa raíz.

## Archivos afectados

- `src/config.py`
- `src/core/ai_logic.py`
- `.env.example`
- `tests/test_config.py`
- `tests/test_ai_logic.py` (nuevo)

## Cambios

### 1. `src/config.py`

Mantener `groq_api_key: str` tal cual (compatibilidad con `.env` de una
sola key). Añadir property análoga a `coingecko_api_keys`:

```python
@property
def groq_api_keys(self) -> List[str]:
    """Lista de API keys de Groq (soporta múltiples separadas por coma)."""
    if not self.groq_api_key:
        return []
    return [k.strip() for k in self.groq_api_key.split(",") if k.strip()]
```

### 2. `src/core/ai_logic.py`

- Import `itertools`.
- `_call_groq_async(payload, timeout)` pasa a intentar con cada key
  disponible (round-robin vía `itertools.cycle`, inicializado
  perezosamente en el primer uso para no romper el patrón de lazy
  `get_settings()` que ya usa este módulo):
  - 429 y quedan keys por probar → log warning (solo últimos 4
    caracteres de la key) y reintenta con la siguiente.
  - Cualquier otro status (400, 401, 500...) → **no reintenta con
    otra key** (rotar no arregla un 400), pero SÍ loguea el cuerpo de
    la respuesta (`e.response.text[:500]`) antes de relanzar, para
    que quede en el log qué rechazó Groq exactamente.
  - Timeout/NetworkError: se mantiene el retry con backoff de
    `tenacity` que ya existe (eso no cambia).
- Las tres funciones públicas (`get_groq_crypto_analysis`,
  `get_groq_price_spotlight`, `get_groq_market_spotlight`) no cambian
  su lógica — siguen llamando a `_call_groq_async` igual que ahora.
- Con 0 o 1 key configurada, comportamiento idéntico al actual.

### 3. `.env.example`

Documentar el formato multi-key para `GROQ_API_KEY`, mismo texto que
ya se usó para `COINGECKO_API_KEY`:

```
# Soporta varias keys separadas por coma para repartir carga entre
# distintas cuentas gratuitas de Groq. El bot rota automáticamente
# entre ellas, y salta a la siguiente si una devuelve 429 (rate limit).
#
#   Una sola key:  GROQ_API_KEY=gsk_xxxxxxxx
#   Varias keys:   GROQ_API_KEY=gsk_xxxxxxxx,gsk_yyyyyyyy
GROQ_API_KEY=
```

### 4. Tests

- `tests/test_config.py`: test de `groq_api_keys` (vacío, 1 valor, 2
  valores separados por coma) — igual que el existente para
  `coingecko_api_keys`.
- `tests/test_ai_logic.py` (nuevo): con 2 keys mockeadas, simular 429
  en la primera y 200 en la segunda → la llamada pública devuelve el
  contenido esperado sin propagar error. Simular 400 → no debe
  reintentar con la segunda key (una sola llamada HTTP) y debe
  propagar/loguear el error tal como hoy.

## Fuera de alcance

- No se toca taso-gcg en este plan (ya tiene su propia rotación
  implementada de forma independiente en `core/ai_client.py`); el
  diagnóstico de sus 400 repetidos es un paso aparte, después de
  este.
- No se cambia el modelo (`DEFAULT_MODEL = "llama-3.3-70b-versatile"`)
  ni los prompts — eso queda pendiente de confirmar con el log de
  cuerpo de error que añade este mismo plan.
- No se persiste el índice de rotación entre reinicios (mismo
  criterio que CoinGecko: `itertools.cycle` reinicia en 0 en cada
  arranque, es intrascendente).
