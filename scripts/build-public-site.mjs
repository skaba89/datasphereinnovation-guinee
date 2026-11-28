// Export only the public marketing site; never serve the REC bundle publicly.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {posts} from './blog-content.mjs';
import {sectors} from './sector-content.mjs';
import {offers,offerUseCases} from './offer-content.mjs';
import {publicSolutionFamilies} from './public-solution-families.mjs';
import {loadReferenceLogos,renderReferenceLogos} from './reference-logos.mjs';
import {renderLegalMain,renderPrivacyMain,legalPaths,legalFields,legalReadiness,approvedContact} from './legal-content.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const source=path.join(root,'dist');
const origin='https://dsig-consulting.com';
const read=name=>fs.readFileSync(path.join(source,name),'utf8');
const esc=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const context=vm.createContext({document:{documentElement:{lang:'fr'},querySelector:()=>null}});
const data=vm.runInContext(read('expertise.js')+'\n;({expertiseGroups,expertiseEnglishGroups,expertiseEnglish,expertiseDetails,expertiseId})',context);
const pages=[];
const assets=['style.css','brand.css','solutions.css','enterprise.css','premium.css','studio.css','consulting.css','identity.css','local-intake.css','expertise.css','accessibility.css','favicon.svg','dsig-mark.svg','digital-mockup.svg','waves.svg','hero-image.webp','sphere.svg','icons.js','fonts/open-sans-Regular.woff','fonts/open-sans-Semibold.woff','fonts/open-sans-Bold.woff','fonts/open-sans-ExtraBold.woff','fonts/LICENSE.txt'];

