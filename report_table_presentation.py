"""Publish shared report table presentation without modifying source data."""
import hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent

BETTERGOV_COLOR_REPLACEMENTS={
    '#087e78':'#0038A8', '#168277':'#0038A8', '#174b55':'#0038A8', '#123944':'#00246A', '#102f3e':'#00246A',
    '#18303b':'#212121', '#28424c':'#212121', '#24434b':'#616161', '#536873':'#616161', '#526773':'#616161',
    '#a7ddd1':'#FCD116', '#66bca8':'#FCD116', '#b9dfd4':'#FCD116', '#b8e5da':'#FCD116', '#e5b64b':'#FCD116', '#f2c968':'#FCD116',
    '#eef5f3':'#EAF0FF', '#f7faf9':'#F5F5F5', '#f8fbfa':'#F5F5F5', '#f1f7f6':'#F5F5F5', '#e7f1ee':'#F5F5F5', '#eaf1ef':'#EAF0FF',
    '#c6dbd6':'#E0E0E0', '#d9e3e1':'#E0E0E0', '#ccdcd8':'#E0E0E0', '#b6c9c4':'#BDBDBD', '#a8bbb6':'#BDBDBD', '#9bb7af':'#BDBDBD', '#9fbab3':'#BDBDBD',
    '#d7e6e4':'#F5F5F5', '#e4efed':'#F5F5F5', '#c0d4d1':'#E0E0E0', '#e0ecea':'#F5F5F5',
    '#28a745':'#0038A8', '#4caf50':'#0038A8', '#17a2b8':'#0038A8', '#007bff':'#0038A8',
}

def apply_bettergov_palette(text):
    """Normalize legacy teal/green report accents to the shared BetterGov palette."""
    if re.search(r'<body\b[^>]*\bclass=["\'][^"\']*\bout-of-place-theme\b',text,re.I):
        return text
    for old,new in BETTERGOV_COLOR_REPLACEMENTS.items():
        text=re.sub(re.escape(old),new,text,flags=re.I)
    return text

def publish_assets():
    static=ROOT.parent/'open-data-visualization/static/nep-preview';out=ROOT/'analysis_output';versions={}
    evidence=(ROOT/'report_assets/project_evidence_details.js').read_bytes()
    for target in (static,out):
        (target/'project-evidence-details.js').write_bytes(evidence)
    evidence_version=hashlib.sha256(evidence).hexdigest()[:12]
    for suffix in ('css','js'):
        raw=(ROOT/f'report_assets/table_readability.{suffix}').read_bytes();name=f'report-table-readability.{suffix}'
        if suffix=='js':raw=raw.replace(b'__EVIDENCE_READER_VERSION__',evidence_version.encode())
        (static/name).write_bytes(raw);(out/name).write_bytes(raw);versions[suffix]=hashlib.sha256(raw).hexdigest()[:12]
    for suffix in ('css','js'):
        raw=(ROOT/f'report_assets/stage_comparison.{suffix}').read_bytes();name=f'nep-hgab-comparison-graphs.{suffix}'
        (static/name).write_bytes(raw);(out/name).write_bytes(raw);versions['comparison_'+suffix]=hashlib.sha256(raw).hexdigest()[:12]
    raw=(ROOT/'report_assets/research_theme.css').read_bytes()
    (static/'research-theme.css').write_bytes(raw);(out/'research-theme.css').write_bytes(raw)
    versions['theme']=hashlib.sha256(raw).hexdigest()[:12]
    tailwind=ROOT.parent/'open-data-visualization/static/css/tailwind.css'
    if not tailwind.exists():raise FileNotFoundError(f'Tailwind stylesheet missing: {tailwind}')
    versions['tailwind']=hashlib.sha256(tailwind.read_bytes()).hexdigest()[:12]
    return versions

def apply_tailwind_link(text,href,version):
    text=re.sub(r'<link\b[^>]*\bid="bettergov-tailwind-style"[^>]*>','',text)
    link=f'<link id="bettergov-tailwind-style" rel="stylesheet" href="{href}?v={version}">'
    return re.sub(r'<head\b[^>]*>',lambda m:m[0]+link,text,count=1)

