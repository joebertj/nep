"""Prepare NIA master-plan/source evidence and add cross-source views to reports."""
from __future__ import annotations
import csv, gzip, json, math, os, re, struct, subprocess, tempfile, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
OUT=ROOT/'analysis_output'
DATA=ROOT/'data_sources'
NIA_SOURCE_ROOT=Path(os.environ.get('NEP_NIA_SOURCE_ROOT','/Volumes/T5 EVO/nep/data_sources')).expanduser()
FGIS=NIA_SOURCE_ROOT/'FARMLAND GEOGRAPHIC INFORMATION SYSTEM (FGIS)'/'Canal Network Shapefiles'
NIMP=NIA_SOURCE_ROOT/'NATIONAL IRRIGATION MASTER PLAN (NIMP)'
RIMP=NIA_SOURCE_ROOT/'REGIONAL IRRIGATION MASTER PLAN (RIMP)'
RDC=NIA_SOURCE_ROOT/'RDC ENDORSEMENT'
POW=NIA_SOURCE_ROOT/'PROGRAM OF WORKS AND PICTURES (ONGOING UPLOADING)'
WORKBOOK=DATA/'2026-11-10--with geolocation_bettergov-house-bill-2027-nia-projects.xlsx'
PSGC=DATA/'bettergov-psgc-locations.jsonl'

def source_path(path): return str(path.relative_to(NIA_SOURCE_ROOT))

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
STOP={'construction','construct','rehabilitation','repair','improvement','completion','phase','project','program','national','irrigation','administration','nia','system','systems','works','proposed','and','the','for','of','in','at','to','by','with','barangay','brgy'}

def norm(s): return ' '.join(re.findall(r'[a-z0-9]+',str(s or '').casefold()))
def tokens(s): return {t for t in norm(s).split() if len(t)>2 and t not in STOP}

def xlsx_rows(path):
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared=[''.join(t.text or '' for t in si.findall('.//m:t',NS)) for si in root.findall('m:si',NS)]
        sheets=[n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)]
        for sheet in sheets:
            root=ET.fromstring(z.read(sheet))
            for row in root.findall('.//m:sheetData/m:row',NS):
                vals=[]
                for c in row.findall('m:c',NS):
                    v=c.find('m:v',NS); val=v.text if v is not None else ''
                    if c.attrib.get('t')=='s' and val: val=shared[int(val)]
                    vals.append(val)
                yield ' '.join(vals)

def workbook_nia_rows():
    import nia_geolocation_flags
    return nia_geolocation_flags._workbook_rows()

def read_dbf(path):
    b=path.read_bytes(); n=struct.unpack_from('<I',b,4)[0]; header=struct.unpack_from('<H',b,8)[0]; rowlen=struct.unpack_from('<H',b,10)[0]
    fields=[]; off=32
    while off<len(b) and b[off]!=13:
        name=b[off:off+11].split(b'\0')[0].decode('ascii','replace'); typ=chr(b[off+11]); width=b[off+16]; fields.append((name,typ,width)); off+=32
    rows=[]; pos=header
    for _ in range(n):
        rec=b[pos:pos+rowlen]; pos+=rowlen
        if len(rec)<rowlen or rec[0]==42: continue
        cur=1; row={}
        for name,typ,width in fields:
            raw=rec[cur:cur+width].decode('cp1252','replace').strip();cur+=width
            if raw:
                try: row[name]=float(raw) if typ in 'NF' else raw
                except ValueError: row[name]=raw
        rows.append(row)
    return rows

def read_shp(path):
    b=path.read_bytes(); pos=100
    while pos+8<=len(b):
        words=struct.unpack_from('>I',b,pos+4)[0]; size=words*2; content=b[pos+8:pos+8+size];pos+=8+size
        if len(content)<44: continue
        shape=struct.unpack_from('<i',content,0)[0]
        if shape not in (3,13,23): continue
        parts,points=struct.unpack_from('<ii',content,36); p0=44
        if points<2 or parts<1: continue
        starts=list(struct.unpack_from('<'+'i'*parts,content,p0));p0+=4*parts
        coords=[struct.unpack_from('<dd',content,p0+i*16) for i in range(points)]
        starts.append(points)
        for j in range(parts):
            pts=coords[starts[j]:starts[j+1]]
            for a,c in zip(pts,pts[1:]): yield a,c

