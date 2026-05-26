"""
MappingStorage — хранение и загрузка маппингов.

Основное хранилище: PostgreSQL (через SQLAlchemy).
Fallback / offline: JSON-файл (для работы без БД / тестов).

Публичный API:
    storage.save(config)                  → MappingObj
    storage.find_by_struct_hash(hash)     → Optional[MappingObj]
    storage.get_all()                     → list[MappingObj]
    storage.get_by_id(id)                 → Optional[MappingObj]
    storage.update(mapping_id, **kwargs)  → Optional[MappingObj]
    storage.delete(mapping_id)            → bool
    storage.export_json(path)             → Path
    storage.import_json(path)             → int
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from mapping.interactive_mapper import MappingConfig, FieldMapping

logger = logging.getLogger(__name__)

_DEFAULT_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "mappings.json"


# ─────────────────────────────────────────────────────────
# Переносимый объект маппинга (работает без SQLAlchemy)
# ─────────────────────────────────────────────────────────
@dataclass
class MappingFieldObj:
    source_column: str
    target_field: str
    data_type: str
    date_format: Optional[str] = None
    is_required: bool = False
    description: Optional[str] = None
    mapping_id: int = 0
    id: int = 0


@dataclass
class MappingObj:
    id: int
    name: str
    struct_hash: str
    category: str
    subcategory: Optional[str]
    purpose: Optional[str]
    column_count: Optional[int]
    raw_columns: Optional[list]
    notes: Optional[str]
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]
    fields: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────
# Конвертеры
# ─────────────────────────────────────────────────────────
def _config_to_dict(config: MappingConfig, id: int, now: str) -> dict:
    return {
        "id": id,
        "name": config.name,
        "struct_hash": config.struct_hash,
        "category": config.category,
        "subcategory": config.subcategory,
        "purpose": config.purpose,
        "column_count": config.column_count,
        "raw_columns": config.raw_columns,
        "notes": config.notes,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "fields": [
            {
                "source_column": f.source_column,
                "target_field": f.target_field,
                "data_type": f.data_type,
                "date_format": f.date_format,
                "is_required": f.is_required,
                "description": f.description,
            }
            for f in config.fields
        ],
    }


def _dict_to_obj(d: dict) -> MappingObj:
    fields = [
        MappingFieldObj(
            source_column=f["source_column"],
            target_field=f["target_field"],
            data_type=f["data_type"],
            date_format=f.get("date_format"),
            is_required=f.get("is_required", False),
            description=f.get("description"),
            mapping_id=d.get("id", 0),
        )
        for f in d.get("fields", [])
    ]
    return MappingObj(
        id=d.get("id", 0),
        name=d["name"],
        struct_hash=d["struct_hash"],
        category=d.get("category", ""),
        subcategory=d.get("subcategory"),
        purpose=d.get("purpose"),
        column_count=d.get("column_count"),
        raw_columns=d.get("raw_columns"),
        notes=d.get("notes"),
        is_active=d.get("is_active", True),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
        fields=fields,
    )


def _dict_to_config(d: dict) -> MappingConfig:
    fields = [
        FieldMapping(
            source_column=f["source_column"],
            target_field=f["target_field"],
            data_type=f["data_type"],
            date_format=f.get("date_format"),
            is_required=f.get("is_required", False),
            description=f.get("description"),
        )
        for f in d.get("fields", [])
    ]
    return MappingConfig(
        name=d["name"],
        struct_hash=d["struct_hash"],
        category=d.get("category", ""),
        subcategory=d.get("subcategory", ""),
        purpose=d.get("purpose", ""),
        raw_columns=d.get("raw_columns", []),
        column_count=d.get("column_count", 0),
        fields=fields,
        notes=d.get("notes"),
    )


# ─────────────────────────────────────────────────────────
# MappingStorage
# ─────────────────────────────────────────────────────────
class MappingStorage:
    """
    use_db=True  → PostgreSQL (требует psycopg2 и живую БД)
    use_db=False → JSON-файл  (работает везде, без БД)
    """

    def __init__(self, use_db: bool = True, json_path: Path = _DEFAULT_JSON_PATH):
        self._use_db = use_db
        self._json_path = json_path
        if not use_db:
            self._json_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info("[storage] JSON mode.")

    # ── SAVE ─────────────────────────────────────────────

    def save(self, config: MappingConfig) -> Optional[MappingObj]:
        if self._use_db:
            return self._save_db(config)
        return self._save_json(config)

    def _save_db(self, config: MappingConfig) -> Optional[MappingObj]:
        from db.database import SessionLocal
        from db.models import Mapping, MappingField
        from sqlalchemy.exc import IntegrityError

        with SessionLocal() as db:
            existing = db.query(Mapping).filter_by(struct_hash=config.struct_hash).first()
            if existing:
                logger.info(f"[storage] Already exists: '{existing.name}'")
                return self._orm_to_obj(existing)

            mapping = Mapping(
                name=config.name, struct_hash=config.struct_hash,
                category=config.category, subcategory=config.subcategory,
                purpose=config.purpose, column_count=config.column_count,
                raw_columns=config.raw_columns, notes=config.notes, is_active=True,
            )
            for fm in config.fields:
                mapping.fields.append(MappingField(
                    source_column=fm.source_column, target_field=fm.target_field,
                    data_type=fm.data_type, date_format=fm.date_format,
                    is_required=fm.is_required, description=fm.description,
                ))
            db.add(mapping)
            try:
                db.commit()
                db.refresh(mapping)
                logger.info(f"[storage] Saved: '{mapping.name}' id={mapping.id}")
                return self._orm_to_obj(mapping)
            except IntegrityError:
                db.rollback()
                existing = db.query(Mapping).filter_by(struct_hash=config.struct_hash).first()
                return self._orm_to_obj(existing) if existing else None

    def _save_json(self, config: MappingConfig) -> MappingObj:
        data = self._load_raw()
        for item in data:
            if item["struct_hash"] == config.struct_hash:
                logger.info(f"[storage][json] Already exists: '{item['name']}'")
                return _dict_to_obj(item)

        new_id = max((d.get("id", 0) for d in data), default=0) + 1
        now = datetime.utcnow().isoformat()
        entry = _config_to_dict(config, new_id, now)
        data.append(entry)
        self._save_raw(data)
        logger.info(f"[storage][json] Saved: '{config.name}' id={new_id}")
        return _dict_to_obj(entry)

    # ── FIND ─────────────────────────────────────────────

    def find_by_struct_hash(self, struct_hash: str) -> Optional[MappingObj]:
        if self._use_db:
            from db.database import SessionLocal
            from db.models import Mapping
            with SessionLocal() as db:
                m = db.query(Mapping).filter_by(struct_hash=struct_hash, is_active=True).first()
                return self._orm_to_obj(m) if m else None
        for item in self._load_raw():
            if item["struct_hash"] == struct_hash and item.get("is_active", True):
                return _dict_to_obj(item)
        return None

    def get_by_id(self, mapping_id: int) -> Optional[MappingObj]:
        if self._use_db:
            from db.database import SessionLocal
            from db.models import Mapping
            with SessionLocal() as db:
                m = db.query(Mapping).filter_by(id=mapping_id).first()
                return self._orm_to_obj(m) if m else None
        for item in self._load_raw():
            if item["id"] == mapping_id:
                return _dict_to_obj(item)
        return None

    def get_all(self, active_only: bool = True) -> list[MappingObj]:
        if self._use_db:
            from db.database import SessionLocal
            from db.models import Mapping
            with SessionLocal() as db:
                q = db.query(Mapping)
                if active_only:
                    q = q.filter_by(is_active=True)
                return [self._orm_to_obj(m) for m in q.order_by(Mapping.created_at.desc()).all()]
        raw = self._load_raw()
        if active_only:
            raw = [d for d in raw if d.get("is_active", True)]
        return [_dict_to_obj(d) for d in raw]

    def get_fields(self, mapping_id: int) -> list[MappingFieldObj]:
        m = self.get_by_id(mapping_id)
        return m.fields if m else []

    # ── UPDATE ───────────────────────────────────────────

    def update(self, mapping_id: int, **kwargs) -> Optional[MappingObj]:
        allowed = {"name", "category", "subcategory", "purpose", "notes", "is_active"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if self._use_db:
            from db.database import SessionLocal
            from db.models import Mapping, MappingField
            with SessionLocal() as db:
                mapping = db.query(Mapping).filter_by(id=mapping_id).first()
                if not mapping:
                    return None
                for k, v in updates.items():
                    setattr(mapping, k, v)
                mapping.updated_at = datetime.utcnow()
                if "fields" in kwargs:
                    db.query(MappingField).filter_by(mapping_id=mapping_id).delete()
                    for fm in kwargs["fields"]:
                        db.add(MappingField(
                            mapping_id=mapping_id,
                            source_column=fm.source_column, target_field=fm.target_field,
                            data_type=fm.data_type, date_format=fm.date_format,
                            is_required=fm.is_required, description=fm.description,
                        ))
                db.commit()
                db.refresh(mapping)
                return self._orm_to_obj(mapping)

        data = self._load_raw()
        for item in data:
            if item["id"] == mapping_id:
                for k, v in updates.items():
                    item[k] = v
                item["updated_at"] = datetime.utcnow().isoformat()
                if "fields" in kwargs:
                    item["fields"] = [
                        {
                            "source_column": f.source_column, "target_field": f.target_field,
                            "data_type": f.data_type, "date_format": f.date_format,
                            "is_required": f.is_required, "description": f.description,
                        }
                        for f in kwargs["fields"]
                    ]
                self._save_raw(data)
                return _dict_to_obj(item)
        return None

    # ── DELETE ───────────────────────────────────────────

    def delete(self, mapping_id: int, hard: bool = False) -> bool:
        if self._use_db:
            from db.database import SessionLocal
            from db.models import Mapping
            with SessionLocal() as db:
                mapping = db.query(Mapping).filter_by(id=mapping_id).first()
                if not mapping:
                    return False
                if hard:
                    db.delete(mapping)
                else:
                    mapping.is_active = False
                    mapping.updated_at = datetime.utcnow()
                db.commit()
                return True

        data = self._load_raw()
        for i, item in enumerate(data):
            if item["id"] == mapping_id:
                if hard:
                    data.pop(i)
                else:
                    item["is_active"] = False
                self._save_raw(data)
                return True
        return False

    # ── EXPORT / IMPORT ──────────────────────────────────

    def export_json(self, path: Path = None) -> Path:
        out = path or self._json_path
        out.parent.mkdir(parents=True, exist_ok=True)
        if self._use_db:
            data = [self._obj_to_dict(m) for m in self.get_all(active_only=False)]
        else:
            data = self._load_raw()
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[storage] Exported {len(data)} mappings → {out}")
        return out

    def import_json(self, path: Path) -> int:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        count = 0
        for d in data:
            if self.find_by_struct_hash(d["struct_hash"]):
                logger.debug(f"[storage] Skip duplicate: '{d['name']}'")
                continue
            self.save(_dict_to_config(d))
            count += 1
        logger.info(f"[storage] Imported {count} new mappings from {path}")
        return count

    # ── Helpers ──────────────────────────────────────────

    def _load_raw(self) -> list[dict]:
        if not self._json_path.exists():
            return []
        try:
            with open(self._json_path, encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else []
        except (json.JSONDecodeError, ValueError):
            return []

    def _save_raw(self, data: list[dict]):
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _orm_to_obj(m) -> MappingObj:
        """Конвертирует SQLAlchemy ORM объект → MappingObj."""
        fields = [
            MappingFieldObj(
                id=f.id if hasattr(f, "id") else 0,
                source_column=f.source_column,
                target_field=f.target_field,
                data_type=f.data_type,
                date_format=f.date_format,
                is_required=f.is_required,
                description=f.description,
                mapping_id=f.mapping_id if hasattr(f, "mapping_id") else 0,
            )
            for f in (m.fields or [])
        ]
        return MappingObj(
            id=m.id,
            name=m.name,
            struct_hash=m.struct_hash,
            category=m.category,
            subcategory=m.subcategory,
            purpose=m.purpose,
            column_count=m.column_count,
            raw_columns=m.raw_columns,
            notes=m.notes,
            is_active=m.is_active,
            created_at=str(m.created_at) if m.created_at else None,
            updated_at=str(m.updated_at) if m.updated_at else None,
            fields=fields,
        )

    @staticmethod
    def _obj_to_dict(m: MappingObj) -> dict:
        return {
            "id": m.id, "name": m.name, "struct_hash": m.struct_hash,
            "category": m.category, "subcategory": m.subcategory,
            "purpose": m.purpose, "column_count": m.column_count,
            "raw_columns": m.raw_columns, "notes": m.notes,
            "is_active": m.is_active, "created_at": m.created_at, "updated_at": m.updated_at,
            "fields": [
                {
                    "source_column": f.source_column, "target_field": f.target_field,
                    "data_type": f.data_type, "date_format": f.date_format,
                    "is_required": f.is_required, "description": f.description,
                }
                for f in m.fields
            ],
        }
