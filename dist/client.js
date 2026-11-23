// Organization 360° view: read-only, sections filtered server-side by role.
const $=id=>document.getElementById(id);
let token='',epoch=0;
const STAGES={PROSPECT:'Prospect',QUALIFIE:'Qualifié',PROPOSITION:'Proposition',NEGOCIATION:'Négociation',GAGNE:'Gagné',EN_MISSION:'En mission',TERMINE:'Terminé',PERDU:'Perdu'};
const KINDS={OPPORTUNITE:'Opportunité',RENDEZ_VOUS:'Rendez-vous',DEMANDE:'Demande',DEVIS:'Devis',MISSION:'Mission',FACTURE:'Facture',PAIEMENT:'Encaissement',EMAIL:'E-mail'};
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined&&text!==null)n.textContent=text;return n};
const id=new URLSearchParams(location.search).get('id')||'';
function notice(s){$('notice').textContent=s}

function section(title,items,render,empty,href){
 const s=el('section'),h=el('h2','',title+' ('+items.length+')');s.append(h);
 if(!items.length)s.append(el('p','client-empty',empty));
 else{const ul=el('ul','client-items');for(const item of items){const li=el('li');render(li,item);ul.append(li)}s.append(ul)}
 if(href){const a=el('a','cockpit-link','Ouvrir le module');a.href=href;s.append(a)}
 return s;
}
function line(li,main,meta,badge,late){const left=el('div');left.append(el('span','',main));if(meta)left.append(el('small','',' · '+meta));li.append(left);if(badge)li.append(el('span','badge'+(late?' due':''),badge))}
function kpi(value,label){const d=el('div','kpi');d.append(el('strong','',String(value)),el('span','',label));$('client-kpis').append(d)}

async function load(){
 const current=++epoch;
 if(!/^[0-9a-f-]{36}$/.test(id))throw Error('Organisation non précisée. Ouvrez la fiche depuis le référentiel CRM.');
 const r=await fetch('/api/admin/crm/organizations/'+encodeURIComponent(id)+'/overview',{headers:{Authorization:'Bearer '+token}});
 const d=await r.json();if(!r.ok)throw Error(d.error);
 if(current!==epoch||!token)return;
 const org=d.organization,today=new Date().toISOString().slice(0,10);
 $('client-name').textContent=org.name;document.title='DSIG | '+org.name;
 $('client-meta').textContent=org.kind+(org.country?' · '+org.country:'')+' · créée le '+org.created_at.slice(0,10)+(org.notes?' · '+org.notes:'');
 $('client-kpis').replaceChildren();
 const open=d.opportunities.filter(o=>['PROSPECT','QUALIFIE','PROPOSITION','NEGOCIATION'].includes(o.status)).length;
 kpi(open,'Opportunités ouvertes');
 kpi(d.opportunities.filter(o=>['GAGNE','EN_MISSION','TERMINE'].includes(o.status)).length,'Opportunités gagnées');
 if(d.missions)kpi(d.missions.filter(m=>m.status==='ACTIVE').length,'Missions actives');
 if(d.billing_totals)for(const [c,t] of Object.entries(d.billing_totals))kpi(t.balance+' '+c,'Reste à encaisser ('+c+')');
 const main=el('div','client-main'),side=el('section');
 main.append(section('Opportunités',d.opportunities,(li,o)=>{line(li,o.title,[o.contact,o.email,o.followup?'relance '+o.followup:''].filter(Boolean).join(' · '),STAGES[o.status]||o.status,false);if(o.followup&&o.followup<today&&['PROSPECT','QUALIFIE','PROPOSITION','NEGOCIATION'].includes(o.status))li.append(el('span','badge due','Relance en retard'))},'Aucune opportunité liée.','crm.html#kanban'));
 if(d.requests)main.append(section('Demandes reçues',d.requests,(li,x)=>line(li,x.besoin,x.nom+' · '+x.created_at.slice(0,10),x.status),'Aucune demande liée.','admin.html'));
 if(d.quotes)main.append(section('Devis',d.quotes,(li,q)=>line(li,q.title,q.mode+' · '+q.revenue+' '+q.currency+' HT',q.status),'Aucun devis.','quotes.html'));
 if(d.missions)main.append(section('Missions',d.missions,(li,m)=>line(li,m.contract_ref,m.start_date+' → '+m.end_date,m.status),'Aucune mission.','missions.html'));
 if(d.invoices)main.append(section('Factures',d.invoices,(li,i)=>{const late=Number(i.balance)>0&&i.due_date<today;line(li,i.reference,i.amount+' '+i.currency+' · échéance '+i.due_date,Number(i.balance)>0?(late?'En retard · ':'Reste ')+i.balance+' '+i.currency:'Réglée',late)},'Aucune facture.','billing.html'));
 main.append(section('Rendez-vous',d.appointments,(li,a)=>line(li,a.title,a.starts.replace('T',' ').slice(0,16),a.status),'Aucun rendez-vous.','appointments.html'));
 main.append(section('E-mails préparés',d.emails||[],(li,m)=>line(li,m.subject,m.recipient+' · '+m.actor+' · '+String(m.created_at).slice(0,16)),'Aucun e-mail préparé.'));
 side.append(el('h2','','Historique'));
 if(!d.timeline.length)side.append(el('p','client-empty','Aucun événement.'));
 else{const ul=el('ul','timeline');for(const e of d.timeline){const li=el('li');li.append(el('span','',e.label),el('small','',(KINDS[e.kind]||e.kind)+' · '+String(e.at).replace('T',' ').slice(0,16)));ul.append(li)}side.append(ul)}
 $('client-body').replaceChildren(main,side);
 if(window.dsigClientEmail)window.dsigClientEmail(d.opportunities,token,()=>load().catch(err=>notice(err.message)));
}

$('login-form').onsubmit=async e=>{e.preventDefault();token=$('token').value;$('token').value='';try{await load();$('login').hidden=true;$('workspace').hidden=false;notice('Connecté.')}catch(err){token='';notice(err.message)}};
$('logout').onclick=()=>{epoch++;token='';$('client-body').replaceChildren();$('client-kpis').replaceChildren();if(window.dsigClientEmail)window.dsigClientEmail(null);$('workspace').hidden=true;$('login').hidden=false;notice('Déconnecté.')};
