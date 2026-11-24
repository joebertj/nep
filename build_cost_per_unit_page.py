#!/usr/bin/env python3
"""Build only the peer-comparison cost-per-unit page."""
import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def _compact_bill_rows(rows):
    result=[]
    for row in rows or []:
        if not row.get('description') or not str(row.get('unit') or '').strip():
            continue
        result.append({key:row.get(key) for key in
                       ('costBasis','description','unit','amountPesos','quantity','sourcePage')
                       if key in row})
    return result


def _bill_key(value):
    text=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',text).strip()


def _unit_key(value):
    text=str(value or '').lower().replace('²','2').replace('³','3')
    key=re.sub(r'[^a-z0-9]+',' ',text).strip()
    aliases={'kgs':'kg','kilogram':'kg','kilograms':'kg','cubic meter':'cu m','cubic meters':'cu m',
             'm3':'cu m','sqm':'sq m','square meter':'sq m','square meters':'sq m','m2':'sq m',
             'ea':'each','unit':'each','ls':'lump sum','l s':'lump sum','sum':'lump sum',
             'lump':'lump sum','lumpsum':'lump sum'}
    return aliases.get(key,key)


def _project_family(value):
    text=str(value or '')
    if re.search(r'\b(?:multi\s*[- ]?purpose\s+building|mpb)\b',text,re.I): return 'Multi-Purpose Buildings (MPB)'
    if re.search(r'\birrigation\b',text,re.I): return 'Irrigation'
    if re.search(r'\bbridges?\b',text,re.I): return 'Bridges'
    if re.search(r'\broads?\b',text,re.I): return 'Roads'
    text=re.sub(r'\s+[–—-]\s+.*\b(?:District Engineering Office|Regional Office)\b.*$','',text,flags=re.I)
    text=re.sub(r'\s+[–—-]\s+.*\b(?:National Capital Region|Cordillera Administrative Region|Region\s+[IVXLC0-9-]+|NCR|CAR)\s*$','',text,flags=re.I)
    return re.sub(r'\s+',' ',text).strip().strip('-–—,;')


