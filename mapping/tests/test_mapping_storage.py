"""
python -m pytest mapping/tests/test_mapping_storage.py -v
Работает без PostgreSQL — JSON-only режим.
"""
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mapping.mapping_storage import MappingStorage
from mapping.mapping_repository import MappingRepository
from mapping.interactive_mapper import MappingConfig, FieldMapping


# ─── Фабрика тестового конфига ───────────────────────────
def make_config(
    name="WB Продажи",
    struct_hash="testhash001",
    category="wb_report",
    subcategory="sales",
    purpose="profit",
) -> MappingConfig:
    return MappingConfig(
        name=name,
        struct_hash=struct_hash,
        category=category,
        subcategory=subcategory,
        purpose=purpose,
        raw_columns=["Артикул WB", "Дата", "Количество", "Цена"],
        column_count=4,
        fields=[
            FieldMapping("Артикул WB", "sku",      "str",   is_required=True),
            FieldMapping("Дата",        "date",     "date",  date_format="%d.%m.%Y"),
            FieldMapping("Количество",  "quantity", "int"),
            FieldMapping("Цена",        "price",    "float"),
        ],
        notes="тест",
    )


class TestMappingStorageSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.path = Path(self.tmp.name)
        self.storage = MappingStorage(use_db=False, json_path=self.path)

    def test_save_new(self):
        config = make_config()
        m = self.storage.save(config)
        self.assertIsNotNone(m)
        self.assertEqual(m.name, "WB Продажи")
        self.assertEqual(m.id, 1)

    def test_save_duplicate_returns_existing(self):
        config = make_config()
        m1 = self.storage.save(config)
        m2 = self.storage.save(config)
        self.assertEqual(m1.id, m2.id)

        # Только одна запись в JSON
        with open(self.path) as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_save_multiple(self):
        self.storage.save(make_config(name="A", struct_hash="h1"))
        self.storage.save(make_config(name="B", struct_hash="h2"))
        self.storage.save(make_config(name="C", struct_hash="h3"))
        all_m = self.storage.get_all()
        self.assertEqual(len(all_m), 3)

    def test_fields_saved(self):
        config = make_config()
        m = self.storage.save(config)
        self.assertEqual(len(m.fields), 4)
        targets = {f.target_field for f in m.fields}
        self.assertIn("sku", targets)
        self.assertIn("date", targets)

    def test_date_format_preserved(self):
        config = make_config()
        m = self.storage.save(config)
        date_field = next(f for f in m.fields if f.target_field == "date")
        self.assertEqual(date_field.date_format, "%d.%m.%Y")


