import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {build} from './build-public-site.mjs';
import {posts} from './blog-content.mjs';
import {sectors} from './sector-content.mjs';

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
  const match=html.match(/<script type="application\/ld\+json">([^<]+)<\/script>/);
  assert(match,'Missing structured data '+url);
  const schema=JSON.parse(match[1]),graph=schema['@graph'];
  assert.equal(schema['@context'],'https://schema.org');
  const org=graph.find(n=>n['@type']==='Organization');
  assert.equal(org['@id'],'https://dsig-consulting.com/#organization');
  assert.equal(org.email,'test@dsig-consulting.com');
  assert(org.areaServed.some(a=>a.name==='Conakry'));
  assert(!org.address&&!org.telephone&&!org.aggregateRating);
  assert(!graph.some(n=>n['@type']==='LocalBusiness'));
  const page=graph.find(n=>n['@type']==='WebPage');
  assert.equal(page.url,'https://dsig-consulting.com'+url);
  if(url.startsWith('/expertise-')){
   const service=graph.find(n=>n['@type']==='Service');
   assert.equal(service.provider['@id'],org['@id']);
   assert.equal(page.mainEntity['@id'],service['@id']);
   const breadcrumb=graph.find(n=>n['@type']==='BreadcrumbList');
   assert.equal(breadcrumb.itemListElement[1].item,page.url);
   assert(html.includes('aria-current="page"'));
  }
  if(url.startsWith('/blog-')&&url!=='/blog-en.html'){
   const article=graph.find(n=>n['@type']==='BlogPosting');
   assert(article);
   assert.equal(article.author['@id'],org['@id']);
   assert.equal(page.mainEntity['@id'],article['@id']);
   assert(html.includes('property="og:type" content="article"'));
   assert(html.includes('<article'));
   assert(urls.some(u=>u.startsWith('/expertise-')&&html.includes('href="'+u+'"')));
  }
 }
 for(const name of ['index.html','en.html']){
  const html=read(name);
  assert(html.includes('mailto:test@dsig-consulting.com'));
  assert.equal([...html.matchAll(/href="\/expertise-[^"]+"/g)].length,urls.filter(u=>u.startsWith('/expertise-')).length/2);
  assert(html.includes('href="'+(name==='en.html'?'/blog-en.html':'/blog.html')+'"'));
 }
 assert.equal(urls.filter(u=>u.startsWith('/blog')).length,2+posts.length*2);
 assert.equal(urls.filter(u=>/^\/sect(?:eurs|ors)[.-]/.test(u)).length,2+sectors.length*2);
 for(const lang of ['fr','en']){
  const prefix=lang==='en'?'sectors':'secteurs',other=lang==='en'?'secteurs':'sectors';
  assert(read(lang==='en'?'en.html':'index.html').includes('href="/'+prefix+'.html"'));
  const index=read(prefix+'.html');
  for(const sector of sectors){
   const url='/'+prefix+'-'+sector.slug+'.html',alternate='/'+other+'-'+sector.slug+'.html';
   assert(urls.includes(url));assert(urls.includes(alternate));
   assert(index.includes('href="'+url+'"'));
   const html=read(url.slice(1));
   assert(html.includes('href="'+alternate+'" hreflang="'+(lang==='en'?'fr':'en')+'"'));
   assert(html.includes('href="/'+prefix+'.html"'));
   assert.equal([...html.matchAll(/<h1\b/g)].length,1);
   assert(html.includes('mailto:test@dsig-consulting.com'));
   for(const slug of sector.expertise)assert(html.includes('href="/expertise-'+(lang==='en'?'en-':'')+slug+'.html"'));
  }
 }
 for(const post of posts)for(const lang of ['fr','en']){
  const index=read(lang==='en'?'blog-en.html':'blog.html');
  assert(index.includes('href="/blog'+(lang==='en'?'-en':'')+'-'+post.slug+'.html"'));
 }
 assert(fs.readFileSync(new URL('../dist/robots.txt',import.meta.url),'utf8').includes('Disallow: /'));
 assert(fs.readFileSync(new URL('../dist/index.html',import.meta.url),'utf8').includes('noindex,nofollow'));
 console.log('PASS: public SEO export, '+count+' indexable pages, REC unchanged');
}finally{fs.rmSync(tmp,{recursive:true,force:true});}
