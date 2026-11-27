"""Render the procurement title-match report and its archive search."""
from html import escape
import re
from urllib.parse import quote

from report_hero_module import STYLE as HERO_STYLE, hero
from uniform_report_menu import apply_page

V2_LINK = 'https://huggingface.co/datasets/bettergovph/philgeps-v2'
IRR_LINK = 'https://www.gppb.gov.ph/wp-content/uploads/2025/02/IRR-of-RA-No.-12009.pdf'

STYLE = """<style>
*{box-sizing:border-box}body{margin:0}main{width:100%;padding:24px clamp(16px,2vw,32px)}
section{min-width:0;margin:14px 0;padding:clamp(14px,2vw,24px);border:1px solid #cbd9e2;border-radius:12px;background:#fff;overflow-wrap:anywhere}
h2{margin:0 0 .5rem;color:#18304b} p{max-width:92ch}
a{overflow-wrap:anywhere}.coverage{display:flex;flex-wrap:wrap;gap:12px;margin:1rem 0}
.coverage div{background:#eef4fa;padding:.65rem .9rem;border-radius:8px}.coverage strong{display:block;font-size:1.2rem}
.invitation{border-left:5px solid #007d74;background:#f0f7f6;padding:1rem;border-radius:6px;margin:.8rem 0}
.invitation h3{margin:0;color:#123953}.invitation ul{padding-left:1.35rem}
.review-flags{border-left:3px solid #a45617;background:#fff6e8;padding:.7rem 1rem;margin-top:.8rem}
.review-flags h4{margin:0 0 .4rem}.review-flags ul{margin:.35rem 0}.review-flags li+li{margin-top:.4rem}
.controls,.pagination{display:flex;align-items:end;flex-wrap:wrap;gap:.65rem;margin:1rem 0}
.controls label{display:grid;gap:.25rem;min-width:0;max-width:100%}.controls label:first-child{flex:1 1 18rem}
input,select,button{font:inherit;min-height:40px;border-radius:6px;border:1px solid #89a4ba;background:#fff;padding:.4rem .7rem}
button{color:#073577;cursor:pointer}button:disabled{cursor:default;opacity:.5}
.table-scroll{max-width:100%;overflow-x:auto;border:1px solid #cbd9e2;border-radius:7px}
table{min-width:760px;width:100%;table-layout:fixed;border-collapse:collapse;text-align:left}td,th{padding:.65rem;vertical-align:top;border-bottom:1px solid #dae4ed}
th:nth-child(1){width:32%}th:nth-child(2){width:22%}th:nth-child(3){width:14%}th:nth-child(4){width:32%}
th{background:#edf3f9}td small{display:block;margin:.35em 0}td ul{padding-left:1.2em;margin:0}td details{margin:.4em 0}
</style>"""

SCRIPT = r"""<script>
(() => {
  const section = document.querySelector('#archive');
  const byId = id => document.getElementById(id);
  const [query, stage, status, prev, next, body] =
    ['title-filter','stage-filter','archive-status','archive-prev','archive-next','archive-rows'].map(byId);
  const escape = text => String(text ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const pesos = amount => amount == null ? '—' : Number(amount).toLocaleString('en-PH', {maximumFractionDigits:2});
  const normalize = value => String(value ?? '').toLowerCase().replace(/\s+/g,' ').trim();
  const pageSize = 25;
  let rows = [], budget = {}, page = 0;

  function sourceLink(line) {
    const title = escape(line.stage + ' · ' + line.program + ' · ' + line.title);
    const source = line.url ? `<a href="${escape(line.url)}">${title}</a>` : title;
    return `<li>${source} · ₱${pesos(line.amount)}${line.office ? ' · ' + escape(line.office) : ''}</li>`;
  }

  function renderRow(row) {
    const reference = escape(row.reference);
    const notice = /^\d+$/.test(row.reference)
      ? `<a href="https://notices.philgeps.gov.ph/GEPSNONPILOT/Tender/SplashBidNoticeAbstractUI.aspx?menuIndex=3&amp;refID=${reference}">PhilGEPS ${reference}</a>`
      : `PhilGEPS ${reference}`;
    const lines = budget[row.key].filter(line => !stage.value || line.stage === stage.value);
    const links = `<ul>${lines.map(sourceLink).join('')}</ul>`;
    return `<tr>
      <td><strong>${escape(row.title || row.matched_title)}</strong><small>${escape(row.office)}</small>
        ${notice}${row.solicitation ? ' · ' + escape(row.solicitation) : ''}
        <small>${escape(row.field)}${row.matched_title !== row.title ? ' · ' + escape(row.matched_title) : ''}</small></td>
      <td>${escape(row.published || 'Date unavailable')}<small>${escape(row.notice_status || 'Status unavailable')}</small>
        ABC ${pesos(row.abc)}<small title="${escape(row.source)}">${escape([row.source_file || row.source, row.sheet, 'row ' + row.source_row].filter(Boolean).join(' · '))}</small></td>
      <td>${row.award_reference ? escape(row.award_reference) + '<small>' + escape([row.award_status, row.award_date].filter(Boolean).join(' · ')) + '</small>' : '—'}</td>
      <td>${lines.length > 3 ? `<details><summary>${lines.length} budget lines</summary>${links}</details>` : links}</td>
    </tr>`;
  }

  function draw() {
    const q = normalize(query.value), wanted = stage.value;
    const filtered = rows.filter(row => (!wanted || budget[row.key].some(line => line.stage === wanted))
      && (!q || row.search.includes(q)));
    const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
    page = Math.min(page, pages - 1);
    body.innerHTML = filtered.slice(page * pageSize, (page + 1) * pageSize).map(renderRow).join('')
      || '<tr><td colspan="4">No matching archive records.</td></tr>';
    status.textContent = `${filtered.length.toLocaleString()} title and notice pairs · Page ${page + 1} of ${pages}`;
    prev.disabled = page === 0;
    next.disabled = page >= pages - 1;
  }

  async function load() {
    const retry = byId('archive-retry');
    retry.hidden = true;
    status.textContent = 'Loading PhilGEPS v2 matches…';
    try {
      const response = await fetch(section.dataset.source);
      if (!response.ok) throw Error(response.status);
      const data = await response.json();
      budget = data.budgetMatches;
      rows = data.archive.map(row => ({...row, search: normalize([
        row.title, row.matched_title, row.office, row.reference, row.solicitation,
        ...budget[row.key].map(line => line.title)
      ].join(' '))}));
      query.disabled = stage.disabled = false;
      draw();
    } catch (_) {
      status.textContent = 'Could not load archive matches.';
      retry.hidden = false;
    }
  }

  query.oninput = stage.onchange = () => { page = 0; draw(); };
  prev.onclick = () => { page--; draw(); };
  next.onclick = () => { page++; draw(); };
  byId('archive-retry').onclick = load;
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); load(); }
    }, {rootMargin:'400px'});
    observer.observe(section);
  } else load();
})();
</script>"""


