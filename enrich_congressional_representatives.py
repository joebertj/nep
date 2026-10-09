#!/usr/bin/env python3
"""Add cautious 20th-Congress representative labels to local ODV NEP tables.

Run from any directory:
    python3 /Users/joebertj/nep/enrich_congressional_representatives.py

The script uses ODV's local representative roster and municipality/district
crosswalk. It does not equate DPWH District Engineering Office numbers with
congressional districts. Ambiguous locations receive an empty representative
list and render as an em dash.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ODV = Path("/Users/joebertj/open-data-visualization")
DATA = ODV / "static/data"
PREVIEW = ODV / "static/nep-preview"
ROSTER_FILE = DATA / "20th_congress_representatives.json"
CROSSWALK_FILE = DATA / "districts.json"


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"\bcity of\b", " ", text)
    text = re.sub(r"\bmunicipality of\b", " ", text)
    text = re.sub(r"\bprovince of\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def district_key(value: Any) -> str:
    text = norm(value)
    if "lone" in text:
        return "lone"
    match = re.search(r"\b(\d+)(?:st|nd|rd|th)?\b", text)
    return match.group(1) if match else ""


class RepresentativeLookup:
    def __init__(self) -> None:
        roster = json.loads(ROSTER_FILE.read_text(encoding="utf-8"))
        crosswalk = json.loads(CROSSWALK_FILE.read_text(encoding="utf-8"))["districts"]
        self.reps: dict[str, dict[str, set[str]]] = {}
        for row in roster:
            province = norm(row.get("province"))
            seat = district_key(row.get("district"))
            name = str(row.get("representative") or "").strip()
            if province and seat and name and "party list" not in province and "senate" not in province:
                self.reps.setdefault(province, {}).setdefault(seat, set()).add(name)

        self.entities: dict[str, str] = {}
        self.municipalities: dict[str, list[tuple[str, str]]] = {}
        municipality_candidates: dict[str, set[tuple[str, str]]] = {}
        for entity, details in crosswalk.items():
            if details.get("entity_type") == "partylist":
                continue
            entity_key = norm(entity)
            if entity_key not in self.reps:
                continue
            self.entities[entity_key] = entity
            self.municipalities[entity_key] = []
            for municipality, district in details.get("municipalities", {}).items():
                name = norm(municipality)
                seat = district_key(district)
                if name and name != "nationwide" and seat:
                    self.municipalities[entity_key].append((name, seat))
                    municipality_candidates.setdefault(name, set()).add((entity_key, seat))
        self.unique_municipalities = {
            name: next(iter(candidates))
            for name, candidates in municipality_candidates.items()
            if len(candidates) == 1 and len(name) >= 5
        }

        self.entity_names = sorted(self.entities, key=len, reverse=True)

    @staticmethod
    def _contains(haystack: str, needle: str) -> bool:
        return bool(needle and f" {needle} " in f" {haystack} ")

    def _names_for(self, province: str, seats: set[str]) -> list[str]:
        return sorted({name for seat in seats for name in self.reps.get(province, {}).get(seat, set())})

    def from_location(self, value: Any) -> list[str]:
        """Resolve names only when a named municipality maps to a known seat."""
        text = norm(value)
        matched_entities: set[str] = set()
        for entity in self.entity_names:
            if self._contains(text, entity):
                # Suppress nested entity names (e.g. Cagayan inside Cagayan de Oro).
                if not any(entity != longer and entity in longer and self._contains(text, longer)
                           for longer in self.entity_names):
                    matched_entities.add(entity)

        seats_by_entity: dict[str, set[str]] = {}
        for entity in matched_entities:
            seats = {
                seat for municipality, seat in self.municipalities.get(entity, [])
                if len(municipality) >= 4 and self._contains(text, municipality)
            }
            if seats:
                seats_by_entity[entity] = seats

        # A unique single-seat province/city is enough when the text names only
        # that entity. For multi-seat entities, require a mapped municipality.
        names: set[str] = set()
        for entity in matched_entities:
            seats = seats_by_entity.get(entity)
            if seats:
                names.update(self._names_for(entity, seats))
            elif len(self.reps.get(entity, {})) == 1:
                names.update(self._names_for(entity, set(self.reps[entity])))
        if not names:
            for municipality, (entity, seat) in self.unique_municipalities.items():
                if self._contains(text, municipality):
                    names.update(self._names_for(entity, {seat}))
        return sorted(names)

    def from_office(self, office: Any, province_hint: Any = "") -> list[str]:
        """Map a DEO only when its named province has a single seat."""
        text = norm(f"{province_hint} {office}")
        matches = [entity for entity in self.entity_names if self._contains(text, entity)]
        if not matches:
            return []
        entity = max(matches, key=len)
        if len(self.reps.get(entity, {})) != 1:
            return []
        return self._names_for(entity, set(self.reps[entity]))

    def province_names(self, province: Any) -> list[str]:
        key = norm(province)
        seats = self.reps.get(key, {})
        # Province-level totals may show all of its district representatives.
        return sorted(name for names in seats.values() for name in names)


def reps(loc: RepresentativeLookup, text: Any, office: Any = "", province: Any = "") -> list[str]:
    result = loc.from_location(text)
    if result:
        return result
    return loc.from_office(office, province)


def enrich_rows(rows: list[dict[str, Any]], loc: RepresentativeLookup, *text_keys: str,
                office_key: str = "office", province_key: str = "province") -> None:
    for row in rows:
        location_text = " ".join(str(row.get(k) or "") for k in text_keys)
        row["congressional_representatives"] = reps(
            loc, location_text, row.get(office_key), row.get(province_key)
        )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise ValueError(f"Could not find {label} in the expected HTML")
    return text.replace(old, new, 1)


def update_dpwh_html(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '<th>District office</th><th class="num">FY2027 NEP</th>',
        '<th>District office</th><th>Representative(s) by named project location</th><th class="num">FY2027 NEP</th>',
        "repeat table representative header",
    )
    text = replace_once(
        text,
        '<th>District office</th><th>Region</th><th class="num">HB allocation</th>',
        '<th>District office</th><th>Representative(s) by named project location</th><th>Region</th><th class="num">HB allocation</th>',
        "insertion table representative header",
    )
    text = replace_once(
        text,
        '${esc(r.office)}</td><td class="num">${peso(r.amount_2027)}',
        '${esc(r.office)}</td><td>${esc((r.congressional_representatives||[]).join("; ")||"—")}</td><td class="num">${peso(r.amount_2027)}',
        "repeat table row",
    )
    text = replace_once(
        text,
        '${esc(r.office)}</td><td>${esc(r.region)}</td><td class="num">${peso(r.amountPesos)}',
        '${esc(r.office)}</td><td>${esc((r.congressional_representatives||[]).join("; ")||"—")}</td><td>${esc(r.region)}</td><td class="num">${peso(r.amountPesos)}',
        "insertion table row",
    )
    text = replace_once(
        text,
        '<div class="toolbar"><input id="priorityRepeatSearch"',
        '<p class="sub rep-note">Representative names use named project locations matched to ODV’s municipality-to-congressional-district crosswalk and the 20th Congress roster. A dash means the location did not resolve confidently; DPWH office numbering is not treated as a congressional district.</p><div class="toolbar"><input id="priorityRepeatSearch"',
        "repeat table attribution note",
    )
    text = replace_once(
        text,
        '<div class="toolbar"><input id="hbInsertionSearch"',
        '<p class="sub rep-note">Representative names use named project locations matched to ODV’s municipality-to-congressional-district crosswalk and the 20th Congress roster. A dash means the location did not resolve confidently; DPWH office numbering is not treated as a congressional district.</p><div class="toolbar"><input id="hbInsertionSearch"',
        "insertion table attribution note",
    )

    # For tables that group by DEO, show the representative(s) associated with
    # the named featured project, or the sole representative for a single-seat
    # province. Do not infer from the engineering-office ordinal.
    columns = [
        ("{key:'project_name',title:true},{key:'amount',num:true,render:r=>peso(r.amount)}],sorters:{}",
         "{key:'project_name',title:true},{key:'congressional_representatives',title:true,render:r=>esc((r.congressional_representatives||[]).join('; ')||'—')},{key:'amount',num:true,render:r=>peso(r.amount)}],sorters:{}"),
        ("{key:'largest_project_name',title:true}],sorters:{amount:(a,b)=>b.total_amount-a.total_amount",
         "{key:'largest_project_name',title:true},{key:'congressional_representatives',title:true,render:r=>esc((r.congressional_representatives||[]).join('; ')||'—')}],sorters:{amount:(a,b)=>b.total_amount-a.total_amount"),
        ("{key:'combined_amount',num:true,render:r=>peso(r.combined_amount)}],sorters:{}",
         "{key:'combined_amount',num:true,render:r=>peso(r.combined_amount)},{key:'congressional_representatives',title:true,render:r=>esc((r.congressional_representatives||[]).join('; ')||'—')}],sorters:{}"),
        ("{key:'project_name',title:true},{key:'amount',num:true,render:r=>peso(r.amount)}],sorters:{}",
         "{key:'project_name',title:true},{key:'congressional_representatives',title:true,render:r=>esc((r.congressional_representatives||[]).join('; ')||'—')},{key:'amount',num:true,render:r=>peso(r.amount)}],sorters:{}"),
        ("{key:'largest_project_share_pct',num:true,render:r=>`${Number(r.largest_project_share_pct).toFixed(1)}%`}],sorters:",
         "{key:'largest_project_share_pct',num:true,render:r=>`${Number(r.largest_project_share_pct).toFixed(1)}%`},{key:'congressional_representatives',title:true,render:r=>esc((r.congressional_representatives||[]).join('; ')||'—')}],sorters:"),
    ]
    for old, new in columns:
        text = text.replace(old, new, 1)
    # Add column headings matching the data columns above.
    headings = [
        ('<th>Project</th><th class="num">Allocation</th></tr></thead><tbody id="inspireBody">', '<th>Project</th><th>Representative(s) for project location</th><th class="num">Allocation</th></tr></thead><tbody id="inspireBody">'),
        ('<th>Largest project</th></tr></thead><tbody id="districtProgramBody">', '<th>Largest project</th><th>Representative(s) for largest project location</th></tr></thead><tbody id="districtProgramBody">'),
        ('<th class="num">Combined listed amount</th></tr></thead><tbody id="fiveMillionBody">', '<th class="num">Combined listed amount</th><th>Representative(s), if province has one seat</th></tr></thead><tbody id="fiveMillionBody">'),
        ('<th>Project title</th><th class="num">Allocation</th></tr></thead><tbody id="waterBody">', '<th>Project title</th><th>Representative(s) for project location</th><th class="num">Allocation</th></tr></thead><tbody id="waterBody">'),
        ('<th class="num">Largest project share</th></tr></thead><tbody id="districtBody">', '<th class="num">Largest project share</th><th>Representative(s) for largest project location</th></tr></thead><tbody id="districtBody">'),
    ]
    for old, new in headings:
        if old in text:
            text = text.replace(old, new, 1)
    text = text.replace(
        "if(!groups[key])groups[key]={fiscal_year:r.fiscal_year,office:r.office,region:r.region,road_count:0,flood_count:0};",
        "if(!groups[key])groups[key]={fiscal_year:r.fiscal_year,office:r.office,region:r.region,congressional_representatives:r.congressional_representatives||[],road_count:0,flood_count:0};",
        1,
    )
    path.write_text(text, encoding="utf-8")


def update_sector_html(path: Path, page_label: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '<th>Status</th><th>Project / facility</th><th class="num">2nd reading</th>',
        '<th>Status</th><th>Project / facility</th><th>Representative(s) by named project location</th><th class="num">2nd reading</th>',
        f"{page_label} 3rd-reading comparison header",
    )
    old_row = '<td>${x.status}</td><td>${x.name}</td><td class="num">${peso(x.secondAmount)}</td>'
    new_row = '<td>${x.status}</td><td>${x.name}</td><td>${(x.congressional_representatives||[]).join(\'; \')||\'—\'}</td><td class="num">${peso(x.secondAmount)}</td>'
    text = replace_once(text, old_row, new_row, f"{page_label} 3rd-reading comparison row")
    text = text.replace("colspan=\"6\">No rows for this filter", "colspan=\"7\">No rows for this filter", 1)
    text = text.replace("const cols=['status','name','secondAmount'", "const cols=['status','name','congressional_representatives','secondAmount'", 1)
    path.write_text(text, encoding="utf-8")


def update_irrigation_html(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, '<th>NIA project line</th><th class="num">3rd HGAB</th>', '<th>NIA project line</th><th>Representative(s) by named project location</th><th class="num">3rd HGAB</th>', "NIA irrigation repeat table header")
    text = replace_once(text, '<th>Project / work</th><th>Station / chainage</th>', '<th>Project / work</th><th>Representative(s) by named project location</th><th>Station / chainage</th>', "NIA irrigation schedule table header")
    text = replace_once(text, '<td>${x.name}</td><td class="num">${peso(x.amount)}</td>', '<td>${x.name}</td><td>${(x.congressional_representatives||[]).join(\'; \')||\'—\'}</td><td class="num">${peso(x.amount)}</td>', "NIA irrigation repeat row")
    text = replace_once(text, '<td>${x.projectName}</td><td>${(x.projectName.match', '<td>${x.projectName}</td><td>${(x.congressional_representatives||[]).join(\'; \')||\'—\'}</td><td>${(x.projectName.match', "NIA irrigation schedule row")
    text = text.replace('colspan="8">No title candidates at the current filter', 'colspan="9">No title candidates at the current filter', 1)
    text = text.replace("['name','amount','prior_name'", "['name','congressional_representatives','amount','prior_name'", 1)
    text = text.replace("['edition','projectName','amountPesos'", "['edition','projectName','congressional_representatives','amountPesos'", 1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    for required in (ROSTER_FILE, CROSSWALK_FILE, PREVIEW / "dpwh-data.json"):
        if not required.is_file():
            raise FileNotFoundError(required)
    loc = RepresentativeLookup()

    # DPWH repeated-project and insertion line items, plus office and project
    # summaries used by the district tables.
    dpwh_path = PREVIEW / "dpwh-data.json"
    dpwh = read_json(dpwh_path)
    enrich_rows(dpwh.get("priorityRepeats", []), loc, "project", "prior_project")
    enrich_rows(dpwh.get("hbInsertions", []), loc, "projectName")
    enrich_rows(dpwh.get("nonRoadBridgeTop", []), loc, "project_name", office_key="office")
    enrich_rows(dpwh.get("districtPrograms", []), loc, "largest_project_name", office_key="office")
    enrich_rows(dpwh.get("districts", []), loc, "largest_project_name", office_key="office")
    enrich_rows(dpwh.get("waterWatchlist", []), loc, "project_name", office_key="office")
    enrich_rows(dpwh.get("fiveMillionRows", []), loc, "", office_key="office")
    write_json(dpwh_path, dpwh)
    for page in (PREVIEW / "dpwh.html", PREVIEW / "dpwh-hgab.html"):
        update_dpwh_html(page)

    # Add the same locality-based context to named FMR, NIA, and HFEP line
    # tables. Long or generic scheme names with no resolvable place stay blank.
    revision_path = PREVIEW / "hgab-revision-data.json"
    revision = read_json(revision_path)
    for key in ("fmr", "nia_named", "hfep", "nia_irrigation"):
        section = revision.get(key, {})
        enrich_rows(section.get("rows", []), loc, "name")
    write_json(revision_path, revision)
    for page, label in (("fmr.html", "FMR"), ("nia.html", "NIA"), ("hfep.html", "HFEP")):
        update_sector_html(PREVIEW / page, label)

    irrigation_path = PREVIEW / "nia-irrigation-data.json"
    irrigation = read_json(irrigation_path)
    enrich_rows(irrigation.get("revision", {}).get("rows", []), loc, "name")
    enrich_rows(irrigation.get("repeatCandidates", []), loc, "name", "prior_name")
    enrich_rows(irrigation.get("projects", []), loc, "projectName")
    write_json(irrigation_path, irrigation)
    update_irrigation_html(PREVIEW / "nia-irrigation.html")

    # DPWH reading comparison: use both named versions of each line so that a
    # changed title or a project spanning constituencies can show multiple reps.
    comparison_path = PREVIEW / "dpwh-hgab-comparison.json"
    comparison = read_json(comparison_path)
    for row in comparison.get("rows", []):
        texts = []
        for side in (row.get("second") or {}, row.get("third") or {}):
            texts.append(side.get("projectName", ""))
        row["congressional_representatives"] = loc.from_location(" ".join(texts))
    write_json(comparison_path, comparison)
    comparison_html = PREVIEW / "dpwh-hgab-comparison.html"
    html = comparison_html.read_text(encoding="utf-8")
    html = replace_once(html, '<th>3rd reading line</th><th>2nd chainage</th>', '<th>3rd reading line</th><th>Representative(s) by named project location</th><th>2nd chainage</th>', "DPWH reading comparison header")
    if "${esc((r.congressional_representatives||[]).join('; ')||'—')}" not in html and "${(r.congressional_representatives||[]).join('; ')||'—'}" not in html:
        html = replace_once(html, '${r.third?.projectName||\'—\'}</td><td>${r.second_chainage||\'—\'}', '${r.third?.projectName||\'—\'}</td><td>${(r.congressional_representatives||[]).join(\'; \')||\'—\'}</td><td>${r.second_chainage||\'—\'}', "DPWH reading comparison row")
    html = html.replace(
        "const peso=n=>'₱'+Number(n||0).toLocaleString('en-PH');const fmt=n=>",
        "const peso=n=>'₱'+Number(n||0).toLocaleString('en-PH');const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));const fmt=n=>",
        1,
    )
    html = html.replace(
        "${(r.congressional_representatives||[]).join('; ')||'—'}</td><td>${r.second_chainage",
        "${esc((r.congressional_representatives||[]).join('; ')||'—')}</td><td>${r.second_chainage",
        1,
    )
    html = html.replace(
        "'status','score_pct','second_title','third_title','second_amount_pesos'",
        "'status','score_pct','second_title','third_title','congressional_representatives','second_amount_pesos'",
        1,
    )
    html = html.replace(
        "r.third?.projectName||'',r.second?.amountPesos||''",
        "r.third?.projectName||'',(r.congressional_representatives||[]).join('; '),r.second?.amountPesos||''",
        1,
    )
    comparison_html.write_text(html, encoding="utf-8")

    # RCS is summarized by province and by DPWH engineering office. Province
    # totals can list every current seat in that province; DEOs only inherit a
    # name when the province has a single congressional seat.
    rcs_path = PREVIEW / "rcs-data.json"
    rcs = read_json(rcs_path)
    for row in rcs.get("allocationByProvince", []):
        row["congressional_representatives"] = loc.province_names(row.get("province"))
    for row in rcs.get("districts", []):
        row["congressional_representatives"] = loc.from_office(row.get("office"), row.get("province"))
    write_json(rcs_path, rcs)
    rcs_html_path = PREVIEW / "rcs.html"
    html = rcs_html_path.read_text(encoding="utf-8")
    html = replace_once(html, '<th>Province</th><th class="num">Mean annual rain (mm)</th>', '<th>Province</th><th>Congressional representatives for province</th><th class="num">Mean annual rain (mm)</th>', "RCS province table header")
    html = replace_once(html, '<th>District Engineering Office</th><th class="num">Mean annual rain (mm)</th>', '<th>District Engineering Office</th><th>Representative(s), only when province has one seat</th><th class="num">Mean annual rain (mm)</th>', "RCS district table header")
    if '${esc(x.province)}</td><td class="num">' in html:
        html = replace_once(html, '${esc(x.province)}</td><td class="num">${fmt(x.averageAnnualMm)}', '${esc(x.province)}</td><td>${(x.congressional_representatives||[]).join(\'; \')||\'—\'}</td><td class="num">${fmt(x.averageAnnualMm)}', "RCS province row")
    if '${esc(x.office)}</td><td class="num">' in html:
        html = replace_once(html, '${esc(x.office)}</td><td class="num">${fmt(x.averageAnnualMm)}', '${esc(x.office)}</td><td>${(x.congressional_representatives||[]).join(\'; \')||\'—\'}</td><td class="num">${fmt(x.averageAnnualMm)}', "RCS district row")
    html = html.replace(
        "${(x.congressional_representatives||[]).join('; ')||'—'}</td><td class=\"num\">${fmt(x.averageAnnualMm)}",
        "${esc((x.congressional_representatives||[]).join('; ')||'—')}</td><td class=\"num\">${fmt(x.averageAnnualMm)}",
    )
    html = html.replace(
        "${(x.congressional_representatives||[]).join('; ')||'—'}</td><td class=\"num\">${x.currentUnits}",
        "${esc((x.congressional_representatives||[]).join('; ')||'—')}</td><td class=\"num\">${x.currentUnits}",
    )
    if "Roster: 20th Congress." not in html:
        html = html.replace(
            '<div class="tablewrap"><table><thead><tr><th>Province</th>',
            '<p class="note">Roster: 20th Congress. Province totals list all representatives for that province. District-office rows show a name only when the province has one congressional seat; the DPWH office number is not used as a seat number. A dash means no confident match.</p><div class="tablewrap"><table><thead><tr><th>Province</th>',
            1,
        )
    html = html.replace(
        "const cols=['province','averageAnnualMm','districtOffices','currentUnits'",
        "const cols=['province','congressional_representatives','averageAnnualMm','districtOffices','currentUnits'",
        1,
    )
    rcs_html_path.write_text(html, encoding="utf-8")

    print("Enriched local ODV DPWH line and district tables plus RCS tables.")
    print("Unresolved locations are left with an empty representative list and shown as —.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