class TestMappingStorageFind(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.path = Path(self.tmp.name)
        self.storage = MappingStorage(use_db=False, json_path=self.path)
        self.storage.save(make_config(name="WB Sales", struct_hash="hash_sales"))
        self.storage.save(make_config(name="WB Finance", struct_hash="hash_fin", subcategory="finance"))

    def test_find_by_struct_hash_found(self):
        m = self.storage.find_by_struct_hash("hash_sales")
        self.assertIsNotNone(m)
        self.assertEqual(m.name, "WB Sales")

    def test_find_by_struct_hash_not_found(self):
        m = self.storage.find_by_struct_hash("nonexistent_hash")
        self.assertIsNone(m)

    def test_get_all_returns_all(self):
        result = self.storage.get_all()
        self.assertEqual(len(result), 2)

    def test_get_by_id(self):
        m = self.storage.get_by_id(1)
        self.assertIsNotNone(m)
        self.assertEqual(m.id, 1)

    def test_get_by_id_missing(self):
        m = self.storage.get_by_id(999)
        self.assertIsNone(m)

    def test_get_fields(self):
        fields = self.storage.get_fields(1)
        self.assertEqual(len(fields), 4)


class TestMappingStorageUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.path = Path(self.tmp.name)
        self.storage = MappingStorage(use_db=False, json_path=self.path)
        self.storage.save(make_config())

    def test_update_name(self):
        m = self.storage.update(1, name="New Name")
        self.assertEqual(m.name, "New Name")

    def test_update_notes(self):
        m = self.storage.update(1, notes="Updated notes")
        self.assertEqual(m.notes, "Updated notes")

    def test_update_fields(self):
        new_fields = [
            FieldMapping("Артикул WB", "sku", "str"),
            FieldMapping("Новая колонка", "custom", "float"),
        ]
        m = self.storage.update(1, fields=new_fields)
        self.assertEqual(len(m.fields), 2)

    def test_update_nonexistent(self):
        m = self.storage.update(999, name="Ghost")
        self.assertIsNone(m)


class TestMappingStorageDelete(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.path = Path(self.tmp.name)
        self.storage = MappingStorage(use_db=False, json_path=self.path)
        self.storage.save(make_config(name="To Delete", struct_hash="del_hash"))

    def test_soft_delete(self):
        result = self.storage.delete(1)
        self.assertTrue(result)
        # Мягкое удаление — не видно в active_only=True
        active = self.storage.get_all(active_only=True)
        self.assertEqual(len(active), 0)
        # Но видно в active_only=False
        all_m = self.storage.get_all(active_only=False)
        self.assertEqual(len(all_m), 1)
        self.assertFalse(all_m[0].is_active)

    def test_hard_delete(self):
        result = self.storage.delete(1, hard=True)
        self.assertTrue(result)
        all_m = self.storage.get_all(active_only=False)
        self.assertEqual(len(all_m), 0)

    def test_delete_nonexistent(self):
        result = self.storage.delete(999)
        self.assertFalse(result)

    def test_soft_deleted_not_found_by_hash(self):
        self.storage.delete(1)
        m = self.storage.find_by_struct_hash("del_hash")
        self.assertIsNone(m)


class TestMappingStorageExportImport(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.json_path = Path(self.dir) / "mappings.json"
        self.storage = MappingStorage(use_db=False, json_path=self.json_path)
        self.storage.save(make_config(name="A", struct_hash="h1"))
        self.storage.save(make_config(name="B", struct_hash="h2"))

    def test_export(self):
        out = self.storage.export_json()
        self.assertTrue(out.exists())
        with open(out) as f:
            data = json.load(f)
        self.assertEqual(len(data), 2)

    def test_import_new(self):
        # Экспортируем из первого хранилища
        out_path = Path(self.dir) / "export.json"
        self.storage.export_json(out_path)

        # Импортируем в новое пустое хранилище
        new_path = Path(self.dir) / "new_mappings.json"
        new_storage = MappingStorage(use_db=False, json_path=new_path)
        count = new_storage.import_json(out_path)
        self.assertEqual(count, 2)
        self.assertEqual(len(new_storage.get_all()), 2)

    def test_import_skips_duplicates(self):
        out_path = Path(self.dir) / "export2.json"
        self.storage.export_json(out_path)
        # Импортируем в то же хранилище — должно пропустить всё
        count = self.storage.import_json(out_path)
        self.assertEqual(count, 0)


class TestMappingRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.path = Path(self.tmp.name)
        self.storage = MappingStorage(use_db=False, json_path=self.path)
        self.repo = MappingRepository(self.storage)
        self.storage.save(make_config(name="WB Продажи", struct_hash="s1", category="wb_report"))
        self.storage.save(make_config(name="WB Реклама", struct_hash="s2", category="ad"))
        self.storage.save(make_config(name="Остатки склада", struct_hash="s3", category="external"))

    def test_find_by_name_exact(self):
        m = self.repo.find_by_name("WB Продажи")
        self.assertIsNotNone(m)

    def test_find_by_name_case_insensitive(self):
        m = self.repo.find_by_name("wb продажи")
        self.assertIsNotNone(m)

    def test_find_by_name_not_found(self):
        m = self.repo.find_by_name("Несуществующий маппинг")
        self.assertIsNone(m)

    def test_search_by_name_partial(self):
        results = self.repo.search("WB")
        self.assertEqual(len(results), 2)

    def test_search_by_category(self):
        results = self.repo.search("external")
        self.assertEqual(len(results), 1)

    def test_list_by_category(self):
        results = self.repo.list_by_category("wb_report")
        self.assertEqual(len(results), 1)

    def test_stats(self):
        s = self.repo.stats()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["active"], 3)
        self.assertIn("wb_report", s["by_category"])

    def test_summary_list(self):
        lst = self.repo.summary_list()
        self.assertEqual(len(lst), 3)
        keys = set(lst[0].keys())
        self.assertIn("id", keys)
        self.assertIn("name", keys)
        self.assertIn("struct_hash", keys)


if __name__ == "__main__":
    unittest.main()
