#!/usr/bin/env python3
"""Build an HGAB 3rd-reading-only, source-linked FY2027 trivia bank."""
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BANK = ROOT.parent / 'open-data-visualization/static/nep-preview/budget-trivia-2027.json'
IN_DEPTH = ROOT / 'analysis_output/dpwh-in-depth-data.json'
QUEUE = ROOT / 'analysis_output/line_item_review_queue.json'
COSTS = ROOT / 'analysis_output/cost_per_km.json'
MPB = ROOT / 'analysis_output/mpb_analysis.json'
RCS = ROOT / 'analysis_output/rcs_stage_trace.json'
LOCATION = ROOT / 'analysis_output/congress_arcgis_bridge_audit.json'
LEADERBOARD = ROOT / 'project_documents/hgab_2027_leaderboard_data.json'
FMR_COORDINATES = ROOT / 'data_sources/fmr_analyst/hgab_fmr_coordinates_normalized.json'
FMR_COORDINATE_AUDIT = ROOT / 'data_sources/fmr_analyst/hgab_fmr_coordinate_normalization_audit.json'
MPB_COORDINATE_AUDIT = ROOT / 'analysis_output/mpb_coordinate_audit.json'
SUMMARY_HERO = {
    'leads': 12,
    'uniformRcsOffices': 199,
    'repeatCandidateProposals': 1379,
}
TARGET_PROJECT_QUESTIONS = 1000
HGAB3_PROJECTS = ROOT / 'hb10858_3rd_dpwh_projects.json'
STAGE = 'HGAB 3rd reading'
SNAPSHOT_DATE = '2026-10-18'

