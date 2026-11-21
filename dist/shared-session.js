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
  'my-activity.html':['rows'],'appointments.html':['rows'],'recruitment.html':['rows']
 };
 for(const id of lists[page]||[]){
  const root=document.getElementById(id);if(!root)continue;
  const controls=document.createElement('div');controls.className='dsig-pager';
  controls.setAttribute('role','group');controls.setAttribute('aria-label','Pagination '+id);
  const prev=document.createElement('button'),next=document.createElement('button'),status=document.createElement('span'),size=document.createElement('select');
  prev.type=next.type='button';prev.textContent='Précédent';next.textContent='Suivant';status.setAttribute('role','status');
  size.setAttribute('aria-label','Éléments par page');for(const n of [10,25,50])size.append(new Option(n+' par page',n));size.value='25';
  controls.append(prev,status,next,size);
  const anchor=root.closest('.table-wrap')||root;anchor.after(controls);
  let current=1;
  function render(){const items=Array.from(root.children);const limit=Number(size.value),pages=Math.max(1,Math.ceil(items.length/limit));current=Math.min(current,pages);items.forEach((item,i)=>{item.hidden=i<(current-1)*limit||i>=current*limit});status.textContent='Page '+current+' / '+pages+' · '+items.length+' élément(s)';prev.disabled=current===1;next.disabled=current===pages;controls.hidden=items.length<=10;}
  prev.onclick=()=>{current--;render()};next.onclick=()=>{current++;render()};size.onchange=()=>{current=1;render()};
  new MutationObserver(()=>{current=1;render()}).observe(root,{childList:true});render();
 }
});
