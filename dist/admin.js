const $=id=>document.getElementById(id), states={NOUVELLE:'Nouvelle',QUALIFIEE:'Qualifiée',EN_COURS:'En cours',GAGNEE:'Gagnée',PERDUE:'Perdue'};
let token='',page=1,total=0,epoch=0;
function option(value,label){const o=document.createElement('option');o.value=value;o.textContent=label;return o}
for(const [v,l] of Object.entries(states))$('status').append(option(v,l));
function notice(text){$('notice').textContent=text}
async function api(path,options={}){const r=await fetch(path,{...options,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'}});const d=await r.json();if(!r.ok)throw Error(d.error||'Erreur');return d}
const mailStates={PENDING:'En attente / relance automatique',FAILED:'Échec de la file',ACCEPTED:'Accepté par le fournisseur'};
const deliveryStates={unverified:'Livraison non vérifiée',sent:'Envoyé',delivered:'Livré',delivery_delayed:'Livraison retardée',bounced:'Rebond',complained:'Plainte',failed:'Échec de livraison',suppressed:'Bloqué par le fournisseur'};
function mailLabel(kind){if(kind==='internal')return 'Notification interne';if(kind==='ack')return 'Accusé de réception';return 'État : '+(states[kind.split('-').pop()]||'Notification');}
function communicationCell(row,items){const td=cell(row,'');if(!items.length){td.textContent='Aucun historique';return}const list=document.createElement('ul');for(const item of items){const li=document.createElement('li');li.textContent=mailLabel(item.kind)+' — '+(mailStates[item.queue_state]||item.queue_state)+(item.queue_state==='ACCEPTED'?' · '+(deliveryStates[item.delivery]||item.delivery):'');list.append(li)}td.append(list)}
function conversionEditor(container,item){
 if(!item.workflow)return;
 if(item.conversion){const p=document.createElement('p');const a=document.createElement('a');a.href='crm.html';a.textContent='Opportunité CRM : '+item.conversion.title;p.append(a,document.createTextNode(' · '+item.conversion.status+' · '+item.conversion.quotes+' devis · '+item.conversion.missions+' mission(s)'));container.append(p);return}
 const lead=item.lead;
 if(lead){const p=document.createElement('p'),a=document.createElement('a');a.href='crm.html#kanban';a.textContent=(lead.outcome==='CREATED'?'Prospect CRM automatique : ':'Prospect CRM existant (même e-mail) : ')+lead.title;p.append(a,document.createTextNode(' · '+lead.status));container.append(p)}
 if(item.status!=='QUALIFIEE'||item.besoin==='Candidature spontanée')return;
 const promote=lead&&lead.outcome==='CREATED'&&lead.status==='PROSPECT';
 const button=document.createElement('button');button.type='button';button.textContent=promote?'Qualifier le prospect CRM':'Créer une opportunité CRM';button.onclick=async()=>{button.disabled=true;try{await api('/api/admin/requests/'+encodeURIComponent(item.id)+'/convert',{method:'POST'});await load();notice('Opportunité CRM liée.')}catch(e){notice(e.message);button.disabled=false}};container.append(button);
}
function workflowEditor(container,item,owners){
 const w=item.workflow;if(!w)return;
 const panel=document.createElement('details'),summary=document.createElement('summary');
 summary.textContent='Suivi : '+(w.owner||'Non affectée')+' · '+w.priority+(w.due_date?' · '+w.due_date:'');panel.append(summary);
 const form=document.createElement('form');const owner=document.createElement('select'),priority=document.createElement('select'),due=document.createElement('input'),note=document.createElement('textarea');
 owner.append(option('','Non affectée'));for(const a of owners)owner.append(option(a.id,a.username));
 if(w.owner_id&&!owners.some(a=>a.id===w.owner_id))owner.append(option(w.owner_id,(w.owner||'Compte')+' (indisponible)'));
 owner.value=w.owner_id;for(const p of ['NORMALE','HAUTE','URGENTE'])priority.append(option(p,p));priority.value=w.priority;due.type='date';due.value=w.due_date;note.required=true;note.maxLength=1000;
 for(const [label,input] of [['Commercial',owner],['Priorité',priority],['Échéance',due],['Action / note interne',note]]){const l=document.createElement('label');l.textContent=label;l.append(input);form.append(l)}
 const save=document.createElement('button');save.textContent='Enregistrer le suivi';form.append(save);
 form.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{await api('/api/admin/requests/'+encodeURIComponent(item.id)+'/workflow',{method:'PATCH',body:JSON.stringify({owner_id:owner.value,priority:priority.value,due_date:due.value,revision:w.revision,note:note.value})});await load();notice('Suivi enregistré.')}catch(err){notice(err.message);save.disabled=false}};
 panel.append(form);const history=document.createElement('ul');for(const h of w.history){const li=document.createElement('li');li.textContent=h.created_at+' UTC · '+h.actor+' · '+(h.owner||'Non affectée')+' · '+h.priority+' · '+(h.due_date||'Sans échéance')+' · '+h.note;history.append(li)}panel.append(history);container.append(panel);
}
function renderCommercial(metrics){
 const totals={total:0,won:0,lost:0,untreated:0,overdue:0,treated:0,treatment_hours:0};
 for(const m of metrics)for(const key of Object.keys(totals))totals[key]+=m[key]||0;
 const rate=m=>m.total?(100*m.won/m.total).toFixed(1)+' %':'—';
 const delay=m=>m.treated?(m.treatment_hours/m.treated).toFixed(1)+' h':'—';
 $('commercial-kpis').replaceChildren();
 for(const [label,value] of [['Demandes filtrées',totals.total],['Part gagnée',rate(totals)],['Non traitées',totals.untreated],['À relancer (48 h)',totals.overdue],['Délai moyen',delay(totals)]]){
  const div=document.createElement('div'),n=document.createElement('strong');div.className='count';n.textContent=value;div.append(n,document.createTextNode(label));$('commercial-kpis').append(div);
 }
 const table=document.createElement('table'),head=table.createTHead().insertRow();
 for(const label of ['Prestation','Demandes','Gagnées','Perdues','Part gagnée','À relancer','Délai moyen']){const th=document.createElement('th');th.scope='col';th.textContent=label;head.append(th)}
 const body=table.createTBody();for(const m of metrics){const row=body.insertRow();for(const v of [m.category,m.total,m.won,m.lost,rate(m),m.overdue,delay(m)])cell(row,v)}
 $('commercial-breakdown').replaceChildren(table);
}
function renderWorkload(d){
 for(const id of ['workload-panel','owner-label','priority-label','overdue-label'])$(id).hidden=!d.can_manage_workflow;
 const select=$('owner'),selected=select.value;select.replaceChildren(option('','Tous'));
 if(!d.can_manage_workflow){$('workload').replaceChildren();return}
 select.append(option('unassigned','Non affectées'));if(d.can_filter_mine)select.append(option('mine','Mes demandes'));
 for(const a of d.workflow_owners||[])select.append(option(a.id,a.username));
 for(const a of d.workload||[])if(a.owner_id&&![...select.options].some(o=>o.value===a.owner_id))select.append(option(a.owner_id,a.owner||'Compte indisponible'));
 if([...select.options].some(o=>o.value===selected))select.value=selected;
 const table=document.createElement('table'),head=table.createTHead().insertRow();
 for(const label of ['Responsable','Total','Ouvertes','Urgentes ouvertes','Échéances dépassées','Gagnées','Part gagnée']){const th=document.createElement('th');th.scope='col';th.textContent=label;head.append(th)}
 const body=table.createTBody();for(const m of d.workload||[]){const row=body.insertRow();for(const v of [m.owner||(m.owner_id?'Compte indisponible':'Non affectées'),m.total,m.opened,m.urgent,m.overdue,m.won,m.total?(100*m.won/m.total).toFixed(1)+' %':'—'])cell(row,v)}
 $('workload').replaceChildren(table);
}
function logout(){epoch++;token='';$('token').value='';$('rows').replaceChildren();$('counts').replaceChildren();$('mail-summary').textContent='';$('commercial-kpis').replaceChildren();$('commercial-breakdown').replaceChildren();$('workload').replaceChildren();$('owner').replaceChildren(option('','Tous'));$('priority').value='';$('overdue').value='';$('dashboard').hidden=true;$('login').hidden=false;notice('Déconnecté.')}
function cell(row,text){const td=document.createElement('td');td.textContent=text;row.append(td);return td}
async function load(){const current=++epoch;const d=await api('/api/admin/requests?'+new URLSearchParams({q:$('search').value,status:$('status').value,besoin:$('besoin').value,period:$('period').value,owner:$('owner').value,priority:$('priority').value,overdue:$('overdue').value,page,page_size:$('page-size').value}));if(current!==epoch||!token)return;total=d.total;renderCommercial(d.commercial_metrics||[]);renderWorkload(d);$('counts').replaceChildren();for(const [v,l] of Object.entries(states)){const div=document.createElement('div');div.className='count';const n=document.createElement('strong');n.textContent=d.counts[v]||0;div.append(n,document.createTextNode(l));$('counts').append(div)}$('rows').replaceChildren();
const messages=d.items.flatMap(item=>item.communications||[]);const failures=messages.filter(m=>m.queue_state==='FAILED'||['bounced','complained','failed','suppressed'].includes(m.delivery)).length;$('mail-summary').textContent='Communications sur cette page : '+messages.length+' · Livrées : '+messages.filter(m=>m.delivery==='delivered').length+' · En échec : '+failures+' · En attente : '+messages.filter(m=>m.queue_state==='PENDING').length;
for(const item of d.items){const row=document.createElement('tr');const contact=cell(row,item.nom+' — '+item.org);const email=document.createElement('small');email.textContent=item.email;contact.append(email);const req=cell(row,item.besoin+(item.solution?' · '+item.solution:''));const details=document.createElement('details'),summary=document.createElement('summary'),msg=document.createElement('p');summary.textContent='Voir le message';msg.textContent=item.message;details.append(summary,msg);req.append(details);const date=document.createElement('small');date.textContent=item.created_at+' UTC';req.append(date);workflowEditor(req,item,d.workflow_owners||[]);conversionEditor(req,item);communicationCell(row,item.communications||[]);const select=document.createElement('select');select.setAttribute('aria-label','Nouveau statut pour '+item.org);for(const [v,l] of Object.entries(states))select.append(option(v,l));select.value=item.status;cell(row,'').append(select);const save=document.createElement('button');save.textContent='Enregistrer';save.onclick=async()=>{save.disabled=true;try{await api('/api/admin/requests/'+encodeURIComponent(item.id),{method:'PATCH',body:JSON.stringify({status:select.value,previous:item.status})});await load();notice('Statut enregistré.')}catch(e){notice(e.message);save.disabled=false}};cell(row,'').append(save);$('rows').append(row)}
if(!d.items.length){const row=document.createElement('tr');const td=cell(row,'Aucune demande.');td.colSpan=5;$('rows').append(row)}$('pages').textContent='Page '+page+' · '+total+' demande(s)';$('prev').disabled=page===1;$('next').disabled=page*Number($('page-size').value)>=total;}
async function refresh(){try{await load();notice('Liste actualisée.')}catch(e){notice(e.message)}}
$('login-form').onsubmit=async e=>{e.preventDefault();token=$('token').value;$('token').value='';page=1;try{await load();$('login').hidden=true;$('dashboard').hidden=false;notice('Connecté.')}catch(e){token='';notice(e.message)}};
$('logout').onclick=logout;$('filter').onsubmit=e=>{e.preventDefault();page=1;refresh()};$('refresh').onclick=refresh;$('prev').onclick=()=>{if(page>1){page--;refresh()}};$('next').onclick=()=>{if(page*Number($('page-size').value)<total){page++;refresh()}};
let searchTimer;$('search').addEventListener('input',()=>{clearTimeout(searchTimer);if(!token)return;const queued=++epoch;page=1;$('prev').disabled=$('next').disabled=true;searchTimer=setTimeout(()=>{if(token&&epoch===queued)refresh()},350)});$('page-size').onchange=()=>{clearTimeout(searchTimer);page=1;if(token)refresh()};