KEEP_IDS = {
    'hgab3-project-row-count', 'hgab3-unmatched-count', 'hgab3-inspected-missing-docs',
    'hgab3-most-missing-type', 'hgab3-documents-listed-count', 'hgab3-linked-rows',
    'hgab3-linked-share', 'hgab3-missing-photos', 'hgab3-missing-pow',
    'hgab3-missing-docs-share',
    'hgab-3rd-highest-bridge-stated-meter-allocation',
    'medium-burol-rate-math',
    'easy-summary-rcs-same-package', 'summary-hero-lead-count',
    'summary-hero-uniform-rcs-offices', 'summary-hero-repeat-candidate-count',
    'medium-deo-villa-socorro-rate', 'hgab3-mpb-amount',
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def number(value, places=0):
    value = round(float(value), places)
    if abs(value - round(value)) < 1e-9:
        return f'{int(round(value)):,}'
    return f'{value:,.{places}f}'.rstrip('0').rstrip('.')


def choices_for(value, currency=False, places=0, unit=''):
    answer = round(float(value), places)
    factors = [0.6, 1.4, 2.0, 2.7, 3.3, 4.0]
    distractors = []
    for factor in factors:
        candidate = round(answer * factor, places)
        if candidate != answer and candidate not in distractors:
            distractors.append(candidate)
        if len(distractors) == 3:
            break
    def label(n):
        rendered = ('₱' if currency else '') + number(n, places)
        return rendered if currency or not unit else rendered + ' ' + unit
    return [label(answer), *(label(n) for n in distractors)], label(answer)


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-')[:80]


def set_answer(question, answer, distractors=None):
    """Keep four distinct choices while replacing an outdated correct value."""
    old = question.get('choices', [])
    if answer in old:
        wrong = [x for x in old if x != answer]
    else:
        wrong = [x for x in old if x != question.get('answer')]
    if distractors:
        wrong = list(distractors) + wrong
    choices = [answer]
    for value in wrong:
        if value not in choices:
            choices.append(value)
        if len(choices) == 4:
            break
    if len(choices) < 4:
        for value in ('Review the source page', 'Not established by this screen', 'Use the HGAB 3rd figure'):
            if value not in choices:
                choices.append(value)
            if len(choices) == 4:
                break
    random.Random(question['id']).shuffle(choices)
    question['answer'] = answer
    question['choices'] = choices


def current_curated(bank):
    questions = [q for q in bank.get('questions', []) if q.get('id') in KEEP_IDS]
    found = {q.get('id') for q in questions}
    missing = KEEP_IDS - found
    if missing:
        raise ValueError('Expected existing HGAB questions were not found: ' + ', '.join(sorted(missing)))
    return questions


def update_curated(questions, coverage, review, cost, rcs, mpb, location):
    by_id = {q['id']: q for q in questions}
    project_rows = coverage['projectRows']
    linked_rows = coverage['linkedRows']
    missing_any = coverage['missingAnyTypeRows']
    listed_any = coverage['listedAnyRows']
    missing = coverage['missingTypes']

    q = by_id['hgab3-project-row-count']
    q['question'] = 'In the October 18, 2026 Transparency snapshot, how many HGAB 3rd project rows were checked for document coverage?'
    set_answer(q, number(project_rows))
    q['explanation'] = f'The HGAB 3rd document-coverage snapshot checked {number(project_rows)} project rows. Its linked-document counts use the DPWH Transparency metadata snapshot retrieved {SNAPSHOT_DATE}; it does not count every HGAB schedule allocation record.'

    q = by_id['hgab3-unmatched-count']
    q['question'] = 'How many HGAB 3rd project rows had no selected NEP counterpart in the current one-to-one screen?'
    set_answer(q, number(coverage['noSelectedNepRows']))
    q['explanation'] = 'These are HGAB 3rd rows without a selected one-to-one NEP counterpart. A missing match is a review lead, not proof the project was newly added.'

    q = by_id['hgab3-inspected-missing-docs']
    q['question'] = f'Among {number(coverage["inspectedRows"])} inspected HGAB 3rd rows with listed documents, how many lacked at least one of the three tracked types?'
    set_answer(q, number(missing_any))
    q['explanation'] = f'{number(missing_any)} inspected rows lacked a POW, geotagged photos, or an RDC endorsement in the {SNAPSHOT_DATE} listing. Uninspected and unlisted source records are not treated as checked.'

    q = by_id['hgab3-most-missing-type']
    set_answer(q, 'RDC endorsement')
    q['question'] = f'Which tracked document type was most often absent among the {number(coverage["inspectedRows"])} inspected HGAB 3rd rows?'
    q['explanation'] = f'RDC endorsements were absent for {number(missing["rdc"]["count"])} inspected rows in the {SNAPSHOT_DATE} metadata snapshot. This does not prove that a document is unavailable elsewhere.'

    q = by_id['hgab3-documents-listed-count']
    q['question'] = 'How many HGAB 3rd rows had at least one matched DPWH Transparency document listed in the snapshot?'
    set_answer(q, number(listed_any))
    q['explanation'] = f'{number(listed_any)} rows had a matched source entry with one or more listed documents in the {SNAPSHOT_DATE} snapshot.'

    q = by_id['hgab3-linked-rows']
    q['question'] = 'How many HGAB 3rd rows had a selected DPWH Transparency NEP counterpart in the snapshot?'
    set_answer(q, number(linked_rows))
    q['explanation'] = f'{number(linked_rows)} of {number(project_rows)} coverage rows were linked to the retained NEP/Transparency project list. This is a record match count, not a measure of project completion.'

    q = by_id['hgab3-linked-share']
    set_answer(q, f'{coverage["linkedPct"]:.1f}%')
    q['question'] = 'What share of the HGAB 3rd document-coverage rows had a selected Transparency NEP counterpart?'
    q['explanation'] = f'{number(linked_rows)} of {number(project_rows)} rows were linked ({coverage["linkedPct"]:.1f}%) in the {SNAPSHOT_DATE} snapshot.'

    for qid, key, label in [('hgab3-missing-photos', 'photos', 'geotagged photos'), ('hgab3-missing-pow', 'pow', 'POW attachment')]:
        q = by_id[qid]
        set_answer(q, number(missing[key]['count']))
        q['question'] = f'Among the {number(coverage["inspectedRows"])} inspected HGAB 3rd rows, how many had no {label} listed in the Transparency record?'
        q['explanation'] = f'{number(missing[key]["count"])} inspected rows had no {label} listed in the {SNAPSHOT_DATE} Transparency metadata snapshot. This describes the listing, not whether a source document exists elsewhere.'

    q = by_id['hgab3-missing-docs-share']
    set_answer(q, f'{coverage["missingAnyTypePct"]:.1f}%')
    q['question'] = f'What share of inspected HGAB 3rd rows with listed documents lacked at least one tracked document type?'
    q['explanation'] = f'{number(missing_any)} of {number(coverage["inspectedRows"])} inspected rows ({coverage["missingAnyTypePct"]:.1f}%) lacked a POW, geotagged photos, or an RDC endorsement in the {SNAPSHOT_DATE} snapshot.'

    q = by_id['easy-summary-rcs-same-package']
    q['difficulty'] = 'basic'
    q['topic'] = 'budget'
    q['questionType'] = 'hgab3-allocation'
    q['question'] = 'What allocation did each of the 199 district-office Rainwater Collector System lines retain in the HGAB 3rd schedule?'
    set_answer(q, '₱4.2 million')
    q['explanation'] = 'The stage trace found 199 district-office Rainwater Collector System lines, all retained at ₱4.2 million in the HGAB 3rd schedule. The office title does not locate the funded installation or establish who benefits.'
    q['sources'] = [{'label': 'RCS · HGAB 3rd stage trace · PDF page references in source data', 'url': 'rcs.html'}]

    q = by_id['summary-hero-lead-count']
    q['question'] = 'How many investigative leads does the summary hero highlight?'
    q['topic'] = 'summary-leads'
    q['difficulty'] = 'medium'
    q['questionType'] = 'summary-hero-number'
    q['generatedFromSummaryHero'] = True
    set_answer(q, f"{number(SUMMARY_HERO['leads'])} leads")
    q['choices'] = [f'{number(n)} leads' for n in (4, SUMMARY_HERO['leads'], 24, 60)]
    q['explanation'] = 'The summary hero highlights 12 investigative leads. They are review leads, not findings of wrongdoing.'
    q['sources'] = [{'label': 'Budget Summary · investigative leads · hero', 'url': 'summary.html#ranked-leads'}]

    q = by_id['summary-hero-uniform-rcs-offices']
    q['question'] = 'How many offices are covered by the uniform RCS packages highlighted in the summary hero?'
    q['topic'] = 'summary-leads'
    q['difficulty'] = 'medium'
    q['questionType'] = 'summary-hero-number'
    q['generatedFromSummaryHero'] = True
    set_answer(q, f"{number(SUMMARY_HERO['uniformRcsOffices'])} offices")
    q['choices'] = [f'{number(n)} offices' for n in (100, SUMMARY_HERO['uniformRcsOffices'], 500, 1990)]
    q['explanation'] = 'The summary hero reports uniform Rainwater Collector System packages for 199 offices.'
    q['sources'] = [{'label': 'Budget Summary · investigative leads · hero', 'url': 'summary.html#ranked-leads'}]

    q = by_id['summary-hero-repeat-candidate-count']
    q['question'] = 'How many repeat-candidate proposals appear in the summary hero?'
    q['topic'] = 'summary-leads'
    q['difficulty'] = 'medium'
    q['questionType'] = 'summary-hero-number'
    q['generatedFromSummaryHero'] = True
    set_answer(q, f"{number(SUMMARY_HERO['repeatCandidateProposals'])} proposals")
    q['choices'] = [f'{number(n)} proposals' for n in (137, SUMMARY_HERO['repeatCandidateProposals'], 5137, 13790)]
    q['explanation'] = 'The hero highlights 1,379 repeat candidates for review; a repeated title does not establish duplicate work.'
    q['sources'] = [{'label': 'Budget Summary · investigative leads · hero', 'url': 'summary.html#ranked-leads'}]

    q = by_id['hgab-3rd-highest-bridge-stated-meter-allocation']
    q['finalChallenge'] = True
    q['question'] = 'In the HGAB 3rd bridge table, which project has the highest allocation per stated meter?'
    q['explanation'] = 'Burol Overpass is listed at ₱150 million over 25 stated meters, or ₱6 million per stated meter. The ratio does not establish funded construction length or overpricing.'

    q = by_id['hgab3-mpb-amount']
    q['difficulty'] = 'medium'
    mpb_answer = '₱' + number(mpb['summary']['hgabPesos'])
    set_answer(q, mpb_answer)
    q['explanation'] = f"The current MPB analysis totals ₱{number(mpb['summary']['hgabPesos'])} across HGAB 3rd-reading lines; this is an allocation total, not a reported expenditure total."

    # Attach the current source vintage to all retained questions. These
    # coverage questions intentionally refer to the dated Transparency snapshot.
    for question in questions:
        question['stage'] = STAGE
        if question.get('topic') == 'coverage' and question.get('sources'):
            question['sources'] = [{'label': f'DPWH · HGAB 3rd document coverage · snapshot {SNAPSHOT_DATE}',
                                    'url': 'dpwh.html'}]
            question['snapshotRetrievedAt'] = SNAPSHOT_DATE


def generated_allocation_questions(hgab_source):
    """Sample 1,000 project-line allocation questions from the HGAB 3rd file alone."""
    rows = hgab_source['data']['data']
    eligible = [row for row in rows
                if row.get('allocationKind') in {'project', 'foreign-assisted project'}
                and row.get('projectName') and row.get('amountPesos', 0) > 0
                and row.get('sourcePage')]
    # Skip exact duplicate source occurrences, while retaining repeated projects
    # with different offices, pages, or printed allocations.
    unique = {}
    for row in eligible:
        key = (row.get('office'), row['projectName'], row['sourcePage'], int(row['amountPesos']))
        unique.setdefault(key, row)
    eligible = list(unique.values())
    strata = {
        'easy': [r for r in eligible if r['amountPesos'] <= 10_000_000],
        'medium': [r for r in eligible if 10_000_000 < r['amountPesos'] <= 100_000_000],
        'hard': [r for r in eligible if r['amountPesos'] > 100_000_000],
    }
    target_counts = {'easy': 300, 'medium': 400, 'hard': 300}
    selected = []

    def proportional_quotas(group_sizes, target):
        total = sum(group_sizes.values())
        raw = {key: target * count / total for key, count in group_sizes.items()}
        quotas = {key: min(group_sizes[key], int(raw[key])) for key in group_sizes}
        remainder = target - sum(quotas.values())
        for key in sorted(group_sizes, key=lambda k: (-(raw[k] - int(raw[k])), k)):
            take = min(remainder, group_sizes[key] - quotas[key])
            quotas[key] += take
            remainder -= take
            if remainder == 0:
                break
        if remainder:
            raise ValueError('Not enough allocation rows in a difficulty band')
        return quotas

    for difficulty, target in target_counts.items():
        by_program = {}
        for row in strata[difficulty]:
            by_program.setdefault(row.get('pap1') or 'Program not listed', []).append(row)
        quotas = proportional_quotas({k: len(v) for k, v in by_program.items()}, target)
        for program, candidates in by_program.items():
            candidates = sorted(candidates, key=lambda r: r['id'])
            random.Random(f'hgab3-project-allocations-{difficulty}-{program}').shuffle(candidates)
            selected.extend((difficulty, row) for row in candidates[:quotas[program]])

    if len(selected) != TARGET_PROJECT_QUESTIONS:
        raise RuntimeError(f'Expected {TARGET_PROJECT_QUESTIONS} HGAB allocation rows; selected {len(selected)}')

    text_rows = [row for difficulty, row in selected if difficulty == 'easy']
    numeric_rows = [row for difficulty, row in selected if difficulty != 'easy']
    if len(text_rows) != 300 or len(numeric_rows) != 700:
        raise RuntimeError(f'Unexpected allocation question answer-type split: {len(text_rows)} text, {len(numeric_rows)} numeric')
    random.Random('hgab3-allocation-numeric-difficulty').shuffle(numeric_rows)

    def amount_choices(value, narrow):
        factors = (0.97, 1.03, 1.06) if narrow else (0.55, 1.45, 2.1)
        values = [int(value)]
        for factor in factors:
            candidate = round(int(value) * factor)
            if candidate not in values:
                values.append(candidate)
        if len(values) != 4:
            raise ValueError(f'Could not create four distinct amount choices for {value}')
        labels = [('₱' + number(v)) for v in values]
        random.Random(f'hgab3-amount-choice-{value}-{narrow}').shuffle(labels)
        return labels

    def choice_spread(choices):
        values = [float(x.replace('₱', '').replace(',', '')) for x in choices]
        return (max(values) - min(values)) / max(1.0, sum(values) / len(values))

    # Project-title recall is at least medium. Numeric allocation questions are
    # classified from answer-choice dispersion: especially round allocations
    # are easy, wider irregular-value choices are medium, and close choices are hard.
    output = []
    staged = [('text', row) for row in text_rows]
    for index, row in enumerate(numeric_rows):
        narrow = (index % 2) == 1
        choices = amount_choices(row['amountPesos'], narrow)
        spread = choice_spread(choices)
        difficulty = ('hard' if spread < 0.2 else
                      'easy' if int(row['amountPesos']) % 10_000_000 == 0 else
                      'medium')
        staged.append((difficulty, row, choices))

    for item in staged:
        answer_type, row = item[0], item[1]
        amount = int(row['amountPesos'])
        office = row.get('office')
        subject = row['projectName'] + (f' ({office})' if office else '')
        hid = row['id']
        page = row['sourcePage']
        pap = row.get('pap3') or row.get('pap2') or row.get('pap1') or 'HGAB allocation'
        if answer_type == 'text':
            allocation_answer_type = 'text'
            answer = row['projectName']
            prompt = f"Which project title has a listed allocation of ₱{number(amount)} under {office or 'the listed office'} on HGAB 3rd PDF page {page}?"
            other_titles = []
            same_program = [r for r in eligible if (r.get('pap3') or r.get('pap2') or r.get('pap1')) == pap]
            for candidate in same_program + eligible:
                title = candidate.get('projectName')
                if title and title != answer and title not in other_titles:
                    other_titles.append(title)
                if len(other_titles) == 3:
                    break
            choices = [answer] + other_titles
            random.Random('hgab3-project-title-' + hid).shuffle(choices)
            difficulty = 'medium'
            explanation = f'The HGAB 3rd schedule lists “{answer}” under {office or "the listed office"} on PDF page {page}, with an allocation of ₱{number(amount)}. This is an appropriation in the House bill, not a verified payment.'
        else:
            allocation_answer_type = 'numeric'
            difficulty, choices = item[0], item[2]
            answer = '₱' + number(amount)
            prompt = f'In the HGAB 3rd-reading schedule, what allocation is listed for {subject} on PDF page {page}?'
            spread = choice_spread(choices)
            explanation = f'The HGAB 3rd-reading schedule lists {answer} for this {pap} line on PDF page {page}. This is an appropriation, not a verified payment.'
        output.append({
            'id': 'hgab3-allocation-' + slug(hid),
            'question': prompt,
            'choices': choices,
            'answer': answer,
            'explanation': explanation,
            'hint': f'Check the project amount printed on HGAB 3rd-reading PDF page {page}.',
            'sources': [{'label': f"HB 10858 · HGAB 3rd · PDF p. {page} · {hid}", 'url': 'dpwh-hgab.html'}],
            'difficulty': difficulty,
            'category': 'HGAB 3rd allocations',
            'topic': 'budget',
            'questionType': 'hgab3-allocation',
            'stage': STAGE,
            'hgabId': hid,
            'allocationProgram': pap,
            'generatedFromHgabAllocation': True,
            'allocationAnswerType': allocation_answer_type,
        })
    counts = {d: sum(q['difficulty'] == d for q in output) for d in ('easy', 'medium', 'hard')}
    if sum(counts.values()) != TARGET_PROJECT_QUESTIONS:
        raise RuntimeError(f'Allocation difficulty counts do not match answer type and choice spread: {counts}')
    return output


def leaderboard_questions(source):
    """Create 100 questions from the FY2027 public leaderboard snapshot."""
    entries=source['entries']; totals=source['totals']; built_at=source['built_at']
    root='https://budget.bettergov.ph/hgab/2027/leaderboard'
    boards={
        'house':'house-bill-largest','added':'added-budget','added_count':'added-count',
        'increase':'increase','increase_pct':'increase-pct','cuts':'cuts','dropped':'dropped',
        'added_share':'added-share','history':'enacted-total','year':'enacted-2026',
        'members':'bills','index':'',
    }
    categories={'2027 House bill':'leaderboard-house-bill',
                'Enacted budget history':'leaderboard-history',
                'House members':'leaderboard-members'}
    questions=[]
    def office(e):
        names=[o.get('name') for o in e.get('offices',[]) if o.get('name')]
        return ' / '.join(names) or e.get('key','Unlisted office')
    def rank(field, reverse=True, keep=None):
        rows=[e for e in entries if isinstance(e.get(field),(int,float)) and (keep is None or keep(e))]
        return sorted(rows,key=lambda e:((-e[field] if reverse else e[field]),office(e).casefold()))
    def display_person(p):
        n=str(p.get('name') or 'Unlisted representative')
        if ', ' in n:
            last,first=n.split(', ',1); return f'{first} {last}'
        return n
    def ordinal(n):
        suffix='th' if 10 <= n % 100 <= 20 else {1:'st',2:'nd',3:'rd'}.get(n % 10,'th')
        return f'{n}{suffix}'
    people_by_id={}
    for e in entries:
        for p in e.get('people',[]):
            if p.get('district_id') and isinstance(p.get('bill_count'),int): people_by_id[p['district_id']]=p
    people=sorted(people_by_id.values(),key=lambda p:(-p['bill_count'],display_person(p).casefold()))
    def fmt(v,kind):
        return '₱'+number(v) if kind=='money' else f'{float(v):.1f}%' if kind=='pct' else number(v)
    def numeric_wrong(v,kind,candidates):
        wrong=[]; target=fmt(v,kind)
        for x in candidates:
            if not isinstance(x,(int,float)): continue
            label=fmt(x,kind)
            if label!=target and label not in wrong: wrong.append(label)
            if len(wrong)==3:return wrong
        for factor in (.7,1.3,1.8,2.2,.45):
            x=v*factor
            if kind=='money':x=round(x/1_000_000)*1_000_000
            elif kind=='count':x=round(x)
            label=fmt(x,kind)
            if label!=target and label not in wrong:wrong.append(label)
            if len(wrong)==3:return wrong
        raise ValueError(f'Could not produce choices for {v}')
    def add(cat,diff,prompt,answer,wrong,board,explanation):
        n=sum(q['category']==cat for q in questions)+1
        qid=f'leaderboard-{slug(cat)}-{n:03d}'
        choices=[str(answer)]
        for w in wrong:
            if str(w) not in choices:choices.append(str(w))
            if len(choices)==4:break
        if len(choices)!=4:raise ValueError(f'Not enough unique choices for {qid}')
        random.Random(qid).shuffle(choices)
        url=root+('/'+boards[board] if boards[board] else '')
        questions.append({
            'id':qid,'question':prompt,'choices':choices,'answer':str(answer),
            'explanation':explanation,
            'hint':'Open the cited leaderboard and check its title and ranking measure.',
            'sources':[{'label':'BetterGov · HGAB 2027 leaderboard · '+board.replace('_',' '),'url':url}],
            'difficulty':diff,'category':cat,'topic':categories[cat],
            'questionType':'hgab3-leaderboard-fact','stage':STAGE,
            'generatedFromLeaderboard':True,'leaderboardBuiltAt':built_at,
        })
    def named(cat,diff,prompt,row,rows,board,explanation):
        answer=office(row); wrong=[office(x) for x in rows if office(x)!=answer]
        add(cat,diff,prompt,answer,wrong,board,explanation)
    def value(cat,diff,prompt,v,kind,candidates,board,explanation):
        add(cat,diff,prompt,fmt(v,kind),numeric_wrong(v,kind,candidates),board,explanation)
    def person_q(cat,diff,prompt,p,rows,board,explanation):
        answer=display_person(p); wrong=[display_person(x) for x in rows if display_person(x)!=answer]
        add(cat,diff,prompt,answer,wrong,board,explanation)
    def person_value(cat,diff,prompt,v,candidates,board,explanation):
        value(cat,diff,prompt,v,'count',candidates,board,explanation)

    house=rank('hgab3_php'); nep=rank('nep_php')
    added=rank('added_php',keep=lambda e:e.get('added_rows',0)>0)
    added_count=rank('added_rows',keep=lambda e:e.get('added_rows',0)>0)
    increases=rank('delta_php',keep=lambda e:e.get('delta_php',0)>0)
    pct_increases=rank('delta_pct',keep=lambda e:e.get('nep_php',0)>=500_000_000 and e.get('delta_pct',0)>0)
    cuts=rank('delta_php',reverse=False,keep=lambda e:e.get('delta_php',0)<0)
    dropped=rank('dropped_php',keep=lambda e:e.get('dropped_rows',0)>0)
    shares=sorted([e for e in entries if e.get('hgab3_php',0)>=1_000_000_000 and e.get('added_rows',0)>0],
                  key=lambda e:(-e['added_php']/e['hgab3_php'],office(e).casefold()))
    all_totals=totals['all']; kinds=totals['by_office_kind']; units=totals['units']
    cat='2027 House bill'; easy='easy'; med='medium'; hard='hard'
    named(cat,easy,'Which district office ranks first by total DPWH amount in the 2027 House bill?',house[0],house,'house','The board ranks DPWH office totals in HB 10858, third reading. Amounts belong to offices, not representatives.')
    value(cat,easy,f"What House bill total is listed for {office(house[0])}?",house[0]['hgab3_php'],'money',[x['hgab3_php'] for x in house[1:]],'house','This is the House bill total shown for the office, not a payment total.')
    value(cat,easy,f"How many House bill lines are listed for {office(house[0])}?",house[0]['hgab3_rows'],'count',[x.get('hgab3_rows') for x in house[1:]],'house','The leaderboard reports this number of House bill lines for the office.')
    named(cat,easy,'Which office ranks first by value of House bill projects with no matching NEP line?',added[0],added,'added','“Added” means no matching NEP line was found. These are candidates, not confirmed insertions.')
    value(cat,easy,f"What unmatched-to-NEP project value is listed for {office(added[0])}?",added[0]['added_php'],'money',[x['added_php'] for x in added[1:]],'added','This is the office value in the unmatched-to-NEP candidate board.')
    named(cat,easy,'Which office ranks first by count of House bill projects without a NEP match?',added_count[0],added_count,'added_count','The board counts House bill project lines without a selected NEP match.')
    value(cat,easy,f"How many unmatched-to-NEP project lines are listed for {office(added_count[0])}?",added_count[0]['added_rows'],'count',[x['added_rows'] for x in added_count[1:]],'added_count','This is the line count displayed on the project-count board.')
    named(cat,easy,'Which office has the largest positive change from its NEP total to its House bill total?',increases[0],increases,'increase','The increase board compares each office’s House bill total with its NEP total.')
    named(cat,easy,'Which office has the largest reduction from its NEP total to its House bill total?',cuts[0],cuts,'cuts','The cuts board ranks offices whose House bill total is below their NEP total.')
    value(cat,easy,'How many DPWH district offices are included in this leaderboard snapshot?',units,'count',[totals['units_tier_a'],totals['units_tier_b'],totals['districts']],'index','The snapshot separately counts DPWH district offices and legislative districts.')

    named(cat,med,'Which office ranks second by total in the House bill?',house[1],house,'house','This is the runner-up on the House bill total board.')
    named(cat,med,'Which office ranks third by total in the House bill?',house[2],house,'house','This is the third office on the House bill total board.')
    value(cat,med,f"What is {office(house[1])}'s House bill total?",house[1]['hgab3_php'],'money',[x['hgab3_php'] for x in house[2:]],'house','This is the second-ranked office total.')
    named(cat,med,'Which office ranks second by value of projects with no NEP match?',added[1],added,'added','Unmatched lines are candidates for review, not confirmed additions.')
    value(cat,med,f"What unmatched-to-NEP project value is listed for {office(added[1])}?",added[1]['added_php'],'money',[x['added_php'] for x in added[2:]],'added','This is the second-ranked value on the added-project board.')
    named(cat,med,'Which office has the second-largest count of projects without a NEP match?',added_count[1],added_count,'added_count','The board ranks the count of candidate project lines.')
    named(cat,med,'Which office ranks first by percentage increase from NEP to House bill, among those with at least ₱500 million in the NEP?',pct_increases[0],pct_increases,'increase_pct','The percentage board limits the ranking to offices with at least ₱500 million in the NEP.')
    named(cat,med,'Which office ranks second by value of NEP projects not listed in the House bill?',dropped[1],dropped,'dropped','No matching House bill line was found for these NEP entries; the screen does not confirm deletion.')
    named(cat,med,'Which office has the largest share of its House bill total in projects with no NEP match?',shares[0],shares,'added_share','The share board includes offices with at least ₱1 billion in the House bill.')
    value(cat,med,'How many offices are Tier A and serve one district?',totals['units_tier_a'],'count',[units,totals['units_tier_b'],totals['districts']],'index','Tier A offices serve one district.')
    value(cat,med,'How many offices are Tier B and serve more than one district?',totals['units_tier_b'],'count',[units,totals['units_tier_a'],totals['districts']],'index','Tier B amounts are shown whole, not split among districts.')
    net=all_totals['hgab3_php']-all_totals['nep_php']
    value(cat,med,'By how much does the full DPWH House bill total exceed the NEP total?',net,'money',[all_totals['added_php'],all_totals['dropped_php'],all_totals['hgab3_php']],'house','Subtract the NEP total from the House bill total in the snapshot.')
    value(cat,med,'How many project lines are in the full no-NEP-match group?',all_totals['added_rows'],'count',[all_totals['dropped_rows'],all_totals['held_rows'],units],'added_count','The no-match group is a candidate list, not a confirmed insertion count.')
    value(cat,med,'How many lines are held because the NEP counterpart is unconfirmed?',all_totals['held_rows'],'count',[all_totals['added_rows'],all_totals['dropped_rows'],totals['units_tier_b']],'added','Held lines are not counted as confident matches.')
    value(cat,med,'What is the Central Office House bill total in the office-type breakdown?',kinds['central']['hgab3_php'],'money',[kinds['deo']['hgab3_php'],all_totals['hgab3_php'],kinds['central']['nep_php']],'house','The office-type breakdown keeps Central Office and district engineering offices separate.')

    top_gap=house[0]['hgab3_php']-house[1]['hgab3_php']
    value(cat,hard,'How much larger is the top office House bill total than the second-ranked office?',top_gap,'money',[x['hgab3_php'] for x in house[2:]],'house','Subtract the second-ranked office total from the first-ranked total.')
    value(cat,hard,'What is the combined House bill total for the three top-ranked offices?',sum(x['hgab3_php'] for x in house[:3]),'money',[sum(x['hgab3_php'] for x in house[1:4]),sum(x['hgab3_php'] for x in house[2:5]),all_totals['hgab3_php']],'house','Add the first three office totals on the leaderboard.')
    value(cat,hard,'What is the net increase from the full DPWH NEP total to the full House bill total?',net,'money',[all_totals['added_php']-all_totals['dropped_php'],all_totals['added_php'],all_totals['dropped_php']],'house','Subtract the full NEP total from the full House bill total.')
    value(cat,hard,'What share of the House bill total is represented by unmatched-to-NEP project value?',100*all_totals['added_php']/all_totals['hgab3_php'],'pct',[100*all_totals['dropped_php']/all_totals['hgab3_php'],100*all_totals['held_php']/all_totals['hgab3_php'],15.0],'added_share','Divide the value in the no-NEP-match group by the full House bill total.')
    top=house[0]
    value(cat,hard,f"What is the average House bill amount per listed line for {office(top)}, rounded to the nearest peso?",round(top['hgab3_php']/top['hgab3_rows']),'money',[round(x['hgab3_php']/x['hgab3_rows']) for x in house[1:]],'house','Divide the office total by its number of listed House bill lines. This is not a unit rate.')
    value(cat,hard,'How much larger is the top unmatched-project amount than the runner-up amount?',added[0]['added_php']-added[1]['added_php'],'money',[x['added_php'] for x in added[2:]],'added','Subtract the second-ranked amount from the top amount.')
    value(cat,hard,'How many more unmatched-to-NEP project lines does the top office have than the runner-up?',added_count[0]['added_rows']-added_count[1]['added_rows'],'count',[x['added_rows'] for x in added_count[2:]],'added_count','Subtract the runner-up count from the top count.')
    value(cat,hard,'What is the combined unmatched-to-NEP value for the three highest-ranked offices?',sum(x['added_php'] for x in added[:3]),'money',[sum(x['added_php'] for x in added[1:4]),sum(x['added_php'] for x in added[2:5]),all_totals['added_php']],'added','Add the first three office amounts on the added-budget board.')
    central=kinds['central']['hgab3_php']; deo=kinds['deo']['hgab3_php']
    value(cat,hard,'How much does the Central Office House bill total exceed the district-office total?',central-deo,'money',[kinds['central']['nep_php']-kinds['deo']['nep_php'],all_totals['hgab3_php']-central,deo],'house','Subtract the district-office total from the Central Office total.')
    value(cat,hard,'What is the percentage increase for the leading office on the percentage board?',pct_increases[0]['delta_pct'],'pct',[x['delta_pct'] for x in pct_increases[1:]],'increase_pct','The percentage board limits the ranking to offices with at least ₱500 million in the NEP.')
    value(cat,hard,'By how much does unmatched-to-NEP value exceed NEP-only value?',all_totals['added_php']-all_totals['dropped_php'],'money',[all_totals['added_php']+all_totals['dropped_php'],net,all_totals['held_php']],'added','Compare the two candidate groups in the full leaderboard totals.')
    value(cat,hard,'What percentage of the top office total has no NEP match?',100*top['added_php']/top['hgab3_php'],'pct',[100*x['added_php']/x['hgab3_php'] for x in shares[1:]],'added_share','Divide the top office’s unmatched value by its House bill total.')
    value(cat,hard,'What is the combined amount of the three largest positive office changes?',sum(x['delta_php'] for x in increases[:3]),'money',[sum(x['delta_php'] for x in increases[1:4]),sum(x['delta_php'] for x in increases[2:5]),net],'increase','Add the three largest positive office changes.')
    value(cat,hard,'What is the combined absolute value of the three largest office cuts?',sum(abs(x['delta_php']) for x in cuts[:3]),'money',[sum(abs(x['delta_php']) for x in cuts[1:4]),sum(abs(x['delta_php']) for x in cuts[2:5]),all_totals['dropped_php']],'cuts','Add the absolute amounts of the three largest reductions.')
    value(cat,hard,'How many lines are in the unmatched-to-NEP group plus the held-for-review group?',all_totals['added_rows']+all_totals['held_rows'],'count',[all_totals['added_rows'],all_totals['dropped_rows'],all_totals['held_rows']],'added','Add the no-match lines to the held lines; both remain review groups.')

    # Enacted budget history · direct ranked facts are medium; calculations hard.
    cat='Enacted budget history'; history=rank('gaa_total_php')
    years={y:sorted([e for e in entries if isinstance(e.get('gaa',{}).get(str(y)),(int,float))],key=lambda e:(-e['gaa'][str(y)],office(e).casefold())) for y in range(2020,2027)}
    named(cat,easy,'Which office ranks first by total enacted DPWH budget from 2020 through 2026?',history[0],history,'history','The historical board adds the enacted amounts available for each office across these fiscal years.')
    value(cat,easy,f"What is {office(history[0])}'s combined enacted total for 2020–2026?",history[0]['gaa_total_php'],'money',[e['gaa_total_php'] for e in history[1:]],'history','This is the historical-total board’s sum for the top office.')
    named(cat,easy,'Which office ranks first by enacted DPWH amount in FY2026?',years[2026][0],years[2026],'year','This board ranks office totals in the enacted FY2026 budget.')
    value(cat,easy,f"What amount is listed for {office(years[2026][0])} in FY2026?",years[2026][0]['gaa']['2026'],'money',[e['gaa']['2026'] for e in years[2026][1:]],'year','This is the enacted FY2026 amount for the leading office.')
    for y in range(2020,2026):
        named(cat,easy,f'Which office ranks first in enacted DPWH amount for FY{y}?',years[y][0],years[y],'history','The yearly board ranks district-office amounts for that enacted fiscal year.')

    named(cat,med,'Which office ranks second by total enacted DPWH amount from 2020 through 2026?',history[1],history,'history','This is the runner-up on the historical-total board.')
    named(cat,med,'Which office ranks third by total enacted DPWH amount from 2020 through 2026?',history[2],history,'history','This is the third office on the historical-total board.')
    value(cat,med,f"What is the second-ranked office’s 2020–2026 enacted total ({office(history[1])})?",history[1]['gaa_total_php'],'money',[e['gaa_total_php'] for e in history[2:]],'history','Read the second value on the enacted-total board.')
    named(cat,med,'Which office ranks second in enacted DPWH amount for FY2026?',years[2026][1],years[2026],'year','This is the runner-up on the FY2026 board.')
    for y in range(2020,2026):
        named(cat,med,f'Which office ranks second in enacted DPWH amount for FY{y}?',years[y][1],years[y],'history','This is the runner-up on the annual enacted-budget ranking.')

    top_history=history[0]; top_years=top_history['gaa_years']
    def enacted_sum(row, selected_years):
        return sum((row.get('gaa',{}).get(str(y)) or 0) for y in selected_years)
    value(cat,hard,'How much larger is the leading 2020–2026 enacted total than the runner-up?',history[0]['gaa_total_php']-history[1]['gaa_total_php'],'money',[e['gaa_total_php'] for e in history[2:]],'history','Subtract the second-ranked total from the leading total.')
    value(cat,hard,'What is the combined 2020–2026 enacted total of the top three offices?',sum(e['gaa_total_php'] for e in history[:3]),'money',[sum(e['gaa_total_php'] for e in history[1:4]),sum(e['gaa_total_php'] for e in history[2:5]),sum(e['gaa_total_php'] for e in history[3:6])],'history','Add the first three office totals on the historical board.')
    value(cat,hard,f"What is the average enacted amount per listed year for {office(top_history)}, rounded to the nearest ₱1 million?",round(top_history['gaa_total_php']/len(top_years)/1_000_000)*1_000_000,'money',[round(e['gaa_total_php']/max(1,len(e.get('gaa_years',[])))/1_000_000)*1_000_000 for e in history[1:]],'history','Divide the seven-year total by the number of available years and round to the nearest million.')
    value(cat,hard,'How much larger is the leading FY2026 office amount than the runner-up?',years[2026][0]['gaa']['2026']-years[2026][1]['gaa']['2026'],'money',[e['gaa']['2026'] for e in years[2026][2:]],'year','Subtract the runner-up’s amount from the top FY2026 amount.')
    value(cat,hard,f"How much is {office(top_history)}'s combined enacted amount for FY2020–FY2022?",enacted_sum(top_history,(2020,2021,2022)),'money',[enacted_sum(e,(2020,2021,2022)) for e in history[1:]],'history','Add this office’s enacted amounts for FY2020, FY2021 and FY2022; unavailable yearly entries count as zero in the published total.')
    value(cat,hard,f"How much is {office(top_history)}'s combined enacted amount for FY2023–FY2026?",enacted_sum(top_history,(2023,2024,2025,2026)),'money',[enacted_sum(e,(2023,2024,2025,2026)) for e in history[1:]],'history','Add this office’s enacted amounts for FY2023 through FY2026; unavailable yearly entries count as zero in the published total.')
    value(cat,hard,f"How much larger is {office(top_history)}'s full historical total than its FY2026 amount?",top_history['gaa_total_php']-enacted_sum(top_history,(2026,)),'money',[e['gaa_total_php']-enacted_sum(e,(2026,)) for e in history[1:]],'history','Subtract FY2026 from the office’s total across the covered years.')
    value(cat,hard,'What is the combined 2020–2026 enacted total for the top five offices?',sum(e['gaa_total_php'] for e in history[:5]),'money',[sum(e['gaa_total_php'] for e in history[1:6]),sum(e['gaa_total_php'] for e in history[2:7]),sum(e['gaa_total_php'] for e in history[3:8])],'history','Add the first five values on the historical-total board.')
    top26=years[2026][0]
    value(cat,hard,f"For {office(top26)}, what is the change from its FY2025 amount to FY2026?",enacted_sum(top26,(2026,))-enacted_sum(top26,(2025,)),'money',[enacted_sum(e,(2026,))-enacted_sum(e,(2025,)) for e in years[2026][1:]],'year','Subtract FY2025 from FY2026 for the office ranked first in 2026.')
    value(cat,hard,'What is the combined FY2020 and FY2026 amount for the top historical-total office?',enacted_sum(top_history,(2020,2026)),'money',[enacted_sum(e,(2020,2026)) for e in history[1:]],'history','Add this office’s amounts from the first and last years in the series.')

    # House members · easy concepts, medium retrieval, hard low-count entries.
    cat='House members'
    if len(people)<20:raise ValueError('Leaderboard snapshot needs at least twenty district representatives with bill counts')
    person_district=lambda p:p.get('district','District not listed')
    lowest_count_people=sorted(people,key=lambda p:(p['bill_count'],display_person(p).casefold()))[:10]
    person_q(cat,easy,'Who ranks first on the members board by bills as principal author?',people[0],people,'members','The members board counts bills listing a district representative as a principal author; it does not rank budget amounts.')
    person_value(cat,easy,f"How many bills are listed for {display_person(people[0])}?",people[0]['bill_count'],[p['bill_count'] for p in people[1:]],'members','The source notes that the bills.juris.ph list is not yet complete.')
    for i in range(1,6):person_q(cat,easy,f'Who ranks {ordinal(i+1)} by bills as principal author?',people[i],people,'members','The members board is ordered by principal-author bill count.')
    value(cat,easy,'How many district representatives with bill counts appear in this snapshot?',len(people),'count',[totals['districts'],totals['units'],totals['units_tier_a']],'members','The members board includes district representatives with a recorded bill count.')
    add(cat,easy,'What does the members leaderboard rank?','Bills as principal author',['DPWH project amounts','District offices','Enacted budget years'],'members','It ranks representatives by bills listing them as principal author.')
    add(cat,easy,'Whose totals appear on the DPWH office-budget boards?','District offices',['Individual representatives','Political parties','Contractors'],'index','The leaderboard says budget amounts belong to DPWH offices, not people.')
    for i in range(7,12):person_q(cat,med,f'Who ranks {ordinal(i+1)} by bills as principal author?',people[i],people,'members','This is the representative’s position on the member-count board.')
    for i in range(1,6):person_value(cat,med,f"How many bills are listed for the member ranked {ordinal(i+1)}?",people[i]['bill_count'],[p['bill_count'] for p in people if p is not people[i]],'members','The member ranking uses principal-author bill counts.')
    for p in lowest_count_people:
        person_q(cat,hard,
                 f"Which representative is listed for {person_district(p)} with {number(p['bill_count'])} principal-author bills?",
                 p,people,'members',
                 'This targets one of the ten lowest bill counts shown on the members board. The source notes its bill list is incomplete; these counts measure listed principal authorship, not district or personal popularity.')

    for q in questions:
        if q['category'] in {'2027 House bill','Enacted budget history'} and q['difficulty']=='easy':
            q['difficulty']='medium'
        elif q['category']=='House members' and q['difficulty']=='easy':
            q['difficulty']='medium'

    ilocos_member=next(p for p in people if p.get('district')=='Ilocos Norte, 1st District')
    mika=next(p for p in people if 'Suansing, Mikaela Angela' in p.get('name',''))
    bojie=next(p for p in people if 'Dy, Faustino "Bojie"' in p.get('name',''))
    rufus=people[0]
    easy_representatives=[
        ('Sandro Marcos','Ilocos Norte, 1st District',ilocos_member,
         ['Mika Suansing','Bojie Dy','Rufus B. Rodriguez'],
         f"The leaderboard lists {display_person(ilocos_member)} for Ilocos Norte, 1st District; he is commonly known as Sandro Marcos."),
        ('Mika Suansing','Nueva Ecija, 1st District',mika,
         ['Sandro Marcos','Bojie Dy','Bella Suansing'],
         f"The leaderboard lists {display_person(mika)} for Nueva Ecija, 1st District."),
        ('Bojie Dy','Isabela, 6th District',bojie,
         ['Sandro Marcos','Mika Suansing','Faustino Michael Carlos III Dy'],
         f"The leaderboard lists {display_person(bojie)} for Isabela, 6th District."),
        ('Rufus B. Rodriguez','Cagayan de Oro City, 2nd District',rufus,
         ['Sandro Marcos','Mika Suansing','Bojie Dy'],
         f"The leaderboard lists {display_person(rufus)} for Cagayan de Oro City, 2nd District; he leads the members board by listed principal-author bills."),
    ]
    for answer,district,person,wrong,explanation in easy_representatives:
        prompts=(f'Which member of Congress is listed for {district}?',
                 f'Who is the {district} representative on the leaderboard?')
        for prompt in prompts:
            add(cat,easy,prompt,answer,wrong,'members',explanation)
            questions[-1]['easyMemberGroup']=answer

    expected={'2027 House bill':{'easy':0,'medium':25,'hard':15},
              'Enacted budget history':{'easy':0,'medium':20,'hard':10},
              'House members':{'easy':8,'medium':20,'hard':10}}
    actual={c:{d:sum(q['category']==c and q['difficulty']==d for q in questions) for d in ('easy','medium','hard')} for c in expected}
    if actual!=expected or len(questions)!=108:raise RuntimeError(f'Leaderboard distribution mismatch: {actual}; total {len(questions)}')
    return questions


def amount_question(qid, prompt, value, source, explanation, difficulty='medium', topic='coverage', unit='', currency=False):
    choices, answer = choices_for(value, currency=currency, places=0 if currency or not unit else 1, unit=unit)
    return {
        'id': qid, 'question': prompt, 'choices': choices, 'answer': answer,
        'explanation': explanation, 'hint': 'Use the cited HGAB 3rd-reading evidence and check its scope note.',
        'sources': [source], 'difficulty': difficulty, 'topic': topic,
        'questionType': 'hgab3-data-fact', 'stage': STAGE,
        'generatedFromHgabAnalysis': True,
    }


def improvement_questions(hgab_primary, in_depth, review, cost, mpb, rcs, location):
    source_pdf = {'label': 'DPWH · HGAB 3rd-reading schedule', 'url': 'dpwh-hgab.html'}
    source_cost = {'label': 'HGAB 3rd · cost per meter and length coverage', 'url': 'cost-per-km.html'}
    source_mpb = {'label': 'Multi-purpose buildings · HGAB 3rd review', 'url': 'mpb.html'}
    source_location = {'label': 'Congressional geographic attribution · HGAB 3rd method', 'url': 'congress.html'}
    source_rcs = {'label': 'Rainwater Collector System · HGAB 3rd stage trace', 'url': 'rcs.html'}
    source_link = {'label': 'HGAB 3rd · matching and review queue', 'url': 'dpwh-hgab.html'}
    facts = []
    facts.append({
        'id': 'fy2027-proposed-total',
        'question': 'How much is the proposed Philippine national budget for 2027?',
        'choices': ['₱6 trillion', '₱7.2 trillion', '₱8.4 trillion', '₱10 trillion'],
        'answer': '₱7.2 trillion',
        'explanation': 'The Department of Budget and Management submitted a proposed FY2027 National Budget of ₱7.2 trillion. This is the proposed NEP total, not the later enacted budget.',
        'hint': 'The cited DBM release gives the proposed total in its headline.',
        'sources': [{'label': 'DBM · Proposed FY2027 National Budget', 'url': 'https://www.dbm.gov.ph/index.php/management-2/4143-dbm-submits-7-2-t-2027-people-centered-budget-to-congress-puts-education-health-jobs-at-heart-of-marcos-administration-s-final-full-year-spending-plan'}],
        'difficulty': 'easy', 'category': None, 'topic': None,
        'questionType': 'national-budget-total', 'generatedFromNationalBudget': True,
    })
    stage_source={'label':'BetterGov · NEP to HGAB budget-stage comparison',
                  'url':'https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/#compare'}
    glossary=[
        ('easy-nep-definition','What does NEP stand for?','National Expenditure Program',
         ['National Economic Program','National Expenditure Plan','New Executive Proposal'],
         'NEP means National Expenditure Program, the proposed budget the Executive submits to Congress.'),
        ('easy-hgab-definition','In our 2027 budget questions, what does HGAB mean?','House General Appropriations Bill',
         ['House General Allocation Budget','Higher Government Appropriations Bill','House Government Annual Budget'],
         'HGAB refers to the House General Appropriations Bill; this project tracks its third-reading version.'),
        ('easy-gab-definition','What does GAB stand for?','General Appropriations Bill',
         ['General Appropriations Act','Government Allocation Budget','General Agency Budget'],
         'GAB means General Appropriations Bill. The House and Senate consider their own bill versions before reconciliation.'),
        ('easy-bicam-definition','What does “bicam” refer to in the budget process?','The House-Senate conference that reconciles bill differences',
         ['The Executive’s original budget proposal','The House’s third-reading vote','The enacted General Appropriations Act'],
         'Bicam is the bicameral conference stage, where the House and Senate reconcile differences between their General Appropriations Bill versions.'),
        ('easy-gaa-definition','What does GAA stand for?','General Appropriations Act',
         ['Government Allocation Agreement','General Agency Appropriation','Government Annual Allocation'],
         'GAA means General Appropriations Act, the enacted national budget.'),
        ('easy-nep-bicam-gaa-order','Which order correctly arranges NEP, Bicam, and GAA?',
         'NEP → Bicam → GAA',
         ['Bicam → NEP → GAA','NEP → GAA → Bicam','GAA → Bicam → NEP'],
         'The NEP is the proposed budget, Bicam reconciles the House and Senate bills later in the process, and the GAA is the enacted budget.'),
        ('easy-nep-hgab-gab-order','Which order correctly arranges NEP, HGAB, and GAB?',
         'NEP → HGAB → GAB',
         ['GAB → HGAB → NEP','NEP → GAB → HGAB','HGAB → NEP → GAB'],
         'The NEP is the Executive proposal, HGAB is the House bill, and GAB is the Senate bill in this stage comparison.'),
    ]
    for qid,prompt,answer,wrong,explanation in glossary:
        choices=[answer,*wrong]
        random.Random(qid).shuffle(choices)
        facts.append({
            'id':qid,'question':prompt,'choices':choices,'answer':answer,
            'explanation':explanation,
            'hint':'Think of the budget stages from the proposed NEP through congressional deliberation to the enacted GAA.',
            'sources':[stage_source],'difficulty':'easy','category':None,'topic':'budget-basics',
            'questionType':'budget-stage-definition','generatedFromBudgetGlossary':True,
        })
    schedule = hgab_primary['metadata']['sourceFiles'][0]
    facts.append(amount_question('hgab3-schedule-records',
        'How many project allocation records were extracted directly from the HGAB 3rd-reading schedule?',
        schedule['candidateRows'], source_pdf,
        'The extracted HGAB 3rd-reading dataset contains this many allocation records. Schedule records are not equivalent to verified construction projects.',
        'basic', 'budget'))
    facts.append(amount_question('hgab3-schedule-total',
        'What total amount is represented by project allocations extracted directly from the HGAB 3rd-reading schedule?',
        schedule['allocationPesos'], source_pdf,
        'The extracted schedule records total this amount. It is an appropriation total, not evidence of payment or completion.',
        'basic', 'budget', currency=True))

    coverage = in_depth['hgabCoverage']
    facts.append(amount_question('hgab3-high-rate-candidates',
        'How many HGAB 3rd road and bridge lines meet the project’s high allocation-per-meter review screen?',
        cost['highRateScreen']['candidates'], source_cost,
        'The exploratory screen requires a rate above both twice the peer median and Q3 + 1.5 × IQR. It is a review lead, not proof of overpricing.'))
    facts.append(amount_question('hgab3-rate-graph-extremes',
        'How many high-rate HGAB 3rd records are displayed as graph extremes after the stricter chart cutoff?',
        cost['highRateScreen']['graphExtremeRecords'], source_cost,
        'Graph extremes use a stricter chart cutoff than the high-rate candidate screen; they remain scope-review candidates.'))

    length_rows = {row['category']: row for row in cost['summary']}
    for cat, label, qid, difficulty in [
        ('Roads', 'road', 'hgab3-road-length-coverage', 'medium'),
        ('Bridges', 'bridge', 'hgab3-bridge-length-coverage', 'medium'),
        ('FMR', 'farm-to-market road', 'hgab3-fmr-length-coverage', 'medium'),
    ]:
        row = length_rows[cat]
        facts.append(amount_question(qid,
            f'In the HGAB 3rd {label} length screen, how many of {number(row["lineItems"])} allocation lines have a usable stated length?',
            row['withLength'], source_cost,
            f'{number(row["withLength"])} of {number(row["lineItems"])} lines have usable stated lengths. This coverage limit means the other allocations do not receive a per-meter rate from this screen.',
            difficulty, 'cost-per-meter'))

    m = mpb['summary']
    facts.append(amount_question('hgab3-mpb-allocation-lines',
        'How many multi-purpose building allocation lines were reviewed in the HGAB 3rd dataset?',
        m['hgabLines'], source_mpb,
        'The MPB review covers this many HGAB 3rd lines. Its matching and repeat groups are review candidates, not confirmed project additions or duplicate work.',
        'basic', 'budget'))
    facts.append(amount_question('hgab3-mpb-insertion-candidates',
        'How many HGAB 3rd MPB lines have no selected NEP counterpart and are therefore insertion candidates for review?',
        m['insertionCandidates'], source_mpb,
        'These are candidate HGAB 3rd lines from the NEP-versus-HGAB title/scope screen. No selected counterpart does not confirm a new project or a legislative insertion.',
        'medium', 'budget'))
    facts.append(amount_question('hgab3-mpb-repeat-pairs',
        'How many multi-purpose-building title-pair candidates appear in the HGAB 3rd historical-repeat screen?',
        m['repeatPairs'], source_mpb,
        'Title recurrence is a lead for checking location, funded scope, phase, completion status, and chainage. It is not proof of duplicate paid work.',
        'medium', 'budget'))

    # Turn selected historical MPB matches into straightforward repeat-appearance
    # trivia. Require verified barangay/municipality/province agreement for every
    # year in a group, and describe GAA appearances rather than asserting that
    # appropriated work was completed.
    repeat_groups = {}
    for row in mpb.get('repeats', []):
        if row.get('sameBarangayVerified') is not True or not row.get('comparison_year'):
            continue
        if not row.get('barangay') or row['barangay'] == 'Same barangay not established':
            continue
        key = (row.get('source_code'), row.get('project'))
        repeat_groups.setdefault(key, []).append(row)
    repeated_sites = []
    for (_, title), rows in repeat_groups.items():
        years = sorted({int(row['comparison_year']) for row in rows})
        if len(years) < 2:
            continue
        sites = {row.get('barangay') for row in rows}
        if len(sites) != 1:
            continue
        site = next(iter(sites))
        repeated_sites.append((len(years), years, title, site))
    repeated_sites.sort(key=lambda item: (-item[0], item[3], item[2]))
    for i, (count, years, title, site) in enumerate(repeated_sites[:10], 1):
        site_label = ', '.join(part.strip().title() for part in site.split(' · '))
        answer = f'{count} years'
        wrong_counts = [n for n in (count - 2, count - 1, count + 1, count + 2, count + 3)
                        if n > 0 and n != count]
        choices = [answer] + [f'{n} years' for n in wrong_counts[:3]]
        numeric_choices = [count] + wrong_counts[:3]
        choice_spread = (max(numeric_choices) - min(numeric_choices)) / (sum(numeric_choices) / len(numeric_choices))
        difficulty = 'hard' if choice_spread < 0.2 else 'medium'
        qid = f'mpb-historic-appearance-{i:03d}'
        random.Random(qid).shuffle(choices)
        facts.append({
            'id': qid,
            'question': f'Across how many past GAA years does a multi-purpose building project at {site_label} appear?',
            'choices': choices,
            'answer': answer,
            'explanation': f'The historical MPB screen lists corresponding project titles at this verified administrative site in {", ".join(map(str, years))}. GAA listings show appropriations, not proof that construction was completed or that every entry refers to the same physical building.',
            'hint': 'Count the distinct fiscal years in the cited historical project matches.',
            'sources': [{'label': 'Multi-purpose buildings · historical GAA title matches', 'url': 'mpb.html'}],
            'difficulty': difficulty,
            'topic': 'budget',
            'questionType': 'hgab3-mpb-historical-appearance',
            'stage': STAGE,
            'generatedFromMpbHistoricalGaa': True,
            'historicalGaaYears': years,
        })

    facts.append(amount_question('hgab3-rainwater-unchanged-lines',
        'How many district-office Rainwater Collector System lines were retained unchanged in the HGAB 3rd schedule?',
        rcs['summary']['unchangedInHGAB'], source_rcs,
        'The stage trace paired all 199 district-office RCS rows to HGAB 3rd lines with unchanged listed amounts. Office labels do not establish installation locations.',
        'medium', 'budget'))

    facts.append(amount_question('hgab3-single-district-lines',
        'How many HGAB 3rd DPWH allocation lines received a unique district association under the current location screen?',
        location['summary']['uniquelyAssignedLines'], source_location,
        'Assignments use qualified geography and checked source context. The result describes geographic association, not project sponsorship or a representative’s control.',
        'medium', 'coverage'))
    facts.append(amount_question('hgab3-strict-location-share',
        'What share of HGAB 3rd DPWH allocation value is assigned under the strict location screen?',
        location['summary']['strictCoveragePct'], source_location,
        f'The current screen strictly assigns {number(location["summary"]["strictAssignedPesos"], 0)} pesos. Unresolved or shared locations stay out; this is not a complete district-budget allocation.',
        'medium', 'coverage', unit='%'))

    # The stale question is converted to the actual 3rd-reading RCS value.
    facts.append({
        'id': 'hgab3-rainwater-line-amount',
        'question': 'What amount appears for each of the 199 district-office Rainwater Collector System lines retained in HGAB 3rd?',
        'choices': ['₱4,200,000', '₱2,100,000', '₱8,400,000', '₱42,000,000'],
        'answer': '₱4,200,000',
        'explanation': 'All 199 district-office RCS lines in the stage trace retain a ₱4.2 million allocation in the HGAB 3rd schedule. This is the listed amount, not verified spending or an installation count.',
        'hint': 'Check the HGAB 3rd allocation in the linked stage trace.',
        'sources': [source_rcs], 'difficulty': 'basic', 'topic': 'budget',
        'questionType': 'hgab3-allocation', 'stage': STAGE, 'generatedFromHgabAnalysis': True,
    })
    return facts


def geography_questions(fmr_coordinates, fmr_audit, mpb_audit):
    """Make trivia from the most striking, documented coordinate anomalies."""
    by_id = {p['project_id']: p for p in fmr_coordinates['projects']}
    repairs = {}
    for repair in fmr_audit['digit_repairs']:
        repairs.setdefault(repair['project_id'], []).append(repair)
    candidates = mpb_audit['candidates']
    baclao = next(x for x in candidates if 'Barangay Baclao' in x['projectName'])
    villamiemban = next(x for x in candidates if 'Villamiemban' in x['projectName'])
    tampac = by_id['ib:p685:r5']
    tagumpay = by_id['ib:p692:r16']
    badian = by_id['ib:p713:r3']
    buyon = by_id['ib:p677:r5']

    def fix(project_id, phrase):
        return next(x for x in repairs[project_id] if phrase in x['repair'])

    def distance_km(points):
        from math import asin, cos, radians, sin, sqrt
        (lon1, lat1), (lon2, lat2) = points
        dlon, dlat = radians(lon2-lon1), radians(lat2-lat1)
        a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
        return 6371.0088 * 2 * asin(sqrt(a))

    buyon_raw_km = distance_km([
        [121.879510, 16.851721], [121.879302, 18.826792],
    ])
    buyon_fixed_km = distance_km(buyon['coordinates'][0])
    sources = {
        'fmr': {'label': 'HGAB 3rd · FMR coordinate review', 'url': 'cost-matching.html'},
        'mpb': {'label': 'HGAB 3rd · MPB coordinate boundary audit', 'url': 'mpb.html'},
    }
    questions = []

    def add(qid, prompt, answer, distractors, difficulty, source, explanation):
        choices = [str(answer)]
        for item in distractors:
            if str(item) not in choices:
                choices.append(str(item))
            if len(choices) == 4:
                break
        if len(choices) != 4:
            raise ValueError(f'Not enough unique geography choices for {qid}')
        random.Random(qid).shuffle(choices)
        questions.append({
            'id': qid, 'question': prompt, 'choices': choices, 'answer': str(answer),
            'explanation': explanation,
            'hint': 'Compare the printed coordinate with the reviewed location evidence.',
            'sources': [source], 'difficulty': difficulty, 'topic': 'geography',
            'questionType': 'hgab3-coordinate-anomaly', 'stage': STAGE,
            'generatedFromGeographicEvidence': True,
        })

    tampac_repair = fix(tampac['project_id'], 'end longitude')
    add('geo-tampac-project',
        'Which Guimba, Nueva Ecija FMR had an endpoint printed at 129.803°E, far east of its named location?',
        'Tampac I FMR', ['Buyon FMR', 'Tagumpay FMR', 'Basiao–Candiis FMR'], 'medium', sources['fmr'],
        'The HGAB coordinate audit accepted a correction from 129.8030109°E to 120.8030109°E for Tampac I in Guimba.')
    add('geo-tampac-corrected-longitude',
        'What corrected longitude was accepted for the Tampac I FMR endpoint?',
        '120.803°E', ['129.803°E', '126.803°E', '120.083°E'], 'medium', sources['fmr'],
        f"The printed value was 129.8030109°E; the reviewed coordinate is {tampac_repair['accepted'][0]:.6f}°E.")

    tagumpay_repair = fix(tagumpay['project_id'], 'S2 start latitude')
    add('geo-tagumpay-project',
        'Which FMR in Real, Quezon briefly placed a section point at 4.606488°N, far south of the project?',
        'Tagumpay FMR', ['Tampac I FMR', 'Buyon FMR', 'Basiao–Candiis FMR'], 'medium', sources['fmr'],
        'The source-listed S2 point was 4.606488°N; the coordinate audit accepted 14.606488°N using the matching project location evidence.')
    add('geo-tagumpay-corrected-latitude',
        'What latitude was accepted for the Tagumpay FMR S2 point?',
        '14.606488°N', ['4.606488°N', '14.066488°N', '15.606488°N'], 'medium', sources['fmr'],
        f"The coordinate audit records the correction {tagumpay_repair['repair']}.")

    badian_repair = fix(badian['project_id'], 'section 2 end latitude')
    add('geo-badian-project',
        'A Badian, Cebu FMR section ended at a printed latitude of 1.804228°N. Which project was it?',
        'Basiao–Candiis FMR', ['Tampac I FMR', 'Buyon FMR', 'Tagumpay FMR'], 'medium', sources['fmr'],
        'The reviewed source record is the Basiao–Candiis FMR; the audit accepted an endpoint latitude correction to 9.8042275°N.')
    add('geo-badian-corrected-latitude',
        'What corrected latitude was accepted for the Badian FMR section 2 endpoint?',
        f"{badian_repair['accepted'][1]:.6f}°N", ['1.804228°N', '9.084228°N', '10.804228°N'], 'medium', sources['fmr'],
        f"The printed 1.8042275°N value was corrected to {badian_repair['accepted'][1]:.7f}°N in the audit.")

    add('geo-buyan-before-correction',
        'Before its latitude correction, how far apart did the two Buyon FMR endpoints appear?',
        f'{buyon_raw_km:.1f} km', ['2.8 km', '22.0 km', '777.9 km'], 'hard', sources['fmr'],
        f'The printed coordinates imply about {buyon_raw_km:.1f} km. After the reviewed correction, the same endpoints are about {buyon_fixed_km:.1f} km apart.')
    add('geo-buyan-after-correction',
        'After the Buyon FMR coordinate correction, about how far apart are its two endpoints?',
        f'{buyon_fixed_km:.1f} km', ['0.3 km', '22.0 km', f'{buyon_raw_km:.1f} km'], 'hard', sources['fmr'],
        'The printed end latitude 18.826792° was corrected to 16.826792° using location evidence, reducing the apparent span from about 219.6 km to about 2.8 km.')

    add('geo-mpb-baclao-distance',
        'How far outside its named municipality did the coordinate for the Baclao MPB in Cauayan, Negros Occidental plot?',
        f"{baclao['outsideBoundaryKm']:.1f} km", ['106.5 km', '104.7 km', '47.5 km'], 'medium', sources['mpb'],
        'The point is a coordinate review lead: it falls 777.9 km outside the named Cauayan boundary. This does not establish the project’s actual site.')
    add('geo-mpb-villamiemban-distance',
        'How far outside Cordon, Isabela did the Villamiemban MPB coordinate plot?',
        f"{villamiemban['outsideBoundaryKm']:.1f} km", ['777.9 km', '104.7 km', '47.5 km'], 'medium', sources['mpb'],
        'The municipal-boundary audit measured the printed coordinate 106.5 km outside Cordon. It flags a location mismatch for review, not proof of a mislocated project.')
    return questions


def road_bridge_3d_questions(cost):
    """Create thirty ranked graph questions each for roads and bridges."""
    eligible = {'Roads': [], 'Bridges': []}
    lane_sources = [
        ('titleStatedLanes', 'Stated in project title/context'),
        ('inventoryEffectiveLanes', 'Matched existing-road inventory estimate'),
        ('inventoryAssetEffectiveLanes', 'Matched existing-asset dimensions'),
    ]
    for row in cost['projects']:
        category = row.get('category')
        if category not in eligible or not row.get('lengthMeters') or row['lengthMeters'] < 10 or not row.get('amountPesos'):
            continue
        lane_count = None
        lane_basis = None
        for key, basis in lane_sources:
            if row.get(key) and row[key] > 0:
                lane_count, lane_basis = float(row[key]), basis
                break
        if lane_count is None and category == 'Bridges' and row.get('manualLaneEstimateLanes', 0) > 0:
            lane_count, lane_basis = float(row['manualLaneEstimateLanes']), 'Assumed two lanes for group comparison'
        if lane_count is None:
            continue
        enriched = dict(row)
        enriched['plotLanes'] = lane_count
        enriched['laneBasis'] = lane_basis
        enriched['plotDensity'] = float(row['amountPesos']) / (float(row['lengthMeters']) * lane_count)
        eligible[category].append(enriched)

    output = []
    for category, anchor, kind in [
        ('Roads', 'roads-3d-plot', 'road'),
        ('Bridges', 'bridges-3d-plot', 'bridge'),
    ]:
        # Python's stable sort preserves D.projects order for equal densities,
        # matching the chart's JavaScript Array.sort behavior.
        ranked = sorted(eligible[category], key=lambda row: -row['plotDensity'])[:30]
        if len(ranked) < 30:
            raise ValueError(f'The {category} 3D graph has fewer than thirty eligible plotted records')
        titles = []
        for row in ranked:
            title = row.get('projectName') or row['id']
            if title not in titles:
                titles.append(title)

        def choose_numeric(answer, pool, label, qid):
            answer_text = f'{number(answer)} {label}'
            wrong = []
            for value in pool:
                text = f'{number(value)} {label}'
                if text != answer_text and text not in wrong:
                    wrong.append(text)
                if len(wrong) == 3:
                    break
            offset = max(1, round(float(answer) * 0.1))
            if len(wrong) < 3:
                for delta in (offset, -offset, offset * 2, -offset * 2, 1, 2):
                    value = max(0, float(answer) + delta)
                    text = f'{number(value)} {label}'
                    if text != answer_text and text not in wrong:
                        wrong.append(text)
                    if len(wrong) >= 3:
                        break
            choices = [answer_text] + wrong[:3]
            if len(choices) != 4 or len(set(choices)) != 4:
                raise ValueError(f'Not enough unique numeric choices for {qid}')
            random.Random(qid).shuffle(choices)
            return answer_text, choices

        def add(rank_index, diff, prompt, answer, choices, row, explanation):
            rank = rank_index + 1
            qid = f'graph-{kind}-{rank:02d}'
            output.append({
                'id': qid,
                'question': prompt,
                'choices': choices,
                'answer': answer,
                'explanation': explanation,
                'hint': 'Read the 3D chart hover details and check whether its lane count is stated, matched, or assumed.',
                'sources': [{'label': f"HGAB 3rd · {category.lower()} 3D allocation-density graph · rank {rank}",
                             'url': f'cost-per-km.html#{anchor}'}],
                'difficulty': diff,
                'category': category,
                'topic': 'cost-per-meter',
                'questionType': 'hgab3-3d-cost-density',
                'stage': STAGE,
                'generatedFrom3dGraph': True,
                'graphRank': rank,
                'graphProjectId': row['id'],
            })

        def base_explanation(row):
            return (
                f"The graph plots {number(row['lengthMeters'])} m and uses {number(row['plotLanes'])} lane(s) "
                f"({row['laneBasis']}) for {row['projectName']}. Actual allocation density is the full listed allocation "
                "divided by stated segment length and the lane count used for comparison. It is a screening measure, "
                "not a construction unit cost or a finding of overpricing."
            )

        for index, row in enumerate(ranked):
            rank = index + 1
            title = row.get('projectName') or row['id']
            if rank <= 10:
                wrong_titles = [name for name in titles if name != title][:3]
                if len(wrong_titles) < 3:
                    raise ValueError(f'Not enough distinct project titles in {category} 3D graph')
                choices = [title] + wrong_titles
                random.Random(f'graph-{kind}-{rank:02d}').shuffle(choices)
                add(index, 'medium',
                    f'Which project ranks {rank}{"st" if rank % 10 == 1 and rank % 100 != 11 else "nd" if rank % 10 == 2 and rank % 100 != 12 else "rd" if rank % 10 == 3 and rank % 100 != 13 else "th"} by allocation density in the 30-project {kind} graph?',
                    title, choices, row, base_explanation(row))
            elif rank <= 20:
                answer, choices = choose_numeric(row['lengthMeters'],
                    [x['lengthMeters'] for x in ranked], 'm', f'graph-{kind}-{rank:02d}')
                add(index, 'medium',
                    f'What stated segment length does the graph plot for the #{rank} {kind}, {title}?',
                    answer, choices, row, base_explanation(row))
            else:
                answer, choices = choose_numeric(row['plotDensity'],
                    [x['plotDensity'] for x in ranked], 'pesos per lane-meter', f'graph-{kind}-{rank:02d}')
                add(index, 'hard',
                    f'Using the listed allocation, stated length, and {number(row["plotLanes"])} lane(s), what is the actual allocation density for {title}, rounded to the nearest peso per lane-meter?',
                    answer, choices, row,
                    f"Divide the listed ₱{number(row['amountPesos'])} allocation by {number(row['lengthMeters'])} stated meters and {number(row['plotLanes'])} lane(s) ({row['laneBasis']}) to get {answer}. This is allocation density for comparison, not a construction unit cost.")

    counts = {category: {difficulty: sum(q['category'] == category and q['difficulty'] == difficulty for q in output)
                         for difficulty in ('easy', 'medium', 'hard')}
              for category in ('Roads', 'Bridges')}
    expected = {category: {'easy': 0, 'medium': 20, 'hard': 10} for category in ('Roads', 'Bridges')}
    if counts != expected or len(output) != 60:
        raise RuntimeError(f'3D graph question distribution mismatch: {counts}')
    return output


def deo_crosswalk_questions(source):
    """Build a compact Tier A/Tier B office-to-district trivia category."""
    entries = source['entries']
    units = source['totals']
    source_link = {'label': 'BetterGov · HGAB 2027 leaderboard · DEO district crosswalk',
                   'url': 'https://budget.bettergov.ph/hgab/2027/leaderboard'}
    questions = []

    def office_name(entry):
        return ' / '.join(x.get('name', '') for x in entry.get('offices', []) if x.get('name')) or 'Unlisted DEO'

    def district_names(entry):
        return list(dict.fromkeys(p.get('district') for p in entry.get('people', []) if p.get('district')))

    def add(qid, prompt, answer, wrong, difficulty, explanation):
        choices = [str(answer)]
        for item in wrong:
            if str(item) not in choices:
                choices.append(str(item))
            if len(choices) == 4:
                break
        if len(choices) != 4:
            raise ValueError(f'Not enough crosswalk answer choices for {qid}')
        random.Random(qid).shuffle(choices)
        questions.append({
            'id': qid, 'question': prompt, 'choices': choices, 'answer': str(answer),
            'explanation': explanation,
            'hint': 'Use the leaderboard’s Tier A/Tier B office-to-district mapping.',
            'sources': [source_link], 'difficulty': difficulty,
            'category': 'DEO crosswalk', 'topic': 'deo',
            'questionType': 'hgab3-deo-crosswalk', 'stage': STAGE,
            'generatedFromDEOCrosswalk': True,
            'crosswalkBuiltAt': source.get('built_at'),
        })

    tier_a = [e for e in entries if e.get('tier') == 'A' and len(e.get('offices', [])) == 1 and len(district_names(e)) == 1]
    tier_b = [e for e in entries if e.get('tier') == 'B' and len(e.get('offices', [])) == 1 and len(district_names(e)) >= 2]
    all_districts = list(dict.fromkeys(d for e in entries for d in district_names(e)))
    tier_a = sorted(tier_a, key=lambda e: (office_name(e).casefold(), e.get('key', '')))
    tier_b = sorted(tier_b, key=lambda e: (office_name(e).casefold(), e.get('key', '')))

    # Crosswalk facts need source-specific terminology or mapping lookups.
    stat_questions = [
        ('tier-a-count', 'How many Tier A DEO units appear in the leaderboard crosswalk?', units['units_tier_a'], [units['units_tier_b'], units['units'], units['districts']]),
        ('tier-b-count', 'How many Tier B DEO units appear in the leaderboard crosswalk?', units['units_tier_b'], [units['units_tier_a'], units['units'], units['districts']]),
        ('deo-unit-count', 'How many DEO units are represented across Tier A and Tier B?', units['units'], [units['units_tier_a'], units['units_tier_b'], units['districts']]),
        ('district-count', 'How many legislative districts are in the leaderboard crosswalk scope?', units['districts'], [units['units'], units['units_tier_a'], units['units_tier_b']]),
        ('tier-a-minus-b', 'How many more Tier A units than Tier B units are listed?', units['units_tier_a'] - units['units_tier_b'], [units['units_tier_b'], units['units'], units['districts']]),
    ]
    for qid, prompt, answer, wrong in stat_questions:
        add('deo-crosswalk-' + qid, prompt, number(answer), [number(x) for x in wrong], 'easy',
            'These counts describe the leaderboard crosswalk. The tier is an office-to-district grouping, not a district-boundary overlay or evidence of project sponsorship.')
    add('deo-crosswalk-tier-a-meaning', 'What does Tier A mean in this DEO crosswalk?',
        'One DEO mapped to one legislative district',
        ['One DEO shared across several districts', 'One district mapped to several DEOs', 'A district with no DEO'], 'easy',
        'Tier A is the one-office/one-district grouping in the leaderboard data.')
    add('deo-crosswalk-tier-b-meaning', 'What does Tier B mean in this DEO crosswalk?',
        'One DEO shared across multiple legislative districts',
        ['One DEO mapped to one district', 'A regional office with no districts', 'A district with no projects'], 'easy',
        'Tier B groups multiple legislative districts under a shared DEO in the leaderboard data.')

    aklan = next(e for e in tier_b if office_name(e) == 'Aklan DEO')
    add('deo-crosswalk-aklan-district-count', 'How many districts are grouped under Aklan DEO?',
        number(len(district_names(aklan))), ['1', '3', '5'], 'easy',
        'The Tier B entry groups Aklan, 1st District and Aklan, 2nd District under Aklan DEO.')
    add('deo-crosswalk-aklan-tier', 'Aklan DEO groups two legislative districts. Which crosswalk tier is it?',
        'Tier B', ['Tier A', 'Tier C', 'Unclassified'], 'easy',
        'Aklan DEO is a Tier B shared-office entry in the leaderboard crosswalk.')
    abra = next(e for e in tier_a if office_name(e) == 'Abra DEO')
    add('deo-crosswalk-abra-tier', f"{office_name(abra)} maps to {district_names(abra)[0]}. Which tier is it?",
        'Tier A', ['Tier B', 'Tier C', 'Unclassified'], 'easy',
        'Abra DEO is a one-office/one-district Tier A entry in the leaderboard crosswalk.')

    # Ten medium questions: identify a Tier A office’s single paired district.
    for i, entry in enumerate(tier_a[:10], 1):
        office, answer = office_name(entry), district_names(entry)[0]
        jurisdiction = answer.split(',')[0]
        wrong = [d for d in all_districts if d != answer and d.split(',')[0] == jurisdiction]
        wrong += [d for d in all_districts if d != answer and d not in wrong]
        add(f'deo-crosswalk-tier-a-map-{i:02d}',
            f'Which legislative district is paired with {office} in the Tier A crosswalk?',
            answer, wrong, 'medium',
            f'Tier A pairs {office} with {answer}. This reflects the leaderboard crosswalk grouping.')

    # Ten hard questions: recover an additional district from shared Tier B mappings.
    shared = [e for e in tier_b if len(district_names(e)) >= 3]
    shared.sort(key=lambda e: (len(district_names(e)), office_name(e).casefold()))
    if len(shared) < 10:
        raise ValueError('Not enough Tier B DEOs with three or more mapped districts')
    for i, entry in enumerate(shared[:10], 1):
        office = office_name(entry)
        districts = district_names(entry)
        answer = districts[-1]
        known = districts[:-1]
        jurisdiction = answer.split(',')[0]
        wrong = [d for d in all_districts if d != answer and d not in districts and d.split(',')[0] == jurisdiction]
        wrong += [d for d in all_districts if d != answer and d not in districts and d not in wrong]
        prompt = f"The Tier B crosswalk for {office} lists {' and '.join(known)}. Which additional district is included?"
        add(f'deo-crosswalk-tier-b-map-{i:02d}', prompt, answer, wrong, 'hard',
            f"The leaderboard groups {'; '.join(districts)} under {office}. Tier B is a shared-office grouping, not a geographic allocation of project value.")

    for q in questions:
        if q['difficulty']=='easy':
            q['difficulty']='medium'
    expected = {'easy': 0, 'medium': 20, 'hard': 10}
    actual = {d: sum(q['difficulty'] == d for q in questions) for d in expected}
    if len(questions) != 30 or actual != expected:
        raise RuntimeError(f'DEO crosswalk question distribution mismatch: {actual}')
    return questions


def assign_question_pools(questions):
    for q in questions:
        qid = q.get('id', '')
        kind = q.get('questionType')
        topic = q.get('topic')
        if q.get('generatedFromDEOCrosswalk'):
            pool = 'deo-crosswalk-' + slug(qid)
        elif q.get('generatedFrom3dGraph'):
            pool = 'cost-3d-' + slug(qid)
        elif q.get('generatedFromHgabAllocation'):
            pool = 'hgab-project-' + q.get('hgabId', qid)
        elif q.get('easyMemberGroup'):
            pool = 'easy-member-' + slug(q['easyMemberGroup'])
        elif topic == 'flags' or kind in {'flag-scenario', 'deo-flag-count'} or qid.startswith('flag-'):
            pool = 'flags'
        elif topic == 'coverage':
            pool = 'documentation-coverage'
        elif topic == 'cost-per-meter' or kind == 'derivedBridgeRate':
            pool = 'bridge-cost-per-meter'
        elif topic == 'summary-leads':
            pool = 'summary-leads'
        elif topic == 'budget' or kind == 'hgab3-allocation':
            pool = 'budget-basics-' + slug(qid)
        else:
            pool = 'question-' + slug(qid)
        q['pool'] = pool
        q.pop('easyMemberGroup', None)


def main():
    bank = read(BANK)
    in_depth = read(IN_DEPTH)
    review = read(QUEUE)
    cost = read(COSTS)
    mpb = read(MPB)
    rcs = read(RCS)
    location = read(LOCATION)
    leaderboard = read(LEADERBOARD)
    hgab_project_source = read(HGAB3_PROJECTS)
    fmr_coordinates = read(FMR_COORDINATES)
    fmr_coordinate_audit = read(FMR_COORDINATE_AUDIT)
    mpb_coordinate_audit = read(MPB_COORDINATE_AUDIT)
    curated = current_curated(bank)
    update_curated(curated, in_depth['hgabCoverage'], review, cost, rcs, mpb, location)
    generated = generated_allocation_questions(hgab_project_source)
    new_facts = improvement_questions(hgab_project_source, in_depth, review, cost, mpb, rcs, location)
    geography = geography_questions(fmr_coordinates, fmr_coordinate_audit, mpb_coordinate_audit)
    graph_questions = road_bridge_3d_questions(cost)
    leaderboard_q = leaderboard_questions(leaderboard)
    deo_questions = deo_crosswalk_questions(leaderboard)
    bank['questions'] = curated + new_facts + geography + graph_questions + generated + leaderboard_q + deo_questions
    for question in bank['questions']:
        if not (question.get('generatedFromLeaderboard') or question.get('generatedFromMpbHistoricalGaa') or question.get('generatedFromGeographicEvidence') or question.get('generatedFromSummaryHero') or question.get('generatedFrom3dGraph') or question.get('generatedFromDEOCrosswalk') or question.get('generatedFromHgabAllocation') or question.get('generatedFromNationalBudget') or question.get('generatedFromBudgetGlossary')) and question.get('difficulty') != 'hard' and not question.get('finalChallenge'):
            question['difficulty'] = 'medium'
        if question.get('topic') == 'coverage':
            question['topic'] = 'summary-leads'
        if question.get('topic') == 'summary-leads':
            question['category'] = 'Summary leads'
        if question.get('topic') == 'budget':
            if question.get('stage') != STAGE:
                raise ValueError(f"Budget topic question is not scoped to {STAGE}: {question.get('id')}")
            question['category'] = 'HGAB 3rd'
    assign_question_pools(bank['questions'])
    bank['generatedFrom'] = {
        'stage': STAGE,
        'stageSource': 'HB 10858, General Appropriations Bill FY2027, third-reading extracted schedule; budget-topic project allocation questions use that HGAB 3rd source directly',
        'projectAllocationQuestions': len(generated),
        'projectQuestionMethod': '1,000 sampled project-level HGAB 3rd allocations from hb10858_3rd_dpwh_projects.json only: 300 text-answer project-title recall questions are medium; numeric amount questions with values divisible by ₱10 million are easy, other numeric amount questions are medium or hard based on numeric-choice dispersion; office and regional aggregate rows are excluded to avoid leaderboard duplication; no NEP data is used to select or answer these questions',
        'budgetTopicScope': 'Every topic=budget question is tagged with category HGAB 3rd and stage HGAB 3rd reading; allocation questions use the primary HGAB 3rd extracted schedule, not NEP data.',
        'projectAllocationQuestionCounts': {
            difficulty: sum(q['difficulty'] == difficulty for q in generated)
            for difficulty in ('easy', 'medium', 'hard')
        },
        'coverageSnapshotRetrievedAt': SNAPSHOT_DATE,
        'leaderboardSource': 'https://budget.bettergov.ph/hgab/2027/leaderboard',
        'leaderboardBuiltAt': leaderboard['built_at'],
        'leaderboardQuestionCounts': {
            category: {difficulty: sum(q.get('category')==category and q.get('difficulty')==difficulty for q in leaderboard_q)
                       for difficulty in ('easy','medium','hard')}
            for category in ('2027 House bill','Enacted budget history','House members')
        },
        'leaderboardQuestions': len(leaderboard_q),
        'geographyQuestions': len(geography),
        'costPerMeter3dQuestions': len(graph_questions),
        'costPerMeter3dQuestionCounts': {
            category: {difficulty: sum(q['category'] == category and q['difficulty'] == difficulty for q in graph_questions)
                       for difficulty in ('easy', 'medium', 'hard')}
            for category in ('Roads', 'Bridges')
        },
        'deoCrosswalkQuestions': len(deo_questions),
        'deoCrosswalkQuestionCounts': {
            difficulty: sum(q['difficulty'] == difficulty for q in deo_questions)
            for difficulty in ('easy', 'medium', 'hard')
        },
        'coverageScope': 'HGAB 3rd line items linked to the retained DPWH Transparency NEP metadata snapshot; absent listing is not proof of absent documents',
        'difficultyPolicy': 'Difficulty follows the work a player must do, not answer format alone: the fixed national-budget opener, basic budget-stage definitions, and simple representative lookups are easy; specific title/rank/value lookups and contextual facts are medium; multi-step calculations, tight numeric choices, and obscure low-count member identification are hard.',
        'removedQuestionFamilies': ['NEP department proposals', 'NEP POW amounts and quantities', 'NEP POW signatories', 'unscoped representative and DEO crosswalk lookup questions', 'unscoped party-list roster questions'],
        'currentHGABQuestions': len(curated) + len(new_facts) + len(geography),
        'questionsTotal': len(bank['questions']),
    }
    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'retainedHGABQuestions': len(curated), 'newHGABFacts': len(new_facts),
                      'convertedProjectAllocationQuestions': len(generated),
                      'leaderboardQuestions': len(leaderboard_q),
                      'geographyQuestions': len(geography),
                      'costPerMeter3dQuestions': len(graph_questions),
                      'deoCrosswalkQuestions': len(deo_questions),
                      'totalQuestions': len(bank['questions'])}, indent=2))


if __name__ == '__main__':
    main()
