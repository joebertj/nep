"""Pure numeric currency formatting for rendered report table cells."""
import html
import re
from decimal import Decimal


def money_header(header):
    # Units, percentages and record counts are not currency values.
    return bool(re.search(r'pesos|₱|allocation|amount|cost|budget',header,re.I)) and not bool(re.search(r'count|lines|items|records|pairs|proposals|offices|districts|share|percent|%|units|formula|method|ratio|variation',header,re.I))


def format_cell(header,value):
    text=str(value)
    if money_header(header) and re.fullmatch(r'-?\d+(?:\.\d+)?',text):
        return '₱'+format(Decimal(text),',f')
    return text


def format_tables(text):
    """Format plain numeric cells under currency headers, preserving data scripts."""
    changed=0
    def table_match(match):
        nonlocal changed
        table=match[0]
        head=re.search(r'<thead\b.*?</thead>',table,re.S)
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