def invitation_html(row):
    title = re.sub(r'^' + re.escape(row['contract']) + r'\s*[-:–—]\s*', '', row['title'])
    budget_links = ''.join(
        f'<li><a href="{escape(line["url"], quote=True)}">{label or escape(line["stage"])} budget source</a>'
        f' · ₱{line["amount"]:,} · {escape(line["title"])}</li>'
        for label, lines in [('', row['budget']), ('Different-segment NEP', row.get('related', []))]
        for line in lines if line['url'] and line['amount'] is not None
    )
    bulletin = (f'<li><a href="{row["bulletin"]}">Supplemental bulletin on contract duration and quantities</a></li>'
                if row.get('bulletin') else '')
    status = f' · PhilGEPS status {escape(row["status"])}' if row.get('status') else ''
    abc = format(row['abc'], ',.2f' if isinstance(row['abc'], float) else ',')
    opening = f' · Scheduled bid opening {row["opening"]}' if row['opening'] else ''
    flag_entries = ''.join(
        f'<li><strong>{escape(flag["label"])}</strong> · {escape(flag["evidence"])} '
        f'<a href="{escape(flag["url"], quote=True)}">{escape(flag.get("sourceId") or "Source")}</a></li>'
        for flag in row.get('flags', [])
    )
    flags = f'<div class="review-flags"><h4>Review flags</h4><ul>{flag_entries}</ul></div>' if flag_entries else ''
    return f'''<article class="invitation">
<h3>{escape(row['contract'])} · {escape(title)}</h3>
<p>{escape(row['office'])}{status} · {escape(row.get('dateLabel', 'Invitation issued'))} {row['issued']}{opening} · ABC ₱{abc}</p>
<p>{escape(row['basis'])}</p>
<ul><li><a href="{row['url']}">PhilGEPS invitation to bid · document {row['reference']}</a></li>
{bulletin}{budget_links}</ul>{flags}</article>'''


