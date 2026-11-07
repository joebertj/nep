"""Download ESA WorldCover 2021 tiles needed around the FMR endpoints."""
import concurrent.futures
import hashlib
import json
import math
import subprocess
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data_sources/esa_worldcover_2021'
BASE='https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/'

def download(tile):
    lat,lon=tile
    name=f'ESA_WorldCover_10m_2021_v200_N{lat:02d}E{lon:03d}_Map.tif'
    target=OUT/name
    if not target.exists():
        part=target.with_suffix('.tif.part')
        subprocess.run(['curl','--fail','--location','--silent','--show-error','--retry','3','--max-time','300',BASE+name,'-o',str(part)],check=True)
        part.replace(target)
    print(name,target.stat().st_size,flush=True)
    return {'file':name,'url':BASE+name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=json.loads((ROOT/'analysis_output/connectivity-map-data.json').read_text())['projects'].values()
    tiles=set()
    for row in rows:
        for coordinate in (row.get('start'),row.get('end')):
            if not coordinate or None in coordinate:continue
            lon,lat=coordinate
            for x in (lon-.025,lon+.025):
                for y in (lat-.025,lat+.025):tiles.add((math.floor(y/3)*3,math.floor(x/3)*3))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        files=list(pool.map(download,sorted(tiles)))
    manifest={'retrievedAtUtc':datetime.now(timezone.utc).isoformat(),'source':'ESA WorldCover 2021 v200','sourceUrl':'https://esa-worldcover.org/en/data-access','license':'CC BY 4.0','croplandClass':40,'resolutionMeters':10,'files':files}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('COMPLETE',len(files),flush=True)
if __name__=='__main__':main()
