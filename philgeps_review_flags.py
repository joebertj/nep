"""Attach source-linked budget and procurement checks to verified notices."""
from collections import defaultdict
from decimal import Decimal


def attach_flags(notices, scr_rows, existing, title_key):
    scr_by_title = defaultdict(dict)
    for row in scr_rows:
        for title in (row['title'], row['house_title']):
            if title:
                scr_by_title[title_key(title)][row['id']] = row
    hgab_flags = {row['hgabId']: row for row in existing}

    for notice in notices:
        flags = []
        budget = notice['budget']
        if notice.get('epaWording') is False:
            flags.append({'label': 'EPA wording needs review',
                          'evidence': 'The notice text cites FY2027 funding. The crawl did not locate explicit EPA wording in the notice text. Check the bidding documents and approved indicative APP.',
                          'url': notice['url']})
        if notice.get('related'):
            flags.append({'label': 'Different project segment',
                          'evidence': 'The invitation and the nearby NEP line state disjoint chainage ranges. Check the corrected schedule for a funding link.',
                          'url': notice['url']})
        if not budget and not notice.get('related'):
            flags.append({'label': 'Budget match unestablished',
                          'evidence': 'Check the notice title, project scope and location against the FY2027 budget schedules.',
                          'url': notice['url']})
        if budget and not any(line['stage'] == 'SCR' for line in budget):
            trace = {}
            for line in budget:
                trace.update(scr_by_title[title_key(line['title'])])
            if len(trace) == 1 and (source := next(iter(trace.values())))['status'] in {'cut', 'nep_only'}:
                label, evidence = (
                    ('Removed in the SCR crosswalk', 'The retained stage crosswalk records a zero Senate allocation.')
                    if source['status'] == 'cut' else
                    ('NEP-only line in the stage crosswalk', 'The retained crosswalk found no House or Senate counterpart. Check the latest funding schedule before award.')
                )
                flags.append({'label': label, 'evidence': evidence, 'url': source['page_url']})
            else:
                flags.append({'label': 'SCR funding link needs review',
                              'evidence': 'The available SCR extract has no exact matched title. Check for changes in title, scope or funding.',
                              'url': 'scr.html'})

        for stage in ('SCR', 'HGAB', 'NEP'):
            stage_lines = [line for line in budget if line['stage'] == stage and (line['amount'] or 0) > 0]
            if not stage_lines:
                continue
            amounts = {line['amount'] for line in stage_lines}
            if len(amounts) == 1 and (amount := next(iter(amounts))) < Decimal(str(notice['abc'])):
                flags.append({'label': 'ABC above matched proposed allocation',
                              'evidence': f'The notice ABC exceeds the matched {stage} amount of ₱{amount:,}. Check the approved indicative APP for the applicable ceiling.',
                              'url': stage_lines[0]['url']})
            break

        recorded = set()
        for line in budget:
            source = hgab_flags.get(line['id']) if line['stage'] == 'HGAB' else None
            if not source or source['amountPesos'] != line['amount'] or title_key(source['title']) != title_key(line['title']):
                continue
            evidence_by_label = {item['label']: item['evidence'] for item in source['detailedFlagEvidence']}
            for label in source['existingReviewFlags']:
                if label in recorded:
                    continue
                recorded.add(label)
                evidence = (evidence_by_label.get(label) if label.startswith('No listed ') else None)
                flags.append({'label': label, 'evidence': evidence or 'See the linked HGAB project review and its supporting evidence.',
                              'url': 'flags.html', 'sourceId': line['id']})
        notice['flags'] = flags
