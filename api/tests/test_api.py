"""
python -m pytest api/tests/test_api.py -v
FastAPI тесты через httpx TestClient — без реального Redis/DB.
"""
import sys, json, tempfile, unittest
from pathlib import Path
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_PLATFORM = Path(__file__).resolve().parents[3] / "wb_platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from fastapi.testclient import TestClient
import mapping.mapping_storage as ms_mod
from review_queue import queue_store as qs_mod

# Патчим пути хранилищ перед импортом app
_tmp = Path(tempfile.mkdtemp())
_mapping_json = _tmp / "mappings.json"
_queue_json   = _tmp / "queue.json"
ms_mod._DEFAULT_JSON_PATH = _mapping_json
qs_mod._DEFAULT_QUEUE_PATH = _queue_json

from api.main import app
from api.deps import get_storage, get_review_queue, get_redis_client
from mapping.mapping_storage import MappingStorage
from review_queue.queue_store import ReviewQueue
from worker.queue_client import RedisQueueClient

# Переопределяем зависимости на изолированные экземпляры
_storage = MappingStorage(use_db=False, json_path=_mapping_json)
_queue   = ReviewQueue(use_db=False, path=_queue_json)
_redis   = RedisQueueClient(mock=True)

app.dependency_overrides[get_storage]      = lambda: _storage
app.dependency_overrides[get_review_queue] = lambda: _queue
app.dependency_overrides[get_redis_client] = lambda: _redis


_AUTH = {"X-API-Key": "dev-key-change-in-prod"}
client = TestClient(app)


def _fresh_overrides():
    """Create fresh isolated storage instances and override dependencies."""
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    fresh_storage = MappingStorage(use_db=False, json_path=tmp / "m.json")
    fresh_queue   = ReviewQueue(use_db=False, path=tmp / "q.json")
    fresh_redis   = RedisQueueClient(mock=True)
    app.dependency_overrides[get_storage]      = lambda: fresh_storage
    app.dependency_overrides[get_review_queue] = lambda: fresh_queue
    app.dependency_overrides[get_redis_client] = lambda: fresh_redis
    return fresh_storage, fresh_queue, fresh_redis, tmp


