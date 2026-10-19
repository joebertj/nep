#!/usr/bin/env python3
"""Archive duplicated overviews while keeping every project-level table usable.
Immutable original reports remain in the committed release and private snapshots.
The display adapter waits for legacy report initialization before retiring only
named overview panels; this preserves the old scripts' project-level controls.
"""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis_output';ODV=ROOT.parent/'open-data-visualization';STATIC=ODV/'static/nep-preview'
SITE='https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/'
CONFIG={
 'dpwh.html':{'titles':['Projects by region','Other priority programs by district','District Engineering Office allocation ranking']},
 'dpwh-hgab.html':{'ids':['hgab-headline-breakdowns'],'titles':['Projects by region','Other priority programs by district','District Engineering Office allocation ranking']},
 'dpwh-hgab-comparison.html':{'ids':['other-agency-readings'],'titles':['2nd vs 3rd allocations','Line changes after filters']},
 'fmr.html':{'titles':['Regional allocations · NEP versus HGAB']},
 'hfep.html':{'ids':['hfep-nep-stage-comparison','reviewed-hfep-annex'],'titles':['Allocation counts by facility type','HFEP component allocation mix']},
 'nia-irrigation.html':{'ids':['reviewed-nia-controls']},
 'nia.html':{'ids':['nia-detail-reviewed-nia-controls']},
 'summary.html':{'ids':['summary-neutral']},
}
SCRIPT=r'''(()=>{
const config=__CONFIG__,name=document.currentScript?.dataset.reportPage||location.pathname.split('/').pop()||'index.html',rule=config[name==='index.html'?'summary.html':name];
if(!rule)return;
const retired=new WeakSet();let scheduled=false;
function retire(node){
 if(!node||retired.has(node)||node.id==='upstream-budget-analysis')return;
 retired.add(node);
 for(const canvas of node.querySelectorAll('canvas')){
  try{if(window.Chart?.getChart)window.Chart.getChart(canvas)?.destroy();else if(window.Chart?.instances)Object.values(window.Chart.instances).filter(c=>c.canvas===canvas).forEach(c=>c.destroy());}catch(e){console.warn('Archived chart cleanup',e);}
 }
 // Keep original methodology prose and data downloads available beside the
 // upstream link. Only the overview charts/tables and their controls retire.
 const downloads=[...node.querySelectorAll('a[download]')].map(a=>a.cloneNode(true));
 const methods=[...node.querySelectorAll('p')].filter(p=>/method|scope|uncertain|not (?:proof|evidence)|source|missing|limitation|discrepancy|not.*(?:certif|establish)/i.test(p.textContent)).map(p=>p.cloneNode(true));
 const panel=document.createElement('div');panel.className='archived-analysis-link';
 panel.innerHTML='<p><strong>Higher-level overview archived.</strong> <a href="https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/#compare">Use csiiiv for budget-stage totals and comparisons ↗</a> · <a href="archive/index.html">Archived versions and source revision</a>.</p>';
 if(downloads.length){const p=document.createElement('p');downloads.forEach((a,i)=>{if(i)p.append(' · ');p.append(a)});panel.append(p)}
 if(methods.length){const notes=document.createElement('div');notes.className='archived-supporting-methodology';notes.innerHTML='<h3>Retained source and scope notes</h3>';methods.forEach(p=>notes.append(p));panel.append(notes)}
 node.replaceChildren(panel);
 node.classList.add('archived-overview');
}
function scan(){
 scheduled=false;observer.disconnect();
 (rule.ids||[]).forEach(id=>retire(document.getElementById(id)));
 const titles=new Set(rule.titles||[]);
 document.querySelectorAll('main h2').forEach(h=>{if(titles.has(h.textContent.trim()))retire(h.closest('article,section,.card'))});
 observer.observe(document.querySelector('main')||document.body,{childList:true,subtree:true});
}
const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(scan)}});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scan,{once:true});else scan();
})();'''
def apply():
    from build_investigation_summary import esc
    manifest_path=OUT/'higher_level_archive.json'
    if manifest_path.exists():manifest=json.loads(manifest_path.read_text())
    else:
        revision=subprocess.check_output(['git','-C',str(ODV),'rev-parse','HEAD'],text=True).strip()
        snapshot=ROOT/'data_sources/report_archive'/revision;snapshot.mkdir(parents=True,exist_ok=True)
        records=[]
        for name,rules in CONFIG.items():
            source=f'static/nep-preview/{name}'
            raw=subprocess.check_output(['git','-C',str(ODV),'show',f'{revision}:{source}'])
            (snapshot/name).write_bytes(raw)
            records.append({'page':name,'sha256':hashlib.sha256(raw).hexdigest(),'archivedOverviewSelectors':rules,'immutableSourceUrl':f'https://github.com/bettergovph/open-data-visualization/blob/{revision}/{source}','retention':'Original complete HTML and its committed data/assets are retained at this revision; active project-level tables are not archived.'})
        manifest={'sourceRevision':revision,'upstream':SITE,'pages':records,'policy':'Archive duplicated higher-level presentation, retain all project-level evidence and supporting methodology. The immutable Git revision preserves original report code and data. Local private snapshots preserve original HTML bytes.'}
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    (STATIC/'higher-level-archive.json').write_text(json.dumps(manifest,indent=2)+'\n')
    script=SCRIPT.replace('__CONFIG__',json.dumps(CONFIG,ensure_ascii=False))
    asset=STATIC/'archive-higher-level.js';asset.write_text(script);(OUT/asset.name).write_text(script)
    version=hashlib.sha256(script.encode()).hexdigest()[:12]
    archive=STATIC/'archive';archive.mkdir(exist_ok=True)
    links=''.join('<li><a href="'+r['immutableSourceUrl']+'">'+esc(r['page'])+' · archived source</a><p>'+esc(', '.join(r['archivedOverviewSelectors'].get('titles',[])+r['archivedOverviewSelectors'].get('ids',[])))+'</p></li>' for r in manifest['pages'])
    page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Archived budget overviews</title><style>body{margin:0;font:16px/1.6 system-ui,sans-serif;background:#f3f6f5;color:#18303b}header,main{padding:24px clamp(16px,3vw,48px)}header{background:#102f3e;color:white}a{color:#087e78}header a{color:#b8e5da}li{margin:18px 0}code{overflow-wrap:anywhere}</style></head><body><header><h1>Archived higher-level budget analysis</h1><a href="../summary.html">Project-level investigation leads ←</a></header><main><p>Budget-stage totals, regional/program distributions and overview comparisons now point to <a href="'+SITE+'#overview">csiiiv’s maintained workbench</a>. Project records, repeats, overlap diagrams, engineering and location evidence, cost calculations and supporting methods remain on our active pages.</p><p>The archived source reports and their data are preserved in ODV Git revision <code>'+manifest['sourceRevision']+'</code>. These links open immutable source snapshots, not the current live analysis. Archived results may be superseded by later source corrections.</p><ul>'+links+'</ul><p><a href="../higher-level-archive.json" download>Archive manifest and HTML checksums (JSON)</a></p></main></body></html>'
    (archive/'index.html').write_text(page)
    source_links='<div id="report-source-links"><p><strong>Sources and research records</strong> · <a href="'+SITE+'">csiiiv source workbench ↗</a> · <a href="archive/index.html">Archived higher-level analyses</a></p><p><a href="reviewed-annex-baselines.json" download>Reviewed annex source rows</a> · <a href="reviewed-source-adoption.json" download>Adoption and source-equivalence methodology</a>. Local pages retain project-level records, engineering and location evidence, and reproducible investigation leads.</p></div>'
    for path in STATIC.glob('*.html'):
        if path.name=='index.html':continue
        text=path.read_text();text=re.sub(r'<aside id="upstream-budget-analysis".*?</aside>','',text,flags=re.S)
        text=re.sub(r'<script\b[^>]*src="archive-higher-level\.js[^\"]*"[^>]*></script>','',text)
        text=re.sub(r'<div id="report-source-links"[^>]*>.*?</div>','',text,flags=re.S)
        # Keep existing acknowledgements intact and place the footer after report content.
        footers=re.findall(r'<footer\b[^>]*>.*?</footer>',text,re.S)
        text=re.sub(r'<footer\b[^>]*>.*?</footer>','',text,flags=re.S)
        if footers:
            footers[-1]=footers[-1].replace('</footer>',source_links+'</footer>',1)
            footer=''.join(footers)
        else:footer='<footer class="report-source-footer">'+source_links+'</footer>'
        text=text.replace('</body>',footer+'</body>',1)
        if path.name in CONFIG:text=text.replace('</body>',f'<script src="archive-higher-level.js?v={version}" data-report-page="{path.name}"></script></body>',1)
        path.write_text(text)
        mirror=OUT/path.name
        if mirror.exists():mirror.write_text(text)
    return {'archivedSourceRevision':manifest['sourceRevision'],'pagesWithRetiredOverviews':list(CONFIG),'allProjectLevelTablesRetained':True}
if __name__=='__main__':print(json.dumps(apply(),indent=2))
