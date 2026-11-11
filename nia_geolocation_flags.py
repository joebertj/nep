"""Build location-quality evidence from the dated NIA geolocation workbook."""
from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
WORKBOOK = ROOT / 'data_sources' / '2026-11-10--with geolocation_bettergov-house-bill-2027-nia-projects.xlsx'
PSGC_PATH = ROOT / 'data_sources' / 'bettergov-psgc-locations.jsonl'
OUT = ROOT / 'analysis_output' / 'nia_geolocation_audit.json'
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _column_index(ref: str) -> int:
    value = 0
    for char in re.match(r'[A-Z]+', ref).group(0):
        value = value * 26 + ord(char) - 64
    return value - 1


def _workbook_rows() -> list[dict[str, str]]:
    with ZipFile(WORKBOOK) as book:
        shared_root = ET.fromstring(book.read('xl/sharedStrings.xml'))
        shared = [''.join(t.text or '' for t in item.findall('.//m:t', NS))
                  for item in shared_root.findall('m:si', NS)]
        sheet = ET.fromstring(book.read('xl/worksheets/sheet2.xml'))
    rows = sheet.findall('.//m:sheetData/m:row', NS)
    if not rows:
        return []

    def unpack(row: ET.Element) -> list[str]:
        cells = row.findall('m:c', NS)
        values = [''] * (max((_column_index(c.attrib['r']) for c in cells), default=-1) + 1)
        for cell in cells:
            value = cell.find('m:v', NS)
            text = value.text if value is not None else ''
            if cell.attrib.get('t') == 's' and text:
                text = shared[int(text)]
            values[_column_index(cell.attrib['r'])] = text
        return values

    headers = unpack(rows[0])
    return [dict(zip(headers, unpack(row))) for row in rows[1:]]


