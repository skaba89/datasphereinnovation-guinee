document.addEventListener('DOMContentLoaded',async()=>{
 const form=document.getElementById('login-form')||document.getElementById('form');const input=document.getElementById('token');if(!form||!input)return;
 const link=document.createElement('a');link.href='connexion.html';link.textContent='Portail de connexion';form.after(link);
 const button=document.getElementById('logout');if(button)button.addEventListener('click',async()=>{try{const r=await fetch('/api/auth/logout',{method:'POST',headers:{Authorization:'Bearer session','Content-Type':'application/json'},body:'{}'});if(r.ok)location.assign('connexion.html')}catch{} });
 try{const r=await fetch('/api/auth/me',{headers:{Authorization:'Bearer session'}});if(r.ok&&!input.value){const me=await r.json();renderSidebar(me);input.value='session';form.requestSubmit()}}catch{}
});

function renderSidebar(me){
 const items=[['requests','admin.html','Demandes'],['direction','direction.html','Pilotage'],['crm','crm.html','CRM'],['quotes','quotes.html','Devis et marges'],['missions','missions.html','Missions et CRA'],['billing','billing.html','Finance'],['consultants','consultants.html','Consultants'],['recruitment','recruitment.html','Recrutement'],['tenders','tenders.html','Appels d’offres'],['accounts','accounts.html','Comptes'],['audit','audit.html','Journal'],['documents','documents.html','Documents privés'],['alerts','alerts.html','Alertes métier'],['notifications','notifications.html','Notifications'],['my-activity','my-activity.html','Mes CRA']];
 const sidebar=document.createElement('aside');sidebar.className='app-sidebar';const heading=document.createElement('h2');heading.textContent='Espace professionnel';sidebar.append(heading);
 const nav=document.createElement('nav');nav.setAttribute('aria-label','Modules autorisés');
 const add=(url,label,home=false)=>{const a=document.createElement('a');a.href=url;a.textContent=label;if(home)a.className='sidebar-home';if(location.pathname.endsWith('/'+url))a.setAttribute('aria-current','page');nav.append(a)};
 add('connexion.html','← Mon espace',true);
 for(const [resource,url,label] of items){const mode=me.permissions[resource]??me.permissions['*'];if(mode)add(url,label)}
 sidebar.append(nav);document.querySelector('header').after(sidebar);document.body.classList.add('app-shell');
}

