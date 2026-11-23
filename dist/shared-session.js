document.addEventListener('DOMContentLoaded',async()=>{
 const form=document.getElementById('login-form')||document.getElementById('form');const input=document.getElementById('token');if(!form||!input)return;
 const link=document.createElement('a');link.href='connexion.html';link.textContent='Portail de connexion';link.setAttribute('aria-label','Portail de connexion — identifiant, mot de passe et MFA');form.after(link);
 const button=document.getElementById('logout');if(button)button.addEventListener('click',async()=>{try{const r=await fetch('/api/auth/logout',{method:'POST',headers:{Authorization:'Bearer session','Content-Type':'application/json'},body:'{}'});if(r.ok)location.assign('connexion.html')}catch{} });
 try{const r=await fetch('/api/auth/me',{headers:{Authorization:'Bearer session'}});if(r.ok&&!input.value){const me=await r.json();renderSidebar(me);input.value='session';form.requestSubmit()}}catch{}
});

function renderSidebar(me){
 const items=[['requests','admin.html','Demandes'],['direction','direction.html','Pilotage'],['crm','crm.html','CRM'],['crm','taches.html','Tâches commerciales'],['crm','appointments.html','Rendez-vous commerciaux'],['quotes','quotes.html','Devis et marges'],['missions','missions.html','Missions et CRA'],['billing','billing.html','Finance'],['consultants','consultants.html','Consultants'],['recruitment','recruitment.html','Recrutement'],['tenders','tenders.html','Appels d’offres'],['accounts','accounts.html','Comptes'],['audit','audit.html','Journal'],['documents','documents.html','Documents privés'],['alerts','alerts.html','Alertes métier'],['notifications','notifications.html','Notifications'],['my-activity','my-activity.html','Mes CRA']];
 const sidebar=document.createElement('aside');sidebar.className='app-sidebar';const heading=document.createElement('h2');heading.textContent='Espace professionnel';sidebar.append(heading);
 const nav=document.createElement('nav');nav.setAttribute('aria-label','Modules autorisés');
 const add=(url,label,home=false)=>{const a=document.createElement('a');a.href=url;a.textContent=label;if(home)a.className='sidebar-home';if(location.pathname.endsWith('/'+url))a.setAttribute('aria-current','page');nav.append(a)};
 add('connexion.html','← Mon espace',true);
 for(const [resource,url,label] of items){const mode=me.permissions[resource]??me.permissions['*'];if(mode)add(url,label)}
 // Phones: modules behind a "Menu" button, plus a bottom bar with the main shortcuts.
 nav.id='app-modules';
 const toggle=document.createElement('button');toggle.type='button';toggle.className='sidebar-toggle';toggle.textContent='Menu';
 toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-controls','app-modules');
 const setOpen=open=>{sidebar.classList.toggle('open',open);toggle.setAttribute('aria-expanded',String(open))};
 toggle.onclick=()=>setOpen(!sidebar.classList.contains('open'));
 sidebar.addEventListener('keydown',e=>{if(e.key==='Escape'&&sidebar.classList.contains('open')){setOpen(false);toggle.focus()}});
 sidebar.append(toggle,nav);document.querySelector('header').after(sidebar);document.body.classList.add('app-shell');
 const can=r=>!!(me.permissions[r]??me.permissions['*']);
 const shortcuts=[['connexion.html','Accueil',true],['taches.html','Tâches',can('crm')],['crm.html','CRM',can('crm')],['notifications.html','Notifications',can('notifications')]].filter(x=>x[2]);
 if(shortcuts.length>1&&!document.querySelector('.app-bottombar')){
  const bar=document.createElement('nav');bar.className='app-bottombar';bar.setAttribute('aria-label','Raccourcis');
  for(const [url,label] of shortcuts){const a=document.createElement('a');a.href=url;a.textContent=label;if(location.pathname.endsWith('/'+url))a.setAttribute('aria-current','page');bar.append(a)}
  document.body.append(bar);document.body.classList.add('has-bottombar');
 }
 renderTopbar(me);
}