function metadata(html,title,description,fr,en,lang){
 const canonical=lang==='fr'?fr:en;
 const tags=[
  '<meta name="robots" content="index,follow,max-image-preview:large">',
  '<meta name="description" content="'+esc(description)+'">',
  '<link rel="canonical" href="'+origin+canonical+'">',
  ...[['fr',fr],['en',en],['x-default',fr]].map(([l,u])=>'<link rel="alternate" hreflang="'+l+'" href="'+origin+u+'">'),
  ...Object.entries({'og:title':title,'og:description':description,'og:type':'website','og:url':origin+canonical,'og:image':origin+'/hero-image.webp','og:locale':lang==='fr'?'fr_FR':'en_US'}).map(([k,v])=>'<meta property="'+k+'" content="'+esc(v)+'">'),
  '<meta name="twitter:card" content="summary_large_image">'
 ].join('\n');
 return html.replace(/<title>[^<]*<\/title>/,'<title>'+esc(title)+'</title>')
  .replace(/<meta name="(?:robots|description)"[^>]*>/g,'')
  .replace('</head>',tags+'\n</head>');
}
function put(out,name,content){fs.writeFileSync(path.join(out,name),content);}
// Bundle in original cascade order, at the same directory depth as the source CSS.
function optimizePublicPages(out){
 for(const name of fs.readdirSync(out).filter(n=>n.endsWith('.html'))){
  const file=path.join(out,name);let html=fs.readFileSync(file,'utf8');
  // Harmonize generated editorial pages only; never alter the REC templates or legal notices.
  const editorial=/^(expertise-|blog(?:-|\.)|secteurs(?:-|\.)|sectors(?:-|\.)|offres(?:-|\.)|offers(?:-|\.))/.test(name);
  if(editorial){
   const lang=html.match(/<html lang="(fr|en)"/)?.[1];
   if(!lang)throw Error('Missing editorial language: '+name);
   const en=lang==='en',other=en?'fr':'en';
   const alternate=html.match(new RegExp('<a href="([^"]+)" hreflang="'+other+'">'))?.[1];
   if(!alternate)throw Error('Missing editorial language switch: '+name);
   const links=[[home(lang)+'#services',en?'Expertise':'Expertises'],[offerPath(lang),en?'Services':'Nos offres'],[sectorPath(lang),en?'Industries':'Secteurs'],[blogPath(lang),'Blog'],[home(lang)+'#contact',en?'Contact':'Contact']];
   const markup=links.map(([url,label])=>'<a href="'+esc(url)+'">'+esc(label)+'</a>').join('');
   const header='<header class="public-editorial-header"><a class="brand" href="'+home(lang)+'"><img src="/dsig-mark.svg" width="100" height="40" alt="DSIG"></a><nav aria-label="'+(en?'Main navigation':'Navigation principale')+'">'+markup+'<a href="'+esc(alternate)+'" hreflang="'+other+'">'+(en?'Français':'English')+'</a></nav></header>';
   // Keep the existing footer wording and legal links, including the company status notice.
   html=html.replace(/<header class="nav">[\s\S]*?<\/header>/,()=>header).replace('<footer>','<footer class="public-editorial-footer">');
  }
  const styles=[...html.matchAll(/<link rel="stylesheet" href="\/?([a-z-]+\.css)">/g)];
  if(!styles.length)throw Error('Missing public styles: '+name);
  let css=styles.map(m=>read(m[1])).join('\n')+(['index.html','en.html'].includes(name)?'\n.corporate-premium .public-reference-intro{max-width:72ch;color:#42566e;font-size:16px;line-height:1.7}.corporate-premium .public-reference-action{margin-top:24px}.corporate-premium .references .footnote{border-left:3px solid #1249a0;padding:12px 16px;background:#f3f6fa;color:#42566e}.public-commercial-journey{margin-bottom:32px}.public-commercial-journey h3{font-size:20px;color:#08182f;margin:0 0 12px}.public-commercial-journey .expertise-grid{grid-template-columns:repeat(2,minmax(0,1fr))}@media(max-width:580px){.public-commercial-journey .expertise-grid{grid-template-columns:1fr}}':'');
  if(editorial)css+='\n.public-editorial-header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;padding:16px 5%;background:#08182f;color:white}.public-editorial-header nav{position:static;display:flex;flex-wrap:wrap;gap:12px 20px;background:transparent;padding:0;border:0;color:white;flex:1;justify-content:flex-end}.public-editorial-header nav a{color:white;padding:8px 0;line-height:1.5}.public-editorial-header nav a:hover{color:#83e4d8}.public-editorial-footer{background:#08182f;color:#d4dfec}.public-editorial-footer a{color:white;text-decoration:underline}@media(max-width:700px){.public-editorial-header nav{flex-basis:100%;justify-content:flex-start;gap:4px 16px}.public-editorial-header nav a{min-height:44px;display:flex;align-items:center}}';
  if(['index.html','en.html'].includes(name))css+='\n.corporate-premium .references .ref-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.corporate-premium .references .ref-grid article{display:flex;flex-direction:column;justify-content:center;gap:10px;min-width:0;min-height:120px;padding:20px;background:#fff;border:1px solid #dce5ef;border-radius:12px;overflow-wrap:anywhere}.corporate-premium .references .ref-grid.recent article{border-top:3px solid #008f8a}.corporate-premium .references .ref-grid article strong{color:#08182f;font-size:17px;line-height:1.35}.corporate-premium .references .ref-grid article span{color:#42566e;font-size:14px;line-height:1.6}.corporate-premium .references .reference-logo{width:100%;height:64px;display:flex;align-items:center;justify-content:flex-start}.corporate-premium .references .reference-logo img{width:160px;max-width:100%;height:64px;object-fit:contain;object-position:left center}.corporate-premium .references .ref-heading{color:#08182f;margin-top:28px}@media(max-width:900px){.corporate-premium .references .ref-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:480px){.corporate-premium .references .ref-grid{grid-template-columns:1fr}.corporate-premium .references .ref-grid article{min-height:0;padding:16px}}';
  const hash=createHash('sha256').update(css).digest('hex').slice(0,16);
  const bundle='public-'+hash+'.css';
  put(out,bundle,css);
  let first=true;
  html=html.replace(/<link rel="stylesheet" href="\/?[a-z-]+\.css">/g,()=>{
   if(!first)return '';first=false;return '<link rel="stylesheet" href="/'+bundle+'">';
  });
  html=html.replace(/<script src="(icons|public-menu)\.js">/g,'<script defer src="$1.js">');
  html=html.replace('<img src="digital-mockup.svg" alt="">','<img src="digital-mockup.svg" alt="" width="720" height="560" fetchpriority="high">');
  html=html.replace('<img src="dsig-mark.svg" alt="DSIG" width="124" height="45">','<img src="dsig-mark.svg" alt="DSIG" width="124" height="45" loading="lazy" decoding="async">');
  put(out,name,html);
 }
}
function publicPath(lang,slug){return '/expertise-'+(lang==='en'?'en-':'')+slug+'.html'}
function home(lang){return lang==='fr'?'/':'/en.html'}
const orgId=origin+'/#organization',siteId=origin+'/#website';
function structuredData(html,lang,url,title,description,contact,service=null,article=null){
 const en=lang==='en',canonical=origin+url;
 const areaServed=[{'@type':'City',name:'Conakry',containedInPlace:{'@type':'Country',name:en?'Guinea':'Guinée'}},
  {'@type':'Country',name:en?'Guinea':'Guinée'},{'@type':'Country',name:'France'}];
 const organization={'@type':'Organization','@id':orgId,name:'DataSphere Innovation Guinée',alternateName:'DSIG',url:origin+'/',logo:origin+'/dsig-mark.svg',email:contact,areaServed};
 const website={'@type':'WebSite','@id':siteId,name:'DataSphere Innovation Guinée',alternateName:'DSIG',url:origin+'/',publisher:{'@id':orgId},inLanguage:['fr','en']};
 const page={'@type':'WebPage','@id':canonical+'#webpage',url:canonical,name:title,description,inLanguage:lang,isPartOf:{'@id':siteId},about:{'@id':orgId}};
 const graph=[organization,website,page];
 if(service){
  const serviceId=canonical+'#service',breadcrumbId=canonical+'#breadcrumb';
  page.mainEntity={'@id':serviceId};page.breadcrumb={'@id':breadcrumbId};
  graph.push({'@type':'Service','@id':serviceId,name:service,serviceType:service,description,url:canonical,provider:{'@id':orgId},areaServed});
  graph.push({'@type':'BreadcrumbList','@id':breadcrumbId,itemListElement:[
   {'@type':'ListItem',position:1,name:en?'Home':'Accueil',item:origin+home(lang)},
   {'@type':'ListItem',position:2,name:service,item:canonical}
  ]});
 }
 if(article){
  const articleId=canonical+'#article',breadcrumbId=canonical+'#breadcrumb';
  page.mainEntity={'@id':articleId};page.breadcrumb={'@id':breadcrumbId};
  graph.push({'@type':'BlogPosting','@id':articleId,headline:article.title,description,
   inLanguage:lang,mainEntityOfPage:{'@id':page['@id']},author:{'@id':orgId},publisher:{'@id':orgId}});
  graph.push({'@type':'BreadcrumbList','@id':breadcrumbId,itemListElement:[
   {'@type':'ListItem',position:1,name:en?'Home':'Accueil',item:origin+home(lang)},
   {'@type':'ListItem',position:2,name:'Blog',item:origin+blogPath(lang)},
   {'@type':'ListItem',position:3,name:article.title,item:canonical}
  ]});
 }
 // Escape markup-breaking characters so JSON can never terminate its script tag.
 const json=JSON.stringify({'@context':'https://schema.org','@graph':graph}).replaceAll('<','\\u003c');
 return html.replace('</head>','<script type="application/ld+json">'+json+'</script>\n</head>');
}
const blogPath=(lang,slug='')=>'/blog'+(lang==='en'?'-en':'')+(slug?'-'+slug:'')+'.html';
const sectorPath=(lang,slug='')=>(lang==='en'?'/sectors':'/secteurs')+(slug?'-'+slug:'')+'.html';
const offerPath=(lang,slug='')=>(lang==='en'?'/offers':'/offres')+(slug?'-'+slug:'')+'.html';
function buildOffers(out,contact){
 for(const lang of ['fr','en']){
  const en=lang==='en',index=offerPath(lang),title=en?'Digital consulting and SaaS offers | DSIG':'Offres de conseil et SaaS en Guinée | DSIG',description=en?'Explore consulting, project delivery, training and business application options.':'Découvrez nos prestations de conseil, régie, forfait, formation et solutions métiers.';
  const request=(label,subject)=>'<a class="btn" href="mailto:'+esc(contact)+'?subject='+encodeURIComponent(subject)+'">'+esc(label)+'</a>';
  const note=en?'Scope, availability, price and timing are confirmed after review. Please do not send personal or sensitive data.':'Périmètre, disponibilité, prix et délais à confirmer après étude. Ne transmettez aucune donnée personnelle ou sensible.';
  const save=(slug,t,d,body)=>{const url=offerPath(lang,slug),fr=offerPath('fr',slug),english=offerPath('en',slug);put(out,url.slice(1),structuredData(metadata(blogTemplate(lang,body,en?fr:english),t,d,fr,english,lang),lang,url,t,d,contact));pages.push(url);};
  for(const offer of offers){const [name,desc,deliverables]=offer[lang];
   const examples=offerUseCases[offer.slug]?.[lang];
   if(!examples||examples.length!==3)throw Error('Missing public offer use cases: '+offer.slug);
   const solutionCatalogue=offer.slug==='saas'?'<div class="public-solution-catalogue"><h2>'+(en?'Business solution families':'Familles de solutions métiers')+'</h2><p>'+(en?'Indicative areas for assessment, not a list of available products.':'Domaines à étudier avec vous, et non un inventaire de produits disponibles.')+'</p><div class="expertise-grid sector-directory">'+publicSolutionFamilies.map(f=>{if(!sectors.some(sector=>sector.slug===f.sector))throw Error('Unknown solution sector: '+f.sector);const item=f[lang];return '<article><h3>'+esc(item.title)+'</h3><p><strong>'+(en?'For: ':'Pour : ')+ '</strong>'+esc(item.audience)+'</p><p>'+esc(item.benefit)+'</p><a class="service-link" href="'+sectorPath(lang,f.sector)+'">'+(en?'Explore the sector':'Découvrir le secteur')+'</a></article>';}).join('')+'</div></div>':'';
   const body='<nav class="sector-breadcrumb" aria-label="'+(en?'Breadcrumb':'Fil d’Ariane')+'"><a href="'+index+'">'+(en?'Offers':'Offres')+'</a> / <span aria-current="page">'+esc(name)+'</span></nav><article class="policy sector-detail offer-detail"><div class="sector-intro"><span class="tag">'+(en?'DSIG SERVICES':'LES OFFRES DSIG')+'</span><h1>'+esc(name)+'</h1><p>'+esc(desc)+'</p></div><section class="sector-insight"><h2>'+(en?'Possible deliverables':'Livrables possibles')+'</h2><p>'+esc(deliverables)+'</p></section><section class="sector-insight public-offer-use-cases"><h2>'+(en?'Illustrative use cases':'Exemples de besoins')+'</h2><ul>'+examples.map(example=>'<li>'+esc(example)+'</li>').join('')+'</ul><p>'+(en?'Examples are indicative and subject to assessment.':'Exemples indicatifs, sous réserve d’étude.')+'</p></section>'+solutionCatalogue+'<section class="sector-insight"><h2>'+(en?'Discuss your requirements':'Parlons de votre besoin')+'</h2><p>'+esc(note)+'</p><p>'+request(en?'Request a quote':'Demander un devis',(en?'Quote request: ':'Demande de devis : ')+name)+'</p>'+(offer.slug==='saas'?'<p>'+request(en?'Request a demonstration':'Demander une démonstration',(en?'Demonstration request: ':'Demande de démonstration : ')+name)+'</p>':'')+'</section></article>';
   save(offer.slug,name+' | DSIG',desc,body);
  }
  save('',title,description,'<div class="sector-intro"><span class="tag">'+(en?'OUR SERVICES':'NOS PRESTATIONS')+'</span><h1>'+(en?'Expertise for every stage of your project':'Un accompagnement adapté à chaque étape de votre projet')+'</h1><p>'+esc(description)+'</p></div><div class="expertise-grid sector-directory offer-directory">'+offers.map((o,i)=>'<article><span class="tag">0'+(i+1)+'</span><h2><a href="'+offerPath(lang,o.slug)+'">'+esc(o[lang][0])+'</a></h2><p>'+esc(o[lang][1])+'</p><a class="service-link" href="'+offerPath(lang,o.slug)+'">'+(en?'Explore this service':'Découvrir cette offre')+'</a></article>').join('')+'</div><p>'+esc(note)+'</p><p>'+request(en?'Discuss your project':'Parlons de votre projet',en?'Project enquiry':'Demande de projet')+'</p>');
 }
}
function blogTemplate(lang,body,alternate){
 const en=lang==='en';
 return '<!doctype html><html lang="'+lang+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Blog | DSIG</title><link rel="icon" href="/favicon.svg">'+
 ['style.css','brand.css','premium.css','studio.css','identity.css','expertise.css','accessibility.css','corporate-premium.css'].map(css=>'<link rel="stylesheet" href="/'+css+'">').join('')+
 '</head><body><a class="skip-link" href="#main">'+(en?'Skip to content':'Aller au contenu')+'</a><header class="nav"><a class="brand" href="'+home(lang)+'"><img class="dsig-logo" src="/dsig-mark.svg" width="100" height="40" alt="DSIG"></a><a href="'+blogPath(lang)+'">Blog</a><a href="'+alternate+'" hreflang="'+(en?'fr':'en')+'">'+(en?'Français':'English')+'</a></header><main class="section" id="main" tabindex="-1">'+body+'</main><footer><p>DataSphere Innovation Guinée</p><a href="'+legalPaths[lang].legal+'">'+(en?'Legal notice':'Mentions légales')+'</a> <a href="'+legalPaths[lang].privacy+'">'+(en?'Privacy':'Confidentialité')+'</a></footer></body></html>';
}
const sectorFamilies=[
   {id:'operations',fr:'Transport, logistique et industries',en:'Transport, logistics and industries',slugs:['transport','logistique','transport-logistique','mines','industrie','btp-infrastructures','energie-environnement','agriculture']},
   {id:'business',fr:'Entreprises, commerce et finance',en:'Business, retail and finance',slugs:['commerce-distribution','finance-comptabilite','banques','immobilier','services-entreprises','telecoms']},
   {id:'institutions',fr:'Institutions et services à la population',en:'Institutions and public services',slugs:['administrations','education','sante','culture']}
  ];

