"""Tests para src/services/ads_manager.py."""

import pytest
from unittest.mock import AsyncMock, patch

from src.services import ads_manager


@pytest.fixture(autouse=True)
def _reset_state():
    """Resetea el estado de módulo (última id mostrada) y el cache entre tests."""
    ads_manager._last_shown_id = None
    ads_manager.cache.invalidate(ads_manager._CACHE_KEY)
    yield
    ads_manager._last_shown_id = None
    ads_manager.cache.invalidate(ads_manager._CACHE_KEY)


class TestEscapeAdText:
    def test_strips_markdown_special_chars(self):
        raw = "Promo _increíble_ *ahora* con `código` y [link]"
        cleaned = ads_manager._escape_ad_text(raw)
        assert "_" not in cleaned
        assert "*" not in cleaned
        assert "`" not in cleaned
        assert "[" not in cleaned
        assert "]" not in cleaned

    def test_empty_text_returns_empty(self):
        assert ads_manager._escape_ad_text("") == ""


class TestFormatAdBlock:
    def test_sponsored_label_with_markdown(self):
        ad = {"text": "Promo externa", "is_sponsored": True}
        block = ads_manager.format_ad_block(ad, markdown=True)
        assert "*Patrocinado:*" in block
        assert "Promo externa" in block

    def test_aviso_label_default(self):
        ad = {"text": "Nuevo canal", "is_sponsored": False}
        block = ads_manager.format_ad_block(ad, markdown=True)
        assert "*Aviso:*" in block

    def test_without_markdown_drops_asterisks(self):
        """Cuando el mensaje anfitrión usa parse_mode=None (entidades DATE_TIME),
        el bloque no debe llevar asteriscos literales."""
        ad = {"text": "Nuevo canal", "is_sponsored": False}
        block = ads_manager.format_ad_block(ad, markdown=False)
        assert "*" not in block
        assert "Aviso:" in block

    def test_empty_ad_text_returns_empty_block(self):
        ad = {"text": "", "is_sponsored": False}
        assert ads_manager.format_ad_block(ad) == ""


class TestSafeAppend:
    def test_appends_when_within_limit(self):
        base = "Precio actual: $100"
        block = "\n---\nAviso: promo"
        result = ads_manager.safe_append(base, block, hard_limit=4096)
        assert result == base + block

    def test_omits_when_over_limit(self):
        base = "x" * 4090
        block = "\n---\nAviso: promo"
        result = ads_manager.safe_append(base, block, hard_limit=4096)
        assert result == base

    def test_noop_when_ad_block_empty(self):
        base = "Precio actual: $100"
        assert ads_manager.safe_append(base, "") == base


class TestGetAdBlock:
    @pytest.mark.asyncio
    async def test_disabled_kill_switch_returns_empty(self):
        api_client = AsyncMock()
        api_client.get_active_ads = AsyncMock(return_value=[{"id": 1, "text": "x", "weight": 1}])
        with patch("src.services.ads_manager.settings") as mock_settings:
            mock_settings.ads_enabled = False
            result = await ads_manager.get_ad_block(api_client)
        assert result == ""
        api_client.get_active_ads.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_active_ads_returns_empty(self):
        api_client = AsyncMock()
        api_client.get_active_ads = AsyncMock(return_value=[])
        with patch("src.services.ads_manager.settings") as mock_settings:
            mock_settings.ads_enabled = True
            result = await ads_manager.get_ad_block(api_client)
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_formatted_block_when_ad_available(self):
        api_client = AsyncMock()
        api_client.get_active_ads = AsyncMock(
            return_value=[{"id": 1, "text": "Visita nuestro canal", "is_sponsored": False, "weight": 1}]
        )
        with patch("src.services.ads_manager.settings") as mock_settings:
            mock_settings.ads_enabled = True
            result = await ads_manager.get_ad_block(api_client)
        assert "Visita nuestro canal" in result

    @pytest.mark.asyncio
    async def test_uses_cache_avoids_repeated_api_calls(self):
        api_client = AsyncMock()
        api_client.get_active_ads = AsyncMock(
            return_value=[{"id": 1, "text": "Aviso 1", "is_sponsored": False, "weight": 1}]
        )
        with patch("src.services.ads_manager.settings") as mock_settings:
            mock_settings.ads_enabled = True
            await ads_manager.get_ad_block(api_client)
            await ads_manager.get_ad_block(api_client)
            await ads_manager.get_ad_block(api_client)
        api_client.get_active_ads.assert_called_once()

    @pytest.mark.asyncio
    async def test_avoids_immediate_repeat_with_multiple_ads(self):
        api_client = AsyncMock()
        api_client.get_active_ads = AsyncMock(return_value=[
            {"id": 1, "text": "Aviso 1", "is_sponsored": False, "weight": 1},
            {"id": 2, "text": "Aviso 2", "is_sponsored": False, "weight": 1},
        ])
        with patch("src.services.ads_manager.settings") as mock_settings:
            mock_settings.ads_enabled = True
            seen_ids = []
            for _ in range(20):
                await ads_manager.get_ad_block(api_client)
                seen_ids.append(ads_manager._last_shown_id)
        # Nunca dos ids iguales consecutivos
        for a, b in zip(seen_ids, seen_ids[1:]):
            assert a != b

    @pytest.mark.asyncio
    async def test_never_raises_on_api_error(self):
        api_client = AsyncMock()
        api_client.get_active_ads = AsyncMock(side_effect=Exception("network down"))
        with patch("src.services.ads_manager.settings") as mock_settings:
            mock_settings.ads_enabled = True
            result = await ads_manager.get_ad_block(api_client)
        assert result == ""


class TestInvalidateAdCache:
    @pytest.mark.asyncio
    async def test_invalidate_forces_fresh_fetch(self):
        api_client = AsyncMock()
        api_client.get_active_ads = AsyncMock(
            return_value=[{"id": 1, "text": "Aviso", "is_sponsored": False, "weight": 1}]
        )
        with patch("src.services.ads_manager.settings") as mock_settings:
            mock_settings.ads_enabled = True
            await ads_manager.get_ad_block(api_client)
            ads_manager.invalidate_ad_cache()
            await ads_manager.get_ad_block(api_client)
        assert api_client.get_active_ads.call_count == 2
