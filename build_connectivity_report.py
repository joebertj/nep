"""Build the FY2027 FMR-to-road screen and attach shared place inventories."""
from __future__ import annotations

import json
import math
import hashlib
import re
from sync_connectivity_manual_greens import sync_from_server
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
FMR = ROOT / 'analysis_output' / 'fmr_corrected_dataset.json'
ROAD = ROOT / 'data_sources/arcgis_dpwh/archive/selected/road_classification/layers/Road_Classification_FeatureServer_1-b0aa1cb4/features.jsonl'
OUT = ROOT / 'analysis_output' / 'connectivity-fmr-road.json'
SOURCE_DATA = ROOT / 'analysis_output' / 'connectivity-data.json'
SOURCE_ROAD_PROJECTS = ROOT / 'analysis_output' / 'connectivity-road-projects.json'
PAGE = STATIC / 'connectivity.html'
DATA = STATIC / 'connectivity-data.json'
SCRIPT = STATIC / 'connectivity.js'
CELL = 1000.0
ROUTE_CONNECTION_TOLERANCE_M = 50.0
ROUTE_SEARCH_RADIUS_M = 1000.0
MAX_ENDPOINT_GAP_M = 20000.0

JS = r'''(()=>{
  const n=x=>Number(x||0).toLocaleString('en-PH'),peso=x=>'₱'+n(x),
    esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const distanceColors=['#25834b','#b4232e'],unknownColor='#89959e';
  const connectivityApiBase=location.hostname==='research.bettergov.ph'?'https://visualizations.bettergov.ph':'';
  const apiFailure=async response=>{let detail='';try{detail=(await response.json()).detail||''}catch{}return new Error(`HTTP ${response.status}${detail?': '+detail:''}`)};
  const adminHash=new URLSearchParams(location.search).get('hash')||'';
  window.connectivityAdminAccess=adminHash?fetch(connectivityApiBase+'/api/connectivity/manual-greens?hash='+encodeURIComponent(adminHash),{cache:'no-store'}).then(async response=>{if(!response.ok)return null;const saved=await response.json();document.documentElement.dataset.connectivityAdmin='true';document.documentElement.dataset.connectivityReveal='true';document.getElementById('connectivity-source-name-notice')?.removeAttribute('hidden');return saved}).catch(()=>null):Promise.resolve(null);
  const manualGreenOptions=[['near-produce','Near green space likely used for produce'],['closes-loop','Closes a road loop'],['extends-road','Extends an existing road'],['road-segment','Part of a continuous road segment'],['connects-road-segments','Connects two road segments'],['near-school','Near a school'],['near-health-center','Near a health center'],['near-hospital','Near a hospital']];
  const manualGreenLabels=Object.fromEntries(manualGreenOptions);
  const manualRedOptions=[['section2-visitor-venue','Near a mapped visitor venue'],['section2-subdivision-village','Near a subdivision or village'],['section2-large-residential-property','Near a large residential property'],['section2-restricted-access-property','Near a restricted-access property'],['section2-private-property-cue','Near another mapped private-property cue'],['section2-coordinate-quality','Coordinate quality needs review'],['baywalk-shoreline-review','Baywalk / shoreline ecological review']];
  const manualRedLabels=Object.fromEntries(manualRedOptions);
  const downloadJson=(filename,payload)=>{const blob=new Blob([JSON.stringify(payload,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)};
  const exportProject=row=>{const keys=['id','title','region','amountPesos','sourcePage','coordinateBasis','startLatitude','startLongitude','endLatitude','endLongitude','coordinateGapMeters','coordinateQualityFlag','flagTags','connectivityClass','result','roadName','roadClass','roadSection','nearestDistanceMeters','startDistanceMeters','endDistanceMeters','farmDistanceMeters','farmCoverage1000m','farmAssessment','unpavedRoadConnection','routeNetworkDistanceMeters','routeNetworkStatus','routeNetworkExemption','exemptionReasons','manualGreenReasons','manualGreenNote','manualRedReasons','manualRedReason','exemptionNote','userMapReviewNotes','ecologicalReview','nearbyPublicServices','nearbyPublicServiceEvidence','nearbySubdivisionVillageCount','nearbyVisitorVenueCount'];return Object.fromEntries(keys.filter(key=>row[key]!==undefined).map(key=>[key,row[key]]))};
  const roadBand=value=>value==null?null:value<=500?0:1;
  const farmBand=row=>row.farmDistanceMeters!=null?(row.farmDistanceMeters<=50?0:1):row.farmCoverage1000m?1:null;
  const roadDistanceLabel=band=>['≤500 m','>500 m'][band]||'Unresolved';
  const farmDistanceLabel=band=>['≤50 m','>50 m'][band]||'Unresolved';
  const reviewDetail=row=>{const road=roadBand(row.nearestDistanceMeters),farm=farmBand(row);return road==null||farm==null?'Road or cropland distance unresolved':`Road ${roadDistanceLabel(road)} × cropland ${farmDistanceLabel(farm)}`};
  const endpointGapMeters=row=>{const raw=[row.startLatitude,row.startLongitude,row.endLatitude,row.endLongitude];if(raw.some(v=>v==null||v===''))return null;const c=raw.map(Number);if(!c.every(Number.isFinite))return null;const rad=x=>x*Math.PI/180,dl=rad(c[2]-c[0]),dn=rad(c[3]-c[1]),a=Math.sin(dl/2)**2+Math.cos(rad(c[0]))*Math.cos(rad(c[2]))*Math.sin(dn/2)**2;return 6371008.8*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a))};
  const coordinateFlag=row=>Boolean(row.coordinateQualityFlag)||(endpointGapMeters(row)||0)>20000;
  const googleMapsEndpoints=row=>{const coords=[row.startLatitude,row.startLongitude,row.endLatitude,row.endLongitude].map(Number);if(!coords.every(Number.isFinite))return '';const origin=encodeURIComponent(coords[0]+','+coords[1]),destination=encodeURIComponent(coords[2]+','+coords[3]),center=((coords[0]+coords[2])/2)+','+((coords[1]+coords[3])/2),satellite='https://www.google.com/maps/@?api=1&map_action=map&center='+encodeURIComponent(center)+'&zoom=14&basemap=satellite',gap=endpointGapMeters(row),directions='https://www.google.com/maps/dir/?api=1&origin='+origin+'&destination='+destination+'&travelmode=driving',route=gap>20000?`<strong style="display:block;color:#8f1515;background:#fee2e2;padding:3px 6px">⚠ RED FLAG: endpoints about ${n(gap/1000)} km apart; spatial calculations suppressed</strong><a href="${directions}" target="_blank" rel="noopener noreferrer" title="Google Maps suggested driving route and distance between endpoints; not the project alignment or straight-line measurement">Route + distance ↗</a>`:`<a href="${directions}" target="_blank" rel="noopener noreferrer" title="Google Maps suggested driving route and distance between endpoints; not the project alignment or straight-line measurement">Route + distance ↗</a>`;return `<a href="${satellite}" target="_blank" rel="noopener noreferrer" title="Satellite view centered between the printed source endpoints">Google Maps satellite ↗</a> · ${route}`};
  const rgb=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
  const multiplyColors=(a,b)=>'#'+rgb(a).map((v,i)=>Math.round(v*rgb(b)[i]/255).toString(16).padStart(2,'0')).join('');
  const textColor=color=>{const c=rgb(color).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return c[0]*.2126+c[1]*.7152+c[2]*.0722>.179?'#111':'#fff'};
  const colorStyle=color=>`background:${color};color:${textColor(color)};font-variant-numeric:tabular-nums`;
  const bandStyle=band=>colorStyle(band==null?unknownColor:distanceColors[band]);
  const finalColor=row=>{if(coordinateFlag(row))return unknownColor;const road=roadBand(row.nearestDistanceMeters),farm=farmBand(row);return road==null||farm==null?unknownColor:multiplyColors(distanceColors[road],distanceColors[farm])};
  if(location.protocol==='file:'){
    const message='Connectivity data is stored in separate JSON files. Open this page through the local web server (HTTP), not directly as a file.';
    document.getElementById('rows').innerHTML='<tr><td colspan="11">'+message+'</td></tr>';
    document.getElementById('road-project-count').textContent=message;
    return;
  }
  fetch('connectivity-farm-status.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{const note=document.getElementById('farm-data-status');if(note)note.textContent=d.message+' Checked '+new Date(d.checkedAtUtc).toLocaleDateString('en-PH')+'.';}).catch(()=>{const note=document.getElementById('farm-data-status');if(note)note.textContent='Farm proximity is not assessed; the local farm-data audit could not be loaded.';});
  fetch('connectivity-data.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('connectivity-data.json returned HTTP '+r.status);return r.json()}).then(async d=>{
    const rows=d.projects||[],q=document.getElementById('q'),sel=document.getElementById('result'),sortControl=document.getElementById('connectivity-sort'),excludeGreen=document.getElementById('exclude-green-exemptions'),body=document.getElementById('rows'),projectCount=document.getElementById('connectivity-project-count'),pageLabel=document.getElementById('connectivity-project-page'),prev=document.getElementById('connectivity-project-prev'),next=document.getElementById('connectivity-project-next'),size=document.getElementById('connectivity-project-size');let admin=false,page=0,currentItems=[],manualGreenMap={};
    const authorizedAnnotations=await window.connectivityAdminAccess;
    if(authorizedAnnotations){admin=true;manualGreenMap=authorizedAnnotations.projects||{}}
    const manualRecord=x=>manualGreenMap[x.id]||null;
    const manualReasons=x=>{const record=manualRecord(x);return record?(record.greenReasons||record.reasons||[]):(x.manualGreenReasons||[])};
    const manualGreenNote=x=>{const record=manualRecord(x);return record?String(record.greenNote||''):String(x.manualGreenNote||'')};
    const manualRedReasons=x=>{const record=manualRecord(x),values=record?record.redReasons:x.manualRedReasons;return Array.isArray(values)?values.filter(value=>Object.hasOwn(manualRedLabels,value)):[]};
  const manualRedReason=x=>{const record=manualRecord(x);return record?String(record.redReason||''):String(x.manualRedReason||'')};
    const classSummary=d.connectivitySummary||d.summary||{};Object.keys(classSummary).forEach(x=>sel.add(new Option(`${x} (${n(classSummary[x])})`,x)));
    const reviewCounts=new Map();rows.filter(r=>String(r.connectivityClass||'').startsWith('Review')).forEach(r=>{const key=reviewDetail(r);reviewCounts.set(key,(reviewCounts.get(key)||0)+1)});
    [...reviewCounts.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).forEach(([label,count])=>sel.add(new Option(`${label} (${n(count)})`,`review:${label}`)));
    document.getElementById('road-stats').innerHTML=Object.entries(d.connectivitySummary||d.summary||{}).map(([k,v])=>`<div class="stat"><strong>${n(v)}</strong>${esc(k)}</div>`).join('')+`<div class="stat"><strong>${n(rows.length)}</strong>FMR projects · ${n(d.roadFeatures)} DPWH road sections</div>`;
    const order=['Near road · ≤500 m','No nearby DPWH classified road · >500 m','Coordinate review · endpoints >20 km apart'],colors=['#25834b','#b4232e','#6b7280'],max=Math.max(1,...order.map(k=>Number(d.summary?.[k]||0)));
    document.getElementById('road-distance-chart').innerHTML=order.map((label,i)=>{const value=Number(d.summary?.[label]||0);return `<div class="road-chart-row"><span>${esc(label.replace(/^.*· /,''))}</span><div class="road-chart-track"><i style="width:${value/max*100}%;background:${colors[i]}"></i></div><strong>${n(value)}</strong></div>`}).join('');
    const combined=document.getElementById('farm-road-chart');if(combined){const labels=['Baseline FMR · road ≤500 m and mapped cropland ≤50 m','Flag FMR · only one distance threshold met','Double Flag FMR · road >500 m and mapped cropland >50 m','Unresolved · incomplete cropland coverage','Coordinate review · endpoints >20 km apart'],total=rows.length;combined.innerHTML=labels.map(label=>{const matches=rows.filter(r=>r.connectivityClass===label),colors={};matches.forEach(r=>{const c=finalColor(r);colors[c]=(colors[c]||0)+1});return `<div class="road-chart-row"><span>${esc(label)}</span><div class="road-chart-track" style="display:flex">${Object.entries(colors).sort(([a],[b])=>a.localeCompare(b)).map(([color,count])=>`<i style="width:${total?count/total*100:0}%;background:${color};border-radius:0" title="${n(count)} FMRs · combined road and farm distance colors"></i>`).join('')}</div><strong>${n(matches.length)}</strong></div>`}).join('');}
    const reviewChart=document.getElementById('farm-road-review-chart');if(reviewChart){const max=Math.max(1,...reviewCounts.values());reviewChart.innerHTML=[...reviewCounts.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).map(([label,count])=>{const sample=rows.find(r=>String(r.connectivityClass||'').startsWith('Review')&&reviewDetail(r)===label);return `<div class="road-chart-row"><span>${esc(label)}</span><div class="road-chart-track"><i style="width:${count/max*100}%;background:${finalColor(sample)}"></i></div><strong>${n(count)}</strong></div>`}).join('')||'<p class="note">No projects currently fall into Review.</p>'; }
    const farmChart=document.getElementById('farm-distance-chart');if(farmChart){const labels=['≤50 m','>50 m','Unresolved','Coordinate review · endpoints >20 km apart'],counts=labels.map((_,i)=>rows.filter(r=>i===3?coordinateFlag(r):!coordinateFlag(r)&&farmBand(r)===(i===2?null:i)).length),max=Math.max(1,...counts);farmChart.innerHTML=labels.map((label,i)=>`<div class="road-chart-row"><span>${esc(label)}</span><div class="road-chart-track"><i style="width:${counts[i]/max*100}%;background:${i===3?'#6b7280':distanceColors[i]||unknownColor}"></i></div><strong>${n(counts[i])}</strong></div>`).join('');}
    function draw(){const term=q.value.trim().toLowerCase(),selected=sel.value,sortMode=sortControl?.value||'screen-amount-desc',items=rows.filter(x=>(!selected||(selected.startsWith('review:')?String(x.connectivityClass||'').startsWith('Review')&&reviewDetail(x)===selected.slice(7):(x.connectivityClass||x.result)===selected))&&(!term||`${x.title} ${x.region} ${x.roadName}`.toLowerCase().includes(term))&&(!excludeGreen?.checked||!x.exemptionReasons?.length&&!manualReasons(x).length&&!manualGreenNote(x))).sort((a,b)=>{const av=a.coordinateGapMeters??endpointGapMeters(a),bv=b.coordinateGapMeters??endpointGapMeters(b),aGap=av==null?(sortMode==='gap-asc'?Infinity:-Infinity):Number(av),bGap=bv==null?(sortMode==='gap-asc'?Infinity:-Infinity):Number(bv),amount=Number(b.amountPesos||0)-Number(a.amountPesos||0);if(sortMode==='screen-amount-desc'){const rank=x=>{const label=x.connectivityClass||x.result||'';return label.startsWith('Double Flag')?0:label.startsWith('Flag')?1:label.startsWith('Coordinate review')?2:label.startsWith('Baseline')?3:4};return rank(a)-rank(b)||amount||String(a.title).localeCompare(String(b.title))}return sortMode==='amount-desc'?amount:sortMode==='gap-asc'?aGap-bGap:bGap-aGap||amount});currentItems=items;const per=Number(size?.value||20),pages=Math.max(1,Math.ceil(items.length/per));page=Math.min(page,pages-1);body.innerHTML=items.slice(page*per,(page+1)*per).map(x=>{const badCoordinate=coordinateFlag(x),ecological=Boolean(x.ecologicalReview),exemptionHtml=(x.exemptionReasons||[]).map(reason=>reason.startsWith('User map review:')?`<span class="review-note-label">Review note · ${esc(reason.replace(/^User map review:\s*/,''))}</span>`:`<span class="positive-exemption-label">Positive exemption · ${esc(reason)}</span>`).join(''),manualReasonsForRow=manualReasons(x),manualNoteForRow=manualGreenNote(x),manualRedForRow=manualRedReason(x),manualRedReasonsForRow=manualRedReasons(x),manualGreenHtml=manualReasonsForRow.map(reason=>`<span class="positive-exemption-label">Manual green · ${esc(manualGreenLabels[reason]||reason)}</span>`).join('')+(manualNoteForRow?'<span class="positive-exemption-label">Manual green note · '+esc(manualNoteForRow)+'</span>':''),manualRedHtml=[...manualRedReasonsForRow.map(reason=>'<span class="manual-red-label">Human red flag · '+esc(manualRedLabels[reason])+'</span>'),...(manualRedForRow?['<span class="manual-red-label">Human red flag note · '+esc(manualRedForRow)+'</span>']:[])].join(''),contextNote=x.exemptionNote?`<span class="review-note-label">Context · ${esc(x.exemptionNote)}</span>`:'',userNotes=(x.userMapReviewNotes||[]).map(note=>`<span class="review-note-label">Review note · ${esc(note)}</span>`).join(''),coordinateNote=x.id==='ib:p709:r12'?'<span class="review-note-label">Source coordinate review · printed start longitude 122.979706 appears suspect; 122.09706 would put endpoints about 2.15 km apart, but that correction is unverified.</span>':'',dpwhConnected=Boolean(x.routeNetworkExemption)||Number(x.nearestDistanceMeters)<=50||(x.routeNetworkDistanceMeters!=null&&Number(x.routeNetworkDistanceMeters)<=50),prefersUnpaved=String(x.unpavedRoadConnection?.status||'').startsWith('Likely connected')&&!dpwhConnected,exemptionCell=badCoordinate?(coordinateNote||'<span class="review-note-label">Coordinate review · spatial analysis suppressed.</span>'):(ecological?`<span class="ecological-review-label">Negative review flag · Baywalk/ecological screening</span><small>${esc(x.ecologicalReview)}</small>`:'')+(manualRedHtml||'')+exemptionHtml+manualGreenHtml+userNotes+(contextNote||(!ecological&&!exemptionHtml&&!userNotes?'—':''));return `<tr class="${badCoordinate?'coordinate-flag':(manualRedForRow||manualRedReasonsForRow.length)?'manual-red-flag':ecological?'ecological-review':(x.exemptionReasons?.length||manualReasonsForRow.length||manualNoteForRow)?'route-exempt':''}"${badCoordinate?' style="background:#fff0f0;box-shadow:inset 4px 0 #b91c1c"':''}><td><button type="button" class="connectivity-map-open" data-connectivity-map="${esc(x.id)}" aria-label="Open FMR route and nearby road map for ${esc(x.title)}">FMR + road map</button><small>${googleMapsEndpoints(x)}</small> ${esc(x.title)}<small>Printed source p. ${esc(x.sourcePage)} · ${esc(x.coordinateBasis)}</small></td><td class="num endpoint-gap-cell">${x.coordinateGapMeters==null?'—':(Number(x.coordinateGapMeters)/1000).toFixed(3)+' km'}</td><td>${esc(x.region)}</td><td class="distance-cell" style="${bandStyle(roadBand(x.nearestDistanceMeters))}">${badCoordinate?'Suppressed · coordinate review':prefersUnpaved?esc(x.unpavedRoadConnection.name||x.unpavedRoadConnection.highway||'Mapped unpaved road'):esc(x.roadName)}<small>${badCoordinate?'Road proximity not assessed':prefersUnpaved?'Primary connection · mapped unpaved road':`${esc(x.roadClass)} · ${esc(x.roadSection)}`}</small><small>${badCoordinate?'Endpoint gap exceeds 20 km':prefersUnpaved?`DPWH classified-road comparison: nearest endpoint ${n(x.nearestDistanceMeters)} m away`:`${n(x.nearestDistanceMeters)} m from closest endpoint`}</small></td><td class="unpaved-connection-cell">${badCoordinate?'Suppressed · coordinate review':esc(x.unpavedRoadConnection?.status||'Not assessed')}${x.unpavedRoadConnection?.distanceMeters!=null?`<small>${n(x.unpavedRoadConnection.distanceMeters)} m · ${esc(x.unpavedRoadConnection.name||x.unpavedRoadConnection.highway||'Mapped road')}</small>`:''}</td><td class="num distance-cell" style="${bandStyle(roadBand(x.startDistanceMeters))}">${badCoordinate?'—':n(x.startDistanceMeters)}</td><td class="num distance-cell" style="${bandStyle(roadBand(x.endDistanceMeters))}">${badCoordinate||x.endDistanceMeters==null?'—':n(x.endDistanceMeters)}</td><td class="distance-cell" style="${bandStyle(farmBand(x))}">${badCoordinate?'Suppressed · coordinate review':x.farmDistanceMeters!=null?n(x.farmDistanceMeters)+' m':x.farmCoverage1000m?'>1,000 m':'Unresolved'}<small>${badCoordinate?'Cropland proximity not assessed':'Mapped annual cropland · 2021'+(x.farmCoverage1000m?'':' · incomplete coverage')}</small></td><td class="combined-cell" style="${colorStyle(finalColor(x))}">${esc(x.connectivityClass||x.result)}${String(x.connectivityClass||'').startsWith('Review')?`<small>${esc(reviewDetail(x))}</small>`:''}<small>Road: ${esc(x.result)}</small>${x.flagTags?.includes('Nearest endpoint >500 m from DPWH classified road network')?'<small>Flag tag: nearest endpoint is over 500 m from the DPWH classified road network</small>':''}</td><td class="exemption-cell">${exemptionCell}</td><td class="num">${peso(x.amountPesos)}</td></tr>`}).join('')||'<tr><td colspan="11">No matching records.</td></tr>';if(admin){items.slice(page*per,(page+1)*per).forEach((x,i)=>{const cell=body.rows[i]?.cells[8];if(!cell)return;const record=manualRecord(x),reasons=manualReasons(x),greenNote=manualGreenNote(x),redReason=manualRedReason(x),editor=document.createElement('details');editor.className='manual-green-editor';const summary=document.createElement('summary');summary.textContent='Manual green / red review';editor.append(summary);const greenHeading=document.createElement('strong');greenHeading.textContent='Green exemptions';editor.append(greenHeading);manualGreenOptions.forEach(([value,label])=>{const wrapper=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.manualProject=x.id;input.dataset.manualReason=value;input.checked=reasons.includes(value);wrapper.append(input,document.createTextNode(' '+label));editor.append(wrapper)});const greenLabel=document.createElement('label');greenLabel.textContent='Green note (optional)';const greenInput=document.createElement('textarea');greenInput.dataset.manualGreenNote=x.id;greenInput.value=greenNote;greenInput.maxLength=2000;greenLabel.append(greenInput);editor.append(greenLabel);const redHeading=document.createElement('strong');redHeading.textContent='Manual red flags';editor.append(redHeading);const selectedRedReasons=manualRedReasons(x);manualRedOptions.forEach(([value,label])=>{const wrapper=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.dataset.manualRedProject=x.id;input.dataset.manualRedReasonCategory=value;input.checked=selectedRedReasons.includes(value)||value==='baywalk-shoreline-review'&&redReason.startsWith('Baywalk / shoreline ecological review:');wrapper.append(input,document.createTextNode(' '+label));editor.append(wrapper)});const redLabel=document.createElement('label'),redToggle=document.createElement('input');redToggle.type='checkbox';redToggle.dataset.manualRedToggle=x.id;redToggle.checked=Boolean(selectedRedReasons.length||redReason);redLabel.append(redToggle,document.createTextNode(' Mark for human review'));editor.append(redLabel);const reasonLabel=document.createElement('label');reasonLabel.textContent='Additional free-form red flag note';const reasonInput=document.createElement('textarea');reasonInput.dataset.manualRedReason=x.id;reasonInput.value=redReason;reasonInput.maxLength=2000;reasonLabel.append(reasonInput);editor.append(reasonLabel);const save=document.createElement('button');save.type='button';save.dataset.manualSave=x.id;save.textContent='Save review';editor.append(save);cell.append(editor)})}projectCount.textContent=`Showing ${n(items.length)} matching FMR projects`;if(pageLabel)pageLabel.textContent=`${items.length?page*per+1:0}–${Math.min((page+1)*per,items.length)} of ${n(items.length)} · Page ${page+1} of ${pages}`;if(prev)prev.disabled=page===0;if(next)next.disabled=page>=pages-1}
    if(admin)body.addEventListener('click',async event=>{const button=event.target.closest('[data-manual-save]');if(!button)return;const id=button.dataset.manualSave,reasons=[...body.querySelectorAll('input[data-manual-project]')].filter(input=>input.dataset.manualProject===id&&input.checked).map(input=>input.dataset.manualReason),greenNote=body.querySelector('textarea[data-manual-green-note="'+CSS.escape(id)+'"]')?.value.trim()||'',redCategories=[...body.querySelectorAll('input[data-manual-red-project]')].filter(input=>input.dataset.manualRedProject===id&&input.checked).map(input=>input.dataset.manualRedReasonCategory),redEnabled=(body.querySelector('input[data-manual-red-toggle="'+CSS.escape(id)+'"]')?.checked||false)||redCategories.length>0,redReason=body.querySelector('textarea[data-manual-red-reason="'+CSS.escape(id)+'"]')?.value.trim()||'';if(redEnabled&&!redCategories.length&&!redReason){alert('Choose a manual red flag category or add a free-form reason.');return}button.disabled=true;try{const response=await fetch(connectivityApiBase+'/api/connectivity/manual-greens?hash='+encodeURIComponent(new URLSearchParams(location.search).get('hash')||''),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,greenReasons:reasons,greenNote,redReasons:redEnabled?redCategories:[],redReason:redEnabled?redReason:''})});if(!response.ok)throw await apiFailure(response);const saved=await response.json();manualGreenMap=saved.projects||{};draw()}catch(error){alert('Could not save manual review: '+error.message)}finally{button.disabled=false}});
    q.addEventListener('input',()=>{page=0;draw()});sel.addEventListener('change',()=>{page=0;draw()});excludeGreen?.addEventListener('change',()=>{page=0;draw()});sortControl?.addEventListener('change',()=>{page=0;draw()});size?.addEventListener('change',()=>{page=0;draw()});if(prev)prev.onclick=()=>{page--;draw()};if(next)next.onclick=()=>{page++;draw()};document.getElementById('connectivity-json-export')?.addEventListener('click',()=>downloadJson('connectivity-filtered-fmr-projects.json',{schemaVersion:1,exportedAtUtc:new Date().toISOString(),filters:{search:q.value.trim(),result:sel.value||'all',sort:sortControl?.value||'screen-amount-desc'},rowCount:currentItems.length,projects:currentItems.map(x=>exportProject({...x,manualGreenReasons:manualReasons(x),manualGreenNote:manualGreenNote(x),manualRedReason:manualRedReason(x)}))}));draw();
  }).catch(e=>{document.getElementById('rows').innerHTML='<tr><td colspan="11">Connectivity data unavailable: '+esc(e.message||e)+'</td></tr>';});

})();
'''


