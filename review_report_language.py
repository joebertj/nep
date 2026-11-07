#!/usr/bin/env python3
"""Apply evidence wording and inventory report text; no legal-clearance guarantee."""
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
REPLACEMENTS={
    'The chair and vice-chair labels alone do not establish majority/minority alignment.':'A roster title alone does not establish political alignment.',
    'Committee membership, chairmanship and participation in a prior-year bicam are not used to infer FY2027 conferee status.':'Membership in a different body or participation in a prior-year conference does not establish participation in the FY2027 bicam.',
    'ambiguous 50/50 signals':'tranche differences requiring scope review',
    'ambiguous scope signals (no probability estimated)':'tranche differences requiring scope review',
    'an ambiguous scope signal (no probability estimated)':'a tranche difference requiring scope review',
    'a 50/50 signal':'a tranche difference requiring scope review',
    'a 50/50 review signal':'a tranche difference requiring scope review',
    'tranche differs (50/50 signal)':'tranche differs (scope review needed)',
    'Tranche split (50/50)':'Tranche difference (scope review needed)',
    'Congressional allocations with a clear district location':'Estimated Allocations by Congressional District',
    'DPWH allocations attributed to congressional districts':'Estimated Allocations by Congressional District',
    'Congressional District Allocations · HGAB 3rd Reading':'Estimated Allocations by Congressional District · HGAB 3rd Reading',
    '3rd-reading candidate matches by confidence':'3rd-reading candidate matches by title-screen class',
    'allocation across the review shortlist':'HGAB allocation across the candidate shortlist; not alleged losses',
}
GENERAL_DISCLAIMER=('This site is updated as additional source documents are ingested and reviewed. Its records and calculations are preliminary and open to correction. Additional documents, stakeholder input, and independent review can surface missing information, errors, or context and improve accuracy over time; they may support more complete calculations but do not by themselves verify a record. Inviting people to examine the underlying sources and share corrections is part of the purpose of this work. These are preliminary, document-based observations, not allegations or findings that any person, office, contractor or other entity acted unlawfully. A flag, unmatched record, repeated amount or title, price or location outlier, or missing document is a prompt for review; it does not establish intent, responsibility, benefit, overpayment, duplicate scope or wrongdoing. Names and geographic or district associations indicate possible coverage only, not sponsorship, authorship, control, receipt or personal involvement. Source documents, data completeness, parsing, matching, categories, timing and boundaries may affect results. Verify cited primary records and seek relevant context before drawing or publishing conclusions.')
UPDATE_NOTE='This site is updated as additional source documents are ingested and reviewed. Its records and calculations are preliminary and open to correction. Additional documents, stakeholder input, and independent review can surface missing information, errors, or context and improve accuracy over time; they may support more complete calculations but do not by themselves verify a record. Inviting people to examine the underlying sources and share corrections is part of the purpose of this work.'
NOTICE=f'''<aside id="report-evidence-notice" class="report-disclaimer" role="note"><strong>Disclaimer.</strong> {GENERAL_DISCLAIMER}</aside>'''

def standardize_disclaimer(text):
    """Keep each report's scope text, add the common limit, and share one style."""
    pattern=re.compile(r'(<aside\b[^>]*>)(.*?<strong>(?:Disclaimer|Evidence limits)\.</strong>.*?)(</aside>)',re.S)
    match=pattern.search(text)
    if match:
        opening,body,closing=match.groups()
        if not re.search(r'\bclass\s*=\s*["\'][^"\']*\breport-disclaimer\b',opening):
            if re.search(r'\bclass\s*=',opening):
                opening=re.sub(r'\bclass\s*=\s*(["\'])(.*?)\1',lambda m:'class='+m[1]+(m[2]+' report-disclaimer').strip()+m[1],opening,count=1)
            else:opening=opening[:-1]+' class="report-disclaimer">'
        body=body.replace('<strong>Evidence limits.</strong>','<strong>Disclaimer.</strong>',1)
        if 'This site is updated as additional source documents are ingested' not in body and 'These are preliminary, document-based observations' in body:
            body += '<p>'+UPDATE_NOTE+'</p>'
        elif 'These are preliminary, document-based observations' not in body and 'These archived materials are preliminary, document-based observations' not in body:
            body += '<p>'+GENERAL_DISCLAIMER+'</p>'
        text=text[:match.start()]+opening+body+closing+text[match.end():]
    else:
        text=re.sub(r'(<main\b[^>]*>)',lambda m:m[0]+NOTICE,text,count=1)
    link='<link rel="stylesheet" href="report-disclaimer.css?v=20261029-disclaimer1">'
    if link not in text:text=text.replace('</head>',link+'</head>',1)
    return text

