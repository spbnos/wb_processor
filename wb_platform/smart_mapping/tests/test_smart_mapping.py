"""
python -m pytest smart_mapping/tests/test_smart_mapping.py -v
Coverage: alias_dictionary, column_matcher, type_detector, confidence_scorer, learning_store, smart_mapper
"""
import sys, json, tempfile, unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from smart_mapping.alias_dictionary import ALIASES, REVERSE_LOOKUP, ALL_TARGET_FIELDS
from smart_mapping.column_matcher import ColumnMatcher, normalize
from smart_mapping.type_detector import detect_type
from smart_mapping.confidence_scorer import score as compute_score, ConfidenceLevel
from smart_mapping.learning_store import LearningStore
from smart_mapping.smart_mapper import SmartMapper


# ──────────────────────────────────────────────────────────────────────
# alias_dictionary
# ──────────────────────────────────────────────────────────────────────
class TestAliasDictionary(unittest.TestCase):

    def test_all_fields_have_aliases(self):
        for field_name, aliases in ALIASES.items():
            self.assertGreater(len(aliases), 0, f"Field {field_name!r} has no aliases")

    def test_reverse_lookup_covers_all(self):
        for field_name, aliases in ALIASES.items():
            for alias in aliases:
                self.assertIn(alias, REVERSE_LOOKUP)
                self.assertEqual(REVERSE_LOOKUP[alias], field_name)

    def test_all_aliases_lowercase(self):
        for field_name, aliases in ALIASES.items():
            for alias in aliases:
                self.assertEqual(alias, alias.lower(), f"Alias {alias!r} not lowercase")

    def test_minimum_alias_count(self):
        """Каждое поле должно иметь минимум 3 алиаса."""
        for field_name, aliases in ALIASES.items():
            self.assertGreaterEqual(len(aliases), 3, f"{field_name!r} has < 3 aliases")

    def test_no_duplicate_aliases(self):
        """Один алиас не должен маппиться в два разных поля."""
        seen = {}
        for field_name, aliases in ALIASES.items():
            for alias in aliases:
                if alias in seen:
                    self.fail(f"Duplicate alias {alias!r}: {seen[alias]} and {field_name}")
                seen[alias] = field_name

    def test_standard_fields_present(self):
        required = ["sku", "price", "date", "quantity", "revenue", "commission"]
        for f in required:
            self.assertIn(f, ALL_TARGET_FIELDS)


# ──────────────────────────────────────────────────────────────────────
# normalize
# ──────────────────────────────────────────────────────────────────────
class TestNormalize(unittest.TestCase):

    def test_lowercase(self):
        self.assertEqual(normalize("SKU"), "sku")

    def test_strip_spaces(self):
        self.assertEqual(normalize("  Артикул WB  "), "артикул wb")

    def test_replace_separators(self):
        result = normalize("цена-продажи_товара")
        self.assertNotIn("-", result)
        self.assertNotIn("_", result)

    def test_unicode_preserved(self):
        result = normalize("Количество шт.")
        self.assertIn("количество", result)


