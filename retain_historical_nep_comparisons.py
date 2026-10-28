#!/usr/bin/env python3
"""Retain existing NEP/2nd-reading analyses; never recompute old-stage matches."""
import json,re,subprocess
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parent;STATIC=ROOT.parent/'open-data-visualization/static/nep-preview';OUT=ROOT/'analysis_output'
class End(HTMLParser):
    def __init__(self,text,tag):
        super().__init__();self.tag=tag;self.depth=0;self.end=None;self.text=text;self.starts=[0]
        for m in re.finditer('\n',text):self.starts.append(m.end())
        self.feed(text)
    def handle_starttag(self,t,a):
        if t==self.tag and self.end is None:self.depth+=1
    def handle_endtag(self,t):
        if t==self.tag and self.end is None:
            self.depth-=1
            if self.depth==0:
                line,col=self.getpos();self.end=self.starts[line-1]+col+len('</'+t+'>')
def extract(text,heading):
    pos=text.find(heading)
    if pos<0:return None
    starts=list(re.finditer(r'<(section|div) class="card section"[^>]*>',text[:pos]))
    if not starts:return None
    m=starts[-1];part=text[m.start():];end=End(part,m[1]).end
    return (m.start(),m.start()+end,part[:end]) if end else None

def apply():
    from build_investigation_summary import table,section
    for name,heading in [('nia.html','Potential NEP-to-HGAB project insertions'),('hfep.html','NEP → HGAB facility-level itemization')]:
        p=STATIC/name;s=p.read_text()
        # Take the original section out of the archived wrapper on repeated runs.
        start=s.find('<section id="historical-nep-2nd"')
        if start>=0:
            part=s[start:];end=End(part,'section').end
            old=extract(part[:end],heading)
            if old:s=s[:start]+s[start+end:];saved=old[2]
            else:continue
        else:
            old=extract(s,heading)
            if not old:continue
            saved=old[2];s=s[:old[0]]+s[old[1]:]
        note='<p>Retained earlier NEP → HGAB 2nd-reading analysis. These original results have not been recalculated. They use the earlier matching/extraction scope and are superseded for current findings by the NEP → HGAB 3rd-reading comparison above. Historical figures must not be combined with current totals.</p>'
        archived=section('historical-nep-2nd','Historical analysis · NEP → HGAB 2nd reading',note+saved)
        s=s.replace('</main>',archived+'</main>',1);p.write_text(s)
    # FMR’s corrected page replaced the old envelope-only report. Recover its
    # actual published data once from Git, not by running an old matcher.
    cache=OUT/'fmr_historical_nep_2nd_snapshot.json'
    if not cache.exists():
        revision='912c9a23e';s=subprocess.check_output(['git','-C',str(ROOT.parent/'open-data-visualization'),'show',revision+':static/nep-preview/fmr.html'],text=True)
        m=re.search(r'const FMR_NEP\s*=\s*',s)
        if not m:raise ValueError('Historical FMR snapshot missing')
        rows,_=json.JSONDecoder().raw_decode(s[m.end():]);cache.write_text(json.dumps({'sourceCommit':revision,'scope':'Original published NEP regional-envelope versus HGAB 2nd-reading itemization review; incomplete older House extraction','rows':rows},ensure_ascii=False,indent=2)+'\n')
    d=json.loads(cache.read_text());rows=d['rows'];public=STATIC/'fmr-historical-nep-2nd.json';public.write_text(cache.read_text())
    p=STATIC/'fmr.html';s=p.read_text();start=s.find('<section id="historical-nep-2nd"')
    if start>=0:
        end=End(s[start:],'section').end;s=s[:start]+s[start+end:]
    body='<p>Original published envelope-only NEP → HGAB 2nd-reading review, retained from commit '+d['sourceCommit']+'. No new matching was run. Its 795 House rows totaled ₱14.035375B against the ₱16B NEP envelope. That House extraction was incomplete; the corrected 964-row ledger and detailed NEP baseline above supersede these figures. This historical shortfall is not a budget reduction and these rows were not established insertions.</p>'
    body+=table(['Archived HGAB 2nd-reading line','Archived allocation pesos','Source page as originally recorded','Original schedule context'],[[r['name'],r['amount'],r['page'],r['context']] for r in rows[:25]])
    body+='<p>First 25 original rows shown; the CSV exports these displayed rows. <a href="fmr-historical-nep-2nd.json" download>Download all 795 archived rows and their original provenance</a>.</p>'
    s=s.replace('</main>',section('historical-nep-2nd','Historical analysis · NEP → HGAB 2nd reading',body)+'</main>',1);p.write_text(s)
    p=STATIC/'dpwh-hgab.html';s=p.read_text().replace(':not(#supporting-methodology){display:none!important}',':not(#supporting-methodology):not(#historical-nep-2nd){display:none!important}')
    # The archive builder replaces the historical section with a reference
    # card. Remove prior reference cards before appending the retained section
    # so repeated rebuilds cannot accumulate duplicates at the page footer.
    s=re.sub(r'<section\b(?=[^>]*\bid="historical-nep-2nd-archive-reference")[^>]*>.*?</section>\s*','',s,flags=re.S)
    s=re.sub(r'<h3>Historical analysis · NEP → HGAB 2nd reading</h3>\s*<p>This historical section is now on .*?</p>\s*','',s,flags=re.S)
    start=s.find('<section id="historical-nep-2nd"')
    if start>=0:
        end=End(s[start:],'section').end;s=s[:start]+s[start+end:]
    old=json.loads((STATIC/'dpwh-data.json').read_text());rows=old.get('hbInsertions2nd',[])
    body='<p>Retained pre-existing NEP → HGAB 2nd-reading candidate data. No matcher was run and no new old-stage comparison was generated. These records retain their original comparison statuses and source references. Use the current 3rd-reading analyses above for current findings; do not combine stages as additional allocations. This archived cohort may use an earlier scope or parser version.</p>'
    body+=table(['Archived HGAB 2nd-reading candidate','Archived allocation pesos','Recorded NEP candidate','Original comparison status','Original House source'],[[r['projectName'],r['amountPesos'],r.get('closest_nep_title',''),r['comparison'],r['sourceVolume']+' · p. '+str(r['sourcePage'])] for r in rows[:25]])
    body+='<p>First 25 archived candidates shown. <a href="dpwh-data.json" download>Original data JSON: hbInsertions2nd and hbInsertions2ndSummary retain the complete old cohort and methodology metadata</a>.</p>'
    s=s.replace('</main>',section('historical-nep-2nd','Historical analysis · NEP → HGAB 2nd reading',body)+'</main>',1);p.write_text(s)
    return {'newOldStageMatching':False,'historicalSections':['dpwh-hgab.html','fmr.html','nia.html','hfep.html']}
