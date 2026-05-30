content = open('smart_pipeline.py', encoding='utf-8').read()
old = '''    @staticmethod
    def _infer_category(filepath, sample_df):
        name = filepath.name.lower()
        if any(kw in name for kw in ['sales', 'продаж', 'realization', 'реализ']):
            return 'wb_report'
        if any(kw in name for kw in ['advert', 'рекл', 'campaign', 'кампан']):
            return 'ad'
        return 'external' '''
new = '''    @staticmethod
    def _infer_category(filepath, sample_df):
        name = filepath.name.lower()
        if any(kw in name for kw in ['sales', 'продаж', 'realization', 'реализ', 'детализир', 'ежедневн', 'отчет', 'report']):
            return 'wb_report'
        if any(kw in name for kw in ['advert', 'рекл', 'campaign', 'кампан']):
            return 'ad'
        cols = set(c.lower() for c in sample_df.columns) if sample_df is not None else set()
        wb_cols = {'вайлдберриз реализовал товар (пр)', 'к перечислению продавцу за реализованный товар', 'вознаграждение вайлдберриз (вв), без ндс'}
        if any(c in cols for c in wb_cols):
            return 'wb_report'
        return 'external' '''
if old.strip() in content:
    open('smart_pipeline.py', 'w', encoding='utf-8').write(content.replace(old.strip(), new.strip()))
    print('FIXED category detection')
else:
    import re
    m = re.search(r'def _infer_category.*?return .external.', content, re.DOTALL)
    if m:
        print('Found method:')
        print(m.group())
