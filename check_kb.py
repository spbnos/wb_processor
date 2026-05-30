import sys
sys.path.insert(0, '.')
from knowledge_base.pdf_reader import PDFReader
r = PDFReader()
print('Documents:', r.list_documents())
print('Stats:', r.stats())
