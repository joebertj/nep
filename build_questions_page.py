#!/usr/bin/env python3
"""Download FY2027 House budget hearing records and render a source-linked browser."""
from concurrent.futures import ThreadPoolExecutor
from html import escape
import argparse
import json
from pathlib import Path
import urllib.request
from question_report_layout import render_report

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
DATA_DIR = ROOT / 'data_sources' / 'budget_hearings_fy2027'
API = 'https://budget.bettergov.ph/api/v1/hearings'
HEADERS = {'User-Agent': 'BetterGov research page builder/1.0 (public data download)'}


def get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def download():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index = get_json(API + '?fiscal_year=2027&limit=100&offset=0')
    hearings = index['data']

    def fetch_topics(hearing):
        path = DATA_DIR / f"{hearing['video_id']}.json"
        if path.exists():
            topics = json.loads(path.read_text(encoding='utf-8'))
        else:
            topics = get_json(API + '/' + hearing['video_id'] + '/topics')['data']
            path.write_text(json.dumps(topics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return {**hearing, 'topics': topics}

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(fetch_topics, hearings))
    payload = {
        'source': API,
        'retrievedAt': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'hearingCount': len(records),
        'topicCount': sum(len(row['topics']) for row in records),
        'hearings': records,
    }
    target = DATA_DIR / 'hearings-fy2027.json'
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return payload


def render(data, crosswalk=None):
    rows = []
    for hearing in data['hearings']:
        for topic in hearing['topics']:
            actions = topic.get('actions') or []
            action_html = ''.join(
                '<li><strong>' + escape(str(action.get('kind') or 'Action').replace('_', ' ')) +
                '</strong> · ' + escape(action.get('action', '')) +
                (f' <a href="{escape(action["url"], quote=True)}">at {escape(action.get("timestamp", ""))}</a>' if action.get('url') else '') +
                '</li>' for action in actions
            )
            moments = topic.get('thread') or []
            moment_html = ''.join(
                '<li><a href="' + escape(moment.get('url', hearing['page_url']), quote=True) + '">' +
                escape(moment.get('timestamp', 'Open video')) + '</a> · <strong>' +
                escape(moment.get('speaker') or 'Speaker unavailable') + '</strong> · ' +
                escape(moment.get('said', '')) + '</li>' for moment in moments
            )
            search_text = ' '.join(str(topic.get(field) or '') for field in
                                   ('topic', 'summary', 'question', 'outcome', 'agency_position'))
            rows.append(
                '<tr class="topic" data-agency="' + escape(hearing.get('agency') or '') +
                '" data-search="' + escape(search_text.casefold(), quote=True) + '"><td>' +
                '<div class="topic-meta">' + escape(hearing.get('agency') or 'Agency unavailable') +
                ' · ' + escape(hearing.get('hearing_date') or '') + ' · ' +
                escape(topic.get('status') or 'status unavailable') + '</div><h3>' +
                escape(topic.get('topic') or 'Untitled topic') + '</h3><p>' +
                escape(topic.get('summary') or topic.get('question') or '') + '</p>' +
                (('<details><summary>Questions and agency response</summary><p>' +
                  escape(topic.get('question') or '') + '</p><p>' +
                  escape(topic.get('agency_position') or '') + '</p><p><strong>Outcome</strong> ' +
                  escape(topic.get('outcome') or 'Not recorded') + '</p></details>')) +
                (('<details><summary>Timestamped statements (' + str(len(moments)) + ')</summary><ul>' +
                  moment_html + '</ul></details>') if moments else '') +
                (('<details><summary>Recorded actions (' + str(len(actions)) + ')</summary><ul>' +
                  action_html + '</ul></details>') if actions else '') +
                '<p><a href="' + escape(hearing['page_url'], quote=True) +
                '">Open hearing record and source video</a></p></td></tr>'
            )
    hearings = data['hearings']
    agency_options = ''.join('<option>' + escape(agency) + '</option>' for agency in
                             sorted({row.get('agency') for row in hearings if row.get('agency')}))
    body = ''.join(rows)
    crosswalk = crosswalk or {'classificationCounts': {}, 'budgetRowCount': 0}
    checked = crosswalk.get('topicCount', data.get('topicCount', 0))
    counts = crosswalk.get('classificationCounts', {})
    candidate_count = counts.get('candidate_leads_need_review', 0)
    no_candidate_count = counts.get('no_candidate_in_available_extracts', 0)
    not_covered_count = counts.get('agency_not_covered_in_local_extracts', 0) + counts.get('agency_or_project_scope_unclear', 0)
    topics = crosswalk.get('topics', [])
    later_only = sum(not row['stageCandidates']['NEP']['candidates'] and
                     any(row['stageCandidates'][stage]['candidates'] for stage in ('HGAB', 'SCR'))
                     for row in topics)
    all_stages = sum(all(row['stageCandidates'][stage]['candidates'] for stage in ('NEP', 'HGAB', 'SCR'))
                     for row in topics)
    reviewed = []
    reviewed_amounts = []
    for record in crosswalk.get('topics', []):
        trace = record.get('reviewedTrace')
        if not trace:
            continue
        cells = []
        reviewed_amounts.extend((f"{trace['title']} · {stage}", round(evidence['amountPesos'] / 1e6, 3))
                                for stage, evidence in trace['stages'].items() if evidence['amountPesos'] is not None)
        for stage in ('NEP', 'HGAB', 'SCR'):
            evidence = trace['stages'][stage]
            amount = evidence['amountPesos']
            label = 'No line identified' if amount is None else f'₱{amount:,}'
            url = evidence['url']
            cells.append(f'<td><a href="{escape(url, quote=True)}">{label}</a></td>' if url else f'<td>{label}</td>')
        source_links = ' · '.join(
            f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'
            for label, url in trace.get('additionalSources', {}).items()
        )
        source_html = f'<div class="notice">{source_links}</div>' if source_links else ''
        anchor = escape(record['topicId'].replace(':', '-'), quote=True)
        reviewed.append(
            f'<tr id="review-{anchor}"><th scope="row">{escape(trace["title"])}'
            f'<div class="notice">{escape(trace["label"])}</div></th>'
            f'<td>{escape(trace["hearing"])} <a href="{escape(trace["hearingUrl"], quote=True)}">'
            f'House video at {escape(trace["hearingTimestamp"])}</a></td>'
            + ''.join(cells) + f'<td>{escape(trace["finding"])}{source_html}</td></tr>'
        )
    bars = escape(json.dumps(reviewed_amounts, ensure_ascii=False), quote=True)
    reviewed_section = f'''<section class="card method" id="request-trace">
<h2>Source-reviewed hearing-to-budget traces</h2>
<p>EDSA Busway went from no dedicated appropriation in the executive proposal to ₱75 million in the House and ₱150 million in the Senate committee report. Safe Pathways already had executive funding and gained ₱71.512 million at committee. The committee also proposed ₱1 billion for zero-balance billing in LGU hospitals. The likely Damulog match moved in the opposite direction, with neither NEP component traced into the House schedule. None of these four records identifies the hearing as the cause of the change.</p>
<p>These traces connect specific hearing discussions to named budget lines. Evidence of attribution requires a committee or amendment record that makes the connection explicit. The amounts reflect proposals at each stage. These reviews can find links missed by the automated screen below. A sequence of changes cannot establish who secured an amendment.</p>
<figure class="answer-chart"><figcaption>Source-reviewed budget lines by stage · millions of pesos</figcaption><div id="hearing-budget-chart" data-bars="{bars}"></div></figure>
<div class="table-wrap"><table><thead><tr><th scope="col">Budget line</th><th scope="col">Hearing evidence</th><th scope="col">NEP</th><th scope="col">HGAB</th><th scope="col">SCR</th><th scope="col">Finding</th></tr></thead><tbody>{''.join(reviewed)}</tbody></table></div>
<p class="notice">Hearing wording comes from timestamped machine transcripts. Open the House video to check the audio before quoting it.</p>
</section>'''
    crosswalk_section = f'''<section class="card method" id="question-2"><h2>Question 2 · Budget-document screen · all {checked:,} topic records</h2>
<p>The automated screen compared every topic with <strong>{crosswalk.get('budgetRowCount', 0):,} locally available FY2027 stage-line records</strong> across NEP, HGAB and SCR. Project-level extracts cover DPWH, DA farm-to-market roads, DOH HFEP and NIA, including the NEP irrigation annex. Senate Annex A supplies cross-agency amendments and their comparison amounts. Other agency baselines are only partially represented.</p>
<p><strong>{crosswalk.get('candidateCount', 0):,} candidate stage rows</strong> passed the screen. The browser and both downloads include every retained candidate.</p>
<p>For {later_only} topics, candidates appear in the House bill or Senate report with no candidate in the executive proposal. Select “Later-stage leads only” to inspect them. Another {all_stages} topics have candidates at all three stages. A match at two stages can refer to different projects.</p>
<figure class="answer-chart"><figcaption>Hearing topics by budget-screen result</figcaption><div id="screening-chart" data-bars='[["Candidate leads",{candidate_count}],["No candidate",{no_candidate_count}],["Outside scope",{not_covered_count}]]'></div></figure>
<div class="crosswalk-metrics"><div><strong>{candidate_count:,}</strong><span>topics with automated leads</span></div><div><strong>{no_candidate_count:,}</strong><span>screened, with no candidate in available extracts</span></div><div><strong>{not_covered_count:,}</strong><span>agency or project scope not covered</span></div></div>
<p>This is an automated lexical screen, not a confirmed match audit. Candidates are leads, not proof of project identity or hearing influence; scores rank retrieval and are not probabilities. “No candidate” does not prove no budget link exists.</p>
<p><a href="questions-budget-crosswalk.csv" download>Download all topic results as CSV</a> · <a href="questions-budget-crosswalk.json" download>Download ranked candidates and evidence as JSON</a></p>
<details id="crosswalk-browser" open><summary>Browse every topic and all ranked candidates</summary><div class="crosswalk-controls"><input id="crosswalk-search" type="search" placeholder="Search topics, locations, projects or shared terms"><select id="crosswalk-class"><option value="">All screening results</option><option value="later">Later-stage leads only</option><option value="candidate_leads_need_review">Candidate leads</option><option value="no_candidate_in_available_extracts">No candidate in available extracts</option><option value="agency_not_covered_in_local_extracts">Agency not covered</option><option value="agency_or_project_scope_unclear">Agency or project scope unclear</option></select><span id="crosswalk-count" role="status"></span></div>
<div class="table-wrap"><table class="crosswalk-table"><thead><tr><th>Hearing topic</th><th>Screen result</th><th>NEP candidates</th><th>HGAB candidates</th><th>SCR candidates</th></tr></thead><tbody id="crosswalk-body"><tr><td colspan="5">Open this section to load the crosswalk.</td></tr></tbody></table></div></details></section>'''
    markup = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Questions in the FY2027 budget hearings · BetterGov</title>
<style>
:root{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#1c2935;background:#f4f7fa}}*{{box-sizing:border-box}}
body{{margin:0}}header{{background:#00246A;color:white;padding:34px max(20px,calc((100vw - 1120px)/2));border-bottom:6px solid #FCD116}}
header .eyebrow{{color:#FCD116;font-size:.76rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase}}
.question-nav{{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}}.question-nav a{{color:#fff;border:1px solid #b7c9e2;border-radius:6px;padding:7px 12px;text-decoration:none}}.question-nav a:hover{{background:#174580}}
header h1{{font-size:clamp(2rem,4vw,3.1rem);line-height:1.08;margin:.55rem 0}}
header p{{max-width:850px;color:#edf2fa;line-height:1.6}}main{{max-width:1120px;margin:auto;padding:22px 18px 60px}}
.hero{{padding:22px 25px;background:#fff;border:1px solid #d8e1ea;border-left:6px solid #087e78;border-radius:12px;margin:0 0 22px}}
.hero strong{{font-size:1.6rem;color:#0038A8}}.method,.filters{{background:white;border:1px solid #d8e1ea;border-radius:12px;padding:18px 20px;margin:18px 0}}
.filters{{display:flex;gap:12px;flex-wrap:wrap;align-items:end}}label{{display:grid;gap:5px;font-weight:700}}input,select{{font:inherit;padding:10px;border:1px solid #8b9aaa;border-radius:6px;min-width:220px}}
#count{{margin-left:auto;color:#52616e}}.topic{{background:white;border:1px solid #d8e1ea;border-radius:12px;padding:20px;margin:12px 0}}
.topic h3{{margin:7px 0;font-size:1.2rem}}.topic-meta{{font-size:.84rem;color:#52616e;font-weight:700;text-transform:uppercase;letter-spacing:.04em}}
.topic p{{line-height:1.6}}details{{border-top:1px solid #e1e7ed;padding:12px 0}}summary{{cursor:pointer;color:#0038A8;font-weight:700}}
li{{margin:7px 0;line-height:1.5}}a{{color:#0050ad}}.notice{{color:#5e6872;font-size:.92rem}}.crosswalk-metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px;margin:16px 0}}.crosswalk-metrics div{{background:#edf3f8;border-radius:8px;padding:14px}}.crosswalk-metrics strong{{display:block;color:#0038A8;font-size:1.4rem}}.crosswalk-metrics span{{display:block;font-size:.9rem}}.crosswalk-controls{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}.crosswalk-controls #crosswalk-count{{align-self:center;color:#52616e}}.crosswalk-table{{min-width:1150px;font-size:.9rem}}.candidate{{border-left:3px solid #087e78;padding:5px 8px;margin:6px 0;background:#f6f9fb}}.candidate small{{display:block;color:#52616e}}.screen-tag{{font-weight:700;color:#52616e}}
@media(max-width:600px){{input,select{{width:100%;min-width:0}}#count{{margin:0}}}}
table{{width:100%;border-collapse:collapse;margin:14px 0}}th,td{{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #d8e1ea}}th{{background:#edf3f8}}.table-wrap{{overflow:auto}}
</style></head><body><header><span class="eyebrow">Budget 2027 · House appropriations hearings</span><nav class="question-nav" aria-label="Questions"><a href="amendment-access.html">Question 1 · Infrastructure and access</a><a href="#question-2" aria-current="page">Question 2 · Hearings and budget lines</a><a href="contractor-workload.html">Question 3 · Contractor track records</a><a href="road-handover.html">Question 4 · Roads after handover</a></nav>
<h1>What was requested in the hearings, and where did it go?</h1>
<p>A source-linked index of questions, agency responses, spoken figures and committee actions from {len(hearings)} FY2027 budget hearing streams. Search all hearing topics and follow each ranked lead to the budget source.</p>
</header><main>
<section class="card hero"><strong>{len(hearings)} hearings · {data['topicCount']:,} topic records</strong>
<p>Start with a public request, check whether the project or amount already appears in the NEP, and trace any identifiable line through HGAB and SCR. Each link opens the recorded hearing or timestamp.</p></section>
<section class="card method"><h2>How to read this page</h2>
<p>Transcript summaries and speaker labels are machine-generated. Treat a topic as a lead into the source video, and verify exact wording before quoting it. A request does not establish that a later budget line resulted from that request. The matching stage must be checked against the published source documents.</p>
<p>Budget references: <a href="https://www.dbm.gov.ph/index.php/2027/national-expenditure-program-fy-2027">FY2027 NEP</a> · <a href="/static/nep-preview/dpwh-hgab.html">House bill analysis</a> · <a href="/static/nep-preview/scr.html">Senate committee report</a></p>
</section>
{reviewed_section}
{crosswalk_section}
<div class="filters"><label>Agency<select id="agency"><option value="">All agencies</option>{agency_options}</select></label>
<label>Search topics, requests and outcomes<input id="query" type="search" placeholder="Place, project, amount or issue"></label><span id="count"></span></div>
<section class="card" id="records"><h2>Hearing source records</h2><div class="table-wrap"><table><thead><tr><th>Topic and source evidence</th></tr></thead><tbody id="hearing-records">{body}</tbody></table></div></section>
<p><a href="amendment-access.html">What would the Bolinao bridge change?</a></p>
<p class="notice">Downloaded {escape(data['retrievedAt'])} from the public BetterGov Philippine Budget Data API. HFEP augmented facility/resource catalogs were downloaded from hfep.simple-systems.dev on 2026-11-28. {len(hearings)} FY2027 House Committee on Appropriations hearings; source snapshots are saved with this page’s builder.</p>
</main><script>
const agency=document.querySelector('#agency'),query=document.querySelector('#query'),cards=[...document.querySelectorAll('.topic')],count=document.querySelector('#count'),records=document.querySelector('#hearing-records');
function update(){{const shown=cards.filter(card=>(!agency.value||card.dataset.agency===agency.value)&&(!query.value||card.dataset.search.includes(query.value.toLocaleLowerCase())));records.replaceChildren(...shown);count.textContent=shown.length+' topic records'}}
agency.onchange=query.oninput=update;update();
const crosswalk=document.querySelector('#crosswalk-browser');let crosswalkRows=[];const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function drawCrosswalk(){{if(!crosswalkRows.length)return;const q=document.querySelector('#crosswalk-search').value.toLowerCase(),cl=document.querySelector('#crosswalk-class').value;const list=crosswalkRows.filter(r=>(!cl||r.classification===cl||(cl==='later'&&!r.stageCandidates.NEP.candidates.length&&(r.stageCandidates.HGAB.candidates.length||r.stageCandidates.SCR.candidates.length)))&&(!q||[r.topic,r.summary,r.question,r.agency,...Object.values(r.stageCandidates).flatMap(s=>s.candidates.flatMap(c=>[c.title,...c.sharedTerms,c.place]))].join(' ').toLowerCase().includes(q)));document.querySelector('#crosswalk-count').textContent=`${{list.length}} topic records`;document.querySelector('#crosswalk-body').innerHTML=list.map(r=>{{const stage=s=>{{const cs=r.stageCandidates[s].candidates;return cs.length?cs.map(c=>`<div class="candidate"><a href="${{esc(c.sourceUrl||'#')}}" target="_blank" rel="noopener">${{esc(c.title)}} ↗</a><small>${{esc(c.sector==='CROSS_AGENCY'?'Senate Annex A · '+c.place:c.sector)}} · ${{c.amountPesos==null?'amount unavailable':'₱'+Number(c.amountPesos).toLocaleString()}} · score ${{c.score}} · terms: ${{esc(c.sharedTerms.join(', '))}}${{c.budgetStatus?' · '+esc(c.budgetStatus):''}}</small></div>`).join(''):'<span class="screen-tag">No candidate surfaced</span>'}};return `<tr><td><strong>${{esc(r.topic)}}</strong><small>${{esc(r.agency)}} · ${{esc(r.hearingDate||'')}} · <a href="${{esc(r.hearingUrl)}}" target="_blank" rel="noopener">hearing record ↗</a></small></td><td><span class="screen-tag">${{esc(r.classification.replaceAll('_',' '))}}</span>${{r.reviewedTrace?' <a href="#review-'+esc(r.topicId.replace(':','-'))+'">Read source review</a>':''}}</td><td>${{stage('NEP')}}</td><td>${{stage('HGAB')}}</td><td>${{stage('SCR')}}</td></tr>`}}).join('')||'<tr><td colspan="5">No topic records match these filters.</td></tr>'}}
async function loadCrosswalk(){{if(crosswalk.open&&!crosswalkRows.length){{try{{const res=await fetch('questions-budget-crosswalk.json');if(!res.ok)throw new Error(res.status);crosswalkRows=(await res.json()).topics;drawCrosswalk()}}catch(e){{document.querySelector('#crosswalk-body').innerHTML='<tr><td colspan="5">Could not load crosswalk data. Use the JSON download link above.</td></tr>'}}}}}}
crosswalk.addEventListener('toggle',loadCrosswalk);loadCrosswalk();document.querySelector('#crosswalk-search').oninput=drawCrosswalk;document.querySelector('#crosswalk-class').onchange=drawCrosswalk;
</script></body></html>'''
    return render_report(markup, 'questions.html')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-hearings', action='store_true', help='Refresh the hearing index from BetterGov')
    args = parser.parse_args()
    snapshot = DATA_DIR / 'hearings-fy2027.json'
    data = download() if args.refresh_hearings or not snapshot.exists() else json.loads(snapshot.read_text(encoding='utf-8'))
    import build_questions_budget_crosswalk
    build_questions_budget_crosswalk.main()
    crosswalk = json.loads((ROOT / 'analysis_output' / 'questions-budget-crosswalk.json').read_text(encoding='utf-8'))
    page = render(data, crosswalk)
    STATIC.mkdir(parents=True, exist_ok=True)
    (STATIC / 'questions.html').write_text(page, encoding='utf-8')
    (ROOT / 'analysis_output' / 'questions.html').write_text(page, encoding='utf-8')
    print(f"Loaded {data['hearingCount']} hearings and {data['topicCount']} topics")
    print(f"Wrote {STATIC / 'questions.html'}")


if __name__ == '__main__':
    main()
