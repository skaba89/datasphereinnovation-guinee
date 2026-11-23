// Client sheet: prepare a commercial email from a template, log it, open it in the user's mailbox.
(()=>{
 const $=id=>document.getElementById(id);
 let token='',reload=null,templates=[],opportunities=[];
 const notice=s=>{$('notice').textContent=s};
 const option=(select,value,label)=>{const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o)};
 async function api(method,path,body){
  const r=await fetch('/api/admin/crm/'+path,{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
  const d=await r.json();if(!r.ok)throw Error(d.error);return d;
 }
 function reset(){$('compose-message').hidden=true;$('compose-mailto').hidden=true;$('compose-mailto').removeAttribute('href')}

 window.dsigClientEmail=async(opps,key,onSaved)=>{
  // Keep a prepared message (and its mailto link) visible across history reloads.
  if(!opps){reset();token='';$('composer').hidden=true;return}
  token=key;reload=onSaved;
  opportunities=opps.filter(o=>o.email);
  try{
   const d=await api('GET','email-templates');
   templates=d.items;
   $('composer').hidden=!d.can_compose;
   $('manage-templates').hidden=!d.can_manage;
   if(!d.can_compose)return;
  }catch{ $('composer').hidden=true;return }
  const os=$('compose-opportunity'),ts=$('compose-template'),keep=os.value,keepTemplate=ts.value;
  os.replaceChildren();ts.replaceChildren();
  for(const o of opportunities)option(os,o.id,o.title+' · '+(o.contact||o.email));
  for(const t of templates)option(ts,t.id,t.name+' ('+t.language.toUpperCase()+')');
  if(opportunities.some(o=>o.id===keep))os.value=keep;
  if(templates.some(t=>t.id===keepTemplate))ts.value=keepTemplate;
  const empty=!opportunities.length||!templates.length;
  $('compose-preview').disabled=empty;
  if(!opportunities.length)notice('Aucune opportunité avec adresse e-mail : complétez le contact dans le CRM pour écrire au client.');
 };

 $('compose-form').onsubmit=async e=>{
  e.preventDefault();reset();
  try{
   const d=await api('POST','emails/preview',{opportunity_id:$('compose-opportunity').value,template_id:$('compose-template').value});
   $('compose-to').value=d.to;$('compose-subject').value=d.subject;$('compose-body').value=d.body;
   $('compose-message').hidden=false;$('compose-subject').focus();
  }catch(err){notice(err.message)}
 };
 for(const id of ['compose-opportunity','compose-template'])$(id).onchange=reset;

 $('compose-message').onsubmit=async e=>{
  e.preventDefault();
  try{
   const d=await api('POST','emails',{opportunity_id:$('compose-opportunity').value,template_id:$('compose-template').value,subject:$('compose-subject').value,body:$('compose-body').value});
   const link=$('compose-mailto');
   link.href='mailto:'+encodeURIComponent(d.to)+'?subject='+encodeURIComponent(d.subject)+'&body='+encodeURIComponent(d.body);
   link.hidden=false;
   notice('E-mail enregistré dans l’historique. Ouverture de votre messagerie…');
   link.click();
   if(reload)reload();
  }catch(err){notice(err.message)}
 };
})();
