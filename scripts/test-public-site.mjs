import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {build} from './build-public-site.mjs';

const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'dsig-public-test-'));
const out=path.join(tmp,'site');
try{
 assert.throws(()=>build(out,'invalid'));
 const count=build(out,'test@dsig-consulting.com');
 const files=fs.readdirSync(out);
 const read=name=>fs.readFileSync(path.join(out,name),'utf8');
 assert.throws(()=>build(out,'test@dsig-consulting.com'));
 for(const privateFile of ['accounts.html','accounts.js','admin.html','connexion.html','billing.html','app.js','server.py','expertise.js'])assert(!files.includes(privateFile));
 assert(!read('robots.txt').includes('Disallow: /'));
 const urls=[...read('sitemap.xml').matchAll(/<loc>https:\/\/dsig-consulting\.com([^<]*)<\/loc>/g)].map(m=>m[1]);
 assert.equal(urls.length,count);assert.equal(new Set(urls).size,count);assert(count>=60);
 for(const url of urls){
  const html=read(url==='/'?'index.html':url.slice(1));
  assert(html.includes('content="index,follow,max-image-preview:large"'));
  assert(!html.includes('noindex'));
  assert(html.includes('rel="canonical" href="https://dsig-consulting.com'+url+'"'));
  for(const match of html.matchAll(/hreflang="(?:fr|en|x-default)" href="https:\/\/dsig-consulting\.com([^"]+)"/g))assert(urls.includes(match[1]));
  assert.match(html,/<h1[^>]*>[^<]+/);
  assert(!html.includes('/api/requests'));
  assert(!html.includes('<form'));
 }
 for(const name of ['index.html','en.html']){
  const html=read(name);
  assert(html.includes('mailto:test@dsig-consulting.com'));
  assert.equal([...html.matchAll(/href="\/expertise-[^"]+"/g)].length,(count-2)/2);
 }
 assert(fs.readFileSync(new URL('../dist/robots.txt',import.meta.url),'utf8').includes('Disallow: /'));
 assert(fs.readFileSync(new URL('../dist/index.html',import.meta.url),'utf8').includes('noindex,nofollow'));
 console.log('PASS: public SEO export, '+count+' indexable pages, REC unchanged');
}finally{fs.rmSync(tmp,{recursive:true,force:true});}
