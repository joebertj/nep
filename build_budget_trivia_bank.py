#!/usr/bin/env python3
"""Expand the FY2027 trivia bank with source-linked, arithmetic-checked POW facts."""
import ast, json, random, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'analysis_output/dpwh-in-depth-data.json'
BANK=ROOT.parent/'open-data-visualization/static/nep-preview/budget-trivia-2027.json'
TARGET_AUTOGEN=108
LEG_INSERTIONS=ROOT/'analysis_output/congress_leg_insertions.json'
EXCLUDED={'2027DPWH-Proposal-11853','2027DPWH-Proposal-02306','2027DPWH-Proposal-22663','2027DPWH-Proposal-22656','2027DPWH-Proposal-00294','2027DPWH-Proposal-00296','2027DPWH-Proposal-00301'}
BAD_DESCRIPTION=re.compile(r'\b(?:total|subtotal|division|as submitted|as evaluated|see form|grand total)\b',re.I)

def number(value, places=2):
    value=round(float(value),places)
    if abs(value-round(value))<1e-9:return f'{int(round(value)):,}'
    return f'{value:,.{places}f}'.rstrip('0').rstrip('.')

def precision(value):
    rendered=f'{float(value):.6f}'.rstrip('0').rstrip('.')
    return min(6,max(2,len(rendered.partition('.')[2])))

def choices_for(value, unit='', currency=False, places=2):
    answer=round(float(value),places)
    factors=[0.6,1.4,2.0]
    distractors=[]
    for factor in factors:
        candidate=round(answer*factor,places)
        if candidate!=answer and candidate not in distractors:distractors.append(candidate)
    multiplier=2.7
    while len(distractors)<3:
        candidate=round(answer*multiplier,places);multiplier+=0.6
        if candidate!=answer and candidate not in distractors:distractors.append(candidate)
    def render(n):
        label=('₱' if currency else '')+number(n,places)
        return label if currency or not unit else label+' '+unit
    return [render(n) for n in [answer,*distractors]],render(answer)

def collect_candidates(data):
    candidates=[];seen_projects=set()
    for project in data.get('projects',[]):
        code=project.get('code')
        if not code or code in EXCLUDED:continue
        for doc in project.get('documents',[]):
            if doc.get('kind')!='pow' or not doc.get('url'):continue
            rows=[]
            for row in doc.get('rows',[]):
                description=' '.join(str(row.get('description') or '').split())
                if (not description or len(description)<9 or len(description)>125
                    or not re.search(r'[A-Za-z]{3}',description) or BAD_DESCRIPTION.search(description)):
                    continue
                if not row.get('extractionMethod','').startswith('native DPWH itemized bill'):
                    continue
                if row.get('arithmeticStatus')!='Within rounding tolerance':continue
                try:q=float(row.get('quantity'));amount=float(row.get('amountPesos'))
                except (TypeError,ValueError):continue
                unit=' '.join(str(row.get('unit') or '').split())
                page=row.get('sourcePage')
                if q<=0 or amount<5000 or not unit or not page:continue
                if re.fullmatch(r'(?:l\.?\s*s\.?|lump sum)',unit,re.I):continue
                rows.append((row,description,q,amount,unit,page))
            if not rows:continue
            # One fact per project keeps a single project from dominating a round.
            rows.sort(key=lambda r:(-r[3],r[1].casefold(),r[5]))
            chosen=rows[0]
            if code in seen_projects:continue
            seen_projects.add(code)
            candidates.append((project,doc,*chosen))
    random.Random(2027).shuffle(candidates)
    return candidates

