#!/usr/bin/env python3
"""Screen every FY2027 hearing topic against locally available budget-stage project extracts.

Outputs candidate leads only. This lexical screen does not establish project identity or causal influence.
"""
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data_sources' / 'budget_hearings_fy2027'
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
ANNEX_A = ROOT / 'data_sources/senate-2027-dataset/senate-2027-annex-a.csv'
NEP_HFEP = 'https://www.dbm.gov.ph/wp-content/uploads/NEP2027/HFEP.pdf'
NEP_NIA = 'https://www.dbm.gov.ph/wp-content/uploads/NEP2027/DETAILS-OF-IRRIGATION.pdf'
NEP_DOTR = 'https://www.dbm.gov.ph/wp-content/uploads/NEP2027/DOTr/A.pdf'

STOP = set('''about after again against all also although among an and any are around as at be because been before being between both but by can could did do does doing down during each either else for from further get got had has have having he her here hers herself him himself his how i if in into is it its itself just may me might more most my myself near no nor not of off on once one only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves then there these they this those through to too under until up very was we were what when where which while who whom why will with would you your yours yourself yourselves page hour hearing budget request requested allocation amount peso project schedule fund funding department bureau program line agency district road city province region construction improvement proposed fy2027 twenty twenty seventh year section members member committee house senate committee report house bill proposal proposal's question questions issue issues asked ask asking response position outcome source source-linked percent million billion thousand percent figures figure records record make made include including use used have has had'''.split())
GENERIC_PROJECT_TERMS = set('''doh dpwh nia da hfep lgu road roads bridge bridges flood control flood-control infrastructure project projects construction improvement rehabilitation repair maintenance health hospital medical center care primary super special office regional region central metro capital national public building buildings facilities facility support allocation funding treatment drug education special disaster related services management medicine medicines tourism access safety systems engineering personnel region province city barangay specialty classroom destination planning inventory transport connectivity airport fuel subsidy contracting modernization digital data audit records tracking commission commissions investment implementation priorities priority policy program programs development project selection capacity government department integrated women route service upgrading loan equipment structural mental unit high phase congressional restoration market right labor site engineer three citizen technical land trade reduction two social way regulation special needs school standards requests budget proposed funding authorities assistance administration national local government monitoring implementation committee '''.split())
AGENCY_DEPARTMENTS = {
    'DICT':['INFORMATION AND COMMUNICATIONS TECHNOLOGY'], 'DPWH':['PUBLIC WORKS AND HIGHWAYS'], 'DOH':['DEPARTMENT OF HEALTH'],
    'DA AND NIA':['DEPARTMENT OF AGRICULTURE','NATIONAL IRRIGATION ADMINISTRATION'],
    'DAR':['AGRARIAN REFORM'], 'DOT':['DEPARTMENT OF TOURISM'], 'DEPED':['DEPARTMENT OF EDUCATION'],
    'DFA':['FOREIGN AFFAIRS'], 'DILG':['INTERIOR AND LOCAL GOVERNMENT'],
    'DOE & ERC':['DEPARTMENT OF ENERGY','ENERGY REGULATORY COMMISSION'], 'DOTR':['DEPARTMENT OF TRANSPORTATION'],
    'DENR':['ENVIRONMENT AND NATURAL RESOURCES'],
    'DND':['NATIONAL DEFENSE'], 'DHSUD':['HUMAN SETTLEMENTS AND URBAN DEVELOPMENT'],
    'COA':['COMMISSION ON AUDIT'], 'CSC':['CIVIL SERVICE COMMISSION'],
    'CHED':['COMMISSION ON HIGHER EDUCATION'], 'DMW':['MIGRANT WORKERS'],
    'CHR':['COMMISSION ON HUMAN RIGHTS'], 'OMB':['OFFICE OF THE OMBUDSMAN'],
    'PCO':['PRESIDENTIAL COMMUNICATIONS OFFICE'], 'OP':['OFFICE OF THE PRESIDENT'],
}
WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def mkrow(stage, sector, title, raw, amount=None, place='', source='', status='', source_url='', department=''):
    title = str(title or '').strip()
    if not title:
        return None
    return {
        'stage': stage, 'sector': sector, 'title': title,
        'amountPesos': amount, 'place': str(place or ''),
        'source': str(source or ''), 'status': str(status or ''),
        'sourceUrl': str(source_url or ''),
        'department': str(department or ''),
        'sourceId': str(raw.get('id') or raw.get('project_id') or raw.get('facility_code') or ''),
    }