function buildSectors(out,contact){
 const slugs=new Set();
 for(const sector of sectors){
  if(!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(sector.slug)||slugs.has(sector.slug))throw Error('Invalid sector slug');
  slugs.add(sector.slug);
  for(const lang of ['fr','en']){
   const en=lang==='en',entry=sector[lang],url=sectorPath(lang,sector.slug),fr=sectorPath('fr',sector.slug),english=sectorPath('en',sector.slug);
   const links=sector.expertise.map(slug=>{
    const target=publicPath(lang,slug);
    if(!pages.includes(target))throw Error('Unknown sector expertise: '+target);
    const label=fs.readFileSync(path.join(out,target.slice(1)),'utf8').match(/<title>(.*?) \| DSIG Guinée<\/title>/)?.[1];
    if(!label)throw Error('Missing expertise label: '+target);
    return '<li><a href="'+target+'">'+label+'</a></li>';
   }).join('');
   const body='<nav class="sector-breadcrumb" aria-label="'+(en?'Breadcrumb':'Fil d’Ariane')+'"><a href="'+home(lang)+'">'+(en?'Home':'Accueil')+'</a> / <a href="'+sectorPath(lang)+'">'+(en?'Industries':'Secteurs')+'</a> / <span aria-current="page">'+esc(entry.title)+'</span></nav><article class="policy sector-detail"><div class="sector-intro"><span class="tag">'+(en?'INDUSTRY EXPERTISE':'EXPERTISE SECTORIELLE')+'</span><h1>'+esc(entry.title)+'</h1><p>'+esc(entry.description)+'</p></div>'+entry.sections.map(([heading,copy],i)=>'<section class="sector-insight"><span class="tag">0'+(i+1)+'</span><h2>'+esc(heading)+'</h2><p>'+esc(copy)+'</p></section>').join('')+'<h2>'+(en?'Related expertise':'Expertises associées')+'</h2><ul>'+links+'</ul><p><a class="btn" href="mailto:'+esc(contact)+'">'+(en?'Discuss your project':'Parlons de votre projet')+'</a></p></article>';
   const title=entry.title+' | DSIG';
   put(out,url.slice(1),structuredData(metadata(blogTemplate(lang,body,en?fr:english),title,entry.description,fr,english,lang),lang,url,title,entry.description,contact));pages.push(url);
  }
 }
 for(const lang of ['fr','en']){
  const en=lang==='en',url=sectorPath(lang),title=en?'Industries — Digital consulting in Guinea | DSIG':'Secteurs — Conseil numérique en Guinée | DSIG',description=en?'Explore sector-specific digital and data solutions in Guinea.':'Découvrez les solutions numériques et Data adaptées aux secteurs d’activité en Guinée.';
  const available=sectorFamilies.map(family=>({...family,items:family.slugs.map(slug=>sectors.find(sector=>sector.slug===slug)).filter(Boolean)})).filter(family=>family.items.length);
  const assigned=available.flatMap(family=>family.items);
  const remaining=sectors.filter(sector=>!assigned.includes(sector));
  if(remaining.length)available.push({id:'other',fr:'Autres secteurs',en:'Other industries',items:remaining});
  if(new Set(available.flatMap(family=>family.items)).size!==sectors.length)throw Error('Incomplete public sector navigation');
  const familyNav='<nav class="sector-intro" aria-label="'+(en?'Industry families':'Familles de secteurs')+'"><ul>'+available.map(family=>'<li><a href="#family-'+family.id+'">'+esc(family[lang])+'</a></li>').join('')+'</ul></nav>';
  const familyCards=available.map(family=>'<section class="sector-insight" id="family-'+family.id+'"><h2>'+esc(family[lang])+'</h2><div class="expertise-grid sector-directory">'+family.items.map(sector=>'<article><h3><a href="'+sectorPath(lang,sector.slug)+'">'+esc(sector[lang].title)+'</a></h3><p>'+esc(sector[lang].description)+'</p><a class="service-link" href="'+sectorPath(lang,sector.slug)+'">'+(en?'Explore this industry':'Découvrir ce secteur')+'</a></article>').join('')+'</div></section>').join('');
  const body='<div class="sector-intro"><span class="tag">'+(en?'DSIG INDUSTRIES':'LES SECTEURS DSIG')+'</span><h1>'+(en?'Digital expertise for your industry':'Des expertises adaptées à votre secteur')+'</h1><p>'+esc(description)+'</p></div>'+familyNav+familyCards+'<div class="sector-intro sector-contact"><h2>'+(en?'Discuss your industry challenges':'Parlons de vos enjeux métier')+'</h2><a class="btn" href="mailto:'+esc(contact)+'">'+(en?'Contact our team':'Contacter notre équipe')+'</a></div>';
  put(out,url.slice(1),structuredData(metadata(blogTemplate(lang,body,sectorPath(en?'fr':'en')),title,description,sectorPath('fr'),sectorPath('en'),lang),lang,url,title,description,contact));pages.push(url);
 }
}
function buildBlog(out,contact){
 const slugs=new Set();
 for(const post of posts){
  if(!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(post.slug)||slugs.has(post.slug))throw Error('Invalid or duplicate post slug');
  slugs.add(post.slug);
  for(const lang of ['fr','en']){
   const en=lang==='en',entry=post[lang],url=blogPath(lang,post.slug);
   const expertise=publicPath(lang,post.expertise);
   if(!pages.includes(expertise))throw Error('Unknown related expertise: '+expertise);
   const body='<nav class="sector-breadcrumb" aria-label="'+(en?'Breadcrumb':'Fil d’Ariane')+'"><a href="'+home(lang)+'">'+(en?'Home':'Accueil')+'</a> / <a href="'+blogPath(lang)+'">Blog</a> / <span aria-current="page">'+esc(entry.title)+'</span></nav><article class="policy sector-detail public-blog-article"><div class="sector-intro"><span class="tag">DSIG INSIGHTS</span><h1>'+esc(entry.title)+'</h1><p>'+esc(entry.description)+'</p><p>DataSphere Innovation Guinée</p></div>'+
    entry.sections.map(([heading,text],i)=>'<section class="sector-insight"><span class="tag">0'+(i+1)+'</span><h2>'+esc(heading)+'</h2><p>'+esc(text)+'</p></section>').join('')+
    '<p><a href="'+expertise+'">'+(en?'Explore the related expertise':'Découvrir l’expertise associée')+'</a></p><p><a class="btn" href="mailto:'+esc(contact)+'">'+(en?'Discuss your project':'Parlons de votre projet')+'</a></p><p><a href="'+blogPath(lang)+'">'+(en?'Back to the blog':'Retour au blog')+'</a></p></article>';
   const fr=blogPath('fr',post.slug),english=blogPath('en',post.slug);
   let html=metadata(blogTemplate(lang,body,en?fr:english),entry.title+' | DSIG',entry.description,fr,english,lang).replace('property="og:type" content="website"','property="og:type" content="article"');
   html=structuredData(html,lang,url,entry.title+' | DSIG',entry.description,contact,null,entry);
   put(out,url.slice(1),html);pages.push(url);
  }
 }
 for(const lang of ['fr','en']){
  const en=lang==='en',url=blogPath(lang),title=en?'DSIG Insights — Data, AI and digital transformation':'Blog DSIG — Data, IA et transformation digitale',description=en?'Practical guides for organisations in Guinea and Africa.':'Guides pratiques pour les organisations en Guinée et en Afrique.';
  const body='<div class="sector-intro"><span class="tag">DSIG INSIGHTS</span><h1>'+esc(title)+'</h1><p>'+esc(description)+'</p></div><div class="expertise-grid sector-directory public-blog-directory">'+posts.map(post=>'<article><span class="tag">'+(en?'PRACTICAL GUIDE':'GUIDE PRATIQUE')+'</span><h2><a href="'+blogPath(lang,post.slug)+'">'+esc(post[lang].title)+'</a></h2><p>'+esc(post[lang].description)+'</p><a class="service-link" href="'+blogPath(lang,post.slug)+'">'+(en?'Read the guide':'Lire le guide')+'</a></article>').join('')+'</div>';
  let html=metadata(blogTemplate(lang,body,blogPath(en?'fr':'en')),title,description,blogPath('fr'),blogPath('en'),lang);
  html=structuredData(html,lang,url,title,description,contact);
  put(out,url.slice(1),html);pages.push(url);
 }
}