def render(data, asset):
    summary = data['coverage']
    stage_counts = ' · '.join(f'{stage} {summary["byStage"].get(stage, 0):,}' for stage in ('NEP', 'HGAB', 'SCR'))
    invitations = ''.join(invitation_html(row) for row in data['invitations'])
    source_count = len({row['url'] for row in data['invitations']})
    contract_count = len(data['invitations'])
    matched_count = sum(bool(row['budget']) for row in data['invitations'])
    lead = hero(
        'PhilGEPS · FY2027', f'{contract_count:,}', 'contracts citing FY2027 funds',
        f'{matched_count:,}', 'have a budget match in the available schedules',
        [
            ('Official PhilGEPS sources', f'{source_count:,}', 'Public tender notices and invitations'),
            ('Budget match unestablished', f'{contract_count - matched_count:,}', 'Scope or funding link requires review'),
        ],
        'The sources document invitations to bid. Confirming a contract award requires separate evidence.',
    )
    crawl = data['crawl']
    crawl_summary = ''
    if crawl:
        window = escape(crawl['asOf'])
        if crawl.get('requestedFrom'):
            window = escape(crawl['requestedFrom']) + ' to ' + window
        reviewed = crawl.get('detailsReviewed', crawl['detailsRequested'] - len(crawl.get('detailFailures', [])))
        pending = max(0, crawl['listingsScreened'] - reviewed) if crawl.get('allDetails') else 0
        coverage = ''
        if crawl.get('inProgress'):
            coverage = ' The crawl is still in progress.'
        elif crawl.get('searchError') or pending:
            coverage = ' The run encountered incomplete coverage.'
        if pending:
            coverage += f' {pending:,} listed notices still need detail review.'
        if (reported := crawl.get('reportedListings')) and reported > crawl['listingsScreened']:
            coverage += f' The portal reported {reported:,} listings in the search.'
        crawl_summary = (f'<p>The public civil-works crawl for {window} found '
                         f'{crawl["listingsScreened"]:,} distinct listings and reviewed '
                         f'{reviewed:,} detail pages.{coverage} '
                         f'<a href="{escape(crawl["listingUrl"], quote=True)}">PhilGEPS public listings</a></p>')
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FY2027 budget projects and PhilGEPS | BetterGov</title>{STYLE}{HERO_STYLE}</head>
<body><header><div>BetterGov · Budget research</div>
<h1>FY2027 budget projects and PhilGEPS</h1>
<p>Published invitations, matched budget lines and source-linked review flags.</p>
</header><main>
{lead}
<section id="verified-invitations">
<h2>Verified FY2027 invitations to bid</h2>
<p>The sources establish invitations and scheduled bid openings. Actual bid openings and FY2027 awards remain unverified.</p>
{crawl_summary}
<p>Review flags below link to their source evidence. An invitation under Early Procurement Activity is permitted when the requirements in section 12 are met.</p>
{invitations}
</section>
<section id="procurement-rules">
<h2>What the procurement rules allow</h2>
<p>Section 12 of the approved implementing rules for RA No. 12009 allows Early Procurement Activities after submission of the NEP, subject to an approved indicative Annual Procurement Plan and the applicable guidelines. The procurement must stop short of award until the appropriate funding is approved and effective and the final procurement plan is approved.</p>
<p><a href="{IRR_LINK}">Approved implementing rules, section 12</a></p>
</section>
<section id="archive" data-source="{quote(asset, safe='?=.-')}">
<h2>PhilGEPS v2 historical title matches</h2>
<p>The archive includes postings up to {summary['archiveThrough']}. These title matches flag earlier procurement records for scope review. Establishing a link to FY2027 requires a current procurement record and funding evidence.</p>
<div class="coverage">
<div><strong>{summary['budgetLines']:,}</strong> sourced budget stage lines · {stage_counts}</div>
<div><strong>{summary['titleKeys']:,}</strong> distinct titles screened</div>
<div><strong>{len(data['archive']):,}</strong> historical title and notice pairs</div>
</div>
<div class="controls">
<label>Search project, agency or notice reference<input id="title-filter" type="search" disabled></label>
<label>Matched budget stage<select id="stage-filter" disabled><option value="">All stages</option><option>NEP</option><option>HGAB</option><option>SCR</option></select></label>
</div>
<p id="archive-status" aria-live="polite">Archive matches load when this section comes into view.</p>
<button id="archive-retry" type="button" hidden>Retry loading matches</button>
<div class="table-scroll" tabindex="0" role="region" aria-label="Historical match records">
<table><thead><tr><th scope="col">PhilGEPS record</th><th scope="col">Notice date and source row</th><th scope="col">Archive award reference</th><th scope="col">FY2027 budget lines</th></tr></thead>
<tbody id="archive-rows"></tbody></table></div>
<div class="pagination"><button type="button" id="archive-prev" disabled>Previous</button><button type="button" id="archive-next" disabled>Next</button></div>
</section>
<section>
<h2>Coverage and matching method</h2>
<p>Budget coverage includes the available named FY2027 lines for DPWH, farm-to-market roads, health facilities and NIA irrigation. It includes positive SCR allocations and keeps each budget stage separate.</p>
<p>The search compared titles against the notice title, award title and line-item name in {summary['archiveRows']:,} PhilGEPS v2 rows. It matches whole normalized titles after removing accents, case and punctuation. Each title and bid reference pair retains one source row, preferring notice-title evidence. Verify the agency, work scope and location, especially where a short title names only a facility. Archived amounts retain the dataset’s reported values and historical award dates may contain source errors.</p>
<p><a href="{V2_LINK}">PhilGEPS v2 release, coverage and source inventory</a> · <a href="https://philgeps.gov.ph/CmsHomePages/open-data">Official PhilGEPS exports</a> · <a href="scr.html">FY2027 budget stage sources</a></p>
</section>
</main>{SCRIPT}</body></html>'''
    return apply_page(html, 'philgeps.html').rstrip() + '\n'