def seg_dist(a,b,c,d):
    def orient(p,q,r): return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
    def on(p,q,r): return min(p[0],r[0])-1e-9<=q[0]<=max(p[0],r[0])+1e-9 and min(p[1],r[1])-1e-9<=q[1]<=max(p[1],r[1])+1e-9
    if (o1*o2<0 and o3*o4<0) or (abs(o1)<1e-9 and on(a,c,b)) or (abs(o2)<1e-9 and on(a,d,b)) or (abs(o3)<1e-9 and on(c,a,d)) or (abs(o4)<1e-9 and on(c,b,d)): return 0.0
    def ptseg(p,x,y):
        dx,dy=y[0]-x[0],y[1]-x[1]; den=dx*dx+dy*dy
        t=max(0,min(1,((p[0]-x[0])*dx+(p[1]-x[1])*dy)/den)) if den else 0
        return math.hypot(p[0]-x[0]-t*dx,p[1]-x[1]-t*dy)
    return min(ptseg(p,x,y) for p,x,y in ((a,c,d),(b,c,d),(c,a,b),(d,a,b)))

def fgis_analysis(projects):
    systems=[]; feature_n=0; total_len=0.0; area_count=Counter()
    for shp in sorted(FGIS.rglob('*.shp')):
        pairs=list(read_shp(shp)); dbf=shp.with_suffix('.dbf'); attrs=read_dbf(dbf) if dbf.exists() else []
        if not pairs: continue
        xs=[p[0][0] for p in pairs]+[p[1][0] for p in pairs];ys=[p[0][1] for p in pairs]+[p[1][1] for p in pairs]
        length=sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in pairs)
        region=shp.relative_to(FGIS).parts[0];name=shp.parent.name
        area_count[region]+=1; feature_n+=len(attrs);total_len+=length
        systems.append({'name':name,'region':region,'path':source_path(shp),'featureCount':len(attrs),'lengthM':round(length,1),'bounds':[min(xs),min(ys),max(xs),max(ys)],'segments':pairs})
    # Compare source FMR route linework with FGIS canal linework in their declared UTM 51N CRS.
    from build_connectivity_report import utm51
    results=[]
    for p in projects:
        parts=p.get('routeParts') or []
        routes=[]
        for part in parts:
            coords=[utm51(float(x),float(y)) for x,y in part]
            routes.extend(zip(coords,coords[1:]))
        if not routes:
            for key in ('start','end'):
                pair=p.get(key)
                if pair: routes.append((utm51(float(pair[0]),float(pair[1])),)*2)
        if not routes:
            results.append({'id':p.get('id'),'title':p.get('title'),'distanceM':None,'system':'','source':'FGIS canal proximity not assessed · no route coordinates'});continue
        rx=[q[0] for s in routes for q in s];ry=[q[1] for s in routes for q in s]
        rb=[min(rx),min(ry),max(rx),max(ry)];best=float('inf');best_name='';best_region=''
        for system in systems:
            box=system['bounds'];gapx=max(box[0]-rb[2],rb[0]-box[2],0);gapy=max(box[1]-rb[3],rb[1]-box[3],0)
            if math.hypot(gapx,gapy)>1000 or math.hypot(gapx,gapy)>=best: continue
            for canal in system['segments']:
                for road in routes:
                    dist=seg_dist(road[0],road[1],canal[0],canal[1])
                    if dist<best: best=dist;best_name=system['name'];best_region=system['region']
        results.append({'id':p.get('id'),'title':p.get('title'),'region':p.get('region',''),'distanceM':round(best,1) if best<float('inf') else None,'system':best_name,'fgisRegion':best_region,'source':'FGIS canal network · straight-line source route to mapped canal; local coverage only'})
    stats={'source':'NIA Farmland Geographic Information System · canal network shapefiles','crs':'EPSG:32651 (WGS 84 / UTM zone 51N)','shapefiles':len(list(FGIS.rglob('*.shp'))),'usableShapefiles':len(systems),'features':feature_n,'canalLengthKm':round(total_len/1000,1),'regions':dict(sorted(area_count.items()))}
    public_systems=[{k:v for k,v in s.items() if k!='segments'} for s in systems]
    return stats,public_systems,results