// Public contact form (issue #156, V175): request types offered to visitors (values = server types).
const publicNeeds=[['Demande de devis','Demande de devis','Quote request'],['Demande de démonstration','Démonstration SaaS','SaaS demonstration'],
 ['Partenariat','Partenariat','Partnership'],['Conseil & expertise','Conseil et expertise','Consulting and expertise'],
 ['Formation','Formation','Training'],['Autre demande','Autre demande','Other request']];
function publicForm(lang,contact){
 const en=lang==='en',t=(fr,english)=>en?english:fr;
 const field=(label,input)=>'<label>'+label+input+'</label>';
 return '<form id="request" data-fallback="'+esc(contact)+'" novalidate>'+
  field(t('Nom et prénom','Full name'),'<input name="nom" required maxlength="120" autocomplete="name">')+
  field(t('Entreprise / organisation','Company / organisation'),'<input name="org" required maxlength="180" autocomplete="organization">')+
  field(t('E-mail','Email'),'<input name="email" type="email" required maxlength="254" autocomplete="email">')+
  field(t('Téléphone / WhatsApp <small>(facultatif)</small>','Phone / WhatsApp <small>(optional)</small>'),'<input name="telephone" type="tel" maxlength="30" autocomplete="tel" inputmode="tel" pattern="\\+?[0-9][0-9 \\(\\)\\.\\-]{5,28}">')+
  field(t('Type de demande','Type of request'),'<select name="besoin" required>'+publicNeeds.map(([value,fr,english])=>'<option value="'+esc(value)+'">'+esc(en?english:fr)+'</option>').join('')+'</select>')+
  field('Message','<textarea name="message" rows="5" required maxlength="4000"></textarea>')+
  '<p class="footnote">'+t('Ne transmettez ni données sensibles, ni CV, ni document personnel. Vos données servent uniquement à répondre à votre demande : ','Do not send sensitive data, CVs or personal documents. Your data is only used to answer your request: ')+'<a href="'+legalPaths[lang].privacy+'">'+t('notice de confidentialité','privacy notice')+'</a>.</p>'+
  '<label class="consent-label"><input type="checkbox" name="consent" required> '+t('J’ai lu la notice de confidentialité.','I have read the privacy notice.')+'</label>'+
  '<label class="request-honeypot" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label>'+
  '<button class="btn" type="submit">'+t('Envoyer ma demande','Send my request')+'</button>'+
  '<p id="request-status" role="status" aria-live="polite"></p></form>';
}
const publicContactScript=`// Public contact form: same-origin API only, double-submit protection, accessible status messages.
(()=>{const form=document.getElementById('request');if(!form)return;
const status=document.getElementById('request-status'),button=form.querySelector('[type=submit]'),en=document.documentElement.lang==='en';
const mail=form.dataset.fallback,fallback=(en?'Sending is unavailable right now. Please email ':'Envoi momentanément indisponible. Écrivez-nous à ')+mail+'.';
let busy=false;
form.addEventListener('submit',async e=>{e.preventDefault();if(busy)return;
 if(!form.checkValidity()){form.reportValidity();status.textContent=en?'Please check the highlighted fields.':'Vérifiez les champs signalés.';return}
 busy=true;button.disabled=true;status.textContent=en?'Sending…':'Envoi en cours…';
 const data=Object.fromEntries(new FormData(form).entries());data.consent=data.consent==='on';data.language=en?'en':'fr';
 try{const response=await fetch('/api/contact',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),credentials:'omit'});
  const body=await response.json().catch(()=>({}));
  if(response.ok){form.reset();status.textContent=body.message||(en?'Your request has been received.':'Votre demande a bien été reçue.')}
  else status.textContent=response.status>=500||!body.error?fallback:body.error;
 }catch{status.textContent=fallback}
 finally{busy=false;button.disabled=false;status.focus?.()}
});})();
`;

