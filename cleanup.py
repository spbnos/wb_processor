import sys, json
from pathlib import Path
sys.path.insert(0, '.')
from mapping.mapping_storage import MappingStorage
s = MappingStorage(use_db=False)
# Удаляем все авто-маппинги с неправильной категорией
deleted = 0
for m in s.get_all(active_only=False):
    if m.name.startswith('auto:') or m.name in ['Gone','Import Test','List Test','Show Test','Pipeline Test']:
        s.delete(m.id, hard=True)
        print('Deleted: ' + m.name)
        deleted += 1
print('Total deleted: ' + str(deleted))
# Очищаем transactions (тестовые данные)
tx = Path('data/loaded/transactions.json')
tx.write_text('[]', encoding='utf-8')
print('transactions.json cleared')