def _apply_page_presentation(text,versions,page=None):
    from report_currency_module import format_tables
    text,_=format_tables(text)
    if page not in {'dpwh-hgab.html','dpwh-OO2-hgab.html','repeats.html'}:
        text=re.sub(r'<script\b[^>]*id="chainage-overlap-viewer"[^>]*>.*?</script>','',text,flags=re.S)
    text=apply_bettergov_palette(text)
    text=normalize_table_pagination(text,page)
    text=apply_tailwind_link(text,'../css/tailwind.css',versions['tailwind'])
    def body(match):
        tag=match[0]
        if re.search(r'\bclass="',tag):
            return re.sub(r'\bclass="([^"]*)"',lambda m:'class="'+m[1]+('' if 'bettergov-research' in m[1].split() else ' bettergov-research')+'"',tag,count=1)
        return tag[:-1]+' class="bettergov-research">'
    text=re.sub(r'<body\b[^>]*>',body,text,count=1)
    text=re.sub(r'<link\b[^>]*\bid="research-theme-style"[^>]*>','',text)
    text=text.replace('</head>',f'<link id="research-theme-style" rel="stylesheet" href="research-theme.css?v={versions["theme"]}"></head>',1)
    text=re.sub(r'<link\b[^>]*\bid="report-table-readability-style"[^>]*>','',text)
    text=re.sub(r'<script\b[^>]*\bid="report-table-readability-script"[^>]*>.*?</script>','',text,flags=re.S)
    text=re.sub(r'<script\b[^>]*\bsrc=["\'][^"\']*report-table-readability\.js(?:\?[^"\']*)?["\'][^>]*>\s*</script>','',text,flags=re.S)
    text=text.replace('</head>',f'<link id="report-table-readability-style" rel="stylesheet" href="report-table-readability.css?v={versions["css"]}"></head>',1)
    text=re.sub(r'<link\b[^>]*\bid="nep-hgab-comparison-style"[^>]*>','',text)
    text=re.sub(r'<script\b[^>]*\bid="nep-hgab-comparison-script"[^>]*>.*?</script>','',text,flags=re.S)
    text=text.replace('</head>',f'<link id="nep-hgab-comparison-style" rel="stylesheet" href="nep-hgab-comparison-graphs.css?v={versions["comparison_css"]}"></head>',1)
    text=text.replace('</body>',f'<script id="nep-hgab-comparison-script" src="nep-hgab-comparison-graphs.js?v={versions["comparison_js"]}"></script></body>',1)
    return text.replace('</body>',f'<script id="report-table-readability-script" src="report-table-readability.js?v={versions["js"]}"></script></body>',1)


PAGE_TABLE_CONTRACTS={
    'connectivity.html': {'builder':'build_connectivity_report.py','chartBeforeTable':True},
    'cost-per-km-historical.html': {'builder':'build_cost_per_km_historical.py','chartBeforeTable':True},
    'dpwh-hgab.html': {'builder':'build_dpwh_hgab_page.py','chainageViewer':True,'chartBeforeTable':True},
    'dpwh-OO2-hgab.html': {'builder':'build_dpwh_oo2_hgab.py','chainageViewer':True,'chartBeforeTable':True},
    'mpb-historical.html': {'builder':'build_mpb_historical_page.py','chartBeforeTable':True},
    'integrated-district-totals.html': {'builder':'build_integrated_district_totals.py','chartBeforeTable':True},
    'repeats.html': {'builder':'build_repeats_page.py','chainageViewer':True,'chartBeforeTable':True},
    'repeats-historical.html': {'builder':'build_repeats_historical_page.py','chartBeforeTable':True},
}