def generated_questions(candidates):
    if len(candidates)<TARGET_AUTOGEN:
        raise RuntimeError(f'Only {len(candidates)} eligible projects; need {TARGET_AUTOGEN}')
    output=[]
    for index,(project,doc,row,description,q,amount,unit,page) in enumerate(candidates[:TARGET_AUTOGEN]):
        code=project['code'];name=project['name']
        if index%2==0:
            options,answer=choices_for(q,unit=unit,places=precision(q))
            question=f"According to the POW for {name}, what quantity is listed for {description}?"
            explanation=f"The cited bill row lists {answer}. This is a machine-extracted item quantity; check the source page for its full context."
            hint=f"Look for the quantity and unit columns beside the item description on the cited page."
            kind='quantity'
        else:
            options,answer=choices_for(amount,currency=True,places=2)
            question=f"The POW for {name} lists {number(q)} {unit} of {description}. What direct-cost item amount is shown?"
            explanation=f"The cited row shows {answer} as the submitted direct-cost item amount. It is not the full project allocation."
            hint="The item amount is the direct-cost figure; it excludes the project’s other cost components."
            kind='amount'
        source_url=doc['url'].split('#',1)[0]+f'#page={page}'
        safe_code=re.sub(r'[^a-z0-9]+','-',code.lower()).strip('-')
        safe_item=re.sub(r'[^a-z0-9]+','-',str(row.get('itemCode') or description).lower()).strip('-')[:36]
        output.append({'id':f'pow-{safe_code}-{safe_item}-{kind}','question':question,'choices':options,'answer':answer,
          'explanation':explanation,'hint':hint,'sources':[{'label':f'{name} · POW p. {page}','url':source_url}],
          'generatedFromParsedPow':True,'projectCode':code,'itemCode':row.get('itemCode'),'questionType':kind})
    return output

def pow_district_engineer_questions(data):
    """Build name questions only from people explicitly identified in POWs."""
    records={}
    for project in data.get('projects',[]):
        code=project.get('code')
        office=project.get('office')
        name=project.get('name')
        if not code or not office or not name:
            continue
        for doc in project.get('documents',[]):
            if doc.get('kind')!='pow' or not doc.get('url'):
                continue
            for person in doc.get('people',[]):
                if person.get('kind')!='district_engineer' or not person.get('name') or not person.get('sourcePage'):
                    continue
                if not str(person.get('extractionMethod','')).startswith('native PDF text'):
                    continue
                role=' '.join(str(person.get('roleText') or 'District Engineer').split())
                key=(office,person['name'])
                record={'project':project,'doc':doc,'person':person,'role':role}
                if key not in records or person['sourcePage'] < records[key]['person']['sourcePage']:
                    records[key]=record
    records=sorted(records.values(),key=lambda r:(r['project']['code'],r['person']['name']))
    names=sorted({r['person']['name'] for r in records})
    output=[]
    for index,record in enumerate(records):
        project,doc,person,role=record['project'],record['doc'],record['person'],record['role']
        answer=person['name']
        distractors=[n for n in names if n!=answer]
        rng=random.Random(2700+index)
        rng.shuffle(distractors)
        choices=[answer,*distractors[:3]]
        rng.shuffle(choices)
        page=person['sourcePage']
        code=project['code']
        safe_name=re.sub(r'[^a-z0-9]+','-',answer.lower()).strip('-')
        safe_code=re.sub(r'[^a-z0-9]+','-',code.lower()).strip('-')
        source_url=doc['url'].split('#',1)[0]+f'#page={page}'
        output.append({
            'id':f'deo-pow-engineer-{safe_code}-{safe_name}',
            'question':f"According to the POW for {project['name']} ({code}), who is listed as {role}?",
            'choices':choices,'answer':answer,
            'explanation':f"The POW text extraction lists {answer} with the role ‘{role}’ on page {page}. This records what appears in that document; it does not establish a current appointment or project responsibility.",
            'sources':[{'label':f"{project['name']} · POW p. {page}",'url':source_url}],
            'hint':'Open the linked POW page and check the name printed beside the role.',
            'difficulty':'medium','topic':'deo','questionType':'deo-pow-engineer',
            'generatedFromPowEngineer':True,'projectCode':code
        })
    return output

