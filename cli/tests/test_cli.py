"""
python -m pytest cli/tests/test_cli.py -v
"""
import sys, json, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from click.testing import CliRunner
from cli.commands import cli


def _make_mapping_json(name, struct_hash, category="wb_report", sub="sales"):
    return [{
        "id": 1, "name": name, "struct_hash": struct_hash,
        "category": category, "subcategory": sub, "purpose": "profit",
        "column_count": 2, "raw_columns": ["SKU","Цена"], "notes": None,
        "is_active": True, "created_at": None, "updated_at": None,
        "fields": [
            {"source_column":"SKU","target_field":"sku","data_type":"str",
             "date_format":None,"is_required":True,"description":None},
            {"source_column":"Цена","target_field":"price","data_type":"float",
             "date_format":None,"is_required":False,"description":None},
        ]
    }]


class TestMappingsCLI(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.tmpdir = Path(tempfile.mkdtemp())
        self._json_path = self.tmpdir / "mappings.json"
        # Patch global JSON path so tests are isolated
        import mapping.mapping_storage as ms_mod
        self._orig_path = ms_mod._DEFAULT_JSON_PATH
        ms_mod._DEFAULT_JSON_PATH = self._json_path

    def tearDown(self):
        import mapping.mapping_storage as ms_mod
        ms_mod._DEFAULT_JSON_PATH = self._orig_path

    def _invoke(self, args):
        return self.runner.invoke(cli, args, catch_exceptions=False)

    def test_list_empty(self):
        r = self._invoke(["mappings","list"])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("не найдено", r.output.lower())

    def test_show_not_found(self):
        r = self.runner.invoke(cli, ["mappings","show","999"])
        self.assertIn("не найден", r.output.lower())

    def test_delete_not_found(self):
        r = self.runner.invoke(cli, ["mappings","delete","999","--yes"])
        self.assertIn("не найден", r.output.lower())

    def test_export_creates_file(self):
        out = self.tmpdir / "export.json"
        r = self._invoke(["mappings","export", str(out)])
        self.assertEqual(r.exit_code, 0)
        self.assertTrue(out.exists())
        self.assertIsInstance(json.loads(out.read_text()), list)

    def test_import_nonexistent_path(self):
        r = self.runner.invoke(cli, ["mappings","import","/no/such/file.json"])
        self.assertIn("не найден", r.output.lower())

    def test_import_valid_json(self):
        out = self.tmpdir / "m.json"
        out.write_text(json.dumps(_make_mapping_json("Import Test","hash_import1"), ensure_ascii=False))
        r = self._invoke(["mappings","import", str(out)])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("1", r.output)

    def test_list_shows_imported(self):
        out = self.tmpdir / "m.json"
        out.write_text(json.dumps(_make_mapping_json("List Test","hash_list11"), ensure_ascii=False))
        self._invoke(["mappings","import", str(out)])
        r = self._invoke(["mappings","list"])
        self.assertIn("List Test", r.output)

    def test_show_imported(self):
        out = self.tmpdir / "m.json"
        out.write_text(json.dumps(_make_mapping_json("Show Test","hash_show11","external","stocks"), ensure_ascii=False))
        self._invoke(["mappings","import", str(out)])
        r = self.runner.invoke(cli, ["mappings","show","1"])
        self.assertIn("Show Test", r.output)

    def test_status_cmd(self):
        r = self._invoke(["status"])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("маппинг", r.output.lower())

    def test_cli_help(self):
        r = self._invoke(["--help"])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("mappings", r.output)

    def test_mappings_help(self):
        r = self._invoke(["mappings","--help"])
        self.assertEqual(r.exit_code, 0)
        for cmd in ["list","show","delete"]:
            self.assertIn(cmd, r.output)

    def test_delete_soft(self):
        out = self.tmpdir / "m.json"
        out.write_text(json.dumps(_make_mapping_json("Del Test","hash_del1111"), ensure_ascii=False))
        self._invoke(["mappings","import", str(out)])
        r = self._invoke(["mappings","delete","1","--yes"])
        self.assertIn("деактивирован", r.output.lower())

    def test_delete_then_not_in_list(self):
        out = self.tmpdir / "m.json"
        out.write_text(json.dumps(_make_mapping_json("Gone","hash_gone1111"), ensure_ascii=False))
        self._invoke(["mappings","import", str(out)])
        self._invoke(["mappings","delete","1","--yes"])
        r = self._invoke(["mappings","list"])
        # После мягкого удаления не должен показываться в активных
        self.assertNotIn("Gone", r.output)


class TestPipeline(unittest.TestCase):

    def test_pipeline_unknown_format_cancelled(self):
        import tempfile
        import pandas as pd
        from pipeline import Pipeline
        from unittest.mock import patch

        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
        pd.DataFrame({"Col1":["A"],"Col2":[1]}).to_csv(tmp.name, index=False)
        p = Pipeline(use_db=False)
        with patch.object(p.mapper, "run", side_effect=InterruptedError("cancelled")):
            p.process_file(Path(tmp.name))  # не должно падать

    def test_pipeline_known_format_full_run(self):
        import tempfile
        import pandas as pd
        from pipeline import Pipeline
        from mapping.interactive_mapper import MappingConfig, FieldMapping
        from classification.file_classifier import compute_struct_hash

        cols = {"SKU":["A1","A2"],"Revenue":[1000.0,2000.0]}
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
        pd.DataFrame(cols).to_csv(tmp.name, index=False)
        filepath = Path(tmp.name)

        p = Pipeline(use_db=False)
        struct_hash = compute_struct_hash(list(cols.keys()))
        config = MappingConfig(
            name="Pipeline Test", struct_hash=struct_hash,
            category="wb_report", subcategory="sales", purpose="profit",
            raw_columns=list(cols.keys()), column_count=2,
            fields=[
                FieldMapping("SKU","sku","str",is_required=True),
                FieldMapping("Revenue","revenue","float"),
            ],
        )
        p.storage.save(config)
        p.process_file(filepath)  # не должно падать


if __name__ == "__main__":
    unittest.main()
