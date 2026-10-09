#!/usr/bin/env python3
"""Trace geographic attribution evidence behind three congressional rankings.

Writes private investigation artifacts only; does not change the public reports.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
NEP = OUT.parent
ODV = NEP.parent / "open-data-visualization"
sys.path.insert(0, str(ODV / "analysis"))
import build_congress_allocation_data as builder

reps = builder.reps
TARGETS = ["Quezon · 3rd District", "Cagayan de Oro · 2nd District", "Ilocos Norte · 1st District"]


def setup():
    raw = json.loads(reps.ROSTER_PATH.read_text())
    seat_rows = []
    for row in raw:
        province = str(row.get("province", "")).strip()
        district = reps.district_key(row.get("district"))
        name = builder.clean_name(str(row.get("representative", "")))
        if district in builder.DISTRICT_LABELS and province and name and reps.norm(name) != "special election":
            seat_rows.append(dict(province=province, districtLabel=builder.DISTRICT_LABELS[district],
                                  representative=name, key=reps.norm(name)))
    seats = {(reps.norm(r["province"]), r["districtLabel"]): r for r in seat_rows}
    seats = sorted(seats.values(), key=lambda r: (reps.norm(r["province"]), r["districtLabel"]))
    by_name = defaultdict(list)
    for i, row in enumerate(seats):
        by_name[row["key"]].append(i)
    roster, _ = reps.load_roster()
    for row in seat_rows:
        roster.setdefault(reps.norm(row["province"]), {})[reps.district_key(row["districtLabel"])] = row["representative"]
    locality_index, province_names = reps.make_locality_index(roster)
    first_word = defaultdict(list)
    for place in locality_index:
        first_word[place.split()[0]].append(place)
    return seats, by_name, roster, locality_index, province_names, first_word


def geography_trace(title, roster, locality_index, province_names, first_word):
    text = reps.norm(title)
    named = {p for p in province_names if reps.contains_phrase(text, p)}
    named = {p for p in named if not any(p != q and p in q and reps.contains_phrase(text, q) for q in named)}
    if "manila" in named and reps.contains_phrase(text, "metro manila") and not reps.contains_phrase(text, "manila city") and not reps.contains_phrase(text, "city of manila"):
        named.remove("manila")
    if len(named) > 1:
        return dict(namedJurisdictions=sorted(named), selectedLocalities=[])
    matches = []
    for place in {p for word in set(text.split()) for p in first_word.get(word, ())}:
        if len(place) < 5 or not reps.contains_phrase(text, place):
            continue
        candidates = [(province, seats) for province, seats in locality_index[place] if not named or province in named]
        if len(candidates) != 1:
            continue
        province, seats = candidates[0]
        if any(seat in roster[province] for seat in seats):
            matches.append(dict(place=place, jurisdiction=province, seats=seats))
    if matches:
        longest = max(len(m["place"]) for m in matches)
        matches = sorted((m for m in matches if len(m["place"]) == longest), key=lambda m: m["place"])
    return dict(namedJurisdictions=sorted(named), selectedLocalities=matches)


def main():
    seats, by_name, roster, locality_index, province_names, first_word = setup()
    projects = json.loads((NEP / "hb10858_3rd_dpwh_projects.json").read_text())["data"]["data"]
    primary = json.loads((ODV / "static/data/districts.json").read_text())["districts"]
    generated = json.loads((ODV / "static/data/districts_generated.json").read_text())
    with (OUT / "hb_nep_comparison_3rd.csv").open(encoding="utf-8-sig", newline="") as f:
        review = list(csv.DictReader(f))
    review_by_id = {r["hgab_id"]: r for r in review}
    excluded = {(r["sourcePage"], r["amountPesos"], reps.norm(r["projectName"])) for r in review
                if r.get("comparison", "").startswith("Likely schedule heading/total")}
    evidence = []
    for project in projects:
        title, amount = project["projectName"], int(round(float(project["amountPesos"])))
        if (str(project["sourcePage"]), str(amount), reps.norm(title)) in excluded:
            continue
        names = reps.infer_representatives(title, roster, locality_index, province_names, first_word)
        indices = sorted({i for name in names for i in by_name.get(reps.norm(builder.clean_name(name)), [])})
        districts = [f'{seats[i]["province"]} · {seats[i]["districtLabel"]}' for i in indices]
        if not any(d in TARGETS for d in districts):
            continue
        trace = geography_trace(title, roster, locality_index, province_names, first_word)
        text = reps.norm(title)
        flags, conflicts = [], []
        if TARGETS[0] in districts:
            current = {reps.norm(k): v for k, v in primary["Quezon"].get("municipalities", {}).items()}
            alternate = {reps.norm(k): v for k, v in generated["Quezon"].items()}
            for place, alternate_seat in alternate.items():
                if place == "quezon" or not reps.contains_phrase(text, place):
                    continue
                if place not in current or reps.district_key(current[place]) != reps.district_key(alternate_seat):
                    conflicts.append(dict(locality=place, primaryDistrict=current.get(place),
                                          alternativeDistrict=alternate_seat,
                                          decision="Unresolved; neither local crosswalk is treated as authoritative."))
            if conflicts:
                flags.append("Local crosswalks disagree or the primary crosswalk lacks a named locality.")
            if any(m["place"] == "quezon" for m in trace["selectedLocalities"]):
                flags.append("Quezon is being used as a municipality match; its role as province, city, barangay, bridge or road name must be established from geographic context.")
        if TARGETS[1] in districts:
            flags.append("Cagayan de Oro barangay crosswalk omits the 1st District; a unique returned name does not prove a unique geographic assignment.")
            if any(m["place"] == "cagayan de oro city" for m in trace["selectedLocalities"]):
                flags.append("Whole-city name is indexed as a 2nd District barangay and overrides shorter locality matches.")
            if reps.contains_phrase(text, "puerto princesa"):
                flags.append("Puerto barangay token occurs within Puerto Princesa; this does not establish a Cagayan de Oro location.")
        stage = review_by_id.get(project["id"], {})
        evidence.append(dict(
            id=project["id"], projectName=title, amountPesos=amount, office=project["office"],
            region=project["region"], pap1=project.get("pap1", ""), pap3=project.get("pap3", ""),
            sourceVolume=project["sourceVolume"], sourcePage=project["sourcePage"],
            sourceText=project.get("sourceText", ""),
            currentComputedDistricts=districts, currentComputedRepresentatives=names,
            selectedLocalities=trace["selectedLocalities"], namedJurisdictions=trace["namedJurisdictions"],
            geographicReviewFlags=flags, crosswalkConflicts=conflicts,
            attributionStatus="Unresolved: flagged geographic evidence" if flags else "Not independently verified",
            stageComparison=stage.get("comparison", ""), closestNepTitle=stage.get("closest_nep_title", ""),
            nepSourcePage=stage.get("nep_source_page", "")))
    output = dict(source="HGAB 3rd Reading local extraction", scope=TARGETS,
        method="Evidence audit only. Reproduces the current matcher for tracing, without accepting its assignments as verified. No replacement totals or geographic redistribution is calculated.",
        geographicRule="Require the correct geographic hierarchy: barangay within municipality/city, municipality/city within province or explicitly identified independent city, then verified congressional district. A shared name or a name appearing in a road/bridge title is insufficient. DEO ordinals are not congressional district identifiers.",
        limitation="Workspace-only evidence. Local crosswalk conflicts and incomplete boundaries remain unresolved. These attribution failures do not establish diversion or individual involvement.",
        projects=evidence)
    (OUT / "congress_rankings_investigation.json").write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n")
    with (OUT / "congress_rankings_investigation.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields=["id","projectName","amountPesos","office","region","sourceVolume","sourcePage","currentComputedDistricts","currentComputedRepresentatives","selectedLocalities","geographicReviewFlags","crosswalkConflicts","attributionStatus","stageComparison","closestNepTitle"]
        writer=csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in evidence:
            writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row[k],list) else row[k] for k in fields})
    print("Wrote private JSON and CSV geographic evidence audit; no district totals recalculated.")


if __name__ == "__main__":
    main()