def sources():
    rows = []
    nep = read(ROOT / '2027.json')['data']['data']
    for r in nep:
        rows.append(mkrow('NEP', 'DPWH', r.get('projectName'), r,
                          float(r.get('amount') or 0) * 1000,
                          r.get('region'), f"NEP project API · {r.get('code') or r.get('id')}",
                          source_url='https://www.dbm.gov.ph/index.php/2027/national-expenditure-program-fy-2027'))
    with (ROOT / 'data_sources/fmr_analyst/nep_fmr_projects_normalized.csv').open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            rows.append(mkrow('NEP', 'DA-FMR', r.get('title'), r,
                              float(r['amount_php']) if r.get('amount_php') else None,
                              r.get('region'), f"NEP FMR · {r.get('source_pdf')} p. {r.get('printed_page') or r.get('pdf_page')}",
                              source_url='https://www.dbm.gov.ph/index.php/2027/national-expenditure-program-fy-2027'))
    accepted = ROOT / 'data_sources/csiiiv/accepted'
    for r in read(accepted / 'nep_hfep_data_list.json')['items']:
        page = r['source']['pdf_page']
        rows.append(mkrow('NEP', 'DOH-HFEP', r['label'], r, r['amounts_php'].get('total'),
                          r['hierarchy'].get('province'), f"NEP HFEP annex · PDF p. {page}",
                          source_url=f'{NEP_HFEP}#page={page}'))
    for r in read(accepted / 'nep_nia_dataset.json')['projects']:
        page = r['provenance']['page']
        rows.append(mkrow('NEP', 'NIA', r['label'], r, r['amount_php'],
                          source=f"NEP irrigation annex · PDF p. {page}", source_url=f'{NEP_NIA}#page={page}'))

    hgab_dpwh = read(ROOT / 'hb10858_3rd_dpwh_projects.json')['data']['data']
    for r in hgab_dpwh:
        if r.get('allocationKind') != 'project':
            continue
        rows.append(mkrow('HGAB', 'DPWH', r.get('projectName'), r,
                          r.get('amountPesos'), r.get('region'),
                          f"HB10858 3rd reading · {r.get('sourceVolume')} p. {r.get('sourcePage')}",
                          source_url=f"https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ic.pdf#page={r.get('sourcePage') or 1}"))
    fmr = read(ROOT / 'hb10858_3rd_fmr_projects.json')
    fmr = fmr.get('data', {}).get('data', []) if isinstance(fmr, dict) else fmr
    for r in fmr:
        rows.append(mkrow('HGAB', 'DA-FMR', r.get('projectName') or r.get('title'), r,
                          r.get('amountPesos'), r.get('region'),
                          f"HB10858 FMR · {r.get('sourceVolume')} p. {r.get('sourcePage')}",
                          source_url=f"https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ib.pdf#page={r.get('sourcePage') or 1}"))
    for r in read(ROOT / 'hb10858_hfep_projects.json')['data']['data']:
        rows.append(mkrow('HGAB', 'DOH-HFEP', r.get('projectName'), r,
                          r.get('amountPesos'), r.get('region'),
                          f"HB10858 HFEP · p. {r.get('sourcePage')}",
                          source_url=f"https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ib.pdf#page={r.get('sourcePage') or 1}"))
    for r in read(ROOT / 'hb10858_nia_projects.json')['data']['data']:
        rows.append(mkrow('HGAB', 'NIA', r.get('projectName'), r,
                          r.get('amountPesos'), r.get('region'),
                          f"HB10858 NIA · p. {r.get('sourcePage')}",
                          source_url=f"https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ib.pdf#page={r.get('sourcePage') or 1}"))

    # Cross-agency Annex A covers Senate amendments and carries its NEP/House/Senate
    # amounts, but it is not a complete all-agency baseline schedule.
    with ANNEX_A.open(encoding='utf-8-sig') as f:
        for n, r in enumerate(csv.DictReader(f), 1):
            if r.get('is_total_row', '').lower() != 'true' and r.get('label') in {'PS', 'MOOE', 'FinEx', 'CO'}:
                continue
            title = r.get('printed_heading') or r.get('label')
            for stage, amount_key, url_key in (
                ('NEP', 'nep_php', None), ('HGAB', 'house_php', 'house_pdf_url'), ('SCR', 'senate_php', 'senate_pdf_url')):
                raw_amount = str(r.get(amount_key) or '').strip()
                if not raw_amount:
                    continue
                url = r.get(url_key) if url_key else 'https://www.dbm.gov.ph/index.php/2027/national-expenditure-program-fy-2027'
                rows.append(mkrow(stage, 'CROSS_AGENCY', title, {'id':f"annex-a:{n}"},
                                  float(raw_amount), r.get('agency'),
                                  f"Senate Annex A · {r.get('agency')} · {r.get('status_meaning') or r.get('status')}",
                                  r.get('status'), url, r.get('department')))

    for r in read(OUT / 'scr-data.json')['rows']:
        sector = {'dpwh':'DPWH', 'fmr':'DA-FMR', 'hfep':'DOH-HFEP', 'nia':'NIA'}.get(r.get('program'))
        if not sector:
            continue
        amt = r.get('senate_php')
        rows.append(mkrow('SCR', sector, r.get('title'), r, float(amt) if str(amt or '').strip() else None,
                          r.get('region'),
                          f"SCR · {r.get('senate_doc') or 'Senate schedule'} p. {r.get('senate_page') or '?'}",
                          r.get('status_label') or r.get('status'),
                          f"https://budget-assets.bettergov.ph/senate/2027/pdf/{r.get('senate_doc') or 'senate-cr-annex-a4'}.pdf#page={r.get('senate_page') or 1}"))
    return [r for r in rows if r]


