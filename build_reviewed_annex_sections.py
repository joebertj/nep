#!/usr/bin/env python3
"""Render reviewed NIA/HFEP annex comparisons for their owning page builders."""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data_sources/csiiiv'
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def _esc(value):
    return html.escape(str(value), quote=True)


def _table(headers, rows):
    head = ''.join(f'<th>{_esc(value)}</th>' for value in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{_esc(value)}</td>' for value in row) + '</tr>' for row in rows)
    return f'<div class="evidence-table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _graph(rows):
    maximum = max([value for row in rows for value in row[1:3]] + [1])
    svg = '<figure><figcaption>NEP: blue · HGAB: yellow. Numbered groups correspond to table rows.</figcaption><svg class="evidence-graphic" viewBox="0 0 1100 330" role="img" aria-label="NEP versus HGAB reviewed annex controls">'
    step = 960 / max(len(rows), 1)
    for i, row in enumerate(rows):
        x = 60 + i * step
        for offset, value, color in [(0, row[1], '#0038A8'), (step * .35, row[2], '#FCD116')]:
            height = 210 * value / maximum
            svg += f'<rect x="{x+offset:.2f}" y="{245-height:.2f}" width="{step*.3:.2f}" height="{height:.2f}" fill="{color}"><title>{_esc(row[0])} · ₱{value:,}</title></rect>'
        svg += f'<text x="{x}" y="275">{i+1}</text>'
    return svg + '</svg></figure>'


def _read_inputs():
    policy_path = BASE / 'source_policy.json'
    if not policy_path.exists():
        raise FileNotFoundError(f'Reviewed annex source policy missing: {policy_path}')
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    accepted = BASE / 'accepted'
    def read(name):
        return json.loads((accepted / name).read_text(encoding='utf-8'))
    return policy, read('nep_nia_dataset.json'), read('hgab_nia_tree.json'), read('nep_hfep_data_list.json'), read('hgab_hfep_data_list.json')


def build_baseline_asset():
    """Write the shared source-data download from the refresh orchestrator."""
    policy, nia, house, hfep_nep, hfep_house = _read_inputs()
    data = {'sourcePolicy': policy, 'nia': {'nep': nia, 'house': house}, 'hfep': {'nep': hfep_nep, 'house': hfep_house}}
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    (OUT / 'reviewed_annex_baselines.json').write_text(serialized, encoding='utf-8')
    (STATIC / 'reviewed-annex-baselines.json').write_text(serialized, encoding='utf-8')
    return {'asset': 'reviewed-annex-baselines.json', 'niaProjects': len(nia['projects']), 'hfepFacilities': len(hfep_nep['items'])}


def _upsert(page, identifier, section):
    opening = re.search(rf'<section\b(?=[^>]*\bid=["\']{re.escape(identifier)}["\'])[^>]*>', page, re.I)
    if opening:
        depth = 0
        for token in re.finditer(r'</?section\b[^>]*>', page[opening.start():], re.I):
            if token.group(0).lower().startswith('</'):
                depth -= 1
                if depth == 0:
                    end = opening.start() + token.end()
                    return page[:opening.start()] + section + page[end:]
            else:
                depth += 1
        raise ValueError(f'Unclosed generated section {identifier}')
    if '</main>' not in page:
        raise ValueError('Owning page has no closing main element')
    return page.replace('</main>', section + '</main>', 1)


def _nia_section(policy, nia, house):
    controls = {row['label']: row['printed_amount_php'] for row in house['nodes'] if row['kind'] == 'subprogram_control'}
    rows = []
    for row in nia['sub_programs']:
        label = 'Extension/Expansion of Existing Irrigation System Sub-Program' if row['sub_program'] == 'Extension/Expansion' else row['sub_program'] + ' Sub-Program'
        rows.append([row['sub_program'], row['control_amount'], controls[label], controls[label] - row['control_amount']])
    credits = f'<p>Preferred extraction: <a href="https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/">csiiiv budget-analysis workbench</a> · <a href="{_esc(policy["source"] + "/tree/" + policy["commit"])}">pinned source revision</a>. Documented human corrections take priority over the older automated extraction. Raw titles, repair history, unresolved flags and source identifiers are preserved. This does not claim that every row was individually image-reviewed.</p>'
    downloads = '<p><a href="reviewed-annex-baselines.json" download>Download accepted NEP/HGAB annex rows and provenance (JSON)</a> · <a href="reviewed-source-adoption.json" download>Source adoption and reading-equivalence record</a></p>'
    projects = nia['projects']
    house_rows = [row for row in house['nodes'] if row['kind'] == 'project']
    nep_total = sum(row['amount_php'] for row in projects)
    house_total = sum(row['printed_amount_php'] for row in house_rows)
    body = credits + f'<p>Compare the same printed irrigation sub-programs: NEP {len(projects):,} rows / ₱{nep_total:,}; HGAB {len(house_rows):,} rows / ₱{house_total:,}. Net adjustment: ₱{house_total-nep_total:,}. The old 423-row local extraction missed part of the annex; correcting that extraction is not a legislative insertion. Named major NIA projects are a separate scope.</p>'
    body += _graph(rows) + _table(['Sub-program', 'NEP allocation pesos', 'HGAB allocation pesos', 'Allocation adjustment pesos'], rows)
    body += '<p>Controls are directly comparable at sub-program level. The difference in project counts does not identify individual insertions or removals. Annex text equivalence between the local House readings is preserved in the adoption record.</p>' + downloads
    return f'<section id="reviewed-nia-controls" class="investigation-evidence"><h2>Reviewed irrigation annex · NEP → HGAB 3rd reading</h2>{body}</section>'


def _hfep_section(policy, nep, house):
    n = nep['document']['verification']['summary']
    h = house['document']['verification']['summary']
    rows = []
    for label, key in [('Infrastructure', 'infrastructure'), ('Medical equipment', 'medical_equipment'), ('Motor vehicles', 'motor_vehicle')]:
        a = sum(row['amounts_php'].get(key, 0) for row in nep['items'])
        b = sum(row['amounts_php'].get(key, 0) for row in house['items'])
        rows.append([label, a, b, b-a])
    a = n['facility_ledger_total_php']; b = h['facility_ledger_total_php']
    rows.append(['Facility-ledger total', a, b, b-a])
    credits = f'<p>Preferred extraction: <a href="https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/">csiiiv budget-analysis workbench</a> · <a href="{_esc(policy["source"] + "/tree/" + policy["commit"])}">pinned source revision</a>. Documented human corrections take priority over the older automated extraction. Raw titles, repair history, unresolved flags and source identifiers are preserved. This does not claim that every row was individually image-reviewed.</p>'
    downloads = '<p><a href="reviewed-annex-baselines.json" download>Download accepted NEP/HGAB annex rows and provenance (JSON)</a> · <a href="reviewed-source-adoption.json" download>Source adoption and reading-equivalence record</a></p>'
    body = credits + f'<p>The accepted detailed baseline contains {n["facilities"]} NEP facilities and {h["facilities"]} House facilities. The NEP printed control exceeds its facility ledger by ₱{n["grand_total_php"]-a:,}; the source discrepancy is preserved and is not assigned to a fabricated facility. Funding columns below sum facility records only.</p>'
    body += _graph(rows) + _table(['Funding type', 'NEP facility allocation pesos', 'HGAB facility allocation pesos', 'Allocation adjustment pesos'], rows)
    nc = {row['label']: row['amounts_php']['total'] for row in nep['controls'] if row['kind'] == 'category_control'}
    hc = {row['label']: row['amounts_php']['total'] for row in house['controls'] if row['kind'] == 'category_control'}
    categories = [[label, nc.get(label, 0), hc.get(label, 0), hc.get(label, 0)-nc.get(label, 0)] for label in sorted(set(nc) | set(hc))]
    body += '<h3>Facility categories · retained source controls</h3><p>A category absent from an annex contributes zero to this ledger comparison; it does not establish zero funding outside the annex. Opposing changes do not prove a direct transfer or service consequences.</p>' + _graph(categories) + _table(['Category', 'NEP allocation pesos', 'HGAB allocation pesos', 'Allocation adjustment pesos'], categories) + downloads
    return f'<section id="reviewed-hfep-annex" class="investigation-evidence"><h2>Reviewed HFEP facility annex · NEP → HGAB 3rd reading</h2>{body}</section>'


def apply_page(page, page_name):
    """Render the reviewed annex section for one supplied page; never write HTML."""
    policy, nia, house, hfep_nep, hfep_house = _read_inputs()
    if page_name == 'nia-irrigation.html':
        identifier, section = 'reviewed-nia-controls', _nia_section(policy, nia, house)
    elif page_name == 'hfep.html':
        identifier, section = 'reviewed-hfep-annex', _hfep_section(policy, hfep_nep, hfep_house)
    else:
        return page
    page = _upsert(page, identifier, section)
    if f'href="#{identifier}"' not in page:
        link = f'<p class="reviewed-annex-jump"><a href="#{identifier}">Reviewed NEP → HGAB annex comparison ↓</a></p>'
        page = page.replace('</header>', link + '</header>', 1)
    return page
