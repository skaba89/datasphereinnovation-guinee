// Single source for the legal notice and public privacy notice (V161).
// No legal identifier may be published unless it is confirmed, sourced and validated
// by a named human reviewer. Unconfirmed fields stay null and render as "not published".
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const approvedContact='contact@datasphere-innovation.net';
export const legalPaths={fr:{legal:'/mentions-legales.html',privacy:'/confidentialite.html'},en:{legal:'/legal-en.html',privacy:'/privacy-en.html'}};

// Facts already established in the repository (site content, approved V160 mailbox, public export tests).
export const confirmedFacts=[
 {id:'trade_name',fr:['Nom utilisé sur le site','DataSphere Innovation Guinée (DSIG)'],en:['Name used on this website','DataSphere Innovation Guinée (DSIG)']},
 {id:'status',fr:['Statut déclaré','Projet de société en structuration'],en:['Declared status','Company project in development']},
 {id:'contact',fr:['Contact',approvedContact],en:['Contact',approvedContact]},
 {id:'website',fr:['Site','https://dsig-consulting.com'],en:['Website','https://dsig-consulting.com']},
 {id:'area',fr:['Zone d’intervention','Conakry, Guinée et France, selon le projet'],en:['Service area','Conakry, Guinea and France, depending on the project']}
];

// Every value is null until an official document is provided and validated by a human reviewer.
// To confirm a field: set value, confirmed:true, source (official document reference) and validatedBy.
export const legalFields=[
 {id:'legal_name',section:'publisher',fr:'Dénomination sociale officielle',en:'Registered company name'},
 {id:'legal_form',section:'publisher',fr:'Forme juridique',en:'Legal form'},
 {id:'share_capital',section:'publisher',fr:'Capital social',en:'Share capital'},
 {id:'rccm',section:'publisher',fr:'Numéro RCCM',en:'RCCM registration number'},
 {id:'nif',section:'publisher',fr:'Numéro d’identification fiscale (NIF)',en:'Tax identification number (NIF)'},
 {id:'registered_office',section:'publisher',fr:'Adresse du siège social',en:'Registered office address'},
 {id:'legal_representative',section:'publisher',fr:'Représentant légal',en:'Legal representative'},
 {id:'publication_director',section:'publisher',fr:'Directeur de la publication',en:'Publication director'},
 {id:'host_name',section:'host',fr:'Hébergeur (raison sociale)',en:'Hosting provider (company name)'},
 {id:'host_address',section:'host',fr:'Adresse de l’hébergeur',en:'Hosting provider address'},
 {id:'host_contact',section:'host',fr:'Contact de l’hébergeur',en:'Hosting provider contact'},
 {id:'data_controller',section:'privacy',fr:'Responsable du traitement',en:'Data controller'},
 {id:'email_provider',section:'privacy',fr:'Prestataire de messagerie',en:'Email service provider'},
 {id:'email_retention',section:'privacy',fr:'Durée de conservation des e-mails',en:'Email retention period'},
 {id:'log_retention',section:'privacy',fr:'Durée de conservation des journaux techniques',en:'Technical log retention period'},
 {id:'applicable_law',section:'privacy',fr:'Cadre juridique applicable (revue juridique)',en:'Applicable legal framework (legal review)'},
 {id:'supervisory_authority',section:'privacy',fr:'Autorité de contrôle compétente',en:'Competent supervisory authority'}
].map(field=>({value:null,confirmed:false,source:'',validatedBy:'',...field}));

const placeholder=/^(?:todo|tbd|xxx+|n\/?a|pending|example|placeholder|lorem|à confirmer|a confirmer|to be confirmed|non validé|0+)$|xxx|lorem|placeholder|example\.|à compléter|to be completed/i;
const filled=s=>typeof s==='string'&&s.trim().length>=3&&!placeholder.test(s.trim());

// Throws on any field that could present unvalidated data as official.
export function assertPublishable(fields=legalFields){
 const ids=new Set();
 for(const f of fields){
  if(!/^[a-z_]+$/.test(f.id)||ids.has(f.id))throw Error('Invalid legal field id: '+f.id);
  ids.add(f.id);
  if(f.value===null){if(f.confirmed)throw Error('Confirmed legal field without value: '+f.id);continue;}
  if(f.confirmed!==true)throw Error('Unconfirmed legal value must stay null: '+f.id);
  if(!filled(f.value))throw Error('Placeholder legal value refused: '+f.id);
  if(!filled(f.source)||!filled(f.validatedBy))throw Error('Legal value requires official source and human validator: '+f.id);
 }
 return true;
}

