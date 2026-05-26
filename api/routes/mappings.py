"""
routes/mappings.py — CRUD маппингов.

GET    /mappings            — список всех
GET    /mappings/{id}       — детали + поля
PUT    /mappings/{id}       — обновить (name, category, notes)
DELETE /mappings/{id}       — мягкое удаление
GET    /mappings/export     — скачать JSON дамп
POST   /mappings/import     — загрузить JSON дамп
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from api.auth import require_auth
from api.deps import get_storage
from mapping.mapping_storage import MappingStorage
from mapping.mapping_repository import MappingRepository

router = APIRouter(prefix="/mappings", tags=["mappings"])


class MappingListItem(BaseModel):
    id: int
    name: str
    category: str
    subcategory: Optional[str]
    column_count: Optional[int]
    struct_hash: str
    is_active: bool


class MappingDetail(MappingListItem):
    purpose: Optional[str]
    notes: Optional[str]
    raw_columns: Optional[list]
    fields: list[dict]


class MappingUpdateRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None


class StatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    by_category: dict[str, int]


@router.get("", response_model=list[MappingListItem])
async def list_mappings(
    active_only: bool = True,
    category: Optional[str] = None,
    _auth: dict = Depends(require_auth),
    storage: MappingStorage = Depends(get_storage),
):
    """Список всех маппингов с опциональным фильтром."""
    repo = MappingRepository(storage)
    items = repo.summary_list()
    if active_only:
        items = [i for i in items if i["active"]]
    if category:
        items = [i for i in items if i["category"] == category]
    return [MappingListItem(
        id=i["id"], name=i["name"], category=i["category"],
        subcategory=i["subcategory"], column_count=i["columns"],
        struct_hash=i["struct_hash"], is_active=i["active"],
    ) for i in items]


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    _auth: dict = Depends(require_auth),
    storage: MappingStorage = Depends(get_storage),
):
    repo = MappingRepository(storage)
    s = repo.stats()
    return StatsResponse(**s)


@router.get("/{mapping_id}", response_model=MappingDetail)
async def get_mapping(
    mapping_id: int,
    _auth: dict = Depends(require_auth),
    storage: MappingStorage = Depends(get_storage),
):
    m = storage.get_by_id(mapping_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"Mapping {mapping_id} not found")

    fields = [
        {
            "source_column": f.source_column,
            "target_field": f.target_field,
            "data_type": f.data_type,
            "date_format": f.date_format,
            "is_required": f.is_required,
        }
        for f in m.fields
    ]
    return MappingDetail(
        id=m.id, name=m.name, category=m.category,
        subcategory=m.subcategory, column_count=m.column_count,
        struct_hash=m.struct_hash, is_active=m.is_active,
        purpose=m.purpose, notes=m.notes,
        raw_columns=m.raw_columns, fields=fields,
    )


@router.put("/{mapping_id}", response_model=MappingDetail)
async def update_mapping(
    mapping_id: int,
    body: MappingUpdateRequest,
    _auth: dict = Depends(require_auth),
    storage: MappingStorage = Depends(get_storage),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = storage.update(mapping_id, **updates)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Mapping {mapping_id} not found")

    return await get_mapping(mapping_id, _auth, storage)


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: int,
    hard: bool = False,
    _auth: dict = Depends(require_auth),
    storage: MappingStorage = Depends(get_storage),
):
    ok = storage.delete(mapping_id, hard=hard)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Mapping {mapping_id} not found")


@router.get("/export/json")
async def export_mappings(
    _auth: dict = Depends(require_auth),
    storage: MappingStorage = Depends(get_storage),
):
    """Возвращает все маппинги как JSON (для бэкапа и переноса)."""
    all_m = storage.get_all(active_only=False)
    return {"count": len(all_m), "mappings": [
        {
            "id": m.id, "name": m.name, "struct_hash": m.struct_hash,
            "category": m.category, "subcategory": m.subcategory,
        }
        for m in all_m
    ]}
