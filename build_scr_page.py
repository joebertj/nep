#!/usr/bin/env python3
"""Build the FY2027 Senate Committee Report stage comparison and impact audit."""
import csv, hashlib, json, html
from pathlib import Path
import re, unicodedata

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUT = ROOT / 'analysis_output'
DATA = ROOT / 'data_sources/senate-2027-dataset'

PAGES = [
    ('documents.html', 'Proposal + HGAB document inventory', 'High', 'The document-type totals are aggregate rows and should not get a project disposition. Add SCR columns only to project-level tables that expose a reliable project title; do not infer that a missing file is resolved by an SCR cut.'),
    ('dpwh.html', 'DPWH HGAB projects and documents', 'Highest priority', 'The all-project coverage table and POW line items expose DPWH project titles. Add the SCR column on uniquely matched project rows; keep document-presence findings separate from SCR budget disposition.'),
    ('nia.html', 'NIA irrigation and named projects', 'High', 'Add SCR disposition where a project title joins uniquely. Location and workbook review tables remain NIA-specific evidence and should keep their existing flags.'),
    ('fmr.html', 'FMR coordinate and manual review', 'High', 'The project tables can join to the FMR schedule. The manual red-flag list has a defensible SCR overlap for a removed-row summary; coordinate concerns remain evidence about the House version.'),
    ('dpwh-transparency.html', 'DPWH Transparency inventory', 'Conditional', 'The inventory is not a direct budget-stage table. Add row-level SCR only where the inventory project title and allocation identify one DPWH report row.'),
    ('congress.html', 'Project flags and district allocations', 'High', 'Aggregate district totals cannot take a project SCR column. Project-detail rows can be annotated when title joins uniquely; do not imply that district attribution establishes sponsorship.'),
    ('flags.html', 'Flag index', 'Highest priority', 'Join the row-level flagged project list to SCR by title and amount. The hero can count matched flagged lines removed, while each flag and its historical HGAB basis stays visible.'),
    ('undocumented-hgab.html', 'Undocumented HGAB', 'High', 'Project rows can show whether the House line remains in SCR. A cut changes the later-stage allocation status; it does not retroactively supply missing House documents.'),
    ('repeats.html', 'Project repeats', 'Medium', 'Annotate each matched project occurrence in a pair row. A removal changes stage survival but does not establish that the pair was a duplicate.'),
    ('out-of-place.html', 'Out of Place', 'High', 'The selected-project card can show its SCR disposition. The hero can summarize removed coordinate-review rows and their gross House value; this does not erase the original location signal.'),
    ('cost-per-km.html', 'Cost per meter', 'High', 'The 191 high-rate scope-review candidates can be joined to DPWH SCR rows. The hero can sum gross House allocations for candidates labeled Removed; this is not net or realized savings.'),
    ('pccp-cost-per-unit.html', 'Cost per Unit · DPWH Atlas', 'Conditional', 'Add a project SCR column to identifiable project rows; keep material/benchmark comparisons separate from Senate allocation changes.'),
    ('cost-per-unit.html', 'Cost per Unit · peer comparison', 'Conditional', 'Project-and-office rows can show SCR disposition when the budget row is identifiable. Unit-cost comparisons need scope and quantity checks before a cut is called savings.'),
    ('cmpd-cost-per-unit.html', 'CMPD · cost per unit', 'Conditional', 'POW project rows can receive an SCR link only where the project name uniquely matches. Office material-price references are not Senate project rows.'),
    ('expectation-vs-reality.html', 'Costing vs proposed allocation', 'High', 'Project rows can show SCR title and allocation changes where they join uniquely. Keep estimate-to-allocation differences distinct from SCR removals.'),
    ('rcs.html', 'RCS project scope', 'Conditional', 'Add SCR disposition to identifiable DPWH project rows; RCS scope status alone does not show that a budget change resolves the scope review.'),
    ('mpb.html', 'MPB flags', 'High', 'Project-level location and source rows can show SCR status where matched. A Senate cut changes the later-stage budget line, not the observed geographic evidence.'),
    ('barangay.html', 'Barangay allocations', 'Conditional', 'A barangay aggregate is not a project-level SCR row. Add the column only in project-detail rows with a reliable title match.'),
]

