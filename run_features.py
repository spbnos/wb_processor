import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'D:/MyProject/wb_platform')
from feature_store.feature_pipeline import FeaturePipeline
from pathlib import Path
import json
# Загружаем transactions
tx_path = Path('data/loaded/transactions.json')
stocks_path = Path('data/loaded/stocks.json')
print('transactions.json exists:', tx_path.exists())
if tx_path.exists():
    data = json.loads(tx_path.read_text(encoding='utf-8'))
    print('Transactions count:', len(data))
    if data:
        print('Sample keys:', list(data[0].keys())[:8])
# Запускаем Feature Pipeline
fp = FeaturePipeline(
    data_dir=Path('data/loaded'),
    base_dir=Path('data/feature_store')
)
result = fp.run()
print('Feature pipeline result:', result)
# Проверяем матрицу
matrix = fp.get_feature_matrix('sales_features')
print('Feature matrix shape:', matrix.shape if not matrix.empty else 'EMPTY')
