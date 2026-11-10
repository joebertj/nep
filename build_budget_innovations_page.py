#!/usr/bin/env python3
"""Refresh the budget innovations hero on its own page."""
import json
import re
from pathlib import Path
from report_hero_module import STYLE, hero, peso

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
OUT=ROOT/'analysis_output'


def build():
    data=json.loads((STATIC/'budget-innovations-data.json').read_text(encoding='utf-8'))
    keywords=data['potentialKeywords']
    potential=sum(x.get('keywordStatus')=='Potential first appearance' for x in keywords)
    revived=sum(x.get('keywordStatus')=='Revived' for x in keywords)
    top=max(keywords,key=lambda row:int(row['pesos']))
    card=hero('FY2027 NEP · exact keyword screen',f'{len(keywords)} terms',
        'potential first appearances or revived terms',peso(int(top['pesos'])),
        f"largest keyword-linked allocation · {top['keyword']}",[
            ('Potential first appearances',str(potential),'no exact match in local FY2020–FY2025 GAA text'),
            ('Revived terms',str(revived),'seen in FY2020–FY2022 only')],
        'Keyword-linked allocations may overlap and do not prove a new project. Terms are prompts for line-item review; this local archive starts in FY2020.')
    path=STATIC/'budget-innovations.html'
    page=path.read_text(encoding='utf-8')
    page=re.sub(r'<section\b[^>]*class="impact"[^>]*>.*?</section>','',page,count=1,flags=re.S)
    wrapper='<section id="report-hero"><div id="budget-hero-bindings" hidden><span id="headline"></span><span id="potentialCount"></span><span id="revivedCount"></span></div>'+card+'</section>'
    if re.search(r'<section\b[^>]*id="report-hero"',page):
        page=re.sub(r'<section\b[^>]*id="report-hero"[^>]*>.*?</section>',wrapper,page,count=1,flags=re.S)
    else:
        page=re.sub(r'(<main\b[^>]*>)',lambda m:m[1]+wrapper,page,count=1)
    if 'id="report-hero-style"' not in page:
        page=page.replace('</head>',STYLE+'</head>',1)
    from investigation_page_sections import apply_owned_sections
    page=apply_owned_sections(page,'budget-innovations.html')
    from report_table_presentation import apply_page_table_module
    page,_=apply_page_table_module('budget-innovations.html',page)
    from uniform_report_menu import apply_page as apply_uniform_menu
    page=apply_uniform_menu(page,'budget-innovations.html')
    path.write_text(page,encoding='utf-8')
    mirror=OUT/path.name
    if mirror.exists():mirror.write_text(page,encoding='utf-8')
    return {'page':path.name,'keywordTerms':len(keywords),'potentialFirstAppearances':potential,'revivedTerms':revived}


if __name__=='__main__':
    print(json.dumps(build(),ensure_ascii=False))
