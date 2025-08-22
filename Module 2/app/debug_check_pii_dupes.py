# save as: debug_check_pii_dupes.py
import sys, json, csv
from pathlib import Path

p = Path(sys.argv[1])
rows = []
if p.suffix.lower()=='.jsonl':
    for line in open(p, encoding='utf-8'):
        s=line.strip()
        if s: rows.append(json.loads(s))
else:
    import pandas as pd
    rows = pd.read_csv(p, dtype=str, keep_default_na=False).to_dict(orient='records')

key = lambda r: (r.get('source_path',''), r.get('source_type',''), r.get('container',''), str(r.get('row','')), str(r.get('col','')))
from collections import defaultdict
bykey=defaultdict(list)
for r in rows: bykey[key(r)].append(r)

dupes=[(k,v) for k,v in bykey.items() if k[3] not in ('', 'None') and len(v)>1 and (v[0].get('source_type')=='xlsx' or v[1].get('source_type')=='xlsx')]
print(f"total={len(rows)}, dup_keys={len(dupes)}")
for k,v in dupes[:20]:
    print("DUP", k, "->", [(r.get('pii_type'), r.get('text'), r.get('source_type')) for r in v])
