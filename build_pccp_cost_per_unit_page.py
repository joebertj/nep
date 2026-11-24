#!/usr/bin/env python3
"""Build only the DPWH Atlas cost-per-unit page and its price data."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def pccp_rows(rows):
    matched=[]
    for row in rows or []:
        description=str(row.get('description') or '')
        unit=str(row.get('unit') or '').lower().replace('²','2').replace('³','3')
        unit=re.sub(r'[^a-z0-9]+',' ',unit).strip()
        if unit not in {'sq m','sqm','square meter','square meters','m2'}:
            continue
        if not re.search(r'pcc|portland cement concrete pavement|cement concrete pavement',description,re.I):
            continue
        if re.search(r'(?:removal|repair)',description,re.I):
            continue
        if not re.search(r'\b0[.,]\d{2,3}\s*m(?:m)?\b|\b\d{2,3}\s*mm\b',description,re.I):
            continue
        matched.append({key:row.get(key) for key in
                        ('costBasis','description','unit','amountPesos','quantity','sourcePage')
                        if key in row})
    return matched


def project_family(value):
    text=str(value or '')
    if re.search(r'\b(?:multi\s*[- ]?purpose\s+building|mpb)\b',text,re.I):
        return 'Multi-Purpose Buildings (MPB)'
    if re.search(r'\birrigation\b',text,re.I): return 'Irrigation'
    if re.search(r'\bbridges?\b',text,re.I): return 'Bridges'
    if re.search(r'\broads?\b',text,re.I): return 'Roads'
    text=re.sub(r'\s+[–—-]\s+.*\b(?:District Engineering Office|Regional Office)\b.*$','',text,flags=re.I)
    text=re.sub(r'\s+[–—-]\s+.*\b(?:National Capital Region|Cordillera Administrative Region|Region\s+[IVXLC0-9-]+|NCR|CAR)\s*$','',text,flags=re.I)
    return re.sub(r'\s+',' ',text).strip().strip('-–—,;')


def build_pccp_cost_data():
    """Publish only PCCP bill rows needed by this page, not all DPWH bill data."""
    index=json.loads((STATIC/'dpwh-in-depth-data.json').read_text(encoding='utf-8'))
    def read_array(name):
        result=[]
        for shard in index.get('arrayShards',{}).get(name,[]):
            path=STATIC/shard['path']
            if not path.is_file():
                raise FileNotFoundError(f'Missing {name} shard: {path}')
            values=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(values,list):
                raise ValueError(f'Invalid {name} shard: {path}')
            result.extend(values)
        return result

    projects=[]
    project_codes=set()
    for project in read_array('projects'):
        documents=[]
        for document in project.get('documents') or []:
            if document.get('kind')!='pow':
                continue
            rows=pccp_rows(document.get('rows'))
            if rows:
                documents.append({'kind':'pow','url':document.get('url') or '', 'rows':rows})
        if documents:
            project_codes.add(project.get('code'))
            projects.append({key:project.get(key) for key in ('code','name','office','region')} | {'documents':documents})

    source_groups=read_array('summaryPeerGroups')
    group_reference_codes={str(group.get('id')):{ref.get('code') for ref in group.get('projects') or []}
                           for group in source_groups}
    groups=[]
    for group in source_groups:
        refs=[{'code':ref.get('code')} for ref in group.get('projects') or []
              if ref.get('code') in project_codes]
        if not refs and group.get('projects'):
            # Keep the selector option so a group with HGAB-only PCCP rows can
            # still be selected; the unmatched proposal stub is ignored by
            # makeItems because it has no PCCP project record in this export.
            refs=[{'code':group['projects'][0].get('code')}]
        if refs:
            groups.append({'id':group.get('id'),'family':group.get('family'),
                           'projectCount':group.get('projectCount',len(group.get('projects') or [])),
                           'projects':refs})

    hgab_rows=[]
    override_codes_by_group={group_id:set() for group_id in group_reference_codes}
    for document in read_array('costUnitHgabResults'):
        if document.get('proposalCode') and document.get('rows'):
            proposal_code=document['proposalCode']
            family=project_family(document.get('hgabTitle'))
            for group in source_groups:
                group_id=str(group.get('id'))
                if proposal_code in group_reference_codes[group_id] or family==group.get('family'):
                    override_codes_by_group[group_id].add(proposal_code)
        rows=pccp_rows(document.get('rows'))
        if rows:
            hgab_rows.append({key:document.get(key) for key in
                              ('proposalCode','hgabId','code','hgabTitle')} | {'rows':rows})

    payload={
        'projects':projects,
        'summaryPeerGroups':groups,
        'costUnitHgabResults':hgab_rows,
        'hgabOverrideProposalCodesByGroup':{key:sorted(values) for key,values in override_codes_by_group.items()},
        'powBillMerges':index.get('powBillMerges',{}),
        'powBillLabels':index.get('powBillLabels',{}),
    }
    serialized=json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n'
    version=hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:12]
    for target in (OUT,STATIC):
        target.mkdir(parents=True,exist_ok=True)
        (target/'pccp-cost-per-unit-data.json').write_text(serialized,encoding='utf-8')
    return serialized,version,{'projects':len(projects),'hgabDocuments':len(hgab_rows),
                              'proposalOverrides':sum(map(len,override_codes_by_group.values())),
                              'bytes':len(serialized.encode('utf-8'))}


def build():
    from build_dpwh_indepth import publish_pccp_price_reference
    from report_table_presentation import apply_page as apply_tables, publish_assets
    from uniform_report_menu import apply_page as apply_menu

    publish_pccp_price_reference()
    script = ROOT / 'project_documents/cost-per-unit.js'
    cost_js = script.read_text(encoding='utf-8')
    indepth_js = (ROOT / 'project_documents/indepth.js').read_text(encoding='utf-8')
    loader = (ROOT / 'project_documents/dpwh-data-loader.js').read_text(encoding='utf-8')
    _,pccp_version,pccp_stats=build_pccp_cost_data()
    loader_version = hashlib.sha256((loader + '\n' + pccp_version).encode()).hexdigest()[:12]
    page = (ROOT / 'project_documents/pccp-cost-per-unit.html').read_text(encoding='utf-8')
    page = page.replace('data-dpwh-data-mode="cost-per-unit"','data-dpwh-data-mode="pccp"')
    page = page.replace('src="cost-per-unit.js"',
                        f'src="cost-per-unit.js?v={hashlib.sha256(cost_js.encode()).hexdigest()[:12]}"')
    page = re.sub(r'src="dpwh-in-depth\.js(?:\?v=[^"]*)?"',
                  f'src="dpwh-in-depth.js?v={hashlib.sha256(indepth_js.encode()).hexdigest()[:12]}"', page, count=1)
    page = re.sub(r'src="dpwh-data-loader\.js(?:\?v=[^"]*)?"',
                  f'src="dpwh-data-loader.js?v={loader_version}"', page, count=1)
    page = apply_tables(apply_menu(page, 'pccp-cost-per-unit.html'), publish_assets())
    for target in (OUT, STATIC):
        target.mkdir(parents=True, exist_ok=True)
        (target / 'cost-per-unit.js').write_text(cost_js, encoding='utf-8')
        (target / 'dpwh-data-loader.js').write_text(loader, encoding='utf-8')
        (target / 'pccp-cost-per-unit.html').write_text(page, encoding='utf-8')
    return {'page': 'pccp-cost-per-unit.html','pccpData':pccp_stats}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
