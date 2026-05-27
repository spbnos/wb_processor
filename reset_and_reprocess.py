"""
reset_and_reprocess.py — сброс стале очереди и повторная обработка файла.

ЗАПУСК: python reset_and_reprocess.py

Что делает:
1. Очищает review_queue.json (удаляет все pending items)
2. Ищет Excel файл оферты в processed/ и копирует обратно в incoming/
3. SmartMapper с исправленным реестром теперь правильно замапит все колонки

"""
import json
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INCOMING_DIR = BASE_DIR / "incoming"
PROCESSED_DIR = BASE_DIR / "processed"
QUEUE_PATH = DATA_DIR / "review_queue.json"

def main():
    print("=" * 60)
    print("WB Processor — сброс очереди и повторная обработка")
    print("=" * 60)

    # 1. Очистить review_queue.json
    if QUEUE_PATH.exists():
        with open(QUEUE_PATH) as f:
            items = json.load(f)
        pending = [i for i in items if i.get("status") == "pending"]
        print(f"\n[1] review_queue.json: {len(items)} items, {len(pending)} pending")

        # Получаем список уникальных файлов
        files_in_queue = set()
        for item in pending:
            fp = item.get("filepath", "")
            if fp:
                files_in_queue.add(Path(fp).name)

        # Помечаем все pending как expired
        for item in items:
            if item.get("status") == "pending":
                item["status"] = "expired"
                item["resolved_by"] = "manual_reset"

        with open(QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"    ✓ Сброшено {len(pending)} pending → expired")
        print(f"    Файлы в очереди: {files_in_queue}")
    else:
        print("\n[1] review_queue.json не найден")
        files_in_queue = set()

    # 2. Найти Excel файлы в processed/ и вернуть в incoming/
    print(f"\n[2] Ищем Excel файлы в {PROCESSED_DIR}")
    excel_files = list(PROCESSED_DIR.glob("*.xlsx")) + list(PROCESSED_DIR.glob("*.xls"))

    if not excel_files:
        print("    ⚠ Файлы не найдены в processed/")
        print(f"    Положи файл оферты вручную в {INCOMING_DIR}")
        return

    for src in excel_files:
        dest = INCOMING_DIR / src.name
        if dest.exists():
            print(f"    ⚠ Уже в incoming/: {src.name} — пропускаем")
            continue
        shutil.copy2(str(src), str(dest))
        print(f"    ✓ Скопирован: {src.name} → incoming/")

    # 3. Очистить processed registry чтобы файл не пропустился как дубликат
    registry_path = DATA_DIR / "processed_files.json"
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)

        original_count = len(registry)
        # Удаляем записи для файлов которые возвращаем на обработку
        names_to_remove = {f.name for f in excel_files}
        registry = {k: v for k, v in registry.items()
                    if v.get("filename") not in names_to_remove}

        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        removed = original_count - len(registry)
        print(f"\n[3] Реестр обработанных файлов: удалено {removed} записей")
    else:
        print("\n[3] processed_files.json не найден — пропускаем")

    print("\n" + "=" * 60)
    print("✅ Готово! Теперь:")
    print("   1. Убедись что FastAPI запущен (uvicorn api.main:app --reload)")
    print("   2. Запусти pipeline или file watcher")
    print("   3. Файл будет обработан с ИСПРАВЛЕННЫМ SmartMapper")
    print("   4. Все колонки получат корректный маппинг AUTO (0 review items)")
    print("=" * 60)

if __name__ == "__main__":
    main()
