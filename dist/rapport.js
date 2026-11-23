// Weekly management report: online view, CSV export and printable (PDF) layout. Read-only.
const $=id=>document.getElementById(id);
let token='',epoch=0,current=null;
const STAGES=[['PROSPECT','Prospect'],['QUALIFIE','Qualifié'],['PROPOSITION','Proposition'],['NEGOCIATION','Négociation'],['GAGNE','Gagné'],['EN_MISSION','En mission'],['TERMINE','Terminé'],['PERDU','Perdu']];
const OPEN=['PROSPECT','QUALIFIE','PROPOSITION','NEGOCIATION'];
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined&&text!==null)n.textContent=text;return n};
function notice(s){$('notice').textContent=s}
function iso(d){return d.toISOString().slice(0,10)}
function shift(days){const d=new Date($('report-date').value+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+days);$('report-date').value=iso(d);return load()}
function kpi(value,label){const d=el('div','kpi');d.append(el('strong','',String(value)),el('span','',label));$('report-kpis').append(d)}
function rows(body,items,empty){
 body.replaceChildren();
 for(const [a,b] of items){const tr=el('tr');tr.append(el('td','',a),el('td','',String(b)));body.append(tr)}
 if(!items.length){const tr=el('tr'),td=el('td','',empty);td.colSpan=2;tr.append(td);body.append(tr)}
}
function url(format){return '/api/admin/direction/weekly-report?date='+encodeURIComponent($('report-date').value)+(format?'&format='+format:'')}

async function load(){
 const mine=++epoch;
 if(!/^\d{4}-\d{2}-\d{2}$/.test($('report-date').value))throw Error('Date invalide.');
 const r=await fetch(url(),{headers:{Authorization:'Bearer '+token}});
 const d=await r.json();if(!r.ok)throw Error(d.error);
 if(mine!==epoch||!token)return;
 current=d;
 const last=new Date(d.end+'T00:00:00Z');last.setUTCDate(last.getUTCDate()-1);
 $('report-period').textContent='Semaine '+d.week+' · du '+d.start+' au '+iso(last)+' inclus';
 document.title='DSIG | Rapport '+d.week;
 $('report-kpis').replaceChildren();
 kpi(d.requests,'Demandes reçues');kpi(d.auto_leads,'Prospects créés automatiquement');kpi(d.qualified,'Demandes qualifiées');
 kpi(d.quotes_sent,'Devis transmis');kpi(d.won,'Opportunités gagnées');kpi(d.lost,'Opportunités perdues');
 kpi(OPEN.reduce((n,k)=>n+(d.pipeline[k]||0),0),'Opportunités ouvertes');
 rows($('pipeline-rows'),STAGES.map(([k,l])=>[l,d.pipeline[k]||0]),'Aucune opportunité.');
 rows($('need-rows'),d.requests_by_need,'Aucune demande sur la période.');
 const list=$('attention');list.replaceChildren();
 const item=(text,alert)=>list.append(el('li',alert?'due':'',text));
 item('Demandes sans traitement depuis plus de 48 h : '+d.untreated_48h,d.untreated_48h>0);
 item('Relances commerciales en retard : '+d.overdue_followups_total,d.overdue_followups_total>0);
 for(const [company,title,day] of d.overdue_followups)item('· '+company+' — '+title+' (relance prévue le '+day+')',false);
 const recv=Object.entries(d.overdue_receivables);
 item('Créances échues non encaissées : '+(recv.length?recv.map(([c,v])=>v+' '+c).join(', '):'aucune'),recv.length>0);
 $('next').disabled=$('report-date').value>=tomorrow();
 notice('Rapport '+d.week+' chargé.');
}

async function exportCsv(){
 if(!token||!current)return;
 const r=await fetch(url('csv'),{headers:{Authorization:'Bearer '+token}});
 if(!r.ok){notice('Export indisponible.');return}
 const blob=await r.blob(),link=el('a'),href=URL.createObjectURL(blob);
 link.href=href;link.download='rapport-direction-'+current.week+'.csv';document.body.append(link);link.click();link.remove();
 setTimeout(()=>URL.revokeObjectURL(href),1000);
 notice('Export CSV '+current.week+' téléchargé.');
}

function tomorrow(){const d=new Date();d.setUTCDate(d.getUTCDate()+1);return iso(d)}
// Period end is excluded: default to tomorrow so the current day is included.
$('report-date').value=tomorrow();
$('login-form').onsubmit=async e=>{
 e.preventDefault();token=$('token').value;$('token').value='';
 try{await load();$('login').hidden=true;$('workspace').hidden=false}catch(err){token='';notice(err.message)}
};
$('report-date').onchange=()=>load().catch(err=>notice(err.message));
$('previous').onclick=()=>shift(-7).catch(err=>notice(err.message));
$('next').onclick=()=>shift(7).catch(err=>notice(err.message));
$('export-csv').onclick=()=>exportCsv().catch(()=>notice('Export indisponible.'));
$('print').onclick=()=>window.print();
$('logout').onclick=()=>{
 epoch++;token='';current=null;
 for(const id of ['report-kpis','pipeline-rows','need-rows','attention'])$(id).replaceChildren();
 $('report-period').textContent='';$('workspace').hidden=true;$('login').hidden=false;notice('Déconnecté.');
};
