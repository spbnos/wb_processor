"""domain_parser_factory.py — фабрика domain парсеров."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
from classification.canonical_report_registry import CanonicalClassification
from parsers.domain.base_domain_parser import BaseDomainParser, DomainParseResult
from parsers.domain.daily_report_parser import DailyReportParser
from parsers.domain.weekly_parser import WeeklyReportParser
from parsers.domain.ad_cost_parser import AdCostParser
from parsers.domain.stocks_parser import StocksParser
from parsers.domain.recommendations_parser import RecommendationsParser
from parsers.domain.returns_parser import ReturnsParser
from parsers.domain.price_template_parser import PriceTemplateParser
from parsers.domain.paid_storage_parser import PaidStorageParser
from parsers.domain.product_catalog_parser import ProductCatalogParser
from parsers.domain.commission_parser import CommissionParser
from parsers.domain.rating_parser import RatingParser
logger = logging.getLogger(__name__)

_PARSERS: dict[str, BaseDomainParser] = {
    "daily_report":    DailyReportParser(),
    "weekly":          WeeklyReportParser(),
    "ad_cost":         AdCostParser(),
    "stocks":          StocksParser(),
    "recommendations": RecommendationsParser(),
    "returns":         ReturnsParser(),
    "price_template":  PriceTemplateParser(),
    "storage":         PaidStorageParser(),
    "product_catalog": ProductCatalogParser(),
    "commission":      CommissionParser(),
    "rating":          RatingParser(),
}

class DomainParserFactory:
    @classmethod
    def parse(cls, filepath: Path, classification: CanonicalClassification) -> Optional[DomainParseResult]:
        if classification.report_type is None:
            logger.warning(f"[factory] Unknown report type for {filepath.name}")
            return None
        strategy = classification.report_type.parser_strategy
        parser   = _PARSERS.get(strategy)
        if parser is None:
            logger.error(f"[factory] No parser for strategy={strategy!r}")
            return None
        logger.info(f"[factory] {filepath.name} → {strategy} (table={classification.report_type.db_table})")
        return parser.parse(filepath, header_row=classification.header_row)
