#!/usr/bin/env python3
"""Inspect candidate service/layer metadata only; never download feature rows."""
import argparse
import json
from types import SimpleNamespace
import urllib.parse
from download_arcgis_inventory import ARCHIVE,BASE,Downloader,safe,write

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('services',nargs='+');args=parser.parse_args()
    root=ARCHIVE/'metadata_review';root.mkdir(parents=True,exist_ok=True)
    client=Downloader(SimpleNamespace(output=root,delay=3,batch_size=200));summary=[]
    for name in args.services:
        relative=name+'/FeatureServer';url=BASE+'/'+urllib.parse.quote(relative,safe='/')
        service=client.cached(url,root/(safe(relative)+'.json'))
        candidates=[r for r in service.get('layers',[])+service.get('tables',[]) if r.get('type')!='Group Layer']
        item={'service':name,'url':url,'description':service.get('serviceDescription') or service.get('description'),'copyright':service.get('copyrightText'),'advertisedLayers':candidates,'inspectedLayers':[]}
        # First thematic layer is enough to review schema. Other IDs stay listed.
        for layer in candidates[:1]:
            target=url+'/'+str(layer['id']);meta=client.cached(target,root/(safe(relative+'/'+str(layer['id']))+'.json'))
            item['inspectedLayers'].append({'id':layer['id'],'name':meta.get('name'),'geometry':meta.get('geometryType'),'description':meta.get('description'),'copyright':meta.get('copyrightText'),'fields':[{'name':f['name'],'alias':f.get('alias'),'type':f['type']} for f in meta.get('fields',[])]})
        summary.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    write(root/'review_summary.json',summary)

if __name__=='__main__':main()
