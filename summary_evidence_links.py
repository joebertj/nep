"""Direct each summary claim to its supporting evidence, with stable section links."""
import html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;STATIC=ROOT.parent/'open-data-visualization/static/nep-preview';OUT=ROOT/'analysis_output'
TARGETS={
 'rcs':('rcs.html#rcs-statistical-evidence','Uniform allocation and rainfall evidence'),
 'insertions':('dpwh-hgab.html#hgab-insertion','Domestic insertion candidate table'),
 'mpb':('mpb.html#mpb-insertions','MPB insertion candidate table'),
 'repeats':('repeats.html#repeat-hgab-survival','Repeat-candidate HGAB retention evidence'),
 'prices':('repeats.html#dpwh-investigation-evidence','Exact ₱5M clustering statistics'),
 'inspire':('budget-innovations.html#innovation-investigation-evidence','INSPIRE appropriation history'),
 'length-coverage':('cost-matching.html#cost-coverage','Missing-length coverage by category and program'),
 'cost-per-km':('cost-per-km.html#cost-roads','Road high-rate candidate table'),
 'short-printed-ranges':('cost-matching.html#short-segment-evidence','Original-source short-range examples'),
 'hgab-no-nep-counterpart':('dpwh.html#hgab-coverage','HGAB 3rd NEP-counterpart coverage'),
 'hgab-no-listed-documents':('dpwh.html#hgab-coverage','DPWH Transparency document coverage'),
 'hgab-missing-document-types':('dpwh.html#hgab-coverage','POW, photo and RDC attachment coverage'),
}
def enrich_findings(findings):
 for row in findings:
  if row['id'] not in TARGETS:continue
  url,label=TARGETS[row['id']];row['page']=url;row['detailLinks']=[{'page':url,'label':label}]
  if row['id']=='rcs':row['detailLinks'].append({'page':'rcs.html#rcs-stage-evidence','label':'All 199 NEP → HGAB allocation traces'})
  if row['id']=='cost-per-km':row['detailLinks'] += [{'page':'cost-per-km.html#cost-bridges','label':'Bridge high-rate candidate table'},{'page':'cost-per-km.html#length-density-groups','label':'Peer groups and screening methodology'}]
 return findings

def link_cards(text,findings):
 for row in findings:
  url=html.escape(row['page'],quote=True)
  pattern=r'(<article\b[^>]*\bid="lead-'+re.escape(row['id'])+r'"[^>]*>)(.*?)(</article>)'
  def article(m):
   body=m[2]
   body=re.sub(r'(<h2[^>]*>).*?(</h2>)',lambda n:n[1]+'<a href="'+url+'">'+html.escape(row['title'])+'</a>'+n[2],body,count=1,flags=re.S)
   body=re.sub(r'<p(?: class="summary-evidence-links")?><a href="[^"]+">Supporting analysis and source tables[^<]*</a>.*?</p>','',body,flags=re.S)
   body=re.sub(r'<p class="summary-evidence-links">.*?</p>','',body,flags=re.S)
   links=' · '.join('<a href="'+html.escape(r['page'],quote=True)+'">'+html.escape(r['label'])+' →</a>' for r in row['detailLinks'])
   return m[1]+body+'<p class="summary-evidence-links">'+links+'</p>'+m[3]
  text=re.sub(pattern,article,text,flags=re.S)
  title=html.escape(row['title'])
  text=text.replace('<td>'+title+'</td>','<td><a href="'+url+'">'+title+'</a></td>')
 return text

def apply():
 path=STATIC/'summary-data.json'
 if not path.exists():return
 data=json.loads(path.read_text());enrich_findings(data['findings']);serialized=json.dumps(data,ensure_ascii=False,indent=2)+'\n';path.write_text(serialized);(OUT/'investigation_summary.json').write_text(serialized)
 for name in ('summary.html','index.html'):
  p=STATIC/name
  if not p.exists():continue
  text=link_cards(p.read_text(),data['findings']);p.write_text(text)
  if (OUT/name).exists():(OUT/name).write_text(text)
 return [{'id':r['id'],'links':r['detailLinks']} for r in data['findings']]
if __name__=='__main__':print(json.dumps(apply(),indent=2))
