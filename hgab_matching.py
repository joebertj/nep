"""Scope-aware, one-to-one NEP matching for the corrected native HGAB rows."""
from __future__ import annotations
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from chainage import compare_chainage, compare_tranche, has_directional_conflict

ROOT=Path(__file__).resolve().parent
EXACT='Exact normalized title found in NEP'
POTENTIAL='Plausible NEP title counterpart; review scope'
UNMATCHED='No plausible NEP title counterpart; review candidate'
AMBIGUOUS='Multiple or already paired NEP counterparts; review scope'


def normalize(value):
    value=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower()
    value=re.sub(r'\bk\s*(\d+)\s*\+',r'\1+',value)
    value=re.sub(r'\(\s*-\s*(\d+)\s*\)',r'negative \1',value)
    for old,new in [('brgy','barangay'),('rd','road'),('br','bridge'),('ave','avenue'),('st','street')]:
        value=re.sub(r'\b'+old+r'\b',new,value)
    return re.sub(r'[^a-z0-9]+',' ',value).strip()


def title_key(row,title=None):
    key=normalize(title or row.get('projectName'))
    if 'preventive maintenance' in normalize(row.get('pap3')):
        key=re.sub(r'^preventive maintenance(?: along| of)?\s+','',key)
    return key


def nep_amount(row):
    return int(row.get('amountPesos') or round(float(row.get('amount') or 0)*1000))


def load_nep(api_path,trace_path=None):
    api=json.loads(api_path.read_text())['data']['data']
    api_by_id={r.get('code') or r.get('id'):r for r in api}
    if len(api_by_id)!=len(api) or None in api_by_id or '' in api_by_id:
        raise ValueError('NEP API records have duplicate or missing IDs')
    if any(not r.get('projectName') or r.get('amount') is None for r in api):
        raise ValueError('NEP API project title or amount missing')
    if not trace_path:
        return [{**r,'amountPesos':nep_amount(r),'sourceNepId':r.get('code') or r.get('id'),'apiId':r.get('code') or r.get('id'),'primaryTitleTrusted':True,'officialTitleTrusted':False} for r in api],len(api)
    trace=json.loads(trace_path.read_text());source={};anchors={}
    # Read NEP source records only. No upstream House matches are imported.
    for p in trace['projects']:
        n=p.get('nep')
        if n:
            if n['id'] in source and source[n['id']]!=n:
                raise ValueError(f'Conflicting Official NEP record {n["id"]}')
            source[n['id']]=n
            if p.get('api'):
                a=p['api']; actual=api_by_id.get(a['id'])
                if not actual or any(a.get(k)!=actual.get(v) for k,v in [('title','projectName'),('pap','pap3'),('region','region'),('office','office')]) or a['amount_php']!=nep_amount(actual):
                    raise ValueError(f"Trace API snapshot disagrees with local 2027.json: {a['id']}")
                if n['amount_php']!=a['amount_php']:
                    raise ValueError(f"Trace API/Official NEP amount disagreement: {n['id']}")
                if n['id'] in anchors and anchors[n['id']]!=a:
                    raise ValueError(f"Multiple API anchors for Official NEP record {n['id']}")
                anchors[n['id']]=a
    if len(source)!=trace['summary']['stages']['official_nep']['projects']:
        raise ValueError('Official NEP records are incomplete')
    if len({a['id'] for a in anchors.values()})!=len(anchors) or {a['id'] for a in anchors.values()}!=set(api_by_id):
        raise ValueError('Trace API anchors do not provide complete unique coverage of local NEP')
    if sum(n['amount_php'] for n in source.values())!=trace['summary']['stages']['official_nep']['operations_php']:
        raise ValueError('Official NEP row amounts do not reconcile with the trace operation total')
    rows=[]
    for ident,n in source.items():
        a=anchors.get(ident,{})
        actual=api_by_id.get(a.get('id'),{})
        good_pdf=n.get('evidence')=='within_bbox_agreement'
        rows.append({'id':ident,'code':ident,'sourceNepId':ident,'apiId':a.get('id',''),
            'projectName':actual.get('projectName') or n['title'],'officialNepTitle':n['title'],
            'amountPesos':n['amount_php'],'amount':n['amount_php']/1000,'pap1':n.get('program',''),
            'pap3':'Foreign-assisted projects (FAP)' if n.get('zone')=='fap' else n.get('pap',''),'region':a.get('region') or n.get('region',''),
            'office':a.get('office') or n.get('office',''),'sourcePage':n.get('pdf_page'),
            'sourceEvidence':n.get('evidence'),'apiPresence':'paired' if a else 'outside Transparency API',
            'apiPairKind':a.get('pair_kind'),
            'primaryTitleTrusted':bool(a) or good_pdf,
            'officialTitleTrusted':good_pdf and (not a or a.get('pair_kind')=='exact_title_amount')})
    return rows,len(api)


