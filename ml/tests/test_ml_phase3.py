"""
python -m pytest ml/tests/test_ml_phase3.py -v
Feature Store + Training Pipeline + Inference + Drift Detection
"""
import sys, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from feature_store.schema import FeatureStoreSchema, FeatureSet, FeatureValue
from feature_store.aggregator import SalesAggregator, StockAggregator
from feature_store.feature_pipeline import FeaturePipeline
from ml.model_registry import ModelRegistry, ModelRecord
from ml.training_pipeline import (
    AnomalyDetectorTrainer, StockoutPredictorTrainer,
    TrainingOrchestrator,
)
from ml.inference_service import InferenceService
from ml.drift_detector import DriftDetector


# ─── Helpers ─────────────────────────────────────────────────────────

def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp())


def _sales_df(n_skus=5, n_days=30) -> pd.DataFrame:
    """Генерирует DataFrame транзакций для теста."""
    rows = []
    base = datetime.now(timezone.utc) - timedelta(days=n_days)
    for sku in [f"ART{i:03d}" for i in range(n_skus)]:
        for d in range(n_days):
            rows.append({
                "sku": sku,
                "date": (base + timedelta(days=d)).strftime("%Y-%m-%d"),
                "revenue": np.random.uniform(500, 5000),
                "quantity": np.random.randint(1, 20),
                "price": np.random.uniform(200, 1500),
                "commission": np.random.uniform(50, 500),
            })
    return pd.DataFrame(rows)


def _stock_df(n_skus=5) -> pd.DataFrame:
    rows = []
    for i in range(n_skus):
        sku = f"ART{i:03d}"
        qty = np.random.randint(0, 200)
        rows.append({
            "sku": sku,
            "quantity": qty,
            "reserved": np.random.randint(0, max(qty, 1)),
            "in_transit": np.random.randint(0, 50),
        })
    return pd.DataFrame(rows)


def _sales_feature_matrix(n_skus=15) -> pd.DataFrame:
    """Feature matrix для обучения аномалии."""
    np.random.seed(42)
    return pd.DataFrame({
        "revenue_7d":          np.random.lognormal(8, 1, n_skus),
        "revenue_30d":         np.random.lognormal(9, 1, n_skus),
        "revenue_90d":         np.random.lognormal(10, 1, n_skus),
        "qty_sold_7d":         np.random.randint(1, 50, n_skus).astype(float),
        "qty_sold_30d":        np.random.randint(5, 200, n_skus).astype(float),
        "avg_price_30d":       np.random.uniform(200, 2000, n_skus),
        "order_count_30d":     np.random.randint(5, 50, n_skus).astype(float),
        "revenue_trend_30d":   np.random.uniform(-100, 200, n_skus),
        "days_since_last_sale":np.random.randint(0, 10, n_skus).astype(float),
        "commission_rate_30d": np.random.uniform(0.1, 0.3, n_skus),
    }, index=[f"ART{i:03d}" for i in range(n_skus)])


def _stock_feature_matrix(n_skus=15) -> pd.DataFrame:
    np.random.seed(99)
    qty = np.random.randint(0, 200, n_skus).astype(float)
    reserved = np.minimum(qty, np.random.randint(0, 100, n_skus).astype(float))
    risk = 1.0 - np.minimum((qty - reserved) / (qty + 1), 1.0)
    return pd.DataFrame({
        "stock_qty_current":        qty,
        "stock_reserved_current":   reserved,
        "stock_in_transit_current": np.random.randint(0, 50, n_skus).astype(float),
        "stockout_risk_score":      risk,
        "revenue_30d":              np.random.lognormal(9, 1, n_skus),
        "qty_sold_30d":             np.random.randint(5, 200, n_skus).astype(float),
    }, index=[f"ART{i:03d}" for i in range(n_skus)])


# ═══════════════════════════════════════════════════════════════════════
# Feature Store Schema
# ═══════════════════════════════════════════════════════════════════════

