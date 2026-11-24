"""Build compact page-specific SCR lookup files for the shared table enhancer."""
import hashlib
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
OUT=ROOT/'analysis_output'
PAGE_PROGRAMS={
    'documents.html':['dpwh'],'dpwh.html':['dpwh'],'fmr.html':['fmr'],'nia.html':['nia'],
    'dpwh-transparency.html':['dpwh'],'repeats.html':['dpwh','fmr','nia','hfep'],
    'out-of-place.html':['dpwh'],'congress.html':['dpwh','fmr','nia','hfep'],
    'flags.html':['dpwh','fmr','nia','hfep'],'undocumented-hgab.html':['dpwh'],
    'cost-per-km.html':['dpwh','fmr'],'pccp-cost-per-unit.html':['dpwh'],
    'cost-per-unit.html':['dpwh'],'cmpd-cost-per-unit.html':['dpwh'],
    'expectation-vs-reality.html':['dpwh'],'rcs.html':['dpwh'],'mpb.html':['dpwh'],
    'barangay.html':['dpwh'],
}
JSON_REF=re.compile(r'''(?:\bfetch(?:Json)?\s*\(\s*|(?:data-[\w-]+)\s*=\s*)["']([^"']+\.json(?:\?[^"']*)?)["']''',re.I)
SCRIPT_REF=re.compile(r'''<script\b[^>]*\bsrc=["']([^"']+\.js(?:\?[^"']*)?)["']''',re.I)
INLINE_TEXT=re.compile(r'''"(?:title|projectName|project|project_name|projectTitle|house_title|hgabTitle|nepTitle)"\s*:\s*"((?:\\.|[^"\\]){18,})"''',re.I)
TITLE_FIELDS={'title','projectname','project','project_name','projecttitle','house_title','hgabtitle','neptitle','project_name'}

class TableCellText(HTMLParser):
    def __init__(self):
        super().__init__();self.skip=0;self.cell=None;self.values=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}:self.skip+=1
        if tag in {'td','th'} and not self.skip:self.cell=[]
    def handle_endtag(self,tag):
        if tag in {'td','th'} and self.cell is not None:
            self.values.append(' '.join(self.cell));self.cell=None
        if tag in {'script','style'} and self.skip:self.skip-=1
    def handle_data(self,data):
        if self.cell is not None and not self.skip:self.cell.append(data)

def normalize(value):
    return re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower()).strip()

def local_asset(ref):
    ref=ref.split('?',1)[0].split('#',1)[0]
    if (not ref or ref.startswith(('http://','https://','//','data:'))
            or ref.endswith('scr-data.json') or Path(ref).name.startswith('scr-page-')):
        return None
    if ref.startswith('/static/nep-preview/'):
        ref=ref.removeprefix('/static/nep-preview/')
    path=(STATIC/ref).resolve()
    try:path.relative_to(STATIC.resolve())
    except ValueError:return None
    return path if path.is_file() and path.suffix.lower()=='.json' else None

def page_title_texts(page,name):
    texts=[]
    parser=TableCellText();parser.feed(page);texts.extend(parser.values)
    def inline_titles(source):
        for match in INLINE_TEXT.finditer(source):
            try:texts.append(json.loads('"'+match.group(1)+'"'))
            except ValueError:pass
    inline_titles(page)
    refs=set(JSON_REF.findall(page))
    for script in SCRIPT_REF.findall(page):
        # Resolve the script itself; its literal fetch targets become JSON inputs.
        script_name=script.split('?',1)[0]
        if script_name.startswith('/static/nep-preview/'):script_name=script_name.removeprefix('/static/nep-preview/')
        script_path=(STATIC/script_name).resolve()
        try:script_path.relative_to(STATIC.resolve())
        except ValueError:continue
        if script_path.is_file() and script_path.stat().st_size<2_000_000:
            source=script_path.read_text(encoding='utf-8',errors='ignore');inline_titles(source);refs.update(JSON_REF.findall(source))
    seen=set();queue=list(refs)
    while queue:
        ref=queue.pop()
        asset=local_asset(ref)
        if asset is None or asset in seen or asset.stat().st_size>100_000_000:continue
        seen.add(asset)
        raw=asset.read_text(encoding='utf-8',errors='ignore')
        inline_titles(raw)
        try:data=json.loads(raw)
        except (ValueError,TypeError):continue
        def walk(value, key=''):
            if isinstance(value,dict):
                shard_path = value.get('path')
                if isinstance(shard_path, str) and shard_path.endswith('.json'):
                    queue.append(shard_path)
                for k, v in value.items():
                    walk(v, k)
                if (name == 'cost-per-unit.html' and 'code' in value
                        and isinstance(value.get('name'), str)):
                    texts.append(value['name'])
            elif isinstance(value,list):
                for v in value:
                    walk(v, key)
            elif isinstance(value,str):
                if 'shard' in key.lower() and value.endswith('.json'):queue.append(value)
                elif key.lower() in TITLE_FIELDS and len(value)>=18:texts.append(value)
        if asset.name == 'cost-per-km-page-index.json':
            fields = data.get('projectIndexFields', [])
            if 'projectName' in fields:
                title_column = fields.index('projectName')
                texts.extend(row[title_column] for row in data.get('projectIndexRows', []) if len(row) > title_column)
        if asset.name == 'cmpd-cost-per-unit-data.json':
            for files in data.get('candidateShards', {}).values():
                queue.extend(files)
        if asset.name == 'cost-per-unit-index.json' and name == 'cost-per-unit.html':
            queue.extend(data.get('costUnitGroupFiles', {}).values())
            queue.extend(data[key] for key in ('costUnitSummaryFile', 'billboardRowsFile') if data.get(key))
        walk(data)
    return {value for text in texts if len(value := normalize(text)) >= 18}

