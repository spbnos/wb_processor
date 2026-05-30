import re
# Fix 1: StockAggregator - optional columns
content = open('feature_store/aggregator.py', encoding='utf-8').read()
pattern = r'agg = df\.groupby\("sku"\)\.agg\(\{[^}]+\}\)'
match = re.search(pattern, content)
if match:
    print('Found:', match.group()[:100])
    new_code = '''agg_cols = {"quantity": "sum"}
        if "reserved" in df.columns: agg_cols["reserved"] = "sum"
        if "in_transit" in df.columns: agg_cols["in_transit"] = "sum"
        agg = df.groupby("sku").agg(agg_cols)'''
    content = re.sub(pattern, new_code, content)
    open('feature_store/aggregator.py', 'w', encoding='utf-8').write(content)
    print('FIXED aggregator.py')
else:
    print('Pattern not found')
    for i,l in enumerate(content.split('\n'),1):
        if 'groupby' in l and 'sku' in l: print(i, l)
# Fix 2: DataLoader - transactions append not overwrite
content2 = open('storage/data_loader.py', encoding='utf-8').read()
print('transactions append logic:')
for i,l in enumerate(content2.split('\n'),1):
    if 'trans' in l.lower() and ('append' in l or 'count' in l or 'json' in l.lower()): print(i, l)
