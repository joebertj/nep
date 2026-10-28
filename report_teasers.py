"""Neutral, attention-grabbing header questions answered by existing data-led heroes."""
import html,re
TEASERS={
 'summary.html':'Where should budget investigators look first?',
 'index.html':'Where should budget investigators look first?',
 'congress.html':'Which flagged projects are tied to each district?',
 'dpwh.html':'What makes up a project’s cost?',
 'dpwh-hgab.html':'How many House budget lines lack a plausible NEP counterpart?',
 'dpwh-hgab-comparison.html':'What appears only in the House’s third-reading extraction?',
 'repeats.html':'How often do project titles and segments resurface?',
 'mpb.html':'How many building allocations lack a plausible NEP counterpart?',
 'cost-per-km.html':'Which projects stand out on cost per meter?',
 'cost-matching.html':'Can asset records recover missing length information?',
 'rcs.html':'Did 199 offices really get the same RCS package?',
 'fmr.html':'More farm roads in the House budget?',
 'nia.html':'What changed in irrigation and named-project allocations?',
 'nia-irrigation.html':'Did the detailed irrigation annex grow in the House?',
 'hfep.html':'What happened to the health-facility capital budget?',
 'deped.html':'Can we tell whether school allocations changed?',
 # This is a utility view, not a finding. Keep its teaser slot reserved.
 'project-documents.html':'',
}
HEADLINES={
 'congress.html':'mapped flagged projects to review',
 'dpwh-hgab.html':'domestic candidates needing counterpart verification',
 'repeats.html':'NEP–GAA comparison pairs to verify',
 'budget-innovations.html':'budget terms flagged as potentially new or revived',
}
TEASERS['budget-innovations.html']='New budget labels—or old ideas returning?'

def apply_page(text,page):
    if page not in TEASERS:return text
    header=re.search(r'<header\b[^>]*>.*?</header>',text,re.S)
    if not header:return text
    first=re.search(r'<p\b[^>]*>.*?</p>',header[0],re.S)
    if not first:return text
    old=first[0];question=TEASERS[page]
    replacement='<p class="report-header-teaser">'+html.escape(question)+'</p>'
    revised=header[0][:first.start()]+replacement+header[0][first.end():]
    text=text[:header.start()]+revised+text[header.end():]
    if 'report-header-teaser' not in old and re.sub('<[^>]+>','',old).strip():
        context='<p class="report-page-context">'+re.sub(r'^<p\b[^>]*>|</p>$','',old)+'</p>'
        notes=re.search(r'<div id="report-header-notes"[^>]*>(.*?)</div>',text,re.S)
        if notes:text=text[:notes.end()-6]+context+text[notes.end()-6:]
        else:
            index=text.rfind('</footer>')
            if index>=0:text=text[:index]+'<div id="report-header-notes">'+context+'</div>'+text[index:]
    if page in HEADLINES:
        # Replace only the first hero headline, preserving live numbers, scope notes,
        # comparison denominators and every supporting table.
        pattern=r'(<div class="repeat-hero-total">\s*<strong>.*?</strong>\s*<span>).*?(</span>)'
        text=re.sub(pattern,lambda m:m[1]+html.escape(HEADLINES[page])+m[2],text,count=1,flags=re.S)
    return text
