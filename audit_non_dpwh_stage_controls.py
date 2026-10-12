#!/usr/bin/env python3
"""Verify visible HFEP controls and NIA named-row evidence in local HGAB PDFs."""
import hashlib,json,re,subprocess,tempfile,xml.etree.ElementTree as ET
from pathlib import Path
from hgab_native import page_boxes
from hgab_matching import normalize
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis_output'

def lines(xml,box):
    out=[]
    for l in ET.fromstring(xml).iter('line'):
        cs=[]
        for c in l.iter('char'):
            b=list(map(float,c.get('bbox').split()))
            if box[0]<=(b[0]+b[2])/2<=box[2] and box[1]<=b[1]<=box[3]:cs.append((b[0],b[1],c.get('c','')))
        if cs:
            out.append({'y':sum(c[1] for c in cs)/len(cs),'x':min(c[0] for c in cs),'text':''.join(c[2] for c in cs).strip()})
    return sorted(out,key=lambda r:(r['y'],r['x']))

def build():
    ia=ROOT/'HB 10858 FOR 3RD READING/1- HB 10858 FOR 3RD READING VOL I-A.pdf';ib=ROOT/'HB 10858 FOR 3RD READING/2- HB 10858 FOR 3RD READING VOL I-B.pdf'
    with tempfile.TemporaryDirectory(prefix='nep-hgab-controls-') as tmp:
        p=Path(tmp)/'hfep.xml';subprocess.run(['gs','-q','-dBATCH','-dNOPAUSE','-dTextFormat=1','-sDEVICE=txtwrite','-dFirstPage=1067','-dLastPage=1067',f'-sOutputFile={p}',str(ia)],capture_output=True,check=True)
        ls=lines(p.read_text(),page_boxes('gs',ia)[1066]);title=next(r for r in ls if r['text']=='Health Facilities Enhancement Program')
        row=[r['text'] for r in sorted(ls,key=lambda r:r['x']) if abs(r['y']-title['y'])<3]
        nums=[int(x.replace(',','')) for x in row if re.fullmatch(r'\d{1,3}(?:,\d{3})+',x)]
        if nums!=[67173000,10021659000,10088832000] or nums[0]+nums[1]!=nums[2]:raise ValueError('HFEP visible control does not agree with expected columns')
        hfep={'programme':'Health Facilities Enhancement Program','sourceVolume':ia.name,'sourcePage':1067,'printedPage':1057,'visibleRow':row,'mooePesos':nums[0],'capitalOutlayPesos':nums[1],'totalPesos':nums[2],'sourcePdfSha256':hashlib.sha256(ia.read_bytes()).hexdigest()}
        boxes=page_boxes('gs',ib);p=Path(tmp)/'nia-%d.xml';subprocess.run(['gs','-q','-dBATCH','-dNOPAUSE','-dTextFormat=1','-sDEVICE=txtwrite','-dFirstPage=569','-dLastPage=574',f'-sOutputFile={p}',str(ib)],capture_output=True,check=True)
        pages={569+i:lines((Path(tmp)/f'nia-{i+1}.xml').read_text(),boxes[568+i]) for i in range(6)};checks=[]
        for h in json.loads((ROOT/'hgab_3rd_editions.json').read_text())['nia_named']:
            found=None
            for page,ls in pages.items():
                titles=[l for l in ls if l['x']<350 and re.search(r'[A-Za-z]',l['text'])]
                for i,l in enumerate(titles):
                    for n in range(1,5):
                        window=titles[i:i+n]
                        if len(window)!=n or window[-1]['y']-window[0]['y']>40:continue
                        if normalize(h['projectName']) not in normalize(' '.join(x['text'] for x in window)):continue
                        amounts=[x['text'] for x in ls if x['x']>=350 and window[0]['y']-3<=x['y']<=window[-1]['y']+4 and re.fullmatch(r'\d{1,3}(?:,\d{3})+',x['text'])]
                        if str(h['amountPesos']) in [x.replace(',','') for x in amounts]:found={'sourcePage':page,'titleFragments':[x['text'] for x in window],'amountFragments':amounts}
                        if found:break
                    if found:break
                if found:break
            checks.append({'hgabId':h['id'],'projectName':h['projectName'],'amountPesos':h['amountPesos'],'visibleRowVerified':bool(found),'evidence':found})
    result={'hfepControl':hfep,'niaChecks':checks,'niaSourcePdfSha256':hashlib.sha256(ib.read_bytes()).hexdigest(),'method':'Ghostscript XML characters clipped to PDF CropBox before reconstructing visible lines. HFEP programme row columns reconcile. NIA whole-title fragments must agree within a 40-point vertical window with the expected printed amount in the amount columns. Original source fragments and actual PDF pages retained.','limits':'Checks verify title/amount transcription, not engineering scope, cross-stage identity or bill authenticity.'}
    (OUT/'non_dpwh_stage_control_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result
if __name__=='__main__':
    d=build();print(json.dumps({'hfep':d['hfepControl'],'niaVerified':sum(r['visibleRowVerified'] for r in d['niaChecks']),'niaChecks':len(d['niaChecks'])},indent=2))
