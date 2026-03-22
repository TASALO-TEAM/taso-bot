"""Tests para el módulo de formatters de TASALO-Bot."""

import pytest
from datetime import datetime

from src.formatters import (
    get_change_indicator,
    get_currency_flag,
    format_rate_value,
    parse_iso_datetime,
    build_eltoque_block,
    build_cadeca_block,
    build_bcc_block,
    build_footer,
    build_full_message,
    INDICATOR_UP,
    INDICATOR_DOWN,
    INDICATOR_NEUTRAL,
    SEPARATOR_THICK,
    SEPARATOR_THIN,
)


# =============================================================================
# TESTS DE FUNCIONES AUXILIARES
# =============================================================================

class TestChangeIndicator:
    """Tests para get_change_indicator."""

    def test_up_indicator(self):
        """Indicador para cambio positivo."""
        assert get_change_indicator("up") == INDICATOR_UP

    def test_down_indicator(self):
        """Indicador para cambio negativo."""
        assert get_change_indicator("down") == INDICATOR_DOWN

    def test_neutral_indicator(self):
        """Indicador para sin cambio."""
        assert get_change_indicator("neutral") == INDICATOR_NEUTRAL

    def test_none_indicator(self):
        """Indicador para valor None."""
        assert get_change_indicator(None) == INDICATOR_NEUTRAL

    def test_unknown_indicator(self):
        """Indicador para valor desconocido."""
        assert get_change_indicator("unknown") == INDICATOR_NEUTRAL


class TestCurrencyFlag:
    """Tests para get_currency_flag."""

    def test_usd_flag(self):
        """Bandera para USD."""
        assert get_currency_flag("USD") == "🇺🇸"

    def test_eur_flag(self):
        """Bandera para EUR."""
        assert get_currency_flag("EUR") == "🇪🇺"

    def test_mlc_flag(self):
        """Bandera para MLC."""
        assert get_currency_flag("MLC") == "🧾"

    def test_usdt_flag(self):
        """Bandera para USDT."""
        assert get_currency_flag("USDT") == "₮"

    def test_btc_flag(self):
        """Bandera para BTC."""
        assert get_currency_flag("BTC") == "₿"

    def test_unknown_flag(self):
        """Bandera para moneda desconocida."""
        assert get_currency_flag("XYZ") == ""

    def test_case_insensitive(self):
        """Las banderas son case-insensitive."""
        assert get_currency_flag("usd") == "🇺🇸"
        assert get_currency_flag("Eur") == "🇪🇺"


class TestFormatRateValue:
    """Tests para format_rate_value."""

    def test_integer_rate(self):
        """Tasa entera."""
        assert format_rate_value(365) == "365.00"

    def test_decimal_rate(self):
        """Tasa con decimales."""
        assert format_rate_value(365.5) == "365.50"

    def test_small_rate(self):
        """Tasa pequeña."""
        assert format_rate_value(24.0) == "24.00"

    def test_large_rate(self):
        """Tasa grande con separador de miles."""
        assert format_rate_value(98500.50) == "98,500.50"


class TestParseIsoDatetime:
    """Tests para parse_iso_datetime."""

    def test_iso_with_z(self):
        """ISO datetime con Z suffix."""
        result = parse_iso_datetime("2026-03-22T14:30:00Z")
        assert result == "2026-03-22 14:30"

    def test_iso_with_timezone(self):
        """ISO datetime con timezone."""
        result = parse_iso_datetime("2026-03-22T14:30:00+00:00")
        assert result == "2026-03-22 14:30"

    def test_iso_without_timezone(self):
        """ISO datetime sin timezone."""
        result = parse_iso_datetime("2026-03-22T14:30:00")
        assert result == "2026-03-22 14:30"

    def test_none_datetime(self):
        """None devuelve datetime actual."""
        result = parse_iso_datetime(None)
        # Verificar formato
        assert len(result) == 16  # "YYYY-MM-DD HH:MM"
        assert result[4] == "-"
        assert result[7] == "-"
        assert result[10] == " "
        assert result[13] == ":"

    def test_invalid_datetime(self):
        """Datetime inválido devuelve actual."""
        result = parse_iso_datetime("invalid")
        assert len(result) == 16


# =============================================================================
# TESTS DE CONSTRUCTORES DE BLOQUES
# =============================================================================

class TestBuildEltoqueBlock:
    """Tests para build_eltoque_block."""

    def test_complete_eltoque_data(self):
        """Datos completos de ElToque."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0, "change": "up", "change_value": 5.0},
                "EUR": {"rate": 398.0, "change": "neutral", "change_value": 0},
                "MLC": {"rate": 210.0, "change": "down", "change_value": -5.0},
                "USDT": {"rate": 362.0, "change": "neutral", "change_value": 0},
            }
        }

        result = build_eltoque_block(data)

        assert "📊 *Mercado Informal (El Toque)*" in result
        assert SEPARATOR_THICK in result
        assert "🇺🇸 USD  365.00 CUP  🔺 +5.00" in result
        assert "🇪🇺 EUR  398.00 CUP  ―" in result
        assert "🧾 MLC  210.00 CUP  🔻 -5.00" in result
        assert "₮ USDT  362.00 CUP  ―" in result

    def test_empty_eltoque_data(self):
        """Datos vacíos de ElToque."""
        data = {"eltoque": {}}

        result = build_eltoque_block(data)

        assert "📊 *Mercado Informal (El Toque)*" in result
        assert "_Datos no disponibles_" in result

    def test_missing_eltoque_data(self):
        """Campo eltoque faltante."""
        data = {}

        result = build_eltoque_block(data)

        assert "_Datos no disponibles_" in result

    def test_eltoque_without_change(self):
        """Datos ElToque sin información de cambio."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0},
            }
        }

        result = build_eltoque_block(data)

        assert "🇺🇸 USD  365.00 CUP  ―" in result