def build_page_subset(page,filename,scr_data):
    scr_rows=scr_data.get('rows',[])
    programs=set(PAGE_PROGRAMS[filename]);source_texts=page_title_texts(page,filename)
    source_by_prefix={}
    for text in source_texts:source_by_prefix.setdefault(' '.join(text.split()[:3]),[]).append(text)
    aliases={}
    for row in scr_rows:
        if row.get('program') not in programs:continue
        for title in dict.fromkeys((normalize(row.get('house_title')), normalize(row.get('title')))):
            if len(title)>=18:aliases.setdefault(' '.join(title.split()[:3]),[]).append((title,row))
    selected={}
    for prefix,candidates in aliases.items():
        source_candidates=source_by_prefix.get(prefix,[])
        if not source_candidates:continue
        for title,row in candidates:
            if title in source_texts or any(source.startswith(title+' ') for source in source_candidates):
                selected[row['id']]=row
    fields=('id','program','status','title','house_php','senate_php','senate_doc','senate_page')
    rows=[]
    for row in selected.values():
        compact={key:row.get(key) for key in fields}
        if normalize(row.get('house_title'))!=normalize(row.get('title')):
            compact['house_title']=row.get('house_title')
        rows.append(compact)
    summary=scr_data.get('pageSummaries',{}).get(filename)
    return {'rows':rows,'pageSummaries':({filename:summary} if summary else {})},len(source_texts)

def attach_subset_url(page,filename,payload):
    serialized=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
    version=hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:12]
    basename=f'scr-page-{Path(filename).stem}.json'
    for target in (STATIC/basename,OUT/basename):
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(serialized,encoding='utf-8')
    def add_attr(match):
        tag=re.sub(r'\sdata-scr-data-url="[^"]*"','',match.group(0),flags=re.I)
        return tag[:-1]+f' data-scr-data-url="{basename}?v={version}">'
    page=re.sub(r'<body\b[^>]*>',add_attr,page,count=1,flags=re.I)
    return page,{'page':filename,'rows':len(payload['rows']),'bytes':len(serialized),'fullBytes':(STATIC/'scr-data.json').stat().st_size}

def prepare_page(page,filename):
    if filename not in PAGE_PROGRAMS:return page,None
    data=json.loads((STATIC/'scr-data.json').read_text(encoding='utf-8'))
    payload,_=build_page_subset(page,filename,data)
    return attach_subset_url(page,filename,payload)

def refresh_all_pages():
    data=json.loads((STATIC/'scr-data.json').read_text(encoding='utf-8'));results=[]
    script_source=ROOT/'report_assets/scr_stage_column.js'
    script_version=hashlib.sha256(script_source.read_bytes()).hexdigest()[:12]
    script_text=script_source.read_bytes()
    (STATIC/'scr-stage-column.js').write_bytes(script_text);(OUT/'scr-stage-column.js').write_bytes(script_text)
    for filename in PAGE_PROGRAMS:
        path=STATIC/filename
        if not path.is_file():continue
        page=path.read_text(encoding='utf-8')
        page=re.sub(r'<script\b[^>]*\bid="scr-stage-column-script"[^>]*>.*?</script>',
                    f'<script id="scr-stage-column-script" src="scr-stage-column.js?v={script_version}"></script>',page,flags=re.I|re.S)
        payload,_=build_page_subset(page,filename,data)
        page,stats=attach_subset_url(page,filename,payload)
        path.write_text(page,encoding='utf-8');(OUT/filename).write_text(page,encoding='utf-8')
        results.append(stats)
    return results
