// Commercial tasks: personal daily list, team view, quick actions. Permissions enforced server-side.
const $=id=>document.getElementById(id);
let token='',epoch=0,data=null;
const KINDS={APPEL:'Appel',EMAIL:'E-mail',RELANCE:'Relance',RENDEZ_VOUS:'Rendez-vous',AUTRE:'Autre'};
const GROUPS=[['late','En retard'],['today','Aujourd’hui'],['upcoming','À venir'],['done','Terminées']];
const preset=new URLSearchParams(location.search).get('opportunity')||'';
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined&&text!==null)n.textContent=text;return n};
function notice(s){$('notice').textContent=s}
function plusDays(day,n){const d=new Date(day+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)}
async function api(method,path,body){
 const r=await fetch('/api/admin/crm/tasks'+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
 const d=await r.json();if(!r.ok)throw Error(d.error);return d;
}
function kpi(value,label,alert){const d=el('div','kpi'+(alert&&value?' alert':''));d.append(el('strong','',String(value)),el('span','',label));$('task-kpis').append(d)}
function fillSelect(select,items,label,keep){
 const fixed=[...select.options].slice(0,keep);select.replaceChildren(...fixed);
 for(const x of items){const o=el('option','',label(x));o.value=x.id;select.append(o)}
}

function render(){
 $('task-kpis').replaceChildren();
 kpi(data.counts.late,'Mes tâches en retard',true);kpi(data.counts.today,'Mes tâches du jour');kpi(data.counts.week,'Mes tâches à 7 jours');
 const root=$('task-groups');root.replaceChildren();
 for(const [bucket,title] of GROUPS){
  const items=data.items.filter(t=>t.bucket===bucket);if(!items.length)continue;
  const s=el('section');s.append(el('h2','',title+' ('+items.length+')'));
  const ul=el('ul','task-list');
  for(const t of items){
   const li=el('li',bucket),main=el('div','task-main');
   main.append(el('strong','',t.title));
   const where=t.company?t.company+' · '+t.opportunity_title:'Sans opportunité';
   main.append(el('small','',KINDS[t.kind]+' · '+(t.status==='A_FAIRE'?'échéance '+t.due_date:'terminée le '+String(t.closed_at).slice(0,10))+' · '+where+' · '+(t.owner||'non attribuée')));
   if(t.organization_id){const a=el('a','','Fiche client');a.href='client.html?id='+encodeURIComponent(t.organization_id);a.setAttribute('aria-label','Fiche client '+t.company);main.append(a)}
   li.append(main);
   const mayEdit=data.can_write&&t.status==='A_FAIRE'&&(data.manage_all||t.owner_id===''||t.owner_id===data.me);
   if(mayEdit){
    const actions=el('div','task-actions');
    const act=(label,body,aria)=>{const b=el('button','',label);b.type='button';b.setAttribute('aria-label',aria+' : '+t.title);b.onclick=()=>change(t,body,b);actions.append(b)};
    act('Fait',{status:'FAIT'},'Marquer comme faite');
    act('Demain',{due_date:plusDays(data.today,1)},'Reporter à demain');
    act('+7 j',{due_date:plusDays(t.due_date<data.today?data.today:t.due_date,7)},'Reporter d’une semaine');
    act('Annuler',{status:'ANNULEE'},'Annuler la tâche');
    li.append(actions);
   }
   ul.append(li);
  }
  s.append(ul);root.append(s);
 }
 if(!root.children.length)root.append(el('p','muted',$('state').value==='done'?'Aucune tâche terminée.':'Aucune tâche à faire. Bon travail !'));
}

async function load(){
 const mine=++epoch;
 const d=await api('GET','?view='+$('view').value+'&state='+$('state').value);
 if(mine!==epoch||!token)return;
 data=d;
 $('task-new').hidden=!d.can_write;
 if(d.can_write){
  const form=$('task-form');
  if(!form.due_date.value)form.due_date.value=d.today;
  const chosen=$('task-opportunity').value||preset;
  fillSelect($('task-opportunity'),d.opportunities,x=>x.company+' · '+x.title,1);
  $('task-opportunity').value=d.opportunities.some(x=>x.id===chosen)?chosen:'';
  const owner=$('task-owner').value;
  const owners=$('task-owner');owners.replaceChildren();
  const option=(value,label)=>{const o=el('option','',label);o.value=value;owners.append(o)};
  if(d.me)option('me','Moi');option('','Non attribuée');
  for(const x of d.owners)if(x.id!==d.me)option(x.id,x.username);
  $('task-owner').value=[...$('task-owner').options].some(o=>o.value===owner)?owner:$('task-owner').options[0].value;
 }
 render();
}

async function change(task,body,button){
 button.disabled=true;
 try{await api('PATCH','/'+task.id,{...body,version:task.version});notice('Tâche mise à jour.');await load()}
 catch(err){notice(err.message);button.disabled=false}
}

$('task-form').onsubmit=async e=>{
 e.preventDefault();const f=e.target;
 const body={title:f.title.value,kind:f.kind.value,due_date:f.due_date.value,opportunity_id:f.opportunity_id.value,owner_id:f.owner_id.value};
 try{await api('POST','',body);f.title.value='';notice('Tâche ajoutée.');await load();$('task-form').title.focus()}catch(err){notice(err.message)}
};
$('login-form').onsubmit=async e=>{
 e.preventDefault();token=$('token').value;$('token').value='';
 try{await load();$('login').hidden=true;$('workspace').hidden=false;if(preset&&!$('task-new').hidden)$('task-form').title.focus()}catch(err){token='';notice(err.message)}
};
for(const id of ['view','state'])$(id).onchange=()=>load().catch(err=>notice(err.message));
$('logout').onclick=()=>{epoch++;token='';data=null;for(const id of ['task-kpis','task-groups'])$(id).replaceChildren();$('workspace').hidden=true;$('login').hidden=false;notice('Déconnecté.')};
