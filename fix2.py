import re
content = open('smart_pipeline.py', encoding='utf-8').read()
old = '''def _infer_category(filepath: Path, sample_df: pd.DataFrame) -> str:
        """Простая эвристика определения категории по имени файла."""
        name = filepath.name.lower()
        if any(kw in name for kw in ["sales", "продаж", "realization", "реализ"]):
            return "wb_report"
        if any(kw in name for kw in ["advert", "рекл", "campaign", "кампан"]):
            return "ad"
        return "external"'''
new = '''def _infer_category(filepath: Path, sample_df: pd.DataFrame) -> str:
        name = filepath.name.lower()
        wb_name_keys = ["sales","продаж","realization","реализ","детализир","ежедневн","отчет","report","wb_"]
        if any(kw in name for kw in wb_name_keys):
            return "wb_report"
        if any(kw in name for kw in ["advert","рекл","campaign","кампан"]):
            return "ad"
        if sample_df is not None:
            cols = " ".join(c.lower() for c in sample_df.columns)
            if any(kw in cols for kw in ["вайлдберриз реализовал","к перечислению продавцу","вознаграждение вайлдберриз"]):
                return "wb_report"
        return "external"'''
if old in content:
    open('smart_pipeline.py', 'w', encoding='utf-8').write(content.replace(old, new))
    print('FIXED')
else:
    print('NOT FOUND - trying regex')
    m = re.search(r'def _infer_category.*?return "external"', content, re.DOTALL)
    if m:
        fixed = content[:m.start()] + new + content[m.end():]
        open('smart_pipeline.py', 'w', encoding='utf-8').write(fixed)
        print('FIXED via regex')
