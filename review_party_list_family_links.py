#!/usr/bin/env python3
"""Audit ODV relationship claims; never use them to attribute allocations."""
import json
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'analysis_output'
ODV = ROOT.parent / 'open-data-visualization'

def tokens(name):
    name = re.sub(r'"[^"]*"|“[^”]*”', '', name)
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return tuple(sorted(re.findall(r'[a-z0-9]+', name)))

def build():
    parquet = ODV / 'data/parquet'
    # File paths are fixed workspace paths. DuckDB runs in memory, read-only.
    sql = f"""SELECT r.*, t.description AS relationship_category,
        struct_pack(id:=p.id,first_name:=p.first_name,middle_name:=p.middle_name,last_name:=p.last_name,
          normalized_name:=p.normalized_name,nickname:=p.nickname,"position":=p.position,
          province:=p.province,municipality_city:=p.municipality_city,"year":=p.year) AS person,
        struct_pack(id:=q.id,first_name:=q.first_name,middle_name:=q.middle_name,last_name:=q.last_name,
          normalized_name:=q.normalized_name,nickname:=q.nickname,"position":=q.position,
          province:=q.province,municipality_city:=q.municipality_city,"year":=q.year) AS related_person
      FROM read_parquet('{parquet}/relationships.parquet') r
      LEFT JOIN read_parquet('{parquet}/political_dynasties.parquet') p ON p.id=r.person_id
      LEFT JOIN read_parquet('{parquet}/political_dynasties.parquet') q ON q.id=r.related_person_id
      LEFT JOIN read_parquet('{parquet}/connection_types.parquet') t ON t.id=r.relationship_type"""
    records = json.loads(subprocess.check_output(['duckdb', '-json', '-c', sql], text=True))
    party = json.loads((DATA / 'house_party_list_roster.json').read_text())['rows']
    districts = json.loads((DATA / 'congress_benchmark.json').read_text())['rows']
    aliases = {r['district']: {tokens(r['representative'])} for r in districts}
    for filename in ['appropriations_roster.json', 'house_leadership_roles.json']:
        for m in json.loads((DATA / filename).read_text())['members']:
            if m.get('district') in aliases:
                aliases[m['district']].add(tokens(m.get('officialName', m['representative'])))
    def names(person):
        return {tokens(person.get('normalized_name') or ''), tokens(' '.join(person.get(k) or '' for k in ['first_name', 'middle_name', 'last_name']))} - {()}
    def party_matches(person):
        ns=names(person)
        return [{'organization': r['organization'], 'officialName': r['representative']} for r in party if tokens(r['representative']) in ns]
    def leg_matches(person):
        ns=names(person)
        return [{'district': r['district'], 'representative': r['representative']} for r in districts if aliases[r['district']] & ns]
    claims=[]
    historical=[]
    for r in records:
        a, b = party_matches(r['person']), party_matches(r['related_person'])
        category = r.get('relationship_category') or 'Unknown type'
        family = category in {'Parent-child relationship','Marriage relationship','Sibling relationship','Extended family relationship','In-law relationship'}
        historical_party=any(re.search(r'party[- ]list', str(p.get('position') or ''), re.I) for p in [r['person'],r['related_person']])
        if not a and not b and not historical_party:
            continue
        r.update(partyListEndpointMatches={'person':a,'relatedPerson':b}, geographicEndpointMatches={'person':leg_matches(r['person']), 'relatedPerson':leg_matches(r['related_person'])},
                 familyType=family, status='Needs source and current identity review', sourceURLPresent=bool(r.get('source_url')),
                 matchingBasis='Exact full-name tokens after removing quoted nicknames, allowing order changes and sourced official/display aliases; no substring, nickname inference or surname-only matching')
        if a or b:
            claims.append(r)
        if historical_party:
            historical.append(r)
    direct=[r for r in claims if r['familyType'] and ((r['partyListEndpointMatches']['person'] and r['geographicEndpointMatches']['relatedPerson']) or (r['partyListEndpointMatches']['relatedPerson'] and r['geographicEndpointMatches']['person']))]
    result={'scope':'Private review of historical ODV relationship claims against recovered party-list roster and current district identities. No relationship is independently verified by this script.',
            'policy':'Kinship does not establish party-list control, geographic representation, allocation authorship or receipts. No allocations are reassigned or summed through family relationships. Historical offices and shared names require review. A source URL and model confidence are not verification.',
            'summary':{'relationshipRecordsRead':len(records),'recordsTouchingExactPartyListIdentity':len(claims),'familyClaimsBetweenRosterEndpoints':len(direct),'familyClaimsWithSourceURL':sum(r['sourceURLPresent'] for r in direct),'historicalPartyListEndpointRecords':len(historical),'historicalPartyListFamilyClaims':sum(r['familyType'] for r in historical)},
            'familyClaimsBetweenRosterEndpoints':direct,'allPartyListEndpointClaims':claims,
            'historicalPartyListEndpointClaims':historical,
            'sources':[str(p.relative_to(ODV)) for p in [parquet/'relationships.parquet',parquet/'political_dynasties.parquet',parquet/'connection_types.parquet']]}
    (DATA / 'party_list_family_link_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

if __name__=='__main__':
    print(json.dumps(build()['summary'],indent=2))
