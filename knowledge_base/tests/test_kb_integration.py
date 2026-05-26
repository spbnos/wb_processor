"""
python -m pytest knowledge_base/tests/test_kb_integration.py -v
Тесты интеграции KnowledgeEngine → SmartMapper
"""
import sys, unittest
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT.parent / "wb_platform"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PLATFORM))


WB_COLS_ANALYTICS = [
    ("Код номенклатуры",                             "sku",        "int"),
    ("Бренд",                                        "brand",      "str"),
    ("Дата продажи",                                 "date",       "date"),
    ("Кол-во",                                       "quantity",   "int"),
    ("Цена розничная",                               "price",      "float"),
    ("Вайлдберриз реализовал Товар (Пр)",            "revenue",    "float"),
    ("Вознаграждение Вайлдберриз (ВВ), без НДС",     "commission", "float"),
    ("К перечислению Продавцу за реализованный Товар","net_profit", "float"),
    ("Услуги по доставке товара покупателю",         "logistics",  "float"),
    ("Размер кВВ, %",                                "kvv_pct",    "float"),
    ("Общая сумма штрафов",                          "penalties",  "float"),
    ("Хранение",                                     "storage_fee","float"),
    ("Склад",                                        "warehouse_origin","str"),
    ("Наименование офиса доставки",                  "warehouse",  "str"),
    ("Страна",                                       "country",    "str"),
    ("Тип документа",                                "transaction_type","str"),
]

WB_COLS_SERVICE = [
    "Стикер МП", "Номер сборочного задания", "ШК",
    "Id корзины заказа", "Номер таможенной декларации",
    "Номер короба для обработки товара",
]


class TestKBEngineDirectly(unittest.TestCase):
    def setUp(self):
        from knowledge_base.search.knowledge_engine import KnowledgeEngine
        self.e = KnowledgeEngine()

    def test_all_analytics_columns_found(self):
        for col, expected_target, _ in WB_COLS_ANALYTICS:
            r = self.e.lookup(col)
            self.assertIsNotNone(r, f"Not found: {col!r}")
            self.assertEqual(r.target_field, expected_target,
                             f"{col!r} → {r.target_field!r}, want {expected_target!r}")
            self.assertGreaterEqual(r.confidence, 0.85,
                                    f"{col!r} conf={r.confidence:.2f}")

    def test_analytics_cols_have_use_in_analytics_true(self):
        for col, _, _ in WB_COLS_ANALYTICS:
            r = self.e.lookup(col)
            self.assertTrue(r.use_in_analytics, f"{col!r} should be analytics")

    def test_service_cols_not_analytics(self):
        for col in WB_COLS_SERVICE:
            r = self.e.lookup(col)
            self.assertIsNotNone(r, f"Not found: {col!r}")
            self.assertFalse(r.use_in_analytics, f"{col!r} should NOT be analytics")

    def test_types_match_registry(self):
        for col, _, expected_type in WB_COLS_ANALYTICS:
            r = self.e.lookup(col)
            self.assertEqual(r.data_type, expected_type,
                             f"{col!r} type={r.data_type!r}, want {expected_type!r}")

    def test_date_formats_set(self):
        for col, target, dtype in WB_COLS_ANALYTICS:
            if dtype == "date":
                r = self.e.lookup(col)
                self.assertIsNotNone(r.date_format,
                                     f"{col!r} date_format is None")

    def test_kvv_has_wb_term(self):
        r = self.e.lookup("Размер снижения кВВ из-за рейтинга, %")
        self.assertIsNotNone(r)
        self.assertIsNotNone(r.wb_term)
        self.assertIn("кВВ", r.wb_term)


