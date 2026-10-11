#!/usr/bin/env python3
"""Keep a visible consolidated source footer on the congressional report."""
import html
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
REFERENCES=[
    ('House of Representatives · member identities','https://congress.gov.ph/house-members'),
    ('House of Representatives · leadership roster','https://congress.gov.ph/house-members/house-leaders'),
    ('House of Representatives · Appropriations Committee roster','https://congress.gov.ph/committees/committee/view/0504'),
    ('House of Representatives · supplementary dated leadership record','https://congress.gov.ph/media/press-releases/9695'),
    ('House of Representatives · bicameral proceedings context','https://www.congress.gov.ph/media/press-releases/10187'),
    ('Philippine Center for Investigative Journalism (PCIJ) · party-list research, March 12, 2026','https://pcij.org/2026/03/12/dynasties-contractors-capture-party-list-seats/'),
    ('PCIJ · accompanying party-list directory','https://phpartylist-20th-congress.vercel.app/'),
    ('PCIJ · supplementary family identity reporting, May 11, 2025','https://pcij.org/2025/05/11/party-list-groups-linked-to-political-dynasties-lead-2025-race/'),
    ('PCIJ report published by CoverStory · membership update, June 1, 2026','https://coverstory.ph/2026/06/01/7-reasons-why-the-party-list-system-serves-dynasties-not-democracy/'),
]

def apply():
    links=''.join('<li><a href="'+html.escape(url,quote=True)+'">'+html.escape(label)+'</a></li>' for label,url in REFERENCES)
    footer='<footer id="congress-source-credits" style="padding:24px clamp(16px,2vw,32px);border-top:1px solid #cad8d8;background:#edf3f2;color:#18303b"><h2>Sources and acknowledgments</h2><p>Institutional records supply identity and role information. Independent reporting supplies the dated family relationships and membership update shown in the party-list table. Sources remain linked beside the relevant records and methods.</p><p><strong>DEO–legislative district crosswalk:</strong> The supplied PDF, <cite>DPWH per district.pdf</cite>, came from the Philippine Center for Investigative Journalism (PCIJ), as confirmed by the contributor. It supports office-to-district mapping review. Its budget stage and boundary dates remain unverified; office coverage does not establish that every project belongs to one legislative district.</p><ul>'+links+'</ul><p>Local analysis downloads: <a href="congress-data.json">HGAB geographic attribution and methodology</a> · <a href="congress-benchmark.json">District comparisons and source hashes</a> · <a href="appropriations-roster.json">Committee identities and decisions</a> · <a href="house-leadership-roles.json">Leadership sources and dates</a> · <a href="house-party-list-roster.json">Party-list identities, relationship sources and coverage limits</a>.</p><p>Web records retrieved October 11, 2026. Publication dates and retrieval dates differ; neither certifies membership at the HGAB reading date. The party-list roster is partial. Reported kinship does not establish project authorship, personal receipts or control of funds.</p></footer>'
    path=STATIC/'congress.html'
    text=re.sub(r'<footer\b[^>]*id="congress-source-credits"[^>]*>.*?</footer>','',path.read_text(),flags=re.S)
    text=text.replace('</main>','</main>'+footer,1)
    path.write_text(text)
    (ROOT/'analysis_output/congress.html').write_text(text)

if __name__=='__main__':apply()
