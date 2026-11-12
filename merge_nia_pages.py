"""Combine detailed irrigation and named NIA project evidence in one public page."""
import hashlib,json,re
from pathlib import Path
from report_hero_module import STYLE,hero
ROOT=Path(__file__).resolve().parent;STATIC=ROOT.parent/'open-data-visualization/static/nep-preview';OUT=ROOT/'analysis_output'
START='<!-- nia-named-content:start -->';END='<!-- nia-named-content:end -->'
SCRIPT_START='<!-- nia-named-scripts:start -->';SCRIPT_END='<!-- nia-named-scripts:end -->'
ARCHIVE_NAMED_START='<!-- nia-archived-named-content:start -->';ARCHIVE_NAMED_END='<!-- nia-archived-named-content:end -->'
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
 if saved is None and (STATIC/'nia-archive.html').exists():
  prior_archive=(STATIC/'nia-archive.html').read_text()
  saved=between(prior_archive,ARCHIVE_NAMED_START,ARCHIVE_NAMED_END)
  if saved is None:
   start=prior_archive.find('<section id="nia-named-projects">')
   end=prior_archive.find('<section class="card"><h2>NEP comparison coverage</h2>')
   if start >= 0 and end > start:saved=prior_archive[start:end]
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
 # The canonical NIA page builder owns its stage-comparison hero.
 # Move the long historical/comparison appendix out of the current NIA page.
 archive_start=donor.find('<section class="card"><h2>NEP comparison coverage</h2>')
 if archive_start < 0: raise ValueError('NIA archive boundary not found')
 archive_content=donor[archive_start:]
 donor=donor[:archive_start]+'<section class="card nia-archive-link"><h2>Older NIA analyses</h2><p>Historical comparisons, the detailed irrigation annex, and supporting tables are archived separately.</p><p><a href="nia-archive.html">Open NIA archive →</a></p></section>'
 donor='<div id="nia-detailed-irrigation">'+donor+'</div>'
 head=named.split('</head>',1)[0]+'</head>'
 head=re.sub(r'<!-- nia-donor-styles:start -->.*?<!-- nia-donor-styles:end -->','',head,flags=re.S)
 styles=''.join(prefix(re.sub(r' id="[^"]+"','',m[0],count=1)) for m in re.finditer(r'<style\b[^>]*>.*?</style>',detail,re.S) if 'uniform-report-menu-style' not in m[0])
 head=head.replace('</head>','<!-- nia-donor-styles:start -->'+styles+'<!-- nia-donor-styles:end --></head>')
 head=re.sub(r'<title>.*?</title>','<title>NIA · irrigation and named projects</title>',head,flags=re.S)
 body_tag=re.search(r'<body\b[^>]*>',named)[0];header=re.search(r'<header\b[^>]*>.*?</header>',named,re.S)[0]
 from uniform_report_menu import NAV as REPORT_NAV
 header=re.sub(r'<h1\b[^>]*>.*?</h1>','<h1>NIA · irrigation and named projects</h1>',header,flags=re.S)
 header=re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',REPORT_NAV,header,count=1,flags=re.S)
 footer=''.join(re.findall(r'<footer\b[^>]*>.*?</footer>',named,re.S))
 # Shared external behaviours and CSV handler run once on the combined DOM.
 external=[];seen=set()
 for m in re.finditer(r'<script\b[^>]*\bsrc="([^"]+)"[^>]*>.*?</script>',named.split('</head>',1)[-1],re.S):
  key=m[1].split('?')[0]
  if key not in seen:external.append(m[0]);seen.add(key)
 csv_handler=re.search(r'<script id="investigation-evidence-script"[^>]*>.*?</script>',named,re.S)
 page=head+body_tag+header+'<main class="wrap">'+donor+'</main>'+(csv_handler[0] if csv_handler else '')+''.join(external)+footer+'</body></html>'
 archive_header=re.sub(r'<h1\b[^>]*>.*?</h1>','<h1>NIA archive · irrigation annex and historical comparisons</h1>',header,flags=re.S)
 archive_head=re.sub(r'<title>.*?</title>','<title>NIA archive · irrigation annex and historical comparisons</title>',head,flags=re.S)
 archive_dependencies=[];dependency_seen=set()
 for script_tag in re.finditer(r'<script\b[^>]*\bsrc="([^"]+)"[^>]*>.*?</script>',detail,re.S):
  dependency=script_tag[1].split('?')[0]
  if dependency not in dependency_seen:
   archive_dependencies.append(script_tag[0]);dependency_seen.add(dependency)
 archive_head=archive_head.replace('</head>',''.join(archive_dependencies)+'</head>')
 archive_page=(archive_head+body_tag+archive_header+'<main class="wrap"><p><a href="nia.html">← Current NIA summary</a></p><div id="nia-archive-sections">'+ARCHIVE_NAMED_START+saved+ARCHIVE_NAMED_END+archive_content+
               '</div></main>'+scripts+donor_scripts+(csv_handler[0] if csv_handler else '')+''.join(external)+footer+'</body></html>')
 from nia_geolocation_flags import render as render_nia_geolocation_flags
 location_flags = render_nia_geolocation_flags()
 nia_audit=json.loads((OUT/'nia_geolocation_audit.json').read_text())
 card=hero(
  'FY2027 NIA schedule · 10 November 2026 workbook',
  f"{nia_audit['sourceRows']:,}",
  'House-bill rows in the location workbook',
  f"{nia_audit['resolvedPsgcRows']:,} / {nia_audit['rowsWithPsgc']:,}",
  'supplied PSGC codes resolve in the current reference',
  [
   ('Station-range rows',f"{nia_audit['stationRangeCandidateRows']:,}",f"{nia_audit['stationRangeSegmentCount']:,} parsed segments"),
   ('Allocation-per-meter screen',f"{nia_audit['stationRangeWithAmountRows']:,} rows",'category-filtered screening ratios'),
  ],
  'PSGC values locate projects administratively, not by surveyed coordinates. Station lengths are inferred from titles, and allocation-per-meter is not a verified unit cost or alignment.'
 )
 page=re.sub(r'<section\b[^>]*id="(?:report-hero|nia-detail-report-hero)"[^>]*>.*?</section>','',page,count=1,flags=re.S)
 page=re.sub(r'<section\b[^>]*id="nia-data-quality-flag"[^>]*>.*?</section>','',page,flags=re.S)
 page=page.replace('<main class="wrap">','<main class="wrap"><section id="report-hero">'+card+'</section>'+location_flags,1)
 flag_style='<style id="nia-data-quality-style"></style>'
 page=re.sub(r'<style id="nia-data-quality-style">.*?</style>','',page,flags=re.S)
 page=page.replace('</head>',flag_style+'</head>',1)
 if 'id="report-hero-style"' not in page:page=page.replace('</head>',STYLE+'</head>',1)
 page=page.replace('repeats.html#nia','repeats-historical.html#nia')
 named_path.write_text(page);(OUT/'nia.html').write_text(page)
 (STATIC/'nia-archive.html').write_text(archive_page);(OUT/'nia-archive.html').write_text(archive_page)
 (OUT/'nia_page_merge.json').write_text(json.dumps({'canonicalPage':'nia.html','detailSource':'nia-irrigation.html','namedSourcePreservedInMarkers':True,'namespacedIds':mapping,'sourceHashes':{'detail':hashlib.sha256(detail.encode()).hexdigest()},'scope':'Presentation merge; project records and allocations are unchanged; the two NIA scopes are not summed.'},indent=2)+'\n')
 # Keep the supplied NIMP/RIMP inventories on the standalone NIA page after merges.
 crosswalk=OUT/'nia-masterplan-crosswalk.json'
 if crosswalk.exists():
  from build_nia_source_sections import attach_nia
  attach_nia(json.loads(crosswalk.read_text()))
 return mapping
if __name__=='__main__':merge()