def load_csv(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def money(v):
    try: return int(float(v or 0))
    except (ValueError, TypeError): return 0

def peso(v): return '₱' + format(round(v), ',')

def norm_title(value):
    value=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+',' ',value).strip()

def comparison_payload(rows):
    columns = (
        'program', 'id', 'house_id', 'status', 'status_label', 'title', 'house_title',
        'region', 'office', 'pap', 'nep_php', 'house_php', 'senate_php', 'check_note',
        'senate_pdf_url', 'senate_page', 'matched_by', 'nep_pdf_url', 'nep_page',
        'house_pdf_url', 'house_page', 'page_url',
    )
    values = {}
    packed_rows = [[values.setdefault(row[key], len(values)) for key in columns] for row in rows]
    return json.dumps(
        {'columns': columns, 'values': list(values), 'rows': packed_rows},
        ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')

def load_optional_json(name):
    for path in (STATIC/name,OUT/name):
        if path.exists():
            try: return json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError): return None
    return None

def overlap_summary(source_rows,scr_rows,program,title_key,amount_key,title,value_label,note,filter_row=None):
    by_title={}
    for row in scr_rows:
        if row['program']!=program: continue
        aliases={norm_title(row.get('house_title')),norm_title(row.get('title'))}-{''}
        for alias in aliases:
            if len(alias)>=18: by_title.setdefault(alias,[]).append(row)
    matched=[]; examined=0
    for source in source_rows:
        if filter_row and not filter_row(source): continue
        examined+=1
        key=norm_title(source.get(title_key))
        candidates={r['id']:r for r in by_title.get(key,[])}
        if len(candidates)>1:
            value=money(source.get(amount_key))
            candidates={rid:r for rid,r in candidates.items() if money(r.get('house_php'))==value or money(r.get('senate_php'))==value}
        if len(candidates)==1: matched.append((source,next(iter(candidates.values()))))
    removed=[pair for pair in matched if pair[1]['status']=='cut']
    return {'title':title,'sourceRows':examined,'matchedCount':len(matched),
        'removedCount':len(removed),'removedGross':sum(abs(money(r.get('house_php'))) for _,r in removed),
        'valueLabel':value_label,'note':note}

def build_page_summaries(scr_rows,by_program):
    summaries={}
    cost=load_optional_json('cost-per-km-data.json')
    if cost:
        summaries['cost-per-km.html']=overlap_summary(cost.get('projects',[]),scr_rows,'dpwh','projectName','amountPesos',
            'SCR · high-rate scope-review candidates','Potential gross savings from removed candidates',
            'Only high-rate candidates listed on this page are counted. Removed House lines are absent from SCR; this is not net or realized savings.',
            lambda r:r.get('rateReview')=='High relative rate · scope review needed')
    oop=load_optional_json('out-of-place-data.json')
    if oop:
        summaries['out-of-place.html']=overlap_summary(oop.get('projects',[]),scr_rows,'dpwh','projectName','amountPesos',
            'SCR · coordinate-review projects','Gross House allocation removed',
            'This counts only the page’s coordinate-review projects. The location signal remains part of the HGAB record; removal changes the later-stage budget status.')
    flags=load_optional_json('flags-data.json')
    if flags:
        summaries['flags.html']=overlap_summary(flags.get('projects',[]),scr_rows,'dpwh','title','amountPesos',
            'SCR · matched flagged House rows','Gross House allocation removed',
            'This summary covers exact-title matches in the flag index. It does not erase the historical HGAB flag or classify every flag as resolved.')
    fmr=load_optional_json('fmr-manual-red-flags.json')
    if fmr:
        summaries['fmr.html']=overlap_summary(fmr.get('projects',[]),scr_rows,'fmr','title','amountPesos',
            'SCR · manual FMR red-flag list','Gross House allocation removed',
            'Counts only projects listed in the manual red-flag table. Coordinate or manual-review evidence remains part of the HGAB-stage record.')
    documents=load_optional_json('hgab-document-coverage.json')
    if documents:
        def proposal_types(source):
            aliases={'pow':'POW','program of works':'POW','program of work':'POW',
                'bp 202':'BP 202','bp202':'BP 202','development council':'Development Council',
                'rdc':'Development Council','pdc':'Development Council','ldc':'Development Council',
                'photos':'Geotagged photos','photo':'Geotagged photos',
                'geotagged photos':'Geotagged photos','geotagged photo':'Geotagged photos',
                'certificate':'Certificate of Implementability',
                'certificate of implementability':'Certificate of Implementability',
                'implementability certificate':'Certificate of Implementability',
                'cert of implementability':'Certificate of Implementability'}
            result=set()
            for value in source.get('proposalDocumentTypes') or []:
                key=' '.join(str(value or '').strip().casefold().split())
                if key in aliases: result.add(aliases[key])
            return result
        named_types={'POW','BP 202','Development Council','Geotagged photos','Certificate of Implementability'}
        summaries['documents.html']=overlap_summary(documents.get('projects',[]),scr_rows,'dpwh','title','amountPesos',
            'SCR · rows with Proposal document-type gaps','Gross House allocation removed in SCR',
            'Each House project row is counted once even when multiple Proposal document types are missing. Only reliable title-and-amount SCR matches are included; gross House allocations are not net or realized savings.',
            lambda row: bool(named_types-proposal_types(row)))
    for page,program in (('dpwh.html','dpwh'),('nia.html','nia')):
        a=by_program.get(program,{})
        summaries[page]={'title':f"SCR · {program.upper()} schedule changes",'sourceRows':a.get('rows',0),
            'matchedCount':a.get('rows',0),'removedCount':a.get('cut',0),'removedGross':a.get('grossCut',0),
            'valueLabel':'Gross House allocation on rows Removed in SCR',
            'note':'Schedule-wide context, not a sum of the page’s document or location flags. It is not net or realized savings.'}
    # Pages whose principal views are aggregates should use the matching full
    # schedule aggregate, rather than imply that a district or price row owns a
    # project disposition.
    return summaries

def build():
    rows = load_csv('senate-2027-projects.csv')
    summary_rows = load_csv('senate-2027-general-summary.csv')
    checks = load_csv('senate-2027-checks.csv')
    provisions = load_csv('senate-2027-provisions.csv')
    annex = load_csv('senate-2027-annex-a.csv')
    by_program = {}
    for r in rows:
        prog = r['program']; agg = by_program.setdefault(prog, {'rows':0,'changed':0,'cut':0,'added':0,'raised':0,'reduced':0,'restored':0,'renamed':0,'unchanged':0,'nep_only':0,'grossCut':0,'grossAdded':0,'grossRaised':0,'grossReduced':0})
        agg['rows'] += 1
        st = r['status']
        if st in agg: agg[st] += 1
        if st not in ('unchanged','nep_only'): agg['changed'] += 1
        if st == 'cut': agg['grossCut'] += abs(money(r['house_php']))
        if st in ('added','restored'): agg['grossAdded'] += money(r['senate_php'])
        if st == 'raised': agg['grossRaised'] += max(0, money(r['senate_php']) - money(r['house_php']))
        if st == 'reduced': agg['grossReduced'] += max(0, money(r['house_php']) - money(r['senate_php']))
    removed_savings = sum(abs(money(r['house_php'])) for r in rows if r['status'] == 'cut')
    # Only the four annexed schedules have row-level projects in the dataset.
    slim = []
    for r in rows:
        slim.append({k:r.get(k,'') for k in ('program','id','house_id','status','status_label','title','house_title','region','office','program_line','pap','nep_php','house_php','senate_php','vs_house_php','vs_nep_php','inserted_by_house','replaces_id','senate_doc','senate_page','senate_pdf_url','house_doc','house_page','house_pdf_url','nep_doc','nep_page','nep_pdf_url','page_url','matched_by','check_id','check_note')})
    page_summaries=build_page_summaries(rows,by_program)
    data = {'source':'data_sources/senate-2027-dataset','rows':slim,
            'pageSummaries':page_summaries}
    summary_by_dept=[]
    for r in summary_rows:
        if r['level'] in ('department','total'):
            summary_by_dept.append({'level':r['level'],'department':r['department'],'nep':money(r['nep_php']),'house':money(r['house_php']),'net':money(r['net_php']),'senate':money(r['house_php'])+money(r['net_php'])})
    # Keep exact check results accessible as source-quality context.
    checks_ok=sum(1 for c in checks if str(c['ok']).lower() in ('true','1','yes'))
    dpwh_tot=next((r for r in summary_by_dept if r['department']=='DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS'),{})
    audit_html=''.join('<tr><td><a href="'+html.escape(path)+'">'+html.escape(path)+'</a><br>'+html.escape(label)+'</td><td>'+html.escape(priority)+'</td><td>'+html.escape(note)+'</td></tr>' for path,label,priority,note in PAGES)
    savings_card=f'<article class="stat savings-stat"><small>SAVINGS · REMOVED LINES</small><strong>{peso(removed_savings)}</strong><span>Gross House allocations on project rows labeled Removed</span><span>Not the General Summary net change or realized savings</span></article>'
    cards=savings_card+''.join(f'<article class="stat"><small>{p.upper()}</small><strong>{a["rows"]:,}</strong><span>rows · {a["changed"]:,} not unchanged/NEP-only</span><span>{a["cut"]:,} cuts · {a["added"]:,} additions · {a["restored"]:,} restored</span></article>' for p,a in sorted(by_program.items()))
    comparison = comparison_payload(slim)
    comparison_version = hashlib.sha256(comparison).hexdigest()[:12]
    comparison_script = (ROOT/'report_assets/scr_project_comparison.js').read_bytes()
    comparison_script_version = hashlib.sha256(comparison_script).hexdigest()[:12]
    page=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>FY2027 Senate Committee Report · NEP → HGAB → SCR</title><style>
 :root{{--ink:#212121;--muted:#616161;--line:#E0E0E0;--paper:#F5F5F5;--green:#0038A8;--red:#a52c25;--amber:#8a5a00}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,sans-serif}}main{{max-width:1240px;margin:auto;padding:24px}}h1{{font-size:clamp(30px,5vw,48px);line-height:1.08;margin:.3em 0}}h2{{font-size:24px;margin:0 0 10px}}h3{{font-size:18px;margin:0 0 8px}}p{{margin:.4em 0 1em}}.eyebrow{{color:var(--green);font-weight:750;letter-spacing:.07em;text-transform:uppercase}}.lead{{font-size:18px;max-width:900px;color:#344238}}.hero,.card{{background:white;border:1px solid var(--line);border-radius:14px;padding:20px;margin:18px 0}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:18px 0}}.stat{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:15px;display:flex;flex-direction:column}}.stat strong{{font-size:30px}}.stat small{{color:var(--green);font-weight:750}}.stat span,.muted{{color:var(--muted)}}.metric{{font-size:28px;font-weight:800}}.rules{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}}.rule{{border:1px solid var(--line);border-radius:10px;padding:14px}}.green{{color:var(--green)}}.red{{color:var(--red)}}.amber{{color:var(--amber)}}.controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:12px 0}}input,select,button{{font:inherit;padding:9px 11px;border:1px solid #BDBDBD;border-radius:8px;background:#fff}}input{{min-width:240px;flex:1}}button{{cursor:pointer}}.tablewrap{{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:8px}}table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}th,td{{padding:9px 10px;border-bottom:1px solid #E0E0E0;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#EAF0FF;color:#00246A;z-index:1}}td.amount,th.amount{{text-align:right;white-space:nowrap}}.pill{{display:inline-block;padding:2px 8px;border-radius:30px;background:#F5F5F5;font-size:12px;font-weight:700}}.pill.cut,.pill.added,.pill.raised,.pill.reduced{{background:#fbe9e7;color:var(--red)}}.pill.restored,.pill.renamed{{background:#e4f4e9;color:var(--green)}}.note{{border-left:4px solid #FCD116;padding:10px 14px;background:#fff9e8}}a{{color:#0038A8}}.small{{font-size:13px}}@media(max-width:640px){{main{{padding:14px}}.tablewrap{{max-height:65vh}}}}
</style></head><body><header class="hero"><div class="eyebrow">FY2027 · Next budget stage</div><h1>NEP → HGAB → Senate committee report</h1><p class="lead">Compare House bill rows against the Senate Committee on Finance’s report on HB 10858. Continue the evidence trail toward GAB, Bicam and GAA while keeping each version distinct.</p><p class="note"><strong>Under citizen review.</strong> This is an unofficial reading of the Senate report. Open the cited report page before relying on a row. Appropriations at different stages are versions of one budget; never add them together.</p></header><main>
<section class="stats">{cards}</section><section class="card"><h2>What the report changes at a glance</h2><p>Across the four detailed schedules, project rows labeled <strong>Removed</strong> sum to <strong>{peso(removed_savings)}</strong> in gross House allocations. DPWH accounts for {by_program.get('dpwh',{}).get('cut',0):,} removed rows and <strong>{peso(by_program.get('dpwh',{}).get('grossCut',0))}</strong> of that amount. This “Savings” figure is the value of lines removed from the House schedule; it is not a net budget reduction or realized savings, since other lines may be added, restored, renamed or increased.</p><p>Separately, DPWH’s General Summary allocation moves from <strong>{peso(dpwh_tot.get('house',0))}</strong> in the House bill to <strong>{peso(dpwh_tot.get('senate',0))}</strong> in the Senate report: net <strong class="red">{peso(dpwh_tot.get('net',0))}</strong>. The dataset has <strong>{len(rows):,} project rows</strong>, {len(annex):,} Annex A rows, {len(provisions):,} Annex B provision amendments, and {checks_ok}/{len(checks)} listed checks passing. Source definitions, caveats and documents are recorded in the supplied dataset README.</p></section>
<section class="card"><h2>How SCR changes should affect existing flags</h2><div class="rules"><div class="rule"><h3 class="green">Green · resolved or corrected</h3><p>Keep the original HGAB flag and add an SCR note when the cited Senate change directly resolves it: for example, the line is cut, a title/location is corrected, or the amount/scope concern is explicitly corrected. The note should cite the SCR page and say what changed.</p></div><div class="rule"><h3 class="red">Red · new or worse</h3><p>Add a red flag when SCR adds a project that triggers an existing flag rule, or when a Senate revision introduces or strengthens a concern (such as a larger amount, broader scope or a new location/attribution issue). Cite the report page and state the rule triggered.</p></div><div class="rule"><h3 class="amber">Review · stage change alone</h3><p>A cut, rename, addition or increase is not automatically a finding. Match the row to the original flag and its rule first. Preserve historical HGAB evidence, then annotate the later status so the reader can see how the finding changed over time.</p></div></div><p class="small muted">This page marks stage disposition from the published dataset. It does not automatically claim that any specific existing flag is invalid or newly substantiated; that requires a defensible row-to-flag match.</p></section>
<section class="card"><h2>Which analyses can benefit from SCR</h2><p>Prioritized by schedule coverage and whether a later-stage row can change the evidence behind a flag.</p><div class="tablewrap"><table><thead><tr><th>Page</th><th>Priority</th><th>Potential SCR comparison</th></tr></thead><tbody>{audit_html}</tbody></table></div></section>
<section class="card" id="scr-project-comparison" data-source="scr-project-comparison.json?v={comparison_version}"><h2>Project row comparison</h2><p>Search Senate, House or NEP title and row identifiers. By default, unchanged and NEP-only rows are hidden so review focuses on SCR-stage changes. Every displayed row retains source page links for all available stages. Savings counts a row’s House allocation only when the SCR labels it Removed; it is not the net budget change.</p><div class="controls"><input id="q" disabled type="search" placeholder="Search project, office, region, ID…"><select id="program" disabled><option value="">All schedules</option><option value="dpwh">DPWH</option><option value="fmr">FMR</option><option value="nia">NIA</option><option value="hfep">HFEP</option></select><select id="status" disabled><option value="changed">Changed / reviewed rows</option><option value="all">All rows</option><option value="cut">Removed</option><option value="added">Added</option><option value="restored">Restored</option><option value="renamed">Renamed</option><option value="raised">Raised</option><option value="reduced">Reduced</option><option value="unchanged">Unchanged</option><option value="nep_only">NEP only</option></select><span id="count" aria-live="polite">Project rows load as you reach this section.</span><button id="scr-retry" type="button" hidden>Retry loading project rows</button></div><div class="tablewrap"><table data-native-pagination="true"><thead><tr><th>Schedule / status</th><th>Senate report title</th><th>House bill title</th><th>Office / region</th><th class="amount">NEP</th><th class="amount">House</th><th class="amount">Senate</th><th class="amount">Savings · Removed</th><th>SCR evidence</th><th>Stage sources</th></tr></thead><tbody id="rows"></tbody></table></div><div class="controls"><button id="prev" disabled>Previous</button><span id="page"></span><button id="next" disabled>Next</button></div><p class="small muted">Rows shown <span id="range"></span>. Amounts are pesos. A blank amount means the source dataset does not supply one for that stage.</p></section>
<section class="card"><h2>Sources and method</h2><p>The data comes from the supplied <code>senate-2027-dataset</code> package. It covers Senate project schedules for DPWH, DA farm-to-market roads, DOH HFEP and NIA; it is not a complete row-level transcription of every department. Department-wide amounts come from the report’s General Summary. Status and matching conventions are defined in the linked README.</p><p>Source validation recorded by the build: {checks_ok} of {len(checks)} checks pass; the README records page-level misses and describes the remaining review needed. The report pages are evidence references, not proof of implementation or spending.</p></section>
</main><script src="scr-project-comparison.js?v={comparison_script_version}" defer></script></body></html>'''
    STATIC.mkdir(parents=True,exist_ok=True); OUT.mkdir(parents=True,exist_ok=True)
    from uniform_report_menu import apply_page as apply_uniform_menu
    from report_table_presentation import apply_page as apply_table_presentation, publish_assets
    page=apply_uniform_menu(page,'scr.html')
    page=apply_table_presentation(page,publish_assets(),'scr.html')
    serialized=json.dumps(data,ensure_ascii=False,separators=(',',':'))
    (STATIC/'scr-project-comparison.json').write_bytes(comparison)
    (OUT/'scr-project-comparison.json').write_bytes(comparison)
    for folder in (STATIC, OUT):
        (folder/'scr-project-comparison.js').write_bytes(comparison_script)
    (STATIC/'scr.html').write_text(page,encoding='utf-8')
    (OUT/'scr.html').write_text(page,encoding='utf-8')
    (STATIC/'scr-data.json').write_text(serialized,encoding='utf-8')
    (OUT/'scr-data.json').write_text(serialized,encoding='utf-8')
    from scr_page_shard_builder import refresh_all_pages
    page_shards=refresh_all_pages()
    print(json.dumps({'page':str(OUT/'scr.html'),'publishedPage':str(STATIC/'scr.html'),'projects':len(rows),'checksPassed':checks_ok,'checksTotal':len(checks),'programs':by_program,'pageShards':page_shards},ensure_ascii=False))

if __name__=='__main__': build()