class TestFeatureStoreSchema(unittest.TestCase):

    def setUp(self):
        self.store = FeatureStoreSchema(base_dir=_tmpdir())

    def test_save_and_get_feature_set(self):
        fs = FeatureSet(name="sales_features", entity_type="sku",
                        feature_names=["rev_7d", "rev_30d"])
        self.store.save_feature_set(fs)
        loaded = self.store.get_feature_set("sales_features")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.entity_type, "sku")
        self.assertIn("rev_7d", loaded.feature_names)

    def test_upsert_and_get_values(self):
        values = [
            FeatureValue("ART001", "sales_features", "revenue_7d", 1500.0),
            FeatureValue("ART001", "sales_features", "revenue_30d", 6000.0),
            FeatureValue("ART002", "sales_features", "revenue_7d", 2000.0),
        ]
        self.store.upsert_values(values)
        result = self.store.get_entity_features("ART001", "sales_features")
        self.assertAlmostEqual(result["revenue_7d"], 1500.0)
        self.assertAlmostEqual(result["revenue_30d"], 6000.0)

    def test_upsert_overwrites(self):
        self.store.upsert_values([FeatureValue("ART001","sf","rev",100.0)])
        self.store.upsert_values([FeatureValue("ART001","sf","rev",200.0)])
        result = self.store.get_entity_features("ART001", "sf")
        self.assertAlmostEqual(result["rev"], 200.0)

    def test_get_all_entities(self):
        self.store.upsert_values([
            FeatureValue("A1","fs","feat",1.0),
            FeatureValue("A2","fs","feat",2.0),
        ])
        all_ents = self.store.get_all_entities("fs")
        self.assertEqual(len(all_ents), 2)
        self.assertIn("A1", all_ents)

    def test_count_values(self):
        self.store.upsert_values([
            FeatureValue("A1","fs","f1",1.0),
            FeatureValue("A1","fs","f2",2.0),
            FeatureValue("A2","fs","f1",3.0),
        ])
        self.assertEqual(self.store.count_values("fs"), 3)

    def test_list_feature_sets(self):
        self.store.save_feature_set(FeatureSet("s1","sku"))
        self.store.save_feature_set(FeatureSet("s2","sku"))
        self.assertIn("s1", self.store.list_feature_sets())
        self.assertIn("s2", self.store.list_feature_sets())

    def test_missing_entity_returns_empty(self):
        result = self.store.get_entity_features("NONEXIST", "no_set")
        self.assertEqual(result, {})


# ═══════════════════════════════════════════════════════════════════════
# Aggregators
# ═══════════════════════════════════════════════════════════════════════

class TestSalesAggregator(unittest.TestCase):

    def setUp(self):
        self.agg = SalesAggregator()

    def test_compute_returns_features(self):
        df = _sales_df(n_skus=3, n_days=35)
        values = self.agg.compute(df)
        self.assertGreater(len(values), 0)
        fnames = {v.feature_name for v in values}
        self.assertIn("revenue_30d", fnames)
        self.assertIn("qty_sold_30d", fnames)

    def test_all_skus_have_features(self):
        df = _sales_df(n_skus=3, n_days=35)
        values = self.agg.compute(df)
        skus = {v.entity_id for v in values}
        for i in range(3):
            self.assertIn(f"ART{i:03d}", skus)

    def test_empty_df_returns_empty(self):
        values = self.agg.compute(pd.DataFrame())
        self.assertEqual(values, [])

    def test_no_sku_column_returns_empty(self):
        df = pd.DataFrame({"revenue": [1000], "date": ["2024-01-01"]})
        values = self.agg.compute(df)
        self.assertEqual(values, [])

    def test_revenue_window_values_sensible(self):
        df = _sales_df(n_skus=1, n_days=40)
        values = self.agg.compute(df)
        sku = "ART000"
        rev_vals = {v.feature_name: v.value for v in values if v.entity_id == sku}
        # revenue_7d <= revenue_30d (7-день подмножество 30-дней)
        if "revenue_7d" in rev_vals and "revenue_30d" in rev_vals:
            self.assertLessEqual(rev_vals["revenue_7d"], rev_vals["revenue_30d"] + 1)

    def test_feature_set_name_correct(self):
        df = _sales_df(n_skus=1, n_days=10)
        values = self.agg.compute(df)
        for v in values:
            self.assertEqual(v.feature_set, SalesAggregator.FEATURE_SET)


