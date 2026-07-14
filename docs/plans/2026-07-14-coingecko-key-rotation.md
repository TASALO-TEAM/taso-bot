# Plan: Rotación de múltiples API keys de CoinGecko

## Contexto

`COINGECKO_API_KEY` acepta hoy un solo valor. El plan Demo de CoinGecko
tiene un límite bajo (30 calls/min), y ya hay dos keys separadas por coma
en `.env` sin usar:

```
COINGECKO_API_KEY=CG-xxxxxxxxxxxxxxxxxxxxxxxx,CG-yyyyyyyyyyyyyyyyyyyyyyyy
```

Objetivo: que `CoinGeckoClient` entienda una lista de keys separadas por
coma y rote entre ellas en cada petición HTTP saliente, con reintento
automático a la siguiente key si una responde 429 (rate limit).

## Archivos afectados

- `src/config.py`
- `src/coingecko_client.py`
- `.env.example`
- `tests/test_coingecko_client.py`

## Cambios

### 1. `src/config.py`

Mantener `coingecko_api_key: str` tal cual (sin romper compatibilidad
con `.env` existentes de un solo valor). Añadir una property que la
parsea a lista:

```python
@property
def coingecko_api_keys(self) -> List[str]:
    """Lista de API keys de CoinGecko (soporta múltiples separadas por coma)."""
    if not self.coingecko_api_key:
        return []
    return [k.strip() for k in self.coingecko_api_key.split(",") if k.strip()]
```

Un solo valor sin coma → lista de 1 elemento, comportamiento actual
intacto.

### 2. `src/coingecko_client.py`

- En `__init__`: guardar `self._keys = self.settings.coingecko_api_keys`
  y crear `self._key_cycle = itertools.cycle(self._keys)` si hay al
  menos una key (evita `StopIteration`/errores con lista vacía).
- `is_configured` → `bool(self._keys)` en vez de `bool(self.settings.coingecko_api_key)`.
- Nuevo método `_next_key() -> str` que hace `next(self._key_cycle)`.
  Es síncrono y no cede el control del event loop, así que es seguro
  aunque haya varias corrutinas concurrentes usando el mismo cliente
  (no hace falta lock).
- `_headers()` deja de leer `self.settings.coingecko_api_key` directo
  y llama a `_next_key()` — así cada llamada HTTP (tanto `/search`
  como `/coins/{id}`) toma la siguiente key en la rotación, no solo
  cada `get_enrichment_data()`.
- **Reintento en 429**: en `_resolve_coin_id` y en el fetch de
  `get_enrichment_data`, si `httpx.HTTPStatusError` tiene
  `response.status_code == 429` y hay más de una key configurada,
  reintentar la misma petición con la siguiente key (hasta
  `len(self._keys)` intentos en total) antes de propagar el error.
  Log a nivel `WARNING` indicando qué key (solo últimos 4 caracteres,
  nunca la key completa) dio 429.
- Con 1 sola key configurada, el comportamiento es idéntico al actual
  (rotación de un solo elemento = sin cambio visible).

### 3. `.env.example`

Actualizar el comentario de `COINGECKO_API_KEY` para documentar el
formato multi-key:

```
# Soporta múltiples keys separadas por coma para repartir carga entre
# distintas cuentas del plan Demo (cada una con su propio límite de
# 30 calls/min). El bot rota automáticamente entre ellas en cada
# petición, y salta a la siguiente si una devuelve 429 (rate limit).
#
# Un solo valor:
#   COINGECKO_API_KEY=CG-xxxxxxxxxxxxxxxxxxxxxxxx
# Varias keys:
#   COINGECKO_API_KEY=CG-xxxxxxxxxxxxxxxxxxxxxxxx,CG-yyyyyyyyyyyyyyyyyyyyyyyy
COINGECKO_API_KEY=
```

### 4. `tests/test_coingecko_client.py`

- Actualizar `_mock_settings()` para exponer también
  `coingecko_api_keys` (property derivada, igual que en el Settings real).
- Nuevos tests:
  - Rotación round-robin: con 2 keys configuradas, 2 llamadas
    consecutivas usan headers con keys distintas.
  - Reintento en 429: primera key devuelve 429, segunda devuelve 200 →
    `get_enrichment_data` retorna datos correctos y no propaga error.
  - Con todas las keys agotadas (todas 429), se comporta como error de
    red actual (`CoinGeckoNetworkError` en `_resolve_coin_id`, `None`
    en `get_enrichment_data`).

## Nota aparte (no incluida en este plan)

`tests/test_coingecko_client.py` actualmente importa
`SYMBOL_TO_COINGECKO_ID` desde `src/coingecko_client.py`, pero ese
módulo ya no define ese símbolo (la resolución es 100% vía `/search`
dinámico). Esto sugiere que la suite ya está rota independientemente
de este cambio — lo señalo pero no lo toco aquí salvo que quieras que
lo arregle en la misma pasada.

## Fuera de alcance

- Persistencia del índice de rotación entre reinicios del bot (no
  hace falta: el cliente es un singleton en memoria durante la vida
  del proceso, `itertools.cycle` retoma en 0 en cada arranque).
- Cooldown/marcado temporal de keys agotadas — el reintento en 429 ya
  cubre el caso práctico sin añadir estado extra.