def extract_corpus():
    cache=OUT/'nia-plan-text-index.json.gz'
    fingerprint=[]
    for root in (NIMP,RIMP):
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix.lower() in ('.pdf','.xlsx','.xlsm','.csv','.docx'):
                st=p.stat();fingerprint.append([source_path(p),st.st_size,st.st_mtime_ns])
    if cache.exists():
        try:
            with gzip.open(cache,'rt',encoding='utf-8') as f:saved=json.load(f)
            if saved.get('fingerprint')==fingerprint:
                for doc in saved['documents']:doc['tokens']=set(doc.get('tokens',[]))
                return saved['documents']
        except Exception:pass
    docs=[]
    def add(path,region,kind,text):
        text=re.sub(r'\s+',' ',text).strip()
        if text: docs.append({'file':source_path(path),'region':region,'kind':kind,'text':text,'tokens':tokens(text)})
    files=sorted([p for p in NIMP.rglob('*') if p.is_file()])+sorted([p for p in RIMP.rglob('*') if p.is_file()])
    for path in files:
        suf=path.suffix.lower(); rel=path.relative_to(RIMP) if RIMP in path.parents else path.relative_to(NIMP)
        region=rel.parts[0] if len(rel.parts)>1 else 'NATIONAL'
        text=''
        try:
            if suf=='.pdf':
                with tempfile.NamedTemporaryFile(suffix='.txt') as tmp:
                    r=subprocess.run(['gs','-q','-sDEVICE=txtwrite','-o',tmp.name,str(path)],capture_output=True,timeout=75)
                    if r.returncode==0: text=Path(tmp.name).read_text(errors='replace')
            elif suf in ('.xlsx','.xlsm'):
                text=' '.join(xlsx_rows(path))
            elif suf=='.csv': text=path.read_text(errors='replace')
            elif suf=='.docx':
                with zipfile.ZipFile(path) as z:
                    x=ET.fromstring(z.read('word/document.xml'));text=' '.join(v.text or '' for v in x.iter() if v.tag.endswith('}t'))
        except Exception: pass
        if text:
            add(path,region,'NIMP' if NIMP in path.parents else 'RIMP',text)
            docs[-1]['normalized']=norm(text)
    with gzip.open(cache,'wt',encoding='utf-8') as f:
        json.dump({'fingerprint':fingerprint,'documents':[{**doc,'tokens':sorted(doc['tokens'])} for doc in docs]},f,ensure_ascii=False,separators=(',',':'))
    return docs

def close_phrase(text, terms, window=120):
    if not terms: return False
    # All distinctive name tokens must occur close together, in any order.
    positions=[]
    for term in terms:
        m=re.search(r'\b'+re.escape(term)+r'\b',text)
        if not m:return False
        positions.append(m.start())
    return max(positions)-min(positions)<=window

