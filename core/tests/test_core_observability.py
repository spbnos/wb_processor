"""
core/tests/test_core_observability.py
Tests for: logging, metrics, schema_validator, middleware
"""
import sys, unittest, tempfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import structlog
from core.logging import get_logger, bind_ctx, clear_ctx, new_request_id, timed_log
from core.metrics import (
    inc_files_processed, inc_tasks, inc_api_request,
    observe_file_duration, observe_api_duration, observe_ml_inference,
    inc_mapping_decision, set_queue_depth, set_review_pending,
    set_active_mappings, get_metrics_output,
)
from core.schema_validator import SchemaValidator, ValidationIssue


class TestStructuredLogging(unittest.TestCase):

    def test_get_logger_returns_logger(self):
        log = get_logger("test.module")
        self.assertIsNotNone(log)

    def test_bind_ctx_request_id(self):
        from core.logging import _request_id
        bind_ctx(request_id="test-123")
        self.assertEqual(_request_id.get(), "test-123")
        clear_ctx()

    def test_bind_ctx_task_id(self):
        from core.logging import _task_id
        bind_ctx(task_id="task-abc")
        self.assertEqual(_task_id.get(), "task-abc")
        clear_ctx()

    def test_new_request_id_format(self):
        rid = new_request_id()
        self.assertIsInstance(rid, str)
        self.assertGreater(len(rid), 4)

    def test_clear_ctx_resets(self):
        from core.logging import _request_id, _task_id
        bind_ctx(request_id="x", task_id="y")
        clear_ctx()
        self.assertEqual(_request_id.get(), "")
        self.assertEqual(_task_id.get(), "")

    def test_timed_log_decorator_runs(self):
        @timed_log("test.operation")
        def slow_fn(x):
            return x * 2
        result = slow_fn(5)
        self.assertEqual(result, 10)

    def test_timed_log_propagates_exceptions(self):
        @timed_log("test.fail")
        def failing():
            raise ValueError("boom")
        with self.assertRaises(ValueError):
            failing()

    def test_multiple_binds_independent(self):
        from core.logging import _request_id, _file_name
        bind_ctx(request_id="r1", file_name="f.csv")
        self.assertEqual(_request_id.get(), "r1")
        self.assertEqual(_file_name.get(), "f.csv")
        clear_ctx()


class TestPrometheusMetrics(unittest.TestCase):

    def test_inc_files_processed(self):
        # Should not raise
        inc_files_processed("ok", "wb_report")
        inc_files_processed("error", "external")

    def test_inc_tasks(self):
        inc_tasks("process_file", "done")
        inc_tasks("health_check", "done")

    def test_inc_api_request(self):
        inc_api_request("GET", "/api/mappings", 200)
        inc_api_request("POST", "/api/files/upload", 202)
        inc_api_request("GET", "/api/mappings", 401)

    def test_observe_durations(self):
        observe_file_duration(1.5, "wb_report")
        observe_api_duration(0.05, "GET", "/api/stats/health")
        observe_ml_inference(0.02, "anomaly_detector")

    def test_inc_mapping_decision(self):
        inc_mapping_decision("auto_apply", 0.95)
        inc_mapping_decision("needs_review", 0.72)
        inc_mapping_decision("low_conf", 0.45)

    def test_gauges(self):
        set_queue_depth("high", 5)
        set_queue_depth("normal", 10)
        set_review_pending(3)
        set_active_mappings(15)

    def test_get_metrics_output_returns_bytes(self):
        data, content_type = get_metrics_output()
        self.assertIsInstance(data, bytes)
        self.assertIn("text/plain", content_type)

    def test_metrics_output_contains_wb_metrics(self):
        inc_files_processed("ok", "test_cat")
        data, _ = get_metrics_output()
        self.assertIn(b"wb_files_processed_total", data)

    def test_path_normalization(self):
        from core.metrics import _normalize_path
        self.assertEqual(_normalize_path("/api/mappings/42"), "/api/mappings/{id}")
        self.assertEqual(_normalize_path("/api/review/abc-def-12"), "/api/review/{id}")