def build_cost_per_unit_data():
    index=json.loads((STATIC/'dpwh-in-depth-data.json').read_text(encoding='utf-8'))
    def read_array(name):
        result=[]
        for shard in index.get('arrayShards',{}).get(name,[]):
            path=STATIC/shard['path']
            values=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(values,list): raise ValueError(f'Invalid {name} shard: {path}')
            result.extend(values)
        return result

    source_groups=read_array('summaryPeerGroups')
    groups=[];refs_by_group={};files={}
    for group in source_groups:
        group_id=str(group.get('id'))
        refs={ref.get('code') for ref in group.get('projects') or [] if ref.get('code')}
        refs_by_group[group_id]=refs
        filename='cost-per-unit-group-'+re.sub(r'[^a-z0-9-]+','-',group_id.lower()).strip('-')+'.json'
        groups.append({key:group.get(key) for key in
                       ('id','family','projectCount','summaryProjectCount','detailProjectCount')})
        files[group_id]=filename

    grouped_projects={group_id:[] for group_id in refs_by_group}
    project_metadata={}
    for project in read_array('projects'):
        code=project.get('code')
        if not code: continue
        project_metadata[code]={key:project.get(key) for key in ('code','name','office','region')}
        source_doc=next((doc for doc in project.get('documents') or []
                         if doc.get('kind')=='pow' and
                         (doc.get('rows') or doc.get('reviewPages') or doc.get('costCategoryBreakdown'))),None)
        if not source_doc: continue
        rows=_compact_bill_rows(source_doc.get('rows'))
        if not rows: continue
        compact={key:project.get(key) for key in ('code','name','office','region')}
        compact['documents']=[{'kind':'pow','url':source_doc.get('url') or '','rows':rows}]
        for group_id,refs in refs_by_group.items():
            if code in refs: grouped_projects[group_id].append(compact)

    grouped_hgab={group_id:[] for group_id in refs_by_group}
    override_codes={group_id:set() for group_id in refs_by_group}
    summary_hgab=[]
    for doc in read_array('costUnitHgabResults'):
        code=doc.get('proposalCode')
        rows=_compact_bill_rows(doc.get('rows'))
        family=_project_family(doc.get('hgabTitle'))
        for group_id,refs in refs_by_group.items():
            group=next(item for item in source_groups if str(item.get('id'))==group_id)
            relevant=(code in refs or family==group.get('family'))
            if not relevant: continue
            if code and doc.get('rows'): override_codes[group_id].add(code)
            if rows:
                grouped_hgab[group_id].append({key:doc.get(key) for key in
                    ('proposalCode','hgabId','code','hgabTitle')} | {'rows':rows})
        if doc.get('costCategoryBreakdown'):
            summary_hgab.append({key:doc.get(key) for key in
                ('proposalCode','hgabId','code','hgabTitle','costCategoryBreakdown')})

    group_paths={};group_payloads={}
    for group_id in refs_by_group:
        payload={'projectRefs':sorted(refs_by_group[group_id]),
                 'projects':grouped_projects[group_id],
                 'costUnitHgabResults':grouped_hgab[group_id],
                 'hgabOverrideProposalCodes':sorted(override_codes[group_id])}
        group_payloads[group_id]=payload
        serialized=json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n'
        digest=hashlib.sha256(serialized.encode()).hexdigest()[:12]
        filename=files[group_id].replace('.json','-'+digest+'.json')
        group_paths[group_id]=filename
        for target in (OUT,STATIC):
            (target/filename).write_text(serialized,encoding='utf-8')

    billboard_rows={basis:{'Roads':[],'Bridges':[]} for basis in ('as_submitted','as_evaluated')}
    bill_merges=index.get('powBillMerges',{})
    target_key='project billboard signboard|each'
    for group in source_groups:
        family=group.get('family')
        if family not in {'Roads','Bridges'}: continue
        group_id=str(group.get('id'));payload=group_payloads[group_id]
        project_by_code={project.get('code'):project for project in payload['projects']}
        overrides=set(payload['hgabOverrideProposalCodes'])
        item_rows={basis:{} for basis in billboard_rows}
        def add_bill(code,name,office,url,rows,source):
            for row in rows or []:
                basis=row.get('costBasis') or 'not_stated'
                if basis not in item_rows or not row.get('description') or not _unit_key(row.get('unit')): continue
                normalized=_bill_key(row.get('description'));merged=bill_merges.get(normalized,normalized)
                if merged+'|'+_unit_key(row.get('unit'))!=target_key: continue
                item=item_rows[basis].setdefault(code,{'code':code,'name':name,'office':office or '',
                    'url':url or '','source':source,'unit':row.get('unit') or 'each','amount':0,'quantity':0,
                    'pages':set()})
                try: amount=float(row.get('amountPesos'));quantity=float(row.get('quantity'))
                except (TypeError,ValueError): amount=quantity=0
                if math.isfinite(amount) and math.isfinite(quantity) and quantity>0:
                    item['amount']+=amount;item['quantity']+=quantity
                if row.get('sourcePage') is not None:item['pages'].add(row.get('sourcePage'))
        for project in payload['projects']:
            if project.get('code') in overrides: continue
            doc=next((x for x in project.get('documents') or [] if x.get('kind')=='pow'),None)
            if doc:add_bill(project.get('code'),project.get('name'),project.get('office'),doc.get('url'),doc.get('rows'),'Proposal')
        for doc in payload['costUnitHgabResults']:
            project=project_by_code.get(doc.get('proposalCode'))
            code=doc.get('proposalCode') or doc.get('hgabId') or doc.get('code')
            add_bill(code,doc.get('hgabTitle') or (project or {}).get('name') or doc.get('code'),
                     (project or {}).get('office'),'',doc.get('rows'),'HGAB')
        for basis,projects_for_basis in item_rows.items():
            for row in projects_for_basis.values():
                if row['quantity']<=0 or row['amount']/row['quantity']<=0: continue
                row['unitCost']=row['amount']/row['quantity'];row['family']=family
                row['pages']=sorted(row['pages'])
                billboard_rows[basis][family].append(row)
    for basis in billboard_rows:
        for family in billboard_rows[basis]:
            billboard_rows[basis][family].sort(key=lambda row:row['unitCost'])

    billboard_json=json.dumps(billboard_rows,ensure_ascii=False,separators=(',',':'))+'\n'
    billboard_hash=hashlib.sha256(billboard_json.encode()).hexdigest()[:12]
    billboard_file='cost-per-unit-billboards-'+billboard_hash+'.json'

    summary_payload={'summaryPeerGroups':source_groups,'costUnitHgabResults':summary_hgab,
                     'summaryProjectMetadata':[project_metadata[code] for code in
                        {doc.get('proposalCode') for doc in summary_hgab}
                        if code in project_metadata]}
    summary_json=json.dumps(summary_payload,ensure_ascii=False,separators=(',',':'))+'\n'
    summary_hash=hashlib.sha256(summary_json.encode()).hexdigest()[:12]
    summary_file='cost-per-unit-summaries-'+summary_hash+'.json'
    # Keep only fields consumed above the fold or by the page controls. The shared
    # in-depth export contains large reconciliation summaries that this page never
    # renders, so copying it wholesale makes every visit parse unnecessary JSON.
    page_index={key:index[key] for key in
                ('generatedAtUtc','summary','hgabCoverage','powBillMerges','powBillLabels')
                if key in index}
    page_index.update({'summaryPeerGroups':groups,'costUnitGroupFiles':group_paths,
                       'costUnitSummaryFile':summary_file,'billboardRowsFile':billboard_file})
    index_json=json.dumps(page_index,ensure_ascii=False,separators=(',',':'))+'\n'
    index_hash=hashlib.sha256(index_json.encode()).hexdigest()[:12]
    for target in (OUT,STATIC):
        (target/'cost-per-unit-index.json').write_text(index_json,encoding='utf-8')
        (target/summary_file).write_text(summary_json,encoding='utf-8')
        (target/billboard_file).write_text(billboard_json,encoding='utf-8')
        keep=set(group_paths.values())|{summary_file,billboard_file}
        for old in target.glob('cost-per-unit-group-*.json'):
            if old.name not in keep: old.unlink()
        for old in target.glob('cost-per-unit-summaries-*.json'):
            if old.name not in keep: old.unlink()
    return index_hash,{'groups':len(groups),'summaryBytes':len(summary_json.encode()),
                       'groupBytes':sum((STATIC/name).stat().st_size for name in group_paths.values()),
                       'groupSizes':{group_id:(STATIC/name).stat().st_size for group_id,name in group_paths.items()}}


