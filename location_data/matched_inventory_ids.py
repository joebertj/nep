"""Build exact-title inventory ID labels from supported, source-backed matches."""
import json
import re
from collections import defaultdict
from pathlib import Path
from location_data.location_text import text_key

ROOT=Path(__file__).resolve().parents[1]

def catalog():
    claims=defaultdict(set)
    cost=ROOT/'analysis_output/cost_per_km.json'
    if cost.exists():
        for row in json.loads(cost.read_text())['projects']:
            e=row.get('inventoryDimensionsEvidence') or row.get('laneInventoryEvidence') or {}
            value=e.get('bridgeId') or e.get('sectionId')
            if value and re.fullmatch(r'[BS]\d{5}[A-Z]{2}',value):claims[text_key(row['projectName'])].add(value)
    context=ROOT.parent/'open-data-visualization/static/data/inventory_location_contexts.json'
    if context.exists():
        for title,row in json.loads(context.read_text()).get('contexts',{}).items():
            e=row.get('inventoryEvidence') or {}
            value=e.get('bridgeId') or e.get('sectionId')
            if value and re.fullmatch(r'[BS]\d{5}[A-Z]{2}',value):claims[text_key(title)].add(value)
    return {title:next(iter(ids)) for title,ids in claims.items() if len(ids)==1}
