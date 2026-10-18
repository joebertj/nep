"""Surface, condition and surfacing evidence for exact inventory asset matches."""
import re
from collections import Counter,defaultdict
from lane_cost_enrichment import rows,key

RECENT_SURFACING_YEARS=5
BUDGET_YEAR=2027
KNOWN_CONDITIONS={'Good','Fair','Poor','Bad'}

def valid_year(value):
    try:year=int(value)
    except (TypeError,ValueError):return None
    return year if 1900<=year<BUDGET_YEAR else None

def segments(ranges,records,fields):
    """Partition complete measure ranges; duplicated claims never add length."""
    cells=[]
    for low,high in ranges:
        cuts=sorted({low,high}|{float(r[k]) for r in records for k in ['START','END_'] if isinstance(r.get(k),(int,float)) and low<r[k]<high})
        for a,b in zip(cuts,cuts[1:]):
            mid=(a+b)/2
            active=[r for r in records if isinstance(r.get('START'),(int,float)) and isinstance(r.get('END_'),(int,float)) and r['START']<=mid<r['END_']]
            cells.append({'meters':b-a,'ids':[r['OBJECTID'] for r in active],
                **{field:sorted({str(r.get(field) or '').strip() for r in active}) for field in fields}})
    return cells

class Context:
    def __init__(self,inventory):
        self.inventory=inventory;self.condition=defaultdict(list)
        for row in rows('road_condition',inventory.sources):self.condition[row.get('SECTION_ID')].append(row)

    def enrich(self,row):
        row.update({'surfaceDisplay':'Not matched','recordedConditionDisplay':'Not matched',
            'surfacingYearDisplay':'Unknown','surfacePeerGroup':'Unknown surface / condition context',
            'rehabGoodFairReview':False,'recentSurfacingReview':False,
            'bridgeGoodFairContextReview':False,
            'inventoryPriorityReview':'No supported condition / surfacing screen',
            'assetContextEvidence':None})
        e=row.get('laneInventoryEvidence')
        if not e:return
        rehabilitation=bool(re.search(r'\brehabilitation\b|\breconstruction\b|\bmajor repair\b',row['program']+' '+row['projectName'],re.I))
        excluded_scope=bool(re.search(r'\bwidening\b|\bnew bridges\b|\bapproaches\b|\bslope\b|\bslips\b|\bdrainage\b|\boff.carriageway\b',row['program']+' '+row['projectName'],re.I))
        evidence={'scope':'Exact asset identity; recorded inventory context, not verified FY2027 condition',
            'budgetYear':BUDGET_YEAR,'recentSurfacingWindowYears':RECENT_SURFACING_YEARS}
        if e.get('bridgeId'):
            candidates=self.inventory.bridges[e['bridgeId']]
            if len(candidates)!=1:return
            b=candidates[0]
            if row.get('region') and key(row['region'])!=key(b.get('REGION')):return
            condition=str(b.get('CONDITION') or 'Unknown').strip()
            surface=str(b.get('BR_TYPE1') or 'Unknown').strip()
            row['surfaceDisplay']='Bridge material: '+surface
            row['recordedConditionDisplay']=condition+' · assessment year unknown'
            row['surfacePeerGroup']='Bridge '+surface+' / '+condition+' / assessment year unknown'
            evidence.update({'bridgeId':e['bridgeId'],'bridgeObjectId':b['OBJECTID'],
                'condition':condition,'assessmentYear':None,'assessmentDatePolicy':'No construction, edit or copyright date is substituted for assessment year'})
            if rehabilitation and condition in {'Good','Fair'} and not excluded_scope:
                row['bridgeGoodFairContextReview']=True
                row['inventoryPriorityReview']='Good/Fair bridge in inventory; assessment date needed before a dated rehabilitation flag'
            row['assetContextEvidence']=evidence;return
        section=e.get('sectionId');ranges=e.get('mappedInventoryRangesMeters')
        if not section or not ranges:return
        records=[r for r in self.condition[section] if not row.get('region') or key(r.get('REGION'))==key(row['region'])]
        cells=segments(ranges,records,['CONDITION','YEAR','SURFACE1'])
        lane_cells=segments(ranges,self.inventory.roads[section],['YR_LAST_SU','PVMT_TYPE','SLAB_THICK'])
        total=sum(c['meters'] for c in cells)
        if not total:return
        conditions=sorted({v for c in cells for v in c['CONDITION'] if v})
        surfaces=sorted({v for c in cells for v in c['SURFACE1'] if v})
        years=sorted({valid_year(v) for c in cells for v in c['YEAR'] if valid_year(v)})
        assessed=sum(c['meters'] for c in cells if len(c['CONDITION'])==1 and c['CONDITION'][0] in KNOWN_CONDITIONS and len(c['YEAR'])==1 and valid_year(c['YEAR'][0]))
        surface_complete=all(len(c['SURFACE1'])==1 and c['SURFACE1'][0] not in {'','Not Known','Unknown'} for c in cells)
        full_assessment=abs(assessed-total)<.001
        row['surfaceDisplay']=' / '.join(surfaces) if surface_complete else 'Partial / unknown surface coverage'
        row['recordedConditionDisplay']=(' / '.join(conditions) or 'Unknown')+' · '+('/'.join(map(str,years)) or 'year unknown')
        if not full_assessment:row['recordedConditionDisplay']+=' · partial/unassessed'
        year_cells=[valid_year(c['YR_LAST_SU'][0]) if len(c['YR_LAST_SU'])==1 else None for c in lane_cells]
        known_surfacing=[y for y in year_cells if y]
        complete_surfacing=bool(year_cells) and all(y is not None for y in year_cells)
        if known_surfacing:
            low,high=min(known_surfacing),max(known_surfacing)
            row['surfacingYearDisplay']=(str(low) if low==high else f'{low}–{high}')+('' if complete_surfacing else ' · partial; others unknown')
        if surface_complete and full_assessment:
            row['surfacePeerGroup']=' / '.join(surfaces)+' | '+' / '.join(conditions)+' | assessment '+','.join(map(str,years))
        if rehabilitation and not excluded_scope:
            row['rehabGoodFairReview']=full_assessment and bool(conditions) and set(conditions)<={'Good','Fair'}
        surfacing_work=rehabilitation or bool(re.search(r'preventive maintenance|resurfac|asphalt|reblocking',row['program']+' '+row['projectName'],re.I))
        if surfacing_work and not excluded_scope:
            row['recentSurfacingReview']=complete_surfacing and min(known_surfacing)>=BUDGET_YEAR-RECENT_SURFACING_YEARS
        flags=[]
        if row['rehabGoodFairReview']:flags.append('Rehabilitation on fully matched recorded Good/Fair segment · verify subsequent deterioration and work scope')
        if row['recentSurfacingReview']:flags.append(f'Pavement work within {RECENT_SURFACING_YEARS} budget years of recorded surfacing · verify prior scope')
        row['inventoryPriorityReview']='; '.join(flags) if flags else ('No qualifying condition/recency flag; not a clearance' if full_assessment else 'Incomplete assessment coverage; no condition flag')
        pavement=sorted({v for c in lane_cells for v in c['PVMT_TYPE'] if v and v not in {'NONE','Not Specified'}})
        evidence.update({'sectionId':section,'mappedRangesMeters':ranges,
            'conditionObjectIds':sorted({i for c in cells for i in c['ids']}),
            'laneInventoryObjectIds':sorted({i for c in lane_cells for i in c['ids']}),
            'assessedCoveragePct':round(100*assessed/total,4),'surfaceFullCoverage':surface_complete,
            'conditions':conditions,'assessmentYears':years,'pavementTypes':pavement,
            'surfacingYears':sorted(set(known_surfacing)),'surfacingYearFullCoverage':complete_surfacing,
            'surfaceSource':'SURFACE1 from road condition inventory; pavement type and last-surfacing year from older lane inventory',
            'caution':'Condition may have deteriorated after assessment. Good/Fair ratings do not rule out structural, safety, drainage or preventive work. Zero surfacing years remain unknown; reconstruction years do not substitute.'})
        row['assetContextEvidence']=evidence

