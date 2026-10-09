#!/usr/bin/env python3
"""Apply the shared lead finding card to all local NEP preview reports."""

from __future__ import annotations

import json
import argparse
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "open-data-visualization" / "static" / "nep-preview"

STYLE = """<style id="report-hero-style">
.repeat-hero{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(320px,.95fr);gap:26px;align-items:stretch;margin:20px 0 24px;padding:clamp(22px,3vw,36px);border-radius:18px;border-left:8px solid #e5b64b;background:linear-gradient(120deg,#102f3e 0%,#174b55 58%,#087e78 100%);color:#fff;box-shadow:0 16px 38px #102f3e26}.repeat-hero-primary,.repeat-hero-detail{min-width:0}.repeat-hero-kicker{display:block;color:#b8e5da;font-size:12px;font-weight:800;letter-spacing:.13em;text-transform:uppercase}.repeat-hero-total{display:flex;align-items:baseline;flex-wrap:wrap;gap:12px;margin:10px 0 8px}.repeat-hero-total strong{font-size:clamp(48px,7vw,78px);line-height:.98;letter-spacing:-.055em;color:#f2c968}.repeat-hero-total span{max-width:500px;font-size:clamp(19px,2.4vw,28px);line-height:1.12;font-weight:760}.repeat-hero-cost{display:flex;align-items:baseline;flex-wrap:wrap;gap:10px;margin-top:14px}.repeat-hero-cost strong{font-size:clamp(24px,3vw,34px);letter-spacing:-.035em}.repeat-hero-cost span{color:#d7e6e4;font-size:14px}.repeat-hero-breakdown{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.repeat-hero-breakdown>div{display:flex;flex-direction:column;gap:5px;min-height:106px;padding:16px;border:1px solid #ffffff35;border-radius:12px;background:#ffffff12}.repeat-hero-breakdown span{color:#e4efed;font-size:13px;line-height:1.3}.repeat-hero-breakdown strong{font-size:25px;line-height:1.1}.repeat-hero-breakdown small{color:#c0d4d1;font-size:12px}.repeat-hero-detail>p{margin:14px 0 0;color:#e0ecea;font-size:13px;line-height:1.5}.repeat-hero h2{margin:0;color:#fff}@media(max-width:760px){.repeat-hero{grid-template-columns:1fr;gap:18px}.repeat-hero-breakdown>div{min-height:90px}}
#congress-main{width:100%;max-width:none;margin:0;padding:24px clamp(16px,2vw,32px)}
</style>"""


def read(name: str) -> dict:
    return json.loads((STATIC / name).read_text(encoding="utf-8"))


def peso(n: int) -> str:
    return f"₱{n / 1_000_000_000:,.2f}B" if n >= 1_000_000_000 else f"₱{n / 1_000_000:,.1f}M" if n >= 1_000_000 else f"₱{n:,.0f}"


def hero(kicker: str, number: str, headline: str, amount: str, amount_label: str,
         cards: list[tuple[str, str, str]], note: str) -> str:
    details = "".join(f"<div><span>{label}</span><strong>{value}</strong><small>{caption}</small></div>" for label, value, caption in cards)
    return (f'<div class="repeat-hero" aria-label="Key finding"><div class="repeat-hero-primary">'
            f'<span class="repeat-hero-kicker">{kicker}</span><div class="repeat-hero-total"><strong>{number}</strong><span>{headline}</span></div>'
            f'<div class="repeat-hero-cost"><strong>{amount}</strong><span>{amount_label}</span></div></div>'
            f'<div class="repeat-hero-detail"><div class="repeat-hero-breakdown">{details}</div><p>{note}</p></div></div>')


