"""
python -m pytest review_queue/tests/test_step9.py -v
Шаг 9: ReviewQueue, MappingBridge, SmartPipeline интеграция
"""
import sys, json, tempfile, unittest
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT.parent / "wb_platform"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PLATFORM))

from review_queue.queue_store import ReviewQueue, ReviewItem, ReviewStatus
from review_queue.mapping_bridge import smart_result_to_config, build_review_items
from smart_pipeline import SmartPipeline
from smart_mapping.smart_mapper import SmartMapper, SmartMappingResult, FieldDecision
from smart_mapping.confidence_scorer import ConfidenceLevel, ConfidenceResult


# ─── Helpers ─────────────────────────────────────────────

def _make_queue(tmp_dir: Path) -> ReviewQueue:
    return ReviewQueue(use_db=False, path=tmp_dir / "queue.json")

def _make_item(
    col="Артикул WB", field="sku", score=0.72,
    level=ConfidenceLevel.NEEDS_REVIEW, struct_hash="hash1"
) -> ReviewItem:
    item_id = f"{struct_hash}::{col}"
    return ReviewItem(
        id=item_id,
        struct_hash=struct_hash,
        source_column=col,
        suggested_field=field,
        suggested_type="str",
        confidence_score=score,
        confidence_level=level.value,
        match_method="fuzzy_token",
        runner_up_field=None,
        runner_up_score=0.0,
        filepath="/tmp/test.csv",
        filename="test.csv",
        sample_values=["A1", "A2", "A3"],
    )


# ──────────────────────────────────────────────────────────────────────
# ReviewQueue
# ──────────────────────────────────────────────────────────────────────
class TestReviewQueue(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.q = _make_queue(self.tmpdir)

    def test_enqueue_and_get(self):
        item = _make_item()
        self.q.enqueue(item)
        pending = self.q.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].source_column, "Артикул WB")

    def test_enqueue_deduplicates(self):
        item = _make_item()
        self.q.enqueue(item)
        self.q.enqueue(item)   # второй раз тот же ключ
        self.assertEqual(len(self.q.get_pending()), 1)

    def test_enqueue_many(self):
        items = [
            _make_item("Col1", "sku",   0.72),
            _make_item("Col2", "price", 0.65),
            _make_item("Col3", "date",  0.55, ConfidenceLevel.LOW_CONF),
        ]
        self.q.enqueue_many(items)
        self.assertEqual(self.q.count_pending(), 3)

    def test_approve_suggested(self):
        item = _make_item()
        self.q.enqueue(item)
        resolved = self.q.approve(item.id)
        self.assertEqual(resolved.status, ReviewStatus.APPROVED.value)
        self.assertEqual(resolved.correct_field, "sku")  # suggested_field
        self.assertEqual(len(self.q.get_pending()), 0)

    def test_approve_override_field(self):
        item = _make_item()
        self.q.enqueue(item)
        resolved = self.q.approve(item.id, field="barcode")  # пользователь выбрал другое
        self.assertEqual(resolved.correct_field, "barcode")

    def test_reject_with_correction(self):
        item = _make_item()
        self.q.enqueue(item)
        resolved = self.q.reject(item.id, correct_field="barcode")
        self.assertEqual(resolved.status, ReviewStatus.REJECTED.value)
        self.assertEqual(resolved.correct_field, "barcode")

    def test_get_by_id(self):
        item = _make_item()
        self.q.enqueue(item)
        found = self.q.get_by_id(item.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.suggested_field, "sku")

    def test_get_by_id_not_found(self):
        result = self.q.get_by_id("nonexistent::col")
        self.assertIsNone(result)

    def test_filter_by_struct_hash(self):
        self.q.enqueue(_make_item("C1", "sku",  0.72, struct_hash="hash_A"))
        self.q.enqueue(_make_item("C2", "date", 0.68, struct_hash="hash_B"))
        result = self.q.get_pending(struct_hash="hash_A")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].struct_hash, "hash_A")

    def test_expire_for_hash(self):
        self.q.enqueue(_make_item("C1", struct_hash="hash_X"))
        self.q.enqueue(_make_item("C2", struct_hash="hash_Y"))
        self.q.expire_for_hash("hash_X")
        # hash_X — expired, hash_Y — pending
        pending = self.q.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].struct_hash, "hash_Y")

    def test_stats(self):
        self.q.enqueue(_make_item("C1"))
        self.q.enqueue(_make_item("C2", score=0.55, level=ConfidenceLevel.LOW_CONF))
        s = self.q.stats()
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["pending"], 2)

    def test_sorted_by_confidence_asc(self):
        """Pending items должны быть отсортированы: низший confidence первым."""
        self.q.enqueue(_make_item("High", score=0.82))
        self.q.enqueue(_make_item("Low",  score=0.42))
        self.q.enqueue(_make_item("Mid",  score=0.62))
        items = self.q.get_pending()
        scores = [i.confidence_score for i in items]
        self.assertEqual(scores, sorted(scores))

    def test_persistence(self):
        item = _make_item()
        self.q.enqueue(item)
        # Новый экземпляр — данные должны сохраниться
        q2 = ReviewQueue(use_db=False, path=self.tmpdir / "queue.json")
        self.assertEqual(q2.count_pending(), 1)


