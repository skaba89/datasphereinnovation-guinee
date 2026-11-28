import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {gzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {build} from './build-public-site.mjs';
import {posts} from './blog-content.mjs';
import {sectors} from './sector-content.mjs';
import {offers} from './offer-content.mjs';
import {loadReferenceLogos,renderReferenceLogos,referenceBrands} from './reference-logos.mjs';

const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'dsig-public-test-'));
const out=path.join(tmp,'site');
try{
 const fixture=path.join(tmp,'logo-fixture');fs.mkdirSync(path.join(fixture,'reference-logos'),{recursive:true});
 const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aW1sAAAAASUVORK5CYII=','base64');
 const entry={id:'keyrus',sourceUrl:'https://example.invalid/logo.png',sha256:createHash('sha256').update(png).digest('hex')};
 const writeManifest=entries=>fs.writeFileSync(path.join(fixture,'reference-logos.json'),JSON.stringify(entries));
 fs.writeFileSync(path.join(fixture,'reference-logos','keyrus.png'),png);
 writeManifest([entry]);const logos=loadReferenceLogos(fixture);
 const markup='<article><strong>Keyrus</strong><span>Analytics</span></article>';
 assert(renderReferenceLogos(markup,logos).includes('src="/reference-logos/keyrus.png" alt=""'));
 assert.equal(renderReferenceLogos(markup,[]),markup);
 assert.throws(()=>renderReferenceLogos(markup+markup,logos));
 writeManifest([entry,entry]);assert.throws(()=>loadReferenceLogos(fixture));
 writeManifest([{...entry,sha256:'0'.repeat(64)}]);assert.throws(()=>loadReferenceLogos(fixture));
 writeManifest([{...entry,id:'../secret'}]);assert.throws(()=>loadReferenceLogos(fixture));
 assert.equal(Object.keys(referenceBrands).length,13);
 assert.throws(()=>build(out,'invalid'));
 assert.throws(()=>build(out,'contact@datasphere-innovation.net'));
 assert.throws(()=>build(out,'contact@example.invalid'));
 const count=build(out,'contact@dsig-consulting.com');
 const files=fs.readdirSync(out);
 const read=name=>fs.readFileSync(path.join(out,name),'utf8');
 for(const name of files.filter(n=>n.endsWith('.html'))){
  const html=read(name),styles=[...html.matchAll(/<link rel="stylesheet" href="\/([^"/]+)">/g)];
  assert.equal(styles.length,1,name+' must request one stylesheet');
  const css=read(styles[0][1]);
  assert.equal(styles[0][1],'public-'+createHash('sha256').update(css).digest('hex').slice(0,16)+'.css');
  assert(gzipSync(css).length<=14*1024,name+' CSS gzip budget');
  assert(gzipSync(html).length<=12*1024,name+' HTML gzip budget');
  assert(!/<script src=/.test(html),name+' has blocking JavaScript');
  // Static accessibility checks for the generated public documents only.
  assert(/^<!doctype html>/i.test(html),name+' missing HTML doctype');
  assert(/<html lang="(?:fr|en)"/.test(html),name+' missing document language');
  const mainTags=[...html.matchAll(/<main\b[^>]*>/g)];
  assert.equal(mainTags.length,1,name+' must have one main landmark');
  const mainId=mainTags[0][0].match(/\bid="([^"]+)"/)?.[1];
  assert(mainId,name+' missing main identifier');
  assert(/\btabindex="-1"/.test(mainTags[0][0]),name+' main is not programmatically focusable');
  const skip=html.match(/<a class="skip-link" href="#([^"]+)">([^<]+)<\/a>/);
  assert(skip&&skip[1]===mainId&&skip[2].trim(),name+' invalid skip link');
  const ids=[...html.matchAll(/<[a-z][^>]*\sid="([^"]+)"/gi)].map(m=>m[1]);
  assert.equal(new Set(ids).size,ids.length,name+' duplicate element IDs');
  assert.equal([...html.matchAll(/<h1\b[^>]*>/gi)].length,1,name+' must have one H1');
  assert(!/<meta[^>]+(?:user-scalable=no|maximum-scale=1(?:[,"]))/i.test(html),name+' disables user zoom');
  // Static performance safeguards: no claim about measured browser Core Web Vitals.
  const scripts=[...html.matchAll(/<script\b[^>]*\bsrc="([^"]+)"[^>]*>/g)];
  for(const [,src] of scripts){
   assert(/^(?:\/)?[a-z0-9-]+\.js$/.test(src),name+' unexpected external script '+src);
   assert(fs.existsSync(path.join(out,src)),name+' missing script '+src);
  }
  const images=[...html.matchAll(/<img\b[^>]*>/g)];
  for(const [tag] of images){
   const src=tag.match(/\bsrc="([^"]+)"/)?.[1];
   assert(src&& !/^(?:[a-z]+:|\/\/)/i.test(src),name+' external or missing image');
   assert(fs.existsSync(path.join(out,src)),name+' missing image '+src);
   assert(/\balt="[^"]*"/.test(tag),name+' missing image alt');
  }
  const transferBytes=gzipSync(html).length+gzipSync(css).length+
   [...new Set(scripts.map(m=>m[1]))].reduce((sum,src)=>sum+gzipSync(fs.readFileSync(path.join(out,src))).length,0);
  assert(transferBytes<=32*1024,name+' combined HTML/CSS/JS gzip budget: '+transferBytes);

  for(const match of css.matchAll(/url\(['"]?([^'"\)]+)['"]?\)/g))assert(fs.existsSync(path.join(out,match[1])),name+' missing CSS asset');
 }
 for(const name of ['index.html','en.html']){
  assert(read(name).includes('width="720" height="560" fetchpriority="high"'));
  assert(read(name).includes('loading="lazy" decoding="async"'));
  const html=read(name);
  assert(!/Offres de prestations à cadrer|Compétences issues des missions|Références issues du parcours|Services are scoped according|Skills drawn from the founder|References from the founder/.test(html));
  assert(html.includes(name==='en.html'?'they are not contractual references or partnerships':'elles ne constituent pas des références contractuelles ou des partenariats'));
  assert.equal(html.split('class="public-reference-intro"').length,2);
  const sectorMega=html.match(/<details class="corporate-mega public-sector-mega">[\s\S]*?<\/details>/)?.[0];
  assert(sectorMega,name+' missing sector mega menu');
  for(const sector of sectors)assert(sectorMega.includes('href="/'+(name==='en.html'?'sectors':'secteurs')+'-'+sector.slug+'.html"'),name+' missing '+sector.slug);
  assert.equal([...sectorMega.matchAll(/<a href=/g)].length,sectors.length);
  assert(!fs.readFileSync(new URL('../dist/'+name,import.meta.url),'utf8').includes('public-sector-mega'));

  assert.equal([...html.matchAll(/class="public-tech-benefit"/g)].length,6);
  assert(html.includes(name==='en.html'?'Brand names do not imply a vendor partnership.':'Les marques citées n’impliquent aucun partenariat éditeur.'));
  assert(html.includes(name==='en.html'?'Discuss your technical requirements':'Échanger sur vos besoins techniques'));
  assert(!fs.readFileSync(new URL('../dist/'+name,import.meta.url),'utf8').includes('public-tech-benefit'));
  assert.equal(html.split('class="public-commercial-journey"').length,2);
  const journey=html.match(/<div class="public-commercial-journey">[\s\S]*?<\/div><\/div><div class="contact">/)?.[0];
  assert(journey,'Missing public commercial journey');
  for(const slug of ['conseil-audit','regie','forfait','saas'])assert(journey.includes('href="/'+(name==='en.html'?'offers':'offres')+'-'+slug+'.html"'));
  assert(!fs.readFileSync(new URL('../dist/'+name,import.meta.url),'utf8').includes('public-commercial-journey'));

  assert.equal(html.split('class="public-reference-action"').length,2);
  assert(html.includes(name==='en.html'?'Discuss a similar challenge':'Échanger sur un enjeu similaire'));
  assert(!fs.readFileSync(new URL('../dist/'+name,import.meta.url),'utf8').includes('public-reference-intro'));
  const referenceSection=html.match(/<section class="section references" id="references">[\s\S]*?<\/section>/)?.[0];
  assert(referenceSection);
  assert.equal([...referenceSection.matchAll(/<article(?:\s|>)/g)].length,13);

  assert(html.includes('class="corporate-institution-grid"'));
  assert(html.includes('class="corporate-leadership-grid"'));
  for(const person of ['Moussa KABA','Sekouna KABA'])assert.equal(html.split('<h4>'+person+'</h4>').length,2);
  assert(html.includes(name==='en.html'?'Co-founder · Managing Director':'Cofondateur · Directeur général'));
  assert(html.includes(name==='en.html'?'Co-founder · Data, AI and IT architecture expert':'Cofondateur · Expert Data, IA et architecture SI'));
  for(const label of name==='en.html'?['Our mission','Our ambition','Our commitments']:['Notre mission','Notre ambition','Nos engagements'])assert(html.includes('<h4>'+label+'</h4>'));
 }
 assert(fs.statSync(path.join(out,'digital-mockup.svg')).size<=8*1024);
 assert(fs.statSync(path.join(out,'hero-image.webp')).size<=180*1024);
 assert(gzipSync(read('icons.js')).length+gzipSync(read('public-menu.js')).length<=4*1024);
 assert.throws(()=>build(out,'test@dsig-consulting.com'));
 for(const privateFile of ['client-portal.html','client-portal.js','accounts.html','accounts.js','admin.html','connexion.html','billing.html','app.js','server.py','expertise.js'])assert(!files.includes(privateFile));
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
  assert.equal(org.email,'contact@dsig-consulting.com');
  assert(org.areaServed.some(a=>a.name==='Conakry'));
  assert(!org.address&&!org.telephone&&!org.aggregateRating);
  assert(!graph.some(n=>n['@type']==='LocalBusiness'));
  const page=graph.find(n=>n['@type']==='WebPage');
  assert.equal(page.url,'https://dsig-consulting.com'+url);
  if(url!=='/'&&url!=='/en.html'){
   const header=html.match(/<header class="public-editorial-header">[\s\S]*?<\/header>/)?.[0];
   assert(header,'Missing public editorial header '+url);
   const en=html.includes('<html lang="en"');
   for(const target of [en?'/en.html#services':'/#services',en?'/offers.html':'/offres.html',en?'/sectors.html':'/secteurs.html',en?'/blog-en.html':'/blog.html',en?'/en.html#contact':'/#contact'])assert(header.includes('href="'+target+'"'),url+' missing '+target);
   assert(html.includes('<footer class="public-editorial-footer">'));
  }
  if(url.startsWith('/expertise-')){
   assert(html.includes('class="corporate-expertise"'));
   assert(html.includes('class="expertise-grid corporate-expertise-grid"'));
   for(const id of ['benefit','scope','deliverables'])assert(new RegExp('id="'+id+'">[^<]+').test(html));
   assert.equal([...html.matchAll(/<h2>/g)].length,3);
   const service=graph.find(n=>n['@type']==='Service');
   assert.equal(service.provider['@id'],org['@id']);
   assert.equal(page.mainEntity['@id'],service['@id']);
   const breadcrumb=graph.find(n=>n['@type']==='BreadcrumbList');
   assert.equal(breadcrumb.itemListElement[1].item,page.url);
   assert(html.includes('aria-current="page"'));
  }
  if(url.startsWith('/blog-')&&url!=='/blog-en.html'){
   assert(html.includes('class="policy sector-detail public-blog-article"'));
   assert.equal([...html.matchAll(/class="sector-insight"/g)].length,3);
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
  assert(html.includes('mailto:contact@dsig-consulting.com'));
  assert.equal([...html.matchAll(/href="\/expertise-[^"]+"/g)].length,urls.filter(u=>u.startsWith('/expertise-')).length/2);
  assert(html.includes('href="'+(name==='en.html'?'/blog-en.html':'/blog.html')+'"'));
 }
 assert.equal(urls.filter(u=>u.startsWith('/blog')).length,2+posts.length*2);
 assert.equal(urls.filter(u=>/^\/sect(?:eurs|ors)[.-]/.test(u)).length,2+sectors.length*2);
 for(const lang of ['fr','en']){
  const prefix=lang==='en'?'sectors':'secteurs',other=lang==='en'?'secteurs':'sectors';
  assert(read(lang==='en'?'en.html':'index.html').includes('href="/'+prefix+'.html"'));
  const index=read(prefix+'.html');
  assert(index.includes('class="expertise-grid sector-directory"'));
  assert.equal([...index.matchAll(/class="service-link"/g)].length,sectors.length);
  assert(index.includes('class="sector-intro sector-contact"'));
  for(const sector of sectors){
   const url='/'+prefix+'-'+sector.slug+'.html',alternate='/'+other+'-'+sector.slug+'.html';
   assert(urls.includes(url));assert(urls.includes(alternate));
   assert(index.includes('href="'+url+'"'));
   const html=read(url.slice(1));
   assert(html.includes('class="policy sector-detail"'));
   assert.equal([...html.matchAll(/class="sector-insight"/g)].length,sector[lang].sections.length);
   assert(html.includes('href="'+alternate+'" hreflang="'+(lang==='en'?'fr':'en')+'"'));
   assert(html.includes('href="/'+prefix+'.html"'));
   assert.equal([...html.matchAll(/<h1\b/g)].length,1);
   assert(html.includes('mailto:contact@dsig-consulting.com'));
   for(const slug of sector.expertise)assert(html.includes('href="/expertise-'+(lang==='en'?'en-':'')+slug+'.html"'));
  }
 }
 for(const post of posts)for(const lang of ['fr','en']){
  const index=read(lang==='en'?'blog-en.html':'blog.html');
  assert(index.includes('class="expertise-grid sector-directory public-blog-directory"'));
  assert.equal([...index.matchAll(/class="service-link"/g)].length,posts.length);
  assert(index.includes('href="/blog'+(lang==='en'?'-en':'')+'-'+post.slug+'.html"'));
 }
 assert.equal(urls.filter(u=>/^\/(offres|offers)[.-]/.test(u)).length,2+offers.length*2);
 for(const lang of ['fr','en']){
  const prefix=lang==='fr'?'offres':'offers',other=lang==='fr'?'offers':'offres';
  const directory=read(prefix+'.html');
  assert(directory.includes('class="expertise-grid sector-directory offer-directory"'));
  assert.equal([...directory.matchAll(/class="service-link"/g)].length,offers.length);
  assert(read(lang==='fr'?'index.html':'en.html').includes('href="/'+prefix+'.html"'));
  for(const offer of offers){
   const url='/'+prefix+'-'+offer.slug+'.html',html=read(url.slice(1));
   assert(urls.includes(url));assert(read(prefix+'.html').includes('href="'+url+'"'));
   assert(html.includes('class="policy sector-detail offer-detail"'));
   assert.equal([...html.matchAll(/class="sector-insight"/g)].length,2);
   assert(html.includes('href="/'+other+'-'+offer.slug+'.html" hreflang='));
   assert(html.includes('mailto:contact@dsig-consulting.com?subject='));
   if(offer.slug==='saas')assert.equal([...html.matchAll(/mailto:contact@dsig-consulting.com\?subject=/g)].length,2);
  }
 }
 for(const name of files.filter(n=>n.endsWith('.html')))assert(!/MineFleet360|MakitiPlus|Gestion Scolaire Pro|Kora Finance|Guinée Logistique/.test(read(name)),name+' exposes internal catalogue');
 assert(fs.readFileSync(new URL('../dist/robots.txt',import.meta.url),'utf8').includes('Disallow: /'));
 assert(fs.readFileSync(new URL('../dist/index.html',import.meta.url),'utf8').includes('noindex,nofollow'));
 console.log('PASS: public SEO export, '+count+' indexable pages, REC unchanged');
}finally{fs.rmSync(tmp,{recursive:true,force:true});}

// Dockerfile.public: every RUN continuation must be a real line break (a literal backslash-n
// once slipped in and passed a stray argument to a test script), and every public test must run.
// Checked from the repository (CI "node tests" step); the Dockerfile is not copied into the image.
const dockerfile=new URL('../Dockerfile.public',import.meta.url);
if(fs.existsSync(dockerfile)){
 const docker=fs.readFileSync(dockerfile,'utf8');
 assert(!/\\n[ \t]+&&/.test(docker),'Dockerfile.public: literal backslash-n in a RUN continuation');
 for(const test of ['test-public-site','test-public-indexing','test-legal-compliance'])
  assert(docker.includes('node scripts/'+test+'.mjs'),'Dockerfile.public must run '+test);
}
