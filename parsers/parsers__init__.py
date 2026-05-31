"""parsers package — lazy imports to avoid db dependency when using domain parsers only."""
def __getattr__(name):
    if name in ("ParserEngine","ParseResult","_read_raw"):
        from parsers.parser_engine import ParserEngine, ParseResult, _read_raw
        globals().update({"ParserEngine":ParserEngine,"ParseResult":ParseResult,"_read_raw":_read_raw})
        return globals()[name]
    raise AttributeError(f"module 'parsers' has no attribute {name!r}")
__all__ = ["ParserEngine","ParseResult","_read_raw"]
