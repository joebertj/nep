#!/usr/bin/env python3
"""Inventory local dynasty evidence and ASOG coverage without changing ODV."""
import collections
import csv
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from review_party_list_family_links import tokens

ROOT=Path(__file__).resolve().parent
ODV=ROOT.parent/'open-data-visualization'
OUT=ROOT/'analysis_output'
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def workbook_rows(path):
    with zipfile.ZipFile(path) as archive:
        strings=[''.join(node.itertext()) for node in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        workbook=ET.fromstring(archive.read('xl/workbook.xml'))
        links={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        rid='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
        for sheet in workbook.findall('s:sheets/s:sheet',NS):
            target='xl/'+links[sheet.attrib[rid]].lstrip('/')
            if sheet.attrib['name']!='Data':continue
            with archive.open(target) as stream:
                headers=None
                for _,row in ET.iterparse(stream,events=['end']):
                    if row.tag!='{'+NS['s']+'}row':continue
                    values={}
                    for cell in row.findall('s:c',NS):
                        column=''.join(c for c in cell.attrib['r'] if c.isalpha())
                        value=cell.find('s:v',NS)
                        text=value.text if value is not None else ''
                        if cell.get('t')=='s' and text:text=strings[int(text)]
                        if cell.get('t')=='inlineStr':text=''.join(cell.find('s:is',NS).itertext())
                        values[column]=text
                    if headers is None:headers=values
                    elif any(values.values()):yield {'sourceRow':int(row.attrib['r']),**{name:values.get(col,'') for col,name in headers.items()}}
                    row.clear()

def query(sql,db=None):
    command=['duckdb']+(['-readonly',str(db)] if db else [])+['-json','-c',sql]
    output=subprocess.check_output(command,text=True).strip()
    return json.loads(output) if output else []

def build():
    path=ODV/'database/ASoG-POLITICAL-DYNASTIES-DATASET-V2016.xlsx'
    years,positions,flags=collections.Counter(),collections.Counter(),collections.Counter()
    provinces=set();count=0
    party=json.loads((OUT/'house_party_list_roster.json').read_text())['rows']
    exact=collections.defaultdict(list)
    party_keys={tokens(r['representative']):r for r in party}
    for row in workbook_rows(path):
        count+=1;years[row['Year']]+=1;positions[row['Position']]+=1;flags[row['fat']]+=1;provinces.add(row['Province'])
        key=tokens(row['First Name']+' '+row['Last Name'])
        if key in party_keys:exact[party_keys[key]['representative']].append(row)
    sources=[]
    for file in (ODV/'data/parquet').glob('*.parquet'):
        if file.name not in ['political_dynasties.parquet','relationships.parquet','party_list_members.parquet','connection_types.parquet']:continue
        sources.append({'path':str(file.relative_to(ODV)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'rowCount':query(f"SELECT count(*) AS n FROM read_parquet('{file}')")[0]['n'], 'columns':[r['column_name'] for r in query(f"DESCRIBE SELECT * FROM read_parquet('{file}')")]})
    db=ODV/'data/parquet/dynasty_data.duckdb'
    tables=[]
    for t in query('SHOW TABLES',db):
        name=t['name']
        tables.append({'table':name,'rowCount':query('SELECT count(*) AS n FROM "'+name+'"',db)[0]['n'],'columns':[r['column_name'] for r in query('DESCRIBE "'+name+'"',db)]})
    cache=ODV/'static/data/relationship_chains_cache.json'
    cached=json.loads(cache.read_text())
    csv_sources=[]
    for file in sorted((ODV/'family_analysis').rglob('*.csv')):
        with file.open(errors='replace',newline='') as stream:
            reader=csv.DictReader(stream)
            columns=reader.fieldnames or []
            if not {'person1_name','person2_name','relationship_type'}.issubset(columns):continue
            records=list(reader)
        if records:
            csv_sources.append({'path':str(file.relative_to(ODV)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'rowCount':len(records),'rowsWithSourceURL':sum(bool(r.get('source_url')) for r in records),'columns':columns,'verification':'Relationship extraction claims; confidence scores are not independent verification.'})
    report={'scope':'Local source inventory for party-list and district family-context enrichment; no public kinship assertion or allocation attribution.',
            'asog':{'path':str(path.relative_to(ODV)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'sheet':'Data','rowCount':count,'years':dict(sorted(years.items())),'provinceLabels':len(provinces),'positions':dict(positions),'dynastyFlagValues':dict(flags),
                    'interpretation':'Historical election rows and an existing dynasty flag. No person-to-person kinship edges or current legislative boundary crosswalk are present in the Data sheet. The filename version is not the observed election-year range.',
                    'exactPartyListNameCandidates':dict(exact),'matchingPolicy':'Exact full-name tokens after removing quoted nicknames; order-insensitive. These are historical identity candidates, not proof of same person or current kinship. No surname-only joins.'},
            'parquetSources':sources,'duckdb':{'path':str(db.relative_to(ODV)),'readOnly':True,'tables':tables},
            'relationshipCSVFiles':csv_sources,
            'chainCache':{'path':str(cache.relative_to(ODV)),'summary':cached['summary'],'people':len(cached['people']),'chains':len(cached['chains']),
                          'limitations':'Includes family, political, contractor and party-list connections. Shared organization and business connections must not be converted into family edges.'},
            'nextJoinPolicy':['Keep source-specific person IDs; never assume IDs agree across independent databases.','Resolve current official identity, district and term against historical rows before using a family link.','Retain relationship direction, description, source URL and dates. Check referenced evidence before marking verified.','Record unmatched identities and contradictory claims for review. Do not infer relatives from surname or a dynasty flag.','Display verified kinship as descriptive context in tables; keep geographic allocation calculations unchanged.']}
    (OUT/'odv_dynasty_source_inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report

if __name__=='__main__':
    report=build()
    print(json.dumps({'asogRows':report['asog']['rowCount'],'years':list(report['asog']['years']),'exactHistoricalPartyListNameCandidates':len(report['asog']['exactPartyListNameCandidates']),'parquetSources':len(report['parquetSources']),'duckdbTables':len(report['duckdb']['tables']),'cachedChains':report['chainCache']['chains']},indent=2))