export function legalReadiness(fields=legalFields){
 assertPublishable(fields);
 const missing=fields.filter(f=>f.value===null).map(f=>f.id);
 return {complete:missing.length===0,missing};
}

const esc=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const pending={fr:'Non publié — en attente de validation officielle',en:'Not published — awaiting official validation'};
const home=lang=>lang==='en'?'/en.html':'/';

function list(lang,fields){
 return '<dl class="legal-list">'+fields.map(f=>'<dt>'+esc(f[lang])+'</dt><dd'+(f.value===null?' class="legal-pending" data-legal-pending="'+f.id+'"':'')+'>'+esc(f.value===null?pending[lang]:f.value)+'</dd>').join('')+'</dl>';
}
function facts(lang,contact){
 return '<dl class="legal-list">'+confirmedFacts.map(f=>{const [label,value]=f[lang];return '<dt>'+esc(label)+'</dt><dd>'+(f.id==='contact'?'<a href="mailto:'+esc(contact)+'">'+esc(contact)+'</a>':esc(value))+'</dd>';}).join('')+'</dl>';
}
function banner(lang,ready){
 if(ready.complete)return '';
 return '<p class="legal-status" role="note"><strong>'+(lang==='en'?'Incomplete notice.':'Mentions incomplètes.')+'</strong> '+(lang==='en'
  ?'The company is still being formed. Items marked “not published” have not been officially validated and must not be treated as official information.'
  :'La société est en cours de structuration. Les éléments marqués « non publié » n’ont pas été validés officiellement et ne doivent pas être considérés comme des informations officielles.')+'</p>';
}

export function renderLegalMain(lang,contact=approvedContact,fields=legalFields){
 const en=lang==='en',ready=legalReadiness(fields),by=s=>fields.filter(f=>f.section===s);
 return '<main class="policy" id="main" tabindex="-1"><div class="tag">'+(en?'LEGAL':'INFORMATIONS LÉGALES')+'</div><h1>'+(en?'Legal notice':'Mentions légales')+'</h1>'+banner(lang,ready)+
  '<h2>'+(en?'Confirmed information':'Informations confirmées')+'</h2>'+facts(lang,contact)+
  '<h2>'+(en?'Website publisher':'Éditeur du site')+'</h2>'+list(lang,by('publisher'))+
  '<h2>'+(en?'Hosting':'Hébergement')+'</h2>'+list(lang,by('host'))+
  '<h2>'+(en?'Intellectual property':'Propriété intellectuelle')+'</h2><p>'+(en
   ?'Third-party names and logos shown on this website remain the property of their respective owners; they are not contractual references or partnerships.'
   :'Les noms et logos de tiers présentés sur ce site restent la propriété de leurs titulaires respectifs ; ils ne constituent pas des références contractuelles ou des partenariats.')+'</p>'+
  '<h2>'+(en?'Personal data':'Données personnelles')+'</h2><p><a href="'+legalPaths[lang].privacy+'">'+(en?'Read the privacy notice':'Consulter la notice de confidentialité')+'</a></p>'+
  '<p><a href="'+home(lang)+'">'+(en?'Back to website':'Retour au site')+'</a></p></main>';
}

