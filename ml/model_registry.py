"""
ml/model_registry.py — реестр ML моделей.

Хранит версии обученных моделей:
  - сериализованный объект (joblib)
  - метрики качества
  - параметры обучения
  - статус: active / archived / failed

Rollback: set_active(model_name, version)
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib

logger = logging.getLogger(__name__)

_REGISTRY_DIR = Path(__file__).resolve().parent.parent / "data" / "model_registry"


@dataclass
class ModelRecord:
    model_name: str          # "anomaly_detector", "stockout_predictor"
    version: str             # "v1", "v2", ...
    status: str              # "active", "archived", "failed"
    metrics: dict            # {"f1": 0.87, "precision": 0.91, ...}
    params: dict             # гиперпараметры
    feature_set: str         # какой feature_set использовался
    feature_names: list[str]
    training_samples: int
    trained_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    description: str = ""


class ModelRegistry:
    """
    Файловый реестр моделей.

    Структура:
        data/model_registry/
            {model_name}/
                v1/
                    model.joblib
                    record.json
                v2/
                    ...
                active.txt   ← имя активной версии
    """

    def __init__(self, base_dir: Path = _REGISTRY_DIR):
        self._base = base_dir
        self._base.mkdir(parents=True, exist_ok=True)

    # ── Save ──────────────────────────────────────────────

    def save(
        self,
        model_name: str,
        model_obj: Any,
        metrics: dict,
        params: dict,
        feature_set: str,
        feature_names: list[str],
        training_samples: int,
        description: str = "",
    ) -> ModelRecord:
        """Сохраняет новую версию модели."""
        version = self._next_version(model_name)
        model_dir = self._base / model_name / version
        model_dir.mkdir(parents=True, exist_ok=True)

        # Сериализуем модель
        joblib.dump(model_obj, model_dir / "model.joblib")

        record = ModelRecord(
            model_name=model_name,
            version=version,
            status="active",
            metrics=metrics,
            params=params,
            feature_set=feature_set,
            feature_names=feature_names,
            training_samples=training_samples,
            description=description,
        )

        # Сохраняем метаданные
        (model_dir / "record.json").write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Архивируем предыдущую активную версию
        prev = self._get_active_version(model_name)
        if prev and prev != version:
            self._set_version_status(model_name, prev, "archived")

        # Делаем новую версию активной
        (self._base / model_name / "active.txt").write_text(version)

        logger.info(
            f"[registry] Saved {model_name} {version} "
            f"metrics={metrics} samples={training_samples}"
        )
        return record

    # ── Load ──────────────────────────────────────────────

    def load(self, model_name: str, version: Optional[str] = None) -> Optional[Any]:
        """Загружает модель. version=None → активная."""
        v = version or self._get_active_version(model_name)
        if not v:
            logger.warning(f"[registry] No active version for {model_name}")
            return None

        model_path = self._base / model_name / v / "model.joblib"
        if not model_path.exists():
            logger.warning(f"[registry] Model file not found: {model_path}")
            return None

        model = joblib.load(model_path)
        logger.info(f"[registry] Loaded {model_name} {v}")
        return model

    def get_record(self, model_name: str, version: Optional[str] = None) -> Optional[ModelRecord]:
        """Метаданные версии."""
        v = version or self._get_active_version(model_name)
        if not v:
            return None
        record_path = self._base / model_name / v / "record.json"
        if not record_path.exists():
            return None
        data = json.loads(record_path.read_text(encoding="utf-8"))
        return ModelRecord(**data)

    # ── Rollback ──────────────────────────────────────────

    def rollback(self, model_name: str, to_version: str) -> bool:
        """Откатывается к указанной версии."""
        record_path = self._base / model_name / to_version / "record.json"
        if not record_path.exists():
            logger.error(f"[registry] Version {to_version} not found for {model_name}")
            return False

        current = self._get_active_version(model_name)
        if current:
            self._set_version_status(model_name, current, "archived")

        (self._base / model_name / "active.txt").write_text(to_version)
        self._set_version_status(model_name, to_version, "active")
        logger.warning(f"[registry] Rollback {model_name}: {current} → {to_version}")
        return True

    # ── List ──────────────────────────────────────────────

    def list_models(self) -> list[str]:
        return [
            d.name for d in self._base.iterdir()
            if d.is_dir()
        ]

    def list_versions(self, model_name: str) -> list[ModelRecord]:
        model_dir = self._base / model_name
        if not model_dir.exists():
            return []
        records = []
        for v_dir in sorted(model_dir.iterdir()):
            if v_dir.is_dir() and (v_dir / "record.json").exists():
                data = json.loads((v_dir / "record.json").read_text())
                records.append(ModelRecord(**data))
        return records

    def get_active_record(self, model_name: str) -> Optional[ModelRecord]:
        return self.get_record(model_name)

    # ── Helpers ───────────────────────────────────────────

    def _get_active_version(self, model_name: str) -> Optional[str]:
        active_file = self._base / model_name / "active.txt"
        if active_file.exists():
            return active_file.read_text().strip()
        return None

    def _next_version(self, model_name: str) -> str:
        versions = [
            d.name for d in (self._base / model_name).iterdir()
            if d.is_dir()
        ] if (self._base / model_name).exists() else []

        nums = [
            int(v[1:]) for v in versions
            if v.startswith("v") and v[1:].isdigit()
        ]
        next_num = max(nums, default=0) + 1
        return f"v{next_num}"

    def _set_version_status(self, model_name: str, version: str, status: str):
        record_path = self._base / model_name / version / "record.json"
        if record_path.exists():
            data = json.loads(record_path.read_text())
            data["status"] = status
            record_path.write_text(json.dumps(data, indent=2))