def match_rows(rows,docs):
    out=[]
    places={r['code']:r for r in (json.loads(x) for x in PSGC.read_text().splitlines() if x.strip())}
    for row in rows:
        title=row.get('title') or ''; psgc=(row.get('10-digit PSGC') or '').zfill(10)
        cur=places.get(psgc,{}); region_code=''
        while cur:
            if cur.get('level')=='region':region_code=cur.get('code','')[:2];break
            cur=places.get(cur.get('parent_code'))
        folder={'13':'CAR','01':'R1','02':'R2-MARIIS','03':'R3-UPRIIS','04':'R4A','17':'R4B','05':'R5','06':'R6','07':'R7','08':'R8','09':'R9','10':'R10','11':'R11','12':'R12','16':'R13'}.get(region_code,'')
        prefix=title.split(':',1)[0]
        alias=tokens(prefix)-{'cis','ris','pis','pip','nis','is','sta','st'}
        if len(alias)<2: alias=set()
        hits=[]
        for d in docs:
            if d['kind']=='RIMP' and folder and folder not in d['file'].split('/'):
                continue
            if d['kind']=='RIMP' and not folder: continue
            if not close_phrase(d['normalized'],alias,window=110):continue
            overlap=alias & d['tokens']; score=len(overlap)/max(1,len(alias))
            if len(overlap)>=2 and score>=0.70:
                hits.append({'plan':d['kind'],'region':d['region'],'file':d['file'],'score':round(score,2),'matchedTerms':sorted(overlap)})
        hits.sort(key=lambda x:(-x['score'],x['plan'],x['file']))
        out.append({'id':row.get('id'),'title':title,'psgc':psgc,'municipality':row.get('City/Municipality',''),'province':row.get('Province',''),'program':row.get('program',''),'nimpMatches':[h for h in hits if h['plan']=='NIMP'][:5],'rimpMatches':[h for h in hits if h['plan']=='RIMP'][:8]})
    return out

def filename_candidates(rows,root,label):
    # macOS AppleDouble sidecars (._*) duplicate file names but contain no source document.
    paths=[p for p in root.rglob('*') if p.is_file() and not p.name.startswith('._')]
    out=[]
    for row in rows:
        identity=tokens(row.get('title','').split(':',1)[0])|tokens(row.get('Name',''))
        identity-=STOP|{'cis','ris','pis','pip','nis','is','sta','st','service','repair','restoration'}
        location=tokens(row.get('City/Municipality',''))|tokens(row.get('Province',''))
        hits=[]
        for path in paths:
            pt=tokens(path.stem+' '+path.parent.name)
            overlap=(identity|location)&pt
            # Two project/location terms, or one long distinctive system/place identifier.
            distinctive=[t for t in overlap if len(t)>=7]
            if len(overlap)>=2 or distinctive:
                hits.append({'file':source_path(path),'matchedTerms':sorted(overlap)})
        out.append([{'file':x['file'],'matchedTerms':x['matchedTerms']} for x in sorted(hits,key=lambda x:(-len(x['matchedTerms']),x['file']))[:5]])
    return out

def fgis_fingerprint():
    return [[source_path(p),p.stat().st_size,p.stat().st_mtime_ns] for p in sorted(FGIS.rglob('*.shp'))]

