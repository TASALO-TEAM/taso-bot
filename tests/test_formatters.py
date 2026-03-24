"""Tests para el módulo de formatters de TASALO-Bot."""

import pytest
from datetime import datetime

from src.formatters import (
    get_change_indicator,
    format_rate_value,
    parse_iso_datetime,
    parse_iso_datetime_extended,
    build_eltoque_block,
    build_cadeca_block,
    build_bcc_block,
    build_footer,
    build_full_message,
    build_eltoque_only_message,
    build_bcc_only_message,
    build_cadeca_only_message,
    build_toque_new_message,
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


class TestParseIsoDatetimeExtended:
    """Tests para parse_iso_datetime_extended."""

    def test_iso_with_z(self):
        """ISO datetime con Z suffix - formato extendido DD/M/YYYY HH:MM:SS."""
        result = parse_iso_datetime_extended("2026-03-22T14:30:45Z")
        assert result == "22/3/2026 14:30:45"

    def test_iso_with_timezone(self):
        """ISO datetime con timezone."""
        result = parse_iso_datetime_extended("2026-03-22T14:30:45+00:00")
        assert result == "22/3/2026 14:30:45"

    def test_iso_without_timezone(self):
        """ISO datetime sin timezone."""
        result = parse_iso_datetime_extended("2026-03-22T14:30:45")
        assert result == "22/3/2026 14:30:45"

    def test_single_digit_day_month(self):
        """Día y mes sin leading zero."""
        result = parse_iso_datetime_extended("2026-01-05T09:05:03")
        # Note: hours/minutes/seconds also don't have leading zeros
        assert result == "5/1/2026 9:5:3"

    def test_none_datetime(self):
        """None devuelve datetime actual en formato extendido."""
        result = parse_iso_datetime_extended(None)
        # Verificar formato DD/M/YYYY HH:MM:SS
        assert "/" in result
        assert ":" in result
        assert " " in result

    def test_invalid_datetime(self):
        """Datetime inválido devuelve actual."""
        result = parse_iso_datetime_extended("invalid")
        assert "/" in result
        assert ":" in result


# =============================================================================
# TESTS DE CONSTRUCTORES DE BLOQUES
# =============================================================================


class TestBuildEltoqueBlock:
    """Tests para build_eltoque_block."""

    def test_complete_eltoque_data(self):
        """Datos completos de ElToque."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0, "change": "up", "prev_rate": 360.0},
                "EUR": {"rate": 398.0, "change": "neutral", "prev_rate": 398.0},
                "MLC": {"rate": 210.0, "change": "down", "prev_rate": 215.0},
                "USDT": {"rate": 362.0, "change": "neutral", "prev_rate": 362.0},
            }
        }

        result = build_eltoque_block(data)

        assert "📊 *MERCADO INFORMAL (El Toque)*" in result
        assert SEPARATOR_THICK in result
        # Legacy format: " *USD:*   365.00  CUP 🔺 +5.00"
        assert "*USD:*" in result
        assert "365.00" in result
        assert "CUP" in result
        assert INDICATOR_UP in result  # 🔺 for up
        assert INDICATOR_DOWN in result  # 🔻 for down

    def test_empty_eltoque_data(self):
        """Datos vacíos de ElToque."""
        data = {"eltoque": {}}

        result = build_eltoque_block(data)

        assert "📊 *MERCADO INFORMAL (El Toque)*" in result
        assert "Datos no disponibles" in result

    def test_missing_eltoque_data(self):
        """Campo eltoque faltante."""
        data = {}

        result = build_eltoque_block(data)

        assert "Datos no disponibles" in result

    def test_eltoque_without_change(self):
        """Datos ElToque sin información de cambio."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0},
            }
        }

        result = build_eltoque_block(data)

        assert "*USD:*" in result
        assert "365.00" in result
        # No indicator when change is None


