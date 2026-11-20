const $=id=>document.getElementById(id);let token='',epoch=0;
const labels={requests:'Demandes',crm:'Opportunités',consultants:'Consultants',tenders:'Appels d’offres',quotes:'Devis'};
function notice(s){$('notice').textContent=s}
function elem(tag,text){const e=document.createElement(tag);e.textContent=text;return e}
async function load(){const e=++epoch;const r=await fetch('/api/admin/direction',{headers:{Authorization:'Bearer '+token}});const d=await r.json();if(!r.ok)throw Error(d.error);if(e!==epoch||!token)return;
 $('date').textContent='Situation au '+d.as_of;$('counts').replaceChildren();$('breakdown').replaceChildren();$('financial').replaceChildren();
 for(const [key,name] of Object.entries(labels)){const values=d.counts[key];const card=elem('div',name);card.className='count';card.prepend(elem('strong',Object.values(values).reduce((a,b)=>a+b,0)));$('counts').append(card);const block=elem('div','');block.append(elem('h3',name));for(const [s,n] of Object.entries(values))block.append(elem('p',s+' : '+n));$('breakdown').append(block)}
 $('alerts').textContent=d.overdue+' relance(s) en retard ; '+d.ambiguous_opportunities+' opportunité(s) avec plusieurs devis acceptés, exclues des totaux.';
 for(const x of d.financial){const row=document.createElement('tr');for(const k of ['currency','count','revenue','direct_cost','margin'])row.append(elem('td',x[k]));$('financial').append(row)}
 if(!d.financial.length){const row=document.createElement('tr'),td=elem('td','Aucun engagement chiffrable.');td.colSpan=5;row.append(td);$('financial').append(row)}
}
$('login-form').onsubmit=async e=>{e.preventDefault();token=$('token').value;$('token').value='';try{await load();$('login').hidden=true;$('workspace').hidden=false;notice('Connecté.')}catch(e){token='';notice(e.message)}};
$('refresh').onclick=async()=>{try{await load();notice('Actualisé.')}catch(e){notice(e.message)}};
$('logout').onclick=()=>{epoch++;token='';for(const id of ['counts','breakdown','financial','date','alerts'])$(id).replaceChildren();$('workspace').hidden=true;$('login').hidden=false;notice('Déconnecté.')};
