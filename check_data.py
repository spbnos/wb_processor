import json, sys
from pathlib import Path
sys.path.insert(0, '.')

for name in ['transactions.json', 'products.json', 'stocks.json']:
    p = Path('data/loaded') / name
    if p.exists():
        data = json.loads(p.read_text(encoding='utf-8'))
        print(name + ': ' + str(len(data)) + ' records')
        if data:
            print('  keys: ' + str(list(data[0].keys())[:6]))
    else:
        print(name + ': NOT EXISTS')

from mapping.mapping_storage import MappingStorage
s = MappingStorage(use_db=False)
for m in s.get_all():
    print('Mapping: ' + m.name + ' category=' + str(m.category) + ' fields=' + str(len(m.fields)))