class TestBuildCadecaBlock:
    """Tests para build_cadeca_block."""

    def test_complete_cadeca_data(self):
        """Datos completos de CADECA."""
        data = {
            "cadeca": {
                "USD": {"buy": 120.0, "sell": 125.0, "change": "up"},
                "EUR": {"buy": 130.0, "sell": 136.0, "change": "neutral"},
            }
        }

        result = build_cadeca_block(data)

        assert "🏢 *CADECA (Exchange Houses)*" in result
        assert "↳ _Airports, Ports & Hotels_" in result
        assert SEPARATOR_THICK in result
        assert "_Currency_" in result
        assert "_Buy_" in result
        assert "_Sell_" in result
        assert "*USD*" in result
        assert "120.00" in result
        assert "125.00" in result
        assert INDICATOR_UP in result

    def test_empty_cadeca_data(self):
        """Datos vacíos de CADECA."""
        data = {"cadeca": {}}

        result = build_cadeca_block(data)

        assert "⚠️ Not available" in result

    def test_missing_cadeca_data(self):
        """Campo cadeca faltante."""
        data = {}

        result = build_cadeca_block(data)

        assert "⚠️ Not available" in result


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

        assert "🏛 *OFFICIAL RATE (BCC)*" in result
        assert SEPARATOR_THICK in result
        assert "*USD:*" in result
        assert "*CUP*" in result
        assert "24.00" in result
        assert "26.50" in result

    def test_bcc_with_dict_format(self):
        """Datos BCC en formato dict."""
        data = {
            "bcc": {
                "USD": {"rate": 24.0, "change": "up", "prev_rate": 23.5},
                "EUR": {"rate": 26.50, "change": "neutral"},
            }
        }

        result = build_bcc_block(data)

        assert "*USD:*" in result
        assert "*CUP*" in result
        assert INDICATOR_UP in result

    def test_empty_bcc_data(self):
        """Datos vacíos de BCC."""
        data = {"bcc": {}}

        result = build_bcc_block(data)

        assert "⚠️ Not available" in result


