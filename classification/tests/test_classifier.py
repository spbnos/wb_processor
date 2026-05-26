"""
python -m pytest classification/tests/test_classifier.py -v
"""
import sys
from pathlib import Path
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from classification.file_classifier import (
    compute_struct_hash,
    compute_file_hash,
    _find_header_row,
    FileClassifier,
)


# ─── Stub MappingStorage ───
class StubStorage:
    def __init__(self, known_hash=None):
        self._hash = known_hash

    def find_by_struct_hash(self, h):
        if h == self._hash:
            class M:
                id = 1
                name = "test_mapping"
            return M()
        return None


class TestStructHash(unittest.TestCase):
    def test_same_columns_same_hash(self):
        h1 = compute_struct_hash(["SKU", "Цена", "Количество"])
        h2 = compute_struct_hash(["Количество", "SKU", "Цена"])
        self.assertEqual(h1, h2)

    def test_different_columns_different_hash(self):
        h1 = compute_struct_hash(["SKU", "Цена"])
        h2 = compute_struct_hash(["SKU", "Артикул"])
        self.assertNotEqual(h1, h2)

    def test_case_insensitive(self):
        h1 = compute_struct_hash(["sku", "price"])
        h2 = compute_struct_hash(["SKU", "PRICE"])
        self.assertEqual(h1, h2)


class TestFindHeaderRow(unittest.TestCase):
    def test_header_not_first_row(self):
        df = pd.DataFrame({
            0: ["Отчёт WB", "SKU", "АРТ001"],
            1: [None, "Цена", 1500],
            2: [None, "Количество", 10],
        })
        row = _find_header_row(df)
        self.assertEqual(row, 1)  # строка с SKU/Цена/Количество

    def test_header_first_row(self):
        df = pd.DataFrame({
            0: ["SKU", "АРТ001", "АРТ002"],
            1: ["Цена", 1500, 2000],
        })
        row = _find_header_row(df)
        self.assertEqual(row, 0)


class TestFileClassifier(unittest.TestCase):
    def _make_csv(self, columns: list, rows=3) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8")
        tmp.write(",".join(columns) + "\n")
        for i in range(rows):
            tmp.write(",".join(["val"] * len(columns)) + "\n")
        tmp.close()
        return Path(tmp.name)

    def test_unknown_format(self):
        path = self._make_csv(["SKU", "Цена", "Остаток"])
        storage = StubStorage(known_hash="nonexistent")
        clf = FileClassifier(storage)
        result = clf.classify(path)
        self.assertFalse(result.is_known)
        self.assertIsNone(result.mapping_id)

    def test_known_format(self):
        cols = ["SKU", "Цена", "Остаток"]
        path = self._make_csv(cols)
        h = compute_struct_hash(cols)
        storage = StubStorage(known_hash=h)
        clf = FileClassifier(storage)
        result = clf.classify(path)
        self.assertTrue(result.is_known)
        self.assertEqual(result.mapping_id, 1)
        self.assertEqual(result.mapping_name, "test_mapping")


if __name__ == "__main__":
    unittest.main()
