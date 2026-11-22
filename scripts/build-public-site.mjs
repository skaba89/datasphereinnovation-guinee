// Export only the public marketing site; never serve the REC bundle publicly.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

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
function publicPath(lang,slug){return '/expertise-'+(lang==='en'?'en-':'')+slug+'.html'}
function home(lang){return lang==='fr'?'/':'/en.html'}
const orgId=origin+'/#organization',siteId=origin+'/#website';
function structuredData(html,lang,url,title,description,contact,service=null){
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
 // Escape markup-breaking characters so JSON can never terminate its script tag.
 const json=JSON.stringify({'@context':'https://schema.org','@graph':graph}).replaceAll('<','\\u003c');
 return html.replace('</head>','<script type="application/ld+json">'+json+'</script>\n</head>');
}

export function build(out,contact){
 if(!/^[a-zA-Z0-9._+-]+@dsig-consulting\.com$/.test(contact))throw Error('Provide an approved DSIG business email.');
 // mkdir fails if destination exists: no overwrite of an existing release.
 fs.mkdirSync(out,{mode:0o755});
 pages.length=0;
 for(const asset of assets){
  const target=path.join(out,asset);fs.mkdirSync(path.dirname(target),{recursive:true});
  fs.copyFileSync(path.join(source,asset),target);
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
  let html=read(filename);
  const placeholder='<div id="expertise-groups"></div>';
  if(!html.includes(placeholder))throw Error('Missing expertise group');
  html=html.replace(placeholder,'<div id="expertise-groups">'+groups[lang].join('')+'</div>')
   .replace('En recette locale, utilisez des données fictives, sans CV ni document personnel.','Ne transmettez pas de CV ni de document personnel lors du premier contact.')
   .replace('In the test environment, use fictitious data without CVs or personal documents.','Do not send CVs or personal documents during initial contact.')
   .replace('<small>Coordonnées commerciales définitives à confirmer.</small>','')
   .replace('<small>Final commercial contact details to be confirmed.</small>','')
   .replace(/<form id="request">[\s\S]*?<\/form>/,'<div class="contact-public"><p>'+(english?'Contact our team by email. Do not send sensitive information.':'Contactez notre équipe par e-mail. Ne transmettez pas de données sensibles.')+'</p><a class="btn" href="mailto:'+esc(contact)+'">'+esc(contact)+'</a></div>')
   .replace('<script src="expertise.js"></script>','').replace('<script src="app.js"></script>','<script src="public-menu.js"></script>')
   .replace('</nav>','<a href="'+home(english?'fr':'en')+'" hreflang="'+(english?'fr':'en')+'">'+(english?'Français':'English')+'</a></nav>')
   .replaceAll('href="index.html','href="/');
  const title=english?'DataSphere Innovation Guinea | Data, AI & digital consulting':'DataSphere Innovation Guinée | Conseil Data, IA et transformation digitale';
  const description=english?'Digital consulting, Data Engineering, AI, BI, cybersecurity, SaaS and logistics expertise for organisations in Guinea and Africa.':'Cabinet de conseil numérique en Guinée : Data Engineering, IA, BI, cybersécurité, SaaS, logistique et transformation digitale pour les organisations.';
  html=metadata(html,title,description,'/', '/en.html',lang);
  html=structuredData(html,lang,home(lang),title,description,contact);
  // Keep the public presentation separate from the REC contact collection.
  put(out,filename,html);pages.push(home(lang));
  const privacy=read(english?'privacy-en.html':'confidentialite.html').replace(/<main[\s\S]*?<\/main>/,
   '<main class="policy" id="main"><h1>'+(english?'Privacy':'Confidentialité')+'</h1><p>'+(english?'This static website contains no contact form. Email links open your own email application. Do not send sensitive information.':'Ce site statique ne contient aucun formulaire de contact. Les liens e-mail ouvrent votre messagerie. Ne transmettez pas de données sensibles.')+'</p><p>'+(english?'Contact: ':'Contact : ')+esc(contact)+'</p><a href="'+home(lang)+'">'+(english?'Back to website':'Retour au site')+'</a></main>');
  put(out,english?'privacy-en.html':'confidentialite.html',privacy);
 }
 put(out,'public-menu.js',`const menu=document.querySelector('#menu'),nav=document.querySelector('#links');function closeMenu(){nav.classList.remove('open');menu.setAttribute('aria-expanded','false')}menu.onclick=()=>menu.setAttribute('aria-expanded',String(nav.classList.toggle('open')));nav.addEventListener('click',e=>{if(e.target.closest('a'))closeMenu()});document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenu();menu.focus()}});`);
 put(out,'robots.txt','User-agent: *\nAllow: /\nSitemap: '+origin+'/sitemap.xml\n');
 put(out,'sitemap.xml','<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+pages.sort().map(u=>'<url><loc>'+origin+u+'</loc></url>').join('\n')+'\n</urlset>\n');
 return pages.length;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 if(process.argv.length!==4)throw Error('Usage: node scripts/build-public-site.mjs NEW_DIRECTORY APPROVED_EMAIL');
 console.log('Indexable public pages: '+build(path.resolve(process.argv[2]),process.argv[3]));
}
