const byId=id=>document.getElementById(id);
const statuses={PROSPECT:'Prospect',QUALIFIE:'Qualifié',PROPOSITION:'Proposition',NEGOCIATION:'Négociation',GAGNE:'Gagné',EN_MISSION:'En mission',TERMINE:'Terminé',PERDU:'Perdu'};
const fields=['company','contact','email','title','mode','skills','consultant_id','next_action','followup','notes','status'];
let token='',page=1,total=0,editing=null,epoch=0,lookupEpoch=0;
const editor=byId('editor'),consultant=byId('consultant');
const qualificationLabels={need:'Besoin confirmé',budget:'Budget confirmé',decision_maker:'Décideur identifié',timeline:'Échéance confirmée'};
const qualificationFields=[...Object.keys(qualificationLabels),'demo_status','demo_date'];
const demoLabels={NONE:'Non demandée',REQUESTED:'Demandée',SCHEDULED:'Planifiée',DONE:'Réalisée',CANCELLED:'Annulée'};
const qualificationBox=document.createElement('fieldset');qualificationBox.className='wide crm-qualification';
const legend=document.createElement('legend');legend.textContent='Qualification commerciale et démonstration';qualificationBox.append(legend);
function qualificationControl(key,label,choices){const wrapper=document.createElement('label');wrapper.textContent=label;const control=document.createElement(choices?'select':'input');control.name='qualification_'+key;if(choices){for(const [value,text] of Object.entries(choices))control.append(option(value,text))}else control.type='date';wrapper.append(control);qualificationBox.append(wrapper);return control}
for(const [key,label] of Object.entries(qualificationLabels))qualificationControl(key,label,{UNKNOWN:'À confirmer',NO:'Non',YES:'Oui'});
qualificationControl('demo_status','État de la démonstration',demoLabels);
qualificationControl('demo_date','Date de démonstration');
const qualificationScore=document.createElement('p');qualificationScore.setAttribute('role','status');qualificationBox.append(qualificationScore);
function updateQualification(){const score=Object.keys(qualificationLabels).filter(k=>editor.elements['qualification_'+k].value==='YES').length;qualificationScore.textContent=score+'/4 critères confirmés — indicateur descriptif, sans engagement commercial.'}
qualificationBox.addEventListener('input',updateQualification);
editor.insertBefore(qualificationBox,byId('save').parentElement);updateQualification();
editor.addEventListener('reset',()=>queueMicrotask(updateQualification));
byId('rows').addEventListener('click',e=>{if(e.target.tagName==='BUTTON'&&editing){for(const key of qualificationFields)editor.elements['qualification_'+key].value=editing.qualification[key];updateQualification()}});
function option(value,label){const o=document.createElement('option');o.value=value;o.textContent=label;return o}
for(const [value,label] of Object.entries(statuses))for(const id of ['editor-status','status'])byId(id).append(option(value,label));
function notice(message){byId('notice').textContent=message}
async function api(path,options={}){const r=await fetch('/api/admin/'+path,{...options,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'}});const d=await r.json();if(!r.ok)throw Error(d.error);return d}
function reset(){lookupEpoch++;editing=null;editor.reset();consultant.replaceChildren(option('','Aucun'));byId('form-title').textContent='Nouvelle opportunité'}
function cell(row,value){const td=document.createElement('td');td.textContent=value;row.append(td);return td}
async function lookup(){const current=++lookupEpoch;const q=byId('consultant-search').value;const d=await api('consultants?'+new URLSearchParams({q,status:'DISPONIBLE'}));if(current!==lookupEpoch||!token)return;const prior=consultant.selectedOptions[0];consultant.replaceChildren(option('','Aucun'));if(prior&&prior.value)consultant.append(option(prior.value,prior.textContent));for(const p of d.items)if(!Array.from(consultant.options).some(o=>o.value===p.id))consultant.append(option(p.id,p.name+' — '+p.role));if(prior)consultant.value=prior.value;notice(d.total>25?'25 résultats affichés : précisez la recherche.':d.total+' consultant(s) disponible(s).')}
byId('find-consultant').onclick=async()=>{try{await lookup()}catch(e){notice(e.message)}};
async function load(){const current=++epoch;const d=await api('crm?'+new URLSearchParams({q:byId('search').value,status:byId('status').value,page,page_size:byId('page-size').value}));if(current!==epoch||!token)return;total=d.total;byId('counts').replaceChildren();byId('rows').replaceChildren();for(const [value,label] of Object.entries(statuses)){const box=document.createElement('div');box.className='count';const n=document.createElement('strong');n.textContent=d.counts[value]||0;box.append(n,document.createTextNode(label));byId('counts').append(box)}
for(const item of d.items){const tr=document.createElement('tr');const profile=cell(tr,item.company);const sub=document.createElement('small');sub.textContent=item.title+' · '+item.mode;profile.append(sub);cell(tr,item.consultant_name?item.consultant_name+' ('+item.consultant_status+')':'Non affecté');const relance=cell(tr,item.followup||'À préciser');const action=document.createElement('small');action.textContent=item.next_action;relance.append(action);const now=new Date();if(item.followup&&Date.parse(item.followup)<Date.UTC(now.getFullYear(),now.getMonth(),now.getDate())&&!['TERMINE','PERDU'].includes(item.status))relance.className='deadline-late';const stage=cell(tr,statuses[item.status]);const summary=document.createElement('small');summary.textContent='Qualification : '+item.qualification_score+'/4 · Démo : '+demoLabels[item.qualification.demo_status]+(item.qualification.demo_date?' ('+item.qualification.demo_date+')':'');stage.append(summary);const b=document.createElement('button');b.textContent='Modifier';b.onclick=()=>{reset();editing=item;if(item.consultant_id)consultant.append(option(item.consultant_id,item.consultant_name||'Profil indisponible'));for(const f of fields)editor.elements[f].value=item[f];byId('form-title').textContent='Modifier l’opportunité';editor.scrollIntoView({block:'start'})};cell(tr,'').append(b);byId('rows').append(tr)}
if(!d.items.length){const tr=document.createElement('tr');cell(tr,'Aucune opportunité.').colSpan=5;byId('rows').append(tr)}byId('pages').textContent='Page '+page+' · '+total+' opportunité(s)';byId('prev').disabled=page===1;byId('next').disabled=page*Number(byId('page-size').value)>=total}
async function refresh(){try{await load()}catch(e){notice(e.message)}}
byId('login-form').onsubmit=async e=>{e.preventDefault();token=byId('token').value;byId('token').value='';page=1;try{await Promise.all([load(),loadCatalogue()]);byId('login').hidden=true;byId('workspace').hidden=false;notice('Connecté.')}catch(e){token='';notice(e.message)}};
byId('logout').onclick=()=>{epoch++;token='';reset();byId('sc-form').reset();byId('rows').replaceChildren();byId('counts').replaceChildren();byId('catalogue-rows').replaceChildren();byId('workspace').hidden=true;byId('login').hidden=false;notice('Déconnecté.')};
editor.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(editor));data.qualification={};for(const key of qualificationFields){data.qualification[key]=data['qualification_'+key];delete data['qualification_'+key]}const {demo_status,demo_date}=data.qualification;if((['SCHEDULED','DONE'].includes(demo_status)&&!demo_date)||(demo_status==='NONE'&&demo_date)){notice('Veuillez renseigner une date cohérente avec l’état de la démonstration.');return}const target=editing;if(target)data.version=target.version;byId('save').disabled=true;try{await api(target?'crm/'+encodeURIComponent(target.id):'crm',{method:target?'PATCH':'POST',body:JSON.stringify(data)});if(token){reset();page=1;await load();notice('Opportunité enregistrée.')}}catch(e){notice(e.message)}finally{byId('save').disabled=false}};
byId('cancel').onclick=reset;byId('filter').onsubmit=e=>{e.preventDefault();page=1;refresh()};byId('prev').onclick=()=>{if(page>1){page--;refresh()}};byId('next').onclick=()=>{if(page*Number(byId('page-size').value)<total){page++;refresh()}};
let searchTimer;byId('search').addEventListener('input',()=>{clearTimeout(searchTimer);if(!token)return;const queued=++epoch;page=1;byId('prev').disabled=byId('next').disabled=true;searchTimer=setTimeout(()=>{if(token&&epoch===queued)refresh()},350)});byId('page-size').onchange=()=>{clearTimeout(searchTimer);page=1;if(token)refresh()};

async function loadCatalogue(){const current=token,d=await api('crm/catalogue');if(!token||current!==token)return;const root=byId('catalogue-rows');root.replaceChildren();for(const x of d.items){const tr=document.createElement('tr');for(const k of ['name','sector','status','scope','conditions'])cell(tr,x[k]);root.append(tr)}}

const scForm=byId('sc-form'),scResults=byId('sc-results'),scNotice=byId('sc-notice');
function clearDiagnostic(){scResults.replaceChildren();scNotice.textContent=''}
scForm.addEventListener('reset',clearDiagnostic);
scForm.addEventListener('input',clearDiagnostic);
scForm.addEventListener('submit',e=>{
 e.preventDefault();clearDiagnostic();
 if(!token)return;
 const data=Object.fromEntries(new FormData(scForm));
 const keys=['shipments','on_time','otif','checked','accurate','cost','km'];
 const values=keys.map(k=>Number(data[k]));
 if(!scForm.checkValidity()||keys.some(k=>data[k].trim()==='')||values.some(v=>!Number.isSafeInteger(v)||v<0)){scNotice.textContent='Mesures invalides.';return}
 const [shipments,onTime,otif,checked,accurate,cost,km]=values;
 if(onTime>shipments||otif>onTime||accurate>checked){scNotice.textContent='Incohérence : vérifiez les volumes et les sous-totaux.';return}
 const format=n=>n.toLocaleString('fr-FR',{maximumFractionDigits:2});
 const rate=(n,d)=>d?format(100*n/d)+' %':'Non calculable';
 const unit=(n,d)=>d?format(n/d)+' '+data.currency:'Non calculable';
 const metrics=[['Livraisons à l’heure',rate(onTime,shipments)],['OTIF (à l’heure et complètes)',rate(otif,shipments)],['Exactitude du stock',rate(accurate,checked)],['Coût par livraison',unit(cost,shipments)],['Coût par km',unit(cost,km)]];
 for(const [label,value] of metrics){const box=document.createElement('div');box.className='count';const strong=document.createElement('strong');strong.textContent=value;box.append(strong,document.createTextNode(label));scResults.append(box)}
 scNotice.textContent='Diagnostic calculé pour '+data.period+' — '+data.currency+'. Les valeurs non calculables correspondent aux dénominateurs nuls.';
});
