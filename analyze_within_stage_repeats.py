#!/usr/bin/env python3
"""Conservative within-stage DPWH title/segment review; never pair NEP with HGAB."""
import csv
import hashlib
import json
import re
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from build_cost_per_km import ROOT,OUT,STATIC
from hgab_matching import normalize,is_fap
from chainage import compare_chainage,compare_tranche,has_directional_conflict,has_structure_identity_conflict,has_bounded_nonoverlap
from location_data.project_location_scope import qualified,location_conflict
from location_data.location_text import geographic_title

STOP=set('construction improvement rehabilitation repair completion of the and in at to for road roads bridge bridges multi purpose building buildings barangay city municipality province project system along concrete concreting flood control drainage'.split())

def scan(rows,stage):
    buckets=defaultdict(list);eligible=[];counts=Counter();pairs=[]
    for r in rows:
        if is_fap(r):counts['fapExcluded']+=1;continue
        if not r.get('primaryTitleTrusted',True):counts['untrustedTitleExcluded']+=1;continue
        title=r['projectName'];base=normalize(geographic_title(title)[0]);q=qualified(title)
        places=bool(q and q['province'] and q['municipality'])
        distinctive=set(base.split())-STOP
        distinctive={t for t in distinctive if not t.isdigit() and len(t)>2}
        if len(distinctive)<3:counts['genericTitleExcluded']+=1;continue
        if places:block=('place',tuple(sorted(q['province'])),tuple(sorted(q['municipality'])))
        elif r.get('office','').strip():block=('office',normalize(r['office']))
        else:counts['unresolvedContextExcluded']+=1;continue
        x={**r,'base':base,'qualifiedContext':places,'distinctive':distinctive}
        eligible.append(x);buckets[(normalize(r.get('pap3')),block)].append(x)
    for members in buckets.values():
        # An inverted title-token index bounds candidate work; no nationwide
        # place-name fuzzy join. Each distinct source occurrence pair evaluated once.
        index=defaultdict(set)
        for i,a in enumerate(members):
            hits=Counter(j for token in a['distinctive'] for j in index[token])
            for j,shared in hits.items():
                if shared<3:continue
                b=members[j];full=normalize(a['projectName'])==normalize(b['projectName'])
                samebase=a['base']==b['base']
                if not samebase:
                    if not (a['qualifiedContext'] and b['qualifiedContext']):continue
                    # A high text ratio cannot override a changed named route
                    # endpoint, barangay, school, river or other scope token.
                    if a['distinctive'] != b['distinctive']:
                        counts['distinctiveScopeTokenVeto']+=1;continue
                    similarity=SequenceMatcher(None,a['base'],b['base'],autojunk=False).ratio()
                    if similarity<.94:continue
                else:similarity=1.0
                if has_bounded_nonoverlap(a['projectName'],b['projectName']):counts['boundedNonoverlapVeto']+=1;continue
                if has_structure_identity_conflict(a['projectName'],b['projectName']):counts['differentBridgeNumberVeto']+=1;continue
                if location_conflict(a['projectName'],b['projectName']) or has_directional_conflict(a['projectName'],b['projectName']):counts['locationOrDirectionVeto']+=1;continue
                if compare_tranche(a['projectName'],b['projectName'])['tranche_conflict']:counts['trancheVeto']+=1;continue
                chain=compare_chainage(a['projectName'],b['projectName'])
                if chain['chainage_status']=='disjoint':counts['disjointChainageVeto']+=1;continue
                kind='Identical normalized full title' if full else 'Similar title with explicit chainage overlap' if chain['overlaps'] else 'Similar title · funded segment unresolved'
                def extract(x):
                    return {k:x.get(k,'') for k in ['id','projectName','pap3','office','amountPesos','sourcePage','sourceVolume','sourceNepId','apiId','sourceEvidence']}
                pairs.append({'stage':stage,'kind':kind,'titleSimilarity':round(similarity,4),'contextEvidence':'Qualified municipality and province agree' if a['qualifiedContext'] and b['qualifiedContext'] else 'Same implementing office only; geographic identity unverified','chainage':chain,'left':extract(b),'right':extract(a)})
            for token in a['distinctive']:index[token].add(i)
    pairs.sort(key=lambda p:(0 if p['chainage']['overlaps'] else 1,0 if p['kind'].startswith('Identical') else 1,-max(p['left']['amountPesos'],p['right']['amountPesos']),p['left']['id'],p['right']['id']))
    summary={'stage':stage,'sourceOccurrences':len(rows),'screenedOccurrences':len(eligible),'candidatePairs':len(pairs),'distinctFlaggedOccurrences':len({x['id'] for p in pairs for x in [p['left'],p['right']]}),'kinds':dict(Counter(p['kind'] for p in pairs)),'positiveOverlapPairs':sum(p['chainage']['overlaps'] for p in pairs),'exclusionsAndVetoes':dict(counts)}
    return summary,pairs