def leg_representative_questions():
    """Build direct representative questions from the displayed LEG table."""
    data=json.loads(LEG_INSERTIONS.read_text())
    districts=[d for d in data.get('districts',[]) if d.get('district') and d.get('representative')]
    names=[]
    for d in districts:
        name=d['representative'].split(';',1)[0].strip()
        if name and name not in names:names.append(name)
    if len(names)<4:
        raise RuntimeError('Need at least four distinct LEG representatives for answer choices')
    output=[]
    for index,district in enumerate(districts):
        answer=district['representative'].split(';',1)[0].strip()
        distractors=[name for name in names if name!=answer]
        rng=random.Random(202710+index);rng.shuffle(distractors)
        choices=[answer,*distractors[:3]];rng.shuffle(choices)
        slug=re.sub(r'[^a-z0-9]+','-',district['district'].lower()).strip('-')
        output.append({'id':f'easy-leg-representative-{slug}',
            'question':f"Who is the representative of {district['district']}?",
            'choices':choices,'answer':answer,
            'explanation':f"The district listing names {answer} as the representative of {district['district']}.",
            'hint':'Open the linked district list and find this district.',
            'sources':[{'label':'Congressional district list','url':'congress.html#leg-district-insertions'}],
            'difficulty':'basic','topic':'representatives','questionType':'leg-representative',
            'pool':'leg-potential-additions-representative','legislativeDistrict':district['district'],
            'generatedFromLegRepresentative':True})
    return output

def department_service_allocation_questions():
    """Create one-pick lookup pool from DBM's proposed FY2027 allocations."""
    # Values and recipient labels are from the cited DBM FY2027 proposal release.
    amounts=[
        ('Social Services',2456),('Economic Services',1833),('the consolidated health sector',1060),
        ('the Build Better More Infrastructure Program',1467),('DepEd',976),
        ('DPWH',644),
        ('Health (DOH, specialty hospitals, and PhilHealth)',353.8),
        ('Interior and Local Government (DILG)',332.5),('National Defense (DND)',328.8),
        ('Transportation (DOTr, PNR, and LRTA)',302.2),
        ('Agriculture and attached agencies',261.7),
        ('Social Welfare (DSWD)',241.6),('Higher Education (SUCs and CHED)',176.5),
        ('the Judiciary',86.3),
    ]
    def display(billions):
        if billions>=1000:
            value=billions/1000
            return f'₱{value:g} trillion'
        return f'₱{billions:g} billion'
    source='https://www.dbm.gov.ph/index.php/management-2/4143-dbm-submits-7-2-t-2027-people-centered-budget-to-congress-puts-education-health-jobs-at-heart-of-marcos-administration-s-final-full-year-spending-plan'
    questions=[]
    for index,(recipient,billions) in enumerate(amounts):
        distractors=sorted((n for _,n in amounts if n!=billions),key=lambda n:(abs(n-billions),n))[:3]
        answer=display(billions)
        choices=[answer,*[display(n) for n in distractors]]
        random.Random(202700+index).shuffle(choices)
        slug=re.sub(r'[^a-z0-9]+','-',recipient.lower()).strip('-')
        questions.append({'id':'medium-allocation-'+slug,
            'question':f"How much did DBM propose for {recipient} in FY2027?",
            'choices':choices,'answer':answer,
            'explanation':f"DBM proposed {answer} for {recipient}. These are proposed allocations, not final enacted appropriations or verified spending.",
            'hint':'Check the recipient’s line in DBM’s FY2027 proposed-budget summary.',
            'sources':[{'label':'DBM · Proposed FY2027 National Budget','url':source}],
            'difficulty':'medium','topic':'budget','questionType':'allocation-lookup',
            'pool':'department-service-allocation','generatedFromAllocationLookup':True})
    return questions

