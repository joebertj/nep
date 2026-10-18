/* Generated static PH location DB labels. No database or network lookup at runtime. */
(()=>{'use strict';
const D=__PH_LOCATION_PAYLOAD__,NativeBlob=window.Blob,key=v=>String(v??'').normalize('NFC').toLowerCase().replace(/\s+/g,' ').trim();
const index=new Map();for(const title of Object.keys(D.projects)){const first=title.split(' ')[0];if(!index.has(first))index.set(first,[]);index.get(first).push(title)}for(const list of index.values())list.sort((a,b)=>b.length-a.length);
const repHeader=v=>/representative|congressman|congressmen|congressional_representatives/i.test(v);
const geoHeader=v=>/project|facility|school|province|district|office|keyword|example|legislative|nep.*line|hgab.*line|line.*item|prior.*line|candidate|term/i.test(v);
function resolve(cells,headers){
  const clean=cells.map(v=>String(v??''));
  const provinceAggregate=!headers.some(h=>/office$|^deo$|project.*(?:name|title|line)|^project$|facility|school|^name$|^title$|line.*item|nep.*line|hgab.*line/i.test(h));
  for(let i=0;i<clean.length;i++){
    if(repHeader(headers[i]||''))continue;
    const text=key(clean[i]);
    if(provinceAggregate&&/^province$/i.test(String(headers[i]||'').trim()))return D.provinces[text]||[];
    if(D.districts[text])return D.districts[text];
    if(!/project|facility|school|name|title|example|line|record/i.test(headers[i]||''))continue;
    const candidates=index.get(text.split(' ')[0])||[];
    for(const title of candidates)if(text===title||text.startsWith(title+' '))return D.projects[title];
  }
  // Multiple explicitly labelled legislative districts are valid geographic
  // coverage; a DEO name or ordinal is never converted into such a label.
  const names=new Set();for(let i=0;i<clean.length;i++){
    if(repHeader(headers[i]||''))continue;
    for(const line of clean[i].split(/\n/)){const text=key(line);for(const [district,people] of Object.entries(D.districts))if(text===district||text.startsWith(district+' · ')||text.startsWith(district+' '))for(const name of people)names.add(name)}
  }
  return [...names].sort();
}
function parseCsv(text){const rows=[];let row=[],cell='',quoted=false;for(let i=0;i<text.length;i++){const c=text[i];if(quoted){if(c==='"'&&text[i+1]==='"'){cell+='"';i++}else if(c==='"')quoted=false;else cell+=c}else if(c==='"')quoted=true;else if(c===','){row.push(cell);cell=''}else if(c==='\n'||c==='\r'){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);rows.push(row);row=[];cell=''}else cell+=c}if(cell||row.length){row.push(cell);rows.push(row)}return rows}
function enrichCsv(text){const bom=text.startsWith('\ufeff');const rows=parseCsv(bom?text.slice(1):text);if(rows.length<2)return text;const headers=rows[0],rep=headers.findIndex(repHeader);if(headers.some(h=>/^(organization|filteredRank|committeeStatus|additionalVerifiedRoles)$/i.test(h.trim())))return text;if(!headers.some(geoHeader))return text;const col=rep<0?headers.length:rep;for(const row of rows.slice(1)){const names=resolve(row,headers);row[col]=names.join('; ')}if(rep<0)headers.push('congressional_representatives');return(bom?'\ufeff':'')+rows.map(row=>row.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n')}
window.PHLocation={createBlob(parts,options){if(/csv/i.test(options?.type||'')&&parts.every(p=>typeof p==='string'))return new NativeBlob([inventoryCsv(enrichCsv(parts.join('')))],options);return new NativeBlob(parts,options)},resolve};
const inventoryKey=v=>key(v).normalize('NFD').replace(/[\u0300-\u036f]/g,''),inventoryIndex=new Map();
for(const [title,id] of Object.entries(D.inventoryIds||{})){const first=title.split(' ')[0];if(!inventoryIndex.has(first))inventoryIndex.set(first,[]);inventoryIndex.get(first).push([title,id]);}
for(const entries of inventoryIndex.values())entries.sort((a,b)=>b[0].length-a[0].length);
const inventoryHeader=v=>/matched[\s_]*inventory[\s_]*ids?/i.test(v);
function inventoryValue(cells,headers){
 const matches=[];
 for(let i=0;i<cells.length;i++){
  if(inventoryHeader(headers[i]||'')||!/(?:project|title|^name$|nep.*line|hgab.*line|prior.*line)/i.test(headers[i]||''))continue;
  const text=inventoryKey(cells[i]),entries=inventoryIndex.get(text.split(' ')[0])||[];
  for(const [title,id] of entries){const suffix=text.slice(title.length);if(text===title||(text.startsWith(title)&&/^\s*·\s*(?:p\.?\s*\d|nep\b|hgab\b|hb\d|gaa\b|\d\s*-\s*hb\b)/i.test(suffix))){matches.push([headers[i],id]);break;}}
 }
 const ids=[...new Set(matches.map(r=>r[1]))];
 return ids.length<2?(ids[0]||''):matches.map(([label,id])=>label+': '+id).join(' | ');
}
function inventoryCsv(text){
 const bom=text.startsWith('\ufeff'),rows=parseCsv(bom?text.slice(1):text);if(rows.length<2)return text;
 const values=rows.slice(1).map(row=>inventoryValue(row,rows[0]));if(!values.some(Boolean))return text;
 const existing=rows[0].findIndex(inventoryHeader);
 if(existing>=0){rows.slice(1).forEach((row,i)=>{if(!row[existing]||row[existing]==='—')row[existing]=values[i];});}
 else{rows[0].push('matched_inventory_ids');rows.slice(1).forEach((row,i)=>row.push(values[i]));}
 return(bom?'\ufeff':'')+rows.map(row=>row.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');
}
function inventoryColumn(table,head){
 let headers=[...head.cells].map(c=>c.textContent.trim()),column=headers.findIndex(inventoryHeader);
 const native=column>=0&&!head.cells[column].dataset.phInventoryColumn;
 const rows=[...table.tBodies].flatMap(body=>[...body.rows]).filter(row=>!(row.cells.length===1&&row.cells[0].colSpan>1));
 const values=rows.map(row=>inventoryValue([...row.cells].map(c=>c.innerText||c.textContent),headers));
 if(column<0){if(!values.some(Boolean))return;column=head.cells.length;const th=document.createElement('th');th.textContent='Matched inventory ID(s)';th.dataset.phInventoryColumn='true';head.append(th);}
 rows.forEach((row,i)=>{while(row.cells.length<=column)row.insertCell();const cell=row.cells[column],value=values[i]||'—';if(native&&cell.textContent.trim()&&cell.textContent.trim()!=='—')return;if(cell.textContent!==value)cell.textContent=value;cell.title='Supported inventory road section or bridge identifier; not proof of funded scope or district attribution';});
}
let pending=false;
function refresh(){pending=false;for(const table of document.querySelectorAll('table')){
  if(table.dataset.phLocationIdentitySource==='roster'){table.dataset.phLocationReview='sourced-identity-preserved';continue}
  const head=table.tHead?.rows[table.tHead.rows.length-1];if(!head)continue;
  inventoryColumn(table,head);
  const headers=[...head.cells].map(c=>c.textContent.trim());let rep=headers.findIndex(repHeader);
  if(!headers.some(geoHeader)){table.dataset.phLocationReview='not-applicable';continue}
  if(rep<0){rep=head.cells.length;const th=document.createElement('th');th.textContent='Representative(s) for listed locations';th.dataset.phLocationColumn='true';head.append(th);headers.push(th.textContent)}
  for(const body of table.tBodies)for(const row of body.rows){if(row.cells.length===1&&row.cells[0].colSpan>1){row.cells[0].colSpan=head.cells.length;continue}
    const values=[...row.cells].map(c=>c.innerText||c.textContent),names=resolve(values,headers);let cell=row.cells[rep];if(!cell){cell=row.insertCell();cell.dataset.phLocationColumn='true'}const value=names.join('; ')||'—';if(cell.textContent!==value)cell.textContent=value;cell.title=names.length?'PH location DB · current 20th Congress geographic coverage; not sponsorship':'Unresolved geographic coverage; no representative inferred';
  }
  table.dataset.phLocationReview='reviewed';
}
if(!document.getElementById('ph-location-roster-note')){const main=document.querySelector('main');if(main){const note=document.createElement('p');note.id='ph-location-roster-note';note.className='note';note.textContent=D.policy+' A dash means unresolved coverage. Province summaries list province-wide members; featured-project names describe only that project. Historic rows show current roster context, not the member in office in that budget year.';main.append(note)}}
}
function schedule(){if(!pending){pending=true;requestAnimationFrame(refresh)}}
function start(){const observer=new MutationObserver(schedule);observer.observe(document.body,{childList:true,subtree:true});schedule()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