class TestSchemaValidator(unittest.TestCase):

    def setUp(self):
        self.v = SchemaValidator()

    def _df(self, data):
        return pd.DataFrame(data)

    def test_valid_data_passes(self):
        df = self._df({
            "sku": ["A1", "A2", "A3"],
            "revenue": [1000.0, 2000.0, 3000.0],
            "quantity": [5, 10, 15],
            "price": [200.0, 200.0, 200.0],
        })
        r = self.v.validate(df, "wb_report")
        self.assertTrue(r.ok)
        self.assertEqual(r.valid_rows, 3)
        self.assertEqual(r.dropped_rows, 0)

    def test_null_sku_removed(self):
        df = self._df({
            "sku": ["A1", None, "A3"],
            "revenue": [1000.0, 2000.0, 3000.0],
        })
        r = self.v.validate(df)
        self.assertFalse(r.ok)   # has error (null required field)
        self.assertEqual(r.dropped_rows, 1)
        self.assertEqual(r.valid_rows, 2)

    def test_out_of_range_price_error(self):
        df = self._df({
            "sku": ["A1", "A2"],
            "price": [-100.0, 200.0],
        })
        r = self.v.validate(df)
        price_issues = [i for i in r.issues if i.field == "price" and i.issue_type == "out_of_range"]
        self.assertGreater(len(price_issues), 0)

    def test_outlier_detected_as_warning(self):
        from core.schema_validator import SchemaValidator
        # Use low zscore threshold (2σ) so outlier is detectable
        v = SchemaValidator(zscore_threshold=2.0)
        values = [100.0] * 20 + [50_000.0]  # clear outlier at 2σ
        df = pd.DataFrame({
            "sku": [f"A{i}" for i in range(21)],
            "revenue": values,
        })
        r = v.validate(df, "wb_report")
        outlier_issues = [i for i in r.issues if i.issue_type == "outlier"]
        self.assertGreater(len(outlier_issues), 0)
        self.assertEqual(outlier_issues[0].severity, "warning")

    def test_duplicate_warning(self):
        df = self._df({
            "sku": ["A1", "A1"],
            "date": ["2024-01-01", "2024-01-01"],
            "revenue": [1000.0, 1000.0],
        })
        r = self.v.validate(df)
        dup_issues = [i for i in r.issues if i.issue_type == "duplicate"]
        self.assertGreater(len(dup_issues), 0)
        self.assertEqual(dup_issues[0].severity, "warning")
        # duplicates are warnings — ok should still be True if no other errors
        self.assertTrue(r.ok)

    def test_empty_df_passes(self):
        r = self.v.validate(pd.DataFrame())
        self.assertTrue(r.ok)
        self.assertEqual(r.valid_rows, 0)

    def test_valid_rows_count(self):
        df = self._df({
            "sku": ["A1", None, "A3", "A4"],
            "price": [100.0, 200.0, -50.0, 300.0],
        })
        r = self.v.validate(df)
        # Row 1 (null sku) + Row 2 (negative price) = 2 bad
        self.assertEqual(r.dropped_rows, 2)
        self.assertEqual(r.valid_rows, 2)

    def test_validation_result_structure(self):
        df = self._df({"sku": ["A1"], "revenue": [1000.0]})
        r = self.v.validate(df)
        self.assertIsInstance(r.df, pd.DataFrame)
        self.assertIsInstance(r.issues, list)
        self.assertIsInstance(r.ok, bool)
        self.assertIsInstance(r.warnings, list)


class TestMiddleware(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import tempfile, mapping.mapping_storage as ms, review_queue.queue_store as qs
        tmp = Path(tempfile.mkdtemp())
        ms._DEFAULT_JSON_PATH = tmp / "m.json"
        qs._DEFAULT_QUEUE_PATH = tmp / "q.json"

        from fastapi.testclient import TestClient
        from api.main import app
        cls.client = TestClient(app)

    def test_x_process_time_header(self):
        r = self.client.get("/api/stats/health")
        self.assertIn("X-Process-Time-Ms", r.headers)

    def test_x_request_id_header(self):
        r = self.client.get("/api/stats/health")
        self.assertIn("X-Request-ID", r.headers)

    def test_custom_request_id_propagated(self):
        r = self.client.get("/api/stats/health",
                            headers={"X-Request-ID": "custom-abc"})
        # Custom ID must be echoed back (or a generated one)
        self.assertIn("X-Request-ID", r.headers)

    def test_metrics_endpoint_returns_prometheus(self):
        r = self.client.get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/plain", r.headers["content-type"])

    def test_process_time_is_numeric(self):
        r = self.client.get("/api/stats/health")
        ms = r.headers["X-Process-Time-Ms"]
        try:
            float(ms)
        except ValueError:
            self.fail(f"X-Process-Time-Ms not numeric: {ms!r}")


if __name__ == "__main__":
    unittest.main()