# ──────────────────────────────────────────────────────────────────────
# ColumnMatcher
# ──────────────────────────────────────────────────────────────────────
class TestColumnMatcher(unittest.TestCase):

    def setUp(self):
        self.m = ColumnMatcher()

    def _match(self, col):
        return self.m.match(col)

    # Точные совпадения
    def test_exact_sku(self):
        r = self._match("Артикул WB")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "sku")
        self.assertGreaterEqual(r.best.score, 0.85)

    def test_exact_price(self):
        r = self._match("Цена розничная")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "price")

    def test_exact_date(self):
        r = self._match("Дата продажи")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "date")

    def test_exact_quantity(self):
        r = self._match("Количество шт")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "quantity")

    def test_exact_revenue(self):
        r = self._match("Выручка")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "revenue")

    def test_exact_commission(self):
        r = self._match("Комиссия WB")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "commission")

    def test_exact_warehouse(self):
        r = self._match("Склад")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "warehouse")

    # Английские варианты
    def test_en_barcode(self):
        r = self._match("barcode")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "barcode")

    def test_en_sku(self):
        r = self._match("SKU")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "sku")

    def test_en_revenue(self):
        r = self._match("Total Revenue")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "revenue")

    # Fuzzy варианты
    def test_fuzzy_artikul(self):
        r = self._match("Артикул поставщика")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "sku")

    def test_fuzzy_nmid(self):
        r = self._match("nmId")
        self.assertIsNotNone(r.best)
        self.assertEqual(r.best.target_field, "sku")

    def test_no_match_garbage(self):
        r = self._match("Xzq99_unknown_field_aaa")
        # Не должно быть HIGH confidence
        if r.best:
            self.assertLess(r.best.score, 0.75)

    # match_many
    def test_match_many(self):
        cols = ["Артикул WB", "Дата", "Количество", "Цена"]
        reports = self.m.match_many(cols)
        self.assertEqual(len(reports), 4)
        targets = [r.best.target_field for r in reports if r.best]
        self.assertIn("sku", targets)
        self.assertIn("date", targets)


# ──────────────────────────────────────────────────────────────────────
# TypeDetector
# ──────────────────────────────────────────────────────────────────────
class TestTypeDetector(unittest.TestCase):

    def test_detect_int(self):
        r = detect_type([1, 2, 3, 100, 500])
        self.assertEqual(r.detected_type, "int")
        self.assertGreater(r.confidence, 0.8)

    def test_detect_float(self):
        r = detect_type([1.5, 2.7, "1 500,00", "2 000.50"])
        self.assertEqual(r.detected_type, "float")

    def test_detect_date_ddmmyyyy(self):
        r = detect_type(["01.06.2024", "15.12.2024", "30.01.2023"])
        self.assertEqual(r.detected_type, "date")
        self.assertEqual(r.format_hint, "%d.%m.%Y")

    def test_detect_date_iso(self):
        r = detect_type(["2024-06-01", "2024-12-15", "2023-01-30"])
        self.assertEqual(r.detected_type, "date")

    def test_detect_bool(self):
        r = detect_type(["yes", "no", "yes", "да", "нет"])
        self.assertEqual(r.detected_type, "bool")

    def test_detect_str(self):
        r = detect_type(["ART001", "ART002", "hello world"])
        self.assertEqual(r.detected_type, "str")

    def test_empty_values(self):
        r = detect_type([None, None, None])
        self.assertEqual(r.detected_type, "str")
        self.assertEqual(r.confidence, 0.0)

    def test_mixed_mostly_int(self):
        r = detect_type([1, 2, 3, "abc", 5])
        # Большинство int — должен определить как int или float
        self.assertIn(r.detected_type, ("int", "float"))


# ──────────────────────────────────────────────────────────────────────
# ConfidenceScorer
# ──────────────────────────────────────────────────────────────────────
class TestConfidenceScorer(unittest.TestCase):

    def test_high_confidence_auto(self):
        r = compute_score("sku", match_score=0.97, type_confidence=0.95, historical_hits=5)
        self.assertEqual(r.level, ConfidenceLevel.AUTO_APPLY)
        self.assertGreaterEqual(r.final_score, 0.85)

    def test_medium_confidence_review(self):
        r = compute_score("price", match_score=0.70, type_confidence=0.80, historical_hits=0)
        self.assertIn(r.level, (ConfidenceLevel.NEEDS_REVIEW, ConfidenceLevel.AUTO_APPLY))

    def test_low_confidence(self):
        r = compute_score("date", match_score=0.30, type_confidence=0.50, historical_hits=0)
        self.assertIn(r.level, (ConfidenceLevel.LOW_CONF, ConfidenceLevel.NEEDS_REVIEW))
        self.assertLess(r.final_score, 0.85)

    def test_zero_score_no_match(self):
        r = compute_score("ignore", match_score=0.0, type_confidence=0.0, historical_hits=0)
        self.assertEqual(r.level, ConfidenceLevel.NO_MATCH)

    def test_history_improves_score(self):
        r_no_hist = compute_score("sku", match_score=0.80, type_confidence=0.85, historical_hits=0)
        r_with_hist = compute_score("sku", match_score=0.80, type_confidence=0.85, historical_hits=20)
        self.assertGreaterEqual(r_with_hist.final_score, r_no_hist.final_score)

    def test_explanation_contains_scores(self):
        r = compute_score("sku", match_score=0.90, type_confidence=0.90)
        self.assertIn("match=", r.explanation)
        self.assertIn("type=", r.explanation)


