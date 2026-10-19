#!/usr/bin/env python3
"""Rank current HGAB DPWH allocation occurrences by reproducible screening flags."""
import csv
import hashlib
import json
import unicodedata
from collections import defaultdict, Counter
from pathlib import Path
from analyze_priority_repeats import previous_rows, classify
from chainage import compare_chainage, compare_tranche, has_directional_conflict
from hgab_matching import UNMATCHED, is_fap, normalize
from location_data.location_text import geographic_title
from location_data.project_location_scope import qualified, location_conflict

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
GROUP_MIN = 10
OFFICE_MIN = 3
QUEUE_CHUNK_SIZE = 500

# One recognizable symbol per review trigger. These are queue markers, not
# severity grades; the legend keeps their meanings explicit.
FLAG_ICONS = {
    'very_short_range': '📐',
    'high_meter_rate': '📈',
    'rehab_good_fair': '🛣️',
    'recent_surfacing': '🛞',
    'insertion': '🧩',
    'missing_documents': '📂',
    'missing_pow': '🧮',
    'missing_photos': '📷',
    'missing_rdc': '🏛️',
    'amount_group': '🪙',
    'historical_title': '🕰️',
    'chainage_overlap': '📍',
}


def historical_key(title):
    # Strip only complete trailing station/coordinate metadata; retain all
    # place names, work descriptions, directions, packages and phases.
    return normalize(geographic_title(title)[0])

def portal_title_key(title):
    return ' '.join(unicodedata.normalize('NFKC', str(title or '')).split())