def tokens(text):
    return [w for w in WORD.findall(str(text or '').lower()) if len(w) > 2 and w not in STOP and not w.isdigit()]


def longest_phrase(a, b, positions=None):
    """Longest contiguous shared run of informative words."""
    best = []
    if positions is None:
        positions = defaultdict(list)
        for i, word in enumerate(a):
            positions[word].append(i)
    for j, word in enumerate(b):
        for i in positions.get(word, []):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            if k > len(best):
                best = a[i:i + k]
    return best


def topic_text(topic):
    fields = ['topic', 'summary', 'question', 'agency_position', 'outcome']
    text = ' '.join(str(topic.get(k) or '') for k in fields)
    for group in ('positions', 'figures', 'actions', 'thread'):
        for item in topic.get(group) or []:
            if isinstance(item, dict):
                text += ' ' + ' '.join(str(v or '') for v in item.values())
            else:
                text += ' ' + str(item)
    return text


def sector_for(agency, topic):
    a = (agency or '').upper()
    t = topic_text(topic).lower()
    out = []
    if 'DPWH' in a or any(x in t for x in ['dpwh', 'national road', 'flood control project', 'bridge project']):
        out.append('DPWH')
    if 'DOH' in a or any(x in t for x in ['hfep', 'health facility', 'hospital project', 'health center']):
        out.append('DOH-HFEP')
    if 'NIA' in a or 'national irrigation' in t or 'irrigation project' in t:
        out.append('NIA')
    if a in {'DA', 'DA AND NIA'} or 'farm-to-market road' in t or 'fmr project' in t:
        out.append('DA-FMR')
    return out


