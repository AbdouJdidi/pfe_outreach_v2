import json
from rich.console import Console
from rich.table import Table
from .db import ranked
def show_report(limit=30):
    rows=ranked(limit); t=Table(title=f'Top {limit} PFE Candidates')
    for c in ['#','Company','Location','Type','Score','Priority','Domains','PFE']: t.add_column(c)
    for i,r in enumerate(rows,1): t.add_row(str(i),r['name'][:28],(r['location'] or 'Unknown')[:18],r['company_type'] or '?',str(r['score']),r['priority'],', '.join(json.loads(r['domains'] or '[]'))[:30],r['pfe_potential'])
    Console().print(t)
    for i,r in enumerate(rows[:10],1): print(f'{i}. {r["name"]}: {r["reasoning"]}')