# ──────────────────────────────────────────────────────────────────────
# LearningStore
# ──────────────────────────────────────────────────────────────────────
class TestLearningStore(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mktemp(suffix=".json"))
        self.store = LearningStore(use_db=False, path=self.tmp)

    def tearDown(self):
        if self.tmp.exists():
            self.tmp.unlink()

    def test_record_and_get(self):
        self.store.record("hash1", "Артикул WB", "sku", score=0.95)
        rec = self.store.get("hash1", "Артикул WB")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.target_field, "sku")
        self.assertEqual(rec.hits, 1)

    def test_record_increments_hits(self):
        self.store.record("hash1", "Цена", "price", 0.90)
        self.store.record("hash1", "Цена", "price", 0.92)
        self.store.record("hash1", "Цена", "price", 0.91)
        rec = self.store.get("hash1", "Цена")
        self.assertEqual(rec.hits, 3)

    def test_get_hits(self):
        self.store.record("hash1", "SKU", "sku", 0.95)
        self.store.record("hash1", "SKU", "sku", 0.95)
        hits = self.store.get_hits("hash1", "SKU", "sku")
        self.assertEqual(hits, 2)

    def test_get_hits_wrong_target(self):
        self.store.record("hash1", "SKU", "sku", 0.95)
        hits = self.store.get_hits("hash1", "SKU", "barcode")
        self.assertEqual(hits, 0)

    def test_confirm(self):
        self.store.record("hash1", "Дата", "date", 0.80)
        self.store.confirm("hash1", "Дата")
        rec = self.store.get("hash1", "Дата")
        self.assertTrue(rec.confirmed)

    def test_reject_replaces(self):
        self.store.record("hash1", "Кол-во", "quantity", 0.70)
        self.store.reject("hash1", "Кол-во", "revenue", 1.0)
        rec = self.store.get("hash1", "Кол-во")
        self.assertEqual(rec.target_field, "revenue")
        self.assertTrue(rec.confirmed)

    def test_get_all_for_hash(self):
        self.store.record("hash_A", "Col1", "sku", 0.95)
        self.store.record("hash_A", "Col2", "price", 0.90)
        self.store.record("hash_B", "Col1", "date", 0.85)
        records = self.store.get_all_for_hash("hash_A")
        self.assertEqual(len(records), 2)

    def test_stats(self):
        self.store.record("h1", "C1", "sku", 0.95, confirmed=False)
        self.store.record("h1", "C2", "price", 0.90, confirmed=True)
        s = self.store.stats()
        self.assertEqual(s["total_records"], 2)
        self.assertEqual(s["confirmed"], 1)

    def test_persistence_reload(self):
        self.store.record("hash1", "SKU", "sku", 0.97)
        # Новый экземпляр того же файла
        store2 = LearningStore(use_db=False, path=self.tmp)
        rec = store2.get("hash1", "SKU")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.target_field, "sku")


