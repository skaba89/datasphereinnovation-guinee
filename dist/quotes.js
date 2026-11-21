const $=id=>document.getElementById(id), editor=$('editor'), opp=$('opportunity');
const fields=['opportunity_id','title','scope','mode','currency','days','rate','daily_cost','expenses','fixed_price','status','valid_until','terms'];
let token='',editing=null,page=1,total=0,epoch=0;
function notice(s){$('notice').textContent=s}
function option(v,t){const o=document.createElement('option');o.value=v;o.textContent=t;return o}
async function api(path,options={}){const r=await fetch('/api/admin/'+path,{...options,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'}});const d=await r.json();if(!r.ok)throw Error(d.error);return d}
function reset(){editing=null;editor.reset();opp.replaceChildren(option('','Sélectionner'));$('form-title').textContent='Nouveau devis'}
async function lookup(){const t=token;const d=await api('crm?'+new URLSearchParams({q:$('lookup').value}));if(!token||t!==token)return;const prior=opp.selectedOptions[0];opp.replaceChildren(option('','Sélectionner'));if(prior?.value)opp.append(option(prior.value,prior.textContent));for(const x of d.items)if(!Array.from(opp.options).some(o=>o.value===x.id))opp.append(option(x.id,x.company+' — '+x.title));if(prior)opp.value=prior.value;notice(d.total>25?'Précisez la recherche (25 premiers résultats).':d.total+' résultat(s).')}
function cell(tr,s){const td=document.createElement('td');td.textContent=s;tr.append(td);return td}
function money(n,x){return n+' '+x.currency}
function closeProposal(){$('proposal-preview').hidden=true;$('proposal-document').replaceChildren();document.body.classList.remove('proposal-print')}
function preview(x){
 const doc=$('proposal-document');doc.replaceChildren();
 const logo=document.createElement('img');logo.src='dsig-mark.svg';logo.alt='DSIG';logo.width=140;doc.append(logo);
 const add=(tag,value)=>{const element=document.createElement(tag);element.textContent=value;doc.append(element)};
 add('h2','DataSphere Innovation Guinée');
 add('h1','Proposition commerciale');
 add('p','RECETTE — DOCUMENT DE TRAVAIL À VALIDER');
 add('p','Référence : DSIG-'+x.id+' / v'+x.version);
 add('p','Client : '+x.company);
 add('p','Date de création : '+x.created_at.slice(0,10)+' · Validité : '+(x.valid_until||'À confirmer'));
 add('h2',x.title);add('p',x.scope);add('h2','Conditions financières');
 add('p','Mode : '+x.mode+' · Jours estimés : '+x.days);
 if(x.mode==='REGIE')add('p','Tarif journalier HT : '+money(x.rate,x));
 add('h2','Total HT estimé : '+money(x.revenue,x));
 add('h2','Conditions commerciales');add('p',x.terms||'À confirmer avant transmission.');
 add('p','Taxes, identité juridique et conditions finales à valider. Ce document ne constitue ni une facture ni un contrat signé.');
 $('proposal-preview').hidden=false;document.body.classList.add('proposal-print');$('proposal-preview').scrollIntoView();
}
$('print-proposal').onclick=()=>{if(token&&!$('proposal-preview').hidden)window.print()};
$('close-proposal').onclick=closeProposal;
function download(x){const lines=['DATASPHERE INNOVATION GUINÉE','PROPOSITION COMMERCIALE — À VALIDER','Référence : '+x.id+' / v'+x.version,'Client : '+x.company,'Objet : '+x.title,'Périmètre : '+x.scope,'Mode : '+x.mode,'Jours estimés : '+x.days,...(x.mode==='REGIE'?['Tarif journalier HT : '+money(x.rate,x)]:[]),'Total HT estimé : '+money(x.revenue,x),'Conditions et taxes à valider avant transmission.'];const url=URL.createObjectURL(new Blob([lines.join('\n\n')],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='DSIG-proposition-'+x.id+'.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function tracking(x,td,canManage){
 const sent=x.transmission, decision=x.decision;
 const info=document.createElement('p');info.textContent=decision?'Décision '+decision.decision+' · '+decision.created_at:sent?'Transmission enregistrée · '+sent.created_at:'Transmission non enregistrée';td.append(info);
 if(x.status==='ACCEPTE'){
  const p=document.createElement('p');p.textContent=x.contract?'Contrat signé enregistré : '+x.contract.reference+' · '+x.contract.signed_date:'Contrat signé non enregistré';td.append(p);
  if(canManage&&!x.contract){
   const form=document.createElement('form'), ref=document.createElement('input'), date=document.createElement('input'), evidence=document.createElement('textarea'), submit=document.createElement('button');
   ref.placeholder='Référence contrat';ref.required=true;ref.maxLength=180;ref.setAttribute('aria-label','Référence contrat');
   date.type='date';date.required=true;date.setAttribute('aria-label','Date de signature');
   evidence.placeholder='Référence de la preuve de signature';evidence.required=true;evidence.maxLength=1000;evidence.setAttribute('aria-label','Preuve de signature');
   submit.textContent='Enregistrer le contrat signé';form.append(ref,date,evidence,submit);td.append(form);
   form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{await api('quotes/'+x.id+'/contract',{method:'POST',body:JSON.stringify({version:x.version,reference:ref.value,signed_date:date.value,evidence:evidence.value})});if(token){await load();notice('Signature existante enregistrée.')}}catch(e){notice(e.message)}finally{submit.disabled=false}};
  }return;
 }
 if(!canManage||x.status!=='PROPOSE')return;
 const form=document.createElement('form'), action=document.createElement('select'), evidence=document.createElement('textarea'), submit=document.createElement('button');
 for(const [v,t] of (sent?[['ACCEPTE','Accepté'],['REFUSE','Refusé']]:[['TRANSMIS','Enregistrer la transmission']]))action.append(option(v,t));
 evidence.required=true;evidence.maxLength=1000;evidence.placeholder='Référence de la preuve ou confirmation client';evidence.setAttribute('aria-label','Preuve de transmission ou décision');
 submit.textContent='Enregistrer le suivi';form.append(action,evidence,submit);td.append(form);
 form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{await api('quotes/'+x.id+'/transmission',{method:'POST',body:JSON.stringify({version:x.version,action:action.value,evidence:evidence.value})});if(token){await load();notice('Suivi enregistré. Aucun envoi externe effectué.')}}catch(e){notice(e.message)}finally{submit.disabled=false}};
}
async function load(){const e=++epoch;const d=await api('quotes?page='+page);if(e!==epoch||!token)return;total=d.total;$('rows').replaceChildren();for(const x of d.items){const tr=document.createElement('tr');cell(tr,x.company+' / '+x.title);cell(tr,x.status);cell(tr,money(x.revenue,x));cell(tr,money(x.direct_cost,x));cell(tr,money(x.margin,x)+' ('+(x.margin_pct??'N/A')+' %)');const td=cell(tr,'');const edit=document.createElement('button');edit.textContent='Modifier';edit.disabled=['ACCEPTE','REFUSE'].includes(x.status)||x.transmission?.version===x.version;edit.onclick=()=>{reset();editing=x;opp.append(option(x.opportunity_id,x.company));for(const f of fields)editor.elements[f].value=x[f]??'';$('form-title').textContent='Modifier le devis';editor.scrollIntoView()};const dl=document.createElement('button');dl.textContent='Exporter proposition';dl.onclick=()=>download(x);const print=document.createElement('button');print.textContent='Aperçu PDF';print.onclick=()=>preview(x);td.append(edit,dl,print);tracking(x,td,d.can_manage);$('rows').append(tr)}$('pages').textContent='Page '+page+' · '+total+' devis';$('prev').disabled=page===1;$('next').disabled=page*25>=total}
async function safe(fn){try{await fn()}catch(e){notice(e.message)}}
$('login-form').onsubmit=async e=>{e.preventDefault();token=$('token').value;$('token').value='';try{await load();$('login').hidden=true;$('workspace').hidden=false;notice('Connecté.')}catch(e){token='';notice(e.message)}};
$('logout').onclick=()=>{epoch++;token='';closeProposal();reset();$('rows').replaceChildren();$('workspace').hidden=true;$('login').hidden=false;notice('Déconnecté.')};
$('find').onclick=()=>safe(lookup);$('cancel').onclick=reset;
editor.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(editor)),target=editing;if(target)data.version=target.version;$('save').disabled=true;try{await api(target?'quotes/'+target.id:'quotes',{method:target?'PATCH':'POST',body:JSON.stringify(data)});if(token){reset();page=1;await load();notice('Devis enregistré.')}}catch(e){notice(e.message)}finally{$('save').disabled=false}};
$('prev').onclick=()=>{if(page>1){page--;safe(load)}};$('next').onclick=()=>{if(page*25<total){page++;safe(load)}};
