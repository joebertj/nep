"""Attach separately loaded place inventories without altering report menus."""
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
PANEL = '''<!-- connectivity-place-inventory:start -->
<h3>FMR routes matched to visitor venues</h3>
<p id="fmr-venue-summary" aria-live="polite">Loading coordinate-backed route matches…</p>
<p class="note"><strong>These 13 matches are FMR project routes; there are no separately budgeted road projects in this table.</strong> The road-project list below contains title and allocation records, but the integrated GAA road rows have no usable coordinates or alignments to match to venues. A route is a remote-area candidate only when both source endpoints fall inside DPWH municipality boundaries. The 100 m check uses a straight segment between printed coordinates; it is a proximity lead, not proof of the actual alignment or usable access.</p>
<p><a href="connectivity-remote-fmr-venues.csv" download>Download matched FMR–venue rows (CSV)</a> · <a href="connectivity-remote-fmr-venues.json" download>Matched FMR–venue data (JSON)</a></p>
<div class="filters"><label>Search route or venue <input id="fmr-venue-query" type="search" placeholder="Project, venue, municipality, province"></label><label>Fiscal year <select id="fmr-venue-year"><option value="">All available years</option></select></label></div>
<div class="table-wrap"><table data-report-table-exempt="true"><thead><tr><th>Year / source</th><th>FMR project route</th><th>Mapped venue</th><th>Location / type</th><th class="num">Distance</th><th>Map</th><th>Source evidence</th></tr></thead><tbody id="fmr-venue-rows"></tbody></table></div>
<div class="controls"><button id="fmr-venue-prev" type="button">Previous</button><span id="fmr-venue-page"></span><button id="fmr-venue-next" type="button">Next</button><label>Rows <select id="fmr-venue-size"><option>10</option><option selected>25</option><option>50</option><option>100</option></select></label></div>
<div id="connectivity-places-inventory">
<h3>Visitor venues, subdivisions and private-property evidence</h3>
<p id="place-source-summary" aria-live="polite">Loading downloaded place inventories…</p>
<p class="note" id="place-source-date"></p>
<p>Use the existing road alignments with a <strong>100 m buffer</strong> to find nearby visitor venues, large residential buildings, residential estates and subdivisions. A mapped villa or large building does not establish its price. Estate/village wording can describe an entire development. Subdivision access needs entrance or road-intersection evidence; proximity alone remains a lead. These source rows have not yet been assigned to budget projects.</p>
<p><a href="connectivity-venues-data.csv" download>Visitor venues CSV</a> · <a href="connectivity-venues-data.json" download>Visitor venues JSON</a> · <a href="connectivity-property-indicators-data.csv" download>Property / subdivision CSV</a> · <a href="connectivity-property-indicators-data.json" download>Property polygons JSON</a> · <a href="connectivity-venue-review-data.csv" download>Unverified venue name cues</a></p>
<div class="filters"><label>Search places <input id="place-query" type="search" placeholder="Venue, province, municipality or source ID"></label><label>Type <select id="place-type"><option value="">All types</option></select></label><label>Location <select id="place-admin"><option value="Municipality" selected>Municipalities</option><option value="City">Cities</option><option value="">All places</option><option value="unresolved">Unresolved</option></select></label></div>
<div class="table-wrap"><table data-report-table-exempt="true"><thead><tr><th>Mapped place / property cue</th><th>Location</th><th>Source evidence</th><th>Mapped footprint / area</th><th>Source record</th></tr></thead><tbody id="place-rows"></tbody></table></div>
<div class="controls"><button id="place-prev" type="button">Previous</button><span id="place-page"></span><button id="place-next" type="button">Next</button><label>Rows <select id="place-size"><option>10</option><option selected>25</option><option>50</option><option>100</option></select></label></div>
<p class="note">© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors · ODbL</a>. Source locations can be node coordinates or bounding-box centers; property polygons are retained where recovered. Public markets, mapped government facilities and closed-use tags are screened out. Personal owner names, contact details and full street addresses are omitted.</p>
</div><!-- connectivity-place-inventory:end -->'''
DISCLAIMER = '''<!-- connectivity-disclaimer:start -->
<aside id="report-evidence-notice" class="report-disclaimer" role="note"><strong>Disclaimer.</strong> Venue names and locations are unverified leads from the cited public map source. A 100 m proximity match does not establish road access, that a project serves or benefits a venue, or that the venue, its owners or staff were involved. This listing is not an allegation of wrongdoing. Verify the source record, location and current status before drawing conclusions.</aside>
<!-- connectivity-disclaimer:end -->'''
ROAD_CONTEXT = '''<!-- connectivity-road-context:start -->
<h3>Budgeted road project titles · not yet spatially matched</h3>
<p class="note">These GAA/HGAB road titles can be reviewed by location wording, but the integrated GAA rows do not provide usable project coordinates or alignments. They therefore cannot yet appear as road-to-venue matches.</p>
<!-- connectivity-road-context:end -->'''