/* Common top bar: logo, global search (CRM permission) and connected role. */
function renderTopbar(me){
 const header=document.querySelector('header');if(!header||header.querySelector('.topbar'))return;
 if(!header.querySelector('img')){const logo=document.createElement('img');logo.src='dsig-mark.svg';logo.alt='DSIG';logo.width=100;header.prepend(logo)}
 const bar=document.createElement('div');bar.className='topbar';
 const can=r=>!!(me.permissions[r]??me.permissions['*']);
 if(can('crm')){
  const form=document.createElement('form'),label=document.createElement('label'),input=document.createElement('input'),panel=document.createElement('div');
  form.className='global-search';form.setAttribute('role','search');
  label.className='visually-hidden';label.textContent='Recherche globale';label.htmlFor='global-search';
  input.id='global-search';input.type='search';input.placeholder='Rechercher un client, une opportunité… (Ctrl+K)';input.autocomplete='off';input.maxLength=80;
  input.setAttribute('aria-controls','global-results');
  panel.id='global-results';panel.className='global-results';panel.hidden=true;panel.setAttribute('aria-live','polite');
  form.append(label,input,panel);bar.append(form);
  const kinds={ORGANISATION:'Organisation',OPPORTUNITE:'Opportunité',DEMANDE:'Demande',DEVIS:'Devis'};
  let timer=0,seq=0;
  const close=()=>{panel.hidden=true;input.setAttribute('aria-expanded','false')};
  async function run(){
   const q=input.value.trim(),n=++seq;
   if(q.length<2){panel.replaceChildren();close();return}
   try{
    const r=await fetch('/api/admin/crm/search?'+new URLSearchParams({q}),{headers:{Authorization:'Bearer session'}});const d=await r.json();
    if(n!==seq)return;panel.replaceChildren();
    if(!r.ok){panel.textContent=d.error||'Recherche indisponible.'}
    else if(!d.items.length){const p=document.createElement('p');p.textContent='Aucun résultat pour « '+d.query+' ».';panel.append(p)}
    else{const status=document.createElement('p');status.className='visually-hidden';status.textContent=d.items.length+' résultat(s)';const ul=document.createElement('ul');for(const x of d.items){const li=document.createElement('li'),a=document.createElement('a'),tag=document.createElement('span'),small=document.createElement('small');a.href=x.url;tag.className='result-kind';tag.textContent=kinds[x.kind]||x.kind;small.textContent=x.detail;a.append(tag,document.createTextNode(x.label),small);li.append(a);ul.append(li)}panel.append(status,ul)}
    panel.hidden=false;input.setAttribute('aria-expanded','true');
   }catch{if(n===seq){panel.textContent='Recherche indisponible.';panel.hidden=false}}
  }
  input.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(run,250)});
  form.addEventListener('submit',e=>{e.preventDefault();clearTimeout(timer);run()});
  form.addEventListener('keydown',e=>{
   const links=[...panel.querySelectorAll('a')],i=links.indexOf(document.activeElement);
   if(e.key==='Escape'){close();input.focus()}
   else if(e.key==='ArrowDown'&&links.length){e.preventDefault();links[Math.min(i+1,links.length-1)].focus()}
   else if(e.key==='ArrowUp'&&links.length){e.preventDefault();i<=0?input.focus():links[i-1].focus()}
  });
  document.addEventListener('click',e=>{if(!form.contains(e.target))close()});
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();input.focus();input.select()}});
 }
 const who=document.createElement('span');who.className='topbar-role';who.textContent=me.role+(me.mfa_enabled?' · MFA active':'');
 bar.append(who);header.append(bar);
}


/* Keep original action buttons and their permission/confirmation handlers intact. */
function groupRowActions(cell,label){
 const buttons=Array.from(cell.children).filter(node=>node.tagName==='BUTTON');
 if(buttons.length<2)return;
 const details=document.createElement('details'),summary=document.createElement('summary'),body=document.createElement('div');
 details.className='row-actions';summary.textContent='Actions';summary.setAttribute('aria-label','Actions pour '+label);body.className='row-actions-body';
 details.append(summary,body);cell.insertBefore(details,buttons[0]);
 for(const button of buttons){button.type='button';body.append(button);}
 details.addEventListener('keydown',e=>{if(e.key==='Escape'&&details.open){details.open=false;summary.focus();e.stopPropagation()}});
}

/* Paginate already-loaded lists only; keep server-side pagination untouched. */
document.addEventListener('DOMContentLoaded',()=>{
 const page=location.pathname.split('/').pop();
 const lists={
  'accounts.html':['rows'],
  'crm.html':['catalogue-rows'],'direction.html':['financial','report-rows'],
  'billing.html':['forecast-rows','aging-rows','totals','cash-rows'],
  'my-activity.html':['rows'],'appointments.html':['rows']
 };
 for(const id of lists[page]||[]){
  const root=document.getElementById(id);if(!root)continue;
  const controls=document.createElement('div');controls.className='dsig-pager';
  controls.setAttribute('role','group');controls.setAttribute('aria-label','Pagination '+id);
  const prev=document.createElement('button'),next=document.createElement('button'),status=document.createElement('span'),size=document.createElement('select'),search=document.createElement('input');
  search.type='search';search.className='dsig-list-search';search.placeholder='Rechercher dans cette liste';search.setAttribute('aria-label','Rechercher dans '+id);search.autocomplete='off';
  prev.type=next.type='button';prev.textContent='Précédent';next.textContent='Suivant';status.setAttribute('role','status');
  size.setAttribute('aria-label','Éléments par page');for(const n of [10,25,50])size.append(new Option(n+' par page',n));size.value='10';
  controls.append(search,prev,status,next,size);
  const anchor=root.closest('.table-wrap')||root;if(page==='accounts.html'&&id==='rows'){search.placeholder='Rechercher un compte…';anchor.before(controls)}else anchor.after(controls);
  let current=1;
  const normalize=value=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('fr');
  function render(){
   const children=Array.from(root.children),items=children.filter(item=>!(item.tagName==='TR'&&item.cells.length===1&&item.cells[0].colSpan>1));
   if(!items.length){search.value='';current=1;controls.hidden=true;children.forEach(item=>item.hidden=false);return;}
   const terms=normalize(search.value.trim()).split(/\s+/).filter(Boolean),matches=items.filter(item=>terms.every(term=>normalize(item.dataset.searchText??item.textContent).includes(term)));
   const limit=Number(size.value),pages=Math.max(1,Math.ceil(matches.length/limit));current=Math.min(current,pages);
   const visible=new Set(matches.slice((current-1)*limit,current*limit));items.forEach(item=>item.hidden=!visible.has(item));
   status.textContent=matches.length?'Page '+current+' / '+pages+' · '+matches.length+' / '+items.length+' élément(s)':'Aucun résultat sur '+items.length+' élément(s)';
   prev.disabled=current===1;next.disabled=current===pages;controls.hidden=false;
  }
  prev.onclick=()=>{current--;render()};next.onclick=()=>{current++;render()};size.onchange=search.oninput=()=>{current=1;render()};
  new MutationObserver(()=>{current=1;render()}).observe(root,{childList:true});render();
 }
});