class TestBuildCadecaBlock:
    """Tests para build_cadeca_block."""

    def test_complete_cadeca_data(self):
        """Datos completos de CADECA."""
        data = {
            "cadeca": {
                "USD": {"buy": 120.0, "sell": 125.0},
                "EUR": {"buy": 130.0, "sell": 136.0},
            }
        }

        result = build_cadeca_block(data)

        assert SEPARATOR_THIN in result
        assert "🏢 *CADECA* — Airports, Ports, Hotels" in result
        assert SEPARATOR_THICK in result
        assert "Currency" in result
        assert "Buy" in result
        assert "Sell" in result
        assert "USD" in result
        assert "120.00" in result
        assert "125.00" in result

    def test_empty_cadeca_data(self):
        """Datos vacíos de CADECA."""
        data = {"cadeca": {}}

        result = build_cadeca_block(data)

        assert "_Datos no disponibles_" in result

    def test_missing_cadeca_data(self):
        """Campo cadeca faltante."""
        data = {}

        result = build_cadeca_block(data)

        assert "_Datos no disponibles_" in result


class TestBuildBccBlock:
    """Tests para build_bcc_block."""

    def test_complete_bcc_data(self):
        """Datos completos de BCC."""
        data = {
            "bcc": {
                "USD": 24.0,
                "EUR": 26.50,
            }
        }

        result = build_bcc_block(data)

        assert SEPARATOR_THIN in result
        assert "🏛 *Banco Central (BCC)*" in result
        assert SEPARATOR_THICK in result
        assert "🇺🇸 USD   24.00 CUP" in result
        assert "🇪🇺 EUR   26.50 CUP" in result

    def test_bcc_with_dict_format(self):
        """Datos BCC en formato dict."""
        data = {
            "bcc": {
                "USD": {"rate": 24.0},
                "EUR": {"rate": 26.50},
            }
        }

        result = build_bcc_block(data)

        assert "🇺🇸 USD   24.00 CUP" in result
        assert "🇪🇺 EUR   26.50 CUP" in result

    def test_empty_bcc_data(self):
        """Datos vacíos de BCC."""
        data = {"bcc": {}}

        result = build_bcc_block(data)

        assert "_Datos no disponibles_" in result


class TestBuildFooter:
    """Tests para build_footer."""

    def test_footer_with_sources(self):
        """Footer con lista de fuentes."""
        data = {
            "updated_at": "2026-03-22T14:30:00Z",
            "sources": ["eltoque", "cadeca", "bcc"],
        }

        result = build_footer(data)

        assert SEPARATOR_THICK in result
        assert "📆 2026-03-22 14:30" in result
        assert "🔗" in result
        assert "elToque.com" in result
        assert "cadeca.cu" in result
        assert "bc.gob.cu" in result

    def test_footer_without_sources(self):
        """Footer sin lista de fuentes."""
        data = {
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_footer(data)

        assert "📆 2026-03-22 14:30" in result
        assert "elToque.com · cadeca.cu · bc.gob.cu" in result

    def test_footer_invalid_datetime(self):
        """Footer con datetime inválido."""
        data = {
            "updated_at": "invalid",
            "sources": ["eltoque"],
        }

        result = build_footer(data)

        assert "📆" in result
        # Debe tener formato válido aunque sea fallback


class TestBuildFullMessage:
    """Tests para build_full_message."""

    def test_complete_message(self):
        """Mensaje completo con todas las fuentes."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0, "change": "up", "change_value": 5.0},
            },
            "cadeca": {
                "USD": {"buy": 120.0, "sell": 125.0},
            },
            "bcc": {
                "USD": 24.0,
            },
            "updated_at": "2026-03-22T14:30:00Z",
            "sources": ["eltoque", "cadeca", "bcc"],
        }

        result = build_full_message(data)

        # Verificar que contiene todos los bloques
        assert "📊 *Mercado Informal (El Toque)*" in result
        assert "🏢 *CADECA*" in result
        assert "🏛 *Banco Central (BCC)*" in result
        assert "📆 2026-03-22 14:30" in result

        # Verificar separadores
        assert SEPARATOR_THICK in result
        assert SEPARATOR_THIN in result

    def test_message_only_eltoque(self):
        """Mensaje solo con ElToque."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0, "change": "up", "change_value": 5.0},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_full_message(data)

        assert "📊 *Mercado Informal (El Toque)*" in result
        assert "🏢 *CADECA*" not in result
        assert "🏛 *Banco Central (BCC)*" not in result
        assert "📆" in result

    def test_message_priority_order(self):
        """Verificar orden de prioridad de monedas."""
        data = {
            "eltoque": {
                "BTC": {"rate": 98500.0, "change": "neutral"},
                "USD": {"rate": 365.0, "change": "up", "change_value": 5.0},
                "EUR": {"rate": 398.0, "change": "neutral"},
                "USDT": {"rate": 362.0, "change": "neutral"},
                "MLC": {"rate": 210.0, "change": "down", "change_value": -5.0},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_full_message(data)

        # Verificar orden: USD, EUR, MLC, USDT, BTC
        usd_pos = result.find("USD")
        eur_pos = result.find("EUR")
        mlc_pos = result.find("MLC")
        usdt_pos = result.find("USDT")
        btc_pos = result.find("BTC")

        assert usd_pos < eur_pos < mlc_pos < usdt_pos < btc_pos