def apply_page(text):
    text = re.sub(r'<!-- connectivity-place-inventory:start -->.*?<!-- connectivity-place-inventory:end -->', '', text, flags=re.S)
    text = re.sub(r'<!-- connectivity-road-context:start -->.*?<!-- connectivity-road-context:end -->', '', text, flags=re.S)
    text = re.sub(r'<!-- connectivity-disclaimer:start -->.*?<!-- connectivity-disclaimer:end -->', '', text, flags=re.S)
    text = re.sub(r'<h3>Budgeted road project titles · not yet spatially matched</h3>\s*<p class="note">These GAA/HGAB road titles can be reviewed by location wording, but the integrated GAA(?: road)? rows do not provide usable (?:project )?coordinates or alignments\. They therefore cannot yet appear as road-to-venue matches\.</p>', '', text)
    text = text.replace('2 · Remote roads and current visitor venues', '2 · Remote roads, visitor venues and private properties')
    if 'report-disclaimer.css' not in text:
        text = text.replace('<link rel="stylesheet" href="report-table-readability.css">', '<link rel="stylesheet" href="report-table-readability.css"><link rel="stylesheet" href="report-disclaimer.css?v=20261104">', 1)
    if '<main>' not in text:
        raise ValueError('Connectivity page main container not found')
    text = text.replace('<main>', '<main>'+DISCLAIMER, 1)
    section = text.find('<h2>2 · Remote roads, visitor venues and private properties</h2>')
    if section < 0:
        raise ValueError('Connectivity section 2 not found')
    end = text.find('</section>', section)
    content = text[section:end]
    content = content.replace('<h3>Budgeted road title context</h3>', '')
    content = re.sub(r'<p class="alert"><strong>Distance and venue counts are pending usable alignments\.</strong>.*?</p>',
                     '<p class="alert"><strong>Place inventories are downloaded.</strong> Compare these records with the existing road data. City roads and DPWH national roads remain outside the remote-road screen. Municipality location is a provisional proxy; a nearby property is not yet an established road connection.</p>', content, flags=re.S)
    content = re.sub(r'<p>For current public venue evidence, OpenStreetMap can supply.*?</p>', '', content, flags=re.S)
    marker = '<div class="filters"><label>Search remote-road title'
    if marker in content:
        content = content.replace(marker, PANEL+ROAD_CONTEXT+marker, 1)
    else:
        content += PANEL
    text = text[:section] + content + text[end:]
    source = ROOT / 'report_assets/connectivity-places.js'
    body = source.read_text()
    (STATIC / 'connectivity-places.js').write_text(body)
    version = hashlib.sha256(body.encode()).hexdigest()[:12]
    map_source = ROOT / 'report_assets/connectivity-map.js'
    map_body = map_source.read_text()
    (STATIC / 'connectivity-map.js').write_text(map_body)
    map_version = hashlib.sha256(map_body.encode()).hexdigest()[:12]
    text = re.sub(r'<script\b[^>]*id="connectivity-places-script"[^>]*>.*?</script>', '', text, flags=re.S)
    text = re.sub(r'<script\b[^>]*id="connectivity-map-script"[^>]*>.*?</script>', '', text, flags=re.S)
    return text.replace('</body>', f'<script id="connectivity-places-script" src="connectivity-places.js?v={version}"></script><script id="connectivity-map-script" src="connectivity-map.js?v={map_version}"></script></body>', 1)


if __name__ == '__main__':
    page = STATIC / 'connectivity.html'
    page.write_text(apply_page(page.read_text()))