def _normal(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', value.lower())


def build() -> dict:
    records = _workbook_rows()
    places = {item['code']: item for item in
              (json.loads(line) for line in PSGC_PATH.read_text(encoding='utf-8').splitlines() if line.strip())}
    granularity: Counter[str] = Counter()
    review_rows = []
    located = 0
    valid_codes = 0
    name_mismatch_count = 0
    hierarchy_mismatch_count = 0
    rows_with_length = sum(bool((row.get('length_m') or '').strip()) for row in records)
    # The workbook's structured length field is blank, but some project titles
    # contain chainage or length text. Preserve these as leads, not normalized
    # measurements, because one title can describe multiple work components.
    chainage_pattern = re.compile(r'\bsta\.?\s*\d+(?:\.\d+)?\s*[+\-–]\s*\d+(?:\.\d+)?', re.I)
    stated_length_pattern = re.compile(r'\b\d+(?:\.\d+)?\s*(?:km|kilomet(?:er|re)s?|meters?|metres?)\b', re.I)
    coordinate_pattern = re.compile(
        r'\b\d{1,2}\.\d{4,}\s*[,/]\s*\d{2,3}\.\d{4,}\b|'
        r'\b\d{1,2}°\s*\d{1,2}[′\']\s*\d{1,2}(?:\.\d+)?[″\"]?\s*[NS].{0,20}'
        r'\b\d{2,3}°\s*\d{1,2}[′\']\s*\d{1,2}(?:\.\d+)?[″\"]?\s*[EW]', re.I)
    station_range_pattern = re.compile(
        r'(?i)(?:\bSTA\.?\s*)?(\d{1,3})\s*\+\s*(\d{1,3}(?:\.\d+)?)\s*'
        r'(?:TO|[-–])\s*(?:STA\.?\s*)?(\d{1,3})\s*\+\s*(\d{1,3}(?:\.\d+)?)')
    title_chainage_rows = sum(bool(chainage_pattern.search(row.get('title') or '')) for row in records)
    title_stated_length_rows = sum(bool(stated_length_pattern.search(row.get('title') or '')) for row in records)
    title_coordinate_rows = sum(bool(coordinate_pattern.search(row.get('title') or '')) for row in records)
    station_range_candidates = []
    for row in records:
        lengths = []
        for match in station_range_pattern.finditer(row.get('title') or ''):
            start = int(match[1]) * 1000 + float(match[2])
            end = int(match[3]) * 1000 + float(match[4])
            if 0 <= start <= 500_000 and 0 <= end <= 500_000 and start != end:
                lengths.append(round(abs(end - start), 2))
        if not lengths:
            continue
        raw_amount = (row.get('hgab3_php') or '').strip()
        amount = float(raw_amount) if raw_amount else None
        total_length = round(sum(lengths), 2)
        station_range_candidates.append({
            'id': row.get('id', ''),
            'title': row.get('title', ''),
            'category': row.get('program', '').strip() or 'Uncategorized',
            'programLine': row.get('pap', '').strip(),
            'sourcePage': row.get('hgab3_page') or re.search(r'ib:p(\d+)', row.get('id', '')).group(1) if re.search(r'ib:p(\d+)', row.get('id', '')) else row.get('hgab3_page', ''),
            'amountPesos': amount,
            'segmentLengthsM': lengths,
            'segmentCount': len(lengths),
            'totalStationRangeM': total_length,
            'screeningPesosPerMeter': round(amount / total_length, 2) if amount is not None and amount > 0 else None,
        })
    for row in records:
        raw_code = (row.get('10-digit PSGC') or '').strip()
        if not raw_code:
            continue
        located += 1
        code = raw_code.zfill(10)
        place = places.get(code)
        if not place:
            review_rows.append({
                'id': row.get('id', ''), 'title': row.get('title', ''),
                'name': row.get('Name', ''), 'municipality': row.get('City/Municipality', ''),
                'province': row.get('Province', ''), 'psgc': raw_code,
                'referencePlace': 'No exact match in the current PSGC reference list',
                'issue': 'Provided PSGC code could not be resolved; verify the location code.',
                'issueType': 'unresolved_psgc',
            })
            continue

        valid_codes += 1
        granularity[place['level']] += 1
        chain = [place]
        parent = place.get('parent_code')
        while parent and parent in places:
            ancestor = places[parent]
            chain.append(ancestor)
            parent = ancestor.get('parent_code')
        by_level = {item['level']: item['name'] for item in chain}
        mismatches = []
        hierarchy_mismatches = []
        supplied_name = (row.get('Name') or '').strip()
        canonical_name = place.get('name', '')
        if supplied_name and canonical_name and _normal(supplied_name) != _normal(canonical_name):
            name_mismatch_count += 1
            mismatches.append(f'Name: provided “{supplied_name}”; PSGC entity says “{canonical_name}”.')
        for field, hierarchy_level, label in (
            ('City/Municipality', 'municipality', 'Municipality'),
            ('City/Municipality', 'city', 'City'),
            ('Province', 'province', 'Province'),
        ):
            provided = (row.get(field) or '').strip()
            canonical = by_level.get(hierarchy_level, '')
            if provided and canonical and _normal(provided) != _normal(canonical):
                # A municipal value is compared with the municipal ancestor where present;
                # city-level PSGC entries use their city ancestor instead.
                if field == 'City/Municipality' and hierarchy_level == 'city' and by_level.get('municipality'):
                    continue
                detail = f'{label}: provided “{provided}”; PSGC hierarchy says “{canonical}”.'
                mismatches.append(detail)
                hierarchy_mismatches.append(detail)
        if mismatches:
            if hierarchy_mismatches:
                hierarchy_mismatch_count += 1
            review_rows.append({
                'id': row.get('id', ''), 'title': row.get('title', ''),
                'name': row.get('Name', ''), 'municipality': row.get('City/Municipality', ''),
                'province': row.get('Province', ''), 'psgc': raw_code,
                'referencePlace': ' · '.join(by_level.get(key, '') for key in ('barangay', 'municipality', 'city', 'province') if by_level.get(key)),
                'issue': ' '.join(mismatches), 'issueType': 'hierarchy_mismatch',
            })

    missing = len(records) - located
    result = {
        'source': WORKBOOK.name,
        'sourceSheet': 'bettergov-house-bill-2027-nia-p',
        'sourceRows': len(records),
        'rowsWithPsgc': located,
        'rowsWithoutPsgc': missing,
        'rowsWithLength': rows_with_length,
        'titleChainageRows': title_chainage_rows,
        'titleStatedLengthRows': title_stated_length_rows,
        'titleCoordinateRows': title_coordinate_rows,
        'stationRangeCandidateRows': len(station_range_candidates),
        'stationRangeSegmentCount': sum(row['segmentCount'] for row in station_range_candidates),
        'stationRangeWithAmountRows': sum(row['screeningPesosPerMeter'] is not None for row in station_range_candidates),
        'stationRangeCandidates': station_range_candidates,
        'resolvedPsgcRows': valid_codes,
        'granularityCounts': dict(sorted(granularity.items())),
        'reviewFlagRows': review_rows,
        'hierarchyMismatchCount': hierarchy_mismatch_count,
        'placeNameMismatchCount': name_mismatch_count,
        'unresolvedPsgcCount': sum(r['issueType'] == 'unresolved_psgc' for r in review_rows),
        'method': 'PSGC values were matched to the local official-place reference. Supplied City/Municipality and Province text was compared with the resolved administrative hierarchy. PSGC is an administrative place key, not a surveyed project point or route alignment.',
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    STATIC.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    OUT.write_text(serialized, encoding='utf-8')
    (STATIC / 'nia-geolocation-audit.json').write_text(serialized, encoding='utf-8')
    return result


def render() -> str:
    data = build()
    total = data['sourceRows']
    located = data['rowsWithPsgc']
    valid = data['resolvedPsgcRows']
    mismatches = data['hierarchyMismatchCount']
    unresolved = data['unresolvedPsgcCount']
    missing = data['rowsWithoutPsgc']
    total_conflicts = data['hierarchyMismatchCount']
    name_conflicts = data['placeNameMismatchCount']
    length_rows = data['rowsWithLength']
    coordinate_bars = [
        ('PSGC value supplied', located),
        ('PSGC resolves', valid),
        ('Location consistency flags', len(data['reviewFlagRows'])),
        ('Rows without PSGC', missing),
    ]
    max_coordinate_count = max(1, *[value for _, value in coordinate_bars])
    coordinate_chart = ''.join(
        f'<div class="nia-check-bar"><span>{escape(label)}</span><span class="nia-check-track"><i style="width:{value / max_coordinate_count * 100:.1f}%"></i></span><strong>{value:,}</strong></div>'
        for label, value in coordinate_bars
    )
    station_data = json.dumps(data['stationRangeCandidates'], ensure_ascii=False).replace('</', '<\\/')
    station_categories = sorted({row['category'] for row in data['stationRangeCandidates']})
    category_options = ''.join(
        f'<option value="{escape(category, quote=True)}">{escape(category)}</option>'
        for category in station_categories
    )
    station_script = r'''(function(){
const D=JSON.parse(document.getElementById('nia-station-data').textContent),$=id=>document.getElementById(id),peso=v=>v==null?'—':'₱'+Number(v).toLocaleString('en-PH',{maximumFractionDigits:0}),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),offsets=[-8,-4,0,4,8],left=76,right=850;
function quantile(values,p){const a=[...values].sort((x,y)=>x-y);if(!a.length)return 0;const pos=(a.length-1)*p,lo=Math.floor(pos),hi=Math.min(lo+1,a.length-1);return a[lo]+(a[hi]-a[lo])*(pos-lo)}
function compact(v){return v>=1e6?`${(v/1e6).toLocaleString('en-PH',{maximumFractionDigits:1})}m`:v>=1000?`${(v/1000).toLocaleString('en-PH',{maximumFractionDigits:0})}k`:String(v)}
function chart(rows,logarithmic,trim){let values=rows.filter(r=>r.screeningPesosPerMeter!=null);const cutoff=trim&&values.length?quantile(values.map(r=>r.screeningPesosPerMeter),.95):null;if(trim)values=values.filter(r=>r.screeningPesosPerMeter<=cutoff);if(!values.length)return {svg:'<p>No rows with a usable amount-per-meter value in this category.</p>',rows:values,cutoff,extremeCount:0,tukeyCount:0};const nums=values.map(r=>r.screeningPesosPerMeter),q1=quantile(nums,.25),med=quantile(nums,.5),q3=quantile(nums,.75),iqr=q3-q1,loFence=q1-1.5*iqr,hiFence=q3+1.5*iqr,lo=Math.min(...nums.filter(v=>v>=loFence)),hi=Math.max(...nums.filter(v=>v<=hiFence)),min=logarithmic?Math.min(...nums):0,max=logarithmic?Math.max(...nums):Math.max(20000,Math.ceil(Math.max(...nums)/20000)*20000),safeMax=max===min?min*1.1:max;
const x=v=>left+(logarithmic?(Math.log10(v)-Math.log10(min))/(Math.log10(safeMax)-Math.log10(min)):v/safeMax)*(right-left),ticks=[];if(logarithmic){for(let p=Math.ceil(Math.log10(min));p<=Math.floor(Math.log10(safeMax));p++)ticks.push(10**p);if(!ticks.length){ticks.push(min);if(safeMax!==min)ticks.push(safeMax)}}else{const step=Math.max(10000,Math.ceil(safeMax/6/10000)*10000);for(let v=0;v<=safeMax;v+=step)ticks.push(v);if(ticks[ticks.length-1]!==safeMax)ticks.push(safeMax)}
const tickSvg=ticks.map(v=>`<line x1="${x(v).toFixed(1)}" y1="75" x2="${x(v).toFixed(1)}" y2="81" stroke="#5b6670"/><text x="${x(v).toFixed(1)}" y="97" text-anchor="middle" font-size="10">₱${compact(v)}</text>`).join(''),points=values.map((r,i)=>{const v=r.screeningPesosPerMeter,out=v<lo||v>hi;return `<circle cx="${x(v).toFixed(1)}" cy="${54+offsets[i%offsets.length]}" r="3" fill="${out?'#b7791f':'#16834a'}" stroke="#fff" stroke-width=".7" opacity=".9"><title>${out?'Tukey outlier':'Row'}: ${esc(r.title)} · ₱${Number(v).toLocaleString('en-PH')}/m</title></circle>`}).join(''),box=`<line x1="${x(lo).toFixed(1)}" y1="54" x2="${x(hi).toFixed(1)}" y2="54" stroke="#0038A8" stroke-width="2"/><line x1="${x(lo).toFixed(1)}" y1="44" x2="${x(lo).toFixed(1)}" y2="64" stroke="#0038A8" stroke-width="2"/><line x1="${x(hi).toFixed(1)}" y1="44" x2="${x(hi).toFixed(1)}" y2="64" stroke="#0038A8" stroke-width="2"/><rect x="${x(q1).toFixed(1)}" y="39" width="${Math.max(1,x(q3)-x(q1)).toFixed(1)}" height="30" fill="#dce8f5" stroke="#0038A8" stroke-width="2"/><line x1="${x(med).toFixed(1)}" y1="39" x2="${x(med).toFixed(1)}" y2="69" stroke="#b42318" stroke-width="3"/>`,svg=`<svg width="100%" height="110" viewBox="0 0 900 110" role="img" aria-label="${logarithmic?'Logarithmic':'Linear'} scale NIA allocation per parsed meter box plot, ${values.length} rows">${box}${points}<line x1="${left}" y1="78" x2="${right}" y2="78" stroke="#5b6670"/>${tickSvg}<text x="${left}" y="15" font-size="12">${logarithmic?'Log':'Linear'} scale · green rows · orange Tukey outliers</text></svg>`,extremeCount=trim?rows.filter(r=>r.screeningPesosPerMeter!=null&&r.screeningPesosPerMeter>cutoff).length:0,tukeyCount=values.filter(r=>r.screeningPesosPerMeter<lo||r.screeningPesosPerMeter>hi).length;return {svg,rows:values,cutoff,extremeCount,tukeyCount}}
let page=0,visible=[];const size=20;function draw(){const category=$('nia-station-category').value,q=$('nia-station-search').value.trim().toLowerCase(),sort=$('nia-station-sort').value,subset=D.filter(r=>category==='all'||r.category===category),full=chart(subset,true,false),trimmed=chart(subset,false,true);$('nia-full-box').innerHTML=full.svg;$('nia-full-caption').textContent=`Full range · ${full.rows.length} rows with amounts · log scale`;$('nia-trimmed-box').innerHTML=trimmed.svg;$('nia-trim-caption').textContent=trimmed.cutoff==null?'No rows with a usable amount-per-meter value in this category.':`Linear scale · excludes only ${trimmed.extremeCount} of ${subset.filter(r=>r.screeningPesosPerMeter!=null).length} rows above ₱${Number(trimmed.cutoff).toLocaleString('en-PH')}/m. Retains ${trimmed.rows.length} rows, including ${trimmed.tukeyCount} Tukey outliers in orange.`;const extremes=subset.filter(r=>r.screeningPesosPerMeter!=null&&r.screeningPesosPerMeter>trimmed.cutoff).sort((a,b)=>b.screeningPesosPerMeter-a.screeningPesosPerMeter);$('nia-trimmed-outliers').innerHTML=extremes.map(r=>`<tr><td>${esc(r.title)}<small>${esc(r.id)} · PDF p. ${esc(r.sourcePage)}</small></td><td>${r.category}</td><td>${r.segmentLengthsM.map(x=>Number(x).toLocaleString('en-PH')+' m').join(' + ')}</td><td>${peso(r.amountPesos)}</td><td>${peso(r.screeningPesosPerMeter)}/m</td></tr>`).join('')||'<tr><td colspan="5">No values were trimmed for this category.</td></tr>';visible=subset.filter(r=>!q||`${r.title} ${r.id} ${r.category} ${r.programLine}`.toLowerCase().includes(q));visible.sort((a,b)=>sort==='title'?a.title.localeCompare(b.title):sort==='length'?b.totalStationRangeM-a.totalStationRangeM:sort==='low'?(a.screeningPesosPerMeter??Infinity)-(b.screeningPesosPerMeter??Infinity):(b.screeningPesosPerMeter??-1)-(a.screeningPesosPerMeter??-1));const pages=Math.max(1,Math.ceil(visible.length/size));page=Math.min(page,pages-1);$('nia-station-rows').innerHTML=visible.slice(page*size,(page+1)*size).map(r=>`<tr><td>${esc(r.title)}<small>${esc(r.id)} · PDF p. ${esc(r.sourcePage)}</small></td><td>${esc(r.category)}<small>${esc(r.programLine)}</small></td><td>${r.segmentLengthsM.map(x=>Number(x).toLocaleString('en-PH')+' m').join(' + ')}</td><td>${Number(r.totalStationRangeM).toLocaleString('en-PH')} m</td><td>${peso(r.amountPesos)}</td><td>${peso(r.screeningPesosPerMeter)} / m</td></tr>`).join('')||'<tr><td colspan="6">No rows found.</td></tr>';$('nia-station-page').textContent=`${visible.length} rows · page ${page+1} of ${pages}`;$('nia-station-prev').disabled=page===0;$('nia-station-next').disabled=page>=pages-1}for(const id of ['nia-station-category','nia-station-search','nia-station-sort'])$(id).addEventListener(id==='nia-station-search'?'input':'change',()=>{page=0;draw()});$('nia-station-prev').onclick=()=>{page--;draw()};$('nia-station-next').onclick=()=>{page++;draw()};draw()})();'''
    table_rows = []
    for row in data['reviewFlagRows']:
        table_rows.append(
            '<tr><td>' + escape(row['title']) + '<small>' + escape(row['id']) + '</small></td>'
            '<td>' + escape(row['name']) + ' · ' + escape(row['municipality']) + ' · ' + escape(row['province']) + '</td>'
            '<td>' + escape(row['psgc']) + '</td><td>' + escape(row['referencePlace']) + '</td>'
            '<td>' + escape(row['issue']) + '</td></tr>'
        )
    return f'''<style id="nia-geolocation-flags-style">.nia-geolocation-flags .nia-location-metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}}.nia-geolocation-flags .nia-location-metrics>div{{display:grid;gap:3px;padding:13px;border:1px solid #dce4e1;border-radius:10px;background:#fff}}.nia-geolocation-flags .nia-location-metrics strong{{font-size:22px;color:#8f1d16;font-variant-numeric:tabular-nums}}.nia-geolocation-flags .nia-location-metrics span,.nia-geolocation-flags small{{display:block;color:#637381;font-size:12px}}.nia-geolocation-flags .nia-location-method{{padding:12px 14px;border-left:4px solid #0038A8;background:#EAF0FF}}.nia-geolocation-flags .nia-check-chart{{display:grid;gap:9px;max-width:760px;margin:14px 0 22px}}.nia-geolocation-flags .nia-check-bar{{display:grid;grid-template-columns:minmax(150px,1fr) minmax(100px,3fr) 64px;gap:10px;align-items:center;font-size:13px}}.nia-geolocation-flags .nia-check-track{{height:12px;border-radius:8px;background:#e8edf3;overflow:hidden}}.nia-geolocation-flags .nia-check-track i{{display:block;height:100%;background:#0038A8;border-radius:8px}}.nia-geolocation-flags .nia-check-bar strong{{text-align:right;font-variant-numeric:tabular-nums}}.nia-geolocation-flags .tablewrap{{overflow:auto}}.nia-geolocation-flags table{{width:100%;border-collapse:collapse;font-size:13px}}.nia-geolocation-flags th{{background:#00246A;color:#fff;text-align:left}}.nia-geolocation-flags th,.nia-geolocation-flags td{{padding:9px 11px;border-bottom:1px solid #dce4e1;vertical-align:top}}.nia-geolocation-flags td:first-child{{min-width:260px}}.nia-geolocation-flags td:last-child{{min-width:250px}}.nia-geolocation-flags .station-controls{{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}}.nia-geolocation-flags .station-controls input,.nia-geolocation-flags .station-controls select{{font:inherit;padding:8px 10px;border:1px solid #bcc8d4;border-radius:8px}}.nia-geolocation-flags .station-controls input{{flex:1;min-width:220px}}.nia-geolocation-flags .station-page{{display:flex;gap:10px;justify-content:flex-end;align-items:center;margin-top:10px}}.nia-geolocation-flags .station-page button{{padding:7px 10px;border:1px solid #bcc8d4;border-radius:7px;background:#fff}}.nia-geolocation-flags .export-btn{{display:inline-block;padding:9px 13px;border-radius:8px;background:#0038A8;color:#fff;text-decoration:none;font-weight:650}}.nia-geolocation-flags .export-btn:hover{{background:#00246A}}@media(max-width:600px){{.nia-geolocation-flags{{overflow:hidden}}.nia-geolocation-flags .nia-location-metrics{{grid-template-columns:1fr 1fr}}}}</style>
<section id="nia-geolocation-flags" class="card nia-geolocation-flags">
<h2>NIA location coverage and administrative consistency flags</h2>
<p>The 10 November 2026 BetterGov House-bill geolocation workbook assigns an administrative PSGC place to <strong>{located:,} of {total:,}</strong> rows; <strong>{valid:,}</strong> codes resolve in the current PSGC reference. This improves locality-level review, but does not provide project coordinates or canal/dam alignments.</p>
<div class="nia-location-metrics"><div><strong>{located:,}/{total:,}</strong><span>rows with a PSGC value</span></div><div><strong>{missing:,}</strong><span>rows without a PSGC value</span></div><div><strong>{mismatches:,}</strong><span>province/municipality hierarchy conflicts</span></div><div><strong>{name_conflicts:,}</strong><span>Name-to-PSGC entity conflicts</span></div><div><strong>{unresolved:,}</strong><span>PSGC values not found in the reference</span></div></div>
<h3>Coordinate and location checks</h3><p>The source has administrative place codes, not project latitude/longitude or route geometry. These counts show location-code coverage and consistency checks; they are not coordinate validation.</p><div class="nia-check-chart" role="img" aria-label="NIA administrative location check counts">{coordinate_chart}</div>
<h3>Station-range length and allocation-per-meter screen</h3>
<p>Station ranges are converted to meters (for example, Sta. 0+500–1+015 = 515 m). The ratio divides the row’s House-bill allocation by its parsed station-range total. This is a screening ratio: an allocation can cover multiple work types, and a title can contain several segments or non-linear works. Select the NIA program category before comparing distributions.</p>
<div class="station-controls">
<label for="nia-station-category">NIA project category <select id="nia-station-category"><option value="all">All project categories</option>{category_options}</select></label>
</div>
<figure class="nia-cost-boxplot"><figcaption id="nia-full-caption">Full-range allocation per parsed meter</figcaption><div id="nia-full-box"></div></figure>
<section class="nia-trimmed-distribution" style="margin:20px 0;padding:18px;border:1px solid #bdd9c6;border-radius:12px;background:#f4f8f4">
<h3>Typical range · top five percent trimmed</h3>
<p id="nia-trim-caption">The second view trims only the highest five percent for the selected category; the full-range view above keeps every row.</p>
<figure class="nia-cost-boxplot"><div id="nia-trimmed-box"></div></figure>
<h4>Highest values trimmed from this view</h4>
<p>These rows remain visible in the full-range plot and are listed here because they are omitted from the linear-scale view. Extreme values are data-quality review leads, not confirmed errors.</p>
<div class="tablewrap"><table><thead><tr><th>Project title / source row</th><th>NIA project category</th><th>Parsed station length</th><th>HGAB amount</th><th>Screening allocation per meter</th></tr></thead><tbody id="nia-trimmed-outliers"></tbody></table></div>
</section>
<div class="station-controls">
<input id="nia-station-search" type="search" placeholder="Search NIA title or source row">
<select id="nia-station-sort"><option value="high">Highest allocation per meter</option><option value="low">Lowest allocation per meter</option><option value="length">Longest parsed length</option><option value="title">Project title</option></select>
</div>
<div class="tablewrap"><table><thead><tr><th>Project title / source row</th><th>NIA project category</th><th>Segments</th><th>Total parsed length</th><th>HGAB amount</th><th>Allocation per meter*</th></tr></thead><tbody id="nia-station-rows"></tbody></table></div>
<div class="station-page"><button type="button" id="nia-station-prev">Previous</button><span id="nia-station-page"></span><button type="button" id="nia-station-next">Next</button></div>
<script id="nia-station-data" type="application/json">{station_data}</script><script>{station_script}</script>
<p class="nia-location-method">Location granularity among resolved codes: {data['granularityCounts'].get('barangay', 0):,} barangay, {data['granularityCounts'].get('municipality', 0):,} municipality, and {data['granularityCounts'].get('city', 0):,} city codes. A municipal or city key locates a project only to that administrative area. {data['titleCoordinateRows']:,} title contains a latitude/longitude pair, but the workbook has no project point or route geometry layer. These title coordinates and lengths need verification against source plans before spatial or unit-cost analysis. We therefore do not apply FMR road-distance, road-overlap, crop-proximity, endpoint, venue, or connectivity flags to these NIA rows. Those checks need project-level points or line geometry.</p>
<p><a class="export-btn" href="nia-geolocation-audit.json" download>Download NIA location flag data ↗</a></p>
<h3>Rows to verify against the source schedule</h3><p>These flags identify a disagreement between workbook administrative text and its PSGC hierarchy, or a PSGC value not found in the current reference. They are location-data checks, not findings about project validity.</p>
<div class="tablewrap"><table><thead><tr><th>NIA project · source row</th><th>Workbook location labels</th><th>PSGC</th><th>Resolved administrative hierarchy</th><th>Review flag</th></tr></thead><tbody>{''.join(table_rows) or '<tr><td colspan="5">No administrative hierarchy conflicts found.</td></tr>'}</tbody></table></div>
<p class="muted">Method: {escape(data['method'])} Source: {escape(data['source'])}. Current PSGC reference checked during page build.</p>
</section>'''

