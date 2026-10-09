#!/usr/bin/env python3
"""Build the RCS rainfall-only allocation scenario and its static ODV page."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / "open-data-visualization"
DATA_DIR = ODV / "static" / "data"
STATIC = ODV / "static" / "nep-preview"
RAINFALL = ROOT / "phl-rainfall-subnat-full.csv"
BUDGET = ROOT / "2027.json"
UNIT_PESOS = 4_200_000
FIRST_YEAR, LAST_YEAR = 1981, 2025

# The local rainfall PCODE uses the same region/province P-codes as its
# administrative areas. ODV's boundary files instead expose province names,
# so this explicit local crosswalk joins the two datasets.
PCODE_PROVINCE = {
    "PH01028": "Ilocos Norte", "PH01029": "Ilocos Sur", "PH01033": "La Union", "PH01055": "Pangasinan",
    "PH02009": "Batanes", "PH02015": "Cagayan", "PH02031": "Isabela", "PH02050": "Nueva Vizcaya", "PH02057": "Quirino",
    "PH03008": "Bataan", "PH03014": "Bulacan", "PH03049": "Nueva Ecija", "PH03054": "Pampanga", "PH03069": "Aurora", "PH03071": "Tarlac", "PH03077": "Zambales",
    "PH04010": "Batangas", "PH04021": "Cavite", "PH04034": "Laguna", "PH04056": "Quezon", "PH04058": "Rizal",
    "PH05005": "Albay", "PH05016": "Camarines Norte", "PH05017": "Camarines Sur", "PH05020": "Catanduanes", "PH05041": "Masbate", "PH05062": "Sorsogon",
    "PH06004": "Aklan", "PH06006": "Antique", "PH06019": "Capiz", "PH06030": "Iloilo", "PH06045": "Negros Occidental", "PH06079": "Guimaras",
    "PH07012": "Bohol", "PH07022": "Cebu", "PH07046": "Negros Oriental", "PH07061": "Siquijor",
    "PH08026": "Eastern Samar", "PH08037": "Leyte", "PH08048": "Northern Samar", "PH08060": "Samar", "PH08064": "Southern Leyte", "PH08078": "Biliran",
    "PH09072": "Zamboanga del Norte", "PH09073": "Zamboanga del Sur", "PH09083": "Zamboanga Sibugay",
    "PH10013": "Bukidnon", "PH10018": "Camiguin", "PH10035": "Lanao del Norte", "PH10042": "Misamis Occidental", "PH10043": "Misamis Oriental",
    "PH11023": "Davao del Norte", "PH11024": "Davao del Sur", "PH11025": "Davao Oriental", "PH11082": "Compostela Valley",
    "PH12047": "North Cotabato", "PH12063": "Sarangani", "PH12065": "South Cotabato", "PH12080": "Sultan Kudarat",
    "PH13074": "Metropolitan Manila",
    "PH14001": "Abra", "PH14011": "Mountain Province", "PH14027": "Apayao", "PH14032": "Ifugao", "PH14044": "Kalinga", "PH14081": "Benguet",
    "PH16002": "Agusan del Norte", "PH16003": "Agusan del Sur", "PH16067": "Dinagat Islands", "PH16068": "Surigao del Norte", "PH16085": "Surigao del Sur",
    "PH17040": "Marinduque", "PH17051": "Occidental Mindoro", "PH17052": "Oriental Mindoro", "PH17053": "Palawan", "PH17059": "Romblon",
    "PH19007": "Basilan", "PH19036": "Lanao del Sur", "PH19066": "Maguindanao", "PH19070": "Sulu", "PH19087": "Tawi-Tawi",
}

REGION_NAMES = {
    "PH01": "Ilocos Region (Region I)", "PH02": "Cagayan Valley (Region II)", "PH03": "Central Luzon (Region III)",
    "PH04": "CALABARZON (Region IV-A)", "PH05": "Bicol Region (Region V)", "PH06": "Western Visayas (Region VI)",
    "PH07": "Central Visayas (Region VII)", "PH08": "Eastern Visayas (Region VIII)", "PH09": "Zamboanga Peninsula (Region IX)",
    "PH10": "Northern Mindanao (Region X)", "PH11": "Davao Region (Region XI)", "PH12": "SOCCSKSARGEN (Region XII)",
    "PH13": "National Capital Region (NCR)", "PH14": "Cordillera Administrative Region (CAR)", "PH16": "Caraga (Region XIII)",
    "PH17": "MIMAROPA (Region IV-B)", "PH19": "Bangsamoro Autonomous Region in Muslim Mindanao (BARMM)",
}


def read_rainfall() -> tuple[list[dict], list[dict]]:
    observations: dict[str, dict[int, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    with RAINFALL.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["adm_level"] != "2" or row["version"] != "final" or not row["rfh"]:
                continue
            year = int(row["date"][:4])
            if not FIRST_YEAR <= year <= LAST_YEAR:
                continue
            # These are the three 10-day observations in each month.
            dekad = (int(row["date"][5:7]) - 1) * 3 + (int(row["date"][8:10]) - 1) // 10
            observations[row["PCODE"]][year][dekad] = float(row["rfh"])

    profiles = []
    province_annual: dict[str, dict[int, float]] = {}
    missing = set(PCODE_PROVINCE)
    for pcode, province in PCODE_PROVINCE.items():
        yearly = observations.get(pcode, {})
        complete = {year: sum(v.values()) for year, v in yearly.items() if len(v) == 36}
        if not complete:
            raise ValueError(f"No complete rainfall years for {pcode} ({province})")
        missing.discard(pcode)
        province_annual[province] = complete
        values = list(complete.values())
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        profiles.append({
            "pcode": pcode, "province": province, "regionCode": pcode[:4],
            "region": REGION_NAMES[pcode[:4]], "years": len(values),
            "averageAnnualMm": round(mean, 1), "medianAnnualMm": round(sorted(values)[len(values) // 2], 1),
            "sdAnnualMm": round(math.sqrt(variance), 1), "minAnnualMm": round(min(values), 1),
            "maxAnnualMm": round(max(values), 1),
        })
    if missing:
        raise ValueError(f"PCODE mapping has no observations: {sorted(missing)}")
    observed_codes = {p for p, years in observations.items() if years}
    if observed_codes != set(PCODE_PROVINCE):
        raise ValueError(f"PCODE crosswalk mismatch; unmapped={sorted(observed_codes-set(PCODE_PROVINCE))}; unused={sorted(set(PCODE_PROVINCE)-observed_codes)}")

    annual_rows = []
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        vals = [series[year] for series in province_annual.values() if year in series]
        annual_rows.append({"year": year, "meanProvinceRainfallMm": round(sum(vals) / len(vals), 1), "provinces": len(vals)})

    dekad_values: dict[int, list[float]] = defaultdict(list)
    with RAINFALL.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["adm_level"] != "2" or row["version"] != "final" or not row["rfh"] or not FIRST_YEAR <= int(row["date"][:4]) <= LAST_YEAR:
                continue
            month = int(row["date"][5:7])
            dekad = (int(row["date"][8:10]) - 1) // 10
            dekad_values[(month - 1) * 3 + dekad + 1].append(float(row["rfh"]))
    seasonality = [{"period": i, "label": f"{(i-1)//3+1:02d}/{('1','11','21')[(i-1)%3]}", "meanTenDayMm": round(sum(v) / len(v), 2)} for i, v in sorted(dekad_values.items())]
    return profiles, [{"annual": annual_rows, "seasonality": seasonality}]


def read_boundaries() -> dict[str, dict]:
    by_name = {}
    for path in DATA_DIR.glob("ph.*.geo.json"):
        feature = json.loads(path.read_text(encoding="utf-8"))
        props = feature.get("properties", {})
        if props.get("type") == "province":
            by_name[props.get("province_name", "").casefold()] = {
                "url": f"../data/{path.name}", "provinceId": str(props.get("province_id", "")),
                "regionName": props.get("region_name", ""),
            }
    return by_name


def read_rcs_rows() -> tuple[list[dict], list[dict]]:
    raw = json.loads(BUDGET.read_text(encoding="utf-8"))["data"]["data"]
    rows = [r for r in raw if r.get("pap3") == "Rainwater Collector System" or "rainwater collector system" in r.get("projectName", "").casefold()]
    districts, other = [], []
    province_names = sorted({p for p in PCODE_PROVINCE.values() if p != "Metropolitan Manila"}, key=len, reverse=True)
    for row in rows:
        office = row.get("office", "")
        amount = round(float(row.get("amount") or 0) * 1000)  # NEP values are in ₱000.
        if "District Engineering Office" not in office:
            other.append({"office": office, "region": row.get("region", ""), "amountPesos": amount, "projectName": row.get("projectName", "")})
            continue
        province = "Metropolitan Manila" if row.get("region") == "NCR" else None
        searchable = f"{office} {row.get('projectName', '')}".casefold()
        if province is None:
            for name in province_names:
                if re.search(rf"(?<![a-z]){re.escape(name.casefold())}(?![a-z])", searchable):
                    province = name
                    break
        aliases = {
            "cotabato": "North Cotabato", "davao de oro": "Compostela Valley",
            "baguio city": "Benguet", "mindoro occidental": "Occidental Mindoro",
            "mindoro oriental": "Oriental Mindoro", "southern mindoro": "Occidental Mindoro",
            "bacolod city": "Negros Occidental", "tacloban city": "Leyte",
            "zamboanga city": "Zamboanga del Sur", "iligan city": "Lanao del Norte",
            "davao city": "Davao del Sur", "butuan city": "Agusan del Norte",
            "davao occidental": "Davao Occidental",
        }
        match_level = "province name"
        if province is None:
            for alias, canonical in aliases.items():
                if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", searchable):
                    province = canonical
                    match_level = "city/office name mapped to province"
                    break
        if province == "Davao Occidental":
            match_level = "province name; rainfall falls back to region"
        districts.append({
            "office": office, "region": row.get("region", ""), "province": province or "",
            "provinceMatchLevel": match_level,
            "projectName": row.get("projectName", ""), "currentPesos": amount,
            "currentUnits": round(amount / UNIT_PESOS, 3),
        })
    return districts, other


def build_data() -> dict:
    profiles, charts = read_rainfall()
    boundaries = read_boundaries()
    for p in profiles:
        boundary = boundaries.get(p["province"].casefold())
        if boundary:
            p["boundaryUrl"] = boundary["url"]
            p["provinceId"] = boundary["provinceId"]
        else:
            p["boundaryUrl"] = ""
            p["provinceId"] = ""
    districts, other = read_rcs_rows()
    region_means: dict[str, list[float]] = defaultdict(list)
    for profile in profiles:
        region_means[profile["regionCode"]].append(profile["averageAnnualMm"])
    for row in districts:
        if row["province"] == "Davao Occidental":
            row["rainfallArea"] = "Davao Region (province series unavailable)"
            row["averageAnnualMm"] = round(sum(region_means["PH11"]) / len(region_means["PH11"]), 1)
            row["rainfallYears"] = LAST_YEAR - FIRST_YEAR + 1
            row["matchLevel"] = "region fallback"
            row["boundaryUrl"] = ""
        else:
            row["rainfallArea"] = row["province"]
            climate_profile = next(p for p in profiles if p["province"] == row["province"])
            row["averageAnnualMm"] = climate_profile["averageAnnualMm"]
            row["rainfallYears"] = climate_profile["years"]
            row["matchLevel"] = row.pop("provinceMatchLevel", "province name")
            row["boundaryUrl"] = boundaries[row["province"].casefold()]["url"]
        row.pop("provinceMatchLevel", None)
    unmapped_provinces = sorted({r["province"] for r in districts if r["province"] and r["province"].casefold() not in boundaries and r["province"] != "Davao Occidental"})
    no_province_rows = [r for r in districts if not r["province"]]
    if no_province_rows or unmapped_provinces:
        raise ValueError(f"RCS district mapping incomplete. Missing province: {[x['office'] for x in no_province_rows]}; no boundary: {unmapped_provinces}")
    profile_by_province = {p["province"]: p for p in profiles}
    districts_per_province: dict[str, int] = defaultdict(int)
    for row in districts:
        districts_per_province[row["rainfallArea"]] += 1
    # Give each province a share proportional to its average annual rainfall,
    # then divide its share equally among its DPWH district offices. This avoids
    # provinces with more offices receiving extra weight merely for office count.
    rainfall_area_means = {p: profile_by_province[p]["averageAnnualMm"] if p in profile_by_province else round(sum(region_means["PH11"]) / len(region_means["PH11"]), 1) for p in districts_per_province}
    rain_weight_total = sum(rainfall_area_means[p] for p in districts_per_province)
    budget_pool = sum(r["currentPesos"] for r in districts)
    unit_pool = budget_pool // UNIT_PESOS
    remainder_pesos = budget_pool - unit_pool * UNIT_PESOS
    expected_by_province = {p: unit_pool * rainfall_area_means[p] / rain_weight_total for p in districts_per_province}
    for row in districts:
        row["provinceShareUnits"] = round(expected_by_province[row["rainfallArea"]], 3)
        row["expectedUnits"] = expected_by_province[row["rainfallArea"]] / districts_per_province[row["rainfallArea"]]
    # Largest-remainder rounding keeps the recommended number of whole units
    # equal to the fundable district pool.
    floored = [math.floor(r["expectedUnits"]) for r in districts]
    leftover = unit_pool - sum(floored)
    ranked = sorted(range(len(districts)), key=lambda i: (-(districts[i]["expectedUnits"] - floored[i]), districts[i]["office"].casefold()))
    extra_units = set(ranked[:leftover])
    for i, row in enumerate(districts):
        row["recommendedUnits"] = floored[i] + (1 if i in extra_units else 0)
        row["recommendedPesos"] = row["recommendedUnits"] * UNIT_PESOS
        row["deltaPesos"] = row["recommendedPesos"] - row["currentPesos"]
        row["expectedUnits"] = round(row["expectedUnits"], 3)
    by_province = []
    for p in profiles:
        subset = [r for r in districts if r["rainfallArea"] == p["province"]]
        if not subset:
            continue
        by_province.append({
            **p, "districtOffices": len(subset), "currentUnits": round(sum(r["currentUnits"] for r in subset), 3),
            "recommendedUnits": sum(r["recommendedUnits"] for r in subset),
            "expectedUnits": round(sum(r["expectedUnits"] for r in subset), 3),
            "currentPesos": sum(r["currentPesos"] for r in subset),
            "recommendedPesos": sum(r["recommendedPesos"] for r in subset),
            "deltaPesos": sum(r["deltaPesos"] for r in subset),
        })
    davao_fallback = [r for r in districts if r["rainfallArea"] == "Davao Region (province series unavailable)"]
    if davao_fallback:
        by_province.append({
            "province": "Davao Occidental (Davao Region rainfall proxy)",
            "averageAnnualMm": rainfall_area_means["Davao Region (province series unavailable)"],
            "districtOffices": len(davao_fallback), "currentUnits": round(sum(r["currentUnits"] for r in davao_fallback), 3),
            "recommendedUnits": sum(r["recommendedUnits"] for r in davao_fallback),
            "expectedUnits": round(sum(r["expectedUnits"] for r in davao_fallback), 3),
            "currentPesos": sum(r["currentPesos"] for r in davao_fallback),
            "recommendedPesos": sum(r["recommendedPesos"] for r in davao_fallback),
            "deltaPesos": sum(r["deltaPesos"] for r in davao_fallback), "boundaryUrl": "",
        })
    districts.sort(key=lambda r: (r["province"], r["office"]))
    by_province.sort(key=lambda r: -r["averageAnnualMm"])
    charts[0]["annual"] = charts[0]["annual"]
    return {
        "method": {"unitPesos": UNIT_PESOS, "rainfallMeasure": "rfh source field, treated as millimetres; dekadal values summed to annual totals", "rainfallYears": f"{FIRST_YEAR}–{LAST_YEAR}", "completeYearsOnly": True, "provinceCrosswalk": "PCODE to province name; matched to ODV province GeoJSON", "allocation": "District RCS pool proportional to mean annual rainfall by province; province share divided evenly among listed DPWH district offices; whole units assigned by largest remainder.", "limitations": "Rainfall depth alone is a screening scenario, not a final needs model. It does not measure population, demand, catchment area, storage capacity, water access, dry-season reliability, or district boundaries. Province rainfall is used for all offices in that province."},
        "summary": {"districtLines": len(districts), "districtPoolPesos": budget_pool, "wholeUnits": unit_pool, "unallocatedRemainderPesos": remainder_pesos, "districtRainfallAreas": len(districts_per_province), "allRcsLines": len(districts) + len(other), "otherLines": other, "nationalAndRegionalPesos": sum(r["amountPesos"] for r in other), "rainfallProvinces": len(profiles), "firstYear": FIRST_YEAR, "lastYear": LAST_YEAR, "averageAnnualRainfallMm": round(sum(p["averageAnnualMm"] for p in profiles) / len(profiles), 1)},
        "rainfall": {"provinces": profiles, "annualTrend": charts[0]["annual"], "seasonality": charts[0]["seasonality"]},
        "allocationByProvince": by_province, "districts": districts,
    }


def page_html() -> str:
    return r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Rainwater Collector System · Rainfall allocation scenario</title>
<script src="/static/js/chart.js"></script>
<style>
:root{--ink:#18303b;--muted:#536873;--paper:#f3f6f5;--card:#fff;--teal:#087e78;--line:#d9e3e1;--blue:#355b92}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}header{padding:34px max(22px,calc((100vw - 1320px)/2));background:#123944;color:#fff}header .eyebrow{opacity:.75;text-transform:uppercase;letter-spacing:.09em;font-size:.8rem}h1{font-size:clamp(2rem,4vw,3.6rem);line-height:1.05;margin:.5rem 0 1rem;max-width:900px}header p{max-width:980px;color:#d6e4e4}.report-nav{display:flex;gap:9px;flex-wrap:wrap;margin-top:20px}.report-nav a{color:#fff;border:1px solid #ffffff6b;border-radius:999px;padding:6px 12px;text-decoration:none;font-size:.9rem}.wrap{max-width:1320px;margin:auto;padding:22px}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin:0 0 18px;box-shadow:0 3px 12px #15323b0a}.card h2{margin:.1rem 0 .35rem;font-size:1.3rem}.sub,.note{color:var(--muted);font-size:.94rem}.grid{display:grid;gap:16px}.charts{grid-template-columns:repeat(2,minmax(0,1fr))}.chart{min-height:350px}.chart canvas{height:270px!important;width:100%!important}.metrics{grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:18px}.metric{padding:14px;background:#f3f8f7;border-radius:10px}.metric-label{font-size:.83rem;color:var(--muted)}.metric-value{font-size:1.55rem;font-weight:750;line-height:1.25}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.toolbar input,.toolbar select,.toolbar button{padding:9px 11px;border:1px solid #bccdca;border-radius:8px;background:#fff;color:var(--ink);font:inherit}.toolbar input{min-width:min(330px,100%);flex:1}.toolbar button{background:var(--teal);border-color:var(--teal);color:#fff;cursor:pointer;font-weight:650}.tablewrap{overflow:auto;max-height:680px}table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}th{position:sticky;top:0;background:#edf3f2;z-index:1}.num{text-align:right;white-space:nowrap}.allocation-grid{grid-template-columns:1fr 1fr}.map-wrap{height:560px;border-radius:10px;overflow:hidden;background:#eef3f2}.map-wrap svg{width:100%;height:100%;display:block}.map-wrap path:hover{stroke:#102f3e;stroke-width:2}.legend{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:.9rem;color:var(--muted)}.swatch{display:inline-block;width:20px;height:12px;border-radius:3px;margin-right:5px;vertical-align:middle}.note{padding:12px;background:#f4f7f6;border-radius:8px}.pagination{display:flex;justify-content:center;gap:14px;align-items:center;margin-top:12px}.pagination button{padding:6px 12px;border:1px solid var(--line);border-radius:7px;background:#fff}@media(max-width:800px){.charts,.allocation-grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.wrap{padding:12px}.map-wrap{height:420px}}
</style></head><body><header><div class="eyebrow">FY2027 NEP · DPWH · Rainwater Collector System</div><h1>What would RCS allocation look like if rainfall were the only input?</h1><p>This scenario distributes the 199 district-office RCS units (₱835.8 million at ₱4.2 million per unit) in proportion to each province’s average annual rainfall. The province share is divided evenly among its listed DPWH district offices. The rainfall charts appear first; the allocation table follows.</p><nav class="report-nav"><a href="dpwh.html">DPWH · NEP patterns</a><a href="dpwh-hgab.html">DPWH · NEP → HGAB</a><a href="dpwh-hgab-comparison.html">DPWH · HGAB 2nd vs 3rd</a><a href="fmr.html">FMR</a><a href="nia.html">NIA</a><a href="hfep.html">HFEP</a></nav></header>
<main class="wrap"><section class="card"><h2>Rainfall record · 1981–2025</h2><p class="sub">Each annual value is the unweighted mean of province annual totals, calculated from complete years only. The local phl-rainfall-subnat-full.csv file supplies the rfh field; values are treated as millimetres and 36 10-day readings are summed to annual totals. This shows historical rainfall patterns, not local water demand.</p><div class="grid charts"><article class="card chart"><h2>Annual rainfall across provinces</h2><canvas id="annualChart"></canvas></article><article class="card chart"><h2>Typical 10-day rainfall through the year</h2><canvas id="seasonChart"></canvas></article></div><h2>Province rainfall map</h2><p class="sub">Fill represents average annual rainfall. Hover over a province for its long-term mean, variation, and RCS office count. The source CSV is province-level; it has no municipality observations to support a town-level rainfall estimate.</p><div class="map-wrap"><svg id="rainMap" viewBox="0 0 1000 700" role="img" aria-label="Province rainfall map"></svg></div><p class="legend"><span><i class="swatch" style="background:#ffffcc"></i>Lower rainfall</span><span><i class="swatch" style="background:#41b6c4"></i>Middle range</span><span><i class="swatch" style="background:#253494"></i>Higher rainfall</span><span><i class="swatch" style="background:#d8d8d8"></i>No matched boundary/data</span></p></section>
<section class="grid metrics" id="metrics"></section><section class="card"><h2>Rainfall-weighted unit scenario</h2><p class="sub">The model redistributes the existing district-office pool while keeping the total at 199 whole RCS units. For each province, its share of units is proportional to its 1981–2025 mean annual rainfall; that share is split across the province’s listed DPWH district offices. Largest-remainder rounding keeps the national total at exactly 199 units. Fractional model shares are shown beside the whole-unit scenario.</p><p class="note" id="methodNote"></p><div class="grid allocation-grid"><article class="card chart"><h2>Current vs rainfall-weighted units by province</h2><canvas id="allocationChart"></canvas></article><article class="card"><h2>Allocation by province</h2><button id="provinceCsv" type="button">Export province CSV</button><div class="tablewrap"><table><thead><tr><th>Province</th><th class="num">Mean annual rain (mm)</th><th class="num">DEOs</th><th class="num">Current units</th><th class="num">Expected units</th><th class="num">Suggested whole units</th><th class="num">Change</th></tr></thead><tbody id="provinceBody"></tbody></table></div></article></div></section>
<section class="card"><h2>District engineering office allocation</h2><div class="toolbar"><input id="search" placeholder="Search district, province, or region"><select id="region"><option value="all">All regions</option></select><select id="sort"><option value="delta">Largest unit change</option><option value="rain">Highest rainfall</option><option value="province">Province name</option></select><button id="csv">Export filtered CSV</button></div><figure class="card chart"><figcaption><h2>Rainfall vs expected RCS units for the selected offices</h2><p class="sub">Each point is one district office; filter the table and this plot together.</p></figcaption><canvas id="districtChart"></canvas></figure><div class="tablewrap"><table><thead><tr><th>Region</th><th>Province proxy</th><th>Geographic match</th><th>District Engineering Office</th><th class="num">Mean annual rain (mm)</th><th class="num">Current units</th><th class="num">Expected units</th><th class="num">Suggested whole units</th><th class="num">Current allocation</th><th class="num">Rainfall-only allocation</th><th class="num">Change</th></tr></thead><tbody id="districtBody"></tbody></table></div><p class="note">The table assigns province-level rainfall to every DEO listed under that province. It does not assert that the DEO serves only that province or that the province average reflects its service area. One Davao Occidental office uses the Davao Region mean because neither a province rainfall series nor a local boundary is present in the workspace.</p><div class="pagination" id="pager"></div></section>
<section class="card"><h2>How to read this scenario</h2><p class="sub">Annual rainfall depth (rfh treated as millimetres) is used as the sole weight because the request is to model a rainfall-only allocation. That is a transparent starting point for water harvesting potential. A complete needs formula should also include service population, usable roof or catchment area, storage capacity, rainfall seasonality and dry spells, water access, existing RCS sites, and construction cost. A province-level average cannot support a final district budget by itself.</p><p class="sub">Regional-office and nationwide RCS lines are shown separately from the district pool because the rainfall source cannot assign them to district service areas. They are not redistributed in this scenario.</p></section></main>
<script>const peso=n=>'₱'+Number(n||0).toLocaleString('en-PH'),fmt=n=>Number(n||0).toLocaleString('en-PH'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));fetch('rcs-data.json').then(r=>r.json()).then(async D=>{
const s=D.summary,provinces=D.allocationByProvince,districts=D.districts;document.getElementById('metrics').innerHTML=[['District offices',fmt(s.districtLines)],['District RCS pool',peso(s.districtPoolPesos)],['Fundable whole units',fmt(s.wholeUnits)],['Rainfall coverage',`${fmt(s.rainfallProvinces)} provinces · ${s.firstYear}–${s.lastYear}`}].map(x=>`<article class="metric"><div class="metric-label">${x[0]}</div><div class="metric-value">${x[1]}</div></article>`).join('');document.getElementById('methodNote').textContent=`Unit price: ${peso(D.method.unitPesos)}. Province-level rainfall was used as a proxy for each district office; ${peso(s.nationalAndRegionalPesos)} in regional-office and nationwide RCS allocations remains outside the district redistribution. The district pool has a ${peso(s.unallocatedRemainderPesos)} remainder below one whole unit.`;
new Chart(document.getElementById('annualChart'),{type:'line',data:{labels:D.rainfall.annualTrend.map(x=>x.year),datasets:[{label:'Mean annual rainfall (mm)',data:D.rainfall.annualTrend.map(x=>x.meanProvinceRainfallMm),borderColor:'#087e78',backgroundColor:'#087e7825',fill:true,tension:.24,pointRadius:1.5}]},options:{responsive:true,maintainAspectRatio:false,scales:{y:{title:{display:true,text:'Millimetres per year'}}},plugins:{tooltip:{callbacks:{label:c=>`${fmt(c.raw)} mm · ${D.rainfall.annualTrend[c.dataIndex].provinces} provinces`}}}});
new Chart(document.getElementById('seasonChart'),{type:'line',data:{labels:D.rainfall.seasonality.map(x=>x.label),datasets:[{label:'Mean 10-day rainfall (mm)',data:D.rainfall.seasonality.map(x=>x.meanTenDayMm),borderColor:'#355b92',backgroundColor:'#355b9225',fill:true,tension:.25,pointRadius:1.7}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{ticks:{maxRotation:60,minRotation:45}},y:{title:{display:true,text:'Millimetres per 10-day period'}}}}});
new Chart(document.getElementById('allocationChart'),{type:'bar',data:{labels:provinces.map(x=>x.province),datasets:[{label:'Current units',data:provinces.map(x=>x.currentUnits),backgroundColor:'#9aaab2'},{label:'Rainfall-weighted whole units',data:provinces.map(x=>x.recommendedUnits),backgroundColor:'#087e78'}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,scales:{x:{beginAtZero:true,title:{display:true,text:'₱4.2M unit equivalents'}}}}});
const provinceBody=document.getElementById('provinceBody');provinceBody.innerHTML=provinces.map(x=>`<tr><td>${esc(x.province)}</td><td class="num">${fmt(x.averageAnnualMm)}</td><td class="num">${fmt(x.districtOffices)}</td><td class="num">${x.currentUnits}</td><td class="num">${fmt(x.expectedUnits)}</td><td class="num">${fmt(x.recommendedUnits)}</td><td class="num">${x.deltaPesos>=0?'+':''}${peso(x.deltaPesos)}</td></tr>`).join('');document.getElementById('provinceCsv').onclick=()=>{const cols=['province','averageAnnualMm','districtOffices','currentUnits','recommendedUnits','expectedUnits','currentPesos','recommendedPesos','deltaPesos'];const csv=[cols,...provinces.map(r=>cols.map(k=>r[k]??''))].map(a=>a.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),link=document.createElement('a');link.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'}));link.download='rcs_rainfall_weighted_by_province.csv';link.click();URL.revokeObjectURL(link.href)};
const allocByName=new Map(provinces.map(x=>[x.province.toLowerCase(),x])),color=v=>{if(v==null)return'#d8d8d8';const vals=D.rainfall.provinces.map(x=>x.averageAnnualMm).sort((a,b)=>a-b),q=v<=vals[Math.floor(vals.length*.2)]?0:v<=vals[Math.floor(vals.length*.4)]?1:v<=vals[Math.floor(vals.length*.6)]?2:v<=vals[Math.floor(vals.length*.8)]?3:4;return['#ffffcc','#a1dab4','#41b6c4','#2c7fb8','#253494'][q]},svg=document.getElementById('rainMap'),geoData=await Promise.all(D.rainfall.provinces.filter(x=>x.boundaryUrl).map(async p=>({p,g:await fetch(p.boundaryUrl).then(r=>r.json())})));let minX=180,maxX=-180,minY=90,maxY=-90;function eachCoord(c,fn){if(typeof c[0]==='number')fn(c);else c.forEach(x=>eachCoord(x,fn))}for(const {g} of geoData)eachCoord(g.geometry.coordinates,c=>{minX=Math.min(minX,c[0]);maxX=Math.max(maxX,c[0]);minY=Math.min(minY,c[1]);maxY=Math.max(maxY,c[1])});function rings(g){return g.type==='Polygon'?g.coordinates:g.coordinates.flat()}function point(c){return[30+(c[0]-minX)/(maxX-minX)*940,20+(maxY-c[1])/(maxY-minY)*660]}svg.innerHTML=geoData.map(({p,g})=>{const d=rings(g.geometry).map(r=>r.map((c,i)=>{const [x,y]=point(c);return`${i?'L':'M'}${x.toFixed(1)},${y.toFixed(1)}`} ).join(' ')+' Z').join(' '),a=allocByName.get(p.province.toLowerCase()),tip=`${p.province} · average annual rainfall ${fmt(p.averageAnnualMm)} mm · ${p.years} complete years · ${a?.districtOffices||0} RCS district offices · current ${a?.currentUnits||0} units · scenario ${a?.recommendedUnits||0} units`;return`<path d="${d}" fill="${color(p.averageAnnualMm)}" fill-rule="evenodd" stroke="#536873" stroke-width="1.1" vector-effect="non-scaling-stroke"><title>${esc(tip)}</title></path>`}).join('');
const regions=[...new Set(districts.map(x=>x.region))].sort(),region=document.getElementById('region');region.innerHTML+='<option value="__blank">Unmatched region</option>'+regions.map(x=>`<option>${esc(x)}</option>`).join('');const districtChart=new Chart(document.getElementById('districtChart'),{type:'scatter',data:{datasets:[{label:'District offices',data:[],backgroundColor:'#087e78'}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{title:{display:true,text:'Mean annual rainfall (mm)'}},y:{beginAtZero:true,title:{display:true,text:'Expected RCS units (fractional)'}}},plugins:{tooltip:{callbacks:{label:c=>`${c.raw.office}: ${c.raw.x} mm · ${Number(c.raw.y).toFixed(3)} expected units`}}}}});let page=0;const size=30,search=document.getElementById('search'),sort=document.getElementById('sort'),body=document.getElementById('districtBody'),pager=document.getElementById('pager');function filtered(){const q=search.value.toLowerCase(),rg=region.value;let a=districts.filter(x=>(rg==='all'||(rg==='__blank'&&!x.region)||x.region===rg)&&[x.office,x.province,x.region].some(v=>String(v).toLowerCase().includes(q)));if(sort.value==='rain')a.sort((x,y)=>y.averageAnnualMm-x.averageAnnualMm);else if(sort.value==='province')a.sort((x,y)=>x.province.localeCompare(y.province)||x.office.localeCompare(y.office));else a.sort((x,y)=>Math.abs(y.deltaPesos)-Math.abs(x.deltaPesos));return a}function draw(){const a=filtered(),pages=Math.max(1,Math.ceil(a.length/size));page=Math.min(page,pages-1);const start=page*size;body.innerHTML=a.slice(start,start+size).map(x=>`<tr><td>${esc(x.region)}</td><td>${esc(x.province)}</td><td>${esc(x.matchLevel)}</td><td>${esc(x.office)}</td><td class="num">${fmt(x.averageAnnualMm)}</td><td class="num">${x.currentUnits}</td><td class="num">${fmt(x.expectedUnits)}</td><td class="num">${fmt(x.recommendedUnits)}</td><td class="num">${peso(x.currentPesos)}</td><td class="num">${peso(x.recommendedPesos)}</td><td class="num">${x.deltaPesos>=0?'+':''}${peso(x.deltaPesos)}</td></tr>`).join('');districtChart.data.datasets[0].data=a.map(x=>({x:Number(x.averageAnnualMm),y:Number(x.expectedUnits),office:x.office}));districtChart.update();pager.innerHTML=`<button ${page===0?'disabled':''} data-d="-1">Previous</button><span>${a.length?fmt(start+1):0}–${fmt(Math.min(start+size,a.length))} of ${fmt(a.length)}</span><button ${page>=pages-1?'disabled':''} data-d="1">Next</button>`;pager.querySelectorAll('button').forEach(b=>b.onclick=()=>{page+=Number(b.dataset.d);draw()})}for(const el of [search,region,sort])el.addEventListener(el===search?'input':'change',()=>{page=0;draw()});document.getElementById('csv').onclick=()=>{const cols=['region','province','matchLevel','office','averageAnnualMm','rainfallYears','currentUnits','expectedUnits','recommendedUnits','currentPesos','recommendedPesos','deltaPesos','projectName'];const rows=filtered();const csv=[cols,...rows.map(r=>cols.map(k=>r[k]??''))].map(a=>a.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),link=document.createElement('a');link.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'}));link.download='rcs_rainfall_weighted_district_scenario.csv';link.click();URL.revokeObjectURL(link.href)};draw()
}).catch(e=>{console.error(e);document.querySelector('main').insertAdjacentHTML('afterbegin','<section class="card">Could not load RCS rainfall data. Check that rcs-data.json and the local boundary GeoJSON files are available.</section>')});</script></body></html>'''


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    data = build_data()
    (STATIC / "rcs-data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (STATIC / "rcs.html").write_text(page_html(), encoding="utf-8")
    summary = {**data["summary"], "method": data["method"]}
    (ROOT / "analysis_output" / "rcs_rainfall_allocation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote RCS page and data: {len(data['districts'])} districts, {data['summary']['wholeUnits']} units, {data['summary']['districtRainfallAreas']} rainfall areas")


if __name__ == "__main__":
    main()
