"""Descriptive high-rate screen within official PAP and data-derived length bands."""
import statistics
import re
from collections import Counter


def enrich(data,density):
    def structure(row):
        title=row['projectName']
        for pattern,label in [(r'\bfootbridge\b|\bpedestrian\b','Pedestrian structures'),(r'\boverpass\b|\bflyover\b','Overpasses / flyovers'),(r'\bviaduct\b','Viaducts')]:
            if re.search(pattern,title,re.I):return label
        return row['category']
    bands={(r['category'],r['program']):[] for r in density['bands']}
    for band in density['bands']:bands[(band['category'],band['program'])].append(band)
    for row in data['projects']:row['rateStructureGroup']=structure(row)
    for row in data['projects']:
        row.update({'typicalPeerRate':None,'peerRateMultiple':None,'peerRecords':0,'peerBand':'',
                    'highRateCandidate':False,'graphExtreme':False,'rateReview':'No usable single-category rate'})
        if row['allocationPerStatedMeter'] is None:continue
        if row['lengthMeters']<10:
            row.update({'graphExtreme':True,'rateReview':'Very short printed range · verify length first'});continue
        band=next((b for b in bands.get((row['category'],row['program']),[]) if b['minimumMeters']<=row['lengthMeters'] and (b['maximumMetersExclusive'] is None or row['lengthMeters']<b['maximumMetersExclusive'])),None)
        if band is None:continue
        peers=[r['allocationPerStatedMeter'] for r in data['projects'] if r['category']==row['category'] and r['rateStructureGroup']==row['rateStructureGroup'] and r.get('surfacePeerGroup')==row.get('surfacePeerGroup') and r['program']==row['program'] and r['allocationPerStatedMeter'] is not None and r['lengthMeters']>=10 and band['minimumMeters']<=r['lengthMeters'] and (band['maximumMetersExclusive'] is None or r['lengthMeters']<band['maximumMetersExclusive'])]
        row.update({'peerRecords':len(peers),'peerBand':band['band']})
        if len(peers)<20:
            row['rateReview']='Insufficient peers · no high-rate conclusion';continue
        median=statistics.median(peers);q1,_,q3=statistics.quantiles(peers,n=4,method='inclusive');iqr=q3-q1
        high=row['allocationPerStatedMeter']>max(2*median,q3+1.5*iqr)
        extreme=row['allocationPerStatedMeter']>max(2*median,q3+3*iqr)
        row.update({'typicalPeerRate':round(median,2),'peerRateMultiple':round(row['allocationPerStatedMeter']/median,2),
                    'highRateCandidate':high,'graphExtreme':extreme,'peerUpperFence':q3+1.5*iqr,'graphUpperFence':max(2*median,q3+3*iqr),
                    'rateReview':'High relative rate · scope review needed' if high else 'Within descriptive peer screen'})
    data['highRateScreen']={'candidates':sum(r['highRateCandidate'] for r in data['projects']),
                           'graphExtremeRecords':sum(r['graphExtreme'] for r in data['projects']),
                           'method':'Peers share category, structure group (overpasses/flyovers, viaducts and pedestrian structures separated), official PAP, a data-derived length band, and matched surface/condition/assessment-year context. Unknown context is pooled only with unknown context and remains explicitly unadjusted. At least 20 peers with stated length ≥10m. Candidate rate exceeds both 2× peer median and Q3+1.5×IQR. Chart extremes exceed max(2×median,Q3+3×IQR); sub-10m printed ranges also stay off rate charts. Lane inventory estimates do not enter these per-meter flags.',
                           'limits':'Exploratory relative-rate screen, not proof of overpricing. Width, terrain, structures, engineering quantities and funded extent remain unverified. Missing or insufficient peers produce no high-rate conclusion.'}
    return data
