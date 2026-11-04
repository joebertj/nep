#!/usr/bin/env python3
"""Publish sharded, public project evidence for shared Details dialogs.

Only explicit project identifiers and complete normalized titles are indexed.
Amounts and stages remain separate observations. Private SEC/person records and
document signatory lists are deliberately outside this public field allowlist.
"""
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUT = STATIC / 'project-evidence'
FIELDS = '''year fiscalYear fiscal_year stage category program pap pap1 pap2 pap3 pap4 uacs code office region district legDistricts
 amountPesos allocationPesos amount_pesos amount source sourceVolume sourcePage printedPage sourceId
 agency province municipality barangay division facilityType secondTotal thirdTotal delta secondAmount thirdAmount
 projectType projectCount currentAmountPesos currentLineItems historicalYearsAvailable historicalAveragePesos
 historicalMaximumPesos historicalPeakYear changeVsAveragePct excessOverMaximumPesos changeVsMaximumPct
 source_code comparison_year prior_source similarity_pct current_chainage prior_chainage chainage_overlap
 secondJhsPs thirdJhsPs secondJhsMooe thirdJhsMooe secondShsMooe thirdShsMooe secondPage thirdPage secondSource thirdSource
 status documentStatus matchBasis nepPairStatus reviewStatus comparison title_similarity_pct
 closest_nep_title closest_nep_office closest_nep_amount_pesos nepTitle nepId nepPesos nep_id
 hgabId hgab_id id code projectCode allocationAdjustmentPesos amount_delta_pesos
 quantity unit costBasis amountBasis lengthMeters lengthKm lengthStatus lengthMethod lengthEvidence
 allocationPerStatedMeter allocationPerStatedKm typicalPeerRate peerRateMultiple peerRecords peerBand
 highRateCandidate graphExtreme scopeNote surfaceDisplay recordedConditionDisplay surfacingYearDisplay
 surfacePeerGroup laneRateStatus titleStatedLanes allocationPerTitleLaneMeter inventoryEffectiveLanes
 allocationPerInventoryLaneMeterProxy allocationPerInventoryAssetLaneMeter approximateLengthMeters
 approximateAllocationPerMeter approximationStatus chainage_status chainageStatus chainage_overlap
 tranche_status tranche_detail buildingType retention coordinateStatus flagCount modeRank modePopulation modeMultiple
 modeAmount sameAmountCount place placeEvidence legAttributionStatus insertionStatus'''.split()
NESTED = '''flags evidenceCautions historicalMatches withinStageRepeatPairs lengthReview
 deoLegCrosswalk transparency plausibleCounterparts coordinateReviewFlags lengthReview
 laneInventoryEvidence assetContextEvidence rangesMeters coordinateSegments historical
 nepCounterpart selectedNepMatch costCategoryBreakdown summaryMetadata reviewPages historyPoints linkedProjectRecords
 repeatComparison sourceEvidence reviewFlags coordinate representativeCards transparencyLinks'''.split()
SAFE_NESTED = set(FIELDS + '''label evidence summaryFinding groupCount officeCount gaaYear gaaTitle gaaAmountPesos
 reason basis note type url documentLinks documentCount portalTitle matchBasis projectName title name
 sourcePage sourceUrl status count amount sharePct submittedAmountPesos evaluatedAmountPesos
 category itemCode description componentContext componentContexts printedUnitCostPesos inclusiveUnitCostPesos
 calculatedUnitCostPesos directCostSharePct manualReview observedPages arithmeticStatus page kind
 qualitativeFacts componentBreakdownStatus value unit section peerMedian peerQ1 peerQ3 peerIqr
 leg legProvince deoAreaFraction legAreaFraction overlapMeters sourceVolume source
 left right chainage has_current_range has_prior_range overlaps contextEvidence titleSimilarity
 current_chainage prior_chainage chainage_overlap chainage_status districtId costCategory
 detail latitude longitude profileUrl photoUrl resolutionStatus memberStatus'''.split())


def key(value):
    # Match the browser normalizer exactly: accents are removed, while smart
    # quotes/dashes separate tokens rather than joining neighboring words.
    value = ''.join(char for char in unicodedata.normalize('NFKD', str(value or ''))
                    if not '\u0300' <= char <= '\u036f').lower()
    return ' '.join(re.findall('[a-z0-9]+', value))


def bucket(value):
    result = 2166136261
    for char in value.encode():
        result = ((result ^ char) * 16777619) & 0xffffffff
    return f'{result & 255:02x}'


def safe(value):
    if isinstance(value, dict):
        return {k: safe(v) for k, v in value.items() if k in SAFE_NESTED and v is not None and v != ''}
    if isinstance(value, list):
        return [safe(v) for v in value]
    return value


