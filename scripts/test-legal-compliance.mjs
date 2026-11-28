// V161: legal notice and privacy — no invented legal data, publication blocked, SEO/REC preserved.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {build} from './build-public-site.mjs';
import {legalFields,confirmedFacts,assertPublishable,legalReadiness,renderLegalMain,renderPrivacyMain,renderLegalPage,legalPaths,approvedContact} from './legal-content.mjs';

const dist=new URL('../dist/',import.meta.url);
const readDist=name=>fs.readFileSync(new URL(name,dist),'utf8');
const clone=()=>structuredClone(legalFields);
const confirm=(f,value)=>Object.assign(f,{value,confirmed:true,source:'Official registry extract (fixture)',validatedBy:'Fixture legal reviewer'});

// 1. Repository data: nothing legal is asserted without validation.
const expected=['legal_name','legal_form','share_capital','rccm','nif','registered_office','legal_representative','publication_director','host_name','host_address','host_contact','data_controller','email_provider','email_retention','log_retention','applicable_law','supervisory_authority'];
assert.deepEqual(legalFields.map(f=>f.id),expected);
for(const f of legalFields){assert.equal(f.value,null,f.id+' must stay null until validated');assert.equal(f.confirmed,false);assert(f.fr&&f.en);}
assert.deepEqual(legalReadiness(),{complete:false,missing:expected});
assert(confirmedFacts.some(f=>f.fr[1]===approvedContact));
assert.equal(approvedContact,'contact@dsig-consulting.com');

// 2. Guard: unvalidated or placeholder values are refused.
const refuse=(mutate,label)=>{const fields=clone();mutate(fields.find(f=>f.id==='rccm'));assert.throws(()=>assertPublishable(fields),label);assert.throws(()=>renderLegalMain('fr',approvedContact,fields),label);};
refuse(f=>{f.value='GN.TCC.2026.B.00001';},'value without confirmation');
refuse(f=>{confirm(f,'GN.TCC.2026.B.00001');f.source='';},'missing source');
refuse(f=>{confirm(f,'GN.TCC.2026.B.00001');f.validatedBy='';},'missing validator');
for(const bad of ['TODO','XXX','à confirmer','To be confirmed','placeholder','0000','GN.TCC.XXXX'])refuse(f=>confirm(f,bad),'placeholder '+bad);
refuse(f=>{f.confirmed=true;},'confirmed without value');
assert.throws(()=>assertPublishable([...clone(),{...clone()[0]}]),'duplicate id');

