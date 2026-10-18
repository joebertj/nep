"""Publish shared report table presentation without modifying source data."""
import hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def publish_assets():
    static=ROOT.parent/'open-data-visualization/static/nep-preview';out=ROOT/'analysis_output';versions={}
    for suffix in ('css','js'):
        raw=(ROOT/f'report_assets/table_readability.{suffix}').read_bytes();name=f'report-table-readability.{suffix}'
        (static/name).write_bytes(raw);(out/name).write_bytes(raw);versions[suffix]=hashlib.sha256(raw).hexdigest()[:12]
    for suffix in ('css','js'):
        raw=(ROOT/f'report_assets/stage_comparison.{suffix}').read_bytes();name=f'nep-hgab-comparison-graphs.{suffix}'
        (static/name).write_bytes(raw);(out/name).write_bytes(raw);versions['comparison_'+suffix]=hashlib.sha256(raw).hexdigest()[:12]
    raw=(ROOT/'report_assets/research_theme.css').read_bytes()
    (static/'research-theme.css').write_bytes(raw);(out/'research-theme.css').write_bytes(raw)
    versions['theme']=hashlib.sha256(raw).hexdigest()[:12]
    return versions

def apply_page(text,versions):
    text=normalize_table_pagination(text)
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
    text=text.replace('</head>',f'<link id="report-table-readability-style" rel="stylesheet" href="report-table-readability.css?v={versions["css"]}"></head>',1)
    text=re.sub(r'<link\b[^>]*\bid="nep-hgab-comparison-style"[^>]*>','',text)
    text=re.sub(r'<script\b[^>]*\bid="nep-hgab-comparison-script"[^>]*>.*?</script>','',text,flags=re.S)
    text=text.replace('</head>',f'<link id="nep-hgab-comparison-style" rel="stylesheet" href="nep-hgab-comparison-graphs.css?v={versions["comparison_css"]}"></head>',1)
    text=text.replace('</body>',f'<script id="nep-hgab-comparison-script" src="nep-hgab-comparison-graphs.js?v={versions["comparison_js"]}"></script></body>',1)
    return text.replace('</body>',f'<script id="report-table-readability-script" src="report-table-readability.js?v={versions["js"]}"></script></body>',1)


def normalize_table_pagination(text):
    """Use ten-row defaults in existing table renderers, retaining their controls.

    Restrict changes to executable inline scripts containing pagination logic;
    chart limits, JSON records, source coordinates and exports stay untouched.
    """
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