def main():
    records = {}
    inputs = []

    def add(row, dataset, title=None, context=None):
        title = title or row.get('projectName') or row.get('project_name') or row.get('name') or row.get('title') or row.get('project')
        if not isinstance(title, str) or (len(key(title)) < 5 and not row.get('_lookupKey')):
            return
        fields = {field: row[field] for field in FIELDS if row.get(field) is not None and row.get(field) != ''}
        for field, value in (context or {}).items():
            fields.setdefault(field, value)
        evidence = {field: safe(row[field]) for field in NESTED if row.get(field)}
        documents = []
        for doc in row.get('documents') or []:
            documents.append({**{k: doc[k] for k in ['kind', 'status', 'url', 'pageCount', 'scopeNote', 'reviewPages'] if doc.get(k) is not None},
                              'billRows': [safe(r) for r in doc.get('rows', [])],
                              'costCategories': [safe(r) for r in doc.get('costCategoryBreakdown', [])]})
        if documents:
            evidence['documents'] = documents
        identifiers = [str(row[f]) for f in ['hgabId', 'hgab_id', 'id', 'code', 'projectCode', 'sourceId','source_code','apiId']
                       if row.get(f) and re.fullmatch(r'(?:HB\d+-[23]-[\w-]+|2027DPWH-Proposal-\d+|nep[_:-][\w:-]+|ib:p\d+:r\d+)', str(row[f]), re.I)]
        linked = []
        transparency = row.get('transparency') or {}
        for value in [transparency.get('code'), row.get('nepId'), row.get('nep_id'), row.get('nep_api_id')]:
            if value:
                linked.append(str(value))
        item = {'title': title, 'lookupKey':row.get('_lookupKey',key(title)), 'dataset': dataset, 'identifiers': identifiers, 'linkedIds': linked,
                'year': fields.get('year', fields.get('fiscalYear', fields.get('fiscal_year'))),
                'stage': fields.get('stage'), 'fields': fields, 'evidence': evidence}
        digest = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
        item['recordId'] = digest
        records[digest] = item

    def walk(value, dataset, context=None):
        if isinstance(value, dict):
            if value.get('project') and value.get('prior_project'):
                add({**value,'code':value.get('source_code'),'year':2027,'stage':'NEP',
                     'amountPesos':value.get('amount_2027'),
                     'historicalMatches':[{'year':value.get('comparison_year'),'title':value['prior_project'],
                                           'amountPesos':value.get('prior_amount'),'source':value.get('prior_source'),
                                           'chainage_status':value.get('chainage_status'),'chainage_overlap':value.get('chainage_overlap')} ]},dataset,title=value['project'])
            if value.get('gaaTitle') and value.get('projectName'):
                add({**value,'year':2027,'stage':'HGAB 3rd','historicalMatches':[{'year':value.get('gaaYear'),
                    'title':value['gaaTitle'],'amountPesos':value.get('gaaAmountPesos'),'source':value.get('gaaSource'),
                    'chainageStatus':value.get('chainageStatus')}]},dataset)
            if isinstance(value.get('left'),dict) and isinstance(value.get('right'),dict):
                for side in ['left','right']:
                    add({**value[side],'year':2027,'stage':value.get('stage'),
                         'repeatComparison':{k:value[k] for k in ['left','right','kind','titleSimilarity','contextEvidence','chainage'] if k in value}},dataset)
            title = value.get('projectName') or value.get('project_name') or value.get('name') or value.get('title')
            if title and any(k in value for k in ['amountPesos','allocationPesos','amount_pesos','amount','hgabId','hgab_id','code','sourcePage','lengthMeters']):
                add(value, dataset, title=title, context=context)
            for k, v in value.items():
                if k == 'projectDetails' and isinstance(v,dict):
                    for identifier, detail in v.items():
                        if isinstance(detail,dict):add({**detail,'hgabId':identifier},dataset,context=context)
                if k not in {'people','officers','incorporators','top25','sources','documents'}:
                    walk(v, dataset, context)
        elif isinstance(value, list):
            for row in value:
                walk(row, dataset, context)

    names = ['line-item-review-queue.json','undocumented-hgab-data.json','cost-per-km-data.json',
             'mpb-data.json','fmr-data.json','deped-data.json','hfep-data.json','nia-data.json',
             'dpwh-data.json','historical-allocations-data.json','repeats-historical-data.json',
             'nia-irrigation-data.json','out-of-place-data.json','rcs-data.json','flood-control-pattern-data.json',
             'within-stage-repeats.json']
    for name in names:
        path = STATIC / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        walk(payload, name, {'year':2027,'stage':'HGAB 3rd'} if name in names[:7] else None)
        inputs.append(name)
    # Some older report builders still expose their public project model as a
    # JSON literal inside a script. Decode the literal only; never evaluate JS.
    decoder = json.JSONDecoder()
    for path in sorted(STATIC.glob('*.html')):
        text = path.read_text()
        for index, match in enumerate(re.finditer(r'\b(?:const\s+D|window\.[A-Z_]+_DATA)\s*=\s*(?=\{)', text)):
            try:
                payload, _ = decoder.raw_decode(text[match.end():])
            except ValueError:
                continue
            walk(payload, path.name + ' · embedded public source ' + str(index + 1))
            inputs.append(path.name)
        for match in re.finditer(r"fetch\(\s*['\"]([^'\"]+\.json)(?:\?[^'\"]*)?['\"]",text):
            relative=match[1]
            if '://' in relative or relative.startswith('/'):
                continue
            candidate=(STATIC/relative).resolve()
            if STATIC not in candidate.parents or not candidate.is_file() or relative in inputs or candidate.stat().st_size>80_000_000:
                continue
            try:payload=json.loads(candidate.read_text())
            except (ValueError,OSError):continue
            walk(payload,relative)
            inputs.append(relative)
    path = STATIC / 'integrated-project-data.json'
    if path.exists():
        integrated_projects = json.loads(path.read_text())['projects']
        for row in integrated_projects:
            add(row, path.name)
        inputs.append(path.name)
        categories={'flood control':'Flood control','mpb':'Multi-purpose building','multi purpose building':'Multi-purpose building',
                    'multi purpose buildings':'Multi-purpose building','road':'Road','roads':'Road','bridge':'Bridge','bridges':'Bridge'}
        by_category_year=defaultdict(list)
        by_district_category=defaultdict(list)
        for row in integrated_projects:
            mini={k:row[k] for k in ['year','stage','category','name','amountPesos','source','districtId'] if k in row}
            by_category_year[(row['category'],row['year'])].append(mini)
            by_district_category[(row['districtId'],row['category'])].append(mini)
        aggregate_path=STATIC/'historical-allocations-data.json'
        if aggregate_path.exists():
            for row in json.loads(aggregate_path.read_text())['rows']:
                category=categories.get(key(row['projectType']))
                add({**row,'category':category,'stage':'HGAB 3rd' if row['year']==2027 else 'GAA',
                     '_lookupKey':key(row['projectType'])+' year '+str(row['year']),
                     'linkedProjectRecords':by_category_year.get((category,row['year']),[]),
                     'scopeNote':'The aggregate retains the source total. Linked project records below contain the independently district-assigned subset; unassigned records are excluded from that list.'},aggregate_path.name,title=row['projectType'])
        pattern_path=STATIC/'flood-control-pattern-data.json'
        if pattern_path.exists():
            for row in json.loads(pattern_path.read_text()).get('districtFamilyScan',{}).get('currentVsHistory',[]):
                add({**row,'year':2027,'stage':'HGAB 3rd',
                     '_lookupKey':key(row['category'])+' district '+key(row['district']),
                     'linkedProjectRecords':by_district_category.get((row['districtId'],row['category']),[])},pattern_path.name,title=row['category'])
    path = STATIC / 'dpwh-in-depth-data.json'
    if path.exists():
        payload = json.loads(path.read_text())
        for shard in payload.get('arrayShards', {}).get('projects', []):
            for row in json.loads((STATIC / shard['path']).read_text()):
                add(row, 'DPWH Transparency / parsed project documents', context={'year':2027,'stage':'NEP / Transparency source'})
        inputs.append(path.name)

    shards = defaultdict(lambda: {'titles': defaultdict(list)})
    ids = defaultdict(set)
    for row in records.values():
        title_key = row['lookupKey']
        shard = bucket(title_key)
        shards[shard]['titles'][title_key].append(row)
        for identifier in row['identifiers']:
            ids[identifier].add(shard)
    OUT.mkdir(exist_ok=True)
    files = {}
    for code, data in sorted(shards.items()):
        body = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
        digest = hashlib.sha256(body).hexdigest()[:12]
        target = OUT / f'{code}.json'
        if not target.exists() or target.read_bytes() != body:
            temporary = target.with_suffix('.json.tmp')
            temporary.write_bytes(body)
            temporary.replace(target)
        files[code] = {'path': f'{code}.json', 'version': digest, 'bytes': len(body)}
    manifest = {'schemaVersion':1,'generatedAtUtc':datetime.now(timezone.utc).isoformat(),
                'recordCount':len(records),'inputs':inputs,'shards':files,
                'idBuckets':{identifier:sorted(codes) for identifier,codes in ids.items()},
                'matching':'Exact source identifier, or complete normalized title with available year, stage and allocation context. Separate source observations are not added together.'}
    temporary = OUT / 'manifest.json.tmp'
    temporary.write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':'))+'\n')
    temporary.replace(OUT / 'manifest.json')
    print(json.dumps({'records':len(records),'shards':len(shards),'bytes':sum(x['bytes'] for x in files.values()),'largestShard':max(x['bytes'] for x in files.values())}))


if __name__ == '__main__':
    main()
