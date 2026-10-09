"""Read the visible DPWH I-C table, preserving its printed hierarchy.

Ghostscript exports off-page InDesign spread text. Crop before reconstructing
rows; never deduplicate legitimate budget occurrences by title or amount.
"""
from __future__ import annotations

from collections import Counter
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

PROGRAMS = {
    'Asset Preservation Program', 'Network Development Program', 'Bridge Program',
    'Flood Management Program', 'Convergence and Special Support Program',
    'National Building Program', 'Local Program', 'FOREIGN-ASSISTED PROJECTS',
    'CONVERGENCE AND SPECIAL SUPPORT PROGRAM', 'LOCALLY-FUNDED PROJECTS',
}
REGION = re.compile(r'^(?:Region\s+[IVX]+(?:-[AB])?|National Capital Region|Cordillera Administrative Region|MIMAROPA(?: Region)?|Negros Island Region|Bangsamoro Autonomous Region.*|BARMM|CAR)$', re.I)
OFFICE = re.compile(r'(?:District Engineering Office|\bDEO\b|Regional Office|Central Office)', re.I)


def page_boxes(gs: str, pdf: Path) -> list[list[float]]:
    # The filename is PostScript data, not shell code.
    name = str(pdf.resolve()).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    code = f'({name}) (r) file runpdfbegin 1 1 pdfpagecount {{pdfgetpage dup /CropBox known {{/CropBox get}} {{/MediaBox get}} ifelse ==}} for quit'
    result = subprocess.run([gs, '-q', '-dNOSAFER', '-dNODISPLAY', '-c', code], capture_output=True, text=True, check=True)
    return [[float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', line)] for line in result.stdout.splitlines() if line.startswith('[')]


def visible_rows(xml: str, box: list[float]) -> tuple[list[dict], int]:
    xml = re.sub(r'&#(x[0-9a-fA-F]+|\d+);', lambda m: m[0] if (lambda n: n in (9,10,13) or 32 <= n <= 0xD7FF or 0xE000 <= n <= 0xFFFD)(int(m[1][1:],16) if m[1].startswith('x') else int(m[1])) else '', xml)
    root = ET.fromstring(xml)
    fragments, outside = [], 0
    # txtwrite uses top-down y coordinates. These editions have no rotation.
    left, bottom, right, top = box
    for line in root.iter('line'):
        chars = []
        fonts = [span.get('font', '') for span in line.iter('span')]
        for char in line.iter('char'):
            b = list(map(float, char.get('bbox').split()))
            if left <= (b[0]+b[2])/2 <= right and bottom <= b[1] <= top:
                chars.append((b[0], b[1], b[2], char.get('c','')))
            else:
                outside += 1
        if chars and ''.join(c[3] for c in chars).strip():
            spans=list(line.iter('span'))
            fragments.append({'chars': chars, 'y': sum(c[1] for c in chars)/len(chars), 'bold': any('Bold' in f for f in fonts), 'fontSize':float(spans[0].get('size','8.4661')) if spans else 8.4661})
    amount_headers = [f for f in fragments if re.fullmatch(r'AMOUNT\s*\(Php\)', ''.join(c[3] for c in f['chars']).strip(), re.I)]
    if not amount_headers:
        return [], outside
    header = amount_headers[0]
    amount_x = min(c[0] for c in header['chars']) - 23
    indent_scale = 8.4661 / header['fontSize']
    groups = []
    for f in sorted(fragments, key=lambda f: f['y']):
        if f['y'] <= header['y']+10 or f['y'] > top-40:
            continue
        if not groups or abs(groups[-1]['y']-f['y']) > 6:
            groups.append({'y': f['y'], 'fragments': []})
        groups[-1]['fragments'].append(f)
    rows = []
    for group in groups:
        title_parts, numbers, xs, bold = [], [], [], False
        seen_fragments = set()
        for f in sorted(group['fragments'], key=lambda f: min(c[0] for c in f['chars'])):
            chars = f['chars']
            s = ''.join(c[3] for c in chars).strip()
            fragment_key = (round(min(c[0] for c in chars)), s)
            if fragment_key in seen_fragments:
                continue
            seen_fragments.add(fragment_key)
            # A separate numeric fragment, including broken thousands groups,
            # belongs to the amount field regardless of embedded whitespace.
            if min(c[0] for c in chars) >= amount_x and re.fullmatch(r'[\d,\s]+', s):
                numbers.append(s)
                continue
            # Some PDF lines contain both description and amount; their long
            # whitespace run is the actual table boundary.
            match = re.search(r'\s{5,}([\d,\s]+)$', ''.join(c[3] for c in chars))
            if match:
                original = ''.join(c[3] for c in chars)
                s = original[:match.start()].strip()
                numbers.append(match[1])
            if s:
                title_parts.append(s)
                xs.append(min(c[0] for c in chars if c[3].strip()))
                bold |= f['bold']
        title = re.sub(r'\s+', ' ', ' '.join(title_parts)).strip()
        numeric = re.sub(r'\s+', '', ''.join(numbers))
        amount = int(numeric.replace(',','')) if re.fullmatch(r'\d{1,3}(?:,\d{3})+', numeric) else None
        if title or numeric:
            rows.append({'title': title, 'amount': amount, 'amountText': numeric, 'indent': (min(xs)-amount_x)*indent_scale if xs else None, 'bold': bold, 'y': round(group['y'],2)})
    return rows, outside


def extract_visible(pdf: Path, page_files: list[Path], boxes: list[list[float]]) -> tuple[list[dict], dict]:
    nodes, current, active, outside = [], None, False, 0
    issues = []
    def flush():
        nonlocal current
        if current:
            current['title'] = re.sub(r'\s+', ' ', ' '.join(current.pop('parts'))).strip()
            nodes.append(current)
            current = None
    for page, (file, box) in enumerate(zip(page_files, boxes),1):
        rows, excluded = visible_rows(file.read_text(encoding='utf-8',errors='replace'), box)
        outside += excluded
        for row in rows:
            title = row['title']
            if title in PROGRAMS:
                active = True
            if not active:
                continue
            clean = re.sub(r'^\s*(?:[a-zA-Z]|\d+)[.)]\s*', '', title).strip()
            new_heading = bool(REGION.fullmatch(clean) or OFFICE.search(clean) and row['amount'] is not None or row['bold'])
            if current and current['bold'] and row['bold'] and row['amount'] is None and abs((row['indent'] or 0)-(current['indent'] or 0)) <= 20:
                current['parts'].append(title)
                continue
            if row['amount'] is not None or new_heading:
                flush()
                current = {**row, 'parts': [title], 'page': page, 'pages': [page]}
            elif current and not current['bold'] and title and row['indent'] is not None and current['indent'] is not None and abs(row['indent']-current['indent']) <= 20:
                current['parts'].append(title)
                if page not in current['pages']:
                    current['pages'].append(page)
            elif row['amountText']:
                issues.append({'page':page, **row})
    flush()
    stack, records, controls = [], [], []
    program, region, office, last_pap = '', '', '', ''
    for index, node in enumerate(nodes):
        # Single initial + surname is part of the name (G. Araneta, P.
        # Florentino); strip list markers only in numbered FAP tables.
        title = re.sub(r'^\s*(?:[a-zA-Z]|\d+)[.)]\s*', '', node['title']).strip() if program=='FOREIGN-ASSISTED PROJECTS' else node['title']
        if node['indent'] is None:
            issues.append({'reason':'amount without title', **node})
            continue
        while stack and stack[-1]['indent'] >= node['indent']-3:
            stack.pop()
        if node['title'] in PROGRAMS:
            program = {'CONVERGENCE AND SPECIAL SUPPORT PROGRAM':'Convergence and Special Support Program',
                       'LOCALLY-FUNDED PROJECTS':'Local Program'}.get(node['title'],node['title'])
            if node['title']=='National Building Program' and any(n['title']=='LOCALLY-FUNDED PROJECTS' for n in stack):
                program = 'Local Program'
            region, office = '', ''
            last_pap = ''
        is_region = bool(REGION.fullmatch(title))
        is_office = bool(re.fullmatch(r'.*(?:District Engineering Office|DEO|Regional Office(?:\s+(?:[IVX]+|MIMAROPA Region))?|Central Office)',title,re.I)) and not re.match(r'^(?:Construction|Rehabilitation|Improvement|Completion|Repair|Installation)\b',title,re.I)
        if is_region:
            region = 'MIMAROPA' if title.startswith('MIMAROPA') else 'CAR' if title.startswith('Cordillera') else 'BARMM' if title.startswith('Bangsamoro') else title
            # NCR/Central Office is an implementing branch for the following
            # geographically identified projects. Subsequent regions inherit
            # Central Office only within this same PAP, never a prior DEO.
            office = 'Central Office' if any(n['title']=='Central Office' for n in stack) else ''
        if is_office:
            office = title
        if node['bold']:
            region, office = '', ''
        next_node = nodes[index+1] if index+1<len(nodes) else None
        has_children = bool(next_node and next_node['indent'] is not None and next_node['indent'] > node['indent']+3)
        ancestors = [n for n in stack if n['bold'] and n['title'] not in PROGRAMS]
        ancestors = [n for n in ancestors if n['title'] not in {'Multipurpose / Facilities','National Roads','National Roads and Bridges'}]
        pap = re.sub(r'^(?:[a-zA-Z]|\d+)[.)]\s*','',ancestors[-1]['title']) if ancestors else last_pap
        if program=='FOREIGN-ASSISTED PROJECTS':
            pap = 'Foreign-assisted projects (FAP)'
        if node['bold'] and node['amount'] is not None:
            controls.append({'title':node['title'], 'program':program, 'amountPesos':node['amount'], 'page':node['page'], 'indent':node['indent']})
        funding_row = bool(re.match(r'^(?:GOP|Loan Proceeds)\b',title))
        fap_project = program=='FOREIGN-ASSISTED PROJECTS' and not node['bold'] and has_children and next_node and re.match(r'^(?:GOP|Loan Proceeds)\b',next_node['title'])
        structural_parent = has_children and (is_office or is_region or title=='Nationwide' or program=='FOREIGN-ASSISTED PROJECTS')
        if node['amount'] is not None and not node['bold'] and (not structural_parent or fap_project) and not funding_row:
            name = title
            if is_office:
                # Flat office allocations (e.g. RCS) are real leaves, not totals.
                name = f'{pap} - {title}'
            if is_region:
                name = f'{pap} - {title}'
            record_id = f'HB10858-{pdf.stem[:1]}-{node["page"]:04d}-{len(records)+1:06d}'
            records.append({'id':record_id,'code':record_id,'fiscalYear':2027,'region':region,'office':office,
                'projectName':name,'pap1':program,'pap2':'','pap3':pap,'amount':node['amount']/1000,
                'amountPesos':node['amount'],'documentCount':1,'sourceVolume':pdf.name,
                'sourcePage':node['page'],'sourcePages':node['pages'],'sourceText':node['title']+'\t'+str(node['amount']),
                'sourceIndent':node['indent'],'sourceY':node['y'],'reviewStatus':'visible native text; project matching remains provisional'})
            records[-1]['sourceTitle'] = title
            records[-1]['allocationKind'] = 'foreign-assisted project' if fap_project else 'office allocation' if is_office else 'regional allocation' if is_region else 'project'
            records[-1]['zone'] = 'fap' if fap_project else 'local'
            last_pap = pap
        stack.append(node)
    program_controls = {}
    control_names = {'CONVERGENCE AND SPECIAL SUPPORT PROGRAM':'Convergence and Special Support Program',
                     'LOCALLY-FUNDED PROJECTS':'Local Program'}
    for control in controls:
        label=control_names.get(control['title'],control['title'])
        if label in {r['pap1'] for r in records} and control['title'] in PROGRAMS:
            program_controls[label]=control['amountPesos']
    reconciliation=[]
    for label, printed in program_controls.items():
        extracted=sum(r['amountPesos'] for r in records if r['pap1']==label)
        reconciliation.append({'program':label,'printedPesos':printed,'extractedPesos':extracted,'differencePesos':extracted-printed})
    if len(reconciliation)!=7 or any(r['differencePesos'] for r in reconciliation) or issues:
        raise ValueError('HGAB extraction failed printed program reconciliation: '+json.dumps({'programs':reconciliation,'issues':issues},ensure_ascii=False))
    return records, {'offPageCharactersExcluded':outside,'visibleHierarchyRows':len(nodes),
        'candidateRows':len(records),'allocationPesos':sum(r['amountPesos'] for r in records),
        'programCounts':dict(Counter(r['pap1'] for r in records)),'programReconciliation':reconciliation,
        'papControls':controls,'unresolvedExtractionRows':issues}
