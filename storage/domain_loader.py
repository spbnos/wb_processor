"""
storage/domain_loader.py — загружает DomainParseResult в data/loaded/{table}.json.
Дедупликация: при повторной обработке файла — заменяем старые записи этого файла.
"""
from __future__ import annotations
import json, logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import pandas as pd
from parsers.domain.base_domain_parser import DomainParseResult
logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "loaded"
_KNOWN = {"transactions","weekly_reports","ad_costs","warehouse_stocks",
          "supply_recommendations","returns","price_templates","paid_storage",
          "product_catalog","wb_commissions","product_ratings"}

@dataclass
class DomainLoadResult:
    filepath:      Path
    db_table:      str
    domain:        str
    rows_total:    int
    rows_written:  int
    rows_replaced: int
    ok:            bool = True
    errors:        list[str] = field(default_factory=list)

class DomainLoader:
    def __init__(self, use_db: bool = False, data_dir: Optional[Path] = None):
        self.use_db   = use_db
        self.data_dir = data_dir or _DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load(self, result: DomainParseResult, file_id: int = 0) -> DomainLoadResult:
        if not result.ok or result.df is None or result.df.empty:
            return DomainLoadResult(filepath=result.filepath,db_table=result.db_table,
                domain=result.domain,rows_total=0,rows_written=0,rows_replaced=0,ok=False,
                errors=[f"Empty/failed parse: {result.filepath.name}"])
        return self._load_json(result, file_id)

    def _load_json(self, result: DomainParseResult, file_id: int) -> DomainLoadResult:
        # Reference tables go to data/ root for direct access by API
        _REF_TABLES = {"wb_commissions"}
        if result.db_table in _REF_TABLES:
            table_path = self.data_dir.parent / f"{result.db_table}.json"
        else:
            table_path = self.data_dir / f"{result.db_table}.json"
        source_key = result.filepath.name
        existing: list[dict] = []
        if table_path.exists():
            try: existing = json.loads(table_path.read_bytes())
            except Exception: existing = []
        before = len(existing)
        existing = [r for r in existing if r.get("_source_file") != source_key]
        replaced = before - len(existing)
        df = result.df.copy()
        now = datetime.now(timezone.utc).isoformat()
        df["_source_file"] = source_key
        df["_file_id"]     = file_id
        df["_loaded_at"]   = now
        df["_domain"]      = result.domain
        if result.period_from: df["_period_from"] = result.period_from
        if result.period_to:   df["_period_to"]   = result.period_to
        new_records = json.loads(df.to_json(orient="records",date_format="iso",force_ascii=False))
        combined = existing + new_records
        table_path.write_text(json.dumps(combined,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        logger.info(f"[domain_loader] {result.db_table}: +{len(new_records)} rows (replaced {replaced}). Total: {len(combined)}")
        return DomainLoadResult(filepath=result.filepath,db_table=result.db_table,domain=result.domain,
            rows_total=len(new_records),rows_written=len(new_records),rows_replaced=replaced,ok=True)