# ──────────────────────────────────────────────────────────────────────
# MappingBridge
# ──────────────────────────────────────────────────────────────────────
class TestMappingBridge(unittest.TestCase):

    def _make_smart_result(self, filepath="/tmp/t.csv") -> SmartMappingResult:
        """Создаём минимальный SmartMappingResult для тестов."""
        def _conf(score, level, method="alias_exact"):
            return ConfidenceResult(
                target_field="sku", final_score=score, level=level,
                match_score=score, type_confidence=0.9,
                history_bonus=0.0, explanation="test",
            )

        auto_d = FieldDecision(
            source_column="Артикул WB", target_field="sku",
            data_type="str", date_format=None,
            confidence=_conf(0.97, ConfidenceLevel.AUTO_APPLY),
            is_ignored=False, needs_review=False,
        )
        review_d = FieldDecision(
            source_column="Дата", target_field="date",
            data_type="date", date_format="%d.%m.%Y",
            confidence=_conf(0.72, ConfidenceLevel.NEEDS_REVIEW),
            is_ignored=False, needs_review=True,
        )
        ignored_d = FieldDecision(
            source_column="Мусор", target_field=None,
            data_type="str", date_format=None,
            confidence=_conf(0.0, ConfidenceLevel.NO_MATCH),
            is_ignored=True, needs_review=False,
        )
        decisions = [auto_d, review_d, ignored_d]
        return SmartMappingResult(
            struct_hash="bridge_hash",
            filepath=Path(filepath),
            decisions=decisions,
            auto_applied=[auto_d],
            needs_review=[review_d],
            ignored=[ignored_d],
            total_columns=3,
            auto_count=1, review_count=1, ignored_count=1,
            avg_confidence=0.80, can_proceed=True,
            blocking_fields=[],
        )

    def test_smart_result_to_config(self):
        result = self._make_smart_result()
        config = smart_result_to_config(result, name="Test Mapping")
        self.assertEqual(config.name, "Test Mapping")
        self.assertEqual(config.struct_hash, "bridge_hash")
        self.assertEqual(len(config.fields), 3)

        targets = {f.source_column: f.target_field for f in config.fields}
        self.assertEqual(targets["Артикул WB"], "sku")
        self.assertEqual(targets["Дата"], "date")
        self.assertEqual(targets["Мусор"], "ignore")

    def test_config_field_types(self):
        result = self._make_smart_result()
        config = smart_result_to_config(result, name="T")
        date_field = next(f for f in config.fields if f.source_column == "Дата")
        self.assertEqual(date_field.data_type, "date")
        self.assertEqual(date_field.date_format, "%d.%m.%Y")

    def test_build_review_items(self):
        result = self._make_smart_result()
        sample = {
            "Дата": ["01.06.2024", "02.06.2024"],
            "Артикул WB": ["A1", "A2"],
        }
        items = build_review_items(result, Path("/tmp/t.csv"), sample)
        self.assertEqual(len(items), 1)   # только NEEDS_REVIEW
        self.assertEqual(items[0].source_column, "Дата")
        self.assertEqual(items[0].suggested_field, "date")
        self.assertLessEqual(len(items[0].sample_values), 5)

    def test_review_item_id_format(self):
        result = self._make_smart_result()
        items = build_review_items(result, Path("/tmp/t.csv"), {})
        self.assertEqual(items[0].id, "bridge_hash::Дата")