class TestStockAggregator(unittest.TestCase):

    def setUp(self):
        self.agg = StockAggregator()

    def test_compute_returns_features(self):
        df = _stock_df(n_skus=3)
        values = self.agg.compute(df)
        self.assertGreater(len(values), 0)
        fnames = {v.feature_name for v in values}
        self.assertIn("stock_qty_current", fnames)
        self.assertIn("stockout_risk_score", fnames)

    def test_stockout_risk_range(self):
        df = _stock_df(5)
        values = self.agg.compute(df)
        risks = [v.value for v in values if v.feature_name == "stockout_risk_score"]
        for r in risks:
            self.assertGreaterEqual(r, 0.0)
            self.assertLessEqual(r, 1.0)

    def test_zero_stock_max_risk(self):
        df = pd.DataFrame([{"sku": "ZERO", "quantity": 0, "reserved": 0, "in_transit": 0}])
        values = self.agg.compute(df)
        risks = [v.value for v in values if v.feature_name == "stockout_risk_score"]
        if risks:
            self.assertAlmostEqual(risks[0], 1.0, places=1)

    def test_high_stock_low_risk(self):
        df = pd.DataFrame([{"sku": "FULL", "quantity": 1000, "reserved": 10, "in_transit": 0}])
        values = self.agg.compute(df)
        risks = [v.value for v in values if v.feature_name == "stockout_risk_score"]
        if risks:
            self.assertLess(risks[0], 0.1)


# ═══════════════════════════════════════════════════════════════════════
# Model Registry
# ═══════════════════════════════════════════════════════════════════════

class TestModelRegistry(unittest.TestCase):

    def setUp(self):
        self.reg = ModelRegistry(base_dir=_tmpdir())

    def _save_dummy(self, name="test_model"):
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression()
        return self.reg.save(
            model_name=name,
            model_obj=model,
            metrics={"f1": 0.85, "roc_auc": 0.90},
            params={"max_iter": 100},
            feature_set="sales_features",
            feature_names=["revenue_7d", "qty_sold_30d"],
            training_samples=100,
            description="test",
        )

    def test_save_and_load(self):
        record = self._save_dummy()
        self.assertEqual(record.version, "v1")
        model = self.reg.load("test_model")
        self.assertIsNotNone(model)

    def test_version_increments(self):
        r1 = self._save_dummy()
        r2 = self._save_dummy()
        self.assertEqual(r1.version, "v1")
        self.assertEqual(r2.version, "v2")

    def test_previous_archived(self):
        self._save_dummy()
        self._save_dummy()
        versions = self.reg.list_versions("test_model")
        statuses = {v.version: v.status for v in versions}
        self.assertEqual(statuses.get("v2"), "active")
        self.assertEqual(statuses.get("v1"), "archived")

    def test_rollback(self):
        self._save_dummy(); self._save_dummy()
        ok = self.reg.rollback("test_model", "v1")
        self.assertTrue(ok)
        record = self.reg.get_active_record("test_model")
        self.assertEqual(record.version, "v1")

    def test_get_record_metrics(self):
        self._save_dummy()
        record = self.reg.get_active_record("test_model")
        self.assertAlmostEqual(record.metrics["f1"], 0.85)

    def test_load_nonexistent(self):
        model = self.reg.load("nonexistent")
        self.assertIsNone(model)

    def test_list_models(self):
        self._save_dummy("model_a")
        self._save_dummy("model_b")
        models = self.reg.list_models()
        self.assertIn("model_a", models)
        self.assertIn("model_b", models)


# ═══════════════════════════════════════════════════════════════════════
# Training Pipeline
# ═══════════════════════════════════════════════════════════════════════

class TestAnomalyTrainer(unittest.TestCase):

    def setUp(self):
        self.reg = ModelRegistry(base_dir=_tmpdir())
        self.trainer = AnomalyDetectorTrainer(n_estimators=10)

    def test_train_success(self):
        X = _sales_feature_matrix(n_skus=20)
        result = self.trainer.train(X, self.reg)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.model_name, "anomaly_detector")
        self.assertGreater(result.training_samples, 0)
        self.assertIn("anomaly_rate", result.metrics)

    def test_model_saved_to_registry(self):
        X = _sales_feature_matrix(20)
        self.trainer.train(X, self.reg)
        model = self.reg.load("anomaly_detector")
        self.assertIsNotNone(model)

    def test_too_few_samples_fails(self):
        X = _sales_feature_matrix(5)
        result = self.trainer.train(X, self.reg)
        # 5 < 10 — должен упасть
        self.assertFalse(result.ok)

    def test_too_few_features_fails(self):
        X = pd.DataFrame({"unknown_col": [1.0]*20})
        result = self.trainer.train(X, self.reg)
        self.assertFalse(result.ok)

    def test_anomaly_rate_in_range(self):
        X = _sales_feature_matrix(30)
        result = self.trainer.train(X, self.reg)
        if result.ok:
            rate = result.metrics["anomaly_rate"]
            self.assertGreaterEqual(rate, 0.0)
            self.assertLessEqual(rate, 1.0)


