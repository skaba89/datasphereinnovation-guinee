// V175: public contact form is only built with validated legal data; Caddy route only when enabled.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {build} from './build-public-site.mjs';
import {legalFields} from './legal-content.mjs';
import {publicCaddyfile,contactUpstream} from './public-caddyfile.mjs';

const email='contact@datasphere-innovation.net';
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'dsig-public-form-'));
const caddy=fs.readFileSync(new URL('../deploy/public/Caddyfile',import.meta.url),'utf8');
try{
 // 1. Real legal data is incomplete: the form build must be refused, the default build must not contain it.
 assert.throws(()=>build(path.join(tmp,'refused'),email,{form:true}),/legal information is incomplete/);
 build(path.join(tmp,'default'),email);
 const plain=name=>fs.readFileSync(path.join(tmp,'default',name),'utf8');
 for(const page of ['index.html','en.html']){
  assert(!plain(page).includes('id="request"'),page+': no form by default');
  assert(plain(page).includes('href="mailto:'+email+'"'));
  assert(!plain(page).includes('public-contact.js'));
 }
 assert(!fs.existsSync(path.join(tmp,'default','public-contact.js')));
 assert(plain('confidentialite.html').includes('ne contient aucun formulaire'));

 // 2. With (fictitious, test-only) validated legal data, the form is rendered in FR and EN.
 const validated=legalFields.map(f=>({...f,value:'Valeur validée '+f.id,confirmed:true,source:'Pièce officielle de recette',validatedBy:'Validateur de recette'}));
 build(path.join(tmp,'form'),email,{form:true,fields:validated});
 const read=name=>fs.readFileSync(path.join(tmp,'form',name),'utf8');
 const needs=['Demande de devis','Demande de démonstration','Partenariat','Conseil &amp; expertise','Formation','Autre demande'];
 for(const [page,lang] of [['index.html','fr'],['en.html','en']]){
  const html=read(page),form=html.match(/<form id="request"[\s\S]*?<\/form>/)?.[0];
  assert(form,page+': form rendered');
  for(const name of ['nom','org','email','telephone','besoin','message','consent','website'])assert(form.includes('name="'+name+'"'),page+': '+name);
  assert.deepEqual([...form.matchAll(/<option value="([^"]+)"/g)].map(m=>m[1]),needs);
  assert(form.includes('pattern="\\+?[0-9][0-9 \\(\\)\\.\\-]{5,28}"'),page+': phone pattern');
  assert(form.includes('href="'+(lang==='en'?'/privacy-en.html':'/confidentialite.html')+'"'));
  assert(form.includes('class="request-honeypot" aria-hidden="true"'));
  assert(!/ on[a-z]+=|style="/.test(form),page+': CSP-safe markup');
  assert(html.includes('<script defer src="public-contact.js"></script>'));
  assert(!html.includes('app.js')&&!html.includes('/api/requests'),page+': no REC code or API');
 }
 const script=read('public-contact.js');
 assert(script.includes("fetch('/api/contact'")&&script.includes("credentials:'omit'"));
 assert(!/https?:\/\//.test(script),'same-origin only');
 assert(read('confidentialite.html').includes('Formulaire de contact')&&read('confidentialite.html').includes('Valeur validée email_retention'));
 assert(read('privacy-en.html').includes('Contact form')&&read('privacy-en.html').includes('Valeur validée data_controller'));
 assert(!read('confidentialite.html').includes('ne contient aucun formulaire'));

 // 3. Caddyfile: unchanged when disabled; dedicated route, connect-src self and trusted proxies when enabled.
 const normalized=caddy.split('\r\n').join('\n');
 assert.equal(publicCaddyfile(caddy),normalized);
 assert(normalized.includes("connect-src 'none'")&&!normalized.includes('/api/contact'));
 const enabled=publicCaddyfile(caddy,'enabled');
 assert(enabled.includes("connect-src 'self'")&&!enabled.includes("connect-src 'none'"));
 assert(enabled.includes('reverse_proxy '+contactUpstream)&&enabled.includes('trusted_proxies static private_ranges'));
 assert(enabled.indexOf('handle @contact')<enabled.indexOf('@private path'),'contact route before the private 404 rule');
 assert(enabled.includes('method POST')&&enabled.includes('max_size 8KB'));
 assert.throws(()=>publicCaddyfile(caddy,'on'));
 assert.throws(()=>publicCaddyfile('no markers','enabled'));
 console.log('PASS: public contact form gated by legal validation, Caddy route only when enabled');
}finally{fs.rmSync(tmp,{recursive:true,force:true});}
