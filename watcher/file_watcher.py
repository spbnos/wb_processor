"""
Watcher — следит за папкой incoming/ через watchdog.
При появлении нового файла запускает pipeline обработки.
"""
import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer

from config.settings import INCOMING_DIR, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


class IncomingFileHandler(FileSystemEventHandler):
    """
    Обрабатывает событие создания файла в папке incoming/.
    Вызывает callback(filepath) для каждого нового поддерживаемого файла.
    """

    def __init__(self, on_new_file_callback):
        super().__init__()
        self._callback = on_new_file_callback
        self._seen: set[str] = set()   # дедупликация — watchdog иногда даёт дубли

    def on_created(self, event: FileCreatedEvent):
        if event.is_directory:
            return

        path = Path(event.src_path)

        # Фильтр по расширению
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            logger.debug(f"[watcher] Ignored (unsupported ext): {path.name}")
            return

        # Игнорируем временные файлы Excel (~$...)
        if path.name.startswith("~$"):
            logger.debug(f"[watcher] Ignored (temp file): {path.name}")
            return

        key = str(path.resolve())
        if key in self._seen:
            return
        self._seen.add(key)

        logger.info(f"[watcher] New file detected: {path.name}")

        # Ждём пока файл дозапишется (на случай медленного копирования)
        self._wait_until_stable(path)

        try:
            self._callback(path)
        except Exception as e:
            logger.error(f"[watcher] Error processing {path.name}: {e}", exc_info=True)

    @staticmethod
    def _wait_until_stable(path: Path, timeout: int = 30, interval: float = 0.5):
        """Ждёт пока размер файла перестанет меняться (файл дозаписан)."""
        prev_size = -1
        elapsed = 0.0
        while elapsed < timeout:
            try:
                curr_size = path.stat().st_size
            except FileNotFoundError:
                time.sleep(interval)
                elapsed += interval
                continue
            if curr_size == prev_size and curr_size > 0:
                return
            prev_size = curr_size
            time.sleep(interval)
            elapsed += interval
        logger.warning(f"[watcher] File {path.name} may still be writing (timeout reached).")


class FolderWatcher:
    """
    Запускает наблюдение за папкой INCOMING_DIR.
    Использование:
        watcher = FolderWatcher(callback=process_file)
        watcher.start()
        ...
        watcher.stop()
    """

    def __init__(self, on_new_file_callback, watch_dir: Path = INCOMING_DIR):
        self._watch_dir = watch_dir
        self._handler = IncomingFileHandler(on_new_file_callback)
        self._observer = Observer()

    def start(self):
        self._watch_dir.mkdir(parents=True, exist_ok=True)
        self._observer.schedule(self._handler, str(self._watch_dir), recursive=False)
        self._observer.start()
        logger.info(f"[watcher] Watching: {self._watch_dir}")

    def stop(self):
        self._observer.stop()
        self._observer.join()
        logger.info("[watcher] Stopped.")

    def run_forever(self):
        """Блокирующий режим — Ctrl+C для остановки."""
        self.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def scan_existing(self):
        """
        Однократно сканирует папку при старте.
        Обрабатывает файлы, которые уже лежат в incoming/.
        """
        existing = [
            f for f in self._watch_dir.iterdir()
            if f.is_file()
            and f.suffix.lower() in SUPPORTED_EXTENSIONS
            and not f.name.startswith("~$")
        ]
        if existing:
            logger.info(f"[watcher] Found {len(existing)} existing file(s) in incoming/")
            for f in sorted(existing):
                logger.info(f"[watcher] Processing existing: {f.name}")
                try:
                    self._handler._callback(f)
                except Exception as e:
                    logger.error(f"[watcher] Error: {f.name}: {e}", exc_info=True)