def build():
    missing=[str(p) for p in (FGIS,NIMP,RIMP,RDC,POW) if not p.exists()]
    if missing:
        raise FileNotFoundError('NIA source folders are unavailable. Set NEP_NIA_SOURCE_ROOT to their parent directory. Missing: '+', '.join(missing))
    nia=workbook_nia_rows()
    # The FMR source layer is an independent line dataset used in connectivity section 1.
    source=json.loads((OUT/'connectivity-map-data.json').read_text())
    oldcross=OUT/'nia-masterplan-crosswalk.json'; oldfgis=OUT/'connectivity-fgis-canal-proximity.json'
    current_fgis_fingerprint=fgis_fingerprint()
    if oldcross.exists() and oldfgis.exists():
        previous=json.loads(oldcross.read_text()); fdata=json.loads(oldfgis.read_text())
        if previous.get('fgisFingerprint')==current_fgis_fingerprint:
            fgstats=previous['fgis']; systems=previous['fgisSystems']; fgis_rows=fdata['projects']
        else:
            fgstats,systems,fgis_rows=fgis_analysis(list(source.get('projects',{}).values()))
    else:
        fgstats,systems,fgis_rows=fgis_analysis(list(source.get('projects',{}).values()))
    fgstats['shapefiles']=len(current_fgis_fingerprint)
    fgstats['usableShapefiles']=len(systems)
    docs=extract_corpus()
    matched=match_rows(nia,docs)
    rdc=filename_candidates(nia,RDC,'RDC');powhits=filename_candidates(nia,POW,'POW')
    for i,r in enumerate(matched): r['rdcFileCandidates']=rdc[i];r['powFileCandidates']=powhits[i]
    catalog=[]
    for label,root in [('NIMP',NIMP),('RIMP',RIMP)]:
        for p in sorted(root.rglob('*')):
            if p.is_file(): catalog.append({'plan':label,'region':p.relative_to(root).parts[0] if len(p.relative_to(root).parts)>1 else 'National','file':source_path(p),'type':p.suffix.lower()})
    data={'builtFrom':{'niaWorkbook':str(WORKBOOK.relative_to(ROOT)),'nimpFiles':len([x for x in catalog if x['plan']=='NIMP']),'rimpFiles':len([x for x in catalog if x['plan']=='RIMP']),'rdcFiles':sum(1 for p in RDC.rglob('*') if p.is_file()),'powFiles':sum(1 for p in POW.rglob('*') if p.is_file()),'planDocumentsParsed':len(docs)},'fgis':fgstats,'fgisFingerprint':current_fgis_fingerprint,'fgisSystems':systems,'connectivityProjects':fgis_rows,'niaLineItems':matched,'planSources':catalog}
    for name in ['nia-masterplan-crosswalk.json','connectivity-fgis-canal-proximity.json']:
        payload=data if name.startswith('nia-') else {'source':fgstats,'projects':fgis_rows}
        (OUT/name).write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')
        (STATIC/name).write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')
    return data

def nia_markup(d):
    plans=d['planSources']; nimp=[x for x in plans if x['plan']=='NIMP'];rimp=[x for x in plans if x['plan']=='RIMP']
    catalog=''.join(f'<tr><td>{x["plan"]}</td><td>{x["region"]}</td><td>{x["file"].split("/")[-1]}</td><td>{x["type"] or "folder"}</td></tr>' for x in plans)
    nimp_rows=''.join(f'<tr><td>{x["plan"]}</td><td>{x["region"]}</td><td>{x["file"].split("/")[-1]}</td><td>{x["type"] or "folder"}</td></tr>' for x in nimp)
    rimp_rows=''.join(f'<tr><td>{x["plan"]}</td><td>{x["region"]}</td><td>{x["file"].split("/")[-1]}</td><td>{x["type"] or "folder"}</td></tr>' for x in rimp)
    return f'''<section class="card section" id="nia-document-availability"><h2>FY2027 NIA line items · POW and RDC document availability</h2><p class="sub">The T5 source folders currently contain filename leads for 108 of 1,013 NIA project lines in the Program of Works and Pictures (POW) folder, and no filename leads in the RDC Endorsement folder. These are screening counts based on project-title and location terms in file names; they are not confirmed project-document matches. A file can match multiple lines, and a candidate may be a photo, layout, or other supporting file rather than a POW itself.</p><p class="sub">AppleDouble metadata files (._*) are excluded. Counts reflect the current T5 snapshot and may change as files are uploaded.</p></section><section class="card section" id="nia-masterplans"><h2>National Irrigation Master Plan (NIMP)</h2><p class="sub">Source files supplied in data_sources · {len(nimp)} files. The supplied national set includes the NIMP 2020–2030 abridged plan and primer. Title occurrences alone do not establish project approval or inclusion.</p><div class="tablewrap"><table><thead><tr><th>Plan</th><th>Scope</th><th>Source file</th><th>Format</th></tr></thead><tbody>{nimp_rows}</tbody></table></div></section><section class="card section" id="nia-regional-masterplans"><h2>Regional Irrigation Master Plans (RIMP)</h2><p class="sub">Source files supplied in data_sources · {len(rimp)} files across {len(set(x['region'] for x in rimp))} regional folders. Main plans, annexes and supporting spatial files are included in the inventory.</p><div class="toolbar"><input id="nia-plan-search" type="search" placeholder="Filter region or file"><select id="nia-plan-region"><option value="">All regions</option>{''.join(f'<option>{x}</option>' for x in sorted(set(x['region'] for x in rimp)))}</select></div><div class="tablewrap"><table><thead><tr><th>Plan</th><th>Region / folder</th><th>Source file</th><th>Format</th></tr></thead><tbody id="nia-plan-body">{rimp_rows}</tbody></table></div><p class="sub">The searchable cross-source NIA line-item table, including candidate NIMP/RIMP, RDC and POW file matches, is on <a href="connectivity.html#nia-cross-source">Connectivity · NIA source cross-check</a>.</p></section>'''

