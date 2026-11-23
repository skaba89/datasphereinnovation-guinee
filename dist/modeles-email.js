// Commercial email templates: list, create and edit (ADMIN only, enforced server-side).
const $=id=>document.getElementById(id);
let token='',epoch=0,items=[],editing=null;
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n};
function notice(s){$('notice').textContent=s}
async function api(method,path,body){
 const r=await fetch('/api/admin/crm/email-templates'+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
 const d=await r.json();if(!r.ok)throw Error(d.error);return d;
}
function edit(t){
 editing=t;const f=$('editor');
 $('editor-title').textContent=t?'Modifier « '+t.name+' »':'Nouveau modèle';
 f.name.value=t?t.name:'';f.language.value=t?t.language:'fr';f.active.value=String(t?!!t.active:true);
 f.subject.value=t?t.subject:'';f.body.value=t?t.body:'';
 $('editor-section').hidden=false;f.name.focus();
}
function render(){
 const body=$('rows');body.replaceChildren();
 for(const t of items){
  const tr=el('tr');tr.append(el('td',t.name),el('td',t.language.toUpperCase()),el('td',t.subject),el('td',t.active?'Actif':'Inactif'));
  const td=el('td'),b=el('button','Modifier');b.type='button';b.setAttribute('aria-label','Modifier le modèle '+t.name);b.onclick=()=>edit(t);td.append(b);tr.append(td);body.append(tr);
 }
}
async function load(){
 const mine=++epoch;const d=await api('GET','');
 if(mine!==epoch||!token)return;
 if(!d.can_manage)throw Error('Gestion des modèles réservée aux administrateurs.');
 items=d.items;render();
}
$('editor').onsubmit=async e=>{
 e.preventDefault();const f=e.target;
 const body={name:f.name.value,language:f.language.value,active:f.active.value==='true',subject:f.subject.value,body:f.body.value};
 try{
  if(editing)await api('PATCH','/'+editing.id,{...body,version:editing.version});else await api('POST','',body);
  $('editor-section').hidden=true;editing=null;notice('Modèle enregistré.');await load();
 }catch(err){notice(err.message)}
};
$('new-template').onclick=()=>edit(null);
$('cancel').onclick=()=>{$('editor-section').hidden=true;editing=null};
$('login-form').onsubmit=async e=>{e.preventDefault();token=$('token').value;$('token').value='';try{await load();$('login').hidden=true;$('workspace').hidden=false}catch(err){token='';notice(err.message)}};
$('logout').onclick=()=>{epoch++;token='';items=[];$('rows').replaceChildren();$('editor-section').hidden=true;$('workspace').hidden=true;$('login').hidden=false;notice('Déconnecté.')};