def build(indepth_data=None):
    source = OUT / 'hb_nep_comparison_3rd.csv'
    with source.open() as f:
        rows = list(csv.DictReader(f))
    ids = [r['hgab_id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Repeated HGAB occurrence IDs cannot be ranked independently')
    cost_source = OUT / 'cost_per_km.json'
    cost_data = json.loads(cost_source.read_text())
    portal = json.loads((OUT / 'dpwh_transparency_document_coverage.json').read_text())
    portal_titles = portal.get('titles', {})
    indepth = indepth_data or json.loads((OUT / 'dpwh-in-depth-data.json').read_text())
    inspected_documents = {p['code']: p for p in indepth.get('projects', [])}
    hgab_stage = json.loads((OUT / 'dpwh_hgab_2nd_vs_3rd.json').read_text())
    project_occurrences = {r['third']['id'] for r in hgab_stage.get('rows', [])
                          if r.get('third') and r['third'].get('allocationKind') == 'project'}
    no_nep_counterpart_ids = {r.get('id') for r in json.loads((OUT / 'hb_nep_comparison_3rd_mapping.json').read_text()).get('hgabWithoutSelectedCounterpart', [])
                              if r.get('allocationKind') == 'project'}
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if not any(s['file'] == source.name and s['sha256'] == source_hash for s in cost_data['sources']):
        raise ValueError('Rebuild cost-per-meter data before ranking: HGAB source hash differs')
    lengths = {r['id']: r for r in cost_data['projects']}
    history = defaultdict(list)
    prior_by_year = previous_rows()
    for year, records in sorted(prior_by_year.items()):
        for record in records:
            history[(classify(record['name']), historical_key(record['name']))].append({**record, 'year': year})
    groups = defaultdict(list)
    for row in rows:
        row['amountPesos'] = int(row['amountPesos'])
        if row['office'].strip():
            groups[(row['pap3'], row['amountPesos'])].append(row)
    attribution = {r['id']: r for r in json.loads((OUT / 'congress_geographic_attribution_db_3rd.json').read_text())['projects']}
    ranked = []
    for row in rows:
        if is_fap(row):
            continue  # Foreign-assisted schedules have a separate comparison.
        title = row['projectName']
        flags = []
        length = lengths.get(row['hgab_id'])
        cautions = []
        if length:
            if length['projectName'] != title or length['amountPesos'] != row['amountPesos']:
                raise ValueError('Cost-per-meter occurrence disagrees with native HGAB row')
            if length['lengthMeters'] is None:
                cautions.append('No usable extracted length; cannot calculate a defensible stated-meter rate. This is an evidence gap, not an extra ranking point.')
            elif length['lengthMeters'] < 10:
                cautions.append(f'Printed range implies {length["lengthMeters"]:g} meters; verify source notation and funded extent before interpreting a rate. No high-rate point awarded.')
                flags.append({'id': 'very_short_range', 'label': 'Very short printed project range',
                              'evidence': f'Extracted printed range is {length["lengthMeters"]:g} meters. Verify notation and funded extent; the short range is a denominator warning, not evidence of an incorrect allocation.'})
            elif length['highRateCandidate']:
                flags.append({'id': 'high_meter_rate', 'label': 'High allocation per stated meter',
                              'evidence': f'₱{length["allocationPerStatedMeter"]:,.2f}/stated meter; {length["peerRateMultiple"]:g}× the ₱{length["typicalPeerRate"]:,.2f} peer median among {length["peerRecords"]} same-category, same-structure ({length.get("rateStructureGroup",length["category"])}), same-PAP, same-surface/condition-context, same-length-band records ({length["peerBand"]}). Exceeds both 2× median and Q3 + 1.5× IQR; funded scope and quantities unverified.',
                              'summaryFinding': 'cost-per-km'})
                if length['graphExtreme']:
                    cautions.append('Extreme rate excluded from rate charts; retained here for denominator and scope review. Not verified overpricing.')
            elif length['typicalPeerRate'] is None:
                cautions.append('Insufficient comparable peers; no high-rate conclusion or point.')
        if length and length.get('rehabGoodFairReview'):
            context=length['assetContextEvidence']
            flags.append({'id':'rehab_good_fair','label':'Rehabilitation on recorded Good/Fair segment',
                'evidence':f'Full matched road range was assessed {length["recordedConditionDisplay"]}; section {context["sectionId"]}. Later deterioration, structural work and scope differences require review; this is not proof the rehabilitation is unnecessary.',
                'summaryFinding':'cost-per-km'})
        if length and length.get('bridgeGoodFairContextReview'):
            cautions.append('Bridge inventory records Good/Fair condition but no assessment date. Verify the date and work scope; no dated-condition point awarded.')
        if length and length.get('recentSurfacingReview'):
            context=length['assetContextEvidence']
            flags.append({'id':'recent_surfacing','label':'Pavement work after recent recorded surfacing',
                'evidence':f'Full matched range has recorded last-surfacing year(s) {length["surfacingYearDisplay"]}, within {context["recentSurfacingWindowYears"]} budget years of FY{context["budgetYear"]}. Screening threshold, not engineering service life; verify earlier and proposed quantities.',
                'summaryFinding':'cost-per-km'})
        portal_entry = portal_titles.get(portal_title_key(title))
        has_listed_docs = bool(portal_entry and portal_entry.get('code')
                               and portal_entry.get('status') not in {'not_found', 'no_verified_match', 'candidate_match', 'ambiguous_match', 'outside_snapshot_scope'}
                               and (portal_entry.get('documentCount') or 0) > 0)
        is_project_occurrence = row['hgab_id'] in project_occurrences
        if ((is_project_occurrence and row['hgab_id'] in no_nep_counterpart_ids)
                or (not is_project_occurrence and row['comparison'] == UNMATCHED)):
            flags.append({'id': 'insertion', 'label': 'No selected NEP counterpart',
                          'evidence': 'The one-to-one HGAB 3rd ↔ NEP comparison selected no counterpart for this occurrence. Unmatched or ambiguous matching is a review candidate, not proof the project is absent from NEP.'})
        if is_project_occurrence and not has_listed_docs:
            flags.append({'id': 'missing_documents', 'label': 'No listed DPWH Transparency documents',
                          'evidence': 'No matched DPWH Transparency entry with one or more listed documents was found in the current snapshot. This is a snapshot disclosure gap, not proof that documents do not exist elsewhere.'})
        inspected_project = inspected_documents.get(portal_entry.get('code')) if (portal_entry and portal_entry.get('code')
                                and portal_entry.get('status') not in {'not_found', 'no_verified_match', 'candidate_match', 'ambiguous_match', 'outside_snapshot_scope'}) else None
        if is_project_occurrence and inspected_project:
            links = inspected_project.get('documentLinks', [])
            kinds = {
                'POW': any((str(d.get('type') or '').lower().strip() == 'pow' or 'program of work' in str(d.get('type') or '').lower()) for d in links),
                'geotagged photos': any('geotagged' in str(d.get('type') or '').lower() and 'photo' in str(d.get('type') or '').lower() for d in links),
                'RDC': any('rdc' in str(d.get('type') or '').lower() or 'regional development council' in str(d.get('type') or '').lower() for d in links),
            }
            ids = {'POW': 'missing_pow', 'geotagged photos': 'missing_photos', 'RDC': 'missing_rdc'}
            for kind, present in kinds.items():
                if not present:
                    flags.append({'id': ids[kind], 'label': 'No listed '+kind,
                                  'evidence': 'This locally inspected DPWH Transparency attachment list contains no '+kind+' entry. Verify against the source record; uninspected projects are unknown.'})
        group = groups[(row['pap3'], row['amountPesos'])]
        offices = sorted({r['office'] for r in group})
        if row['amountPesos'] > 0 and len(group) >= GROUP_MIN and len(offices) >= OFFICE_MIN:
            flags.append({'id': 'amount_group', 'label': 'Repeated allocation amount',
                          'evidence': f'Exact ₱{row["amountPesos"]:,} in this PAP: {len(group)} HGAB occurrences across {len(offices)} named implementing offices.',
                          'groupCount': len(group), 'officeCount': len(offices), 'pap': row['pap3']})
        matches = []
        context = qualified(title)
        if context and context['province'] and context['municipality']:
            for old in history.get((classify(title), historical_key(title)), []):
                old_context = qualified(old['name'])
                if not old_context or not old_context['province'] or not old_context['municipality']:
                    continue
                if not context['province'].intersection(old_context['province']) or not context['municipality'].intersection(old_context['municipality']):
                    continue
                chainage = compare_chainage(title, old['name'])
                if (location_conflict(title, old['name']) or has_directional_conflict(title, old['name'])
                    or compare_tranche(title, old['name'])['tranche_conflict']
                    or chainage['chainage_status'] == 'disjoint'):
                    continue
                matches.append({'year': old['year'], 'title': old['name'], 'amountPesos': old['amount'],
                                'source': old['source'], 'chainage': chainage})
        if matches:
            flags.append({'id': 'historical_title', 'label': 'Historical GAA title recurrence',
                          'evidence': 'Same normalized full title after trailing metadata removal, qualified town/province agreement; not proof of duplicate work.'})
            if any(m['chainage']['overlaps'] for m in matches):
                flags.append({'id': 'chainage_overlap', 'label': 'Explicit historical chainage overlap',
                              'evidence': 'At least one accepted historical title counterpart has positive-length overlap between stated ranges.'})
        if not flags:
            continue
        names = attribution.get(row['hgab_id'], {})
        ranked.append({'hgabId': row['hgab_id'], 'projectName': title, 'program': row['pap3'],
                       'office': row['office'], 'region': row['region'], 'amountPesos': row['amountPesos'],
                       'flagCount': len(flags), 'flags': flags, 'historicalMatches': matches,
                       'evidenceCautions': cautions,
                       'lengthReview': ({k: length.get(k) for k in ['category', 'lengthMeters', 'lengthStatus', 'lengthMethod', 'allocationPerStatedMeter', 'typicalPeerRate', 'peerRateMultiple', 'peerRecords', 'peerBand', 'highRateCandidate', 'graphExtreme', 'titleStatedLanes', 'allocationPerTitleLaneMeter', 'inventoryEffectiveLanes', 'allocationPerInventoryLaneMeterProxy', 'allocationPerInventoryAssetLaneMeter', 'laneRateStatus', 'laneInventoryEvidence', 'surfaceDisplay', 'recordedConditionDisplay', 'surfacingYearDisplay', 'surfacePeerGroup', 'rehabGoodFairReview', 'recentSurfacingReview', 'bridgeGoodFairContextReview', 'assetContextEvidence']} if length else None),
                       'sourceVolume': row['sourceVolume'], 'sourcePage': row['sourcePage'],
                       'transparency': {'code': portal_entry.get('code') if portal_entry else None,
                                        'status': portal_entry.get('status') if portal_entry else 'no_verified_match',
                                        'matchBasis': portal_entry.get('matchBasis') if portal_entry else 'No matching DPWH Transparency record in the retained snapshot',
                                        'portalTitle': portal_entry.get('portalTitle') if portal_entry else None,
                                        'documentCount': portal_entry.get('documentCount') if portal_entry else None,
                                        'documentLinks': (inspected_project or {}).get('documentLinks', [])},
                       'nepStatus': row['comparison'], 'representatives': names.get('representatives', []),
                       'districts': names.get('districts', [])})
    ranked.sort(key=lambda r: (-r['flagCount'], -r['amountPesos'], r['hgabId']))
    for i, row in enumerate(ranked, 1):
        row['rank'] = i
    sources = [source, OUT / 'congress_geographic_attribution_db_3rd.json',
               cost_source,
               ROOT.parent / 'open-data-visualization/data/parquet/parsed_dpwh_2026.parquet',
               *[ROOT.parent / f'open-data-visualization/data/parquet/budget_{year}.parquet'
                 for year in range(2020, 2026)],
               ROOT / 'location_data/philippine_locations.sqlite']
    result = {'scope': 'Domestic DPWH HGAB 3rd-reading occurrences only; not a ranking of the entire national budget.',
              'ranking': 'Flag count descending, allocation pesos descending, occurrence ID ascending for exact ties.',
              'method': {'maximumPossibleFlags': 12, 'amountGroupMinimumOccurrences': GROUP_MIN, 'amountGroupMinimumNamedOffices': OFFICE_MIN,
                         'amountGroupScope': 'Identical PAP and positive exact peso amount; counts are allocation occurrences, not certified distinct construction contracts.',
                         'historicalYears': sorted(prior_by_year),
                         'historicalMatch': 'Identical full normalized title after complete trailing metadata removal; same qualified municipality/province; direction/location/tranche conflict and disjoint stated chainage excluded.',
                         'weights': 'One point per flag type. Multiple historical years do not add points.',
                         'highMeterRate': cost_data['highRateScreen']['method'],
                         'laneEvidence': 'Title lane rates, inventory lane estimates and existing-bridge asset estimates are separate contextual measures. None adds a ranking point or replaces a missing funded length. Lane and station evidence is retained in lengthReview.',
                         'conditionAndSurfacing': cost_data['laneCost']['assetContext'],
                         'evidenceGaps': 'Missing length and insufficient peers are cautions, not points. A sub-10m printed range gets a separate denominator-warning point and remains subject to source verification. Extreme rates require denominator/scope review and are omitted from rate charts.',
                         'summaryCoverage': 'The queue has up to twelve possible flags: the prior nine screening types plus separate incomplete-documentation flags for missing POW, geotagged photos, and RDC among locally inspected attachment records. Potential NEP counterpart and no listed documents are separate flags; document-type flags are unknown outside inspected metadata.',
                         'dependence': 'Historical recurrence and chainage overlap are related indicators; scores are descriptive triage, not independent evidence or probabilities.',
                         'limitations': ['Uniform packages can be legitimate. Exact appropriation amounts are not unit costs.',
                                        'Strict historical matching misses paraphrased titles and unresolved locations; no icon means this screen did not identify a review trigger, not that the project is verified.',
                                        'The prior-year search uses locally available DPWH road, bridge, building and flood records from FY2020–FY2026; it is not a search of every project type or every agency.',
                                        'Matching/parser errors can produce insertion flags. Top 25 overlap other findings; do not sum them as losses.',
                                        'Current office, representative, role and party do not contribute any points.']},
              'summary': {'sourceOccurrences': len(rows), 'flaggedOccurrences': len(ranked),
                          'flagTypes': dict(Counter(f['id'] for r in ranked for f in r['flags'])),
                          'flagCountDistribution': dict(Counter(r['flagCount'] for r in ranked)),
                          'top25Occurrences': min(25, len(ranked))},
              'top25': ranked[:25], 'rankedOccurrences': ranked,
              'sources': [{'file': str(p.relative_to(ROOT.parent)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources]}
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    (OUT / 'line_item_review_queue.json').write_text(serialized)
    (STATIC / 'line-item-review-queue.json').write_text(serialized)
    display_fields = ['rank', 'hgabId', 'projectName', 'program', 'office', 'region',
                      'amountPesos', 'sourceVolume', 'sourcePage', 'flagCount', 'flags',
                      'evidenceCautions', 'historicalMatches', 'transparency']
    display_rows = [{key: row.get(key) for key in display_fields} for row in ranked]
    for base in (OUT, STATIC):
        pages_dir = base / 'line-item-review-queue-pages'
        pages_dir.mkdir(parents=True, exist_ok=True)
        page_count = (len(display_rows) + QUEUE_CHUNK_SIZE - 1) // QUEUE_CHUNK_SIZE
        for page_no in range(page_count):
            start = page_no * QUEUE_CHUNK_SIZE
            chunk = display_rows[start:start + QUEUE_CHUNK_SIZE]
            (pages_dir / f'page-{page_no:04d}.json').write_text(
                json.dumps(chunk, ensure_ascii=False, separators=(',', ':')) + '\n')
        (base / 'line-item-review-queue-pages.json').write_text(json.dumps({
            'rows': len(display_rows), 'chunkSize': QUEUE_CHUNK_SIZE,
            'pageCount': page_count, 'sort': 'flagCount descending, amountPesos descending, hgabId ascending',
            'chunks': 'line-item-review-queue-pages/page-{page:04d}.json; page is zero-based'
        }, ensure_ascii=False, indent=2) + '\n')
    return result


def render(data, table, esc):
    rows = data['rankedOccurrences'][:10]
    graph = '<figure><figcaption>Top 10 projects in queue order · flag count, then allocation</figcaption><svg class="evidence-graphic" style="max-height:470px" viewBox="0 0 1100 465" role="img" aria-label="Top 10 flagged projects, with separate bars for review flags and allocation"><text x="16" y="28" font-size="15" font-weight="700">PROJECT</text><text x="480" y="28" font-size="15" font-weight="700">REVIEW FLAGS</text><text x="760" y="28" font-size="15" font-weight="700">ALLOCATION</text>'
    max_amount = max((r['amountPesos'] for r in rows), default=1)
    max_flags = max((r['flagCount'] for r in rows), default=1)
    for i, row in enumerate(rows):
        y = 48 + i * 40
        name = row['projectName']
        short_name = name if len(name) <= 62 else name[:59].rstrip() + '…'
        amount_label = f'₱{row["amountPesos"]/1e9:.2f}B' if row['amountPesos'] >= 1_000_000_000 else f'₱{row["amountPesos"]/1e6:.1f}M'
        graph += (f'<line x1="12" y1="{y+30}" x2="1080" y2="{y+30}" stroke="#e1e9e7"/> '
                  f'<text x="16" y="{y+20}" font-size="13"><title>{esc(name)}</title>{row["rank"]}. {esc(short_name)}</text> '
                  f'<rect x="480" y="{y+4}" width="190" height="18" rx="7" fill="#e7efed"/><rect x="480" y="{y+4}" width="{row["flagCount"]*150/max_flags}" height="18" rx="7" fill="#087e78"><title>{row["flagCount"]} review flags</title></rect><text x="680" y="{y+19}" font-size="13" font-weight="700">{row["flagCount"]}</text> '
                  f'<rect x="760" y="{y+4}" width="250" height="18" rx="7" fill="#f4e8dc"/><rect x="760" y="{y+4}" width="{row["amountPesos"]*210/max_amount}" height="18" rx="7" fill="#b65b09"><title>₱{row["amountPesos"]:,}</title></rect><text x="1020" y="{y+19}" font-size="13" font-weight="700">{amount_label}</text>')
    graph += '</svg></figure>'
    body = f'<p>One row per domestic DPWH HGAB 3rd-reading allocation occurrence. The full queue contains {data["summary"]["flaggedOccurrences"]:,} flagged rows, sorted by flag count, allocation amount, then occurrence ID. The chart shows the first 10; the paginated table below covers the entire queue. Up to twelve review flags cover amount patterns, NEP counterparts, listed documents, POW/photos/RDC coverage, historical recurrence, chainage, rate, recorded condition, recent surfacing and very short printed ranges. Each icon marks a reason for a human to check the evidence. Icons do not represent findings or levels of guilt. Document-type flags apply only to locally inspected attachment metadata; unavailable or inapplicable evidence is not treated as verified.</p>'
    body += '<p><strong>Icon key:</strong> '+ ' · '.join(f'{FLAG_ICONS[k]} {label}' for k,label in [('very_short_range','short range'),('high_meter_rate','relative rate'),('rehab_good_fair','recorded condition'),('recent_surfacing','recent surfacing'),('insertion','NEP match review'),('missing_documents','listed documents'),('missing_pow','POW'),('missing_photos','geotagged photos'),('missing_rdc','RDC'),('amount_group','repeated amount'),('historical_title','historical title'),('chainage_overlap','chainage overlap')]) + '</p>'
    headers=['Rank', 'HGAB project', 'Program', 'Implementing office', 'Flags for human review', 'HGAB allocation pesos', 'HGAB source']
    icon_map=json.dumps(FLAG_ICONS,ensure_ascii=False,separators=(',',':'))
    shell='<div id="line-item-queue" data-rows="'+str(data['summary']['flaggedOccurrences'])+'"><div class="queue-controls"><button type="button" id="queue-export" class="export-btn">Export full queue CSV</button><span id="queue-count" aria-live="polite"></span><button type="button" id="queue-prev">Previous</button><span id="queue-page"></span><button type="button" id="queue-next">Next</button></div><p id="queue-load-status" role="status">Loading ranked rows…</p><div class="evidence-table"><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody id="queue-body"></tbody></table></div></div><dialog id="flag-evidence-dialog" class="flag-evidence-dialog"><form method="dialog"><button class="export-btn">Close</button></form><h3 id="flag-evidence-title"></h3><ol id="flag-evidence-list"></ol></dialog>'
    queue_script='''<script id="line-item-queue-script">(()=>{const root=document.getElementById('line-item-queue');if(!root)return;const total=Number(root.dataset.rows),pageSize=100,chunkSize=500,iconMap=ICON_MAP,body=document.getElementById('queue-body'),status=document.getElementById('queue-load-status'),count=document.getElementById('queue-count'),pageLabel=document.getElementById('queue-page'),prev=document.getElementById('queue-prev'),next=document.getElementById('queue-next'),cache=new Map(),rowMap=new Map(),dialog=document.getElementById('flag-evidence-dialog'),dialogTitle=document.getElementById('flag-evidence-title'),dialogList=document.getElementById('flag-evidence-list');let page=0;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const num=n=>Number(n||0).toLocaleString('en-PH'),peso=n=>'₱'+Number(n||0).toLocaleString('en-PH');async function chunk(i){if(!cache.has(i))cache.set(i,fetch('line-item-review-queue-pages/page-'+String(i).padStart(4,'0')+'.json').then(r=>{if(!r.ok)throw Error('Could not load ranked rows');return r.json()}));return cache.get(i)}function historical(row){return (row.historicalMatches||[]).map(m=>'GAA '+m.year+': '+m.title+' · '+peso(m.amountPesos)+' · '+m.source+(m.chainage?.overlaps?' · overlap '+m.chainage.chainage_overlap:'')).join(' | ')||'No qualifying historical title link established'}function renderRows(rows){return rows.map(r=>{rowMap.set(r.hgabId,r);const icons=(r.flags||[]).map(f=>iconMap[f.id]||'🔎').join('');const labels=(r.flags||[]).map(f=>f.label).join('; ');return '<tr><td>'+r.rank+'</td><td>'+esc(r.projectName)+'</td><td>'+esc(r.program)+'</td><td>'+esc(r.office)+'</td><td><button class="queue-flag-button" type="button" data-row="'+esc(r.hgabId)+'" title="'+esc(labels)+'" aria-label="Show evidence for '+r.flagCount+' review flags">'+icons+'</button></td><td>'+peso(r.amountPesos)+'</td><td>'+esc(r.sourceVolume+' · p. '+r.sourcePage)+'</td></tr>'}).join('')}async function load(){status.textContent='Loading ranked rows…';body.innerHTML='';try{const start=page*pageSize,chunkIndex=Math.floor(start/chunkSize),offset=start%chunkSize,rows=await chunk(chunkIndex),visible=rows.slice(offset,offset+pageSize);body.innerHTML=renderRows(visible)||'<tr><td colspan="7">No flagged rows.</td></tr>';const first=total?start+1:0,last=Math.min(start+visible.length,total);count.textContent=num(first)+'–'+num(last)+' of '+num(total)+' flagged rows';pageLabel.textContent='Page '+num(page+1)+' of '+num(Math.max(1,Math.ceil(total/pageSize)));prev.disabled=page===0;next.disabled=start+visible.length>=total;status.textContent='Sorted by flag count (highest first), allocation amount (highest first), then occurrence ID.'}catch(e){status.textContent=e.message+'; see the full ranking JSON below.'}}prev.onclick=()=>{if(page>0){page--;load()}};next.onclick=()=>{if((page+1)*pageSize<total){page++;load()}};body.addEventListener('click',e=>{const b=e.target.closest('.queue-flag-button');if(!b)return;const row=rowMap.get(b.dataset.row);if(!row)return;dialogTitle.textContent=row.projectName;const details=[...row.flags.map(f=>{const li=document.createElement('li'),strong=document.createElement('strong'),p=document.createElement('p');strong.textContent=f.label;p.textContent=f.evidence;li.append(strong,p);return li})];if(row.evidenceCautions?.length){const li=document.createElement('li');li.innerHTML='<strong>Evidence cautions · no extra points</strong><p>'+esc(row.evidenceCautions.join(' · '))+'</p>';details.push(li)}if(row.historicalMatches?.length){const li=document.createElement('li');li.innerHTML='<strong>Historical counterpart evidence</strong><p>'+esc(historical(row))+'</p>';details.push(li)}const transparencyFlags=new Set(['insertion','missing_documents','missing_pow','missing_photos','missing_rdc']);const related=(row.flags||[]).some(f=>transparencyFlags.has(f.id));const portal=row.transparency;if(related&&portal){const li=document.createElement('li'),title=document.createElement('strong'),meta=document.createElement('p');title.textContent='DPWH Transparency record';meta.textContent=[portal.code,portal.status,portal.matchBasis,portal.documentCount==null?null:num(portal.documentCount)+' listed documents'].filter(Boolean).join(' · ');li.append(title,meta);if(portal.portalTitle){const p=document.createElement('p');p.textContent=portal.portalTitle;li.append(p)}for(const d of portal.documentLinks||[]){const p=document.createElement('p'),a=document.createElement('a');a.href=d.url;a.target='_blank';a.rel='noopener';a.textContent=d.type||'Document';p.append(a);li.append(p)}details.push(li)}dialogList.replaceChildren(...details);dialog.showModal()});dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});document.getElementById('queue-export').onclick=async e=>{const button=e.currentTarget;button.disabled=true;button.textContent='Preparing CSV…';try{const parts=await Promise.all(Array.from({length:Math.ceil(total/chunkSize)},(_,i)=>chunk(i))),all=parts.flat(),columns=['Rank','HGAB project','Program','Implementing office','Flag count','Flag IDs','HGAB allocation pesos','Evidence cautions','Historical counterpart evidence','HGAB source'],quote=v=>'"'+String(v??'').replaceAll('"','""')+'"',csv=[columns.map(quote).join(','),...all.map(r=>[r.rank,r.projectName,r.program,r.office,r.flagCount,r.flags.map(f=>f.id).join('; '),r.amountPesos,(r.evidenceCautions||[]).join(' | '),historical(r),r.sourceVolume+' · p. '+r.sourcePage].map(quote).join(','))].join('\\r\\n'),url=URL.createObjectURL(new Blob(['\\ufeff'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='full-line-item-review-queue.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){status.textContent='CSV export failed: '+e.message}finally{button.disabled=false;button.textContent='Export full queue CSV'}};load()})();</script>'''.replace('ICON_MAP',icon_map)
    body += graph + shell + queue_script
    body += '<h3>How the ranking is calculated</h3><ol><li><strong>Potential insertion:</strong> the current matcher identifies no plausible NEP counterpart; ambiguous links and FAPs are excluded.</li><li><strong>No listed documents:</strong> no matched DPWH Transparency entry with listed documents exists in the current snapshot. This is independent of NEP counterpart status; documents may exist elsewhere.</li><li><strong>Incomplete documentation:</strong> each absent POW, geotagged-photo or RDC type earns one point only when that project attachment list was locally inspected. No type is inferred missing for uninspected projects.</li><li><strong>Repeated allocation amount:</strong> the same exact positive amount occurs in the same PAP at least 10 times across at least 3 named implementing offices. Roundness alone adds no point.</li><li><strong>Historical title recurrence:</strong> an FY2020–FY2026 DPWH GAA title agrees after case/punctuation normalization and removal of complete trailing station/coordinate metadata, with qualified municipality and province agreement. FY2020–FY2025 use ODV annual GAA data; FY2026 uses the DPWH Details Enrolled Copy. Work descriptions, directions, packages and phases remain; conflicting locations/tranches and disjoint chainages are excluded.</li><li><strong>Historical chainage overlap:</strong> an accepted historical counterpart has explicit, positive-length overlap. This is a scope indicator, not proof of duplicate paid work.</li><li><strong>Very short range:</strong> a recovered printed project length under 10 meters earns a review flag. Verify notation and funded extent; it does not establish an unreasonable allocation.</li></ol><p>Each qualifying type contributes one point, up to twelve possible types. Multiple historical years do not increase points. Historical recurrence and chainage overlap are related signals, so the count is not a statistical probability or independent-evidence score. Missing historical links can reflect conservative matching, incomplete coverage or unresolved names. Standard packages and legitimate amendments can produce these signals. Amounts overlap other findings; do not add them as alleged losses. Names, roles and party affiliations add no points. The complete review queue is also available as <a href="line-item-review-queue.json" download>full ranking JSON</a>.</p>'
    body += '<h3>Condition and prior-surfacing flags</h3><p>One point for rehabilitation/reconstruction/major repair when the full matched road range was assessed Good/Fair in a known pre-budget year. One point for pavement work when the full matched range has a positive recorded last-surfacing year within five budget years. Widening, approaches, slope/drainage and off-carriageway scope are excluded. Unknowns and partial coverage add no point. The five-year window is a screening choice, not an engineering service-life standard. Bridge Good/Fair context without an assessment date remains a review lead and earns no dated-condition point. Later deterioration or different funded components may justify the work. Condition, recent surfacing and historical recurrence can be related; points are not independent evidence or probabilities.</p>'
    body += '<h3>Cost-per-meter and short-range flags</h3><p>One point when allocation per stated meter exceeds both twice the peer median and Q3 + 1.5 × IQR. Peers share the work category, structure group, matched surface/condition/assessment-year context, exact official PAP and a data-derived length band, with at least 20 records whose stated lengths are at least 10 meters. No fixed 100-meter cutoff is used. Separately, a recovered printed length under 10 meters earns a denominator-warning point; verify the notation and funded extent. Extreme rates remain in this review table with a caution but are excluded from rate charts. Missing lengths and insufficient peers add no point. These flags do not establish overpricing: width, terrain, structures, quantities and funded extent remain unverified. <a href="cost-per-km.html#length-density-groups">See full rate and grouping methodology</a>.</p>'
    body += '<h3>How all twelve summary findings relate to this queue</h3>' + table(['Summary finding', 'Treatment in the line-item ranking'], [
        ['1 · Equal RCS packages', 'Repeated-amount flag if its existing thresholds qualify; no extra point for belonging to RCS. Needs weighting requires installation evidence.'],
        ['2 · HGAB insertion candidates', 'Potential-insertion flag; matching uncertainty remains explicit.'],
        ['3 · Multi-purpose buildings', 'MPB records qualify through the same flags as other work. Program membership earns no point.'],
        ['4 · Recurring project titles', 'Historical title recurrence and explicit chainage overlap; related indicators, not independent evidence.'],
        ['5 · Allocation clustering', 'Repeated-amount flag. The office-level road/flood association is not an additional individual-project flag.'],
        ['6 · INSPIRE', 'Outside this domestic DPWH queue; investigated on its own agency page.'],
        ['7 · Length and chainage gaps', 'Missing lengths remain evidence cautions; recovered ranges under 10 meters receive a separate denominator-warning flag.'],
        ['8 · Allocation per stated meter', 'High relative-rate flag using category, PAP and length-band peers.'],
        ['9 · Very short printed ranges', 'A recovered sub-10-meter range earns one denominator-warning flag; verify notation and funded extent.'],
        ['10 · No selected NEP counterpart', 'Potential-insertion flag; the one-to-one screen is not proof that a project is absent from NEP.'],
        ['11 · No listed DPWH Transparency documents', 'One flag when the current snapshot has no matched entry listing documents, regardless of NEP status.'],
        ['12 · Incomplete documentation', 'One point for each missing POW, geotagged-photo or RDC type among locally inspected attachment lists; uninspected projects remain unknown.']])
    return body


if __name__ == '__main__':
    print(json.dumps(build()['summary'], indent=2))
