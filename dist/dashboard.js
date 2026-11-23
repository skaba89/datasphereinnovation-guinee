// Cockpit shown after sign-in. Reads only the APIs the role may already use; server permissions apply.
(()=>{
 const workspace=document.getElementById('workspace');if(!workspace)return;
 const REQUESTS={NOUVELLE:'Nouvelles',QUALIFIEE:'Qualifiées',EN_COURS:'En cours',GAGNEE:'Gagnées',PERDUE:'Perdues'};
 const STAGES={PROSPECT:'Prospect',QUALIFIE:'Qualifié',PROPOSITION:'Proposition',NEGOCIATION:'Négociation',GAGNE:'Gagné',EN_MISSION:'En mission',TERMINE:'Terminé',PERDU:'Perdu'};
 const KINDS={CONTRAT:'Contrat',FACTURE:'Facture',CRA:'CRA',RELANCE:'Relance',RENOUVELLEMENT:'Renouvellement'};
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
 const svg=(tag,attrs)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n};
 const cockpit=el('section','cockpit');cockpit.id='cockpit';cockpit.setAttribute('aria-labelledby','cockpit-title');
 workspace.prepend(cockpit);
 let epoch=0;

 async function get(path){const r=await fetch('/api/admin/'+path,{headers:{Authorization:'Bearer session'}});const d=await r.json();if(!r.ok)throw Error(d.error||'Indisponible');return d}
 const can=(me,resource)=>!!(me.permissions[resource]??me.permissions['*']);

 function kpi(grid,value,label,href,tone){const a=el(href?'a':'div','kpi'+(tone?' '+tone:''));if(href)a.href=href;a.append(el('strong','',String(value)),el('span','',label));grid.append(a)}

 function bars(title,entries,href){
  const card=el('article','cockpit-card'),h=el('h3','',title);card.append(h);
  const max=Math.max(1,...entries.map(e=>e[1])),rowH=26,width=320,labelW=104,height=entries.length*rowH;
  const chart=svg('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':title+' : '+entries.map(([l,v])=>l+' '+v).join(', '),class:'cockpit-chart'});
  entries.forEach(([label,value],i)=>{
   const y=i*rowH,w=Math.round((width-labelW-36)*value/max);
   const t=svg('text',{x:0,y:y+17,class:'chart-label'});t.textContent=label;
   const r=svg('rect',{x:labelW,y:y+5,width:Math.max(w,value?3:0),height:16,rx:4,class:'chart-bar'});
   const v=svg('text',{x:labelW+w+6,y:y+17,class:'chart-value'});v.textContent=value;
   chart.append(t,r,v);
  });
  card.append(chart);if(href){const a=el('a','cockpit-link','Ouvrir');a.href=href;card.append(a)}
  return card;
 }

 function list(title,items,empty,href){
  const card=el('article','cockpit-card');card.append(el('h3','',title));
  if(!items.length)card.append(el('p','cockpit-empty',empty));
  else{const ul=el('ul','cockpit-list');for(const [main,meta,late] of items){const li=el('li',late?'late':'');li.append(el('span','',main),el('small','',meta));ul.append(li)}card.append(ul)}
  if(href){const a=el('a','cockpit-link','Tout voir');a.href=href;card.append(a)}
  return card;
 }

 async function render(){
  const current=++epoch;
  let me;try{const r=await fetch('/api/auth/me',{headers:{Authorization:'Bearer session'}});if(!r.ok)return;me=await r.json()}catch{return}
  if(current!==epoch)return;
  const sources=[];
  if(can(me,'requests'))sources.push(['requests',get('requests?page_size=10')]);
  if(can(me,'crm'))sources.push(['crm',get('crm?page_size=10')]);
  if(can(me,'alerts'))sources.push(['alerts',get('alerts?horizon=7')]);
  if(!sources.length){cockpit.hidden=true;return}
  const settled=await Promise.allSettled(sources.map(s=>s[1]));if(current!==epoch||workspace.hidden)return;
  const data=Object.fromEntries(sources.map((s,i)=>[s[0],settled[i].status==='fulfilled'?settled[i].value:null]));
  const today=new Date().toISOString().slice(0,10);
  const title=el('h2','','Tableau de bord');title.id='cockpit-title';
  const asOf=el('p','muted','Situation au '+today+' · données de votre périmètre');
  const grid=el('div','kpis'),cards=el('div','cockpit-grid');
  if(data.requests){
   const c=data.requests.counts||{},m=data.requests.commercial_metrics||[];
   const sum=k=>m.reduce((a,x)=>a+(Number(x[k])||0),0);
   kpi(grid,c.NOUVELLE||0,'Demandes nouvelles','admin.html');
   kpi(grid,sum('overdue'),'Demandes > 48 h sans traitement','admin.html',sum('overdue')?'alert':'');
   cards.append(bars('Demandes par statut',Object.entries(REQUESTS).map(([k,l])=>[l,c[k]||0]),'admin.html'));
   cards.append(list('Dernières demandes',(data.requests.items||[]).slice(0,5).map(x=>[x.org+' · '+x.besoin,(x.created_at||'').slice(0,10)+' · '+(REQUESTS[x.status]||x.status)+(x.workflow&&x.workflow.owner?' · '+x.workflow.owner:''),false]),'Aucune demande.','admin.html'));
  }
  if(data.crm){
   const c=data.crm.counts||{},open=['PROSPECT','QUALIFIE','PROPOSITION','NEGOCIATION'].reduce((a,k)=>a+(c[k]||0),0);
   kpi(grid,open,'Opportunités ouvertes','crm.html#kanban');
   kpi(grid,(c.GAGNE||0)+(c.EN_MISSION||0),'Gagnées / en mission','crm.html#kanban');
   cards.append(bars('Pipeline commercial',Object.entries(STAGES).map(([k,l])=>[l,c[k]||0]),'crm.html#kanban'));
  }
  if(data.alerts){
   const a=data.alerts;kpi(grid,a.urgent||0,'Alertes urgentes','alerts.html',a.urgent?'alert':'');
   cards.append(list('À traiter sous 7 jours',(a.items||[]).slice(0,6).map(x=>[(KINDS[x.kind]||x.kind)+' · '+x.label,x.due+(x.days_remaining<0?' · '+Math.abs(x.days_remaining)+' j de retard':x.days_remaining===0?' · aujourd’hui':' · dans '+x.days_remaining+' j'),x.days_remaining<0]),'Rien à traiter cette semaine.','alerts.html'));
  }
  const failed=sources.filter((s,i)=>settled[i].status!=='fulfilled').map(s=>s[0]);
  cockpit.replaceChildren(title,asOf,grid,cards);
  if(failed.length)cockpit.append(el('p','muted','Indicateurs indisponibles : '+failed.join(', ')+'.'));
  cockpit.hidden=false;
 }
 // connexion.js toggles #workspace after sign-in, sign-out and MFA changes.
 new MutationObserver(()=>{if(workspace.hidden){epoch++;cockpit.replaceChildren()}else render()}).observe(workspace,{attributes:true,attributeFilter:['hidden']});
 if(!workspace.hidden)render();
})();