def make_heroes() -> dict[str, str]:
    dpwh = read("dpwh-data.json")
    repeat_rows = dpwh["priorityRepeats"]
    distinct_repeat_rows = {x["source_code"]: x for x in repeat_rows}
    repeat_total = sum(int(x.get("amount_2027") or 0) for x in distinct_repeat_rows.values())
    insertion_rows = dpwh["hbInsertions"]
    insertion_total = sum(int(x.get("amountPesos") or 0) for x in insertion_rows)
    summary3 = dpwh["hbInsertions3rdSummary"]
    counts3 = summary3["counts"]
    ambiguous = counts3.get("Multiple or already paired NEP counterparts; review scope", 0)

    rev = read("hgab-revision-data.json")
    def revision(key: str) -> dict:
        return rev[key]["summary"]
    fmr, nia, hfep = revision("fmr"), revision("nia_named"), revision("hfep")
    ir = read("nia-irrigation-data.json")["revision"]["summary"]
    deped = read("deped-data.json")["summary"]
    comparison = read("dpwh-hgab-comparison.json")["summary"]
    rcs = read("rcs-data.json")["summary"]
    innovations = read("budget-innovations-data.json")
    kws = innovations["potentialKeywords"]
    potential = sum(x.get("keywordStatus") == "Potential first appearance" for x in kws)
    revived = sum(x.get("keywordStatus") == "Revived" for x in kws)
    top_kw = kws[0]
    congress = read("congress-data.json")["summary"]

    return {
        "dpwh.html": hero("FY2027 NEP vs enacted DPWH GAA", "737", "potential repeat matches", peso(repeat_total), "FY2027 NEP allocation across distinct matched lines", [
            ("283 matches vs FY2026 GAA", "₱5.88B", "enacted allocations"), ("454 matches vs FY2025 GAA", "₱13.11B", "enacted allocations")],
            "51 FY2027 NEP lines match both GAA years. Totals are screened allocations, not confirmed duplicate costs. Bridge chainage must overlap; missing chainage remains flagged for review."),
        "dpwh-hgab.html": hero("DPWH · FY2027 NEP to 3rd-reading HGAB", f"{len(insertion_rows):,}", "Potential domestic insertions · HGAB-only line items", peso(insertion_total), "allocation across the domestic review shortlist", [
            ("All 3rd-reading DPWH lines", f"{summary3['hbAllocationPesos']:,}", "full schedule allocation in pesos"), ("Ambiguous / already paired", f"{ambiguous:,}", "held out of the shortlist")],
            "Foreign assisted projects are excluded and reviewed separately. Title screening creates review leads, not confirmed insertions. Exact and plausible fuzzy counterparts are screened out; inspect source pages and project scope before drawing conclusions."),
        "dpwh-hgab-comparison.html": hero("DPWH · HB 10858 2nd vs 3rd Reading", str(comparison["statusCounts"].get("New in 3rd reading", 0)), "line items appear only in the 3rd-reading extraction", peso(comparison["thirdAllocationPesos"] - comparison["secondAllocationPesos"]), "net increase across the extracted schedules", [
            ("2nd-reading lines", f"{comparison['secondCandidateCount']:,}", peso(comparison["secondAllocationPesos"])), ("3rd-reading lines", f"{comparison['thirdCandidateCount']:,}", peso(comparison["thirdAllocationPesos"]))],
            "This is a document-stage comparison. A line appearing in one extraction does not by itself establish a policy insertion or deletion."),
        "nia-irrigation.html": hero("NIA irrigation appendix · 3rd vs 2nd Reading", f"{ir['thirdRows']:,}", "irrigation schedule lines retained at the same allocation", peso(ir["thirdTotal"]), "schedule total in the 3rd reading", [
            ("2nd-reading total", peso(ir["secondTotal"]), f"{ir['secondRows']:,} lines"), ("Allocation changes", f"{ir['statusCounts'].get('Allocation changed', 0):,}", "between the two readings")],
            "This appendix is separate from NIA named projects. Matching rows show extracted schedule stability, not repeat projects across fiscal years."),
        "deped.html": hero("DepEd school operations · 3rd vs 2nd Reading", f"{deped['thirdRows']:,}", "school allocation lines retained at the same amounts", peso(deped["thirdTotal"]), "schedule total in the 3rd reading", [
            ("2nd-reading total", peso(deped["secondTotal"]), f"{deped['secondRows']:,} school lines"), ("Allocation changes", f"{deped['statusCounts'].get('Allocation changed', 0):,}", "between the two readings")],
            "These are school operating allocations, not a school construction-project list. Compare schedule fields and source pages before interpreting the unchanged total."),
        "fmr.html": hero("Farm-to-market roads · 3rd vs 2nd Reading", f"{fmr['thirdRows']:,}", "FMR lines retained at the same allocation", peso(fmr["thirdTotal"]), "schedule total in each reading", [
            ("2nd-reading total", peso(fmr["secondTotal"]), f"{fmr['secondRows']:,} lines"), ("Net allocation change", peso(fmr["thirdTotal"]-fmr["secondTotal"]), "between the two readings")],
            "This compares bill stages. Program envelopes and named lines may represent different levels; unchanged amounts do not establish year-on-year project repetition."),
        "nia.html": hero("NIA named projects · 3rd vs 2nd Reading", f"{nia['thirdRows']:,}", "named-project lines retained at the same allocation", peso(nia["thirdTotal"]), "schedule total in each reading", [
            ("2nd-reading total", peso(nia["secondTotal"]), f"{nia['secondRows']:,} lines"), ("Net allocation change", peso(nia["thirdTotal"]-nia["secondTotal"]), "between the two readings")],
            "This page covers NIA named projects. The separate NIA irrigation appendix is reported independently; bill-stage stability is not a repeat-project finding."),
        "hfep.html": hero("HFEP · 3rd vs 2nd Reading", f"{hfep['thirdRows']:,}", "health-facility lines retained at the same allocation", peso(hfep["thirdTotal"]), "schedule total in each reading", [
            ("2nd-reading total", peso(hfep["secondTotal"]), f"{hfep['secondRows']:,} lines"), ("Net allocation change", peso(hfep["thirdTotal"]-hfep["secondTotal"]), "between the two readings")],
            "This compares bill stages. Program envelopes and named facility lines can sit at different budget hierarchy levels."),
        "rcs.html": hero("Rainwater Collector System · schedule and rainfall-only scenario", f"{rcs['districtLines']} offices", "each receives one RCS unit in the current schedule", peso(rcs["districtPoolPesos"]), "district-office pool · ₱4.2M per unit", [
            ("Scenario shift", "₱184.8M", "from losing to gaining offices"), ("Unchanged offices", "120", "under rainfall-only whole-unit allocation")],
            "The scenario redistributes the same 199 units using province-average rainfall only. Rainfall depth is not a complete measure of water need or project capacity."),
        "budget-innovations.html": hero("FY2027 NEP · exact keyword screen", f"{len(kws)} terms", "potential first appearances or revived terms", peso(int(top_kw["pesos"])), f"largest keyword-linked allocation · {top_kw['keyword']}", [
            ("Potential first appearances", str(potential), "no exact match in local FY2020–FY2025 GAA text"), ("Revived terms", str(revived), "seen in FY2020–FY2022 only")],
            "Keyword-linked allocations may overlap and do not prove a new project. Terms are prompts for line-item review; this local archive starts in FY2020."),
        "congress.html": hero("HGAB 3rd Reading · strict congressional location attribution", f"{congress['strictExcludedLines']:,} lines", "remain outside the strict district ranking", peso(congress["strictExcludedAmountPesos"]), "unresolved or shared project allocations", [
            ("Accepted allocations", peso(congress["strictAssignedPesos"]), f"{congress['uniquelyAssignedLines']:,} lines mapped to one district"), ("Allocation coverage", f"{congress['strictCoveragePct']:.2f}%", "of the extracted schedule passes the location rules")],
            "The ranking covers accepted location matches, not complete district budgets. Conflicting maps, incomplete locations and shared lines are excluded. No accepted match does not mean no allocation; location attribution does not establish sponsorship by a representative.")
    }


