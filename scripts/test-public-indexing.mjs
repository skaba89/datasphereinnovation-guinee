import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {build} from './build-public-site.mjs';
import {checkPublic} from './check-public-indexing.mjs';
const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'dsig-index-test-'));
try{
 const site=path.join(tmp,'site');const count=build(site,'contact@datasphere-innovation.net');
 let fault='';
 const mock=async url=>{
  const u=new URL(url);assert(['dsig-consulting.com','rec.dsig-consulting.com'].includes(u.hostname));
  if(u.hostname.startsWith('rec.'))return new Response('',{status:fault==='rec'?200:403});
  if(fault==='private'&&u.pathname==='/accounts.html')return new Response('private');
  const file=path.join(site,u.pathname==='/'?'index.html':u.pathname.slice(1));
  if(!fs.existsSync(file))return new Response('',{status:404});
  let body=fs.readFileSync(file,'utf8');
  if(fault==='sitemap'&&u.pathname==='/sitemap.xml')body=body.replace('https://dsig-consulting.com/','https://evil.example/');
  return new Response(body,{headers:{'content-type':file.endsWith('.html')?'text/html':'text/plain','x-robots-tag':fault==='noindex'&&u.pathname==='/'?'noindex':'index'}});
 };
 const good=await checkPublic(mock);assert.equal(good.status,'PASS');assert.equal(good.pages_checked,count);
 for(const scenario of ['rec','private','sitemap','noindex']){fault=scenario;assert.equal((await checkPublic(mock)).status,'FAIL',scenario);}
 console.log('PASS: publication checks and negative cases');
}finally{fs.rmSync(tmp,{recursive:true,force:true});}
