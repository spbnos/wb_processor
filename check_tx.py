import json
from pathlib import Path
tx = json.loads(Path('data/loaded/transactions.json').read_text(encoding='utf-8'))
print('Total transactions:', len(tx))
skus = set(r.get('sku','') for r in tx)
print('Unique SKUs:', len(skus), list(skus)[:5])
files = set(r.get('file_id','') for r in tx)
print('File IDs:', files)