def reviewed_traces():
    with ANNEX_A.open(encoding='utf-8-sig') as f:
        totals = {row['printed_heading'].split(' / ')[0]: row for row in csv.DictReader(f)
                  if row['is_total_row'].lower() == 'true'}

    traces = {
        '7U4YvhlnbZY:10': {
            'label': 'Likely facility match',
            'title': 'Damulog Bagong Pilipinas Health Center',
            'hearing': 'Rep. Audrey Zubiri asked DOH to review a ₱19 million request. She cited ₱2.7 million and described X-ray sets, generators and water infrastructure. The machine transcript renders the place as “Moolog.” The province, distinctive facility name and exact infrastructure amount support Damulog as the likely match.',
            'hearingUrl': 'https://www.youtube.com/watch?v=7U4YvhlnbZY&t=15864s',
            'hearingTimestamp': '4:24:24',
            'additionalSources': {
                'Machine transcript': 'https://budget-assets.bettergov.ph/hearings/7U4YvhlnbZY/transcript.json',
                'HFEP facility catalog': 'https://hfep.simple-systems.dev/',
                'PhilGEPS notice review': 'philgeps.html',
            },
            'stages': {
                'NEP': {'amountPesos': 3240000, 'url': f'{NEP_HFEP}#page=2'},
                'HGAB': {'amountPesos': None, 'url': 'https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ib.pdf#page=877'},
                'SCR': {'amountPesos': None, 'url': 'https://budget.bettergov.ph/senate/2027/hfep/p/nep_hfep:p2:r35%7Cinfrastructure'},
            },
            'finding': 'The NEP listed ₱2.7 million for infrastructure and ₱540,000 for equipment. The House HFEP extract has no corresponding facility row and the Senate crosswalk lists both components as NEP only. HFEP facility FAC-0589 corroborates the later-stage omission. The available FY2027 PhilGEPS snapshot contains no verified invitation under the facility name.',
        },
    }
    specs = (
        ('wAZmSZkNEok:2', 'NCR Busway Project', 'EDSA Busway', '3818', '1:03:38',
         'A member appealed for the ₱1.7 billion requested for busway maintenance and operations.',
         'The House introduced a distinct NCR Busway line and the Senate proposed doubling it. The ₱150 million line is much smaller than the request and does not establish funding for all 12 stations discussed.'),
        ('wAZmSZkNEok:1', 'Active Transport Bike Share System and Safe', 'Active transport and Safe Pathways', '16342', '4:32:22',
         'Members questioned the decrease in funding for the named bike-share and Safe Pathways program.',
         'The ₱33.856 million line was already in the NEP and carried into the House bill. The Senate proposed adding ₱71.512 million. Amounts include both operating and capital components.'),
        ('4wK1OLsr2lw:2', 'DOH UNIVERSAL HEALTH CARE FUND FOR', 'Zero-balance billing in LGU hospitals', '14598', '4:03:18',
         'Members asked whether zero-balance billing would cover LGU hospitals and how the expansion would be funded.',
         'Senate Annex A inserts a dedicated ₱1 billion LGU-hospital fund. Its scope is the named line, separate from other PhilHealth and medical-assistance funding.'),
    )
    for topic_id, heading, title, seconds, timestamp, hearing, finding in specs:
        row = totals[heading]
        nep_url = 'https://www.dbm.gov.ph/index.php/2027/national-expenditure-program-fy-2027'
        if title == 'Active transport and Safe Pathways':
            nep_url = f'{NEP_DOTR}#page=14'
        elif title == 'EDSA Busway':
            nep_url = NEP_DOTR
        stages = {}
        for stage, amount_key, url in (
            ('NEP', 'nep_php', nep_url),
            ('HGAB', 'house_php', row['house_pdf_url']),
            ('SCR', 'senate_php', row['senate_pdf_url']),
        ):
            stages[stage] = {'amountPesos': int(row[amount_key]) if row[amount_key] else None, 'url': url}
        traces[topic_id] = {
            'label': 'Program line traced',
            'title': title, 'hearing': hearing,
            'hearingUrl': f'https://www.youtube.com/watch?v={topic_id.split(":")[0]}&t={seconds}s',
            'hearingTimestamp': timestamp, 'stages': stages, 'finding': finding,
        }
    return traces