def build():
    from report_table_presentation import apply_page as apply_tables, publish_assets
    from uniform_report_menu import apply_page as apply_menu

    source = ROOT / 'project_documents/cost-per-unit.html'
    script = ROOT / 'project_documents/cost-per-unit.js'
    cost_js = script.read_text(encoding='utf-8')
    indepth_js = (ROOT / 'project_documents/indepth.js').read_text(encoding='utf-8')
    loader = (ROOT / 'project_documents/dpwh-data-loader.js').read_text(encoding='utf-8')
    index_hash,cost_data_stats=build_cost_per_unit_data()
    loader_version = hashlib.sha256((loader + '\n' + index_hash).encode()).hexdigest()[:12]
    page = source.read_text(encoding='utf-8')
    page=page.replace('data-dpwh-data-mode="cost-per-unit"',
                      'data-dpwh-data-mode="cost-per-unit-index"')
    page = page.replace('src="cost-per-unit.js"',
                        f'src="cost-per-unit.js?v={hashlib.sha256(cost_js.encode()).hexdigest()[:12]}"')
    page = re.sub(r'src="dpwh-in-depth\.js(?:\?v=[^"]*)?"',
                  f'src="dpwh-in-depth.js?v={hashlib.sha256(indepth_js.encode()).hexdigest()[:12]}"', page, count=1)
    page = re.sub(r'src="dpwh-data-loader\.js(?:\?v=[^"]*)?"',
                  f'src="dpwh-data-loader.js?v={loader_version}"', page, count=1)
    page = apply_tables(apply_menu(page, 'cost-per-unit.html'), publish_assets())
    for target in (OUT, STATIC):
        target.mkdir(parents=True, exist_ok=True)
        (target / 'cost-per-unit.js').write_text(cost_js, encoding='utf-8')
        (target / 'dpwh-in-depth.js').write_text(indepth_js, encoding='utf-8')
        (target / 'dpwh-data-loader.js').write_text(loader, encoding='utf-8')
        (target / 'cost-per-unit.html').write_text(page, encoding='utf-8')
    return {'page': 'cost-per-unit.html','data':cost_data_stats}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
