"""
python -m pytest knowledge_base/search/tests/test_knowledge_engine.py -v
"""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from knowledge_base.search.knowledge_engine import KnowledgeEngine


class TestLoad(unittest.TestCase):
    def setUp(self): self.e = KnowledgeEngine()
    def test_loaded(self):
        s = self.e.stats()
        self.assertGreater(s["total_fields"], 50)
        self.assertGreater(s["analytics_fields"], 40)
        self.assertGreater(s["aliases_indexed"], 80)

class TestExact(unittest.TestCase):
    def setUp(self): self.e = KnowledgeEngine()
    def _chk(self, col, tgt, min_c=0.90):
        r = self.e.lookup(col)
        self.assertIsNotNone(r, f"No result: {col!r}")
        self.assertEqual(r.target_field, tgt, f"{col!r}→{r.target_field!r}")
        self.assertGreaterEqual(r.confidence, min_c)
    def test_sku(self):        self._chk("Код номенклатуры", "sku")
    def test_barcode(self):    self._chk("Баркод", "barcode")
    def test_name(self):       self._chk("Название", "name")
    def test_brand(self):      self._chk("Бренд", "brand")
    def test_category(self):   self._chk("Предмет", "category")
    def test_vendor(self):     self._chk("Артикул поставщика", "vendor_code")
    def test_revenue(self):    self._chk("Вайлдберриз реализовал Товар (Пр)", "revenue")
    def test_price(self):      self._chk("Цена розничная", "price")
    def test_net_profit(self): self._chk("К перечислению Продавцу за реализованный Товар", "net_profit")
    def test_commission(self): self._chk("Вознаграждение Вайлдберриз (ВВ), без НДС", "commission")
    def test_kvv(self):        self._chk("Размер кВВ, %", "kvv_pct")
    def test_kvv_base(self):   self._chk("Размер кВВ без НДС, % Базовый", "kvv_base_pct")
    def test_logistics(self):  self._chk("Услуги по доставке товара покупателю", "logistics")
    def test_warehouse(self):  self._chk("Наименование офиса доставки", "warehouse")
    def test_qty(self):        self._chk("Кол-во", "quantity")
    def test_date(self):       self._chk("Дата продажи", "date")
    def test_order_date(self): self._chk("Дата заказа покупателем", "order_date")
    def test_tx_type(self):    self._chk("Тип документа", "transaction_type")
    def test_srid(self):       self._chk("Srid", "srid")
    def test_penalties(self):  self._chk("Общая сумма штрафов", "penalties")
    def test_storage(self):    self._chk("Хранение", "storage_fee")
    def test_pvz(self):        self._chk("Возмещение за выдачу и возврат товаров на ПВЗ", "pvz_fee")
    def test_country(self):    self._chk("Страна", "country")
    def test_promo(self):      self._chk("Промокод, %", "promo_discount_pct")
    def test_wibes(self):      self._chk("Скидка Wibes, %", "wibes_discount_pct")
    def test_penalties2(self): self._chk("Общая сумма штрафов", "penalties")
    def test_supply_id(self):  self._chk("Номер поставки", "supply_id")
    def test_sale_method(self):self._chk("Способы продажи и тип товара", "sale_method")
    def test_deductions(self): self._chk("Удержания", "deductions")

class TestTypes(unittest.TestCase):
    def setUp(self): self.e = KnowledgeEngine()
    def test_date_format(self):
        r = self.e.lookup("Дата продажи")
        self.assertEqual(r.data_type, "date")
        self.assertEqual(r.date_format, "%Y-%m-%d")
    def test_int(self):
        self.assertEqual(self.e.lookup("Код номенклатуры").data_type, "int")
    def test_float(self):
        self.assertEqual(self.e.lookup("Вайлдберриз реализовал Товар (Пр)").data_type, "float")
    def test_bool(self):
        self.assertEqual(self.e.lookup("Признак продажи юридическому лицу").data_type, "bool")
    def test_str(self):
        self.assertEqual(self.e.lookup("Название").data_type, "str")

class TestAnalytics(unittest.TestCase):
    def setUp(self): self.e = KnowledgeEngine()
    def test_analytics_fields(self):
        fields = self.e.analytics_fields()
        self.assertGreater(len(fields), 30)
        for f in ("sku","revenue","quantity","date","commission","logistics"):
            self.assertIn(f, fields)
    def test_service_not_analytics(self):
        r = self.e.lookup("Стикер МП")
        self.assertFalse(r.use_in_analytics)
    def test_srid_analytics(self):
        self.assertTrue(self.e.lookup("Srid").use_in_analytics)

class TestQuery(unittest.TestCase):
    def setUp(self): self.e = KnowledgeEngine()
    def test_get_by_target(self):
        self.assertIn("Код номенклатуры", self.e.get_by_target("sku"))
    def test_get_by_category(self):
        self.assertGreater(len(self.e.get_by_category("finance")), 5)
        self.assertGreater(len(self.e.get_by_category("commission")), 3)
    def test_lookup_many(self):
        r = self.e.lookup_many(["Код номенклатуры","Дата продажи","Кол-во"])
        self.assertEqual(r["Код номенклатуры"].target_field, "sku")
        self.assertEqual(r["Дата продажи"].target_field, "date")
    def test_unknown_low_or_none(self):
        r = self.e.lookup("xyz_totally_unknown_zzz")
        if r: self.assertLess(r.confidence, 0.65)
    def test_pdf_search_empty(self):
        self.assertIsInstance(self.e.search_pdf("комиссия"), list)

if __name__ == "__main__":
    unittest.main()

