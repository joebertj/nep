"""Measure FMR endpoint proximity to ESA WorldCover class 40; publish map crop areas."""
import json,math,hashlib
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.features import shapes,geometry_mask
from shapely.geometry import shape,mapping,Point,box
from shapely.ops import unary_union
from shapely import transform as transform_geometry

def transform(function, geometry):
    return transform_geometry(geometry, function, interleaved=False)
from pyproj import Transformer
ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
OUT=ROOT/'analysis_output'
SOURCE=ROOT/'data_sources/esa_worldcover_2021'
FORWARD=Transformer.from_crs(4326,32651,always_xy=True).transform
REVERSE=Transformer.from_crs(32651,4326,always_xy=True).transform
from connectivity_farm_enrichment import classify

def write(name,data):
 text=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n'
 for directory in (OUT,STATIC):(directory/name).write_text(text)

def publish_crop_maps(meta, projects):
 index={};chunks=[];current={};size=0
 for pid,geometry in projects.items():
  encoded=json.dumps(geometry,separators=(',',':'))
  if current and size+len(encoded)>700000:
   chunks.append(current);current={};size=0
  current[pid]=geometry;size+=len(encoded)
 if current:chunks.append(current)
 for chunk in chunks:
  text=json.dumps(chunk,separators=(',',':'))+'\n'
  digest=hashlib.sha256(text.encode()).hexdigest()
  path='connectivity-cropland-shards/crop-'+digest[:16]+'.json'
  for directory in (OUT,STATIC):
   target=directory/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
  for pid in chunk:index[pid]={'path':path,'sha256':digest}
 write('connectivity-cropland-map.json',{'source':meta,'projects':index,'shardCount':len(chunks)})


