"""Combine detailed irrigation and named NIA project evidence in one public page."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;STATIC=ROOT.parent/'open-data-visualization/static/nep-preview';OUT=ROOT/'analysis_output'
START='<!-- nia-named-content:start -->';END='<!-- nia-named-content:end -->'
SCRIPT_START='<!-- nia-named-scripts:start -->';SCRIPT_END='<!-- nia-named-scripts:end -->'
def between(text,start,end):
 m=re.search(re.escape(start)+'(.*?)'+re.escape(end),text,re.S)
 return m[1] if m else None

def main_content(text):return re.search(r'<main\b[^>]*>(.*?)</main>',text,re.S)[1]
def native_scripts(text):
 result=[]
 body=text.split('</head>',1)[-1]
 for m in re.finditer(r'<script([^>]*)>(.*?)</script>',body,re.S):
  if re.search(r'\bsrc=',m[1]) or 'investigation-evidence-script' in m[1]:continue
  if 'application/json' in m[1]:result.append(m[0]);continue
  result.append('<script>\n(()=>{\n'+m[2]+'\n})();\n</script>')
 return ''.join(result)

def merge():
 named_path=STATIC/'nia.html';detail_path=STATIC/'nia-irrigation.html'
 if not named_path.exists() or not detail_path.exists():return
 named=named_path.read_text();detail=detail_path.read_text()
 saved=between(named,START,END)
 if saved is None:
  content=main_content(named)
  # One lead hero per page; retain the named-scope explanation in ordinary prose.
  lead=re.search(r'<section id="report-hero">(.*?)</section>',content,re.S)
  note=''
  if lead:
   plain=re.sub('<[^>]*>',' ',lead[1]);plain=re.sub(r'\s+',' ',plain).strip()
   note='<p class="note">'+plain+'</p>'
   content=content.replace(lead[0],'')
  content=re.sub(r'<aside id="report-evidence-notice".*?</aside>','',content,flags=re.S)
  saved='<section id="nia-named-projects"><h2>Named NIA projects · a separate comparison scope</h2><p>These named-project allocations and the detailed irrigation annex are different budget slices. Their totals must not be added without reconciling hierarchy.</p>'+note+'</section>'+content
  scripts=native_scripts(named)
 else:scripts=between(named,SCRIPT_START,SCRIPT_END) or ''
 donor=main_content(detail)
 # Prefix every donor ID and its exact script/CSS reference before joining DOMs.
 ids=set(re.findall(r'\bid="([^"]+)"',donor));ids.update(re.findall(r'\bid="([^"]+)"',native_scripts(detail)))
 mapping={value:'nia-detail-'+value for value in ids}
 def prefix(text):
  for old,new in sorted(mapping.items(),key=lambda x:-len(x[0])):
   text=text.replace('id="'+old+'"','id="'+new+'"')
   text=text.replace("'"+old+"'","'"+new+"'").replace('"'+old+'"','"'+new+'"')
   text=re.sub(r'#'+re.escape(old)+r'(?=[\s{,:.#>\[\)\"\']|$)','#'+new,text)
  return text
 donor=prefix(donor);donor_scripts=prefix(native_scripts(detail))
 # Keep the detailed annex hero first; place section jumps after all NIA evidence.
 navigation='<p class="nia-scope-links"><a href="#nia-detailed-irrigation">Detailed irrigation works ↓</a> · <a href="#nia-named-projects">Named NIA projects ↓</a></p>'
 donor='<div id="nia-detailed-irrigation">'+donor+'</div>'
 head=named.split('</head>',1)[0]+'</head>'
 head=re.sub(r'<!-- nia-donor-styles:start -->.*?<!-- nia-donor-styles:end -->','',head,flags=re.S)
 styles=''.join(prefix(re.sub(r' id="[^"]+"','',m[0],count=1)) for m in re.finditer(r'<style\b[^>]*>.*?</style>',detail,re.S) if 'uniform-report-menu-style' not in m[0])
 head=head.replace('</head>','<!-- nia-donor-styles:start -->'+styles+'<!-- nia-donor-styles:end --></head>')
 head=re.sub(r'<title>.*?</title>','<title>NIA · irrigation and named projects</title>',head,flags=re.S)
 body_tag=re.search(r'<body\b[^>]*>',named)[0];header=re.search(r'<header\b[^>]*>.*?</header>',named,re.S)[0]
 header=re.sub(r'<h1\b[^>]*>.*?</h1>','<h1>NIA · irrigation and named projects</h1>',header,flags=re.S)
 footer=''.join(re.findall(r'<footer\b[^>]*>.*?</footer>',named,re.S))
 # Shared external behaviours and CSV handler run once on the combined DOM.
 external=[];seen=set()
 for m in re.finditer(r'<script\b[^>]*\bsrc="([^"]+)"[^>]*>.*?</script>',named.split('</head>',1)[-1],re.S):
  key=m[1].split('?')[0]
  if key not in seen:external.append(m[0]);seen.add(key)
 csv_handler=re.search(r'<script id="investigation-evidence-script"[^>]*>.*?</script>',named,re.S)
 page=head+body_tag+header+'<main class="wrap">'+donor+START+saved+END+navigation+'</main>'+SCRIPT_START+scripts+SCRIPT_END+donor_scripts+(csv_handler[0] if csv_handler else '')+''.join(external)+footer+'</body></html>'
 named_path.write_text(page);(OUT/'nia.html').write_text(page)
 (OUT/'nia_page_merge.json').write_text(json.dumps({'canonicalPage':'nia.html','detailSource':'nia-irrigation.html','namedSourcePreservedInMarkers':True,'namespacedIds':mapping,'sourceHashes':{'detail':hashlib.sha256(detail.encode()).hexdigest()},'scope':'Presentation merge; project records and allocations are unchanged; the two NIA scopes are not summed.'},indent=2)+'\n')
 return mapping
if __name__=='__main__':merge()
