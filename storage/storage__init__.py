"""storage package — lazy imports to avoid db dependency when using domain_loader only."""
def __getattr__(name):
    if name in ("DataLoader","LoadResult"):
        from storage.data_loader import DataLoader, LoadResult
        globals().update({"DataLoader":DataLoader,"LoadResult":LoadResult})
        return globals()[name]
    if name in ("ErrorHandler","PipelineError","ErrorSeverity"):
        from storage.error_handler import ErrorHandler, PipelineError, ErrorSeverity
        globals().update({"ErrorHandler":ErrorHandler,"PipelineError":PipelineError,"ErrorSeverity":ErrorSeverity})
        return globals()[name]
    raise AttributeError(f"module 'storage' has no attribute {name!r}")
__all__ = ["DataLoader","LoadResult","ErrorHandler","PipelineError","ErrorSeverity"]
