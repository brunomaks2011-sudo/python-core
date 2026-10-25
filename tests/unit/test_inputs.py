"""Money, user input parsing, configuration and keyboards."""

from __future__ import annotations

import pytest

from gift_sniper.bot.callbacks import BudgetCb, FilterCb, NotifyCb, WikiCb
from gift_sniper.bot.parsing import (
    InputError,
    parse_int,
    parse_names,
    parse_percent,
    parse_period,
    parse_permille_range,
    parse_ton,
    parse_ton_range,
)
from gift_sniper.bot.ui import MAIN_SECTIONS, main_menu_kb
from gift_sniper.config import MRKT_GIFT_LINK, RunMode
from gift_sniper.domain.money import MoneyParseError, format_ton, ton_to_nano
from tests.factories import TON, make_settings


class TestMoney:
    def test_parse(self) -> None:
        assert ton_to_nano("1.5") == 1_500_000_000
        assert ton_to_nano("2,25") == 2_250_000_000
        assert ton_to_nano("3 TON") == 3 * TON
        assert ton_to_nano("0.000000001") == 1

    @pytest.mark.parametrize("bad", ["abc", "-1", "0.0000000001", "nan", "inf", "99999999"])
    def test_reject(self, bad: str) -> None:
        with pytest.raises(MoneyParseError):
            ton_to_nano(bad)

    def test_format(self) -> None:
        assert format_ton(1_500_000_000) == "1.5 TON"
        assert format_ton(10 * TON) == "10 TON"
        assert format_ton(None) == "Нет данных"
        assert format_ton(1) == "0.000000001 TON"


class TestParsing:
    def test_ton_range(self) -> None:
        assert parse_ton_range("1.5-10") == (1_500_000_000, 10 * TON)
        assert parse_ton_range("-10") == (None, 10 * TON)
        assert parse_ton_range("2-") == (2 * TON, None)
        assert parse_ton_range("-") == (None, None)
        for bad in ("10-1", "1-2-3", "abc"):
            with pytest.raises(InputError):
                parse_ton_range(bad)

    def test_permille_range(self) -> None:
        assert parse_permille_range("5-20") == (5, 20)
        assert parse_permille_range("-15") == (None, 15)
        with pytest.raises(InputError):
            parse_permille_range("5-2000")

    def test_names(self) -> None:
        assert parse_names("Plush Pepe, Lunar  Snake;Durov's Cap") == [
            "Plush Pepe",
            "Lunar Snake",
            "Durov's Cap",
        ]
        assert parse_names("-") == []

    def test_numbers(self) -> None:
        assert parse_int("5", minimum=1) == 5
        assert parse_int("-") is None
        with pytest.raises(InputError):
            parse_int("0", minimum=1)
        assert parse_percent("15%") == 15.0
        with pytest.raises(InputError):
            parse_percent("150")
        assert parse_period("3/24") == (3, 24)
        with pytest.raises(InputError):
            parse_period("3")
        with pytest.raises(InputError):
            parse_ton("0")


class TestConfig:
    def test_ids_and_permissions(self) -> None:
        s = make_settings(admin_user_ids="1, 2", allowed_user_ids="3", purchase_user_ids="")
        assert s.admin_user_ids == [1, 2]
        assert s.is_allowed(3) and not s.is_allowed(4)
        assert s.can_purchase(1) and not s.can_purchase(3)
        s2 = make_settings(admin_user_ids=[1], purchase_user_ids=[3])
        assert s2.can_purchase(3) and not s2.can_purchase(1)

    def test_empty_secrets_are_none(self) -> None:
        s = make_settings(mrkt_access_token="", giftwiki_api_key="  ")
        assert s.mrkt_access_token is None and not s.mrkt_configured
        assert not s.giftwiki_configured

    def test_safe_default_mode(self) -> None:
        from gift_sniper.config import Settings

        assert Settings.model_fields["run_mode"].default is RunMode.DRY_RUN

    def test_empty_gift_link_template_means_the_mrkt_share_link(self) -> None:
        assert make_settings(mrkt_listing_url_template="").mrkt_listing_url_template == MRKT_GIFT_LINK
        assert make_settings().mrkt_listing_url_template == "https://t.me/mrkt/app?startapp={gift_id_hex}"
        custom = "https://example.com/{gift_id}"
        assert make_settings(mrkt_listing_url_template=custom).mrkt_listing_url_template == custom


class TestKeyboards:
    def test_main_menu_has_all_sections(self) -> None:
        kb = main_menu_kb()
        texts = [b.text for row in kb.inline_keyboard for b in row]
        assert len(texts) == 11
        assert texts == [t for t, _ in MAIN_SECTIONS]
        for expected in ("Автопокупка подарков", "Автопокупка монохромов", "Управление ботом", "Gift Wiki"):
            assert any(expected in t for t in texts)

    def test_mini_app_button_comes_first(self) -> None:
        rows = main_menu_kb("https://sniper.example.com/app/").inline_keyboard
        assert rows[0][0].web_app is not None and rows[0][0].web_app.url == "https://sniper.example.com/app/"
        assert [b.text for row in rows[1:] for b in row] == [t for t, _ in MAIN_SECTIONS]

    def test_callback_data_fits_telegram_limit(self) -> None:
        samples = [
            FilterCb(action="delete_ok", id=2**31, field="mshare").pack(),
            BudgetCb(action="edit", scope="monochrome", field="tot").pack(),
            NotifyCb(action="toggle", field="matching_only").pack(),
            WikiCb(action="gift", page=999, token="x" * 8).pack(),
        ]
        assert all(len(s.encode()) <= 64 for s in samples)
