"""Match annual GAA titles with a qualified city or municipality."""
import re

from lane_cost_enrichment import key


def location_title(title):
    return re.sub(r'\s+[-–—]\s+(?=(?:sta(?:tion)?|chainage)\b)', ' ', title, count=1, flags=re.I)


def normalized_scope(title):
    return re.sub(r'\bconsrtruction\b', 'construction', key(title))


def project_key(title, places):
    codes, scope = places.resolve_with_scope(location_title(title))
    if not codes or not scope:
        return None
    municipality = places.lineage(codes[0]).get('municipality')
    normalized = normalized_scope(scope)
    if municipality and normalized:
        return municipality, normalized