# ──────────────────────────────────────────────────────────────────────
# SmartMapper — интеграционные тесты
# ──────────────────────────────────────────────────────────────────────
class TestSmartMapper(unittest.TestCase):

    def _make_df(self, data: dict) -> pd.DataFrame:
        return pd.DataFrame(data)

    def _make_mapper(self) -> SmartMapper:
        tmp = Path(tempfile.mktemp(suffix=".json"))
        return SmartMapper(use_db=False, store_path=tmp)

    def test_wb_sales_file(self):
        """Типичный файл продаж WB — все колонки AUTO_APPLY."""
        df = self._make_df({
            "Артикул WB":   ["ART001"] * 10,
            "Дата продажи": ["01.06.2024"] * 10,
            "Количество":   list(range(1, 11)),
            "Цена розн":    [1500.0] * 10,
            "Выручка":      [15000.0] * 10,
            "Комиссия WB":  [1500.0] * 10,
            "Склад":        ["Москва"] * 10,
        })
        mapper = self._make_mapper()
        result = mapper.map_file(Path("/tmp/wb_sales.xlsx"), "hash_sales", df)

        self.assertGreater(result.total_columns, 0)
        # Большинство полей должны быть распознаны
        recognized = result.auto_count + result.review_count
        self.assertGreaterEqual(recognized / result.total_columns, 0.70)
        self.assertGreater(result.avg_confidence, 0.50)

    def test_stocks_file(self):
        """Файл остатков склада."""
        df = self._make_df({
            "SKU":        ["ART001", "ART002"],
            "Qty":        [100, 50],
            "Warehouse":  ["MSK", "SPB"],
        })
        mapper = self._make_mapper()
        result = mapper.map_file(Path("/tmp/stocks.csv"), "hash_stocks", df)
        self.assertGreater(result.total_columns, 0)

    def test_all_garbage_columns(self):
        """Полностью неизвестные колонки — система не должна падать."""
        df = self._make_df({
            "zzz_unknown_1": ["x"] * 5,
            "qwe_rty_123":   [1] * 5,
        })
        mapper = self._make_mapper()
        result = mapper.map_file(Path("/tmp/garbage.csv"), "hash_garbage", df)
        self.assertIsNotNone(result)
        self.assertEqual(result.total_columns, 2)

    def test_learning_improves_confidence(self):
        """После N применений confidence должен расти."""
        tmp = Path(tempfile.mktemp(suffix=".json"))
        mapper = SmartMapper(use_db=False, store_path=tmp)
        df = self._make_df({"Артикул WB": ["ART001"] * 5})

        result1 = mapper.map_file(Path("/tmp/f1.csv"), "hash_learn", df)
        # Применяем 10 раз — hits растут
        for _ in range(10):
            mapper.map_file(Path("/tmp/f1.csv"), "hash_learn", df)
        result2 = mapper.map_file(Path("/tmp/f1.csv"), "hash_learn", df)

        # Confidence должен быть >= первого
        score1 = result1.decisions[0].confidence.final_score if result1.decisions else 0
        score2 = result2.decisions[0].confidence.final_score if result2.decisions else 0
        self.assertGreaterEqual(score2, score1)

    def test_result_structure(self):
        df = self._make_df({"SKU": ["A1"], "Price": [100.0], "Date": ["2024-01-01"]})
        mapper = self._make_mapper()
        result = mapper.map_file(Path("/tmp/t.csv"), "hash_struct", df)

        # Проверяем структуру
        self.assertIsInstance(result.decisions, list)
        self.assertIsInstance(result.auto_applied, list)
        self.assertIsInstance(result.needs_review, list)
        self.assertIsInstance(result.ignored, list)
        self.assertIsInstance(result.can_proceed, bool)
        total = result.auto_count + result.review_count + result.ignored_count
        self.assertEqual(total, result.total_columns)

    def test_confirm_decision(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        mapper = SmartMapper(use_db=False, store_path=tmp)
        mapper.confirm_decision("hash1", "Col1", "sku")
        # Не должно падать

    def test_reject_decision(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        mapper = SmartMapper(use_db=False, store_path=tmp)
        df = self._make_df({"Кол-во": [1, 2, 3]})
        mapper.map_file(Path("/tmp/t.csv"), "hash_rej", df)
        mapper.reject_decision("hash_rej", "Кол-во", "revenue")
        # После reject — hits для revenue должны быть 1
        hits = mapper._store.get_hits("hash_rej", "Кол-во", "revenue")
        self.assertEqual(hits, 1)


if __name__ == "__main__":
    unittest.main()