def compatible(a,b):
    left,right=a['projectName'],b['projectName']
    if has_directional_conflict(left,right): return False
    c=compare_chainage(left,right)
    if c['has_current_range'] and c['has_prior_range'] and not c['overlaps']: return False
    pa,pb=normalize(a.get('pap3')),normalize(b.get('pap3'))
    return not(pa and pb and pa!=pb)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nep',type=Path,default=ROOT/'2027.json')
    parser.add_argument('--official-nep-trace',type=Path)
    parser.add_argument('--hb',type=Path,default=ROOT/'hb10858_projects.json')
    parser.add_argument('--out',type=Path,default=ROOT/'analysis_output/hb_nep_comparison.csv')
    args=parser.parse_args();nep,api_count=load_nep(args.nep,args.official_nep_trace)
    payload=json.loads(args.hb.read_text());hb=payload['data']['data']
    variants=[];exact=defaultdict(set);inverted=defaultdict(set)
    stop={'construction','rehabilitation','improvement','road','bridge','barangay','city','municipality','province','along','system','of','the','and','in','to','multi','purpose','building','flood','control'}
    for j,row in enumerate(nep):
        keys={title_key(row),title_key(row,row.get('officialNepTitle'))};variants.append(keys)
        for key in keys:
            for token in set(key.split())-stop: inverted[token].add(j)
        if row.get('primaryTitleTrusted',True):
            exact[title_key(row)].add(j)
        if row.get('officialTitleTrusted'):
            exact[title_key(row,row['officialNepTitle'])].add(j)
    used=set();linked={};suggestions={};unresolved=[]
    for i,row in enumerate(hb):
        candidate_indices=exact.get(title_key(row),set()) | exact.get(title_key(row,row.get('sourceTitle')),set())
        options=[j for j in candidate_indices if j not in used and compatible(row,nep[j])]
        if options:
            j=min(options,key=lambda j:(abs(row['amountPesos']-nep_amount(nep[j])),normalize(row.get('office'))!=normalize(nep[j].get('office')),nep[j]['sourceNepId']))
            used.add(j);linked[i]=(j,1.,EXACT)
        else: unresolved.append(i)
    edges=[]
    for position,i in enumerate(unresolved):
        row=hb[i];key=title_key(row);tokens=set(key.split())-stop;votes=Counter()
        # Global scope search avoids treating Central Office as the location.
        for token in sorted(tokens,key=lambda t:(len(inverted.get(t,[])),t))[:16]:
            for j in inverted.get(token,[]): votes[j]+=1
        scored=[]
        for j,_ in votes.most_common(80):
            if not compatible(row,nep[j]): continue
            score=max(SequenceMatcher(None,key,k,autojunk=False).ratio() for k in variants[j])
            scored.append((score,j))
            if score>=.83: edges.append((score,i,j))
        suggestions[i]=sorted(scored,reverse=True)[:5]
        if position and position%1000==0: print(f'Screened {position:,}/{len(unresolved):,} nonexact HGAB rows',flush=True)
    for score,i,j in sorted(edges,reverse=True):
        if i not in linked and j not in used:
            linked[i]=(j,score,POTENTIAL);used.add(j)
    fields=['comparison','closest_nep_title','title_similarity_pct','closest_nep_office','closest_nep_amount_pesos','match_basis',
        'fiscalYear','region','office','pap3','projectName','amountPesos','sourceVolume','sourcePage','sourceText','reviewStatus',
        'hgab_id','nep_id','nep_api_id','nep_source_page','paired_one_to_one','amount_delta_pesos','tranche_status','chainage_status']
    args.out.parent.mkdir(parents=True,exist_ok=True);counts=Counter();paired=[]
    with args.out.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for i,row in sorted(enumerate(hb),key=lambda x:x[1]['amountPesos'],reverse=True):
            chosen=linked.get(i);hints=suggestions.get(i,[])
            if chosen: j,score,status=chosen
            elif hints:
                score,j=hints[0];status=AMBIGUOUS if score>=.83 else UNMATCHED
            else: j,score,status=None,0.,UNMATCHED
            other=nep[j] if j is not None else None;counts[status]+=1
            c=compare_chainage(row['projectName'],other['projectName'] if other else '')
            t=compare_tranche(row['projectName'],other['projectName'] if other else '')
            writer.writerow({**{f:row.get(f,'') for f in fields if f in row},'comparison':status,
                'closest_nep_title':other['projectName'] if other else '', 'title_similarity_pct':round(score*100,2),
                'closest_nep_office':other.get('office','') if other else '', 'closest_nep_amount_pesos':nep_amount(other) if other else '',
                'match_basis':'Scope-normalized title and compatible PAP/chainage/direction; amount only orders identical occurrences' if status==EXACT else 'Global rare-token title candidates and compatible PAP/chainage/direction; 83% review threshold',
                'hgab_id':row['id'],'nep_id':other['sourceNepId'] if chosen else '', 'nep_api_id':other.get('apiId','') if chosen else '',
                'nep_source_page':other.get('sourcePage','') if other else '', 'paired_one_to_one':bool(chosen),
                'amount_delta_pesos':row['amountPesos']-nep_amount(other) if chosen else '',
                'chainage_status':c['chainage_status'],'tranche_status':t['tranche_status']})
            if chosen: paired.append({'hgabId':row['id'],'nepId':other['sourceNepId'],'apiId':other.get('apiId',''),
                'kind':'exact_scope' if status==EXACT else 'potential','similarity':score,'hgab':row,'nep':other,
                'amountDeltaPesos':row['amountPesos']-nep_amount(other),'chainage':c,'tranche':t})
    summary={'billSource':payload.get('metadata',{}).get('sourceFiles',[]),'nepRecords':len(nep),'transparencyNepRecords':api_count,
        'officialNepSourceTrace':str(args.official_nep_trace) if args.official_nep_trace else None,
        'hbCandidateRecords':len(hb),'counts':dict(counts),'pairedNepRecords':len(used),
        'nepWithoutSelectedCounterpart':len(nep)-len(used),'hbAllocationPesos':sum(r['amountPesos'] for r in hb),
        'comparisonMethod':'Visible HGAB allocations; Official NEP source records augment the independently validated local Transparency snapshot. One-to-one occurrences; abbreviations and maintenance PAP prefixes normalized. Uncorroborated OCR/native-row-ambiguity titles can only support potential matches. Global candidate search checks PAP, direction and chainage compatibility. 83% fuzzy candidates remain provisional; amount alone never identifies a project.',
        'warning':'Unmatched and potential matches require document review; they do not certify insertions or removals. Official NEP text in the supplied trace may contain OCR errors.', 'csv':str(args.out)}
    args.out.with_name(args.out.stem+'_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    mapping={'summary':{k:v for k,v in summary.items() if k!='billSource'},'pairs':paired,
        'hgabWithoutSelectedCounterpart':[r for i,r in enumerate(hb) if i not in linked],
        'nepWithoutSelectedCounterpart':[r for i,r in enumerate(nep) if i not in used]}
    args.out.with_name(args.out.stem+'_mapping.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(mapping['summary'],ensure_ascii=False,indent=2))


if __name__=='__main__': main()