export function build(out,contact,options={}){
 if(contact!==approvedContact)throw Error('Provide the approved DSIG contact mailbox.');
 const form=options.form===true,fields=options.fields??legalFields;
 // The public form can only be published once every legal field is officially validated (V161).
 if(form&&!legalReadiness(fields).complete)throw Error('Public contact form refused: legal information is incomplete ('+legalReadiness(fields).missing.length+' missing).');
 const logos=loadReferenceLogos(source);
 // mkdir fails if destination exists: no overwrite of an existing release.
 fs.mkdirSync(out,{mode:0o755});
 pages.length=0;
 for(const asset of assets){
  const target=path.join(out,asset);fs.mkdirSync(path.dirname(target),{recursive:true});
  fs.copyFileSync(path.join(source,asset),target);
 }
 for(const logo of logos){
  const target=path.join(out,logo.file);fs.mkdirSync(path.dirname(target),{recursive:true});
  fs.writeFileSync(target,logo.bytes);
 }
 const groups={fr:[],en:[]};let i=0;
 for(const [g,group] of data.expertiseGroups.entries()){
  const cards={fr:[],en:[]};
  for(const [icon,name,description] of group.items){
   const slug=data.expertiseId(name);
   const fr=publicPath('fr',slug),en=publicPath('en',slug);
   for(const lang of ['fr','en']){
    const english=lang==='en';
    const [title,desc,benefit,scope,deliverables]=english?data.expertiseEnglish[i]:[name,description,...data.expertiseDetails[i]];
    const groupName=english?data.expertiseEnglishGroups[g]:group.name;
    const url=english?en:fr;
    let html=read(english?'expertise-en.html':'expertise.html');
    for(const [id,value] of Object.entries({group:groupName,name:title,description:desc,benefit,scope,deliverables})){
     const marker='id="'+id+'">';
     if(!html.includes(marker))throw Error('Missing detail field '+id);
     html=html.replace(marker,marker+esc(value));
    }
    html=html.replace('id="expertise-mark"','id="expertise-mark" data-icon="'+esc(icon)+'"')
     .replace('<script src="expertise.js"></script>','')
     .replace('</header>','<a href="'+(english?fr:en)+'" hreflang="'+(english?'fr':'en')+'">'+(english?'Français':'English')+'</a></header>');
    const seoTitle=title+' | DSIG Guinée';
    html=metadata(html,seoTitle,desc,fr,en,lang)
     .replaceAll('href="index.html','href="/');
    html=html.replace(/<main id="expertise-detail"[^>]*>/,match=>match+
     '<nav aria-label="'+(english?'Breadcrumb':'Fil d’Ariane')+'"><a href="'+home(lang)+'">'+(english?'Home':'Accueil')+'</a> / <span aria-current="page">'+esc(title)+'</span></nav>')
     .replace('</main>','<p class="career-note">'+(english?'Service area: Conakry, Guinea and France, depending on the project.':'Zone d’intervention : Conakry, Guinée et France, selon le projet.')+'</p><p><a href="mailto:'+esc(contact)+'">'+esc(contact)+'</a></p></main>');
    html=structuredData(html,lang,url,seoTitle,desc,contact,title);
    put(out,url.slice(1),html);pages.push(url);
    cards[lang].push('<article><div class="expertise-icon" data-icon="'+esc(icon)+'"></div><h4>'+esc(title)+'</h4><p>'+esc(desc)+'</p><a class="service-link" href="'+url+'">'+(english?'Explore this expertise':'Découvrir cette expertise')+'</a></article>');
   }
   i++;
  }
  for(const lang of ['fr','en'])groups[lang].push('<section class="expertise-group"><h3>'+esc(lang==='fr'?group.name:data.expertiseEnglishGroups[g])+'</h3><div class="expertise-grid">'+cards[lang].join('')+'</div></section>');
 }
 for(const lang of ['fr','en']){
  const english=lang==='en',filename=english?'en.html':'index.html';
  let html=renderReferenceLogos(read(filename),logos);
  // Public-only discovery links: the shared REC homepage is not modified.
  const pillarLinks={
   'DSIG Consulting':{url:offerPath(lang,'conseil-audit'),label:english?'Explore consulting':'Découvrir le conseil'},
   'DSIG Technology':{url:home(lang)+'#services',label:english?'Explore technology expertise':'Découvrir les expertises'},
   'DSIG Solutions':{url:offerPath(lang,'saas'),label:english?'Explore business solutions':'Découvrir les solutions métiers'}
  };
  for(const [name,link] of Object.entries(pillarLinks)){
   const marker='<h3>'+name+'</h3>';
   const start=html.indexOf(marker),end=html.indexOf('</article>',start);
   if(start<0||end<0)throw Error('Missing public pillar: '+name);
   const fragment=html.slice(start,end);
   const updated=fragment.replace(/<a href="[^"]+"[^>]*>[\s\S]*?<\/a>/,'<a href="'+link.url+'">'+esc(link.label)+' <span data-icon="arrow"></span></a>');
   if(updated===fragment)throw Error('Missing public pillar link: '+name);
   html=html.slice(0,start)+updated+html.slice(end);
  }

  const sectorMenuLabels={
   transport:['Transport et mobilité','Transport and mobility'],logistique:['Logistique et supply chain','Logistics and supply chain'],
   'transport-logistique':['Transport et logistique intégrés','Integrated transport and logistics'],mines:['Mines','Mining'],industrie:['Industrie','Manufacturing'],
   'btp-infrastructures':['BTP et infrastructures','Construction and infrastructure'],'energie-environnement':['Énergie et environnement','Energy and environment'],agriculture:['Agriculture','Agriculture'],
   'commerce-distribution':['Commerce et distribution','Retail and distribution'],'finance-comptabilite':['Finance et comptabilité','Finance and accounting'],banques:['Banques','Banking'],immobilier:['Immobilier','Real estate'],
   'services-entreprises':['Services aux entreprises','Business services'],telecoms:['Télécommunications','Telecommunications'],administrations:['Administrations publiques','Public administration'],
   education:['Éducation','Education'],sante:['Santé','Healthcare'],culture:['Culture','Culture']
  };
  const sectorMenu=sectorFamilies.map(family=>{
   const items=family.slugs.map(slug=>sectors.find(sector=>sector.slug===slug)).filter(Boolean);
   return items.length?'<div><strong>'+esc(family[lang])+'</strong>'+items.map(sector=>'<a href="'+sectorPath(lang,sector.slug)+'">'+esc(sectorMenuLabels[sector.slug]?.[english?1:0]??sector[lang].title)+'</a>').join('')+'</div>':'';
  }).join('');
  const sectorDropdown='<details class="corporate-mega public-sector-mega"><summary>'+(english?'Industries':'Secteurs')+'</summary><div class="corporate-mega-panel">'+sectorMenu+'</div></details>';

  // Public positioning only: retain the shared REC homepage unchanged.
  const publicHero=english?{
   eyebrow:'CONSULTING · ENGINEERING · TECHNOLOGY · BUSINESS SOLUTIONS',
   heading:'Your multiservice partner for <em>lasting business transformation.</em>',
   description:'From data and digital strategy to transport, logistics, industry, finance and public services, DSIG helps organisations design and implement solutions tailored to their needs.',
   note:'Serving businesses, industries and institutions in Guinea, Africa and internationally.',
   action:'Explore our sectors'
  }:{
   eyebrow:'CONSEIL · INGÉNIERIE · TECHNOLOGIES · SOLUTIONS MÉTIERS',
   heading:'Votre partenaire multiservices pour <em>transformer durablement vos activités.</em>',
   description:'De la Data et du numérique au transport, à la logistique, à l’industrie, à la finance et aux services publics, DSIG accompagne les organisations dans la conception et la mise en œuvre de solutions adaptées.',
   note:'Au service des entreprises, industries et institutions en Guinée, en Afrique et à l’international.',
   action:'Découvrir nos secteurs'
  };
  let heroUpdated=false;
  html=html.replace(/<div class="hero-content">[\s\S]*?<\/div><div class="visual"/,hero=>{
   heroUpdated=true;
   return hero.replace(/(<div class="eyebrow"><i><\/i> )[\s\S]*?<\/div>/,'$1'+esc(publicHero.eyebrow)+'</div>')
    .replace(/<h1>[\s\S]*?<\/h1>/,'<h1>'+publicHero.heading+'</h1>')
    .replace(/<\/h1><p>[\s\S]*?<\/p>/,'</h1><p>'+esc(publicHero.description)+'</p>')
    .replace(/<div class="hero-note">[\s\S]*?<\/div>/,'<div class="hero-note">'+esc(publicHero.note)+'</div>')
    .replace('</div><div class="hero-note">','<a class="outline" href="'+sectorPath(lang)+'">'+esc(publicHero.action)+'</a></div><div class="hero-note">');
  });
  if(!heroUpdated||!html.includes(publicHero.heading)||!html.includes(esc(publicHero.action)))throw Error('Missing public multiservice hero');

  // Public-only technology positioning. No vendor partnership or product availability claim.
  const techBenefits=english?[
   'Choose storage and processing platforms suited to data volumes and operating constraints.',
   'Build reliable, observable and maintainable data pipelines.',
   'Turn trusted data into actionable indicators and controlled access.',
   'Automate deployment and improve operational reliability.',
   'Frame delivery around measurable objectives and acceptance criteria.',
   'Assess automation and AI use cases before selecting a solution.'
  ]:[
   'Choisir des plateformes adaptées aux volumes de données et aux contraintes d’exploitation.',
   'Construire des pipelines de données fiables, observables et maintenables.',
   'Transformer les données fiables en indicateurs utiles et maîtriser les accès.',
   'Automatiser les déploiements et améliorer la fiabilité opérationnelle.',
   'Cadrer les interventions autour d’objectifs mesurables et de critères de recette.',
   'Évaluer les usages de l’automatisation et de l’IA avant de choisir une solution.'
  ];
  let techCount=0;
  html=html.replace(/<section class="section technologies" id="technologies">[\s\S]*?<\/section>/,section=>{
   const cards=section.replace(/(<article><h3>[^<]+<\/h3>)(<p>[\s\S]*?<\/p><\/article>)/g,(_,heading,tools)=>{
    if(techCount>=techBenefits.length)throw Error('Unexpected public technology card');
    return heading+'<p class="public-tech-benefit">'+esc(techBenefits[techCount++])+'</p>'+tools;
   });
   const notice=english?'Technologies are selected according to project needs. Brand names do not imply a vendor partnership.':'Les technologies sont sélectionnées selon les besoins du projet. Les marques citées n’impliquent aucun partenariat éditeur.';
   return cards.replace('</section>','<p class="footnote">'+esc(notice)+'</p><p><a class="btn" href="#contact">'+(english?'Discuss your technical requirements':'Échanger sur vos besoins techniques')+'</a></p></section>');
  });
  if(techCount!==techBenefits.length)throw Error('Missing public technology cards');

  // Public-only commercial orientation, independent of the application and contact API.
  const journeys=[
   ['conseil-audit',english?'Assess and plan':'Diagnostiquer et planifier',english?'Clarify priorities and define a roadmap.':'Clarifier les priorités et définir une feuille de route.'],
   ['regie',english?'Strengthen your team':'Renforcer vos équipes',english?'Explore specialist support for your project.':'Mobiliser une expertise spécialisée pour votre projet.'],
   ['forfait',english?'Deliver a project':'Réaliser un projet',english?'Define scope, milestones and acceptance criteria.':'Définir le périmètre, les jalons et les critères de recette.'],
   ['saas',english?'Explore business solutions':'Étudier une solution métier',english?'Qualify your needs before discussing a pilot.':'Qualifier vos besoins avant d’envisager un pilote.']
  ];
  const contactMarker='<section class="section" id="contact">';
  if(!html.includes(contactMarker))throw Error('Missing public contact section');
  html=html.replace(contactMarker,contactMarker+'<div class="public-commercial-journey"><div class="section-head"><div><div class="tag">'+(english?'YOUR PROJECT':'VOTRE PROJET')+'</div><h2>'+(english?'Find the right support for your needs':'Trouvez l’accompagnement adapté à vos besoins')+'</h2></div></div><div class="expertise-grid sector-directory">'+journeys.map(([slug,title,description])=>'<article><h3>'+esc(title)+'</h3><p>'+esc(description)+'</p><a class="service-link" href="'+offerPath(lang,slug)+'">'+(english?'Explore the offer':'Découvrir l’offre')+'</a></article>').join('')+'</div></div>');

  // Public-only editorial enhancement: do not alter the shared application templates.
  html=html.replace(/<section class="section references" id="references">[\s\S]*?<\/section>/,section=>{
   const heading=english?'Expertise built in the field.':'Une expertise forgée sur le terrain.';
   const intro=english?'Explore the declared professional experience behind DSIG: analytics platforms, data integration, migrations and business intelligence.':'Découvrez les expériences professionnelles déclarées à l’origine de DSIG : plateformes analytiques, intégration de données, migrations et informatique décisionnelle.';
   const cta=english?'Discuss a similar challenge':'Échanger sur un enjeu similaire';
   return section.replace('<h2>'+heading+'</h2>','<h2>'+heading+'</h2><p class="public-reference-intro">'+esc(intro)+'</p>')
    .replace('</section>','<p class="public-reference-action"><a class="btn" href="#contact">'+esc(cta)+'</a></p></section>');
  });
  const placeholder='<div id="expertise-groups"></div>';
  if(!html.includes(placeholder))throw Error('Missing expertise group');
  html=html.replace(placeholder,'<div id="expertise-groups">'+groups[lang].join('')+'</div>')
   .replace('En recette locale, utilisez des données fictives, sans CV ni document personnel.','Ne transmettez pas de CV ni de document personnel lors du premier contact.')
   .replace('In the test environment, use fictitious data without CVs or personal documents.','Do not send CVs or personal documents during initial contact.')
   .replace('<small>Coordonnées commerciales définitives à confirmer.</small>','')
   .replace('<small>Final commercial contact details to be confirmed.</small>','')
   .replace(/<form id="request">[\s\S]*?<\/form>/,form?publicForm(lang,contact):'<div class="contact-public"><p>'+(english?'Contact our team by email. Do not send sensitive information.':'Contactez notre équipe par e-mail. Ne transmettez pas de données sensibles.')+'</p><a class="btn" href="mailto:'+esc(contact)+'">'+esc(contact)+'</a></div>')
   .replace('<script src="expertise.js"></script>','').replace('<script src="app.js"></script>','<script src="public-menu.js"></script>'+(form?'<script defer src="public-contact.js"></script>':''))
   .replace('<a href="#offres">'+(english?'Our services':'Nos offres')+'</a>','<a href="'+offerPath(lang)+'">'+(english?'Our services':'Nos offres')+'</a>')
   .replace('</nav>','<a href="'+offerPath(lang,'saas')+'">'+(english?'Solutions':'Solutions')+'</a>'+sectorDropdown+'<a href="'+sectorPath(lang)+'">'+(english?'All industries':'Tous les secteurs')+'</a><a href="'+blogPath(lang)+'">Blog</a><a href="'+home(english?'fr':'en')+'" hreflang="'+(english?'fr':'en')+'">'+(english?'Français':'English')+'</a></nav>')
   .replaceAll('href="index.html','href="/');
  const title=english?'DSIG | Multiservice consulting, technology and business solutions':'DSIG Guinée | Conseil multiservices, technologies et solutions métiers';
  const description=english?'Consulting, data, AI, transport, logistics, industry and business solutions for organisations in Guinea, Africa and internationally.':'Conseil, Data, IA, transport, logistique, industrie et solutions métiers pour les organisations en Guinée, en Afrique et à l’international.';
  html=metadata(html,title,description,'/', '/en.html',lang);
  html=structuredData(html,lang,home(lang),title,description,contact);
  // Keep the public presentation separate from the REC contact collection.
  put(out,filename,html);pages.push(home(lang));
  // Legal and privacy notices: noindex, outside the sitemap, rendered from the validated legal source only.
  for(const kind of ['privacy','legal']){
   const file=legalPaths[lang][kind].slice(1),main=kind==='legal'?renderLegalMain(lang,contact,fields):renderPrivacyMain(lang,contact,fields,{form});
   const html=read(file);
   if(!/<main[\s\S]*?<\/main>/.test(html)||!html.includes('content="noindex,nofollow"'))throw Error('Invalid notice source: '+file);
   put(out,file,html.replace(/<main[\s\S]*?<\/main>/,()=>main));
  }
 }
 buildBlog(out,contact);
 buildSectors(out,contact);
 buildOffers(out,contact);
 optimizePublicPages(out);
 put(out,'public-menu.js',`const menu=document.querySelector('#menu'),nav=document.querySelector('#links');function closeMenu(){nav.classList.remove('open');menu.setAttribute('aria-expanded','false')}menu.onclick=()=>menu.setAttribute('aria-expanded',String(nav.classList.toggle('open')));nav.addEventListener('click',e=>{if(e.target.closest('a'))closeMenu()});document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenu();menu.focus()}});document.querySelectorAll('.corporate-mega').forEach(d=>{d.addEventListener('click',e=>{if(e.target.closest('a'))d.open=false});document.addEventListener('click',e=>{if(!d.contains(e.target))d.open=false});d.addEventListener('keydown',e=>{if(e.key==='Escape'&&d.open){e.preventDefault();e.stopPropagation();d.open=false;d.querySelector('summary').focus()}})});`);
 if(form)put(out,'public-contact.js',publicContactScript);
 put(out,'robots.txt','User-agent: *\nAllow: /\nSitemap: '+origin+'/sitemap.xml\n');
 put(out,'sitemap.xml','<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+pages.sort().map(u=>'<url><loc>'+origin+u+'</loc></url>').join('\n')+'\n</urlset>\n');
 return pages.length;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const form=process.argv[4]==='--form';
 if(process.argv.length!==(form?5:4))throw Error('Usage: node scripts/build-public-site.mjs NEW_DIRECTORY APPROVED_EMAIL [--form]');
 // --form always uses the real legal data: it fails until every legal field is validated.
 console.log('Indexable public pages: '+build(path.resolve(process.argv[2]),process.argv[3],{form}));
}
