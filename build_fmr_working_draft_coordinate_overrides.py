#!/usr/bin/env python3
"""Extract explicit DA/GPS FMR coordinate corrections from the November draft."""
from __future__ import annotations
import json, re, math, hashlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRAFT = ROOT / 'analysis_output/fmr-nov5-working-draft.json'
LEDGER = ROOT / 'analysis_output/fmr_corrected_dataset.json'
OUT = ROOT / 'data_sources/fmr_analyst/hgab_fmr_working_draft_coordinate_overrides.json'
AUDIT = ROOT / 'analysis_output/fmr-working-draft-coordinate-audit.json'
SOURCE_XLSX = next((ROOT / 'data_sources').glob('Working Draft as of Nov 5*.xlsx'))

def norm(value: str) -> str:
    return ''.join(re.findall(r'[a-z0-9]+', value.casefold()))

def gap_m(a: list[float], b: list[float]) -> float:
    lat1, lon1 = a[1], a[0]
    lat2, lon2 = b[1], b[0]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, h)))

def points_in_label(label: str) -> list[list[float]]:
    pairs = re.findall(r'(?<![A-Za-z0-9])(\d{1,3}(?:\.\d+)?)\s*[NnSs]?\s*,\s*(\d{1,3}(?:\.\d+)?)\s*[EeWw]?', label)
    points=[]
    for first, second in pairs:
        lat, lon = float(first), float(second)
        if abs(lat) > 90 and abs(lon) <= 90:
            lat, lon = lon, lat
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f'Coordinate outside valid lat/lon ranges: {first}, {second}')
        points.append([lon, lat])
    return points

def main() -> None:
    projects = json.loads(LEDGER.read_text())['projects']
    by_title=defaultdict(list)
    for project in projects:
        by_title[norm(project['title'])].append(project)
    draft=json.loads(DRAFT.read_text())
    # DA changed the Kirayan Tacas–Pungtod Naulid connector from a dash to
    # the word “to”; preserve this one documented identity match explicitly.
    title_aliases = {'R6-NEW-0004': 'ib:p709:r14'}
    overrides=[]; audit=[]
    for record in draft['records']:
        remark=str(record.get('remarks') or '')
        if not re.search(r'coordinate', remark, re.I):
            continue
        text=str(record.get('to') or '')
        title=text.splitlines()[0].strip()
        starts=[]; ends=[]
        for line in text.splitlines():
            if re.match(r'\s*START\s*:', line, re.I): starts=points_in_label(line)
            elif re.match(r'\s*END\s*:', line, re.I): ends=points_in_label(line)
        row={'draftRow':record.get('row'),'control':record.get('control'),'title':title,
             'remark':remark,'matchedProjectIds':[],'status':'unmatched'}
        matches=by_title.get(norm(title),[])
        if not matches and record.get('control') in title_aliases:
            matches=[p for p in projects if p['project_id']==title_aliases[record['control']]]
        if not matches:
            audit.append(row); continue
        row['matchedProjectIds']=[p['project_id'] for p in matches]
        if len(matches)!=1:
            row['status']='ambiguous-title-match'; audit.append(row); continue
        if not starts or len(starts)!=len(ends):
            row['status']='coordinate-sections-need-review'; audit.append(row); continue
        project=matches[0]
        old=project.get('coordinates') or []
        old_points=[point for segment in old for point in segment if point]
        new_segments=[[start,end] for start,end in zip(starts,ends)]
        new_points=[point for segment in new_segments for point in segment]
        gap_before=gap_m(old_points[0],old_points[-1]) if len(old_points)>1 else None
        gap_after=gap_m(new_points[0],new_points[-1]) if len(new_points)>1 else None
        overrides.append({
            'projectId':project['project_id'],'title':project['title'],
            'replacementCoordinates':new_segments,
            'source':{'file':str(SOURCE_XLSX.relative_to(ROOT)),'sheet':'Draft',
                      'derivedRecordFile':'analysis_output/fmr-nov5-working-draft.json',
                      'draftRow':record.get('row'),'control':record.get('control'),'remark':remark},
            'oldCoordinateGapMeters':round(gap_before,1) if gap_before is not None else None,
            'correctedCoordinateGapMeters':round(gap_after,1) if gap_after is not None else None,
            'coordinateBasis':'Working Draft coordinate correction per DA evaluation / GPS survey',
        })
        row.update(status='matched-and-parsed',oldCoordinateGapMeters=round(gap_before,1) if gap_before is not None else None,
                   correctedCoordinateGapMeters=round(gap_after,1) if gap_after is not None else None)
        audit.append(row)
    payload={'source':{'file':str(SOURCE_XLSX.relative_to(ROOT)),'sheet':'Draft',
                       'sha256':hashlib.sha256(SOURCE_XLSX.read_bytes()).hexdigest()},
             'sourceNote':'Working Draft coordinate-correction remarks, parsed to analysis_output/fmr-nov5-working-draft.json.',
             'method':'Apply only correction rows with an exact normalized title match to one FMR ledger project and parseable START/END coordinate pairs. Preserve original ledger coordinates; these are a separate correction overlay.',
             'overrides':overrides}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    AUDIT.write_text(json.dumps({'summary':{'coordinateCorrectionRows':len(audit),'appliedOverrides':len(overrides),
        'matchedRowsOver20kmBefore':sum((r.get('oldCoordinateGapMeters') or 0)>20000 for r in overrides),
        'matchedRowsOver20kmAfter':sum((r.get('correctedCoordinateGapMeters') or 0)>20000 for r in overrides),
        'unmatched':sum(r['status']=='unmatched' for r in audit),
        'ambiguous':sum(r['status']=='ambiguous-title-match' for r in audit),
        'sectionsNeedingReview':sum(r['status']=='coordinate-sections-need-review' for r in audit)},
        'rows':audit},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'overrides':len(overrides),'summary':json.loads(AUDIT.read_text())['summary']},indent=2))

if __name__=='__main__': main()