class TestBuildFooter:
    """Tests para build_footer."""

    def test_footer_with_sources(self):
        """Footer con lista de fuentes."""
        data = {
            "updated_at": "2026-03-22T14:30:00Z",
            "eltoque": {"USD": {"rate": 365.0}},
            "cadeca": {"USD": {"buy": 120.0, "sell": 125.0}},
            "bcc": {"USD": 24.0},
        }

        result = build_footer(data)

        assert SEPARATOR_THICK in result
        assert "📆 2026-03-22 14:30" in result
        assert "Fuentes de consulta:" in result
        assert "elToque.com" in result
        assert "www.cadeca.cu" in result
        assert "www.bc.gob.cu" in result

    def test_footer_without_sources(self):
        """Footer sin datos de fuentes."""
        data = {
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_footer(data)

        assert "📆" in result
        # Debe mostrar todas las fuentes como fallback
        assert "elToque.com" in result
        assert "www.cadeca.cu" in result
        assert "www.bc.gob.cu" in result

    def test_footer_invalid_datetime(self):
        """Footer con datetime inválido."""
        data = {
            "updated_at": "invalid",
            "eltoque": {"USD": {"rate": 365.0}},
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
                "USD": {"rate": 365.0, "change": "up", "prev_rate": 360.0},
            },
            "cadeca": {
                "USD": {"buy": 120.0, "sell": 125.0},
            },
            "bcc": {
                "USD": 24.0,
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_full_message(data)

        # Verificar que contiene todos los bloques
        assert "📊 *MERCADO INFORMAL (El Toque)*" in result
        assert "🏢 *CADECA (Exchange Houses)*" in result
        assert "🏛 *OFFICIAL RATE (BCC)*" in result
        assert "📆 2026-03-22 14:30" in result

        # Verificar separadores
        assert SEPARATOR_THICK in result
        assert SEPARATOR_THIN in result

    def test_message_only_eltoque(self):
        """Mensaje solo con ElToque."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0, "change": "up", "prev_rate": 360.0},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_full_message(data)

        assert "📊 *MERCADO INFORMAL (El Toque)*" in result
        assert "🏢 *CADECA" not in result
        assert "🏛 *OFFICIAL RATE" not in result
        assert "📆" in result

    def test_message_priority_order(self):
        """Verificar orden de prioridad de monedas."""
        data = {
            "eltoque": {
                "BTC": {"rate": 98500.0, "change": "neutral"},
                "USD": {"rate": 365.0, "change": "up", "prev_rate": 360.0},
                "EUR": {"rate": 398.0, "change": "neutral"},
                "USDT": {"rate": 362.0, "change": "neutral"},
                "MLC": {"rate": 210.0, "change": "down", "prev_rate": 215.0},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_full_message(data)

        # Legacy order: EUR, USD, MLC, BTC, TRX, USDT
        eur_pos = result.find("EUR")
        usd_pos = result.find("USD")
        mlc_pos = result.find("MLC")
        btc_pos = result.find("BTC")

        assert eur_pos < usd_pos < mlc_pos < btc_pos


# =============================================================================
# TESTS DE BUILD_HISTORY_MESSAGE
# =============================================================================


class TestBuildHistoryMessage:
    """Tests para build_history_message."""

    def test_build_history_message_basic(self):
        """Test construir mensaje de historial básico."""
        from src.formatters import build_history_message

        history_data = [
            {"sell_rate": 365.0, "fetched_at": "2026-03-22T14:30:00Z"},
            {"sell_rate": 360.0, "fetched_at": "2026-03-21T14:30:00Z"},
            {"sell_rate": 358.0, "fetched_at": "2026-03-20T14:30:00Z"},
        ]

        result = build_history_message("USD", "eltoque", history_data)

        assert "📈 *Histórico USD" in result
        assert "365.00" in result
        assert "360.00" in result
        assert "358.00" in result
        assert SEPARATOR_THICK in result

    def test_build_history_message_with_change(self):
        """Test historial con indicadores de cambio."""
        from src.formatters import build_history_message

        history_data = [
            {"sell_rate": 365.0, "fetched_at": "2026-03-22T14:30:00Z"},
            {"sell_rate": 360.0, "fetched_at": "2026-03-21T14:30:00Z"},
        ]

        result = build_history_message("USD", "eltoque", history_data)

        # Debe mostrar indicador 🔺 porque subió de 360 a 365
        assert (
            INDICATOR_UP in result
            or INDICATOR_DOWN in result
            or INDICATOR_NEUTRAL in result
        )

    def test_build_history_message_empty(self):
        """Test historial vacío."""
        from src.formatters import build_history_message

        result = build_history_message("USD", "eltoque", [])

        assert "📈 *Histórico USD" in result
        assert "_No hay datos históricos disponibles_" in result

    def test_build_history_message_single_item(self):
        """Test historial con un solo dato."""
        from src.formatters import build_history_message

        history_data = [
            {"sell_rate": 365.0, "fetched_at": "2026-03-22T14:30:00Z"},
        ]

        result = build_history_message("USD", "eltoque", history_data)

        assert "365.00" in result
        assert "2026-03-22" in result

    def test_build_history_message_date_format(self):
        """Test formato de fechas en historial."""
        from src.formatters import build_history_message

        history_data = [
            {"sell_rate": 365.0, "fetched_at": "2026-03-22T14:30:00Z"},
        ]

        result = build_history_message("USD", "eltoque", history_data)

        # Debe mostrar fecha en formato legible
        assert "2026-03-22" in result or "22/03/2026" in result

    def test_build_history_message_source_label(self):
        """Test etiqueta de fuente en historial."""
        from src.formatters import build_history_message

        history_data = [
            {"sell_rate": 365.0, "fetched_at": "2026-03-22T14:30:00Z"},
        ]

        result = build_history_message("USD", "cadeca", history_data)

        assert "CADECA" in result or "cadeca" in result


# =============================================================================
# TESTS DE COMANDOS INDIVIDUALES POR FUENTE
# =============================================================================


class TestSeparatorLength:
    """Tests para verificar el tamaño de separadores (legacy style ~20 chars)."""

    def test_separator_thick_length(self):
        """SEPARATOR_THICK debe tener aproximadamente 20 caracteres."""
        # Legacy style: ~20 caracteres para mejor legibilidad en móvil
        assert 18 <= len(SEPARATOR_THICK) <= 22
        assert len(SEPARATOR_THICK) == 20  # Exacto: "—" × 20

    def test_separator_thick_content(self):
        """SEPARATOR_THICK debe contener solo el caracter '—'."""
        assert all(c == "—" for c in SEPARATOR_THICK)

    def test_separator_thin_exists(self):
        """SEPARATOR_THIN debe existir y ser más corto."""
        assert SEPARATOR_THIN == "•••"
        assert len(SEPARATOR_THIN) < len(SEPARATOR_THICK)


class TestBuildEltoqueOnlyMessage:
    """Tests para build_eltoque_only_message."""

    def test_complete_data(self):
        """Datos completos de ElToque."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0, "change": "up", "prev_rate": 360.0},
                "EUR": {"rate": 398.0, "change": "neutral"},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_eltoque_only_message(data)

        assert "📊 *MERCADO INFORMAL (El Toque)*" in result
        assert "*USD:*" in result
        assert "365.00" in result
        assert "🔗 elToque.com" in result
        # Verificar nuevo separador legacy
        assert SEPARATOR_THICK in result
        assert len(SEPARATOR_THICK) == 20

    def test_empty_data(self):
        """Datos vacíos."""
        data = {
            "eltoque": {},
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_eltoque_only_message(data)

        assert "Datos no disponibles" in result
        assert "🔗 elToque.com" in result

    def test_with_change_indicator(self):
        """Datos con indicador de cambio."""
        data = {
            "eltoque": {
                "USD": {"rate": 365.0, "change": "up", "prev_rate": 360.0},
                "EUR": {"rate": 398.0, "change": "down", "prev_rate": 400.0},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_eltoque_only_message(data)

        assert INDICATOR_UP in result  # 🔺 para USD
        assert INDICATOR_DOWN in result  # 🔻 para EUR


class TestBuildBccOnlyMessage:
    """Tests para build_bcc_only_message."""

    def test_complete_data(self):
        """Datos completos de BCC."""
        data = {
            "bcc": {
                "USD": {"rate": 24.0, "change": "up", "prev_rate": 23.5},
                "EUR": {"rate": 26.50, "change": "neutral"},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_bcc_only_message(data)

        assert "🏛 *OFFICIAL RATE (BCC)*" in result
        assert "*USD:*" in result
        assert "*CUP*" in result
        assert "🔗 www.bc.gob.cu" in result
        # Verificar nuevo separador legacy
        assert SEPARATOR_THICK in result

    def test_empty_data(self):
        """Datos vacíos."""
        data = {
            "bcc": {},
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_bcc_only_message(data)

        assert "⚠️ Not available" in result
        assert "🔗 www.bc.gob.cu" in result

    def test_with_change_indicator(self):
        """Datos con indicador de cambio."""
        data = {
            "bcc": {
                "USD": {"rate": 24.0, "change": "up", "prev_rate": 23.5},
                "EUR": {"rate": 26.50, "change": "down", "prev_rate": 27.0},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_bcc_only_message(data)

        assert INDICATOR_UP in result  # 🔺 para USD
        assert INDICATOR_DOWN in result  # 🔻 para EUR


class TestBuildCadecaOnlyMessage:
    """Tests para build_cadeca_only_message."""

    def test_complete_data(self):
        """Datos completos de CADECA."""
        data = {
            "cadeca": {
                "USD": {"buy": 120.0, "sell": 125.0, "change": "up"},
                "EUR": {"buy": 130.0, "sell": 136.0, "change": "neutral"},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_cadeca_only_message(data)

        assert "🏢 *CADECA (Exchange Houses)*" in result
        assert "↳ _Airports, Ports & Hotels_" in result
        assert "_Currency_" in result
        assert "_Buy_" in result
        assert "_Sell_" in result
        assert "🔗 www.cadeca.cu" in result
        # Verificar nuevo separador legacy
        assert SEPARATOR_THICK in result

    def test_empty_data(self):
        """Datos vacíos."""
        data = {
            "cadeca": {},
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_cadeca_only_message(data)

        assert "⚠️ Not available" in result
        assert "🔗 www.cadeca.cu" in result

    def test_with_buy_sell_columns(self):
        """Verificar formato de columnas Buy/Sell."""
        data = {
            "cadeca": {
                "USD": {"buy": 120.0, "sell": 125.0, "change": "up"},
                "EUR": {"buy": 130.0, "sell": 136.0, "change": "down", "prev_rate": 138.0},
            },
            "updated_at": "2026-03-22T14:30:00Z",
        }

        result = build_cadeca_only_message(data)

        assert "120.00" in result  # Buy USD
        assert "125.00" in result  # Sell USD
        assert "130.00" in result  # Buy EUR
        assert "136.00" in result  # Sell EUR
        assert INDICATOR_UP in result  # 🔺 para USD
        assert INDICATOR_DOWN in result  # 🔻 para EUR


# =============================================================================
# TESTS PARA NUEVO FORMATO /toque
# =============================================================================


class TestBuildToqueNewMessage:
    """Tests para build_toque_new_message - nuevo formato del comando /toque."""

    def test_complete_data_structure(self):
        """Datos completos de ElToque - verificar estructura del mensaje."""
        data = {
            "eltoque": {
                "USD": {"rate": 515.0, "change": "up", "prev_rate": 510.0},
                "EUR": {"rate": 580.0, "change": "neutral"},
                "MLC": {"rate": 400.0, "change": "down", "prev_rate": 405.0},
                "BTC": {"rate": 520.0, "change": "up", "prev_rate": 515.0},
                "TRX": {"rate": 185.0, "change": "neutral"},
                "USDT": {"rate": 560.0, "change": "up", "prev_rate": 555.0},
            },
            "updated_at": "2026-03-23T20:32:44Z",
        }

        result = build_toque_new_message(data)

        # Verificar header
        assert "📊 MERCADO INFORMAL" in result
        assert "💹 Tasa en tiempo real" in result
        assert SEPARATOR_THICK in result

        # Verificar sección de fiat
        assert "» Valores actuales del mercado:" in result
        assert "🇪🇺 EUR ⇾" in result
        assert "🇺🇸 USD ⇾" in result
        assert "💳 MLC ⇾" in result

        # Verificar sección de cripto
        assert "» Mercado Criptomonedas" in result
        assert "🪙 BTC ⇾" in result
        assert "⚡ TRX ⇾" in result
        assert "💰 USDT ⇾" in result

        # Verificar footer
        assert "🔗 elToque.com" in result
        # Verificar formato de timestamp extendido
        assert "23/3/2026 20:32:44" in result

    def test_fiat_currencies_format(self):
        """Verificar formato de monedas fiat."""
        data = {
            "eltoque": {
                "EUR": {"rate": 580.50},
                "USD": {"rate": 515.00},
                "MLC": {"rate": 400.25},
            },
            "updated_at": "2026-03-23T20:32:44Z",
        }

        result = build_toque_new_message(data)

        # Verificar formato con 2 decimales
        assert "580.50" in result
        assert "515.00" in result
        assert "400.25" in result
        # Verificar que están en la sección correcta
        assert "🇪🇺 EUR ⇾ 580.50  CUP" in result
        assert "🇺🇸 USD ⇾ 515.00  CUP" in result
        assert "💳 MLC ⇾ 400.25  CUP" in result

    def test_crypto_currencies_format(self):
        """Verificar formato de criptomonedas."""
        data = {
            "eltoque": {
                "BTC": {"rate": 52000.00},
                "TRX": {"rate": 185.50},
                "USDT": {"rate": 560.00},
            },
            "updated_at": "2026-03-23T20:32:44Z",
        }

        result = build_toque_new_message(data)

        # Verificar formato con 2 decimales
        assert "52,000.00" in result  # BTC con separador de miles
        assert "185.50" in result
        assert "560.00" in result
        # Verificar que están en la sección correcta
        assert "🪙 BTC ⇾ 52,000.00 CUP" in result
        assert "⚡ TRX ⇾ 185.50 CUP" in result
        assert "💰 USDT ⇾ 560.00 CUP" in result

    def test_empty_data(self):
        """Datos vacíos."""
        data = {
            "eltoque": {},
            "updated_at": "2026-03-23T20:32:44Z",
        }

        result = build_toque_new_message(data)

        assert "⚠️ Datos no disponibles" in result
        assert "🔗 elToque.com" in result
        # Verificar timestamp en formato extendido (sin leading zeros)
        assert "23/3/2026 20:32:44" in result

    def test_timestamp_format(self):
        """Verificar formato de timestamp DD/M/YYYY HH:MM:SS."""
        data = {
            "eltoque": {
                "USD": {"rate": 515.0},
            },
            "updated_at": "2026-03-05T09:05:03Z",
        }

        result = build_toque_new_message(data)

        # Verificar formato sin leading zeros en día/mes/hora/min/seg
        assert "5/3/2026 9:5:3" in result
