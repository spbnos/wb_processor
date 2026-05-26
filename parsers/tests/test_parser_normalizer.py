"""
python -m pytest parsers/tests/test_parser_normalizer.py -v
Без БД — создаём временные CSV/Excel файлы.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mapping.mapping_storage import MappingObj, MappingFieldObj
from parsers.parser_engine import ParserEngine, _read_raw
from normalizers.normalizer import Normalizer


# ─── Фабрики ─────────────────────────────────────────────

def make_mapping(fields_def: list[tuple]) -> MappingObj:
    """fields_def: [(source, target, dtype, required, date_fmt?), ...]"""
    fields = []
    for item in fields_def:
        src, tgt, dtype = item[0], item[1], item[2]
        req = item[3] if len(item) > 3 else False
        dfmt = item[4] if len(item) > 4 else None
        fields.append(MappingFieldObj(
            source_column=src, target_field=tgt, data_type=dtype,
            is_required=req, date_format=dfmt, mapping_id=1,
        ))
    m = MappingObj(
        id=1, name="Test", struct_hash="testhash", category="wb_report",
        subcategory="sales", purpose="profit", column_count=len(fields),
        raw_columns=[f.source_column for f in fields],
        notes=None, is_active=True, created_at=None, updated_at=None,
        fields=fields,
    )
    return m


def make_csv(data: dict, sep=",") -> Path:
    df = pd.DataFrame(data)
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8")
    df.to_csv(tmp.name, index=False, sep=sep)
    return Path(tmp.name)


def make_excel(data: dict) -> Path:
    df = pd.DataFrame(data)
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    df.to_excel(tmp.name, index=False)
    return Path(tmp.name)


# ─── ParserEngine Tests ───────────────────────────────────

class TestParserEngine(unittest.TestCase):

    def test_parse_csv_basic(self):
        path = make_csv({"Артикул WB": ["A1", "A2"], "Цена": [100, 200], "Количество": [5, 3]})
        mapping = make_mapping([
            ("Артикул WB", "sku", "str", True),
            ("Цена", "price", "float"),
            ("Количество", "quantity", "int"),
        ])
        engine = ParserEngine()
        result = engine.parse(path, mapping)
        self.assertTrue(result.ok)
        self.assertEqual(result.row_count, 2)
        self.assertIn("sku", result.df.columns)
        self.assertIn("price", result.df.columns)
        self.assertIn("quantity", result.df.columns)

    def test_parse_excel_basic(self):
        path = make_excel({"SKU": ["B1", "B2", "B3"], "Дата": ["01.01.2024"]*3, "Выручка": [1000, 2000, 3000]})
        mapping = make_mapping([
            ("SKU", "sku", "str", True),
            ("Дата", "date", "date"),
            ("Выручка", "revenue", "float"),
        ])
        engine = ParserEngine()
        result = engine.parse(path, mapping)
        self.assertTrue(result.ok)
        self.assertEqual(result.row_count, 3)

    def test_missing_required_column(self):
        path = make_csv({"Артикул WB": ["A1"], "Количество": [5]})
        mapping = make_mapping([
            ("Артикул WB", "sku", "str", True),
            ("Цена", "price", "float", True),        # обязательная, но её нет в файле
        ])
        engine = ParserEngine()
        result = engine.parse(path, mapping)
        self.assertFalse(result.ok)
        self.assertIn("Цена", result.missing_required)

    def test_missing_optional_column(self):
        path = make_csv({"Артикул WB": ["A1"], "Количество": [5]})
        mapping = make_mapping([
            ("Артикул WB", "sku", "str", True),
            ("Комиссия", "commission", "float", False),  # опциональная
        ])
        engine = ParserEngine()
        result = engine.parse(path, mapping)
        self.assertTrue(result.ok)
        self.assertIn("Комиссия", result.missing_optional)

    def test_ignore_columns_excluded(self):
        path = make_csv({"Артикул WB": ["A1"], "Мусор": ["x"], "Цена": [100]})
        mapping = make_mapping([
            ("Артикул WB", "sku", "str"),
            ("Мусор", "ignore", "str"),
            ("Цена", "price", "float"),
        ])
        engine = ParserEngine()
        result = engine.parse(path, mapping)
        self.assertNotIn("ignore", result.df.columns)
        self.assertIn("sku", result.df.columns)

    def test_extra_columns_detected(self):
        path = make_csv({"Артикул WB": ["A1"], "Неизвестная": ["x"], "Цена": [100]})
        mapping = make_mapping([
            ("Артикул WB", "sku", "str"),
            ("Цена", "price", "float"),
        ])
        engine = ParserEngine()
        result = engine.parse(path, mapping)
        self.assertIn("Неизвестная", result.extra_columns)

    def test_semicolon_csv(self):
        path = make_csv({"Артикул WB": ["A1"], "Цена": [100]}, sep=";")
        mapping = make_mapping([("Артикул WB", "sku", "str"), ("Цена", "price", "float")])
        engine = ParserEngine()
        result = engine.parse(path, mapping)
        self.assertTrue(result.ok)

    def test_dirty_excel_with_empty_rows(self):
        """Excel с пустыми строками в начале."""
        df = pd.DataFrame({
            "Артикул WB": [None, None, "A1", "A2"],
            "Цена":       [None, None, 100,  200],
        })
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        df.to_excel(tmp.name, index=False)
        path = Path(tmp.name)
        mapping = make_mapping([("Артикул WB", "sku", "str"), ("Цена", "price", "float")])
        engine = ParserEngine()
        result = engine.parse(path, mapping)
        # Не должен упасть
        self.assertIsNotNone(result)


# ─── Normalizer Tests ─────────────────────────────────────

class TestNormalizerStr(unittest.TestCase):

    def _norm_col(self, values, dtype="str", date_fmt=None):
        path = make_csv({"col": values})
        mapping = make_mapping([("col", "target", dtype, False, date_fmt)])
        parse_result = ParserEngine().parse(path, mapping)
        norm_result = Normalizer().normalize(parse_result, mapping)
        return norm_result.df["target"].tolist()

    def test_str_strips_whitespace(self):
        result = self._norm_col(["  hello  ", "  world"])
        self.assertEqual(result[0], "hello")
        self.assertEqual(result[1], "world")

    def test_str_empty_becomes_none(self):
        """Пустые строки → None. Нужна вторая колонка чтобы строка не удалилась dropna(all)."""
        path = make_csv({"col": ["", "   "], "anchor": [1, 2]})
        mapping = make_mapping([("col", "target", "str"), ("anchor", "anc", "int")])
        pr = ParserEngine().parse(path, mapping)
        nr = Normalizer().normalize(pr, mapping)
        vals = nr.df["target"].tolist()
        self.assertIsNone(vals[0])
        self.assertIsNone(vals[1])


class TestNormalizerInt(unittest.TestCase):

    def _norm(self, values):
        path = make_csv({"col": values})
        mapping = make_mapping([("col", "quantity", "int")])
        pr = ParserEngine().parse(path, mapping)
        nr = Normalizer().normalize(pr, mapping)
        return nr.df["quantity"].tolist()

    def test_int_basic(self):
        result = self._norm([1, 2, 3])
        self.assertEqual(result, [1, 2, 3])

    def test_int_from_string(self):
        result = self._norm(["100", "200"])
        self.assertEqual(result[0], 100)

    def test_int_with_spaces(self):
        result = self._norm(["1 000", "2 500"])
        self.assertEqual(result[0], 1000)
        self.assertEqual(result[1], 2500)

    def test_int_invalid_becomes_none(self):
        path = make_csv({"col": ["abc", "xyz"], "anchor": [1, 2]})
        m = make_mapping([("col", "quantity", "int"), ("anchor", "anc", "int")])
        pr = ParserEngine().parse(path, m)
        nr = Normalizer().normalize(pr, m)
        result = nr.df["quantity"].tolist()
        self.assertTrue(pd.isna(result[0]))

    def test_int_none_stays_none(self):
        path = make_csv({"col": [None, 5], "anchor": [1, 2]})
        m = make_mapping([("col", "quantity", "int"), ("anchor", "anc", "int")])
        pr = ParserEngine().parse(path, m)
        nr = Normalizer().normalize(pr, m)
        result = nr.df["quantity"].tolist()
        self.assertTrue(pd.isna(result[0]))
        self.assertEqual(result[1], 5)


class TestNormalizerFloat(unittest.TestCase):

    def _norm(self, values):
        path = make_csv({"col": values})
        mapping = make_mapping([("col", "price", "float")])
        pr = ParserEngine().parse(path, mapping)
        nr = Normalizer().normalize(pr, mapping)
        return nr.df["price"].tolist()

    def test_float_basic(self):
        result = self._norm([1.5, 2.7])
        self.assertAlmostEqual(result[0], 1.5)

    def test_float_comma_separator(self):
        result = self._norm(["1,5", "2,75"])
        self.assertAlmostEqual(result[0], 1.5)
        self.assertAlmostEqual(result[1], 2.75)

    def test_float_with_spaces(self):
        result = self._norm(["1 234,56", "10 000,00"])
        self.assertAlmostEqual(result[0], 1234.56)
        self.assertAlmostEqual(result[1], 10000.0)

    def test_float_invalid_becomes_none(self):
        path = make_csv({"col": ["не число", "abc"], "anchor": [1, 2]})
        m = make_mapping([("col", "price", "float"), ("anchor", "anc", "int")])
        pr = ParserEngine().parse(path, m)
        nr = Normalizer().normalize(pr, m)
        result = nr.df["price"].tolist()
        self.assertTrue(pd.isna(result[0]))

    def test_float_ruble_sign(self):
        result = self._norm(["1500р", "2500₽"])
        self.assertAlmostEqual(result[0], 1500.0)


class TestNormalizerDate(unittest.TestCase):

    def _norm(self, values, fmt):
        path = make_csv({"col": values})
        mapping = make_mapping([("col", "date", "date", False, fmt)])
        pr = ParserEngine().parse(path, mapping)
        nr = Normalizer().normalize(pr, mapping)
        return nr.df["date"].tolist()

    def test_date_ddmmyyyy(self):
        result = self._norm(["01.06.2024", "15.12.2024"], "%d.%m.%Y")
        self.assertEqual(result[0].year, 2024)
        self.assertEqual(result[0].month, 6)
        self.assertEqual(result[0].day, 1)

    def test_date_iso(self):
        result = self._norm(["2024-06-01", "2024-12-15"], "%Y-%m-%d")
        self.assertEqual(result[0].year, 2024)

    def test_date_auto(self):
        result = self._norm(["2024-06-01"], "auto")
        self.assertIsNotNone(result[0])

    def test_date_invalid_becomes_nat(self):
        path = make_csv({"col": ["не дата", "31.02.2024"], "anchor": [1, 2]})
        m = make_mapping([("col", "date", "date", False, "%d.%m.%Y"), ("anchor", "anc", "int")])
        pr = ParserEngine().parse(path, m)
        nr = Normalizer().normalize(pr, m)
        result = nr.df["date"].tolist()
        self.assertTrue(pd.isna(result[0]))

    def test_date_fallback_format(self):
        """Если формат не совпал — пробует из fallback списка."""
        result = self._norm(["2024-06-01"], "%d.%m.%Y")  # формат не тот, но fallback есть
        self.assertIsNotNone(result[0])


class TestNormalizerBool(unittest.TestCase):

    def _norm(self, values):
        path = make_csv({"col": values})
        mapping = make_mapping([("col", "target", "bool")])
        pr = ParserEngine().parse(path, mapping)
        nr = Normalizer().normalize(pr, mapping)
        return nr.df["target"].tolist()

    def test_bool_yes_variants(self):
        for v in ["1", "yes", "да", "true", "y"]:
            result = self._norm([v])
            self.assertTrue(result[0], msg=f"Failed for: {v}")

    def test_bool_no_variants(self):
        for v in ["0", "no", "нет", "false", "n"]:
            result = self._norm([v])
            self.assertFalse(result[0], msg=f"Failed for: {v}")

    def test_bool_unknown_becomes_none(self):
        path = make_csv({"col": ["maybe", "unknown"], "anchor": [1, 2]})
        m = make_mapping([("col", "target", "bool"), ("anchor", "anc", "int")])
        pr = ParserEngine().parse(path, m)
        nr = Normalizer().normalize(pr, m)
        result = nr.df["target"].tolist()
        self.assertTrue(pd.isna(result[0]))


class TestNormalizerIntegration(unittest.TestCase):

    def test_full_pipeline_csv(self):
        """Полный прогон: CSV → parse → normalize."""
        path = make_csv({
            "Артикул WB":    ["ART-001", "ART-002", "ART-003"],
            "Дата продажи":  ["01.06.2024", "02.06.2024", "03.06.2024"],
            "Количество":    [5, "3", "2"],
            "Цена продажи":  ["1 500,00", "2 000,50", "750,00"],
            "Выручка":       [7500, 6001.5, 1500],
        })
        mapping = make_mapping([
            ("Артикул WB",   "sku",      "str",   True),
            ("Дата продажи", "date",     "date",  False, "%d.%m.%Y"),
            ("Количество",   "quantity", "int",   False),
            ("Цена продажи", "price",    "float", False),
            ("Выручка",      "revenue",  "float", False),
        ])
        parse_result = ParserEngine().parse(path, mapping)
        self.assertTrue(parse_result.ok, parse_result.warnings)

        norm_result = Normalizer().normalize(parse_result, mapping)
        self.assertTrue(norm_result.ok)
        self.assertEqual(norm_result.row_count, 3)

        df = norm_result.df
        self.assertEqual(df["sku"].iloc[0], "ART-001")
        self.assertEqual(df["quantity"].iloc[0], 5)
        self.assertAlmostEqual(df["price"].iloc[0], 1500.0)
        self.assertIsNotNone(df["date"].iloc[0])

    def test_full_pipeline_excel(self):
        path = make_excel({
            "SKU":       ["X1", "X2"],
            "Revenue":   [1000.0, 2000.0],
            "Qty":       [10, 20],
        })
        mapping = make_mapping([
            ("SKU",     "sku",      "str",   True),
            ("Revenue", "revenue",  "float"),
            ("Qty",     "quantity", "int"),
        ])
        parse_result = ParserEngine().parse(path, mapping)
        norm_result = Normalizer().normalize(parse_result, mapping)
        self.assertTrue(norm_result.ok)
        self.assertEqual(norm_result.row_count, 2)

    def test_empty_rows_cleaned(self):
        """Полностью пустые строки удаляются после нормализации."""
        path = make_csv({
            "Артикул WB": ["A1", None, "A3"],
            "Цена": [100, None, 300],
        })
        mapping = make_mapping([
            ("Артикул WB", "sku", "str"),
            ("Цена", "price", "float"),
        ])
        pr = ParserEngine().parse(path, mapping)
        nr = Normalizer().normalize(pr, mapping)
        self.assertEqual(nr.row_count, 2)


if __name__ == "__main__":
    unittest.main()