def deo_leg_crosswalk_questions():
    """Create medium questions in both directions from the displayed crosswalk."""
    congress=ROOT.parent/'open-data-visualization/static/nep-preview/congress.html'
    html=congress.read_text(encoding='utf-8')
    match=re.search(r'const deoLegRows=(\[.*?\]);',html,re.S)
    if not match:
        raise RuntimeError('Could not locate the DEO–district rows in congress.html')
    rows=ast.literal_eval(match.group(1))
    deo_to_leg={};leg_to_deo={}
    for deo,leg,_amount in rows:
        deo_to_leg.setdefault(deo,set()).add(leg)
        leg_to_deo.setdefault(leg,set()).add(deo)
    def district_label(value):
        return value.replace(' · ', ' ')
    def options(answer, distractors, seed):
        distractors=sorted(set(distractors)-{answer})
        rng=random.Random(seed);rng.shuffle(distractors)
        choices=[answer,*distractors[:3]];rng.shuffle(choices)
        return choices
    source={'label':'DPWH district allocation crosswalk','url':'congress.html#deoLegTitle'}
    questions=[]
    for index,(deo,districts) in enumerate(sorted(deo_to_leg.items())):
        district=sorted(districts)[0]
        answer=district_label(district)
        other_districts=[district_label(value) for values in deo_to_leg.values() for value in values]
        safe=re.sub(r'[^a-z0-9]+','-',deo.lower()).strip('-')
        questions.append({'id':f'medium-deo-leg-forward-{safe}',
            'question':f'Which legislative district is listed under {deo}?',
            'choices':options(answer,other_districts,202730+index),'answer':answer,
            'explanation':f'The supplied DPWH district allocation crosswalk lists {answer} under {deo}. The scan does not state a fiscal year and does not establish project ownership.',
            'hint':'Check the DEO row in the linked allocation crosswalk.',
            'sources':[source],'difficulty':'medium','topic':'deo','questionType':'deo-leg-crosswalk',
            'generatedFromDeoLegCrosswalk':True,'crosswalkDirection':'deo-to-district'})
    for index,(district,deos) in enumerate(sorted(leg_to_deo.items())):
        labels=sorted(deos)
        answer=' and '.join(labels)
        other_answers=[' and '.join(sorted(values)) for values in leg_to_deo.values()]
        questions.append({'id':f'medium-deo-leg-reverse-{re.sub(r"[^a-z0-9]+","-",district.lower()).strip("-")}',
            'question':f'Which DEO or DEOs are listed for {district_label(district)}?',
            'choices':options(answer,other_answers,202740+index),'answer':answer,
            'explanation':f'The supplied DPWH district allocation crosswalk lists {answer} for {district_label(district)}. The scan does not state a fiscal year and does not establish project ownership.',
            'hint':'Check the legislative district in the linked allocation crosswalk.',
            'sources':[source],'difficulty':'medium','topic':'deo','questionType':'deo-leg-crosswalk',
            'generatedFromDeoLegCrosswalk':True,'crosswalkDirection':'district-to-deo'})
    return questions

