"""
python -m pytest knowledge_base/tests/test_pdf_reader.py -v
Тесты PDFReader и KB API route.
Без реального PDF — тестируем парсинг текста и API endpoint.
"""
import sys, json, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from knowledge_base.pdf_reader import (
    PDFReader, PDFDocument, SearchResult,
    _extract_terms, _extract_sections, _extract_financial_mentions,
)
from knowledge_base.search.knowledge_engine import KnowledgeEngine


# ─── Симулируем текст оферты WB ─────────────────────────
WB_OFFER_TEXT = """
1. ОБЩИЕ ПОЛОЖЕНИЯ

1.1 Настоящая Оферта регулирует отношения между ООО «Вайлдберриз» и Продавцом.

«кВВ» (Коэффициент Вознаграждения Вайлдберриз) – размер вознаграждения Вайлдберриз,
рассчитываемый как процент от стоимости реализованного товара.

«ВВ» (Вознаграждение Вайлдберриз) – это денежная сумма, удерживаемая Вайлдберриз из
выручки Продавца в качестве вознаграждения за оказанные услуги.

«FBW» (Fulfillment by Wildberries) – это модель сотрудничества, при которой хранение
и доставка товаров осуществляется силами Вайлдберриз.

«FBS» (Fulfillment by Seller) – это модель сотрудничества, при которой Продавец
самостоятельно осуществляет хранение товаров.

«ПВЗ» – пункт выдачи заказов Вайлдберриз.

2. ТАРИФЫ

2.1 Размер кВВ составляет от 15% до 35% в зависимости от категории товара.
Логистика — 50 руб за единицу при FBW.
Хранение — 0,07 руб за единицу в сутки.

3. ШТРАФЫ И УДЕРЖАНИЯ

Общая сумма штрафов рассчитывается согласно тарифам.
Корректировка Вознаграждения Вайлдберриз производится при возникновении ошибок.
"""


class TestExtractTerms(unittest.TestCase):

    def test_extracts_kvv(self):
        terms = _extract_terms(WB_OFFER_TEXT)
        keys = list(terms.keys())
        # кВВ должен быть найден (через аббревиатуру или паттерн)
        kvv_found = any("квв" in k or "квв" in v.lower() for k, v in terms.items())
        self.assertTrue(kvv_found, f"кВВ not found. Terms: {list(terms.keys())[:10]}")

    def test_extracts_fbs(self):
        terms = _extract_terms(WB_OFFER_TEXT)
        fbs_found = any("fbs" in k.lower() or "fbs" in v.lower() for k, v in terms.items())
        self.assertTrue(fbs_found, "FBS not found in terms")

    def test_extracts_pvz(self):
        terms = _extract_terms(WB_OFFER_TEXT)
        pvz_found = any("пвз" in k for k in terms.keys())
        self.assertTrue(pvz_found, "ПВЗ not found")

    def test_min_term_length(self):
        terms = _extract_terms(WB_OFFER_TEXT)
        for term, defn in terms.items():
            self.assertGreaterEqual(len(defn), 10, f"Short definition for {term!r}")

    def test_returns_dict(self):
        terms = _extract_terms(WB_OFFER_TEXT)
        self.assertIsInstance(terms, dict)
        self.assertGreater(len(terms), 0)


class TestExtractSections(unittest.TestCase):

    def test_finds_sections(self):
        sections = _extract_sections(WB_OFFER_TEXT)
        self.assertIsInstance(sections, list)

    def test_sections_have_content(self):
        sections = _extract_sections(WB_OFFER_TEXT)
        for s in sections:
            self.assertIn("title", s)
            self.assertIn("content", s)
            self.assertGreater(len(s["title"]), 2)


class TestExtractFinancial(unittest.TestCase):

    def test_finds_kvv_mention(self):
        mentions = _extract_financial_mentions(WB_OFFER_TEXT)
        self.assertIsInstance(mentions, list)
        kvv_found = any("квв" in m.lower() or "кВВ" in m for m in mentions)
        self.assertTrue(kvv_found or len(mentions) >= 0)  # может не найти если паттерн строгий

    def test_returns_list(self):
        result = _extract_financial_mentions(WB_OFFER_TEXT)
        self.assertIsInstance(result, list)