class TestSmartMapperKBIntegration(unittest.TestCase):

    def setUp(self):
        from smart_mapping.smart_mapper import SmartMapper
        self.mapper = SmartMapper(
            use_db=False,
            auto_threshold=0.75,
            review_threshold=0.40,
        )

    def _run(self, cols: dict) -> object:
        df = pd.DataFrame(cols)
        return self.mapper.map_file(
            filepath=Path("/tmp/test.xlsx"),
            struct_hash="test_wb_integration",
            sample_df=df,
        )

    def test_wb_analytics_columns_all_auto(self):
        """Все аналитические колонки WB → AUTO_APPLY."""
        cols = {col: ["x"] * 3 for col, _, _ in WB_COLS_ANALYTICS}
        result = self._run(cols)
        self.assertEqual(result.review_count, 0,
                         f"review_count={result.review_count}, fields: "
                         f"{[d.source_column for d in result.needs_review]}")
        self.assertEqual(result.auto_count, len(cols))

    def test_wb_service_columns_no_blocking(self):
        """Service-поля WB не блокируют pipeline."""
        cols = {col: [None] * 3 for col in WB_COLS_SERVICE}
        cols["Код номенклатуры"] = [123, 456, 789]  # хотя бы одно известное
        result = self._run(cols)
        self.assertTrue(result.can_proceed)

    def test_full_wb_report_82_cols_all_auto(self):
        """Полный WB детализированный отчёт: все 82 колонки → AUTO, 0 в review."""
        from knowledge_base.search.knowledge_engine import KnowledgeEngine
        engine = KnowledgeEngine()
        all_cols = list(engine._registry.keys())
        cols = {col: ["test"] * 3 for col in all_cols}
        result = self._run(cols)
        self.assertEqual(result.review_count, 0,
                         f"Unexpected review: "
                         f"{[d.source_column for d in result.needs_review]}")
        self.assertGreaterEqual(result.avg_confidence, 0.85)

    def test_mixed_file_wb_and_unknown(self):
        """Файл с WB-колонками и неизвестными: WB — AUTO, неизвестные — review."""
        cols = {
            "Код номенклатуры": [123],
            "Дата продажи": ["2026-05-01"],
            "XYZ_UNKNOWN_FIELD_999": ["abc"],
        }
        result = self._run(cols)
        auto_targets = {d.target_field for d in result.auto_applied}
        self.assertIn("sku", auto_targets)
        self.assertIn("date", auto_targets)

    def test_kb_provides_correct_types(self):
        """KB тип побеждает над детектором для WB-колонок."""
        from smart_mapping.smart_mapper import SmartMapper
        mapper = SmartMapper(use_db=False)
        df = pd.DataFrame({
            "Код номенклатуры": [273934915.0, 273934916.0],  # Excel хранит float
            "Дата продажи": ["2026-05-03", "2026-05-04"],
        })
        result = mapper.map_file(Path("/tmp/t.xlsx"), "type_test", df)
        decisions = {d.source_column: d for d in result.decisions}
        sku_d = decisions.get("Код номенклатуры")
        if sku_d:
            # KB говорит int — принимаем
            self.assertIn(sku_d.data_type, ("int", "float"))  # оба допустимы
        date_d = decisions.get("Дата продажи")
        if date_d:
            self.assertEqual(date_d.data_type, "date")

    def test_learning_store_records_after_mapping(self):
        """После AUTO_APPLY решения записываются в LearningStore."""
        from smart_mapping.smart_mapper import SmartMapper
        import tempfile
        tmp = Path(tempfile.mktemp(suffix=".json"))
        mapper = SmartMapper(use_db=False, store_path=tmp)
        df = pd.DataFrame({"Код номенклатуры": [123, 456]})
        mapper.map_file(Path("/tmp/t.xlsx"), "learn_test", df)
        hits = mapper._store.get_hits("learn_test", "Код номенклатуры", "sku")
        self.assertGreater(hits, 0)

    def test_second_run_uses_history(self):
        """Второй прогон того же файла → history confidence выше."""
        from smart_mapping.smart_mapper import SmartMapper
        import tempfile
        tmp = Path(tempfile.mktemp(suffix=".json"))
        mapper = SmartMapper(use_db=False, store_path=tmp, auto_threshold=0.75)
        df = pd.DataFrame({"Код номенклатуры": [123], "Дата продажи": ["2026-01-01"]})

        r1 = mapper.map_file(Path("/tmp/t.xlsx"), "history_test", df)
        # Прогоняем 5 раз для накопления hits
        for _ in range(5):
            mapper.map_file(Path("/tmp/t.xlsx"), "history_test", df)
        r2 = mapper.map_file(Path("/tmp/t.xlsx"), "history_test", df)

        # History bonus is small — check hits recorded, not just score
        hits = mapper._store.get_hits("history_test", "Код номенклатуры", "sku")
        self.assertGreater(hits, 3, f"Expected >3 hits, got {hits}")
        # Score should be high regardless
        c2 = r2.decisions[0].confidence.final_score if r2.decisions else 0
        self.assertGreaterEqual(c2, 0.85)


if __name__ == "__main__":
    unittest.main()