def build():
    baseline=OUT/'nep_dpwh_baseline.json';house=OUT/'hb_nep_comparison_3rd.csv'
    nep=json.loads(baseline.read_text())['data']['data']
    with house.open() as f:hb=[{**r,'id':r['hgab_id'],'amountPesos':int(r['amountPesos'])} for r in csv.DictReader(f)]
    for rows in [nep,hb]:
        if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate source IDs: cannot rank source occurrences')
    summaries=[];pairs=[]
    for stage,rows in [('FY2027 NEP',nep),('FY2027 HGAB 3rd',hb)]:
        summary,found=scan(rows,stage);summaries.append(summary);pairs.extend(found)
    data={'summary':summaries,'pairs':pairs,'method':'Compare distinct allocation occurrence IDs within each stage only. FAPs and untrusted NEP primary titles excluded. Same normalized official PAP and either qualified municipality/province or same implementing office required. At least three shared distinctive nonnumeric title tokens required. Same base title after trailing geographic metadata removal, or ≥0.94 SequenceMatcher similarity with qualified municipality/province AND identical distinctive token sets, produces a candidate. Changed route-endpoint or other distinctive scope tokens veto even when text similarity is high. Different explicit bridge numbers identify different structures and veto a pair, even on the same bypass road. Direction, qualified-location and tranche conflicts veto. Explicit disjoint ranges veto. Printed range endpoints are assumed to be ordered min/max. Mixed bare/plus ranges retain an unknown endpoint: a known maximum at or below another range’s known minimum excludes positive overlap, without resolving length. Other mixed ranges remain incomplete; possible overlap is not certified overlap. No amount-equality requirement. Missing chainage never proves scope overlap.',
          'limits':['Matching allocation occurrences does not establish duplicate contracts, duplicate payment, fraud or authorship. Different engineering components and legitimate amendments can share titles.','Office-only agreement is weaker than site evidence. Unresolved locations are never inferred from similar names.','Pair counts are not project counts: three linked records produce three pairs. Distinct occurrence counts are shown separately; amounts are not summed as loss.','Exact official PAP blocking, trusted-title requirements and conservative location rules miss possible cross-program, paraphrased or unresolved duplicates. No flag is not clearance.','Tranche differences are excluded from this conservative queue, not certified as legitimate. Missing chainage requires source and engineering-scope review.','NEP baseline includes source records outside the API. Its documented source-title confidence limits remain applicable.'],
          'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [baseline,house,ROOT/'location_data/philippine_locations.sqlite']]}
    text=json.dumps(data,ensure_ascii=False,indent=2)+'\n';(OUT/'within_stage_repeats.json').write_text(text);(STATIC/'within-stage-repeats.json').write_text(text)
    return data

def render(data):
    from build_investigation_summary import table,esc
    body='<p>This screen compares NEP with other NEP occurrences, and HGAB 3rd reading with other HGAB 3rd-reading occurrences. It complements the historical GAA screen. Similar titles are candidates for scope review, not established duplicate work. Pair counts and distinct allocation occurrences have different denominators.</p>'
    maxpairs=max((s['candidatePairs'] for s in data['summary']),default=1) or 1
    svg='<svg class="evidence-graphic" viewBox="0 0 900 310" role="img" aria-label="Within-stage similar-title pair counts, separated by NEP and HGAB"><text x="40" y="25">Candidate pairs within each stage · not unique projects</text>'
    for i,s in enumerate(data['summary']):
        h=190*s['candidatePairs']/maxpairs;x=150+i*400
        svg+=f'<rect x="{x}" y="{230-h}" width="140" height="{h}" fill="#087e78"/><text x="{x}" y="{220-h}">{s["candidatePairs"]:,} pairs</text><text x="{x}" y="260">{esc(s["stage"])}</text>'
    body+=svg+'</svg>'+table(['Stage','Source occurrences','Screened occurrences','Candidate pairs','Distinct flagged occurrences','Pairs with explicit range overlap'],[[s['stage'],s['sourceOccurrences'],s['screenedOccurrences'],s['candidatePairs'],s['distinctFlaggedOccurrences'],s['positiveOverlapPairs']] for s in data['summary']])
    for s in data['summary']:
        stage=s['stage'];rows=[p for p in data['pairs'] if p['stage']==stage][:50]
        body+='<h3>'+esc(stage)+' · first 50 review pairs</h3><p>Explicit overlap comes first, followed by identical full titles, then the larger individual allocation. All candidate pairs are available in the downloadable JSON. The CSV exports the displayed pairs.</p>'
        def source(r):return r['id']+' · '+('NEP source p. ' if stage=='FY2027 NEP' else str(r['sourceVolume'])+' · p. ')+str(r['sourcePage'])
        body+=table(['First project · source','Second project · source','Official program','Implementing offices','Individual allocations pesos · first / second','Screening evidence','Stated segment evidence'],[[p['left']['projectName']+' · '+source(p['left']),p['right']['projectName']+' · '+source(p['right']),p['left']['pap3'],p['left']['office']+' / '+p['right']['office'],f'₱{p["left"]["amountPesos"]:,} / ₱{p["right"]["amountPesos"]:,}',p['kind']+' · '+p['contextEvidence'],p['chainage']['chainage_status']+' · '+p['chainage'].get('chainage_overlap','')] for p in rows])
    body+='<h3>Methodology and exclusions</h3><p>'+esc(data['method'])+'</p><ul>'+''.join('<li>'+esc(v)+'</li>' for v in data['limits'])+'</ul>'
    body+=table(['Stage','Excluded records or vetoed candidate comparisons','Count'],[[s['stage'],k,v] for s in data['summary'] for k,v in s['exclusionsAndVetoes'].items()])
    body+='<p><a href="within-stage-repeats.json" download>Download every candidate pair, original titles, source IDs, amounts and input hashes</a></p>'
    return body

if __name__=='__main__':
    print(json.dumps(build()['summary'],indent=2))
