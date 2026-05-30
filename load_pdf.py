import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from knowledge_base.pdf_reader import PDFReader
from knowledge_base.search.knowledge_engine import KnowledgeEngine

PDF_NAME = "Оферта товарная.pdf"
INDEX_PATH = _ROOT / "knowledge_base" / "registry" / "pdf_index.json"

r = PDFReader()
engine = KnowledgeEngine()

if INDEX_PATH.exists():
    import json
    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    term_count = len(data.get("terms", {}))
    if term_count:
        r.load_saved_index()
        enriched = r.enrich_knowledge_engine(engine)
        print(f"OK: saved index ({term_count} terms), engine +{enriched} new")

doc = r.load(PDF_NAME)
if doc:
    print("Pages:", doc.pages)
    print("Chars:", doc.char_count)
    print("Terms extracted:", len(doc.terms))
    enriched = r.enrich_knowledge_engine(engine)
    print("Enriched engine with:", enriched, "new terms")
    saved = r.save_index()
    print("Index saved to:", saved)
elif not INDEX_PATH.exists():
    print("ERROR: Could not read PDF and no pdf_index.json")
    print("Install:  py -3.12 -m pip install pdfplumber")
    sys.exit(1)
else:
    print("PDF skipped; KB uses saved index. Install pdfplumber to refresh from PDF.")