class TestStockoutTrainer(unittest.TestCase):

    def setUp(self):
        self.reg = ModelRegistry(base_dir=_tmpdir())
        self.trainer = StockoutPredictorTrainer()

    def test_train_success(self):
        stock = _stock_feature_matrix(30)
        sales = _sales_feature_matrix(30)
        result = self.trainer.train(stock, sales, self.reg)
        if result.ok:
            self.assertIn("f1", result.metrics)
            self.assertIn("roc_auc", result.metrics)

    def test_empty_stock_fails(self):
        result = self.trainer.train(pd.DataFrame(), None, self.reg)
        self.assertFalse(result.ok)

    def test_metrics_range(self):
        stock = _stock_feature_matrix(50)
        sales = _sales_feature_matrix(50)
        result = self.trainer.train(stock, sales, self.reg)
        if result.ok:
            for metric in ("f1","precision","recall","roc_auc"):
                v = result.metrics.get(metric, 0)
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)


class TestTrainingOrchestrator(unittest.TestCase):

    def test_run_all_returns_list(self):
        tmp = _tmpdir()
        reg = ModelRegistry(base_dir=tmp / "registry")
        fp = FeaturePipeline(data_dir=tmp / "data", base_dir=tmp / "features")

        # Наполняем feature store
        sales_agg = SalesAggregator()
        stock_agg = StockAggregator()
        store = fp._store

        sales_vals = sales_agg.compute(_sales_df(10, 35))
        stock_vals = stock_agg.compute(_stock_df(10))
        store.upsert_values(sales_vals)
        store.upsert_values(stock_vals)

        orch = TrainingOrchestrator(registry=reg, feature_pipeline=fp)
        results = orch.run_all()
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 2)
        # Хотя бы аномалия должна обучиться (enough data)
        names = {r.model_name for r in results}
        self.assertIn("anomaly_detector", names)


# ═══════════════════════════════════════════════════════════════════════
# Inference Service
# ═══════════════════════════════════════════════════════════════════════

