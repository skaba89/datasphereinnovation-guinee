// Kanban view of the CRM pipeline. Reuses crm.js globals (api, token, statuses) and the
// existing PATCH endpoint (full record + version); the server keeps every business rule.
(()=>{
 const FIELDS=['company','contact','email','title','mode','skills','consultant_id','next_action','followup','notes','status'];
 const MODES={REGIE:'Régie',FORFAIT:'Forfait',CONSEIL:'Conseil'};
 const LIMIT=50;
 const pipeline=document.getElementById('pipeline'),counts=document.getElementById('counts');
 if(!pipeline||!counts)return;
 const section=document.createElement('section'),head=document.createElement('div'),title=document.createElement('h2'),hint=document.createElement('p'),status=document.createElement('p'),board=document.createElement('div');
 section.id='kanban';section.className='workflow-section';head.className='toolbar';title.textContent='Pipeline visuel';
 hint.className='muted';hint.textContent='Glissez une carte vers une autre colonne, ou utilisez « Déplacer vers » au clavier. Chaque déplacement est contrôlé par le serveur et historisé.';
 status.id='kanban-notice';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 board.className='kanban';board.setAttribute('aria-label','Pipeline commercial par étape');
 head.append(title);section.append(head,hint,status,board);pipeline.after(section);
 let epoch=0,timer=0,dragged=null;
 const today=()=>new Date().toISOString().slice(0,10);
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};

 async function move(item,target){
  if(item.status===target)return;
  if(target==='PERDU'&&!confirm('Classer « '+item.title+' » en Perdu ?'))return;
  const body={version:item.version};for(const k of FIELDS)body[k]=item[k]??'';body.status=target;
  status.textContent='Déplacement en cours…';
  try{await api('crm/'+encodeURIComponent(item.id),{method:'PATCH',body:JSON.stringify(body)});status.textContent='« '+item.title+' » déplacé vers '+statuses[target]+'.';}
  catch(e){status.textContent=e.message;}
  // Refresh both views: crm.js re-renders counts, which triggers the board refresh.
  if(typeof load==='function'){try{await load()}catch{refresh()}}else refresh();
 }

 function card(item){
  const c=el('article','kanban-card');c.draggable=true;c.dataset.id=item.id;
  c.append(el('strong','',item.company),el('span','kanban-title',item.title));
  const meta=el('p','kanban-meta');meta.append(el('span','kanban-tag',MODES[item.mode]||item.mode));
  if(item.followup){const late=item.followup<today()&&!['GAGNE','EN_MISSION','TERMINE','PERDU'].includes(item.status);const d=el('span','kanban-date'+(late?' late':''),(late?'En retard · ':'Relance ')+item.followup);meta.append(d)}
  if(item.qualification){const score=Object.entries(item.qualification).filter(([k,v])=>!k.startsWith('demo')&&v==='YES').length;meta.append(el('span','kanban-tag','Qualif. '+score+'/4'))}
  c.append(meta);
  const label=el('label','kanban-move'),select=el('select');label.append(el('span','','Déplacer vers'),select);
  select.setAttribute('aria-label','Déplacer '+item.title+' vers une autre étape');
  for(const [v,t] of Object.entries(statuses)){const o=el('option','',t);o.value=v;o.selected=v===item.status;select.append(o)}
  select.onchange=()=>move(item,select.value);
  c.append(label);
  c.ondragstart=e=>{dragged=item;c.classList.add('dragging');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',item.id)};
  c.ondragend=()=>{dragged=null;c.classList.remove('dragging')};
  return c;
 }

 function column(value,label,data){
  const col=el('section','kanban-col'),h=el('h3','',label),n=el('span','kanban-count',String(data.total));
  col.dataset.status=value;h.append(n);col.append(h);
  const list=el('div','kanban-list');
  for(const item of data.items)list.append(card(item));
  if(!data.items.length)list.append(el('p','kanban-empty','Aucune opportunité'));
  if(data.total>data.items.length)list.append(el('p','kanban-empty','+ '+(data.total-data.items.length)+' autre(s) dans le registre'));
  col.append(list);
  col.ondragover=e=>{if(dragged){e.preventDefault();col.classList.add('over')}};
  col.ondragleave=()=>col.classList.remove('over');
  col.ondrop=e=>{e.preventDefault();col.classList.remove('over');if(dragged)move(dragged,value)};
  return col;
 }

 async function refresh(){
  const current=++epoch,session=token;
  if(!session){board.replaceChildren();return}
  try{
   const results=await Promise.all(Object.keys(statuses).map(s=>api('crm?'+new URLSearchParams({status:s,page:1,page_size:LIMIT}))));
   if(current!==epoch||token!==session)return;
   board.replaceChildren(...Object.entries(statuses).map(([v,l],i)=>column(v,l,results[i])));
  }catch(e){if(current===epoch)status.textContent=e.message}
 }
 // crm.js re-renders #counts after every load (login, save, filter): follow it.
 new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(refresh,50)}).observe(counts,{childList:true});
})();
