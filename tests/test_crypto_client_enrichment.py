# tests/test_crypto_client_enrichment.py
"""Tests para CryptoApiClient.get_crypto_data con enriquecimiento de CoinGecko.

Cubre los 4 casos descritos en la mejora de /p:
1. CMC tiene la moneda + CoinGecko también -> enrichment adjunto, CMC manda.
2. Solo CMC tiene la moneda (CoinGecko falla/no la tiene) -> sin enrichment.
3. CMC y CryptoCompare fallan, pero CoinGecko sí tiene la moneda -> CoinGecko
   pasa a ser la fuente PRIMARIA.
4. Ninguna fuente tiene la moneda -> None (comportamiento histórico).
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.crypto_client import CryptoApiClient


def _settings_stub():
    from unittest.mock import MagicMock
    s = MagicMock()
    s.coinmarketcap_api_key = "cmc-key"
    s.coingecko_api_key = "cg-key"
    return s


@pytest.mark.asyncio
async def test_cmc_primary_with_coingecko_enrichment():
    """Caso 1: CMC tiene la moneda y CoinGecko también -> se adjunta enrichment."""
    with patch("src.crypto_client.get_settings", return_value=_settings_stub()):
        client = CryptoApiClient()

        cmc_payload = {
            "BTC": {
                "symbol": "BTC",
                "cmc_rank": 1,
                "quote": {"USD": {
                    "price": 60000.0, "percent_change_1h": 0.1,
                    "percent_change_24h": 1.5, "percent_change_7d": 3.0,
                    "market_cap": 1_200_000_000_000, "volume_24h": 30_000_000_000,
                }},
            },
            "ETH": {"quote": {"USD": {"price": 3000.0}}},
            "BTC_dup": {},
        }
        cg_enrichment = {
            "symbol_used": "BTC", "ath": 73750.07, "ath_change_pct": -18.45,
            "ath_date": "2024-03-10T00:00:00Z", "atl": 67.81, "atl_date": "2013-07-06T00:00:00Z",
            "circulating_supply": 19_800_000, "total_supply": 19_800_000, "max_supply": 21_000_000,
            "category": "Smart Contract Platform", "sentiment_up_pct": 78.3, "market_cap_rank": 1,
            "price": 60001.0, "percent_change_24h": 1.4, "percent_change_7d": 3.1,
            "market_cap": 1_199_000_000_000, "volume_24h": 29_000_000_000,
            "high_24h": 61000.0, "low_24h": 59000.0,
        }

        client._get_from_cmc = AsyncMock(return_value=cmc_payload)
        client.get_high_low_24h = AsyncMock(return_value=(61000.0, 59000.0))
        client.coingecko.get_enrichment_data = AsyncMock(return_value=cg_enrichment)

        result = await client.get_crypto_data("BTC")

        assert result is not None
        assert result["primary_source"] == "coinmarketcap"
        assert result["price"] == 60000.0  # CMC manda el precio, no CoinGecko
        assert result["market_cap_rank"] == 1
        assert "enrichment" in result
        assert result["enrichment"]["ath"] == 73750.07


@pytest.mark.asyncio
async def test_cmc_primary_without_coingecko_data():
    """Caso 2: CMC tiene la moneda pero CoinGecko no -> sin clave 'enrichment'."""
    with patch("src.crypto_client.get_settings", return_value=_settings_stub()):
        client = CryptoApiClient()

        cmc_payload = {
            "XYZ": {
                "symbol": "XYZ",
                "cmc_rank": 500,
                "quote": {"USD": {"price": 1.23, "percent_change_24h": 0.0}},
            },
            "ETH": {"quote": {"USD": {"price": 3000.0}}},
        }

        client._get_from_cmc = AsyncMock(return_value=cmc_payload)
        client.get_high_low_24h = AsyncMock(return_value=(1.3, 1.1))
        client.coingecko.get_enrichment_data = AsyncMock(return_value=None)

        result = await client.get_crypto_data("XYZ")

        assert result is not None
        assert result["primary_source"] == "coinmarketcap"
        assert "enrichment" not in result


@pytest.mark.asyncio
async def test_coingecko_becomes_primary_when_cmc_and_cc_fail():
    """Caso 3: CMC y CryptoCompare no tienen la moneda, CoinGecko sí -> fuente primaria."""
    with patch("src.crypto_client.get_settings", return_value=_settings_stub()):
        client = CryptoApiClient()

        cg_data = {
            "symbol_used": "NEWCOIN", "price": 0.005, "percent_change_24h": 12.5,
            "percent_change_7d": -3.0, "market_cap": 5_000_000, "volume_24h": 200_000,
            "high_24h": 0.0055, "low_24h": 0.0048, "market_cap_rank": 850,
            "ath": 0.02, "ath_change_pct": -75.0, "ath_date": "2025-01-01T00:00:00Z",
            "atl": 0.001, "atl_date": "2024-01-01T00:00:00Z",
            "circulating_supply": 1_000_000_000, "total_supply": 1_000_000_000,
            "max_supply": None, "category": "Meme", "sentiment_up_pct": 60.0,
        }

        client._get_from_cmc = AsyncMock(return_value=None)
        client._get_from_cryptocompare = AsyncMock(return_value=None)
        client.coingecko.get_enrichment_data = AsyncMock(return_value=cg_data)

        result = await client.get_crypto_data("NEWCOIN")

        assert result is not None
        assert result["primary_source"] == "coingecko"
        assert result["price"] == 0.005
        assert result["enrichment"] == cg_data


@pytest.mark.asyncio
async def test_no_source_has_the_symbol_returns_none():
    """Caso 4: ninguna fuente tiene el símbolo -> None (comportamiento histórico)."""
    with patch("src.crypto_client.get_settings", return_value=_settings_stub()):
        client = CryptoApiClient()

        client._get_from_cmc = AsyncMock(return_value=None)
        client._get_from_cryptocompare = AsyncMock(return_value=None)
        client.coingecko.get_enrichment_data = AsyncMock(return_value=None)

        result = await client.get_crypto_data("NOEXISTE")

        assert result is None


@pytest.mark.asyncio
async def test_cmc_and_coingecko_called_in_parallel():
    """Verifica que ambas fuentes se consultan (no secuencialmente bloqueado)."""
    with patch("src.crypto_client.get_settings", return_value=_settings_stub()):
        client = CryptoApiClient()

        cmc_payload = {
            "BTC": {"symbol": "BTC", "cmc_rank": 1, "quote": {"USD": {"price": 60000.0, "percent_change_24h": 1.0}}},
            "ETH": {"quote": {"USD": {"price": 3000.0}}},
        }
        client._get_from_cmc = AsyncMock(return_value=cmc_payload)
        client.get_high_low_24h = AsyncMock(return_value=(61000.0, 59000.0))
        client.coingecko.get_enrichment_data = AsyncMock(return_value=None)

        await client.get_crypto_data("BTC")

        # Ambas fuentes deben haber sido invocadas exactamente una vez
        client._get_from_cmc.assert_called_once()
        client.coingecko.get_enrichment_data.assert_called_once()