def assign_question_pools(questions):
    """Attach a stable draw pool to every question; each pool is used once per game."""
    hard_project_pools={
        'nir-wood-door-equivalent':'pow-nir-regional-office',
        'nir-glass-door-area':'pow-nir-regional-office',
        'dmw-largest-category':'pow-dmw-building',
        'dmw-concrete-total':'pow-dmw-building',
        'dmw-storeys':'pow-building-height',
        'dmw-finishing-share':'pow-dmw-building',
        'prc-largest-category':'pow-prc-building',
        'prc-mechanical-share':'pow-prc-building',
        'prc-finishing-total':'pow-prc-building',
        'prc-concrete-share':'pow-prc-building',
        'coa-largest-share':'pow-coa-building',
        'coa-mechanical-total':'pow-coa-building',
        'coa-finishing-share':'pow-coa-building',
        'rcs-davao-six-schools':'pow-rcs-davao-city-project-00294',
        'rcs-davao-third-fourteen':'pow-rcs-davao-city-project-00296',
        'rcs-davao-del-sur-tanks':'pow-rcs-davao-del-sur-tanks',
        'rcs-package-allocation':'pow-rcs-package-allocation',
        'hgab-3rd-highest-bridge-stated-meter-allocation':'bridge-cost-per-meter',
    }
    for q in questions:
        qid=q.get('id','')
        topic=q.get('topic')
        kind=q.get('questionType')
        if topic=='flags' or kind=='deo-flag-count' or qid.startswith('flag-'):
            pool='flags'
        elif q.get('generatedFromLegRepresentative') or kind=='leg-representative':
            pool='leg-potential-additions-representative'
        elif kind=='allocation-lookup':
            pool='department-service-allocation'
        elif kind=='deo-pow-engineer' or qid.startswith('medium-deo-district-engineer-'):
            pool='district-engineer'
        elif kind=='party-list-representative' or topic=='party-list':
            pool='party-list-representative'
        elif kind=='deo-leg-crosswalk':
            pool='deo-leg-crosswalk'
        elif kind=='deo-line-item':
            pool='pow-line-item'
        elif topic=='coverage':
            pool='documentation-coverage'
        elif topic=='summary-leads' or kind=='summary-lead':
            pool='summary-leads'
        elif topic=='budget-comparison':
            pool='budget-comparison'
        elif topic=='cost-per-meter' or kind=='derivedBridgeRate':
            pool='bridge-cost-per-meter'
        elif qid in hard_project_pools:
            pool=hard_project_pools[qid]
        elif q.get('generatedFromParsedPow'):
            code=re.sub(r'[^a-z0-9]+','-',str(q.get('projectCode','')).lower()).strip('-')
            pool='pow-project-'+(code or re.sub(r'[^a-z0-9]+','-',qid.lower()).strip('-'))
        elif q.get('difficulty')=='medium' and topic=='deo':
            pool='district-engineer'
        elif topic=='budget' or qid.startswith('fy2027-'):
            pool='budget-basics'
        else:
            pool='question-'+re.sub(r'[^a-z0-9]+','-',qid.lower()).strip('-')
        q['pool']=pool

def main():
    bank=json.loads(BANK.read_text())
    curated=[q for q in bank.get('questions',[]) if not q.get('generatedFromParsedPow') and not q.get('generatedFromPowEngineer') and not q.get('generatedFromAllocationLookup') and not q.get('generatedFromLegRepresentative') and not q.get('generatedFromDeoLegCrosswalk') and not q.get('id','').startswith('medium-deo-district-engineer-') and not (q.get('topic')=='representatives' and q.get('questionType')=='leg-representative') and not (q.get('topic')=='budget' and q.get('questionType')=='allocation-lookup') and not (q.get('topic')=='deo' and q.get('questionType')=='deo-leg-crosswalk')]
    source=json.loads(SOURCE.read_text())
    generated=generated_questions(collect_candidates(source))
    engineer_questions=pow_district_engineer_questions(source)
    leg_questions=leg_representative_questions()
    allocation_questions=department_service_allocation_questions()
    crosswalk_questions=deo_leg_crosswalk_questions()
    bank['questions']=curated+leg_questions+allocation_questions+crosswalk_questions+generated+engineer_questions
    assign_question_pools(bank['questions'])
    bank['generatedFrom']={'dataset':'analysis_output/dpwh-in-depth-data.json','selection':'native DPWH itemized bill rows whose printed unit cost arithmetic is within rounding tolerance; one eligible row per project; source page links retained','generatedQuestionCount':len(generated),'districtEngineerQuestionSelection':'POW documents only; explicit district_engineer role; native PDF text extraction; one question per distinct DEO/name pair; cited source page retained','districtEngineerQuestionCount':len(engineer_questions),'legRepresentativeQuestionSelection':'One randomly selected direct representative question from districts listed in Potential additions per legislative district (LEG); the pool is asked at most once per game','legRepresentativeQuestionCount':len(leg_questions),'departmentServiceAllocationQuestionSelection':'DBM proposed FY2027 department and service allocations; exactly one question from this pool is guaranteed in the medium round','departmentServiceAllocationQuestionCount':len(allocation_questions)}
    BANK.write_text(json.dumps(bank,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'curatedQuestions':len(curated),'generatedQuestions':len(generated),'districtEngineerQuestions':len(engineer_questions),'deoLegCrosswalkQuestions':len(crosswalk_questions),'totalQuestions':len(bank['questions']),'eligibleProjects':len(collect_candidates(source))},indent=2))

if __name__=='__main__':main()
