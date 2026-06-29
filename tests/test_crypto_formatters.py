# tests/test_crypto_formatters.py
"""Tests para las funciones de formateo de /p: mensaje base y bloque extendido."""

from src.formatters import (
    build_crypto_message,
    build_crypto_extended_block,
    format_supply,
    format_ath_date,
)


# ── format_supply ──

def test_format_supply_trillions():
    assert format_supply(2_500_000_000_000) == "2.50T"


def test_format_supply_billions():
    assert format_supply(1_200_000_000) == "1.20B"


def test_format_supply_millions():
    assert format_supply(19_800_000) == "19.80M"


def test_format_supply_thousands():
    assert format_supply(5_000) == "5.00K"


def test_format_supply_small_number():
    assert format_supply(42) == "42.00"


def test_format_supply_none():
    assert format_supply(None) == "N/A"


# ── format_ath_date ──

def test_format_ath_date_valid_iso():
    assert format_ath_date("2024-03-10T07:10:36.635Z") == "10/03/2024"


def test_format_ath_date_none():
    assert format_ath_date(None) == "N/A"


def test_format_ath_date_invalid_string():
    assert format_ath_date("not-a-date") == "N/A"


# ── build_crypto_message (caso base, sin cambios respecto al comportamiento actual) ──

def test_build_crypto_message_basic():
    data = {
        "symbol": "BTC",
        "price": 60000.1234,
        "price_eth": 20.5,
        "price_btc": 1.0,
        "high_24h": 61000.0,
        "low_24h": 59000.0,
        "percent_change_1h": 0.5,
        "percent_change_24h": 1.5,
        "percent_change_7d": -2.3,
        "market_cap_rank": 1,
        "market_cap": 1_200_000_000_000,
        "volume_24h": 30_000_000_000,
    }
    msg = build_crypto_message(data)
    assert "*BTC*" in msg
    assert "$60,000.1234" in msg
    assert "#1" in msg
    # No debe incluir info de CoinGecko si no se le pasó enrichment
    assert "CoinGecko" not in msg


# ── build_crypto_extended_block (nuevo bloque "Ver más") ──

def test_build_crypto_extended_block_full_data():
    enrichment = {
        "ath": 73750.07,
        "ath_change_pct": -18.45,
        "ath_date": "2024-03-10T07:10:36.635Z",
        "atl": 67.81,
        "atl_date": "2013-07-06T00:00:00.000Z",
        "circulating_supply": 19_800_000,
        "total_supply": 19_800_000,
        "max_supply": 21_000_000,
        "category": "Smart Contract Platform",
        "sentiment_up_pct": 78.3,
        "market_cap_rank": 1,
    }
    block = build_crypto_extended_block(enrichment)

    assert "Info adicional (CoinGecko)" in block
    assert "$73,750.0700" in block
    assert "10/03/2024" in block
    assert "-18.45%" in block
    assert "$67.8100" in block
    assert "19.80M" in block
    assert "21.00M" in block
    assert "Smart Contract Platform" in block
    assert "78.3%" in block
    # No debe repetir precio/cambios % que ya muestra build_crypto_message
    assert "Precio" not in block
    assert "Vol:" not in block


def test_build_crypto_extended_block_partial_data():
    """Si solo hay algunos campos (p.ej. sin sentiment ni categoría), no rompe."""
    enrichment = {
        "ath": 100.0,
        "ath_change_pct": -10.0,
        "ath_date": None,
        "atl": None,
        "circulating_supply": None,
        "max_supply": None,
        "total_supply": None,
        "category": None,
        "sentiment_up_pct": None,
        "market_cap_rank": None,
    }
    block = build_crypto_extended_block(enrichment)
    assert "$100.0000" in block
    assert "N/A" in block  # fecha ATH desconocida
    # No debe lanzar excepción ni dejar el bloque vacío
    assert "Info adicional" in block


def test_build_crypto_extended_block_empty_enrichment():
    """Si enrichment no tiene ningún dato útil, muestra mensaje de fallback."""
    block = build_crypto_extended_block({})
    assert "Sin datos adicionales disponibles" in block