def attach_nia(d):
    path=OUT/'nia.html'
    if not path.exists(): return
    html=path.read_text()
    html=re.sub(r'<script id="nia-plan-catalog-filter">.*?</script>','',html,flags=re.S)
    start='<!-- nia-masterplan-sections:start -->';end='<!-- nia-masterplan-sections:end -->'
    html=re.sub(re.escape(start)+r'.*?'+re.escape(end),'',html,flags=re.S)
    html=html.replace('</main>',start+nia_markup(d)+end+'</main>',1)
    js='''<script id="nia-plan-catalog-filter">(()=>{const body=document.getElementById('nia-plan-body'),q=document.getElementById('nia-plan-search'),r=document.getElementById('nia-plan-region');if(!body)return;const all=[...body.rows];function draw(){const term=(q.value||'').toLowerCase(),region=r.value;all.forEach(row=>{const text=row.innerText.toLowerCase();row.hidden=(term&&!text.includes(term))||(region&&!text.includes(region))})}q.addEventListener('input',draw);r.addEventListener('change',draw)})();</script>'''
    html=html.replace('</body>',js+'</body>')
    for dest in (path,STATIC/'nia.html'): dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(html)

def connectivity_markup(d):
    f=d['fgis']; rows=d['niaLineItems']; fg=d['connectivityProjects']
    nimp=sum(bool(x['nimpMatches']) for x in rows); rimp=sum(bool(x['rimpMatches']) for x in rows); rdc=sum(bool(x['rdcFileCandidates']) for x in rows); powc=sum(bool(x['powFileCandidates']) for x in rows)
    fprox=sum(x.get('distanceM') is not None and x['distanceM']<=100 for x in fg)
    return '''<section class="card" id="nia-cross-source"><h2>NIA line items · master-plan, RDC and POW cross-check</h2><p class="note">A text match is a review lead, not proof that the budget line is the same project or formally approved. NIMP/RIMP rows require title text overlap; RDC/POW rows currently use project-title and location terms in filenames. Review the source document before treating a hit as confirmed.</p><div class="stats"><div class="stat"><strong>@@NIA_ROWS@@</strong>NIA workbook rows reviewed</div><div class="stat"><strong>@@NIMP_HITS@@</strong>with NIMP text candidate</div><div class="stat"><strong>@@RIMP_HITS@@</strong>with RIMP text candidate</div><div class="stat"><strong>@@RDC_HITS@@</strong>with RDC filename lead</div><div class="stat"><strong>@@POW_HITS@@</strong>with POW filename lead</div></div><div class="filters"><input id="nia-cross-search" type="search" placeholder="Search project or place"><select id="nia-cross-filter"><option value="all">All NIA rows</option><option value="matched">Any candidate source</option><option value="nimp">NIMP candidate</option><option value="rimp">RIMP candidate</option><option value="rdc">RDC filename lead</option><option value="pow">POW filename lead</option></select></div><p><a href="nia-masterplan-crosswalk.json" download>Download full NIA cross-check JSON</a></p><div class="table-wrap"><table><thead><tr><th>FY2027 NIA line item</th><th>Municipality / province</th><th>NIMP text candidate</th><th>RIMP text candidate</th><th>RDC filename lead · lower confidence</th><th>POW filename lead · lower confidence</th></tr></thead><tbody id="nia-cross-body"></tbody></table></div><p class="note">Matching data: @@DOCS_PARSED@@ NIMP/RIMP document files parsed. Candidate score is the share of distinctive project-title terms present in a plan text source; results require at least two matched terms and a 70% score.</p></section><section class="card" id="fgis-farmland"><h2>FGIS · irrigation canals near FMR routes</h2><p class="note">FGIS supplies mapped canal network lines rather than parcel boundaries. Compared with the existing annual-cropland raster, these lines add an irrigation-infrastructure signal; they do not prove that a farm is served or that a road connects to the canal.</p><div class="stats"><div class="stat"><strong>@@FGIS_FILES@@</strong>source shapefiles (@@FGIS_USABLE@@ with line data)</div><div class="stat"><strong>@@FGIS_FEATURES@@</strong>canal features</div><div class="stat"><strong>@@FGIS_KM@@ km</strong>summed mapped line length</div><div class="stat"><strong>@@FGIS_NEAR@@</strong>FMR routes within 100 m</div></div><p>Measured source-route to canal distances are provided by <a href="connectivity-fgis-canal-proximity.json" download>project-level FGIS proximity JSON</a>. Calculations use the shapefiles’ stated UTM 51N coordinates; only local canal coverage is represented.</p></section><script id="nia-cross-script">fetch('nia-masterplan-crosswalk.json').then(r=>r.json()).then(d=>{const rows=d.niaLineItems||[],body=document.getElementById('nia-cross-body'),q=document.getElementById('nia-cross-search'),f=document.getElementById('nia-cross-filter'),esc=s=>String(s||'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c])),lead=x=>x.length?x.slice(0,3).map(y=>`${esc(y.file.split('/').slice(-1)[0])} · ${Math.round(y.score*100)}% terms`).join('<br>'):'—';function draw(){const term=q.value.toLowerCase(),filter=f.value;const list=rows.filter(x=>{const any=x.nimpMatches.length||x.rimpMatches.length||x.rdcFileCandidates.length||x.powFileCandidates.length;return (!term||`${x.title} ${x.municipality} ${x.province}`.toLowerCase().includes(term))&&(filter==='all'||filter==='matched'&&any||filter==='nimp'&&x.nimpMatches.length||filter==='rimp'&&x.rimpMatches.length||filter==='rdc'&&x.rdcFileCandidates.length||filter==='pow'&&x.powFileCandidates.length)});body.innerHTML=list.map(x=>`<tr><td>${esc(x.title)}</td><td>${esc(x.municipality)} · ${esc(x.province)}</td><td>${lead(x.nimpMatches)}</td><td>${lead(x.rimpMatches)}</td><td>${x.rdcFileCandidates.slice(0,2).map(y=>esc(y.file.split('/').slice(-1)[0])).join('<br>')||'—'}</td><td>${x.powFileCandidates.slice(0,2).map(y=>esc(y.file.split('/').slice(-1)[0])).join('<br>')||'—'}</td></tr>`).join('')||'<tr><td colspan="6">No rows match.</td></tr>'}q.addEventListener('input',draw);f.addEventListener('change',draw);draw()}).catch(()=>{document.getElementById('nia-cross-body').innerHTML='<tr><td colspan="6">Cross-check data could not be loaded. Use the downloadable file link to inspect the source data.</td></tr>'});</script>'''.replace('@@NIA_ROWS@@',f'{len(rows):,}').replace('@@NIMP_HITS@@',f'{nimp:,}').replace('@@RIMP_HITS@@',f'{rimp:,}').replace('@@RDC_HITS@@',f'{rdc:,}').replace('@@POW_HITS@@',f'{powc:,}').replace('@@DOCS_PARSED@@',f"{d['builtFrom']['planDocumentsParsed']:,}").replace('@@FGIS_FILES@@',f"{f['shapefiles']:,}").replace('@@FGIS_USABLE@@',f"{f['usableShapefiles']:,}").replace('@@FGIS_FEATURES@@',f"{f['features']:,}").replace('@@FGIS_KM@@',f"{f['canalLengthKm']:,.0f}").replace('@@FGIS_NEAR@@',f'{fprox:,}')

