"""
knowledge_base/pdf_reader.py

PDF Reader для документов WB (оферта, инструкции, тарифы).

Возможности:
  1. Извлечение текста (pdfplumber → PyMuPDF → pypdf fallback)
  2. Структурный парсинг: определения терминов, таблицы тарифов
  3. Поиск по тексту документа
  4. Авто-индексирование → обогащение KnowledgeEngine

Папка документов: knowledge_base/documents/
Клади сюда: оферту WB, тарифы, инструкции по API.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DOCS_DIR  = Path(__file__).resolve().parent / "documents"
_INDEX_FILE = Path(__file__).resolve().parent / "registry" / "pdf_index.json"

# ─── WB-специфичные паттерны для извлечения терминов ─────────────────
# Формат оферты WB: "Термин" – определение
_TERM_PATTERNS = [
    re.compile(r"^«(.{3,60})»\s*[–—-]\s*(.{20,})", re.MULTILINE),
    re.compile(r"^\"(.{3,60})\"\s*[–—-]\s*(.{20,})", re.MULTILINE),
    re.compile(r"^(.{3,60})\s*[–—-]\s*это\s+(.{20,})", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(\d+\.\d+[\.\d]*)\s+(.{10,})", re.MULTILINE),   # нумерованные пункты
]

# Паттерны для финансовых показателей WB
_WB_FINANCIAL_PATTERN = re.compile(
    r"(кВВ|ВВ|Вознаграждение|Комиссия|Логистика|Хранение|Штраф|Скидка)"
    r".{0,200}"
    r"(\d+[,\.]\d+\s*%|\d+\s*руб)",
    re.IGNORECASE | re.DOTALL
)


@dataclass
class PDFDocument:
    """Загруженный и распарсенный PDF документ."""
    filename: str
    path: str
    pages: int
    char_count: int
    terms: dict[str, str]          # {термин_lower: определение}
    sections: list[dict]           # [{title, content, page}]
    financial_mentions: list[str]  # упоминания финансовых показателей
    full_text: str = field(default="", repr=False)


@dataclass
class SearchResult:
    document: str
    page_hint: int
    context: str           # фрагмент текста вокруг совпадения
    score: float           # релевантность 0–1


# ─────────────────────────────────────────────────────────────────────
# Извлечение текста
# ─────────────────────────────────────────────────────────────────────

def extract_text(pdf_path: Path, max_pages: int = 200) -> tuple[str, int]:
    """
    Извлекает текст из PDF.
    Возвращает (text, page_count).
    Пробует: pdfplumber → PyMuPDF → pypdf.
    """
    # 1. pdfplumber — лучший для таблиц и структурных PDF
    try:
        import pdfplumber
        parts, page_count = [], 0
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages[:max_pages]:
                t = page.extract_text()
                if t:
                    parts.append(t)
        text = "\n\n".join(parts)
        logger.info(f"[pdf] pdfplumber: {page_count}p, {len(text)} chars ← {pdf_path.name}")
        return text, page_count
    except ImportError:
        logger.debug("[pdf] pdfplumber not installed")
    except Exception as e:
        logger.warning(f"[pdf] pdfplumber failed: {e}")

    # 2. PyMuPDF (fitz) — быстрый, хорош для кириллицы
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)
        parts = [doc[i].get_text() for i in range(min(max_pages, page_count))]
        text = "\n\n".join(p for p in parts if p)
        logger.info(f"[pdf] PyMuPDF: {page_count}p, {len(text)} chars ← {pdf_path.name}")
        doc.close()
        return text, page_count
    except ImportError:
        logger.debug("[pdf] PyMuPDF not installed")
    except Exception as e:
        logger.warning(f"[pdf] PyMuPDF failed: {e}")

    # 3. pypdf — базовый fallback
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        parts = []
        for page in reader.pages[:max_pages]:
            t = page.extract_text()
            if t:
                parts.append(t)
        text = "\n\n".join(parts)
        logger.info(f"[pdf] pypdf: {page_count}p, {len(text)} chars ← {pdf_path.name}")
        return text, page_count
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[pdf] pypdf failed: {e}")

    logger.error(
        f"[pdf] Cannot read {pdf_path.name}. "
        "Install: pip install pdfplumber  OR  pip install pymupdf"
    )
    return "", 0


# ─────────────────────────────────────────────────────────────────────
# Парсинг структуры
# ─────────────────────────────────────────────────────────────────────

def _extract_terms(text: str) -> dict[str, str]:
    """
    Извлекает термины и их определения из текста.
    Фокус: WB-специфичная лексика (кВВ, ВВ, FBW/FBS, ПВЗ и т.д.)
    """
    terms: dict[str, str] = {}

    for pattern in _TERM_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if len(groups) >= 2:
                term = groups[0].strip().rstrip(".,;:")
                definition = groups[1].strip()[:300]
                if len(term) >= 2 and len(definition) >= 15:
                    terms[term.lower()] = definition

    # Дополнительно: WB-специфичные аббревиатуры из текста
    wb_abbrev = {
        "фбо": "FBO (Fulfillment By Ozon/WB) — хранение и доставка силами маркетплейса",
        "fbw": "FBW (Fulfillment By Wildberries) — хранение и доставка силами WB",
        "fbs": "FBS (Fulfillment By Seller) — хранение у продавца, доставка WB",
        "квв": "кВВ — Коэффициент Вознаграждения Вайлдберриз (комиссия %)",
        "вв":  "ВВ — Вознаграждение Вайлдберриз (итоговая комиссия без НДС)",
        "пвз": "ПВЗ — Пункт Выдачи Заказов",
        "мгт": "МГТ — Моногрузовой Тип (тип упаковки WB)",
    }
    for abbr, desc in wb_abbrev.items():
        if abbr not in terms and abbr in text.lower():
            terms[abbr] = desc

    return terms


def _extract_sections(text: str) -> list[dict]:
    """
    Разбивает текст на секции по заголовкам.
    Заголовок: строка из 1-10 слов, после которой идёт текст.
    """
    sections = []
    # Паттерн заголовка: нумерованный (1. / 1.1.) или CAPS
    heading_re = re.compile(
        r"(?:^|\n)(\d+(?:\.\d+)*\.?\s+[А-ЯA-Z].{3,80}|[А-Я]{4,}[А-Яа-яA-Za-z\s]{3,60})\n",
    )
    matches = list(heading_re.finditer(text))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()[:1000]
        if len(content) > 50:
            sections.append({
                "title": title,
                "content": content,
                "char_offset": m.start(),
            })
    return sections


def _extract_financial_mentions(text: str) -> list[str]:
    """Находит упоминания ключевых финансовых показателей."""
    mentions = []
    for match in _WB_FINANCIAL_PATTERN.finditer(text):
        ctx = match.group(0).strip()[:200].replace("\n", " ")
        mentions.append(ctx)
    return mentions[:30]  # топ-30


# ─────────────────────────────────────────────────────────────────────
# PDFReader — главный класс
# ─────────────────────────────────────────────────────────────────────

class PDFReader:
    """
    Читает и индексирует PDF документы из knowledge_base/documents/.

    Использование:
        reader = PDFReader()

        # Загрузить и проиндексировать оферту WB
        doc = reader.load("Оферта_WB_2024.pdf")
        print(doc.terms)  # все извлечённые термины

        # Поиск по всем документам
        results = reader.search("кВВ комиссия")

        # Обогатить KnowledgeEngine
        reader.enrich_knowledge_engine(kb_engine)
    """

    def __init__(self, docs_dir: Path = _DOCS_DIR):
        self._docs_dir = docs_dir
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        self._loaded: dict[str, PDFDocument] = {}   # filename → PDFDocument
        self._index: dict[str, str] = {}             # term_lower → definition

    # ── Load ─────────────────────────────────────────────

    def load(self, filename: str) -> Optional[PDFDocument]:
        """Загружает один PDF по имени файла."""
        path = self._docs_dir / filename
        if not path.exists():
            logger.warning(f"[pdf_reader] Not found: {path}")
            return None
        return self._parse(path)

    def load_all(self) -> dict[str, PDFDocument]:
        """Загружает все PDF из documents/."""
        results = {}
        pdfs = list(self._docs_dir.glob("*.pdf"))
        if not pdfs:
            logger.info(f"[pdf_reader] No PDFs in {self._docs_dir}")
            return {}
        for pdf_path in sorted(pdfs):
            doc = self._parse(pdf_path)
            if doc:
                results[pdf_path.name] = doc
        logger.info(f"[pdf_reader] Loaded {len(results)} documents")
        return results

    def _parse(self, path: Path) -> Optional[PDFDocument]:
        """Полный парсинг одного PDF."""
        if path.name in self._loaded:
            return self._loaded[path.name]

        text, page_count = extract_text(path)
        if not text:
            logger.warning(f"[pdf_reader] Empty text from {path.name}")
            return None

        terms     = _extract_terms(text)
        sections  = _extract_sections(text)
        fin_ments = _extract_financial_mentions(text)

        # Добавляем в глобальный индекс
        self._index.update(terms)

        doc = PDFDocument(
            filename=path.name,
            path=str(path),
            pages=page_count,
            char_count=len(text),
            terms=terms,
            sections=sections,
            financial_mentions=fin_ments,
            full_text=text,
        )
        self._loaded[path.name] = doc
        logger.info(
            f"[pdf_reader] Parsed {path.name}: "
            f"{page_count}p, {len(terms)} terms, {len(sections)} sections"
        )
        return doc

    # ── Search ───────────────────────────────────────────

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """
        Полнотекстовый поиск по всем загруженным документам.
        Возвращает список SearchResult, отсортированных по релевантности.
        """
        q = query.lower().strip()
        results: list[SearchResult] = []

        for filename, doc in self._loaded.items():
            text = doc.full_text.lower()
            pos = 0
            while True:
                idx = text.find(q, pos)
                if idx == -1:
                    break
                # Контекст ±200 символов
                start = max(0, idx - 200)
                end   = min(len(text), idx + len(q) + 200)
                context = doc.full_text[start:end].replace("\n", " ").strip()

                # Релевантность: чем ближе к началу документа — тем выше
                score = 1.0 - (idx / max(len(text), 1))

                results.append(SearchResult(
                    document=filename,
                    page_hint=max(1, idx // 3000),  # грубая оценка страницы
                    context=context,
                    score=round(score, 3),
                ))
                pos = idx + 1
                if len(results) >= max_results * 3:
                    break

        # Сортируем по score
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

    def search_terms(self, query: str) -> list[dict]:
        """Поиск по извлечённым терминам."""
        q = query.lower().strip()
        return [
            {"term": term, "definition": defn}
            for term, defn in self._index.items()
            if q in term or q in defn.lower()
        ][:10]

    # ── Enrich KnowledgeEngine ───────────────────────────

    def enrich_knowledge_engine(self, engine) -> int:
        """
        Обогащает KnowledgeEngine терминами из PDF.
        Добавляет найденные термины в pdf_index engine'а.

        Returns: кол-во добавленных терминов
        """
        if not self._index:
            # Загружаем документы если ещё не загружены
            self.load_all()

        count = 0
        for term, definition in self._index.items():
            if term not in engine._pdf_index:
                engine._pdf_index[term] = definition
                count += 1

        if count:
            logger.info(f"[pdf_reader] Enriched KnowledgeEngine with {count} PDF terms")
        return count

    # ── Persistence ──────────────────────────────────────

    def save_index(self, path: Path = _INDEX_FILE) -> Path:
        """Сохраняет извлечённый индекс в JSON для последующей загрузки."""
        path.parent.mkdir(parents=True, exist_ok=True)
        index_data = {
            "documents": {
                fname: {
                    "pages": doc.pages,
                    "char_count": doc.char_count,
                    "term_count": len(doc.terms),
                    "section_count": len(doc.sections),
                }
                for fname, doc in self._loaded.items()
            },
            "terms": self._index,
            "total_terms": len(self._index),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        logger.info(f"[pdf_reader] Index saved: {path} ({len(self._index)} terms)")
        return path

    def load_saved_index(self, path: Path = _INDEX_FILE) -> int:
        """Загружает ранее сохранённый индекс (быстро, без перечитки PDF)."""
        if not path.exists():
            return 0
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._index.update(data.get("terms", {}))
        count = len(data.get("terms", {}))
        logger.info(f"[pdf_reader] Loaded saved index: {count} terms from {path}")
        return count

    # ── Info ─────────────────────────────────────────────

    def list_documents(self) -> list[dict]:
        """Список PDF файлов в documents/ с метаданными."""
        docs = []
        for pdf in sorted(self._docs_dir.glob("*.pdf")):
            stat = pdf.stat()
            loaded = pdf.name in self._loaded
            info = {
                "filename": pdf.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "loaded": loaded,
            }
            if loaded:
                doc = self._loaded[pdf.name]
                info.update({
                    "pages": doc.pages,
                    "terms": len(doc.terms),
                    "sections": len(doc.sections),
                })
            docs.append(info)
        return docs

    def stats(self) -> dict:
        return {
            "documents_dir": str(self._docs_dir),
            "loaded": len(self._loaded),
            "available": len(list(self._docs_dir.glob("*.pdf"))),
            "indexed_terms": len(self._index),
        }