def utm51(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 to UTM zone 51N, matching the archived DPWH ArcGIS layers."""
    a, ecc_sq, k0 = 6378137.0, 0.00669437999014, 0.9996
    lat_r, lon_r = math.radians(lat), math.radians(lon)
    lon0 = math.radians(123.0)
    ecc_p = ecc_sq / (1 - ecc_sq)
    n = a / math.sqrt(1 - ecc_sq * math.sin(lat_r) ** 2)
    t = math.tan(lat_r) ** 2
    c = ecc_p * math.cos(lat_r) ** 2
    aa = math.cos(lat_r) * (lon_r - lon0)
    m = a * ((1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256) * lat_r
             - (3 * ecc_sq / 8 + 3 * ecc_sq**2 / 32 + 45 * ecc_sq**3 / 1024) * math.sin(2 * lat_r)
             + (15 * ecc_sq**2 / 256 + 45 * ecc_sq**3 / 1024) * math.sin(4 * lat_r)
             - (35 * ecc_sq**3 / 3072) * math.sin(6 * lat_r))
    x = k0 * n * (aa + (1 - t + c) * aa**3 / 6 + (5 - 18*t + t*t + 72*c - 58*ecc_p) * aa**5 / 120) + 500000
    y = k0 * (m + n * math.tan(lat_r) * (aa**2 / 2 + (5 - t + 9*c + 4*c*c) * aa**4 / 24
              + (61 - 58*t + t*t + 600*c - 330*ecc_p) * aa**6 / 720))
    return x, y


def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx*dx + dy*dy
    t = 0 if den == 0 else max(0, min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / den))
    return math.hypot(p[0] - (a[0] + t*dx), p[1] - (a[1] + t*dy))


def endpoint_gap_meters(a, b):
    """Great-circle distance between printed endpoints in lon/lat order."""
    lon1, lat1, lon2, lat2 = map(math.radians, (float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    dlat, dlon = lat2-lat1, lon2-lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371008.8 * 2 * math.atan2(math.sqrt(h), math.sqrt(1-h))


def cell(point):
    return int(point[0] // CELL), int(point[1] // CELL)


def nearest_road(point, grid, segments, bounds):
    """Expand the indexed cell search until no unsearched segment can be nearer."""
    cx, cy = cell(point)
    min_x, max_x, min_y, max_y = bounds
    max_radius = max(abs(cx - min_x), abs(cx - max_x), abs(cy - min_y), abs(cy - max_y))
    seen = set()
    best = (float('inf'), None)
    for radius in range(max_radius + 1):
        if radius == 0:
            cells = ((cx, cy),)
        else:
            cells = (
                [(x, cy - radius) for x in range(cx - radius, cx + radius + 1)]
                + [(x, cy + radius) for x in range(cx - radius, cx + radius + 1)]
                + [(cx - radius, y) for y in range(cy - radius + 1, cy + radius)]
                + [(cx + radius, y) for y in range(cy - radius + 1, cy + radius)]
            )
        candidates = set()
        for key in cells:
            candidates.update(grid.get(key, ()))
        for idx in candidates - seen:
            a, b, attrs = segments[idx]
            distance = point_segment_distance(point, a, b)
            if distance < best[0]:
                best = distance, attrs
        seen.update(candidates)
        left, right = (cx - radius) * CELL, (cx + radius + 1) * CELL
        bottom, top = (cy - radius) * CELL, (cy + radius + 1) * CELL
        unsearched_gap = min(point[0] - left, right - point[0], point[1] - bottom, top - point[1])
        if math.isfinite(best[0]) and unsearched_gap > best[0]:
            return best
        if radius >= max_radius:
            return best
    return best


def segment_distance(a, b, c, d):
    """Minimum planar distance between two UTM line segments."""
    def orient(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on_segment(p, q, r):
        return min(p[0],r[0])-1e-8 <= q[0] <= max(p[0],r[0])+1e-8 and min(p[1],r[1])-1e-8 <= q[1] <= max(p[1],r[1])+1e-8
    o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
    if ((o1*o2 < 0 and o3*o4 < 0) or
        (abs(o1)<1e-8 and on_segment(a,c,b)) or (abs(o2)<1e-8 and on_segment(a,d,b)) or
        (abs(o3)<1e-8 and on_segment(c,a,d)) or (abs(o4)<1e-8 and on_segment(c,b,d))):
        return 0.0
    return min(point_segment_distance(a,c,d), point_segment_distance(b,c,d),
               point_segment_distance(c,a,b), point_segment_distance(d,a,b))


def nearest_road_to_route(route_parts, grid, segments, bounds):
    """Find nearest classified-road segment to any source-geometry leg."""
    legs=[]
    for part in route_parts:
        points=[utm51(float(lon),float(lat)) for lon,lat in part]
        legs.extend(zip(points,points[1:]))
    if not legs:
        return float('inf'), None
    best=(float('inf'),None)
    min_x,max_x,min_y,max_y=bounds
    for a,b in legs:
        x0=max(min_x,int((min(a[0],b[0])-ROUTE_SEARCH_RADIUS_M)//CELL))
        x1=min(max_x,int((max(a[0],b[0])+ROUTE_SEARCH_RADIUS_M)//CELL))
        y0=max(min_y,int((min(a[1],b[1])-ROUTE_SEARCH_RADIUS_M)//CELL))
        y1=min(max_y,int((max(a[1],b[1])+ROUTE_SEARCH_RADIUS_M)//CELL))
        candidates=set()
        for gx in range(x0,x1+1):
            for gy in range(y0,y1+1): candidates.update(grid.get((gx,gy),()))
        for idx in candidates:
            c,d,attrs=segments[idx]
            distance=segment_distance(a,b,c,d)
            if distance<best[0]: best=(distance,attrs)
            if best[0]==0:return best
    return best


def route_legs_utm(route_parts):
    legs=[]
    for part in route_parts:
        points=[utm51(float(lon),float(lat)) for lon,lat in part]
        legs.extend(zip(points,points[1:]))
    return legs


def nearby_service_details(route_parts, service_grid, service_points, radius=500.0):
    legs=route_legs_utm(route_parts);candidates=set()
    for a,b in legs:
        x0=int((min(a[0],b[0])-radius)//CELL);x1=int((max(a[0],b[0])+radius)//CELL)
        y0=int((min(a[1],b[1])-radius)//CELL);y1=int((max(a[1],b[1])+radius)//CELL)
        for gx in range(x0,x1+1):
            for gy in range(y0,y1+1):candidates.update(service_grid.get((gx,gy),()))
    found=[]
    for idx in candidates:
        row,point=service_points[idx]
        distance=min(point_segment_distance(point,a,b) for a,b in legs)
        if distance<=radius:
            found.append({'name':row.get('name') or row.get('type'),'type':row.get('type') or 'Public service',
                          'distanceMeters':round(distance,1),'sourceUrl':row.get('sourceUrl')})
    return sorted(found,key=lambda x:(x['type'],x['distanceMeters'],x['name']))


def place_point_index(rows):
    grid=defaultdict(list);points=[]
    for row in rows:
        try: point=utm51(float(row['longitude']),float(row['latitude']))
        except (KeyError,TypeError,ValueError):continue
        idx=len(points);points.append((row,point));grid[cell(point)].append(idx)
    return grid,points


def build():
    # Always refresh the private review snapshot before calculations. If SSH
    # or schema validation fails, stop rather than publish from stale reviews.
    _, sync_summary = sync_from_server()
    print(f"Fetched {sync_summary['records']:,} manual review records from server.")
    grid = defaultdict(list)
    segments = []
    roads = 0
    road_classes = Counter()
    with ROAD.open() as f:
        for line in f:
            feature = json.loads(line)
            attrs, paths = feature.get('attributes') or {}, (feature.get('geometry') or {}).get('paths') or []
            roads += 1
            road_classes[str(attrs.get('ROAD_SEC_CLASS') or 'Unclassified')] += 1
            for path in paths:
                pts = [(float(x), float(y)) for x, y, *_ in path]
                for a, b in zip(pts, pts[1:]):
                    idx = len(segments)
                    segments.append((a, b, attrs))
                    for gx in range(int(min(a[0],b[0])//CELL), int(max(a[0],b[0])//CELL)+1):
                        for gy in range(int(min(a[1],b[1])//CELL), int(max(a[1],b[1])//CELL)+1):
                            grid[gx,gy].append(idx)
    grid_x = [key[0] for key in grid]
    grid_y = [key[1] for key in grid]
    grid_bounds = (min(grid_x), max(grid_x), min(grid_y), max(grid_y))

    source = json.loads(FMR.read_text())
    unpaved_path=ROOT/'analysis_output/connectivity-unpaved-road-indicator.json'
    unpaved_rows={str(r.get('id')):r for r in json.loads(unpaved_path.read_text()).get('rows',[])} if unpaved_path.exists() else {}
    # The static counterpart is a manifest plus browser shards. The report
    # builder reads the complete local build source in analysis_output.
    services_path=ROOT/'analysis_output/connectivity-public-services-data.json'
    venues_path=STATIC/'connectivity-venues-data.json'
    services=json.loads(services_path.read_text()).get('rows',[]) if services_path.exists() else []
    venues=json.loads(venues_path.read_text()).get('rows',[]) if venues_path.exists() else []
    service_grid,service_points=place_point_index(services)
    venue_grid,venue_points=place_point_index(venues)
    subdivision_counts=defaultdict(set)
    property_matches_path=ROOT/'analysis_output/connectivity-remote-fmr-properties.json'
    if property_matches_path.exists():
        for match in json.loads(property_matches_path.read_text()).get('rows',[]):
            if match.get('venueType')=='Subdivision / residential village cue':
                subdivision_counts[str(match.get('roadId'))].add(str(match.get('placeId')))
    integrated_path = STATIC / 'integrated-project-data.json'
    integrated = json.loads(integrated_path.read_text())
    import re
    remote_cue = re.compile(r'\b(?:sitio|barangay|brgy\.?|purok|farm.?to.?market|fmr|rural|mountain|upland|interior|access road)\b', re.I)
    explicit_city = re.compile(r'\bcity\b', re.I)
    national_road_cue = re.compile(r'\b(?:national road|national highway|national road network|national route|circumferential(?: road)?|bypass(?: road)?|coastal(?: road)?)\b', re.I)
    boundary_path = ROOT / 'data_sources/arcgis_dpwh/archive/selected/city_municipal_boundaries/layers/City_Municipal_Boundaries_FeatureServer_0-0340fd6a/features.jsonl'
    admin_places = []
    with boundary_path.open() as f:
        for line in f:
            a = (json.loads(line).get('attributes') or {})
            name = str(a.get('MUN_DBM') or a.get('MUNICIPAL') or '').strip()
            center = str(a.get('CENTERS') or '')
            if name and center in {'Municipality', 'City'}:
                admin_places.append((name, center, str(a.get('PROVINCE') or ''), str(a.get('REGION') or '')))
    def norm(s):
        return ' '.join(re.findall(r'[a-z0-9]+', str(s).lower()))
    def classify_place(title):
        title_n = f' {norm(title)} '
        # Require a whole place-name match; ambiguous same-name city/municipality
        # matches remain unresolved rather than being guessed as remote.
        hits = [(name, kind, province, region) for name, kind, province, region in admin_places
                if f' {norm(name)} ' in title_n]
        kinds = {h[1] for h in hits}
        if kinds == {'Municipality'}:
            return 'Municipality named · remote-area proxy', sorted({h[0] for h in hits})
        if 'City' in kinds and 'Municipality' not in kinds:
            return 'City named · exclude from remote screen', sorted({h[0] for h in hits})
        if len(kinds) > 1:
            return 'Ambiguous city/municipality name · review', sorted({h[0] for h in hits})
        return 'No municipality/city match in title · unresolved', []
    road_projects = []
    for row in integrated.get('projects', []):
        year, stage, title = int(row.get('year') or 0), str(row.get('stage') or ''), str(row.get('name') or '')
        if row.get('category') != 'Road' or not (stage == 'GAA' and 2015 <= year <= 2026 or year == 2027 and stage == 'HGAB 3rd'): continue
        if not remote_cue.search(title) and not national_road_cue.search(title): continue
        place_status, place_names = classify_place(title)
        if national_road_cue.search(title):
            place_status = 'National-road indicator · not remote'
        road_projects.append({'year':year,'stage':stage,'title':title,'amountPesos':int(float(row.get('amountPesos') or 0)),
                              'source':str(row.get('source') or ''),'districtId':str(row.get('districtId') or ''),
                              'placeStatus':place_status,'matchedPlaces':place_names})
    road_projects.sort(key=lambda x:(-x['year'],-x['amountPesos'],x['title']))
    gaa_road_rows = [r for r in integrated.get('projects', []) if r.get('category') == 'Road' and r.get('stage') == 'GAA']
    geometry_keys = {'geometry','coordinates','polyline','shape','startlongitude','start_longitude','latitude','longitude','startlatitude','start_latitude'}
    gaa_rows_with_location_fields = [r for r in gaa_road_rows if any(str(k).lower() in geometry_keys for k in r)]
    road_project_path = STATIC / 'connectivity-road-projects.json'
    place_summary = dict(Counter(r['placeStatus'] for r in road_projects))
    road_project_text = json.dumps({'scope':'Road-category projects with rural/remote wording; place status is matched against DPWH City-Municipal Boundaries (as of March 2022). A named municipality is a remote-area proxy only, not a claim that every road outside cities is remote. Projects without an unambiguous municipality match remain unresolved.','boundarySource':'DPWH City-Municipal Boundaries FeatureServer; source metadata cites NAMRIA rectified digitally by DPWH GIS staff (as of March 2022), with OpenStreetMap and PSA references.','placeStatusCounts':place_summary,'rows':road_projects},ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n'
    road_project_path.write_text(road_project_text)
    SOURCE_ROAD_PROJECTS.write_text(road_project_text)
    results = []
    for row in source['projects']:
        coords = row.get('coordinates') or []
        raw_points = [point for part in coords for point in part]
        if not raw_points:
            continue
        start_ll, end_ll = raw_points[0], raw_points[-1]
        gap_m = endpoint_gap_meters(start_ll, end_ll) if len(raw_points) > 1 else None
        if gap_m is not None and gap_m > MAX_ENDPOINT_GAP_M:
            ecological_review=('Baywalk title-screen flag: review the pre-project shoreline baseline, coastal habitats and ecological functions, coastal processes, storm-surge design basis, alternatives, and applicable environmental clearances. This precautionary screen is not a finding of ecological damage, project motive, or protective necessity.' if re.search(r'\bbaywalk\b', str(row.get('title') or ''), re.I) else None)
            results.append({
                'id':row['project_id'],'title':row['title'],'region':row['region'],'amountPesos':int(row['amount_php']),'sourcePage':row['source']['printed_page'],
                'routeParts':[],'startLatitude':float(start_ll[1]),'startLongitude':float(start_ll[0]),'endLatitude':float(end_ll[1]),'endLongitude':float(end_ll[0]),
                'coordinateBasis':'Printed start/end pair','coordinateGapMeters':round(gap_m,1),'coordinateQualityFlag':True,
                'startDistanceMeters':None,'endDistanceMeters':None,'nearestDistanceMeters':None,'endpointNearestDistanceMeters':None,'routeNetworkDistanceMeters':None,
                'routeNetworkExemption':False,'routeNetworkStatus':'Suppressed · endpoint coordinates require review before proximity analysis.',
                'exemptionReasons':[],'exemptionNote':'','unpavedRoadConnection':{'status':'Suppressed · endpoint coordinates require review'},
                'nearbyPublicServices':{},'nearbyPublicServiceEvidence':[],'userMapReviewNotes':[],'ecologicalReview':ecological_review,
                'nearbySubdivisionVillageCount':0,'nearbyVisitorVenueCount':0,'result':'Coordinate review · endpoints >20 km apart',
                'connectivityClass':'Coordinate review · endpoints >20 km apart','flagTags':['Coordinate quality · endpoint gap exceeds 20 km; spatial matches suppressed'],
                'roadName':'Suppressed · coordinate review','roadClass':'','roadSection':''})
            continue
        points = []
        for part in coords:
            for lon, lat in part:
                points.append(utm51(float(lon), float(lat)))
        if not points:
            continue
        ends = [points[0], points[-1]] if len(points) > 1 else [points[0]]
        nearest = []
        for p in ends:
            nearest.append(nearest_road(p, grid, segments, grid_bounds))
        best_idx = min(range(len(nearest)), key=lambda i: nearest[i][0])
        endpoint_distance, endpoint_attrs = nearest[best_idx]
        route_distance, route_attrs = nearest_road_to_route(coords, grid, segments, grid_bounds)
        route_connected = route_distance <= ROUTE_CONNECTION_TOLERANCE_M
        endpoint_only_exempt = endpoint_distance > 1000 and route_connected
        # Keep the original start/end screen unchanged; route-based criteria
        # are shown separately as documented exemptions.
        distance, attrs = endpoint_distance, endpoint_attrs
        service_details=nearby_service_details(coords,service_grid,service_points,500.0)
        service_counts=Counter(x['type'] for x in service_details)
        venue_counts=Counter(x['type'] for x in nearby_service_details(coords,venue_grid,venue_points,100.0))
        subdivision_ids=subdivision_counts.get(str(row['project_id']),set())
        user_map_notes=({'ib:p719:r7':['Aralec Farm · identified by the user in Google Maps; exact map point not independently geolocated.']}.get(str(row['project_id']),[]))
        ecological_review=('Baywalk title-screen flag: review the pre-project shoreline baseline, coastal habitats and ecological functions, coastal processes, storm-surge design basis, alternatives, and applicable environmental clearances. This precautionary screen is not a finding of ecological damage, project motive, or protective necessity.' if re.search(r'\bbaywalk\b', str(row.get('title') or ''), re.I) else None)
        exemption_reasons=[]
        if endpoint_only_exempt:
            exemption_reasons.append('Possible loop/shortcut: source route is within 50 m of a DPWH classified road while both endpoints screen beyond 1 km.')
        for kind,count in sorted(service_counts.items()):
            details=[f"{x['name']} ({int(round(x['distanceMeters']))} m)" for x in service_details if x['type']==kind]
            exemption_reasons.append(f"{kind}: {count} mapped site(s) within 500 m of the source route ({'; '.join(details)}).")
        if len(subdivision_ids)>=2:
            exemption_reasons.append(f'{len(subdivision_ids)} mapped subdivision/village footprints within 100 m of the source route.')
        if sum(venue_counts.values())>2:
            exemption_reasons.append(f'{sum(venue_counts.values())} mapped visitor venues within 100 m of the source route.')
        exemption_note=(f'{len(subdivision_ids)} mapped subdivision/village footprint within 100 m; exemption requires at least two.'
                        if len(subdivision_ids)==1 else '')
        threshold = 'Near road · ≤500 m' if distance <= 500 else 'No nearby DPWH classified road · >500 m'
        results.append({
            'id': row['project_id'], 'title': row['title'], 'region': row['region'],
            'amountPesos': int(row['amount_php']), 'sourcePage': row['source']['printed_page'],
            'routeParts': coords,
            'startDistanceMeters': round(nearest[0][0],1),
            'endDistanceMeters': round(nearest[-1][0],1) if len(nearest)>1 else None,
            'startLatitude': float(coords[0][0][1]), 'startLongitude': float(coords[0][0][0]),
            'endLatitude': float(coords[-1][-1][1]), 'endLongitude': float(coords[-1][-1][0]),
            'coordinateBasis': 'Printed start/end pair' if len(points) > 1 else 'Single coordinate; no route line',
            'coordinateGapMeters': round(gap_m,1) if gap_m is not None else None, 'coordinateQualityFlag': False,
            'closestEnd': 'Start' if best_idx == 0 else 'End', 'nearestDistanceMeters': round(distance,1),
            'endpointNearestDistanceMeters': round(endpoint_distance,1),
            'routeNetworkDistanceMeters': round(route_distance,1) if math.isfinite(route_distance) else None,
            'routeNetworkExemption': endpoint_only_exempt,
            'routeNetworkStatus': ('Endpoint distance exceeds 1 km, but source FMR geometry reaches a DPWH classified road within 50 m; exempt from endpoint-only gap flag.'
                                   if endpoint_only_exempt else 'No loop/shortcut exemption; endpoint and route geometry evidence remain available for review.'),
            'exemptionReasons': exemption_reasons,
            'exemptionNote': exemption_note,
            'unpavedRoadConnection': unpaved_rows.get(str(row['project_id']), {'status':'Not assessed · OSM indicator not built'}),
            'nearbyPublicServices': dict(service_counts),
            'nearbyPublicServiceEvidence': service_details,
            'userMapReviewNotes': user_map_notes,
            'ecologicalReview': ecological_review,
            'nearbySubdivisionVillageCount': len(subdivision_ids),
            'nearbyVisitorVenueCount': sum(venue_counts.values()),
            'result': threshold,
            'flagTags': ['DPWH National Road Network comparison · primary/secondary/tertiary classes included', 'HGAB 3rd-reading · DA FMR coordinate row'] + (['Nearest endpoint >500 m from DPWH classified road network'] if distance > 500 else []) + (['Ecological review · Baywalk title-screen flag'] if ecological_review else []),
            'roadName': (attrs or {}).get('ROAD_NAME') or 'Road name unavailable',
            'roadClass': (attrs or {}).get('ROAD_SEC_CLASS') or 'Class unavailable',
            'roadSection': (attrs or {}).get('SECTION_ID') or '',
        })
    results.sort(key=lambda x:(x['nearestDistanceMeters'] if x['nearestDistanceMeters'] is not None else float('inf'), x['region'], x['title']))
    from audit_connectivity_farm_data import audit_farm_data
    audit_farm_data()
    for result in results:
        result.update(farmDistanceMeters=None, farmAssessment='unavailable')
    summary = Counter(r['result'] for r in results)
    coordinate_rows_with_route_pair = sum(
        sum(len(part) for part in (row.get('coordinates') or [])) >= 2
        for row in source['projects'])
    payload = {
        'scope': 'FY2027 House HGAB 3rd-reading DA FMR projects tested against DPWH National Road Network polylines, including the published primary, secondary and tertiary functional classes.',
        'method': 'The main FMR screen uses separate cutoffs: the nearer printed endpoint is within 500 m of a DPWH national-road centerline and within 50 m of mapped cropland for Baseline; only one threshold met is Flag; both thresholds exceeded is Double Flag. The 500 m road tolerance allows for endpoint and centerline positional uncertainty; it is not a road-boundary match or proof of access. Exact distances remain available. Separate exemptions do not alter these classes: source route within 50 m of a classified road while both endpoints are over 1 km away is a possible loop/shortcut; public-service sites within 500 m, at least two subdivision/village footprints within 100 m, or more than two visitor venues within 100 m are recorded separately. A single subdivision/village cue does not qualify. Source-route geometry is a local proxy, not a Google driving route; proximity does not prove access or project service. The classified network contains primary, secondary and tertiary functional classes. The separate FY2024/FY2025 DA FMR ArcGIS layers are used in the venue-link review.',
        'coordinateAudit': {'hgabFmrProjectRows': len(source['projects']), 'rowsWithRouteCoordinatePairs': coordinate_rows_with_route_pair, 'singleCoordinateRows': len(source['projects']) - coordinate_rows_with_route_pair, 'separateDaFmrArcgisLayers': {'fy2024Features': 1062, 'fy2025Features': 474}},
        'farmCoverage': {'available': False, 'audit': 'connectivity-farm-status.json'},
        'roadClasses': dict(road_classes),
        'gaaRoadAlignmentAudit': {'integratedGaaRoadRows': len(gaa_road_rows), 'rowsWithUsableGeometryOrCoordinateFields': len(gaa_rows_with_location_fields), 'note': 'This audit covers the integrated budget line-item table only. Coordinate-bearing FY2027 HGAB DA FMR project records and FY2024/FY2025 DA FMR ArcGIS records are separate datasets.'},
        'limits': ['This layer is the DPWH national-road network; its primary/secondary/tertiary labels are functional classes within that network, not a separate local-road inventory.', 'It does not cover every local, barangay, farm, or private road.', 'Coordinates are printed FMR endpoints and may be approximate; straight-line endpoint proximity does not prove an access connection.', 'Bridge analysis is deferred.', 'For question 2, DPWH National Road Network matches and routes explicitly named as national, circumferential, bypass or coastal are not treated as remote. A municipality match is a provisional remote-area proxy; routes with a city or unresolved endpoint stay out of the confirmed remote subset.', 'The visitor-venue join uses a 100 m buffer around straight-line segments reconstructed from available start/end coordinates. Route alignment, operating status, property ownership, and actual access remain unverified.'],
        'roadFeatures': roads, 'roadSegments': len(segments), 'roadProjectCandidates': len(road_projects), 'roadProjectPlaceStatusCounts': place_summary, 'summary': dict(summary), 'projects': results,
        'placeInventories': {'visitorVenues': 'connectivity-venues-data.json', 'privatePropertyIndicators': 'connectivity-property-indicators-data.json', 'publicServices': 'connectivity-public-services-data.json', 'unverifiedVenueNameCues': 'connectivity-venue-review-data.json', 'officialTourismDirectory': 'connectivity-official-venues-data.json', 'propertyRouteMatches': 'connectivity-remote-fmr-properties.json'},
    }
    from connectivity_farm_enrichment import load_measurements, apply_measurement
    farm_cache = load_measurements()
    if farm_cache:
        farm_cache['source']['limits'] = 'Class 40 describes annual herbaceous cropland; woody perennial crops may be tree/shrub cover. This dated satellite classification does not establish present farms, property boundaries, ownership, access or wrongdoing. Section 1 uses a 500 m DPWH-centerline cutoff and a 50 m mapped-cropland cutoff; exact values remain available, while incomplete raster coverage remains unresolved.'
        for row in payload['projects']:
            apply_measurement(row, farm_cache)
        payload['farmCoverage'] = farm_cache['source']
        payload['limits'] = [text for text in payload.get('limits', []) if 'no farm-boundary layer' not in text]
        payload['limits'].append(farm_cache['source']['limits'])
        payload['connectivitySummary'] = dict(Counter(row.get('connectivityClass', 'Unresolved · incomplete cropland coverage') for row in payload['projects']))
    manual_file = ROOT / 'analysis_output/connectivity-manual-greens.json'
    if manual_file.exists():
        saved = json.loads(manual_file.read_text())
        manual_projects = saved.get('projects', {})
        allowed_reasons = {'near-produce','closes-loop','extends-road','road-segment','connects-road-segments','near-school','near-health-center','near-hospital'}
        allowed_red_reasons = {'section2-visitor-venue','section2-subdivision-village','section2-large-residential-property','section2-restricted-access-property','section2-private-property-cue','section2-coordinate-quality','baywalk-shoreline-review'}
        for row in payload['projects']:
            record = manual_projects.get(row['id'], {})
            row['manualGreenReasons'] = [reason for reason in record.get('greenReasons', record.get('reasons', [])) if reason in allowed_reasons]
            row['manualGreenNote'] = str(record.get('greenNote') or '')[:2000]
            row['manualRedReasons'] = [reason for reason in record.get('redReasons', []) if reason in allowed_red_reasons]
            row['manualRedReason'] = str(record.get('redReason') or '')[:2000]
    text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    OUT.write_text(text)
    SOURCE_DATA.write_text(text)
    DATA.write_text(text)
    (STATIC / 'connectivity-fmr-road.json').write_text(text)
    SCRIPT.write_text(JS)
    (ROOT / 'analysis_output/connectivity.js').write_text(JS)
    make_page(payload)
    print(json.dumps({'projects':len(results),'roadFeatures':roads,'roadSegments':len(segments),'summary':dict(summary)}))


def make_page(d):
    """Render connectivity from the checked-in page template, never prior output."""
    template = ROOT / 'report_assets/connectivity-page-template.html'
    if not template.is_file():
        raise FileNotFoundError(f'Connectivity source template is missing: {template}')
    html = template.read_text()
    script_version = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()[:12]
    html = re.sub(r'<script src="connectivity\.js(?:\?v=[^"]*)?"></script>',
                  f'<script src="connectivity.js?v={script_version}"></script>', html)
    import importlib
    import uniform_report_menu, connectivity_places_page
    uniform_report_menu = importlib.reload(uniform_report_menu)
    connectivity_places_page = importlib.reload(connectivity_places_page)
    html = uniform_report_menu.apply_page(html, PAGE.name)
    rendered = connectivity_places_page.apply_page(html)
    rendered = uniform_report_menu.apply_research_status(rendered)
    from report_table_presentation import apply_page_table_module
    rendered,_=apply_page_table_module(PAGE.name,rendered)
    from report_json_shards import attach_loader
    rendered=attach_loader(rendered, PAGE.name)
    rendered = re.sub(r'(<details\b[^>]*\bid="connectivity-places-inventory"[^>]*)\s+open(?=[\s>])', r'\1', rendered)

    required_ids = ('exclude-green-exemptions', 'connectivity-project-pagination', 'connectivity-places-inventory',
                    'connectivity-coordinate-note', 'unpaved-road-indicator-note',
                    'connectivity-exemption-note', 'connectivity-json-export',
                    'fmr-venue-json-export', 'fmr-property-json-export',
                    'connectivity-source-name-notice')
    for identifier in required_ids:
        count = len(re.findall(r'\bid="' + re.escape(identifier) + r'"', rendered))
        if count != 1:
            raise ValueError(f'Connectivity template must contain one {identifier}; found {count}')
    if 'connectivity-filtered-fmr-projects.json' not in JS or 'currentItems.map(x=>exportProject' not in JS:
        raise ValueError('Connectivity Section 1 filtered JSON export is missing from the builder script')
    if "!excludeGreen?.checked||!x.exemptionReasons?.length&&!manualReasons(x).length&&!manualGreenNote(x)" not in JS:
        raise ValueError('Connectivity Section 1 green-exemption filter is missing from the builder script')
    if len(re.findall(r'<nav\b[^>]*class="report-nav"', rendered)) != 1:
        raise ValueError('Connectivity template must render exactly one report navigation')
    if len(re.findall(r'<aside\b[^>]*class="[^"]*\bresearch-status\b', rendered)) != 1:
        raise ValueError('Connectivity template must render exactly one research-status notice')
    if 'services1.arcgis.com' in rendered or 'services.arcgis.com' in rendered:
        raise ValueError('Connectivity output contains a restricted ArcGIS service URL')

    PAGE.write_text(rendered)
    (ROOT / 'analysis_output/connectivity.html').write_text(rendered)


if __name__ == '__main__':
    build()