def main():
 manifest=json.loads((SOURCE/'manifest.json').read_text())
 datasets=[rasterio.open(SOURCE/r['file']) for r in manifest['files']]
 cache={}
 def endpoint(lon,lat):
  key=(round(lon,8),round(lat,8))
  if key in cache:return cache[key]
  p=Point(*FORWARD(lon,lat)); search=p.buffer(1300)
  bounds=transform(REVERSE,search).bounds
  selected=[ds for ds in datasets if box(*ds.bounds).intersects(box(*bounds))]
  if not selected:return {'distance':None,'coverage':{r:False for r in (100,500,1000)},'crop':None}
  raster,affine=merge(selected,bounds=bounds,nodata=0)
  data=raster[0];coverage={}
  for radius in (100,500,1000):
   circle=mapping(transform(REVERSE,p.buffer(radius)))
   mask=geometry_mask([circle],out_shape=data.shape,transform=affine,invert=True,all_touched=True)
   coverage[radius]=bool(mask.any() and np.all(data[mask]!=0))
  mask=data==40
  polygons=[transform(FORWARD,shape(geom)) for geom,value in shapes(mask.astype('uint8'),mask=mask,transform=affine) if value==1]
  crop=unary_union(polygons) if polygons else None
  distance=float(p.distance(crop)) if crop is not None and not crop.is_empty else None
  result={'distance':distance,'coverage':coverage,'crop':crop};cache[key]=result;return result
 mapdata=json.loads((OUT/'connectivity-map-data.json').read_text());measurements={};mapcrops={}
 for index,(pid,project) in enumerate(mapdata['projects'].items()):
  if project.get('coordinateQualityFlag'):
   measurements[pid]={'farmObservedDistanceMeters':None,'farmDistanceMeters':None,**{f'farmCoverage{r}m':False for r in (100,500,1000)},'farmSourceYear':2021,'farmSearchRadiusMeters':1000,'farmAssessment':'suppressed_coordinate_review'}
   continue
  measures=[endpoint(float(c[0]),float(c[1])) for c in (project.get('start'),project.get('end')) if c and None not in c]
  distances=[m['distance'] for m in measures if m['distance'] is not None]
  observed=min(distances) if distances else None
  record={'farmObservedDistanceMeters':round(observed,1) if observed is not None else None,'farmDistanceMeters':round(observed,1) if observed is not None and observed<=1000 else None,
          **{f'farmCoverage{r}m':bool(measures) and all(m['coverage'][r] for m in measures) for r in (100,500,1000)},
          'farmSourceYear':2021,'farmSearchRadiusMeters':1000,'farmAssessment':'mapped_cropland_proxy'}
  if not record['farmCoverage1000m'] and not distances:record['farmAssessment']='incomplete_coverage'
  measurements[pid]=record
  crops=[m['crop'] for m in measures if m['crop'] is not None and not m['crop'].is_empty]
  if crops:
   crop=transform(REVERSE,unary_union(crops).simplify(12,preserve_topology=True))
   def rounded(coords):
    if isinstance(coords[0],(int,float)):return [round(v,6) for v in coords]
    return [rounded(c) for c in coords]
   geom=mapping(crop);mapcrops[pid]={'type':geom['type'],'coordinates':rounded(geom['coordinates'])}
  project.update(record)
  if index%100==0:print('measured',index,flush=True)
 data=json.loads((OUT/'connectivity-data.json').read_text())
 for row in data['projects']:
  row.update(measurements[str(row['id'])]);row['connectivityClass']=classify(row)
 summary=dict(Counter(r['connectivityClass'] for r in data['projects']))
 meta={'available':True,'source':'ESA WorldCover 2021 v200 · class 40','sourceUrl':'https://esa-worldcover.org/en/data-access','sourceYear':2021,'resolutionMeters':10,'tileCount':len(datasets),'audit':'connectivity-farm-status.json','mapData':'connectivity-cropland-map.json','method':'Distance from either printed source endpoint to 2021 class-40 cropland pixels; exact raster-derived polygon boundaries in UTM 51N. Display polygons simplified by 12 m. No-data cells remain unknown. Search tested within 1 km of both endpoints.','limits':'Class 40 describes annual herbaceous cropland; woody perennial crops may be tree/shrub cover. This dated satellite classification does not establish present farms, property boundaries, ownership, access or wrongdoing. Measured road and cropland distances use a shared 500 m classification cutoff; exact values remain available, while incomplete raster coverage remains unresolved.','attribution':'© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium','license':'CC BY 4.0'}
 data['farmCoverage']=meta;data['connectivitySummary']=summary
 data['limits']=[x for x in data.get('limits',[]) if 'no farm-boundary layer' not in x];data['limits'].append(meta['limits'])
 write('connectivity-data.json',data);write('connectivity-fmr-road.json',data)
 mapdata['farmLocationAvailable']=True;mapdata['farmSource']=meta;write('connectivity-map-data.json',mapdata)
 publish_crop_maps(meta,mapcrops)
 write('connectivity-cropland-measurements.json',{'source':meta,'projects':{pid:{**measurements[pid],'start':p['start'],'end':p['end']} for pid,p in mapdata['projects'].items()}})
 audit={'checkedAtUtc':datetime.now(timezone.utc).isoformat(),'availableForConnectivity':True,'status':'integrated','source':meta,'tiles':manifest['files'],'projectsAssessed':len(data['projects']),'projectsWithMappedCroplandWithin1km':sum(r['farmDistanceMeters'] is not None for r in data['projects']),'complete1kmCoverage':sum(r['farmCoverage1000m'] for r in data['projects']),'summary':summary,'message':'Farm proximity uses ESA WorldCover 2021 satellite-classified annual cropland at 10 m resolution. Green map areas are crop-cover pixels, not cadastral farm boundaries. Tree crops and more recent land-use changes may be missed.'}
 write('connectivity-farm-status.json',audit)
 for ds in datasets:ds.close()
 print(json.dumps({'projects':len(data['projects']),'croplandMaps':len(mapcrops),'classes':summary,'complete1kmCoverage':audit['complete1kmCoverage']}),flush=True)
if __name__=='__main__':main()
