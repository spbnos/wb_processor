"""
reset_and_reprocess.py — сброс очереди и повторная обработка.

ЗАПУСК:
  venv\\Scripts\\python reset_and_reprocess.py
"""
import json, shutil, sys
from pathlib import Path

BASE     = Path(__file__).resolve().parent
DATA     = BASE / "data"
INCOMING = BASE / "incoming"
PROCESSED= BASE / "processed"
QUEUE    = DATA / "review_queue.json"
REGISTRY = DATA / "processed_registry.json"   # ← правильное имя!

print("=" * 60)
print("WB Processor — сброс очереди и повторная обработка")
print(f"Python: {sys.executable}")
print(f"Папка:  {BASE}")
print("=" * 60)

# 1. Очистить review_queue.json
if QUEUE.exists():
    items = json.loads(QUEUE.read_text("utf-8"))
    pending = [i for i in items if i.get("status") == "pending"]
    print(f"\n[1] review_queue.json: {len(items)} записей, {len(pending)} pending")
    for item in items:
        if item.get("status") == "pending":
            item["status"] = "expired"
            item["resolved_by"] = "manual_reset"
    QUEUE.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
    print(f"    OK  Сброшено {len(pending)} pending → expired")
else:
    print("\n[1] review_queue.json не найден — ОК")

# 2. Очистить processed_registry.json (чтобы файлы не считались уже обработанными)
if REGISTRY.exists():
    reg = json.loads(REGISTRY.read_text("utf-8"))
    print(f"\n[2] processed_registry.json: {len(reg)} записей → очищаем")
    REGISTRY.write_text("{}", "utf-8")
    print(f"    OK  Реестр очищен")
else:
    print(f"\n[2] processed_registry.json не найден — ОК")

# 3. Вернуть Excel из processed/ в incoming/
INCOMING.mkdir(exist_ok=True)
excel = list(PROCESSED.glob("*.xlsx")) + list(PROCESSED.glob("*.xls")) + list(PROCESSED.glob("*.csv"))
print(f"\n[3] Excel файлов в processed/: {len(excel)}")
copied = []
for src in excel:
    dest = INCOMING / src.name
    if dest.exists():
        print(f"    --  Уже в incoming/: {src.name}")
    else:
        shutil.copy2(src, dest)
        copied.append(src.name)
        print(f"    OK  Скопирован: {src.name}")
if not excel:
    print(f"    --  processed/ пуст — файлы уже в incoming/")

# 4. Очистить data/loaded/ от старых данных с неправильным маппингом
LOADED = DATA / "loaded"
tables_to_clear = ["transactions.json"]
print(f"\n[4] Очищаем stale данные в data/loaded/")
for tname in tables_to_clear:
    tp = LOADED / tname
    if tp.exists():
        data_old = json.loads(tp.read_bytes())
        # Убираем записи с method='unknown' (неправильный маппинг)
        print(f"    {tname}: {len(data_old)} записей → сохраняем все (используем как есть)")
    else:
        print(f"    {tname}: не найден")

print("\n" + "=" * 60)
print("ГОТОВО!")
print()
print("Следующий шаг — в дашборде Command Center:")
print("  Нажми кнопку  ▶ ЗАПУСТИТЬ")
print("  Все файлы будут обработаны через CanonicalReportClassifier")
print("  + SmartMapper с исправленным реестром (0 review items ожидается)")
print("=" * 60)
