#!/usr/bin/env python3
"""Format numeric money cells without changing source amounts or CSV payloads."""
import html
import json
import re
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

def money_header(header):
    # Units, percentages and record counts are not currency values.
    return bool(re.search(r'pesos|₱|allocation|amount|cost|budget',header,re.I)) and not bool(re.search(r'count|lines|items|records|pairs|proposals|offices|districts|share|percent|%|units|formula|method|ratio|variation',header,re.I))

def format_cell(header,value):
    text=str(value)
    if money_header(header) and re.fullmatch(r'-?\d+(?:\.\d+)?',text):
        return '₱'+format(Decimal(text),',f')
    return text

def format_tables(text):
    changed=0
    def table_match(match):
        nonlocal changed
        table=match[0];head=re.search(r'<thead\b.*?</thead>',table,re.S)
        if not head:return table
        headers=[html.unescape(re.sub(r'<[^>]+>','',h)).strip() for h in re.findall(r'<th\b[^>]*>(.*?)</th>',head[0],re.S)]
        def row_match(row):
            index=0
            def cell_match(cell):
                nonlocal index,changed
                i=index;index+=1
                if i>=len(headers):return cell[0]
                value=cell[2].strip()
                formatted=format_cell(headers[i],value)
                if formatted==value:return cell[0]
                changed+=1
                return cell[1]+html.escape(formatted)+cell[3]
            return re.sub(r'(<td\b[^>]*>)([^<]*)(</td>)',cell_match,row[0])
        return table[:head.end()]+re.sub(r'<tr\b.*?</tr>',row_match,table[head.end():],flags=re.S)
    return re.sub(r'<table\b.*?</table>',table_match,text,flags=re.S),changed

def apply():
    report=[]
    for path in sorted(STATIC.glob('*.html')):
        text,count=format_tables(path.read_text());path.write_text(text)
        mirror=ROOT/'analysis_output'/path.name
        if mirror.exists():mirror.write_text(text)
        report.append({'page':path.name,'formattedCurrencyCells':count})
    doc={'policy':'Numeric cells under currency headers display ₱ and thousands separators. Decimal places, signs, source amounts, column units and CSV payloads are preserved. Counts and percentages are excluded.','pages':report}
    (ROOT/'analysis_output/report_currency_review.json').write_text(json.dumps(doc,indent=2)+'\n')
    return doc
if __name__=='__main__':print(json.dumps(apply(),indent=2))
