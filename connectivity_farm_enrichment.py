"""Preserve measured cropland evidence across road/map data refreshes."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'analysis_output/connectivity-cropland-measurements.json'
ROAD_CUTOFF_M=500
CROP_CUTOFF_M=50
MODEL='Baseline FMR · road ≤500 m and mapped cropland ≤50 m'
FLAG='Flag FMR · only one distance threshold met'
DOUBLE='Double Flag FMR · road >500 m and mapped cropland >50 m'
REVIEW='Review · other distance combinations'
UNKNOWN='Unresolved · incomplete cropland coverage'
COORDINATE_REVIEW='Coordinate review · endpoints >20 km apart'

def classify(row):
 if row.get('coordinateQualityFlag'):return COORDINATE_REVIEW
 road=row.get('nearestDistanceMeters');farm=row.get('farmDistanceMeters')
 if road is None:return UNKNOWN
 near=farm is not None and farm<=CROP_CUTOFF_M
 road_near=road<=ROAD_CUTOFF_M
 if road_near and near:return MODEL
 farm_known=farm is not None or row.get('farmCoverage1000m')
 if not farm_known:return UNKNOWN
 if road_near!=near:return FLAG
 farm_far=(farm is not None and farm>CROP_CUTOFF_M) or (farm is None and row.get('farmCoverage1000m'))
 if road>ROAD_CUTOFF_M and farm_far:return DOUBLE
 return REVIEW

def load_measurements():
 return json.loads(CACHE.read_text()) if CACHE.exists() else None

def apply_measurement(row, cache):
 if row.get('coordinateQualityFlag'):return False
 candidate=cache['projects'].get(str(row.get('id'))) if cache else None
 if not candidate:return False
 start=row.get('start') or [row.get('startLongitude'),row.get('startLatitude')]
 end=row.get('end') or [row.get('endLongitude'),row.get('endLatitude')]
 if any(None in pair for pair in (start,end)):return False
 if any(abs(float(a)-float(b))>1e-7 for pair,ref in [(start,candidate['start']),(end,candidate['end'])] for a,b in zip(pair,ref)):return False
 row.update({k:v for k,v in candidate.items() if k not in ('start','end')})
 row['connectivityClass']=classify(row)
 return True