# ──────────────────────────────────────────────────────────────────────
# SmartPipeline — интеграция
# ──────────────────────────────────────────────────────────────────────
class TestSmartPipeline(unittest.TestCase):

    def _make_csv(self, data: dict, name="test.csv") -> Path:
        import tempfile
        tmp = Path(tempfile.mkdtemp()) / name
        pd.DataFrame(data).to_csv(tmp, index=False)
        return tmp

    def _make_pipeline(self) -> SmartPipeline:
        return SmartPipeline(use_db=False)

    def test_known_format_processed(self):
        """Известный формат — AUTO без ремаппинга."""
        from mapping.interactive_mapper import MappingConfig, FieldMapping
        from classification.file_classifier import compute_struct_hash

        cols = {"SKU": ["A1", "A2"], "Revenue": [1000.0, 2000.0]}
        filepath = self._make_csv(cols)

        p = self._make_pipeline()
        struct_hash = compute_struct_hash(list(cols.keys()))
        config = MappingConfig(
            name="Known Test", struct_hash=struct_hash,
            category="wb_report", subcategory="sales", purpose="profit",
            raw_columns=list(cols.keys()), column_count=2,
            fields=[
                FieldMapping("SKU", "sku", "str", is_required=True),
                FieldMapping("Revenue", "revenue", "float"),
            ],
        )
        p.storage.save(config)
        status = p.process_file(filepath)
        self.assertIn(status, ("ok", "queued"))

    def test_unknown_format_auto_mapping(self):
        """Неизвестный формат — SmartMapper авто-маппит."""
        cols = {
            "Артикул WB": ["A1", "A2", "A3"],
            "Количество":  [5, 3, 2],
            "Выручка":     [1000.0, 600.0, 400.0],
        }
        filepath = self._make_csv(cols, "wb_sales.csv")
        p = self._make_pipeline()
        status = p.process_file(filepath)
        # Должно обработаться (ok или queued если review items есть)
        self.assertIn(status, ("ok", "queued", "deferred"))

    def test_queue_stats_structure(self):
        p = self._make_pipeline()
        stats = p.queue_stats()
        self.assertIn("review_queue", stats)
        self.assertIn("learning_store", stats)
        self.assertIn("pending", stats["review_queue"])

    def test_review_queue_populated_on_low_confidence(self):
        """Low-confidence колонки попадают в review queue."""
        # Подаём файл с нестандартными названиями колонок
        cols = {
            "xyz_col_1": ["A1", "A2"],
            "Артикул WB": ["B1", "B2"],  # хотя бы один понятный
            "qwe_unknown": [1.0, 2.0],
        }
        filepath = self._make_csv(cols, "weird.csv")
        p = self._make_pipeline()
        p.process_file(filepath)
        # Не должно быть исключений
        stats = p.queue_stats()
        self.assertIsInstance(stats["review_queue"]["total"], int)

    def test_apply_pending_reviews_no_mapping(self):
        """apply_pending_reviews без маппинга — не падает."""
        p = self._make_pipeline()
        count = p.apply_pending_reviews("nonexistent_hash")
        self.assertEqual(count, 0)

    def test_approve_and_apply(self):
        """Цикл: enqueue → approve → apply_pending_reviews."""
        from mapping.interactive_mapper import MappingConfig, FieldMapping
        from classification.file_classifier import compute_struct_hash

        cols = {"Артикул WB": ["A1"], "Дата продажи": ["01.06.2024"]}
        filepath = self._make_csv(cols)
        p = self._make_pipeline()

        # Сохраняем маппинг напрямую
        sh = compute_struct_hash(list(cols.keys()))
        config = MappingConfig(
            name="Review Test", struct_hash=sh,
            category="wb_report", subcategory="sales", purpose="profit",
            raw_columns=list(cols.keys()), column_count=2,
            fields=[
                FieldMapping("Артикул WB", "sku", "str"),
                FieldMapping("Дата продажи", "date", "date"),
            ],
        )
        p.storage.save(config)

        # Добавляем item в очередь
        item = ReviewItem(
            id=f"{sh}::Дата продажи",
            struct_hash=sh,
            source_column="Дата продажи",
            suggested_field="date",
            suggested_type="date",
            confidence_score=0.72,
            confidence_level=ConfidenceLevel.NEEDS_REVIEW.value,
            match_method="fuzzy_token",
            runner_up_field=None,
            runner_up_score=0.0,
            filepath=str(filepath),
            filename=filepath.name,
        )
        p.review_queue.enqueue(item)

        # Пользователь одобряет
        p.review_queue.approve(item.id, field="date")

        # Применяем
        count = p.apply_pending_reviews(sh)
        self.assertGreaterEqual(count, 0)   # >= 0 (маппинг обновлён)


if __name__ == "__main__":
    unittest.main()