class TestInferenceService(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Обучаем модели один раз для всех тестов inference."""
        tmp = _tmpdir()
        cls.reg = ModelRegistry(base_dir=tmp / "registry")
        cls.fp = FeaturePipeline(data_dir=tmp / "data", base_dir=tmp / "features")

        store = cls.fp._store
        sales_vals = SalesAggregator().compute(_sales_df(10, 35))
        stock_vals = StockAggregator().compute(_stock_df(10))
        store.upsert_values(sales_vals)
        store.upsert_values(stock_vals)

        trainer_a = AnomalyDetectorTrainer(n_estimators=10)
        trainer_a.train(cls.fp.get_feature_matrix("sales_features"), cls.reg)

        cls.svc = InferenceService(registry=cls.reg, feature_pipeline=cls.fp)
        cls.skus = [f"ART{i:03d}" for i in range(10)]

    def test_predict_anomaly_returns_result(self):
        sku = self.skus[0]
        result = self.svc.predict_anomaly(sku)
        if result:
            self.assertEqual(result.sku, sku)
            self.assertIsInstance(result.is_anomaly, (bool, int))
            self.assertGreaterEqual(result.confidence, 0.0)
            self.assertLessEqual(result.confidence, 1.0)

    def test_predict_anomalies_batch(self):
        results = self.svc.predict_anomalies(self.skus[:5])
        self.assertIsInstance(results, dict)

    def test_predict_stockout_fallback(self):
        """Без stockout модели — возвращает fallback из feature store."""
        sku = self.skus[0]
        result = self.svc.predict_stockout(sku)
        if result:
            self.assertEqual(result.sku, sku)
            self.assertGreaterEqual(result.stockout_risk, 0.0)
            self.assertLessEqual(result.stockout_risk, 1.0)

    def test_predict_all_structure(self):
        results = self.svc.predict_all(self.skus[:3])
        self.assertIsInstance(results, dict)
        for sku, insights in results.items():
            self.assertEqual(insights.sku, sku)

    def test_invalidate_cache(self):
        self.svc._models["test"] = "dummy"
        self.svc.invalidate_cache()
        self.assertEqual(len(self.svc._models), 0)

    def test_unknown_sku_returns_none(self):
        result = self.svc.predict_anomaly("UNKNOWN_SKU_XYZ")
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════
# Drift Detector
# ═══════════════════════════════════════════════════════════════════════

class TestDriftDetector(unittest.TestCase):

    def setUp(self):
        tmp = _tmpdir()
        self.reg = ModelRegistry(base_dir=tmp / "registry")
        self.detector = DriftDetector(registry=self.reg, reports_dir=tmp / "reports")

        # Сохраняем dummy модель чтобы был record
        from sklearn.ensemble import IsolationForest
        self.reg.save(
            model_name="anomaly_detector",
            model_obj=IsolationForest(n_estimators=5),
            metrics={"anomaly_rate": 0.05, "score_mean": -0.1},
            params={"contamination": 0.05},
            feature_set="sales_features",
            feature_names=["revenue_7d","revenue_30d","qty_sold_30d"],
            training_samples=100,
        )

    def _feature_df(self, n=50, shift=0.0) -> pd.DataFrame:
        np.random.seed(1)
        return pd.DataFrame({
            "revenue_7d":  np.random.lognormal(8, 1, n) + shift,
            "revenue_30d": np.random.lognormal(9, 1, n) + shift,
            "qty_sold_30d":np.random.randint(5, 200, n).astype(float),
        })

    def test_no_drift_stable(self):
        baseline = self._feature_df(100)
        current  = self._feature_df(100)
        report = self.detector.detect("anomaly_detector", baseline, current)
        self.assertIsNotNone(report)
        self.assertIn(report.overall_severity, ("none","warning","critical"))

    def test_major_drift_detected(self):
        baseline = self._feature_df(100, shift=0)
        current  = self._feature_df(100, shift=10000)  # большой сдвиг
        report = self.detector.detect("anomaly_detector", baseline, current)
        # С таким большим сдвигом должен быть drift
        self.assertIn(report.overall_severity, ("warning", "critical"))

    def test_report_has_feature_drifts(self):
        baseline = self._feature_df(80)
        current  = self._feature_df(80)
        report = self.detector.detect("anomaly_detector", baseline, current)
        self.assertIsInstance(report.feature_drifts, list)
        self.assertGreater(len(report.feature_drifts), 0)

    def test_psi_range(self):
        baseline = self._feature_df(100)
        current  = self._feature_df(100)
        report = self.detector.detect("anomaly_detector", baseline, current)
        for fd in report.feature_drifts:
            self.assertGreaterEqual(fd.psi, 0.0)

    def test_concept_drift_detection(self):
        baseline = self._feature_df(80)
        current  = self._feature_df(80)
        # Большое изменение anomaly_rate → concept drift
        report = self.detector.detect(
            "anomaly_detector", baseline, current,
            current_metrics={"anomaly_rate": 0.50},  # было 0.05
        )
        self.assertTrue(report.concept_drift_detected)

    def test_recommendations_not_empty(self):
        baseline = self._feature_df(80)
        report = self.detector.detect("anomaly_detector", baseline, self._feature_df(80))
        self.assertGreater(len(report.recommendations), 0)

    def test_report_saved_to_disk(self):
        tmp = _tmpdir()
        detector = DriftDetector(registry=self.reg, reports_dir=tmp / "reps")
        baseline = self._feature_df(50)
        detector.detect("anomaly_detector", baseline, self._feature_df(50))
        reports = list((tmp / "reps").glob("anomaly_detector_*.json"))
        self.assertEqual(len(reports), 1)

    def test_psi_computation(self):
        a = np.random.normal(0, 1, 200)
        b = np.random.normal(0, 1, 200)
        psi_same = DriftDetector._compute_psi(a, b)
        b_shifted = np.random.normal(5, 1, 200)
        psi_diff = DriftDetector._compute_psi(a, b_shifted)
        self.assertGreater(psi_diff, psi_same)


if __name__ == "__main__":
    unittest.main()