# ──────────────────────────────────────────────────────────────────────
# Health / Root
# ──────────────────────────────────────────────────────────────────────
class TestHealthAndRoot(unittest.TestCase):

    def test_root(self):
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("WB Intelligent", r.json()["name"])

    def test_health_no_auth(self):
        r = client.get("/api/stats/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_docs_available(self):
        r = client.get("/docs")
        self.assertEqual(r.status_code, 200)


# ──────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────
class TestAuth(unittest.TestCase):

    def test_no_auth_returns_401(self):
        r = client.get("/api/mappings")
        self.assertEqual(r.status_code, 401)

    def test_wrong_api_key_returns_401(self):
        r = client.get("/api/mappings", headers={"X-API-Key": "wrong-key"})
        self.assertEqual(r.status_code, 401)

    def test_valid_api_key(self):
        r = client.get("/api/mappings", headers=_AUTH)
        self.assertEqual(r.status_code, 200)

    def test_timing_header_present(self):
        r = client.get("/api/stats/health")
        self.assertIn("X-Process-Time-Ms", r.headers)


# ──────────────────────────────────────────────────────────────────────
# Mappings API
# ──────────────────────────────────────────────────────────────────────
class TestMappingsAPI(unittest.TestCase):

    def setUp(self):
        self._storage, self._queue, self._redis, self._tmp = _fresh_overrides()
        self._mapping_json = self._tmp / "m.json"

    def _import_mapping(self, name: str, struct_hash: str) -> None:
        data = [{
            "id": 1, "name": name, "struct_hash": struct_hash,
            "category": "wb_report", "subcategory": "sales",
            "purpose": "profit", "column_count": 2,
            "raw_columns": ["SKU", "Revenue"], "notes": None,
            "is_active": True, "created_at": None, "updated_at": None,
            "fields": [
                {"source_column": "SKU", "target_field": "sku", "data_type": "str",
                 "date_format": None, "is_required": True, "description": None},
                {"source_column": "Revenue", "target_field": "revenue",
                 "data_type": "float", "date_format": None,
                 "is_required": False, "description": None},
            ]
        }]
        self._mapping_json.write_text(json.dumps(data, ensure_ascii=False))

    def test_list_empty(self):
        r = client.get("/api/mappings", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_list_with_mappings(self):
        self._import_mapping("WB Sales", "hash_sales_001")
        r = client.get("/api/mappings", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["name"], "WB Sales")

    def test_get_mapping_by_id(self):
        self._import_mapping("WB Sales", "hash_sales_002")
        r = client.get("/api/mappings/1", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("fields", data)
        self.assertEqual(len(data["fields"]), 2)

    def test_get_mapping_not_found(self):
        r = client.get("/api/mappings/999", headers=_AUTH)
        self.assertEqual(r.status_code, 404)

    def test_update_mapping_name(self):
        self._import_mapping("Old Name", "hash_update_01")
        r = client.put(
            "/api/mappings/1",
            headers=_AUTH,
            json={"name": "New Name"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "New Name")

    def test_update_no_fields_400(self):
        self._import_mapping("Test", "hash_upd_empty")
        r = client.put("/api/mappings/1", headers=_AUTH, json={})
        self.assertEqual(r.status_code, 400)

    def test_delete_mapping(self):
        self._import_mapping("To Delete", "hash_delete_01")
        r = client.delete("/api/mappings/1", headers=_AUTH)
        self.assertEqual(r.status_code, 204)
        # После мягкого удаления — не видно в active list
        r2 = client.get("/api/mappings", headers=_AUTH)
        self.assertEqual(len(r2.json()), 0)

    def test_stats_endpoint(self):
        r = client.get("/api/mappings/stats", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("total", data)
        self.assertIn("active", data)

    def test_export_endpoint(self):
        self._import_mapping("Export Test", "hash_export_01")
        r = client.get("/api/mappings/export/json", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertIn("mappings", r.json())

    def test_filter_by_category(self):
        self._import_mapping("WB Report", "hash_cat_01")
        r = client.get("/api/mappings?category=wb_report", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)


# ──────────────────────────────────────────────────────────────────────
# Files / Queue API
# ──────────────────────────────────────────────────────────────────────
class TestFilesAPI(unittest.TestCase):

    def test_queue_status(self):
        r = client.get("/api/files/queue", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for key in ("high", "normal", "low", "dead"):
            self.assertIn(key, data)

    def test_upload_unsupported_format(self):
        r = client.post(
            "/api/files/upload",
            headers=_AUTH,
            files={"file": ("test.pdf", b"content", "application/pdf")},
        )
        self.assertEqual(r.status_code, 400)

    def test_upload_csv(self):
        csv_content = b"SKU,Revenue\nART001,1000\nART002,2000\n"
        r = client.post(
            "/api/files/upload",
            headers=_AUTH,
            files={"file": ("test.csv", csv_content, "text/csv")},
        )
        self.assertEqual(r.status_code, 202)
        data = r.json()
        self.assertIn("task_id", data)
        self.assertEqual(data["status"], "queued")

    def test_upload_xlsx(self):
        import pandas as pd
        buf = io.BytesIO()
        pd.DataFrame({"SKU": ["A1"], "Rev": [100]}).to_excel(buf, index=False)
        buf.seek(0)
        r = client.post(
            "/api/files/upload",
            headers=_AUTH,
            files={"file": ("test.xlsx", buf.read(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(r.status_code, 202)

    def test_get_task_not_found(self):
        r = client.get("/api/files/tasks/nonexistent-id", headers=_AUTH)
        self.assertEqual(r.status_code, 404)

    def test_upload_then_get_task(self):
        csv_content = b"SKU,Revenue\nART001,1000\n"
        upload_r = client.post(
            "/api/files/upload",
            headers=_AUTH,
            files={"file": ("t.csv", csv_content, "text/csv")},
        )
        task_id = upload_r.json()["task_id"]
        # Task ещё pending — результат не сохранён до обработки воркером
        r = client.get(f"/api/files/tasks/{task_id}", headers=_AUTH)
        # 404 — потому что воркер ещё не обработал и не сохранил result
        self.assertIn(r.status_code, (404, 200))


# ──────────────────────────────────────────────────────────────────────
# Review API
# ──────────────────────────────────────────────────────────────────────
class TestReviewAPI(unittest.TestCase):

    def setUp(self):
        self._storage, self._queue, self._redis, self._tmp = _fresh_overrides()

    def _add_item(self, col="Артикул WB", field="sku", score=0.72) -> str:
        from review_queue.queue_store import ReviewItem
        from smart_mapping.confidence_scorer import ConfidenceLevel
        item = ReviewItem(
            id=f"hash_review::{col}",
            struct_hash="hash_review",
            source_column=col,
            suggested_field=field,
            suggested_type="str",
            confidence_score=score,
            confidence_level=ConfidenceLevel.NEEDS_REVIEW.value,
            match_method="fuzzy_token",
            runner_up_field=None,
            runner_up_score=0.0,
            filepath="/tmp/t.csv",
            filename="t.csv",
        )
        self._queue.enqueue(item)
        return item.id

    def test_get_pending_empty(self):
        r = client.get("/api/review", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_get_pending_returns_items(self):
        self._add_item()
        r = client.get("/api/review", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["source_column"], "Артикул WB")

    def test_approve_suggested(self):
        item_id = self._add_item()
        r = client.post(f"/api/review/{item_id}/approve", headers=_AUTH, json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "approved")
        self.assertEqual(r.json()["correct_field"], "sku")

    def test_approve_override_field(self):
        item_id = self._add_item()
        r = client.post(
            f"/api/review/{item_id}/approve",
            headers=_AUTH,
            json={"field": "barcode"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["correct_field"], "barcode")

    def test_reject_with_correction(self):
        item_id = self._add_item()
        r = client.post(
            f"/api/review/{item_id}/reject",
            headers=_AUTH,
            json={"correct_field": "barcode"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "rejected")
        self.assertEqual(r.json()["correct_field"], "barcode")

    def test_approve_not_found(self):
        r = client.post("/api/review/nonexistent::col/approve", headers=_AUTH, json={})
        self.assertEqual(r.status_code, 404)

    def test_review_stats(self):
        self._add_item("Col1")
        self._add_item("Col2")
        r = client.get("/api/review/stats", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pending"], 2)

    def test_apply_reviews_enqueues_task(self):
        r = client.post("/api/review/apply/hash_test", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("task_id", data)
        self.assertEqual(data["struct_hash"], "hash_test")

    def test_filter_by_struct_hash(self):
        self._add_item("C1")
        # Добавляем item с другим hash напрямую
        from review_queue.queue_store import ReviewItem
        from smart_mapping.confidence_scorer import ConfidenceLevel
        item2 = ReviewItem(
            id="other_hash::C2",
            struct_hash="other_hash",
            source_column="C2",
            suggested_field="price",
            suggested_type="float",
            confidence_score=0.65,
            confidence_level=ConfidenceLevel.NEEDS_REVIEW.value,
            match_method="fuzzy_partial",
            runner_up_field=None, runner_up_score=0.0,
            filepath="/tmp/t.csv", filename="t.csv",
        )
        self._queue.enqueue(item2)

        r = client.get("/api/review?struct_hash=hash_review", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)


# ──────────────────────────────────────────────────────────────────────
# Stats API
# ──────────────────────────────────────────────────────────────────────
class TestStatsAPI(unittest.TestCase):

    def test_system_stats_structure(self):
        r = client.get("/api/stats/system", headers=_AUTH)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("mappings", data)
        self.assertIn("review_queue", data)
        self.assertIn("redis_queues", data)


if __name__ == "__main__":
    unittest.main()
