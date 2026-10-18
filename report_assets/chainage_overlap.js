/* Shared chainage viewer. Full printed ranges only; no uncertain lengths filled. */
(()=>{
  'use strict';
  if(window.chainageOverlapViewer)return;
  window.chainageOverlapViewer=true;
  const records=__CHAINAGE_RECORDS__;
  const normalized=s=>String(s||'').replace(/\s+/g,' ').trim().toLocaleLowerCase();
  const prepared=records.map(r=>({...r,leftKey:normalized(r.left),rightKey:normalized(r.right)}));
  const number=v=>Number(v).toLocaleString('en-PH',{maximumFractionDigits:6});
  const station=v=>{const km=Math.floor(v/1000),parts=String(Number((v-km*1000).toFixed(6))).split('.');return km+'+'+parts[0].padStart(3,'0')+(parts[1]?'.'+parts[1]:'')};
  const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const style=document.createElement('style');
  style.textContent=`
    .chainage-overlap-link{display:inline!important;border:0!important;padding:0!important;background:none!important;color:#006a70!important;text-decoration:underline!important;text-decoration-style:dotted!important;text-underline-offset:3px;font:inherit!important;font-weight:700!important;cursor:pointer}
    .chainage-overlap-link:focus-visible{outline:3px solid #d77824;outline-offset:3px}
    #chainage-overlap-dialog{width:min(1100px,95vw);max-width:95vw;max-height:90vh;padding:24px;border:1px solid #bed0d0;border-radius:16px;background:white;color:#18303b;overflow:auto;box-sizing:border-box}
    #chainage-overlap-dialog::backdrop{background:#102f3ec0}
    #chainage-overlap-dialog .overlap-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}
    #chainage-overlap-dialog h2{margin:0;font-size:24px}
    #chainage-overlap-dialog button,#chainage-overlap-dialog select{font:inherit;padding:8px 12px;border:1px solid #aabfbe;border-radius:8px}
    #chainage-overlap-dialog .overlap-source{font-size:13px;color:#48626e;overflow-wrap:anywhere}
    #chainage-overlap-dialog .overlap-project{padding:10px 12px;border-left:5px solid #087e78;background:#f1f7f6;overflow-wrap:anywhere}
    #chainage-overlap-dialog .overlap-project.second{border-color:#d07a22}
    #chainage-overlap-dialog .overlap-chart{display:block;width:100%;height:auto!important;max-height:none!important;aspect-ratio:1100/350}
    #chainage-overlap-dialog .overlap-note{font-size:14px;line-height:1.5}
    #chainage-overlap-dialog .overlap-picker{display:block;width:100%;margin:12px 0}
    @media(max-width:600px){#chainage-overlap-dialog{padding:14px}#chainage-overlap-dialog h2{font-size:20px}#chainage-overlap-dialog .overlap-chart text{font-size:24px}}
  `;
  document.head.append(style);
  const dialog=document.createElement('dialog');
  dialog.id='chainage-overlap-dialog';
  dialog.setAttribute('aria-labelledby','chainage-overlap-title');
  dialog.innerHTML='<div class="overlap-heading"><h2 id="chainage-overlap-title">Stated chainage overlap</h2><button type="button" class="overlap-close" aria-label="Close overlap diagram">Close</button></div><select class="overlap-picker" aria-label="Choose the source comparison"></select><div class="overlap-content"></div>';
  document.body.append(dialog);
  let opener=null;
  dialog.querySelector('.overlap-close').onclick=()=>dialog.close();
  dialog.addEventListener('click',event=>{
    if(event.target!==dialog)return;
    const box=dialog.getBoundingClientRect();
    if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.close();
  });
  dialog.addEventListener('close',()=>opener?.focus());
  function draw(r){
    const all=r.leftRanges.concat(r.rightRanges);
    const minimum=Math.min(...all.map(a=>a[0])),maximum=Math.max(...all.map(a=>a[1]));
    const x=v=>150+880*(v-minimum)/(maximum-minimum);
    let svg='<svg class="overlap-chart" viewBox="0 0 1100 350" role="img" aria-label="Two horizontal chainage bars on a shared scale; purple marks the overlapping segment"><defs><pattern id="chainage-overlap-hatch" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#704a9b"/><path d="M-2 2L2 -2M0 8L8 0M6 10L10 6" stroke="white" stroke-width="1.5"/></pattern></defs>';
    for(const [a,b] of r.overlapRanges)svg+='<rect x="'+x(a)+'" y="35" width="'+(x(b)-x(a))+'" height="210" fill="#704a9b" opacity=".09"/>';
    for(const [ranges,y,color,label] of [[r.leftRanges,65,'#087e78','Item 1'],[r.rightRanges,175,'#d07a22','Item 2']]){
      svg+='<text x="12" y="'+(y+28)+'" font-size="18">'+label+'</text>';
      for(const [a,b] of ranges){
        svg+='<rect x="'+x(a)+'" y="'+y+'" width="'+(x(b)-x(a))+'" height="42" rx="3" fill="'+color+'"><title>'+escape(label+': '+station(a)+' to '+station(b))+'</title></rect>';
        svg+='<text x="'+x(a)+'" y="'+(y-10)+'" text-anchor="start" font-size="15">'+escape(station(a))+'</text><text x="'+x(b)+'" y="'+(y+64)+'" text-anchor="end" font-size="15">'+escape(station(b))+'</text>';
        for(const [u,v] of r.overlapRanges){const start=Math.max(a,u),end=Math.min(b,v);if(end>start)svg+='<rect x="'+x(start)+'" y="'+y+'" width="'+(x(end)-x(start))+'" height="42" fill="url(#chainage-overlap-hatch)"/>';}
      }
    }
    svg+='<path d="M150 270H1030" stroke="#7b9199"/>';
    for(let i=0;i<=4;i++){const v=minimum+(maximum-minimum)*i/4,position=x(v);svg+='<path d="M'+position+' 270v7" stroke="#7b9199"/><text x="'+position+'" y="302" font-size="14" text-anchor="'+(i===0?'start':i===4?'end':'middle')+'">'+escape(number(v))+' m</text>';}
    svg+='<text x="150" y="337" font-size="15">Shared chainage scale · purple hatching = positive overlap</text></svg>';
    const intervals=[];
    for(const [a,b] of r.overlapRanges){const previous=intervals.at(-1);if(previous&&a<=previous[1])previous[1]=Math.max(previous[1],b);else intervals.push([a,b]);}
    const meters=intervals.reduce((sum,[a,b])=>sum+b-a,0);
    dialog.querySelector('.overlap-content').innerHTML='<p class="overlap-project"><strong>Item 1 · '+escape(r.leftLabel)+'</strong><br>'+escape(r.left)+'<br><span class="overlap-source">'+escape(r.leftSource)+'</span></p><p class="overlap-project second"><strong>Item 2 · '+escape(r.rightLabel)+'</strong><br>'+escape(r.right)+'<br><span class="overlap-source">'+escape(r.rightSource)+'</span></p>'+svg+'<p><strong>'+escape(number(meters))+' meters of stated chainage overlap</strong> · '+intervals.map(([a,b])=>escape(station(a)+'–'+station(b))).join('; ')+'</p><p class="overlap-note">Both bars use the same scale and their actual chainage positions. This shows numerical overlap in printed ranges, not duplicate contracts or payments. Different work components or station references can share chainage; verify engineering scope. Incomplete endpoints are not filled.</p>';
  }
  function matches(row){
    if(row.dataset.chainagePair)return prepared.filter(r=>r.rowKey===row.dataset.chainagePair);
    const text=normalized(row.textContent);
    return prepared.filter(r=>text.includes(r.leftKey)&&text.includes(r.rightKey)&&r.requiredIds.every(id=>text.includes(normalized(id)))&&(!r.year||text.includes(String(r.year)))&&(!r.rejectHouseIds||! /\bhb\d+-[23]-/.test(text)));
  }
  function open(button,items){
    opener=button;
    const picker=dialog.querySelector('.overlap-picker');
    picker.replaceChildren(...items.map((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=r.leftLabel+' ↔ '+r.rightLabel+' · '+r.rightSource;return o}));
    picker.hidden=items.length===1;
    picker.onchange=()=>draw(items[Number(picker.value)]);
    draw(items[0]);dialog.showModal();
  }
  // The historical table creates its own evidence button on every redraw.
  // Use its attached source ranges directly, without title/key discovery.
  document.addEventListener('click',event=>{
    const button=event.target.closest('button[data-chainage-diagram]');
    if(!button)return;
    const record=JSON.parse(button.dataset.chainageDiagram);
    if(record.leftRanges?.length&&record.rightRanges?.length&&record.overlapRanges?.length)open(button,[record]);
  });
  let scheduled=false;
  function decorate(){
    scheduled=false;
    for(const row of document.querySelectorAll('table tr')){
      const table=row.closest('table'),header=table.querySelector('thead tr')||table.querySelector('tr');
      const column=Array.from(header?.cells||[]).findIndex(cell=>['chainage / tranche check','stated segment evidence'].includes(normalized(cell.textContent)));
      const evidenceCell=row.querySelector('td[data-chainage-evidence]')||(column>=0?row.cells[column]:null);
      for(const button of row.querySelectorAll('.chainage-overlap-link')){
        if(button.closest('td')!==evidenceCell)button.replaceWith(document.createTextNode(button.textContent));
      }
      if(!/\boverlap\b/i.test(row.textContent))continue;
      if(!evidenceCell||evidenceCell.tagName!=='TD')continue;
      if(evidenceCell.querySelector('button[data-chainage-diagram]'))continue;
      const items=matches(row);if(!items.length)continue;
      for(const cell of [evidenceCell]){
        const walker=document.createTreeWalker(cell,NodeFilter.SHOW_TEXT,{acceptNode:node=>node.parentElement.closest('button,a,script,style')?NodeFilter.FILTER_REJECT:/\boverlap\b/i.test(node.textContent)?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT});
        const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
        for(const node of nodes){
          const fragment=document.createDocumentFragment();let last=0;
          for(const m of node.textContent.matchAll(/\boverlap\b/gi)){
            fragment.append(document.createTextNode(node.textContent.slice(last,m.index)));
            const button=document.createElement('button');button.type='button';button.className='chainage-overlap-link';button.textContent=m[0];button.setAttribute('aria-label','Show chainage overlap diagram');button.onclick=()=>open(button,items);fragment.append(button);last=m.index+m[0].length;
          }
          fragment.append(document.createTextNode(node.textContent.slice(last)));node.replaceWith(fragment);
        }
      }
    }
  }
  const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(decorate)}});
  observer.observe(document.querySelector('main')||document.body,{childList:true,subtree:true});
  decorate();
})();
