"""
python -m pytest storage/tests/test_data_loader.py -v
Без БД — JSON-only режим.
"""
import sys, json, tempfile, unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mapping.mapping_storage import MappingObj
from normalizers.normalizer import NormalizeResult
from parsers.parser_engine import ParseResult
from storage.data_loader import DataLoader, LoadResult
from storage.error_handler import ErrorHandler, ErrorSeverity


def make_norm(data, ok=True):
    df = pd.DataFrame(data) if ok else pd.DataFrame()
    return NormalizeResult(df=df, filepath=Path("/tmp/t.csv"), row_count=len(df), ok=ok,
                           warnings=[] if ok else ["failed"])

def make_mapping(category="wb_report", sub="sales"):
    return MappingObj(id=1, name="T", struct_hash="h", category=category,
                      subcategory=sub, purpose="profit", column_count=2,
                      raw_columns=[], notes=None, is_active=True,
                      created_at=None, updated_at=None, fields=[])

def make_parse(ok=True, missing_req=None, missing_opt=None):
    df = pd.DataFrame({"sku": ["A1"]}) if ok else pd.DataFrame()
    return ParseResult(df=df, mapping_id=1, filepath=Path("/tmp/t.csv"),
                       row_count=len(df), ok=ok,
                       missing_required=missing_req or [],
                       missing_optional=missing_opt or [],
                       extra_columns=[], warnings=[])