class VisibleText(HTMLParser):
    def __init__(self):super().__init__();self.hidden=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}:self.hidden+=1
    def handle_endtag(self,tag):
        if tag in {'script','style'}:self.hidden=max(0,self.hidden-1)
    def handle_data(self,value):
        if not self.hidden:self.parts.append(value)

def expose_methodology(text):
    # Keep inherited NEP tables on the patterns page, but expose their
    # supporting explanations, source footer and previous-reading archive.
    if 'data-page="insertions"' in text:
        text=re.sub(r'<section id="supporting-methodology"[^>]*>.*?</section>', '', text, flags=re.S)
        rule=re.search(r'body\[data-page="insertions"\] main>[^{}]+\{display:none!important\}',text)
        if rule:
            allowed=set(re.findall(r':not\(#([^)]*)\)',rule[0]))
            notes=[]
            for section in re.finditer(r'<section\b([^>]*)>(.*?)</section>',text,re.S):
                attrs,body=section.groups()
                identifier=re.search(r'\bid="([^"]+)"',attrs)
                if identifier and identifier[1] in allowed:continue
                heading=re.search(r'<h2\b[^>]*>(.*?)</h2>',body,re.S)
                paragraphs=re.findall(r'<p\b[^>]*>.*?</p>',body,re.S)
                paragraphs=[p for p in paragraphs if 'rep-note' not in p and not re.search(r'<p[^>]*>\s*</p>',p)]
                if heading and paragraphs:
                    paragraphs=[re.sub(r'\s+id="[^"]*"','',p) for p in paragraphs]
                    notes.append('<h3>'+heading[1]+'</h3>'+''.join(paragraphs))
            if notes:
                appendix='<section id="supporting-methodology" class="card section"><h2>Supporting methodology · NEP baseline screens</h2><p class="sub">These explanations describe the NEP baseline screens on the <a href="dpwh.html">DPWH patterns page</a>. They are distinct from the HGAB insertion and removal comparison above.</p>'+''.join(notes)+'</section>'
                text=text.replace('</main>',appendix+'</main>',1)
            # Hide only inherited pattern sections; never blanket-hide source
            # footers, archives, notices or future methodological elements.
            replacement=re.sub(r'main>(?:section)?', 'main>section', rule[0])
            if ':not(#supporting-methodology)' not in replacement:
                replacement=replacement.replace('{display:none',':not(#supporting-methodology){display:none')
            text=text.replace(rule[0],replacement)
    text=re.sub(r'<details\b([^>]*)>',lambda m:'<details'+m[1]+('' if re.search(r'\bopen\b',m[1]) else ' open')+'>',text)
    return text

def apply_page_editorial(text,page):
    """Apply shared editorial language to HTML in memory for one page build."""
    for old,new in REPLACEMENTS.items():
        text=text.replace(old,new)
    text=expose_methodology(text)
    if page=='congress.html':
        text=re.sub(r'<title>.*?</title>', '<title>Estimated Allocations by Congressional District · HGAB 3rd Reading</title>', text, count=1, flags=re.S)
        text=re.sub(r'<h1\b[^>]*>.*?</h1>', '<h1>Estimated Allocations by Congressional District</h1>', text, count=1, flags=re.S)
    text=text.replace(':not(#foreign-assisted-review){display:none!important}',
                      ':not(#foreign-assisted-review):not(#hgab-investigation-evidence):not(#report-evidence-notice){display:none!important}')
    if page!='budget-trivia.html':
        text=standardize_disclaimer(text)
    return text


def apply():
    """Compatibility entry point; use apply_page_editorial inside page builders."""
    return {'mode':'module-only','pageWrites':0,
            'instruction':'The owning page builder should pass its HTML through apply_page_editorial.'}

if __name__=='__main__':print(json.dumps(apply(),indent=2))
