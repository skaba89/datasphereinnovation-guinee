document.addEventListener('DOMContentLoaded',async()=>{
 const form=document.getElementById('login-form')||document.getElementById('form');const input=document.getElementById('token');if(!form||!input)return;
 const link=document.createElement('a');link.href='connexion.html';link.textContent='Portail de connexion';link.setAttribute('aria-label','Portail de connexion — identifiant, mot de passe et MFA');form.after(link);
 const button=document.getElementById('logout');if(button)button.addEventListener('click',async()=>{try{const r=await fetch('/api/auth/logout',{method:'POST',headers:{Authorization:'Bearer session','Content-Type':'application/json'},body:'{}'});if(r.ok)location.assign('connexion.html')}catch{} });
 try{const r=await fetch('/api/auth/me',{headers:{Authorization:'Bearer session'}});if(r.ok&&!input.value){const me=await r.json();renderSidebar(me);input.value='session';form.requestSubmit()}}catch{}
});

function renderSidebar(me){
 const items=[['requests','admin.html','Demandes'],['direction','direction.html','Pilotage'],['crm','crm.html','CRM'],['crm','appointments.html','Rendez-vous commerciaux'],['quotes','quotes.html','Devis et marges'],['missions','missions.html','Missions et CRA'],['billing','billing.html','Finance'],['consultants','consultants.html','Consultants'],['recruitment','recruitment.html','Recrutement'],['tenders','tenders.html','Appels d’offres'],['accounts','accounts.html','Comptes'],['audit','audit.html','Journal'],['documents','documents.html','Documents privés'],['alerts','alerts.html','Alertes métier'],['notifications','notifications.html','Notifications'],['my-activity','my-activity.html','Mes CRA']];
 const sidebar=document.createElement('aside');sidebar.className='app-sidebar';const heading=document.createElement('h2');heading.textContent='Espace professionnel';sidebar.append(heading);
 const nav=document.createElement('nav');nav.setAttribute('aria-label','Modules autorisés');
 const add=(url,label,home=false)=>{const a=document.createElement('a');a.href=url;a.textContent=label;if(home)a.className='sidebar-home';if(location.pathname.endsWith('/'+url))a.setAttribute('aria-current','page');nav.append(a)};
 add('connexion.html','← Mon espace',true);
 for(const [resource,url,label] of items){const mode=me.permissions[resource]??me.permissions['*'];if(mode)add(url,label)}
 sidebar.append(nav);document.querySelector('header').after(sidebar);document.body.classList.add('app-shell');
}


/* Paginate already-loaded lists only; keep server-side pagination untouched. */
document.addEventListener('DOMContentLoaded',()=>{
 const page=location.pathname.split('/').pop();
 const lists={
  'accounts.html':['rows','events'],'audit.html':['rows'],
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
  size.setAttribute('aria-label','Éléments par page');for(const n of [10,25,50])size.append(new Option(n+' par page',n));size.value='25';
  controls.append(search,prev,status,next,size);
  const anchor=root.closest('.table-wrap')||root;anchor.after(controls);
  let current=1;
  const normalize=value=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('fr');
  function render(){
   const children=Array.from(root.children),items=children.filter(item=>!(item.tagName==='TR'&&item.cells.length===1&&item.cells[0].colSpan>1));
   if(!items.length){search.value='';current=1;controls.hidden=true;children.forEach(item=>item.hidden=false);return;}
   const terms=normalize(search.value.trim()).split(/\s+/).filter(Boolean),matches=items.filter(item=>terms.every(term=>normalize(item.textContent).includes(term)));
   const limit=Number(size.value),pages=Math.max(1,Math.ceil(matches.length/limit));current=Math.min(current,pages);
   const visible=new Set(matches.slice((current-1)*limit,current*limit));items.forEach(item=>item.hidden=!visible.has(item));
   status.textContent=matches.length?'Page '+current+' / '+pages+' · '+matches.length+' / '+items.length+' élément(s)':'Aucun résultat sur '+items.length+' élément(s)';
   prev.disabled=current===1;next.disabled=current===pages;controls.hidden=false;
  }
  prev.onclick=()=>{current--;render()};next.onclick=()=>{current++;render()};size.onchange=search.oninput=()=>{current=1;render()};
  new MutationObserver(()=>{current=1;render()}).observe(root,{childList:true});render();
 }
});
