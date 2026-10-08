"""Shared layout overrides for readable, non-scrolling report tables."""


TABLE_FIT_CSS = """
 .repeat-hero{display:grid;grid-template-columns:minmax(300px,.9fr) minmax(320px,1.1fr);gap:28px;align-items:center;margin:0 0 24px;padding:26px 30px;border-radius:14px;background:linear-gradient(120deg,#102f3e,#17586a);border-left:8px solid #f2ad4e;color:#f6faf8}
.repeat-hero-kicker{display:block;color:#a7ddd1;text-transform:uppercase;letter-spacing:.14em;font-size:12px;font-weight:750}
.repeat-hero-total{display:flex;align-items:baseline;gap:15px;flex-wrap:wrap;margin-top:4px}
.repeat-hero-total strong{font-size:clamp(68px,9vw,112px);line-height:.95;letter-spacing:-.065em;color:#ffc45f;font-variant-numeric:tabular-nums}
.repeat-hero-total span{font-size:clamp(20px,2.4vw,30px);line-height:1.1;font-weight:750}
.repeat-hero-cost{display:grid;gap:1px;margin-top:14px;padding-top:12px;border-top:1px solid #ffffff35}
.repeat-hero-cost strong{font-size:clamp(29px,4vw,43px);line-height:1.05;letter-spacing:-.03em;color:#fff;font-variant-numeric:tabular-nums}
.repeat-hero-cost span{font-size:13px;line-height:1.35;color:#d1dfde}
.repeat-hero-breakdown{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.repeat-hero-breakdown div{padding:12px 14px;border:1px solid #ffffff35;border-radius:10px;background:#ffffff0d}
.repeat-hero-breakdown span{display:block;color:#d1dfde;font-size:13px}
.repeat-hero-breakdown strong{display:block;margin-top:2px;font-size:clamp(22px,2.4vw,32px);line-height:1.1;font-variant-numeric:tabular-nums;color:#ffc45f}
.repeat-hero-breakdown small{display:block;margin-top:4px;color:#d1dfde;font-size:11px}
.repeat-hero-detail p{margin:12px 0 0;color:#d1dfde;font-size:13px;line-height:1.45}
@media(max-width:760px){.repeat-hero{grid-template-columns:1fr;padding:20px;gap:16px}}
.repeat-summary.metrics{grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:0}
.repeat-summary .mlabel,.repeat-summary .metric-label{font-size:12px;color:var(--muted)}
.repeat-summary .mvalue,.repeat-summary .metric-value{font-size:clamp(19px,2vw,24px);line-height:1.2;font-weight:760;margin-top:4px;font-variant-numeric:tabular-nums}
.repeat-summary .mnote,.repeat-summary .metric-note{font-size:11px;color:var(--muted);margin-top:4px}
details{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 16px;color:var(--muted);font-size:13px}
details summary{cursor:pointer;font-weight:700;color:var(--ink)}
header .report-nav{display:flex;gap:16px;flex-wrap:wrap;margin-top:16px;font-size:13px}
header .report-nav a{color:#a7ddd1}
header .source-context{margin:12px 0 0;color:#b8d3ce;font-size:13px}
@media(max-width:900px){.repeat-summary.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
header{padding-left:clamp(16px,3vw,48px);padding-right:clamp(16px,3vw,48px)}
.wrap{width:100%;max-width:1800px;padding-left:clamp(14px,3vw,48px);padding-right:clamp(14px,3vw,48px)}
.tablewrap,.table-wrap{max-width:100%;overflow:visible}
table{width:100%;table-layout:fixed}
th,td{white-space:normal;overflow-wrap:anywhere;word-break:normal}
td.title{min-width:0;max-width:none}
td.num,th.num{white-space:nowrap;font-size:11px;padding-left:6px;padding-right:6px}
@media(max-width:900px){
  .wrap{padding-left:14px;padding-right:14px}
  .card{padding:16px}
  table{font-size:11px}
  th,td{padding:7px 6px}
  td.num,th.num{font-size:10px;padding-left:3px;padding-right:3px}
}
"""


def fit_tables(page: str) -> str:
    """Use available page width and wrap table content instead of scrolling."""
    if "</style>" not in page:
        raise ValueError("Report page has no style block to apply table layout")
    return page.replace("</style>", TABLE_FIT_CSS + "</style>", 1)
