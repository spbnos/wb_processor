"""
db/models.py — минимальная заглушка.

Этот пакет отсутствовал в репозитории (не закоммичен ранее), хотя
mapping/mapping_repository.py импортирует из него `Mapping` как тип
для аннотаций (`-> Optional[Mapping]`, `list[Mapping]`). Реальные операции
выполняются через mapping.mapping_storage.MappingObj (use_db=False режим),
полноценная SQLAlchemy ORM-модель здесь не требуется и не создаётся —
это не входит в задачу аудита РК, не лезем в архитектуру БД без отдельного
запроса. Алиас существует только чтобы цепочка импортов
api.deps → mapping.mapping_storage → mapping.mapping_repository
не падала при старте FastAPI.
"""
from mapping.mapping_storage import MappingObj as Mapping  # noqa: F401