class TestDataLoader(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.L = DataLoader(use_db=False, json_dir=self.d)

    def test_insert_products(self):
        r = self.L.load(make_norm({"sku":["A1","A2"],"name":["X","Y"]}), make_mapping(), 1)
        self.assertTrue(r.ok)
        self.assertIn("products", r.tables_written)
        self.assertGreaterEqual(r.rows_inserted, 2)

    def test_upsert_dedup(self):
        self.L.load(make_norm({"sku":["A1"],"name":["Old"]}), make_mapping(), 1)
        self.L.load(make_norm({"sku":["A1"],"name":["New"]}), make_mapping(), 2)
        prods = json.loads((self.d/"products.json").read_text())
        self.assertEqual(len([p for p in prods if p["sku"]=="A1"]), 1)
        self.assertEqual([p for p in prods if p["sku"]=="A1"][0]["name"], "New")

    def test_skip_null_sku(self):
        r = self.L.load(make_norm({"sku":[None,"A1"]}), make_mapping(), 1)
        self.assertGreaterEqual(r.rows_skipped, 1)

    def test_rows_total(self):
        r = self.L.load(make_norm({"sku":["A1","A2","A3"]}), make_mapping(), 1)
        self.assertEqual(r.rows_total, 3)

    def test_failed_norm_not_loaded(self):
        r = self.L.load(make_norm({}, ok=False), make_mapping(), 1)
        self.assertFalse(r.ok)

    def test_transactions_for_wb_report(self):
        r = self.L.load(make_norm({"sku":["A1"],"revenue":[1000.0]}), make_mapping("wb_report"), 5)
        self.assertIn("transactions", r.tables_written)
        trans = json.loads((self.d/"transactions.json").read_text())
        self.assertEqual(trans[0]["file_id"], 5)

    def test_no_transactions_for_external(self):
        r = self.L.load(make_norm({"sku":["A1"],"quantity":[10]}), make_mapping("external","stocks"), 1)
        self.assertNotIn("transactions", r.tables_written)

    def test_stocks_for_external(self):
        r = self.L.load(make_norm({"sku":["A1"],"quantity":[50],"warehouse":["MSK"]}),
                        make_mapping("external","stocks"), 1)
        self.assertIn("stocks", r.tables_written)
        stocks = json.loads((self.d/"stocks.json").read_text())
        self.assertEqual(stocks[0]["quantity"], 50)

    def test_multiple_batches_append(self):
        m = make_mapping("wb_report")
        self.L.load(make_norm({"sku":["A1"]}), m, 1)
        self.L.load(make_norm({"sku":["A2"]}), m, 2)
        trans = json.loads((self.d/"transactions.json").read_text())
        self.assertEqual(len(trans), 2)


class TestErrorHandler(unittest.TestCase):
    def setUp(self):
        self.eh = ErrorHandler(interactive=False)

    def test_parse_ok(self):
        self.assertTrue(self.eh.handle_parse_result(make_parse(ok=True)))

    def test_parse_missing_required(self):
        self.assertFalse(self.eh.handle_parse_result(make_parse(ok=False, missing_req=["Цена"])))
        errs = self.eh.get_errors(severity=ErrorSeverity.ERROR)
        self.assertTrue(any("Цена" in e.message for e in errs))

    def test_parse_missing_optional_still_ok(self):
        self.assertTrue(self.eh.handle_parse_result(make_parse(ok=True, missing_opt=["Комиссия"])))
        warns = self.eh.get_errors(severity=ErrorSeverity.WARNING)
        self.assertTrue(any("Комиссия" in e.message for e in warns))

    def test_normalize_type_errors_warning(self):
        nr = NormalizeResult(df=pd.DataFrame({"s":["a"]}), filepath=Path("/t"), row_count=1,
                             ok=True, type_errors={"price": 3})
        self.eh.handle_normalize_result(nr)
        warns = self.eh.get_errors(severity=ErrorSeverity.WARNING)
        self.assertTrue(any("price" in e.message for e in warns))

    def test_normalize_failed(self):
        nr = NormalizeResult(df=pd.DataFrame(), filepath=Path("/t"), row_count=0,
                             ok=False, warnings=["fail"])
        self.assertFalse(self.eh.handle_normalize_result(nr))

    def test_load_ok(self):
        lr = LoadResult(filepath=Path("/t"), mapping_category="wb_report",
                        rows_total=5, rows_inserted=5, rows_updated=0, rows_skipped=0,
                        tables_written=["transactions"], ok=True)
        self.assertTrue(self.eh.handle_load_result(lr))

    def test_load_error(self):
        lr = LoadResult(filepath=Path("/t"), mapping_category="wb_report",
                        rows_total=5, rows_inserted=0, rows_updated=0, rows_skipped=5,
                        errors=["DB down"], ok=False)
        self.assertFalse(self.eh.handle_load_result(lr))

    def test_summary_fields(self):
        self.eh.handle_parse_result(make_parse(ok=False, missing_req=["SKU"]))
        s = self.eh.summary()
        self.assertIn("total", s)
        self.assertIn("by_severity", s)
        self.assertIn("has_fatal", s)

    def test_clear_resets(self):
        self.eh.handle_parse_result(make_parse(ok=False, missing_req=["SKU"]))
        self.eh.clear()
        self.assertEqual(self.eh.get_errors(), [])

    def test_infer_date(self):
        self.assertEqual(ErrorHandler._infer_type(["01.06.2024","15.12.2024"]), "date")

    def test_infer_float(self):
        self.assertEqual(ErrorHandler._infer_type(["1500.5","2000.0"]), "float")

    def test_infer_int(self):
        self.assertEqual(ErrorHandler._infer_type(["100","200","300"]), "int")

    def test_infer_str(self):
        self.assertEqual(ErrorHandler._infer_type(["ART001","hello"]), "str")

    def test_infer_empty(self):
        self.assertIsNone(ErrorHandler._infer_type([None,""]))

    def test_persist_and_reload(self):
        tmp = Path(tempfile.mktemp(suffix=".json"))
        import storage.error_handler as m
        orig = m._ERROR_LOG_PATH
        m._ERROR_LOG_PATH = tmp
        try:
            self.eh.handle_parse_result(make_parse(ok=False, missing_req=["SKU"]))
            self.eh.persist_errors()
            data = json.loads(tmp.read_text())
            self.assertGreater(len(data), 0)
            self.assertIn("message", data[0])
        finally:
            m._ERROR_LOG_PATH = orig
            tmp.exists() and tmp.unlink()


if __name__ == "__main__":
    unittest.main()