// 3. Rendering: pending items are explicit, never fake identifiers.
for(const lang of ['fr','en']){
 const legal=renderLegalMain(lang),privacy=renderPrivacyMain(lang);
 for(const html of [legal,privacy]){
  assert.equal([...html.matchAll(/<h1\b/g)].length,1);
  assert(html.includes('id="main" tabindex="-1"'));
  assert(html.includes('role="note"'),'incomplete banner');
  assert(!/GN\.TCC|RCCM\s*:?\s*[A-Z]{2}[.\-]?\d|NIF\)?\s*:?\s*\d|[Cc]apital(?: social)?\s*:?\s*\d|\b\d{6,}\b/.test(html),'no legal identifier may appear');
  assert(html.includes('mailto:'+approvedContact));
 }
 assert.equal([...legal.matchAll(/data-legal-pending="/g)].length,legalFields.filter(f=>['publisher','host'].includes(f.section)).length);
 for(const f of legalFields.filter(f=>f.section!=='privacy'))assert(legal.includes('data-legal-pending="'+f.id+'"'));
 assert(legal.includes('href="'+legalPaths[lang].privacy+'"'));assert(privacy.includes('href="'+legalPaths[lang].legal+'"'));
 assert(!/SQLite|Resend|recette locale|test mailbox|boîte de test/i.test(privacy),'public privacy must not describe REC processing');
 assert(/REC/.test(privacy),'public privacy must state REC separation');
}

// 4. Fully confirmed fixture: values shown, banner removed, readiness complete.
const full=clone();full.forEach((f,i)=>confirm(f,'Validated value '+i));
assert.deepEqual(legalReadiness(full),{complete:true,missing:[]});
const fullHtml=renderLegalMain('fr',approvedContact,full);
assert(!fullHtml.includes('role="note"'));assert(!fullHtml.includes('data-legal-pending'));assert(fullHtml.includes('Validated value 3'));

// 5. REC static sources stay in sync with the single legal source and remain noindex.
assert.equal(readDist('mentions-legales.html'),renderLegalPage('fr'),'run: node scripts/legal-content.mjs --write-dist');
assert.equal(readDist('legal-en.html'),renderLegalPage('en'),'run: node scripts/legal-content.mjs --write-dist');
for(const name of ['mentions-legales.html','legal-en.html','confidentialite.html','privacy-en.html']){
 const html=readDist(name);
 assert(html.includes('content="noindex,nofollow"'));assert(html.includes('class="skip-link"'));assert(html.includes('accessibility.css'));
 assert.match(html,/<html lang="(fr|en)">/);
}
assert(/environnement de recette \(REC\)/.test(readDist('confidentialite.html')));
assert(/Test environment \(REC\)/.test(readDist('privacy-en.html')));
for(const [name,link] of [['index.html','mentions-legales.html'],['expertise.html','mentions-legales.html'],['confidentialite.html','mentions-legales.html'],['en.html','legal-en.html'],['expertise-en.html','legal-en.html'],['privacy-en.html','legal-en.html']])
 assert(readDist(name).includes('href="'+link+'"'),name+' footer must link '+link);

// 6. Public export: 96 indexable pages preserved, notices excluded from sitemap, all internal links resolve.
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'dsig-legal-test-'));
try{
 const out=path.join(tmp,'site'),count=build(out,approvedContact);
 const read=name=>fs.readFileSync(path.join(out,name),'utf8');
 assert.equal(count,120,'indexable public pages must match the 120 approved pages');
 const sitemap=read('sitemap.xml');
 for(const lang of ['fr','en'])for(const kind of ['legal','privacy']){
  const url=legalPaths[lang][kind],html=read(url.slice(1));
  assert(!sitemap.includes(url),url+' must stay out of the sitemap');
  assert(html.includes('content="noindex,nofollow"'));assert(!html.includes('index,follow'));
  assert.match(html,new RegExp('<html lang="'+lang+'">'));
  assert.equal([...html.matchAll(/<h1\b/g)].length,1);
  assert(html.includes(kind==='legal'?renderLegalMain(lang):renderPrivacyMain(lang)));
  assert(!/SQLite|Resend|données fictives|fictional data/i.test(html),url+' exposes REC wording');
 }
 const html=fs.readdirSync(out).filter(n=>n.endsWith('.html'));
 const sample=['index.html','en.html','blog.html','blog-en.html','secteurs.html','sectors.html','offres.html','offers.html',html.find(n=>/^expertise-(?!en-)/.test(n)),html.find(n=>n.startsWith('expertise-en-'))];
 for(const name of sample){
  const page=read(name),en=/lang="en"/.test(page.slice(0,200));
  for(const kind of ['legal','privacy']){const target=legalPaths[en?'en':'fr'][kind];assert(page.includes('href="'+target+'"')||page.includes('href="'+target.slice(1)+'"'),name+' must link '+target);}
 }
 for(const name of html){
  for(const [,href] of read(name).matchAll(/href="([^"#?:]+\.html)(?:[#?][^"]*)?"/g)){
   const target=href==='/'?'index.html':href.replace(/^\//,'');
   assert(fs.existsSync(path.join(out,target)),name+' links missing page '+href);
  }
 }
 for(const privateFile of ['accounts.html','connexion.html','admin.html','server.py','legal-content.mjs'])assert(!fs.existsSync(path.join(out,privateFile)));
}finally{fs.rmSync(tmp,{recursive:true,force:true});}
console.log('PASS: V161 legal notice and privacy, '+legalReadiness().missing.length+' legal items awaiting validation, publication blocked');
