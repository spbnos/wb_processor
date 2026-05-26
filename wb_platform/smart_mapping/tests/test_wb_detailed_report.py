"""Тесты словаря детализации WB (L0)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from smart_mapping.wb_detailed_report import match_wb_column, is_wb_detailed_columns
from smart_mapping.column_matcher import ColumnMatcher, normalize


class TestWbDetailedDictionary:
    def test_sticker_ignore(self):
        r = match_wb_column("Стикер МП")
        assert r is not None
        assert r.target_field == "ignore"
        assert r.method == "wb_ignore"

    def test_inn_partner_ignore(self):
        r = match_wb_column("ИНН партнера")
        assert r and r.target_field == "ignore"

    def test_core_sku(self):
        r = match_wb_column("Код номенклатуры")
        assert r and r.target_field == "sku" and r.method == "wb_exact"

    def test_net_profit_substring(self):
        r = match_wb_column("К перечислению Продавцу за реализованный Товар")
        assert r and r.target_field == "net_profit"

    def test_wibes_discount_ignore(self):
        r = match_wb_column("Скидка Wibes, %")
        assert r and r.target_field == "ignore"

    def test_detect_profile(self):
        cols = [
            "Тип документа",
            "Обоснование для оплаты",
            "К перечислению Продавцу за реализованный Товар",
            "Стикер МП",
        ]
        assert is_wb_detailed_columns(cols)

    def test_matcher_l0_beats_fuzzy_guess(self):
        cols = [
            "Тип документа",
            "Обоснование для оплаты",
            "К перечислению Продавцу за реализованный Товар",
            "Стикер МП",
            "ИНН партнера",
        ]
        m = ColumnMatcher()
        r = m.match("Стикер МП", columns_context=cols)
        assert r.best and r.best.target_field == "ignore"

    def test_weak_fuzzy_not_matched(self):
        cols = ["Тип документа", "Обоснование для оплаты", "К перечислению продавцу"]
        m = ColumnMatcher()
        # Нет в словаре — не должно матчиться на sku с 30%
        r = m.match("Случайная колонка XYZ", columns_context=cols)
        assert r.best is None
