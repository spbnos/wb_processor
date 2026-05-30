import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'D:/MyProject/wb_platform')
from smart_pipeline import SmartPipeline
from pathlib import Path
p = SmartPipeline(use_db=False)
files = list(Path('incoming').glob('*.xlsx')) + list(Path('incoming').glob('*.csv'))
print('Files found:', [f.name for f in files])
for f in files:
    print(f'Processing: {f.name}')
    status = p.process_file(f)
    print(f'Status: {status}')
    print()
print('Queue stats:', p.queue_stats())
