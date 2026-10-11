"""Refresh the table enrichment runtime without recalculating location assignments."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def refresh():
    path = STATIC / 'ph-location-representatives.js'
    if not path.exists():
        return
    existing = path.read_text()
    payload, _ = json.JSONDecoder().raw_decode(existing.split('const D=', 1)[1])
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    asset = (ROOT / 'location_data/table_representatives.js').read_text().replace('__PH_LOCATION_PAYLOAD__', serialized)
    path.write_text(asset)
    version = hashlib.sha256(asset.encode()).hexdigest()[:12]
    for directory in (STATIC, ROOT / 'analysis_output'):
        for page in directory.glob('*.html'):
            original = page.read_text()
            updated = re.sub(r'src="ph-location-representatives\.js(?:\?v=[^"]*)?"',
                             f'src="ph-location-representatives.js?v={version}"', original)
            if original != updated:
                page.write_text(updated)
    return version


if __name__ == '__main__':
    print(refresh())
