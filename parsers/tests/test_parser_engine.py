"""
python -m pytest parsers/tests/test_parser_engine.py -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from parsers.parser_engine import (
    ParserEngine, ParseResult, _build_rename_map, _apply_mapping,
)
from mapping.mapping_storage import MappingStorage, MappingObj, MappingFieldObj
from mapping.interactive_mapper import MappingConfig, FieldMapping
from classification.file_classifier import FileSignature


# ─── Helpers ─────────────────────────────────────────────
def make_csv(columns: list, rows: list, suffix=".csv") -> Path:
    tmp = tempfile.NamedTemporaryFile(
        suffix=suffix, delete=False, mode="w", encoding="utf-8"
    )
    tmp.write(",".join(columns) + "\n")
    for row in rows:
        tmp.write(",".join(str(v) for v in row) + "\n")
    tmp.close()
    return Path(tmp.name)


def make_signature(filepath: Path, columns: list) -> FileSignature:
    return FileSignature(
        filepath=filepath,
        extension=filepath.suffix.lower(),
        columns=columns,
        column_count=len(columns),
        struct_hash="testhash",
        file_hash="filehash",
        sample=pd.DataFrame(columns=columns),
        row_count_estimate=10,
        sheet_name=None,
        encoding="utf-8",
        extra={"sep": ","},
    )


def make_mapping_obj(fields_spec: list[tuple]) -> MappingObj:
    """fields_spec: [(source, target, dtype, required), ...]"""
    fields = [
        MappingFieldObj(
            source_column=src,
            target_field=tgt,
            data_type=dtype,
            is_required=req,
            mapping_id=1,
        )
        for src, tgt, dtype, req in fields_spec
    ]
    return MappingObj(
        id=1,
        name="Test Mapping",
        struct_hash="testhash",
        category="wb_report",
        subcategory="sales",
        purpose="profit",
        column_count=len(fields),
        raw_columns=[f[0] for f in fields_spec],
        notes=None,
        is_active=True,
        created_at=None,
        updated_at=None,
        fields=fields,
    )


def make_storage_with_mapping(mapping_obj: MappingObj) -> MappingStorage:
    """Создаёт storage с одним маппингом."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    path = Path(tmp.name)
    storage = MappingStorage(use_db=False, json_path=path)
    config = MappingConfig(
        name=mapping_obj.name,
        struct_hash=mapping_obj.struct_hash,
        category=mapping_obj.category,
        subcategory=mapping_obj.subcategory or "",
        purpose=mapping_obj.purpose or "",
        raw_columns=mapping_obj.raw_columns or [],
        column_count=mapping_obj.column_count or 0,
        fields=[
            FieldMapping(
                source_column=f.source_column,
                target_field=f.target_field,
                data_type=f.data_type,
                is_required=f.is_required,
            )
            for f in mapping_obj.fields
        ],
    )
    storage.save(config)
    return storage


# ─────────────────────────────────────────────────────────
class TestBuildRenameMap(unittest.TestCase):
    def test_basic_rename(self):
        columns = ["Артикул WB", "Цена", "Количество"]
        fields = [
            MappingFieldObj("Артикул WB", "sku",      "str", is_required=True,  mapping_id=1),
            MappingFieldObj("Цена",        "price",    "float", is_required=False, mapping_id=1),
            MappingFieldObj("Количество",  "quantity", "int",   is_required=False, mapping_id=1),
        ]
        rename_map, ignore_cols, errors = _build_rename_map(columns, fields)
        self.assertEqual(rename_map["Артикул WB"], "sku")
        self.assertEqual(rename_map["Цена"], "price")
        self.assertEqual(rename_map["Количество"], "quantity")
        self.assertEqual(len(errors), 0)

    def test_ignore_column(self):
        columns = ["Артикул WB", "Мусор"]
        fields = [
            MappingFieldObj("Артикул WB", "sku",    "str", mapping_id=1),
            MappingFieldObj("Мусор",       "ignore", "str", mapping_id=1),
        ]
        rename_map, ignore_cols, errors = _build_rename_map(columns, fields)
        self.assertIn("Мусор", ignore_cols)
        self.assertNotIn("Мусор", rename_map)

    def test_missing_optional_column(self):
        columns = ["Артикул WB"]
        fields = [
            MappingFieldObj("Артикул WB",   "sku",   "str", is_required=True,  mapping_id=1),
            MappingFieldObj("Нет в файле", "price", "float", is_required=False, mapping_id=1),
        ]
        rename_map, ignore_cols, errors = _build_rename_map(columns, fields)
        self.assertEqual(len(errors), 1)
        self.assertFalse(errors[0].is_critical)

    def test_missing_required_column(self):
        columns = ["Цена"]
        fields = [
            MappingFieldObj("SKU обязательный", "sku", "str", is_required=True, mapping_id=1),
            MappingFieldObj("Цена",             "price", "float", mapping_id=1),
        ]
        rename_map, ignore_cols, errors = _build_rename_map(columns, fields)
        critical = [e for e in errors if e.is_critical]
        self.assertEqual(len(critical), 1)


