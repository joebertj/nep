"""Approximate endpoint separation, kept separate from stated segment length."""
from analyze_mpb_proximity import PAIR,distance

def approximate(source,ledger=None):
    segments=[];status='No unambiguous endpoint pair recovered';rules=[]
    if ledger is not None:
        rules=ledger.get('normalization_rules',[])
        if ledger.get('status')!='normalized' or ledger.get('review_flags'):
            return {'approximateLengthMeters':None,'approximationStatus':'Coordinate review flags · withheld','approximateAllocationPerMeter':None,'coordinateSegments':[]}
        segments=ledger.get('coordinates',[])
        if not segments or any(len(s)!=2 or any(p is None for p in s) for s in segments):segments=[]
    else:
        points=[]
        for m in PAIR.finditer(source['projectName']):
            a,b=float(m[1]),float(m[2])
            if min(len(m[1].split('.')[1]),len(m[2].split('.')[1]))<4:continue
            if 4<=a<=22 and 116<=b<=127:points.append([b,a])
            elif 116<=a<=127 and 4<=b<=22:points.append([a,b]);rules.append('longitude-first order identified')
        if len(points)==2:segments=[points]
        elif len(points)>2:status='Multiple coordinate points without verified segment pairing · withheld'
    values=[]
    for segment in segments:
        if any(not(116<=p[0]<=127 and 4<=p[1]<=22) for p in segment):values=[];status='Coordinate outside broad PH numeric range · withheld';break
        a,b=segment;meters=distance({'longitude':a[0],'latitude':a[1]},{'longitude':b[0],'latitude':b[1]})
        if meters<=0:values=[];status='Coincident endpoints · approximate rate withheld';break
        values.append(meters)
    length=sum(values) if values else None
    return {'approximateLengthMeters':round(length,1) if length else None,
        'approximateAllocationPerMeter':round(int(source['amountPesos'])/length,2) if length else None,
        'approximationStatus':('APPROXIMATION · sum of labeled segment chords; route alignment unknown' if ledger is not None else 'APPROXIMATION · two printed-point separation; endpoint roles and alignment unverified') if length else status,
        'coordinateSegments':segments,'coordinateNormalizationRules':rules}