def main():
    hearings = read(DATA / 'hearings-fy2027.json')['hearings']
    budgets = sources()
    traces = reviewed_traces()
    # Stage-specific term frequencies weight rare project and place names above generic budget language.
    idf = {}
    for stage in ('NEP', 'HGAB', 'SCR'):
        docs = [set(tokens(f"{r['title']} {r['place']}")) for r in budgets if r['stage'] == stage]
        df = Counter(w for doc in docs for w in doc)
        for w, n in df.items():
            idf[(stage, w)] = math.log(1 + (len(docs) + 1) / (n + 1))
    index = defaultdict(list)
    for i, r in enumerate(budgets):
        r['_tokens'] = set(tokens(r['title']))
        for w in r['_tokens']:
            index[(r['stage'], w)].append(i)

    results = []
    for hearing in hearings:
        agency = hearing.get('agency') or ''
        for topic in hearing.get('topics') or []:
            corpus = topic_text(topic)
            topic_title_tokens = set(tokens(topic.get('topic') or ''))
            query_sequence = tokens(' '.join(str(topic.get(k) or '') for k in
                                             ('topic', 'summary', 'question', 'agency_position', 'outcome')))
            query_positions = defaultdict(list)
            for qi, qw in enumerate(query_sequence):
                query_positions[qw].append(qi)
            qtokens = set(tokens(corpus))
            sectors = sector_for(agency, topic)
            stage_results = {}
            for stage in ('NEP', 'HGAB', 'SCR'):
                # Rare terms drive retrieval; common language such as "road" or
                # "funding" otherwise expands the candidate set to most records.
                informative = sorted((w for w in qtokens if idf.get((stage, w), 0) >= 1.0),
                                     key=lambda w: (-idf[(stage, w)], w))[:70]
                denominator = max(1.0, sum(idf.get((stage, w), .1) for w in informative))
                query_terms = set(informative)
                pool = set()
                for w in informative:
                    pool.update(index.get((stage, w), []))
                scored = []
                for i in pool:
                    r = budgets[i]
                    if r['sector'] == 'CROSS_AGENCY':
                        departments = AGENCY_DEPARTMENTS.get(agency.upper(), [])
                        if departments and not any(d in r['department'].upper() for d in departments):
                            continue
                    elif r['sector'] not in sectors:
                        continue
                    # Exclude obvious non-project hierarchy/package rows from the
                    # crosswalk candidate list; their titles bundle many projects.
                    if len(r['title']) > 420 or r['title'].startswith('['):
                        continue
                    shared = query_terms & r['_tokens']
                    title_shared = topic_title_tokens & r['_tokens']
                    if not shared:
                        continue
                    title_sequence = tokens(r['title'])
                    phrase = longest_phrase(query_sequence, title_sequence, query_positions)
                    high_value_shared = [w for w in shared if idf.get((stage, w), 0) >= 3.2]
                    # A genuine project lead should share a specific name or phrase,
                    # rather than only broad terms such as health, bridge or funding.
                    if len(phrase) < 3 and not (len(phrase) >= 2 and max((idf.get((stage,w),0) for w in phrase), default=0) >= 3.2) and len(high_value_shared) < 2:
                        continue
                    title_score = len(title_shared) / max(1, len(topic_title_tokens))
                    title_specific = [w for w in title_shared if w not in GENERIC_PROJECT_TERMS and idf.get((stage, w), 0) >= 5.5]
                    if not title_specific:
                        continue
                    phrase_score = min(1.0, len(phrase) / max(3, len(title_sequence)))
                    score = round(phrase_score * .75 + title_score * .25, 4)
                    evidence = phrase if len(phrase) >= 2 else sorted(high_value_shared, key=lambda w: (-idf[(stage, w)], w))[:6]
                    scored.append((score, title_score, r, evidence, title_specific))
                scored.sort(key=lambda x: (-x[0], -x[1], x[2]['title'], x[2]['source']))
                selected=[]
                seen=set()
                for score,title_score,r,terms,title_specific_terms in scored:
                    key=(r['sourceId'],r['title'],r['source'],r['amountPesos'])
                    if key in seen: continue
                    seen.add(key)
                    selected.append({'title':r['title'],'sector':r['sector'],'score':round(score,4),
                                     'topicTitleCoverage':round(title_score,3),'sharedTerms':terms,
                                     'topicTitleSpecificTerms':title_specific_terms,
                                     'matchEvidence':'shared phrase or distinctive project-name terms',
                                     'amountPesos':r['amountPesos'],'place':r['place'],'source':r['source'],
                                     'budgetStatus':r['status'],
                                     'sourceUrl':r['sourceUrl'],'sourceId':r['sourceId'],'status':r['status']})
                stage_results[stage]={'coverage':'screened','candidates':selected}
            if any(v['candidates'] for v in stage_results.values()):
                classification='candidate_leads_need_review'
            elif not sectors:
                classification=('agency_not_covered_in_local_extracts' if agency else
                                'agency_or_project_scope_unclear')
            else:
                classification='no_candidate_in_available_extracts'
            topic_id = f"{hearing.get('video_id')}:{topic.get('index')}"
            trace = traces.get(topic_id)
            results.append({
                'topicId':topic_id,
                'hearingId':hearing.get('video_id'),'agency':agency or 'Agency not identified',
                'hearingDate':hearing.get('hearing_date'),'topic':topic.get('topic') or '',
                'summary':topic.get('summary') or '', 'question':topic.get('question') or '',
                'hearingUrl':topic.get('url') or hearing.get('page_url'),
                'identifiedSectors':sectors,'classification':classification,
                'reviewStatus':trace['label'] if trace else 'unreviewed automated lexical screen',
                'reviewedTrace':trace, 'stageCandidates':stage_results,
            })
    counts=Counter(r['classification'] for r in results)
    payload={
      'title':'FY2027 hearing-topic budget crosswalk candidate screen',
      'generatedFrom':{'hearings':str((DATA/'hearings-fy2027.json').relative_to(ROOT)),'NEP':'DPWH API extract, FMR normalized schedule, reviewed HFEP and NIA annex extracts, and Senate Annex A crosswalk',
                       'HGAB':'HB10858 3rd DPWH, FMR, HFEP and NIA extracts plus Senate Annex A crosswalk','SCR':'Senate crosswalk rows for DPWH, FMR, HFEP and NIA plus Annex A'},
      'method':'Lexical retrieval on topic, question, summary, agency position, outcome and timestamped statements against budget-line titles and place fields. Ranked candidates are leads only; all require source-page review. No candidate means none was detected in these local extracts, not proof of absence.',
      'coverageLimit':'Full local line-item extracts cover DPWH, DA farm-to-market roads, DOH HFEP and NIA. Senate Annex A adds partial cross-agency amendment lines with NEP/House/Senate comparison amounts; it is not a full baseline for all agencies. Most non-infrastructure agency baseline schedules are outside this screen. General requests, policy issues and funding totals are not individual project matches.',
      'topicCount':len(results),'classificationCounts':dict(counts),'topics':results,
      'reviewedTraceCount':len(traces),
      'candidateCount':sum(len(stage['candidates']) for record in results for stage in record['stageCandidates'].values()),
      'budgetRowCount':len(budgets),
      'budgetRowsByStage':dict(Counter(r['stage'] for r in budgets)),
    }
    OUT.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    for dest in (OUT/'questions-budget-crosswalk.json', DATA/'questions-budget-crosswalk.json', STATIC/'questions-budget-crosswalk.json'):
        dest.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    csv_paths = [OUT/'questions-budget-crosswalk.csv', DATA/'questions-budget-crosswalk.csv', STATIC/'questions-budget-crosswalk.csv']
    fields=['topicId','agency','hearingDate','topic','classification','identifiedSectors','hearingUrl','reviewStatus','reviewFinding','NEP_candidates','HGAB_candidates','SCR_candidates']
    for csv_path in csv_paths:
        with csv_path.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
            for r in results:
                w.writerow({'topicId':r['topicId'],'agency':r['agency'],'hearingDate':r['hearingDate'],'topic':r['topic'],
                            'classification':r['classification'],'identifiedSectors':'; '.join(r['identifiedSectors']),'hearingUrl':r['hearingUrl'], 'reviewStatus':r['reviewStatus'],
                            'reviewFinding':(r['reviewedTrace'] or {}).get('finding', ''),
                            **{f'{s}_candidates':' | '.join(f"{c['title']} [rank {c['score']}; {', '.join(c['sharedTerms'])}]" for c in r['stageCandidates'][s]['candidates']) for s in ('NEP','HGAB','SCR')}})
    print(json.dumps({'topics':len(results),'budgetRows':len(budgets),'classifications':dict(counts),'files':[str(OUT/'questions-budget-crosswalk.json'),str(csv_paths[0])]},indent=2))

if __name__=='__main__': main()