def replace_lead(html: str, page: str, card: str) -> str:
    # Remove previous standalone teaser cards; keep all report tables and charts.
    html = re.sub(r'<section\b[^>]*class="impact-teaser"[^>]*>.*?</section>', '', html, count=1, flags=re.S)
    if page == "congress.html" and 'id="report-hero"' in html:
        html = re.sub(r'<section id="report-hero">.*?</section>', '<section id="report-hero">' + card + '</section>', html, count=1, flags=re.S)
    if page == "dpwh-hgab.html":
        html = html.replace(
            'body[data-page="insertions"] main>:not(#hgab-insertion){display:none!important}',
            'body[data-page="insertions"] main>:not(#hgab-insertion):not(#report-hero):not(#hgab-headline-breakdowns):not(#subtractions-domestic):not(#subtractions-fap):not(#allocation-adjustments-domestic):not(#foreign-assisted-review){display:none!important}',
        )
    if page == "dpwh.html":
        # Preserve page layout while swapping in the common lead card content.
        html = re.sub(r'<div class="repeat-hero"[^>]*>.*?(?=\s*<h2)', card, html, count=1, flags=re.S)
    elif page == "dpwh-hgab.html":
        # Move the insertion finding out of the inherited DPWH repeat section.
        if 'id="report-hero"' not in html:
            html = re.sub(r'<div class="repeat-hero"[^>]*>.*?(?=\s*<h2)', '', html, count=1, flags=re.S)
    elif page == "dpwh-hgab-comparison.html":
        html = re.sub(r'<section class="card" style="margin:20px 0;.*?</section>', '', html, count=1, flags=re.S)
    elif page == "budget-innovations.html":
        html = re.sub(r'<section class="impact">.*?</section>', '', html, count=1, flags=re.S)

    if 'id="report-hero-style"' not in html:
        html = html.replace('</head>', STYLE + '</head>', 1)
    if page == "congress.html" and "#congress-main{" not in html:
        html = re.sub(r'(<style id="report-hero-style">.*?)(</style>)', r'\1#congress-main{width:100%;max-width:none;margin:0;padding:24px clamp(16px,2vw,32px)}\2', html, count=1, flags=re.S)
    # Existing dpwh-hgab teaser appears below its insertion heading; avoid a second lead.
    html = re.sub(r'<section\b[^>]*class="impact-teaser"[^>]*>.*?</section>', '', html, flags=re.S)
    # Add one uniform hero immediately after the page's main opening tag.
    if page == "dpwh-hgab.html" and 'id="report-hero"' not in html:
        html = re.sub(r'(<main\b[^>]*>)', r'\1<section id="report-hero">' + card + '</section>', html, count=1)
    elif page not in {"dpwh.html", "dpwh-hgab.html"} and 'id="report-hero"' not in html:
        html = re.sub(r'(<main\b[^>]*>)', r'\1<section id="report-hero">' + card + '</section>', html, count=1)
    if page == "congress.html":
        html = html.replace('<main class="wrap">', '<main class="wrap" id="congress-main">', 1)
    if page == "budget-innovations.html" and 'id="budget-hero-bindings"' not in html:
        html = html.replace('<section id="report-hero">', '<section id="report-hero"><div id="budget-hero-bindings" hidden><span id="headline"></span><span id="potentialCount"></span><span id="revivedCount"></span></div>', 1)
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", help="refresh one report instead of all reports")
    args = parser.parse_args()
    for page, card in make_heroes().items():
        if args.page and args.page != page:
            continue
        path = STATIC / page
        html = path.read_text(encoding="utf-8")
        path.write_text(replace_lead(html, page, card), encoding="utf-8")
        print(f"Updated {page}")


if __name__ == "__main__":
    main()
