"""Audit locally archived ArcGIS polygons before using them as farm evidence."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def audit_farm_data():
    existing = ROOT / 'analysis_output/connectivity-farm-status.json'
    measurements = ROOT / 'analysis_output/connectivity-cropland-measurements.json'
    source = ROOT / 'data_sources/esa_worldcover_2021/manifest.json'
    if existing.exists() and measurements.exists() and source.exists():
        current = json.loads(existing.read_text())
        manifest = json.loads(source.read_text())
        if current.get('status') == 'integrated' and all((source.parent / item['file']).is_file() for item in manifest['files']):
            return current
    archive = ROOT / 'data_sources/arcgis_dpwh/archive'
    candidates = []
    archived_layers = 0
    for path in sorted(archive.rglob('metadata.json')):
        try:
            metadata = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        feature_path = path.parent / 'features.jsonl'
        if feature_path.is_file():
            archived_layers += 1
        # FMR polylines/endpoints are road evidence, never farm boundaries.
        if metadata.get('geometryType') != 'esriGeometryPolygon':
            continue
        label = str(metadata.get('name') or '')
        if not re.search(r'\b(?:farms?|farmland|cropland|crops?|agricultur\w*|rice|corn|coconut|land[ _-]?use)\b', label, re.I):
            continue
        count = 0
        if feature_path.is_file():
            with feature_path.open() as source:
                for line in source:
                    if (json.loads(line).get('geometry') or {}).get('rings'):
                        count += 1
        candidates.append({'name': label, 'polygonFeatures': count,
                           'metadata': str(path.relative_to(ROOT))})
    failures = []
    for path in sorted((archive / 'selected').glob('*/status.json')):
        try:
            status = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if status.get('workerError'):
            failures.append({'profile': path.parent.name, 'error': status['workerError'],
                             'updatedAt': status.get('updatedAt')})
    data = {'checkedAtUtc': datetime.now(timezone.utc).isoformat(),
            'availableForConnectivity': False, 'status': 'awaiting_integration' if candidates else 'not_downloaded',
            'archivedFeatureLayers': archived_layers, 'candidateLayers': candidates,
            'candidatePolygonFeatures': sum(row['polygonFeatures'] for row in candidates),
            'failedDownloadProfiles': failures,
            'message': 'Farm proximity is not assessed: no farm/cropland polygon layer is loaded into this analysis. DA FMR layers contain road routes and endpoints, not farm boundaries. Missing farm data does not establish that farms are absent.'}
    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    for directory in (ROOT / 'analysis_output', STATIC):
        (directory / 'connectivity-farm-status.json').write_text(text)
    return data


if __name__ == '__main__':
    data = audit_farm_data()
    print(json.dumps({key: data[key] for key in ('status', 'archivedFeatureLayers', 'candidatePolygonFeatures')}))
