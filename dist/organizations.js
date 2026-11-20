// Reuse the CRM session and safe DOM rendering; separate directory editor.
const orgEditor=byId('org-editor');
let orgEditing=null,orgPage=1,orgTotal=0,orgEpoch=0;
const orgLabel=document.createElement('label');orgLabel.textContent='Référentiel associé (facultatif)';
const orgInput=document.createElement('input');orgInput.name='organization_id';orgInput.readOnly=true;orgInput.title='Identifiant de l’organisation sélectionnée';
const orgName=document.createElement('small');
const orgClear=document.createElement('button');orgClear.type='button';orgClear.textContent='Dissocier';
orgLabel.append(orgInput,orgName,orgClear);editor.prepend(orgLabel);
function setOrg(id,name){orgInput.value=id||'';orgName.textContent=name||'Aucune association';}
orgClear.onclick=()=>setOrg('','');
editor.addEventListener('reset',()=>{orgName.textContent='Aucune association';});
function orgNotice(s){byId('org-notice').textContent=s;}
function orgReset(){orgEditing=null;orgEditor.reset();}
byId('org-reset').onclick=orgReset;
async function orgLoad(){const current=++orgEpoch;try{const d=await api('crm/organizations?'+new URLSearchParams({q:byId('org-search').value,page:orgPage}));if(current!==orgEpoch||!token)return;orgTotal=d.total;const rows=byId('org-rows');rows.replaceChildren();for(const item of d.items){const tr=document.createElement('tr');cell(tr,item.name);cell(tr,item.kind+' · '+item.country);cell(tr,item.opportunities);const actions=cell(tr,'');const edit=document.createElement('button');edit.textContent='Modifier';edit.onclick=()=>{orgEditing=item;for(const f of ['name','kind','country','notes'])orgEditor.elements[f].value=item[f];};const link=document.createElement('button');link.textContent='Associer';link.onclick=()=>{setOrg(item.id,item.name);if(!editor.elements.company.value)editor.elements.company.value=item.name;orgNotice('Organisation sélectionnée. Enregistrez l’opportunité pour confirmer.');};actions.append(edit,link);rows.append(tr);}byId('org-page').textContent='Page '+orgPage+' · '+orgTotal+' organisation(s)';byId('org-prev').disabled=orgPage===1;byId('org-next').disabled=orgPage*25>=orgTotal;}catch(e){orgNotice(e.message);}}
byId('org-filter').onsubmit=e=>{e.preventDefault();orgPage=1;orgLoad();};
byId('org-prev').onclick=()=>{if(orgPage>1){orgPage--;orgLoad();}};
byId('org-next').onclick=()=>{if(orgPage*25<orgTotal){orgPage++;orgLoad();}};
orgEditor.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(orgEditor));const target=orgEditing;if(target)data.version=target.version;const button=orgEditor.querySelector('button');button.disabled=true;try{await api('crm/organizations'+(target?'/'+target.id:''),{method:target?'PATCH':'POST',body:JSON.stringify(data)});if(token){orgReset();orgPage=1;await orgLoad();orgNotice('Organisation enregistrée.');}}catch(e){orgNotice(e.message);}finally{button.disabled=false;}};
new MutationObserver(()=>{if(byId('workspace').hidden){orgEpoch++;orgReset();byId('org-rows').replaceChildren();orgNotice('');}else{orgPage=1;orgLoad();}}).observe(byId('workspace'),{attributes:true,attributeFilter:['hidden']});
// The CRM edit handler runs before this bubbling handler.
byId('rows').addEventListener('click',e=>{if(e.target.tagName==='BUTTON'&&editing)setOrg(editing.organization_id,editing.organization_name);});
new MutationObserver(()=>{if(byId('notice').textContent==='Opportunité enregistrée.'&&token)orgLoad();}).observe(byId('notice'),{childList:true});
