#!/usr/bin/env python3
"""Shared pure formatting helpers for individual report page builders."""

STYLE = """<style id="report-hero-style">
.repeat-hero{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(320px,.95fr);gap:26px;align-items:stretch;margin:20px 0 24px;padding:clamp(22px,3vw,36px);border-radius:18px;border-left:8px solid #FCD116;background:linear-gradient(120deg,#00246A 0%,#0038A8 58%,#0038A8 100%);color:#fff;box-shadow:0 16px 38px #00246A26}.repeat-hero-primary,.repeat-hero-detail{min-width:0}.repeat-hero-kicker{display:block;color:#FCD116;font-size:12px;font-weight:800;letter-spacing:.13em;text-transform:uppercase}.repeat-hero-total{display:flex;align-items:baseline;flex-wrap:wrap;gap:12px;margin:10px 0 8px}.repeat-hero-total strong{font-size:clamp(48px,7vw,78px);line-height:.98;letter-spacing:-.055em;color:#FCD116}.repeat-hero-total span{max-width:500px;font-size:clamp(19px,2.4vw,28px);line-height:1.12;font-weight:760}.repeat-hero-cost{display:flex;align-items:baseline;flex-wrap:wrap;gap:10px;margin-top:14px}.repeat-hero-cost strong{font-size:clamp(24px,3vw,34px);letter-spacing:-.035em}.repeat-hero-cost span{color:#F5F5F5;font-size:14px}.repeat-hero-breakdown{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.repeat-hero-breakdown>div{display:flex;flex-direction:column;gap:5px;min-height:106px;padding:16px;border:1px solid #ffffff35;border-radius:12px;background:#ffffff12}.repeat-hero-breakdown span{color:#F5F5F5;font-size:13px;line-height:1.3}.repeat-hero-breakdown strong{font-size:25px;line-height:1.1}.repeat-hero-breakdown small{color:#EEEEEE;font-size:12px}.repeat-hero-detail>p{margin:14px 0 0;color:#e0ecea;font-size:13px;line-height:1.5}.repeat-hero h2{margin:0;color:#fff}@media(max-width:760px){.repeat-hero{grid-template-columns:1fr;gap:18px}.repeat-hero-breakdown>div{min-height:90px}}
#congress-main{width:100%;max-width:none;margin:0;padding:24px clamp(16px,2vw,32px)}
</style>"""


def peso(n: int) -> str:
    return f"₱{n / 1_000_000_000:,.2f}B" if n >= 1_000_000_000 else f"₱{n / 1_000_000:,.1f}M" if n >= 1_000_000 else f"₱{n:,.0f}"


def hero(kicker: str, number: str, headline: str, amount: str, amount_label: str,
         cards: list[tuple[str, str, str]], note: str) -> str:
    details = "".join(f"<div><span>{label}</span><strong>{value}</strong><small>{caption}</small></div>" for label, value, caption in cards)
    return (f'<div class="repeat-hero" aria-label="Key finding"><div class="repeat-hero-primary">'
            f'<span class="repeat-hero-kicker">{kicker}</span><div class="repeat-hero-total"><strong>{number}</strong><span>{headline}</span></div>'
            f'<div class="repeat-hero-cost"><strong>{amount}</strong><span>{amount_label}</span></div></div>'
            f'<div class="repeat-hero-detail"><div class="repeat-hero-breakdown">{details}</div><p>{note}</p></div></div>')

