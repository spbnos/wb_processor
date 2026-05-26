"""
python -m pytest mapping/tests/test_interactive_mapper.py -v
"""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mapping.interactive_mapper import InteractiveMapper, FieldMapping, MappingConfig
from mapping.constants import TARGET_FIELDS, DATA_TYPES


class TestSuggestTarget(unittest.TestCase):
    """Тестируем автоопределение поля по имени колонки."""

    def _suggest(self, col: str):
        return InteractiveMapper._suggest_target(col)

    def test_sku_variants(self):
        for col in ["Артикул WB", "SKU", "nmid", "Артикул поставщика"]:
            result = self._suggest(col)
            self.assertIn(result, ("sku",), msg=f"Failed for col='{col}'")

    def test_barcode(self):
        self.assertEqual(self._suggest("Баркод"), "barcode")
        self.assertEqual(self._suggest("Barcode"), "barcode")

    def test_date(self):
        self.assertEqual(self._suggest("Дата продажи"), "date")
        self.assertEqual(self._suggest("Период"), "date")

    def test_quantity(self):
        self.assertEqual(self._suggest("Количество"), "quantity")
        self.assertEqual(self._suggest("Qty"), "quantity")
        self.assertEqual(self._suggest("Остаток"), "quantity")

    def test_price(self):
        self.assertEqual(self._suggest("Цена розничная"), "price")
        self.assertEqual(self._suggest("Price"), "price")

    def test_revenue(self):
        self.assertEqual(self._suggest("Выручка"), "revenue")

    def test_commission(self):
        self.assertEqual(self._suggest("Комиссия WB"), "commission")

    def test_warehouse(self):
        self.assertEqual(self._suggest("Склад"), "warehouse")

    def test_unknown_returns_none(self):
        self.assertIsNone(self._suggest("Неизвестное поле XYZ"))
        self.assertIsNone(self._suggest("Column_99"))

    def test_case_insensitive(self):
        self.assertEqual(self._suggest("БРЕНД"), "brand")
        self.assertEqual(self._suggest("brand"), "brand")


class TestDefaultTypeFor(unittest.TestCase):
    def test_str_fields(self):
        for f in ["sku", "barcode", "name", "warehouse"]:
            self.assertEqual(InteractiveMapper._default_type_for(f), "str")

    def test_int_fields(self):
        for f in ["quantity", "reserved", "impressions", "clicks"]:
            self.assertEqual(InteractiveMapper._default_type_for(f), "int")

    def test_float_fields(self):
        for f in ["price", "revenue", "commission", "logistics", "ad_spend"]:
            self.assertEqual(InteractiveMapper._default_type_for(f), "float")

    def test_date_field(self):
        self.assertEqual(InteractiveMapper._default_type_for("date"), "date")

    def test_unknown_defaults_to_str(self):
        self.assertEqual(InteractiveMapper._default_type_for("custom_xyz"), "str")


class TestFieldMapping(unittest.TestCase):
    def test_field_mapping_creation(self):
        fm = FieldMapping(
            source_column="Артикул WB",
            target_field="sku",
            data_type="str",
            is_required=True,
        )
        self.assertEqual(fm.source_column, "Артикул WB")
        self.assertEqual(fm.target_field, "sku")
        self.assertTrue(fm.is_required)
        self.assertIsNone(fm.date_format)

    def test_field_mapping_with_date(self):
        fm = FieldMapping(
            source_column="Дата",
            target_field="date",
            data_type="date",
            date_format="%d.%m.%Y",
        )
        self.assertEqual(fm.date_format, "%d.%m.%Y")


class TestMappingConfig(unittest.TestCase):
    def test_mapping_config_creation(self):
        config = MappingConfig(
            name="WB Продажи 2024",
            struct_hash="abc123",
            category="wb_report",
            subcategory="sales",
            purpose="profit",
            raw_columns=["Артикул WB", "Дата", "Количество", "Цена"],
            column_count=4,
            fields=[
                FieldMapping("Артикул WB", "sku",      "str",   is_required=True),
                FieldMapping("Дата",        "date",     "date",  date_format="%d.%m.%Y"),
                FieldMapping("Количество",  "quantity", "int"),
                FieldMapping("Цена",        "price",    "float"),
            ],
        )
        self.assertEqual(config.name, "WB Продажи 2024")
        self.assertEqual(len(config.fields), 4)
        self.assertEqual(config.fields[0].target_field, "sku")
        self.assertEqual(config.fields[1].date_format, "%d.%m.%Y")

    def test_ignore_field(self):
        fm = FieldMapping(source_column="Ненужная колонка", target_field="ignore", data_type="str")
        self.assertEqual(fm.target_field, "ignore")


class TestConstants(unittest.TestCase):
    def test_all_target_fields_have_labels(self):
        for key, label in TARGET_FIELDS.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(label, str)
            self.assertTrue(len(label) > 0)

    def test_all_data_types_valid(self):
        for key, (val, label) in DATA_TYPES.items():
            self.assertIn(val, ("str", "int", "float", "date", "bool"))


if __name__ == "__main__":
    unittest.main()
