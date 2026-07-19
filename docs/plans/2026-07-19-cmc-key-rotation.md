# Plan: Rotación de múltiples API keys de CoinMarketCap (taso-bot)

## Contexto

`COINMARKETCAP_API_KEY` en `src/config.py` acepta hoy un solo valor.
`src/crypto_client.py` la usa en dos puntos distintos sin ningún
mecanismo de rotación ni reintento ante 429:

- `_get_from_cmc()` — usado por `/p` (quotes/latest, 1 llamada por
  consulta de moneda).
- `_cmc_get()` — usado por `/spl`, que dispara **7 llamadas en
  paralelo** cada vez que expira el caché de 15 min (fear&greed,
  global-metrics, 2× listings para top gainers/losers, trending,
  news, altcoin-season).

Además, `src/services/price_alert_checker.py` (job de APScheduler
cada 5 min) instancia su **propio** `CryptoApiClient()` singleton,
pero hoy comparte la misma `COINMARKETCAP_API_KEY` que `/p` y `/spl`
— tres consumidores distintos, uno de ellos automático y periódico,
compitiendo por el mismo cupo.

Hoy, cualquier error que no sea 403 ("plan insuficiente", ya
manejado explícitamente) cae en un `except Exception` genérico que
solo loguea y devuelve `None` — un 429 mata esa sección sin
reintentar ni rotar de key.

## Decisión de diseño (confirmada)

Dos pools de keys independientes, cada uno con su propia rotación:

- `COINMARKETCAP_API_KEY` (varias separadas por coma) → pool
  **interactivo**, usado por `/p` y `/spl` (comparten el mismo
  `CryptoApiClient` singleton vía `get_crypto_client()` en
  `src/handlers/p.py`).
- `CMC_API_KEY_ALERTA` (varias separadas por coma) → pool dedicado al
  **alert checker**, para que el polling automático de cada 5 min no
  consuma cupo de las cuentas que usan los comandos interactivos.

Si `CMC_API_KEY_ALERTA` se deja vacío, el checker cae de vuelta al
pool de `COINMARKETCAP_API_KEY` (comportamiento actual, sin romper
despliegues existentes que aún no configuren la variable nueva).

## Archivos afectados

- `src/config.py`
- `src/crypto_client.py`
- `src/services/price_alert_checker.py`
- `.env.example`
- `tests/test_config.py`
- `tests/test_crypto_client_enrichment.py` (o un nuevo
  `tests/test_crypto_client_cmc_rotation.py`)

## Cambios

### 1. `src/config.py`

Dos campos + dos properties, mismo patrón que `coingecko_api_keys`:

```python
coinmarketcap_api_key: str = Field(default="", ...)  # ya existe, sin cambios

cmc_api_key_alerta: str = Field(
    default="",
    description="CMC Pro API key(s) dedicadas al alert checker (separadas "
    "por coma). Si se deja vacío, el checker usa el pool de "
    "COINMARKETCAP_API_KEY.",
)

@property
def coinmarketcap_api_keys(self) -> List[str]:
    if not self.coinmarketcap_api_key:
        return []
    return [k.strip() for k in self.coinmarketcap_api_key.split(",") if k.strip()]

@property
def cmc_api_key_alerta_keys(self) -> List[str]:
    """Pool dedicado del alert checker; si no está configurado, cae al
    pool interactivo (coinmarketcap_api_keys) — mismo cupo que hoy."""
    if not self.cmc_api_key_alerta:
        return self.coinmarketcap_api_keys
    return [k.strip() for k in self.cmc_api_key_alerta.split(",") if k.strip()]
```

### 2. `src/crypto_client.py`

- `CryptoApiClient.__init__(self, cmc_api_keys: Optional[List[str]] = None)`:
  - `self._cmc_keys = cmc_api_keys if cmc_api_keys is not None else self.settings.coinmarketcap_api_keys`
  - `self._cmc_key_cycle = itertools.cycle(self._cmc_keys) if self._cmc_keys else None`
  - Así cada instancia rota su propio pool — no hay estado compartido
    entre el singleton de `/p`+`/spl` y el del alert checker.
- Nuevo método privado unificado `_cmc_request_with_retry(url, params)`
  (reemplaza la lógica HTTP duplicada de `_get_from_cmc` y `_cmc_get`):
  - Arma headers con la siguiente key del pool de esta instancia
    (`X-CMC_PRO_API_KEY`).
  - 429 y quedan keys por probar → log warning (últimos 4 caracteres
    de la key) y reintenta con la siguiente, hasta `len(self._cmc_keys)`
    intentos.
  - 403 → se propaga tal cual, cada caller sigue resolviendo su propio
    caso "plan insuficiente" exactamente como hoy.
  - Cualquier otro status → se propaga sin reintento (no tiene sentido
    rotar ante un 400/401/500).
- `_get_from_cmc()` y `_cmc_get()` pasan a usar este helper en vez de
  `client.get(...)` directo con una key fija. El resto de su lógica
  (parseo, manejo del 403, logging por endpoint) no cambia.
- Con 0 o 1 key en el pool, comportamiento idéntico al actual.

### 3. `src/services/price_alert_checker.py`

- `_get_crypto_client()` pasa a instanciar:
  ```python
  CryptoApiClient(cmc_api_keys=get_settings().cmc_api_key_alerta_keys)
  ```
  en vez de `CryptoApiClient()` a secas — así el checker rota su
  propio pool (o el compartido, si `CMC_API_KEY_ALERTA` no está
  configurado) sin tocar el singleton que usan `/p` y `/spl`.

### 4. `.env.example`

```
# Keys del pool INTERACTIVO — usadas por /p y /spl. Soporta varias
# separadas por coma para repartir carga entre cuentas del plan
# Basic. El bot rota automáticamente y salta a la siguiente si una
# devuelve 429 (rate limit).
#
#   Una sola key:  COINMARKETCAP_API_KEY=your_cmc_pro_api_key_here
#   Varias keys:   COINMARKETCAP_API_KEY=key1,key2,key3
COINMARKETCAP_API_KEY=

# (Opcional) Pool DEDICADO al alert checker (job automático cada 5
# min) — separado del pool interactivo de arriba para que el polling
# en background no consuma el cupo de /p y /spl. Mismo formato
# (una o varias separadas por coma). Si se deja vacío, el checker usa
# el pool de COINMARKETCAP_API_KEY.
CMC_API_KEY_ALERTA=
```

### 5. Tests

- `tests/test_config.py`: `coinmarketcap_api_keys` (vacío/1/2 valores)
  y `cmc_api_key_alerta_keys` (vacío → cae al pool interactivo; con
  valor propio → usa el suyo).
- Rotación/retry-en-429 para `_cmc_request_with_retry`, mismo esquema
  que `tests/test_coingecko_client.py`.
- Test de que `CryptoApiClient(cmc_api_keys=[...])` rota sobre el
  pool pasado explícitamente y no sobre `settings.coinmarketcap_api_keys`
  (para confirmar el aislamiento entre los dos pools).

## Relación con el plan de Groq

Mismo criterio en los dos: rotación solo cubre 429. Un 403 (plan
insuficiente) o un 400/401/500 no se arregla rotando de key y se
sigue propagando/logueando igual que hoy.

## Fuera de alcance

- No se cambian los 7 endpoints que dispara `/spl` ni su lógica de
  caché de 15 min — solo cómo se autentican las llamadas.
- No se persiste el índice de rotación entre reinicios.
- No se añade un tercer pool para casos futuros — si hace falta,
  se replica el mismo patrón (`cmc_api_keys` como parámetro del
  constructor) cuando surja la necesidad concreta.
