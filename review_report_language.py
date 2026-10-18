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
NOTICE='''<aside id="report-evidence-notice" role="note"><strong>Evidence limits.</strong> Amounts are extracted budget allocations or proposals, not verified payments, losses or personal receipts. Similar titles, repeated amounts and unmatched records are review leads; they do not establish unlawful conduct. Title-similarity percentages are text scores, not probabilities of identity or wrongdoing. Representative names describe possible geographic coverage, not who proposed, controlled, benefited from or received a project. Parsing, location and scope uncertainties must be checked against cited source pages.</aside>'''
CSS='''<style id="report-evidence-notice-style">#report-evidence-notice{display:block!important;margin:0 0 20px;padding:12px 16px;border-left:4px solid #087e78;background:#eef5f3;color:#28424c;font:14px/1.5 system-ui,sans-serif;max-width:none}</style>'''

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

def apply():
    # Exact editorial phrases only. Never replace source project names,
    # numeric data, matching IDs, or geographic identities.
    builder_paths = sorted(set(ROOT.glob('build_*.py')) | {ROOT/'analyze_fmr_nia_repeats.py', ROOT/'compare_hgab_non_dpwh_nep.py'})
    for path in builder_paths:
        text=path.read_text();updated=text
        for old,new in REPLACEMENTS.items():updated=updated.replace(old,new)
        if updated!=text:path.write_text(updated)
    headline=ROOT/'build_dpwh_hgab_headlines.py'
    text=headline.read_text().replace(':not(#foreign-assisted-review){display:none!important}',':not(#foreign-assisted-review):not(#hgab-investigation-evidence):not(#report-evidence-notice){display:none!important}')
    headline.write_text(text)
    nav=re.search(r'<nav class="report-nav".*?</nav>', (STATIC/'rcs.html').read_text(), re.S)[0]
    congress_link='<a href="congress.html">Congressional District Allocations</a>'
    nav=re.sub(r'<a\b[^>]*href="congress.html"[^>]*>.*?</a>', '', nav, flags=re.S)
    nav=nav.replace('</nav>',congress_link+'</nav>')
    from standardize_nep_hgab_pages import apply as standardize_comparison_scope
    standardize_comparison_scope()
    if (STATIC/'nep-agency-baselines.json').exists():
        from build_nep_stage_sections import apply as apply_nep_sections
        apply_nep_sections(json.loads((STATIC/'nep-agency-baselines.json').read_text()))
    from build_report_heroes import refresh as refresh_heroes
    refresh_heroes()
    from build_repeats_page import build as build_repeats_page
    build_repeats_page()
    # Keep the separately attributed source cross-check current on every rebuild.
    from build_external_reference_review import apply_pages as apply_external_reference
    apply_external_reference()
    from build_reviewed_annex_sections import apply as apply_reviewed_annexes
    apply_reviewed_annexes()
    pages=[]
    for path in sorted(STATIC.glob('*.html')):
        if path.name == 'index.html':continue  # generated summary alias
        if path.name=='congress.html':
            from build_appropriations_comparison import apply_roles_page
            apply_roles_page(path)
        original=text=path.read_text()
        if re.search(r'<nav class="report-nav"', text):
            text=re.sub(r'<nav class="report-nav".*?</nav>', lambda m:nav, text, flags=re.S)
        else:
            text=text.replace('</header>',nav+'</header>',1)
        for old,new in REPLACEMENTS.items():text=text.replace(old,new)
        text=expose_methodology(text)
        if path.name=='congress.html':
            text=re.sub(r'<title>.*?</title>', '<title>Estimated Allocations by Congressional District · HGAB 3rd Reading</title>', text, count=1, flags=re.S)
            text=re.sub(r'<h1\b[^>]*>.*?</h1>', '<h1>Estimated Allocations by Congressional District</h1>', text, count=1, flags=re.S)
        text=text.replace(':not(#foreign-assisted-review){display:none!important}',':not(#foreign-assisted-review):not(#hgab-investigation-evidence):not(#report-evidence-notice){display:none!important}')
        text=re.sub(r'<aside id="report-evidence-notice".*?</aside>','',text,flags=re.S)
        text=re.sub(r'<style id="report-evidence-notice-style">.*?</style>','',text,flags=re.S)
        text=re.sub(r'(<main\b[^>]*>)',lambda m:m[0]+NOTICE,text,count=1)
        text=text.replace('</head>',CSS+'</head>',1)
        path.write_text(text)
        visible=VisibleText();visible.feed(text)
        prose=re.sub(r'\s+',' ',' '.join(visible.parts))
        terms=[]
        for match in re.finditer(r'\b(?:corruption|theft|stolen|steal|fraud|illegal|suspicious|wrongdoing|sponsorship)\b',prose,re.I):
            terms.append(prose[max(0,match.start()-100):match.end()+160])
        pages.append({'page':path.name,'sha256':hashlib.sha256(text.encode()).hexdigest(),'changed':text!=original,
                      'evidenceNotice':True,'remainingSensitiveContexts':terms,
                      'reviewOutcome':'Editorial review: screening labels, source-stage distinctions, attribution limits and sensitive-term contexts reviewed; no legal certification.'})
    report={'scope':'All static NEP preview HTML pages; generated labels also reviewed through source builders and embedded scripts. Source project titles are retained.',
            'pages':pages,'reviewedPages':len(pages),'guarantee':False,
            'limitations':['This is an evidence/editorial review, not jurisdiction-specific legal advice or legal clearance.','Disclaimers do not cure a false or misleading statement. Source correctness and surrounding presentation remain material.','Identifiable-person allegations of unlawful conduct require corroborating records and qualified legal review before publication.'],
            'changes':['Removed unsupported 50/50 probability language.','Clarified geographic attribution and budget allocation versus payment or personal receipt.','Made methodology visible on HGAB page.','HGAB hero rebuilt from current native comparison; obsolete count must not be reused.']}
    from retain_historical_nep_comparisons import apply as retain_historical_comparisons
    retain_historical_comparisons()
    from format_report_currency import apply as apply_currency_format
    apply_currency_format()
    from add_chainage_overlap_dialog import build as add_overlap_dialog
    add_overlap_dialog()
    from uniform_report_menu import apply as apply_uniform_menu
    apply_uniform_menu()
    from congress_source_credits import apply as apply_congress_source_credits
    apply_congress_source_credits()
    from location_data.refresh_table_asset import refresh as refresh_table_asset
    refresh_table_asset()
    from build_project_document_view import build as refresh_project_document_view
    refresh_project_document_view()
    from uniform_report_menu import apply as refresh_document_page_menu
    refresh_document_page_menu()
    from archive_higher_level_analysis import apply as archive_duplicated_overviews
    archive_duplicated_overviews()
    summary=(STATIC/'summary.html').read_text()
    (STATIC/'index.html').write_text(summary)
    (ROOT/'analysis_output/index.html').write_text(summary)
    (ROOT/'analysis_output/report_language_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report

if __name__=='__main__':print(json.dumps({'reviewedPages':apply()['reviewedPages'],'legalGuarantee':False},indent=2))