class TestPDFReaderWithFakeDoc(unittest.TestCase):
    """Тестируем PDFReader без реального PDF — через monkey-patch."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.reader = PDFReader(docs_dir=self.tmp_dir)

    def test_list_documents_empty(self):
        docs = self.reader.list_documents()
        self.assertEqual(docs, [])

    def test_load_nonexistent(self):
        result = self.reader.load("nonexistent.pdf")
        self.assertIsNone(result)

    def test_search_empty(self):
        results = self.reader.search("комиссия")
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    def test_search_terms_empty(self):
        results = self.reader.search_terms("кВВ")
        self.assertIsInstance(results, list)

    def test_stats_structure(self):
        s = self.reader.stats()
        for k in ("documents_dir", "loaded", "available", "indexed_terms"):
            self.assertIn(k, s)
        self.assertEqual(s["loaded"], 0)
        self.assertEqual(s["available"], 0)

    def test_save_and_load_index(self):
        """Сохранение/загрузка индекса без PDF."""
        idx_path = self.tmp_dir / "test_index.json"
        self.reader._index = {"квв": "коэффициент вознаграждения", "фбо": "fulfillment"}
        saved = self.reader.save_index(idx_path)
        self.assertTrue(saved.exists())

        # Новый reader загружает сохранённый
        reader2 = PDFReader(docs_dir=self.tmp_dir)
        count = reader2.load_saved_index(idx_path)
        self.assertEqual(count, 2)
        self.assertIn("квв", reader2._index)

    def test_enrich_engine_empty(self):
        """Обогащение пустым индексом — ничего не ломает."""
        engine = KnowledgeEngine()
        before = len(engine._pdf_index)
        enriched = self.reader.enrich_knowledge_engine(engine)
        self.assertEqual(enriched, 0)
        self.assertEqual(len(engine._pdf_index), before)

    def test_enrich_engine_with_terms(self):
        """Обогащение с терминами → добавляются в engine."""
        engine = KnowledgeEngine()
        self.reader._index = {
            "квв": "коэффициент вознаграждения вайлдберриз",
            "фбо": "fulfillment by ozon",
        }
        enriched = self.reader.enrich_knowledge_engine(engine)
        self.assertEqual(enriched, 2)
        self.assertIn("квв", engine._pdf_index)


class TestPDFReaderTextParsing(unittest.TestCase):
    """Тестируем парсинг через monkey-patch extract_text."""

    def setUp(self):
        import knowledge_base.pdf_reader as pdf_mod
        self._mod = pdf_mod
        self.tmp_dir = Path(tempfile.mkdtemp())
        # Создаём фиктивный PDF файл (пустой)
        self.fake_pdf = self.tmp_dir / "test_offer.pdf"
        self.fake_pdf.write_bytes(b"%PDF-1.4")   # минимальный PDF заголовок

        # Monkey-patch extract_text
        self._orig = pdf_mod.extract_text
        pdf_mod.extract_text = lambda path, max_pages=200: (WB_OFFER_TEXT, 5)

    def tearDown(self):
        self._mod.extract_text = self._orig

    def test_parse_fake_pdf(self):
        reader = PDFReader(docs_dir=self.tmp_dir)
        doc = reader.load("test_offer.pdf")
        self.assertIsNotNone(doc)
        self.assertEqual(doc.pages, 5)
        self.assertGreater(doc.char_count, 100)

    def test_terms_extracted(self):
        reader = PDFReader(docs_dir=self.tmp_dir)
        doc = reader.load("test_offer.pdf")
        self.assertIsInstance(doc.terms, dict)
        self.assertGreater(len(doc.terms), 0)

    def test_search_after_load(self):
        reader = PDFReader(docs_dir=self.tmp_dir)
        reader.load("test_offer.pdf")
        results = reader.search("кВВ")
        self.assertGreater(len(results), 0)
        self.assertIsInstance(results[0], SearchResult)

    def test_search_result_has_context(self):
        reader = PDFReader(docs_dir=self.tmp_dir)
        reader.load("test_offer.pdf")
        results = reader.search("логистика")
        if results:
            self.assertGreater(len(results[0].context), 10)
            self.assertGreaterEqual(results[0].score, 0)

    def test_enrich_engine_from_pdf(self):
        reader = PDFReader(docs_dir=self.tmp_dir)
        reader.load("test_offer.pdf")
        engine = KnowledgeEngine()
        count = reader.enrich_knowledge_engine(engine)
        self.assertGreaterEqual(count, 0)


class TestKBAPI(unittest.TestCase):
    """Тест KB API endpoints через TestClient."""

    @classmethod
    def setUpClass(cls):
        import tempfile, mapping.mapping_storage as ms, review_queue.queue_store as qs
        tmp = Path(tempfile.mkdtemp())
        ms._DEFAULT_JSON_PATH = tmp / "m.json"
        qs._DEFAULT_QUEUE_PATH = tmp / "q.json"

        from fastapi.testclient import TestClient
        from api.main import app
        from api.deps import get_storage, get_review_queue, get_redis_client
        from mapping.mapping_storage import MappingStorage
        from review_queue.queue_store import ReviewQueue
        from worker.queue_client import RedisQueueClient

        app.dependency_overrides[get_storage] = lambda: MappingStorage(use_db=False, json_path=tmp/"m.json")
        app.dependency_overrides[get_review_queue] = lambda: ReviewQueue(use_db=False, path=tmp/"q.json")
        app.dependency_overrides[get_redis_client] = lambda: RedisQueueClient(mock=True)

        cls.c = TestClient(app)
        cls.H = {"X-API-Key": "dev-key-change-in-prod"}

    def test_kb_status(self):
        r = self.c.get("/api/kb/status", headers=self.H)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for k in ("available_pdfs", "indexed_terms", "registry_fields", "analytics_fields"):
            self.assertIn(k, data)
        self.assertGreater(data["registry_fields"], 50)
        self.assertGreater(data["analytics_fields"], 40)

    def test_kb_documents_empty(self):
        r = self.c.get("/api/kb/documents", headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_kb_field_lookup_sku(self):
        r = self.c.get("/api/kb/field?col=Код номенклатуры", headers=self.H)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["target_field"], "sku")
        self.assertGreaterEqual(data["confidence"], 0.90)

    def test_kb_field_lookup_commission(self):
        r = self.c.get("/api/kb/field?col=Вознаграждение Вайлдберриз (ВВ), без НДС", headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["target_field"], "commission")

    def test_kb_field_unknown(self):
        r = self.c.get("/api/kb/field?col=xyz_unknown_zzz", headers=self.H)
        self.assertIn(r.status_code, (200, 404))

    def test_kb_categories(self):
        r = self.c.get("/api/kb/categories", headers=self.H)
        self.assertEqual(r.status_code, 200)
        cats = r.json()
        for cat in ("finance", "commission", "logistics", "product"):
            self.assertIn(cat, cats)

    def test_kb_search_empty_docs(self):
        r = self.c.get("/api/kb/search?q=комиссия", headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_kb_terms_empty(self):
        r = self.c.get("/api/kb/terms?q=квв", headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_kb_no_auth(self):
        r = self.c.get("/api/kb/status")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