def check_page_table_contract(page_name, html):
    """Check formatting and behavior for every table emitted by a page builder."""
    import re
    from report_currency_module import money_header
    contract=PAGE_TABLE_CONTRACTS.get(page_name,{'chartBeforeTable':False})
    tables=re.findall(r'<table\b.*?</table>',html,flags=re.I|re.S)
    unformatted=[]
    for table_number,table in enumerate(tables,1):
        head=re.search(r'<thead\b.*?</thead>',table,flags=re.I|re.S)
        if not head:continue
        headers=[re.sub(r'<[^>]+>','',cell).strip() for cell in re.findall(r'<th\b[^>]*>(.*?)</th>',head[0],flags=re.I|re.S)]
        body=table[head.end():]
        for row in re.findall(r'<tr\b.*?</tr>',body,flags=re.I|re.S):
            cells=re.findall(r'<td\b[^>]*>(.*?)</td>',row,flags=re.I|re.S)
            for index,cell in enumerate(cells[:len(headers)]):
                value=re.sub(r'<[^>]+>','',cell).strip().replace(',','')
                if money_header(headers[index]) and re.fullmatch(r'-?\d+(?:\.\d+)?',value):
                    unformatted.append(f'table {table_number}, column {headers[index]!r}')
    if unformatted:raise RuntimeError(f'{page_name}: numeric currency cells are not formatted: {unformatted[:5]}')
    viewer=bool(re.search(r'<script\b[^>]*id="chainage-overlap-viewer"',html,re.I))
    if contract.get('chainageViewer') and not viewer:raise RuntimeError(f'{page_name}: required chainage overlap viewer script is missing')
    table_script=bool(re.search(r'(?:src|href)=["\'][^"\']*report-table-readability\.js(?:\?[^"\']*)?["\']',html,re.I))
    table_style=bool(re.search(r'(?:src|href)=["\'][^"\']*report-table-readability\.css(?:\?[^"\']*)?["\']',html,re.I))
    if not table_script or not table_style:raise RuntimeError(f'{page_name}: shared table presentation CSS and JS are missing')
    css=(Path(__file__).resolve().parent/'report_assets/table_readability.css').read_text(encoding='utf-8')
    js=(Path(__file__).resolve().parent/'report_assets/table_readability.js').read_text(encoding='utf-8')
    wrapper=re.search(r'\.report-table-scroll\s*\{([^}]*)\}',css,re.S)
    no_nested=bool(wrapper and re.search(r'overflow\s*:\s*visible\s*!important',wrapper[1]) and re.search(r'max-height\s*:\s*none\s*!important',wrapper[1]))
    colored=bool(re.search(r'\.report-table-scroll thead th\s*\{[^}]*background\s*:\s*#[0-9a-f]{3,8}',css,re.I|re.S))
    export='report-table-export-json' in js and 'application/json' in js
    navigation="makeNav('top')" in js and "makeNav('bottom')" in js and "report-table-pagination-'+position" in js
    for valid,message in [(no_nested,'shared CSS must prevent nested scrolling'),(colored,'shared CSS must define a colored header'),(export,'shared JS must provide JSON export'),(navigation,'shared JS must provide navigation above and below tables')]:
        if not valid:raise RuntimeError(f'{page_name}: {message}')
    # Only the earliest chart and earliest table matter: if any chart precedes
    # any table, the first chart must precede the first table. Avoid collecting
    # every SVG/plot node and comparing every chart against every table; large
    # reports can contain thousands of inline SVG elements.
    chart_match=re.search(r'<(?:svg|canvas)\b|<[^>]*\b(?:id|class)=["\'][^"\']*\b(?:chart|graph)\b[^"\']*["\'][^>]*>',html,re.I)
    table_match=re.search(r'<table\b',html,re.I)
    chart_before=bool(chart_match and table_match and chart_match.start()<table_match.start())
    if contract.get('chartBeforeTable') and not chart_before:raise RuntimeError(f'{page_name}: add at least one chart above a table')
    return {'page':page_name,'builder':contract.get('builder'),'tables':len(tables),'currencyCellsFormatted':True,'chainageViewer':viewer,'tableStandardModule':True,'noNestedScroll':no_nested,'jsonExport':export,'coloredHeader':colored,'topAndBottomNavigation':navigation,'chartBeforeTable':chart_before}


def apply_page(text,versions=None,page=None):
    """Apply the sole shared table standard, BetterGov presentation and output checks."""
    versions=versions or publish_assets()
    rendered=_apply_page_presentation(text,versions,page)
    if re.search(r'<table\b',rendered,re.I):
        check_page_table_contract(page or 'generated table page',rendered)
    return rendered


def apply_page_table_module(page_name,html):
    """Apply presentation and checks for an owning page builder."""
    versions=publish_assets()
    rendered=_apply_page_presentation(html,versions,page_name)
    contract=check_page_table_contract(page_name,rendered)
    contract['tableAssetVersion']=versions['js']
    return rendered,contract


def normalize_table_pagination(text,page=None):
    """Use ten-row defaults in existing table renderers, retaining their controls.

    Restrict changes to executable inline scripts containing pagination logic;
    chart limits, JSON records, source coordinates and exports stay untouched.
    """
    if page=='cost-per-unit.html':
        return text

    def script(match):
        opening,code,closing=match.groups()
        if re.search(r'\b(?:src|type)\s*=',opening) or not re.search(r'\bpage\b|\bpageSize\b|\bnepSize\b',code,re.I):return match[0]
        code=re.sub(r'\b(pageSize|perPage|nepSize|size)(\s*=\s*)(?:15|20|25|30|40)\b',r'\g<1>\g<2>10',code)
        code=re.sub(r'\bpageSize(\s*:\s*)(?:15|20|25|30|40)\b',r'pageSize\g<1>10',code)
        name=r'(?:[A-Za-z_$][\w$]*[Pp]age|page)'
        code=re.sub(r'\b('+name+r')\s*\*\s*(?:15|20|25|30|40)\b',r'\1*10',code)
        code=re.sub(r'(\('+name+r'\s*\+\s*1\))\s*\*\s*(?:15|20|25|30|40)\b',r'\1*10',code)
        code=re.sub(r'(\b'+name+r'\*10\s*\+)\s*(?:15|20|25|30|40)\b',r'\g<1>10',code)
        code=re.sub(r'\bstart\s*\+\s*(?:15|20|25|30|40)\b','start+10',code)
        code=re.sub(r'(\.length\s*/\s*)(?:15|20|25|30|40)\b',r'\g<1>10',code)
        for script_id,required in [('subtractions-script',"document.getElementById('sub-body-domestic')||document.getElementById('sub-body-fap')"),('allocation-adjustments-script',"document.getElementById('adjust-body')")]:
            if script_id in opening and 'reportSectionGuard' not in code:
                code=code.replace('(()=>{',f'(()=>{{/* reportSectionGuard */if(!({required}))return;',1)
        return opening+code+closing
    return re.sub(r'(<script\b[^>]*>)(.*?)(</script>)',script,text,flags=re.S)