def summary(data):
    result={}
    for category in ['Roads','Bridges','FMR','Mixed roads / bridges']:
        selected=[r for r in data['projects'] if r['category']==category]
        result[category]={'lineItems':len(selected),'withContext':sum(bool((r.get('assetContextEvidence') or {}).get('bridgeObjectId') or (r.get('assetContextEvidence') or {}).get('conditionObjectIds')) for r in selected),
            'fullyAssessedRoadRecords':sum((r.get('assetContextEvidence') or {}).get('assessedCoveragePct')==100 for r in selected),
            'rehabGoodFairCandidates':sum(r.get('rehabGoodFairReview',False) for r in selected),
            'recentSurfacingCandidates':sum(r.get('recentSurfacingReview',False) for r in selected)}
        result[category]['bridgeGoodFairUndatedContext']=sum(r.get('bridgeGoodFairContextReview',False) for r in selected)
    return {'byCategory':result,'budgetYear':BUDGET_YEAR,'recentSurfacingWindowYears':RECENT_SURFACING_YEARS,
        'method':'Condition flag: rehabilitation/reconstruction/major repair only, full matched road range assessed Good/Fair with a known pre-budget assessment year. Recent-surfacing flag: rehabilitation, preventive maintenance or other explicitly described pavement work where the full matched range has a positive recorded last-surfacing year within five budget years; unknown/zero values are not filled. Widening, approaches, slope/drainage and off-carriageway scopes excluded. Bridge condition is displayed, but an unknown assessment year prevents the dated flag.',
        'limits':'Review leads, not proof of waste or incorrect prioritization. Assessment and budget dates differ; later deterioration, structural/safety work or different funded components may justify rehabilitation. Last-surfacing inventory is older and cannot establish that no later work occurred.'}