export function renderPrivacyMain(lang,contact=approvedContact,fields=legalFields){
 const en=lang==='en',ready=legalReadiness(fields),mail='<a href="mailto:'+esc(contact)+'">'+esc(contact)+'</a>';
 const p=(fr,english)=>'<p>'+(en?english:fr)+'</p>';
 return '<main class="policy" id="main" tabindex="-1"><div class="tag">'+(en?'TRANSPARENCY':'TRANSPARENCE')+'</div><h1>'+(en?'Privacy and personal data':'Confidentialité et données personnelles')+'</h1>'+banner(lang,ready)+
  '<h2>'+(en?'Scope':'Périmètre')+'</h2>'+p('Cette notice concerne uniquement le site public dsig-consulting.com. L’environnement de recette (REC) est distinct, à accès restreint, non destiné au public et couvert par sa propre notice.','This notice only covers the public website dsig-consulting.com. The test environment (REC) is separate, access-restricted, not intended for the public and covered by its own notice.')+
  '<h2>'+(en?'What this website does not collect':'Ce que ce site ne collecte pas')+'</h2>'+p('Ce site statique ne contient aucun formulaire, aucun compte utilisateur, aucun cookie, aucun outil de mesure d’audience ou de publicité. Polices, images et scripts sont servis depuis ce site, sans ressource tierce. Le menu de navigation n’utilise aucun stockage dans votre navigateur.','This static website has no form, no user account, no cookies, and no analytics or advertising tools. Fonts, images and scripts are served from this website, with no third-party resources. The navigation menu stores nothing in your browser.')+
  '<h2>'+(en?'Contact by email':'Contact par e-mail')+'</h2>'+p('Les liens e-mail ouvrent votre propre messagerie. Si vous écrivez à '+mail+', votre adresse et le contenu de votre message sont utilisés pour répondre à votre demande. Ne transmettez ni données sensibles, ni CV, ni document personnel lors du premier contact.','Email links open your own email application. If you write to '+mail+', your address and message are used to answer your request. Do not send sensitive data, CVs or personal documents during initial contact.')+
  '<h2>'+(en?'Technical logs':'Journaux techniques')+'</h2>'+p('Comme pour tout site web, l’infrastructure d’hébergement peut traiter des données techniques de connexion (adresse IP, date, page demandée, navigateur) pour la sécurité et le bon fonctionnement du service.','As with any website, the hosting infrastructure may process technical connection data (IP address, date, requested page, browser) for security and service operation.')+
  '<h2>'+(en?'Your rights':'Vos droits')+'</h2>'+p('Pour toute question ou demande concernant vos données, écrivez à '+mail+'. Les modalités d’exercice des droits et l’autorité de recours seront précisées après revue juridique.','For any question or request about your data, write to '+mail+'. Rights procedures and the competent authority will be specified after legal review.')+
  '<h2>'+(en?'Items awaiting validation':'Éléments en attente de validation')+'</h2>'+list(lang,fields.filter(f=>f.section==='privacy'||f.id==='host_name'))+
  '<p><a href="'+legalPaths[lang].legal+'">'+(en?'Legal notice':'Mentions légales')+'</a> · <a href="'+home(lang)+'">'+(en?'Back to website':'Retour au site')+'</a></p></main>';
}

// Static REC page shell (flat relative links, same layout as the REC privacy page).
export function renderLegalPage(lang,contact=approvedContact,fields=legalFields){
 const en=lang==='en',back=en?'en.html':'index.html';
 return '<!doctype html><html lang="'+lang+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+(en?'Legal notice':'Mentions légales')+' | DataSphere Innovation Guinée</title><link rel="icon" href="favicon.svg">'+
  ['style.css','brand.css','premium.css','studio.css','identity.css'].map(c=>'<link rel="stylesheet" href="'+c+'">').join('')+
  '<meta name="robots" content="noindex,nofollow"><meta property="og:site_name" content="DSIG — DataSphere Innovation Guinée"><link rel="stylesheet" href="local-intake.css"><link rel="stylesheet" href="accessibility.css"></head><body><a class="skip-link" href="#main">'+(en?'Skip to content':'Aller au contenu')+'</a><header class="nav"><a class="brand" href="'+back+'"><img class="dsig-logo" src="dsig-mark.svg" width="100" height="40" alt="DSIG"><span class="brand-name">DataSphere<small>INNOVATION GUINÉE</small></span></a><a href="'+(en?'mentions-legales.html':'legal-en.html')+'" hreflang="'+(en?'fr':'en')+'">'+(en?'Français':'English')+'</a></header>'+
  renderLegalMain(lang,contact,fields)+
  '<footer><p>DataSphere Innovation Guinée · '+(en?'Company project in development.':'Projet de société en structuration.')+'</p><a href="'+(en?'privacy-en.html':'confidentialite.html')+'">'+(en?'Privacy notice':'Confidentialité')+'</a></footer></body></html>';
}

export function writeDistLegalPages(dist){
 fs.writeFileSync(path.join(dist,'mentions-legales.html'),renderLegalPage('fr'));
 fs.writeFileSync(path.join(dist,'legal-en.html'),renderLegalPage('en'));
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 if(process.argv[2]==='--write-dist'){writeDistLegalPages(path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..','dist'));console.log('Legal pages written to dist/');}
 else{const r=legalReadiness();console.log(JSON.stringify(r,null,2));if(!r.complete)process.exitCode=1;}
}