def attach_connectivity(d):
    path=STATIC/'connectivity.html'
    html=path.read_text()
    html=re.sub(r'<p class="note fgis-inline-note">.*?</p>','',html,flags=re.S)
    html=re.sub(r'<h3>FMR route proximity to NIA FGIS canals</h3>.*?<p><a href="connectivity-fgis-canal-proximity.json" download>Download project-level FGIS proximity data</a></p>','',html,flags=re.S)
    html=re.sub(r'<script id="fgis-route-table-script">.*?</script>','',html,flags=re.S)
    start='<!-- nia-connectivity-sections:start -->';end='<!-- nia-connectivity-sections:end -->'
    html=re.sub(re.escape(start)+r'.*?'+re.escape(end),'',html,flags=re.S)
    html=html.replace('</main>',start+connectivity_markup(d)+end+'</main>',1)
    # Include FGIS evidence beside the existing ESA annual-cropland farm screen in section one.
    insert='<p id="farm-data-status">'
    note=f'<p class="note fgis-inline-note"><strong>FGIS irrigation-network layer:</strong> {d["fgis"]["shapefiles"]:,} canal-system shapefiles ({d["fgis"]["usableShapefiles"]:,} with line data; {d["fgis"]["features"]:,} features; about {d["fgis"]["canalLengthKm"]:,.0f} mapped km) are now included as a separate proximity signal. See the <a href="#fgis-farmland">canal proximity summary</a>. It does not replace or alter cropland density.</p>'
    if insert in html: html=html.replace(insert,note+insert,1)
    fgis_table='<h3>FMR route proximity to NIA FGIS canals</h3><p class="note">Distance from mapped route geometry to the nearest canal line in the FGIS snapshot. Coverage is local and incomplete; this signal is separate from ESA annual-cropland proximity.</p><p><input id="fgis-route-search" type="search" placeholder="Filter FMR, irrigation system or region"></p><div class="table-wrap"><table><thead><tr><th>FMR project</th><th>FGIS canal / system</th><th>FGIS region</th><th class="num">Distance</th></tr></thead><tbody id="fgis-route-rows"></tbody></table></div><p><a href="connectivity-fgis-canal-proximity.json" download>Download project-level FGIS proximity data</a></p>'
    html=html.replace('<div class="stats" id="road-stats">',fgis_table+'<div class="stats" id="road-stats">',1)
    fgis_js="<script id=\"fgis-route-table-script\">fetch('connectivity-fgis-canal-proximity.json').then(r=>r.json()).then(d=>{const rows=d.projects||[],body=document.getElementById('fgis-route-rows'),search=document.getElementById('fgis-route-search'),esc=s=>String(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));function draw(){const q=search.value.toLowerCase(),list=rows.filter(x=>x.distanceM!=null&&(!q||`${x.title} ${x.system} ${x.fgisRegion} ${x.region}`.toLowerCase().includes(q))).sort((a,b)=>a.distanceM-b.distanceM);body.innerHTML=list.slice(0,100).map(x=>`<tr><td>${esc(x.title)}</td><td>${esc(x.system||'No canal within 1 km')}</td><td>${esc(x.fgisRegion)}</td><td class=\"num\">${x.distanceM==null?'—':Number(x.distanceM).toLocaleString('en-PH')+' m'}</td></tr>`).join('')||'<tr><td colspan=\"4\">No local canal proximity match is available.</td></tr>'}search.addEventListener('input',draw);draw()}).catch(()=>{document.getElementById('fgis-route-rows').innerHTML='<tr><td colspan=\"4\">FGIS proximity data is unavailable.</td></tr>'});</script>"
    html=html.replace('</body>',fgis_js+'</body>',1)
    for dest in (path,OUT/'connectivity.html'): dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(html)

if __name__=='__main__':
    d=build();attach_nia(d);attach_connectivity(d)
    print(json.dumps({'fgis':d['fgis'],'niaRows':len(d['niaLineItems']),'planDocsParsed':d['builtFrom']['planDocumentsParsed'],'sourceFiles':d['builtFrom']},indent=2))