class TestParserEngineWithFile(unittest.TestCase):
    def test_parse_csv_success(self):
        cols = ["Артикул WB", "Цена", "Количество"]
        rows = [
            ["АРТ001", "1500.00", "10"],
            ["АРТ002", "2000.50", "5"],
        ]
        csv_path = make_csv(cols, rows)
        sig = make_signature(csv_path, cols)
        mapping = make_mapping_obj([
            ("Артикул WB", "sku",      "str",   True),
            ("Цена",        "price",    "float", False),
            ("Количество",  "quantity", "int",   False),
        ])
        storage = make_storage_with_mapping(mapping)
        engine = ParserEngine(storage)
        result = engine.parse(sig, mapping_id=1)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.df)
        self.assertIn("sku", result.df.columns)
        self.assertIn("price", result.df.columns)
        self.assertIn("quantity", result.df.columns)
        self.assertEqual(len(result.df), 2)

    def test_parse_csv_with_ignore_column(self):
        cols = ["Артикул WB", "Мусор", "Цена"]
        rows = [["АРТ001", "ненужное", "1500"]]
        csv_path = make_csv(cols, rows)
        sig = make_signature(csv_path, cols)
        mapping = make_mapping_obj([
            ("Артикул WB", "sku",    "str",   True),
            ("Мусор",       "ignore", "str",   False),
            ("Цена",        "price",  "float", False),
        ])
        storage = make_storage_with_mapping(mapping)
        engine = ParserEngine(storage)
        result = engine.parse(sig, mapping_id=1)

        self.assertTrue(result.success)
        self.assertNotIn("ignore", result.df.columns)
        self.assertNotIn("Мусор", result.df.columns)
        self.assertIn("sku", result.df.columns)

    def test_parse_missing_optional_column(self):
        cols = ["Артикул WB", "Цена"]   # нет "Количество"
        rows = [["АРТ001", "1500"]]
        csv_path = make_csv(cols, rows)
        sig = make_signature(csv_path, cols)
        mapping = make_mapping_obj([
            ("Артикул WB", "sku",      "str",   True),
            ("Цена",        "price",    "float", False),
            ("Количество",  "quantity", "int",   False),  # optional, missing
        ])
        storage = make_storage_with_mapping(mapping)
        engine = ParserEngine(storage)
        result = engine.parse(sig, mapping_id=1)

        # Успех — колонка не обязательная
        self.assertTrue(result.success)
        self.assertEqual(len(result.errors), 1)
        self.assertFalse(result.errors[0].is_critical)

    def test_parse_missing_required_column_fails(self):
        cols = ["Цена"]   # нет SKU (обязательного)
        rows = [["1500"]]
        csv_path = make_csv(cols, rows)
        sig = make_signature(csv_path, cols)
        mapping = make_mapping_obj([
            ("Артикул WB", "sku",   "str",   True),   # required, missing!
            ("Цена",        "price", "float", False),
        ])
        storage = make_storage_with_mapping(mapping)
        engine = ParserEngine(storage)
        result = engine.parse(sig, mapping_id=1)

        self.assertFalse(result.success)
        self.assertTrue(result.has_critical_errors)

    def test_parse_with_mapping_obj_directly(self):
        cols = ["SKU", "Кол-во"]
        rows = [["АРТ001", "5"], ["АРТ002", "10"]]
        csv_path = make_csv(cols, rows)
        sig = make_signature(csv_path, cols)
        mapping = make_mapping_obj([
            ("SKU",     "sku",      "str", True),
            ("Кол-во",  "quantity", "int", False),
        ])
        storage = make_storage_with_mapping(mapping)
        engine = ParserEngine(storage)
        result = engine.parse_with_mapping_obj(sig, mapping)

        self.assertTrue(result.success)
        self.assertEqual(len(result.df), 2)

    def test_parse_invalid_mapping_id(self):
        cols = ["SKU"]
        csv_path = make_csv(cols, [["АРТ001"]])
        sig = make_signature(csv_path, cols)
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        storage = MappingStorage(use_db=False, json_path=Path(tmp.name))
        engine = ParserEngine(storage)
        result = engine.parse(sig, mapping_id=999)

        self.assertFalse(result.success)
        self.assertIsNone(result.df)


if __name__ == "__main__":
    unittest.main()
