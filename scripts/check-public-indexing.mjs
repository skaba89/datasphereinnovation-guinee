// Read-only, fixed-host publication checks. No search engine credentials needed.
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const origin='https://dsig-consulting.com';
const rec='https://rec.dsig-consulting.com';

export async function checkPublic(fetcher=fetch){
 const checks=[];
 async function get(url){return fetcher(url,{redirect:'manual',signal:AbortSignal.timeout(15000)});}
 async function check(name,fn){
  try{if(!await fn())throw Error('Unexpected response');checks.push({name,status:'PASS'});}
  catch{checks.push({name,status:'FAIL'});}
 }
 let urls=[];
 await check('robots',async()=>{
  const r=await get(origin+'/robots.txt'),text=await r.text();
  return r.status===200&&/^Sitemap:\s*https:\/\/dsig-consulting\.com\/sitemap\.xml\s*$/mi.test(text)&&!/^Disallow:\s*\/\s*$/mi.test(text);
 });
 await check('sitemap',async()=>{
  const r=await get(origin+'/sitemap.xml'),xml=await r.text();
  if(r.status!==200||!/<urlset\b/.test(xml))return false;
  const locations=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
  if(locations.length<96||locations.length>500||new Set(locations).size!==locations.length||!locations.includes(origin+'/')||!locations.includes(origin+'/en.html')||!locations.includes(origin+'/offres.html')||!locations.includes(origin+'/offers.html')||locations.some(u=>!/^https:\/\/dsig-consulting\.com\/(?:[a-z0-9-]+\.html)?$/.test(u)))return false;
  urls=locations;return true;
 });
 const translations=new Map();
 for(const url of urls){
  await check('indexable '+url.slice(origin.length),async()=>{
   const r=await get(url),html=await r.text();
   const lang=html.match(/<html lang="(fr|en)"/)?.[1];
   const alternates=Object.fromEntries([...html.matchAll(/<link rel="alternate" hreflang="(fr|en|x-default)" href="([^"]+)">/g)].map(m=>[m[1],m[2]]));
   translations.set(url,{lang,alternates});
   const editorial=lang&&alternates[lang]===url&&alternates['x-default']===alternates.fr&&urls.includes(alternates.fr)&&urls.includes(alternates.en)&&alternates.fr!==alternates.en;
   const headings=[...html.matchAll(/<h1\b[^>]*>[\s\S]*?<\/h1>/gi)];
   const title=html.match(/<title>([^<]+)<\/title>/i)?.[1]?.trim();
   const description=html.match(/<meta name="description" content="([^"]+)">/)?.[1]?.trim();
   return editorial&&headings.length===1&&title&&description&&r.status===200&&/text\/html/i.test(r.headers.get('content-type')||'')&&!/\b(?:noindex|none)\b/i.test(r.headers.get('x-robots-tag')||'')&&html.includes('rel="canonical" href="'+url+'"')&&html.includes('content="index,follow,max-image-preview:large"')&&!/<meta\b[^>]*name="(?:robots|googlebot|bingbot)"[^>]*content="[^\"]*\b(?:noindex|none)\b/i.test(html);
  });
 }
 await check('reciprocal hreflang',async()=>urls.length>0&&urls.every(url=>{
  const current=translations.get(url);
  if(!current?.lang)return false;
  const {fr,en}=current.alternates;
  const french=translations.get(fr),english=translations.get(en);
  return french?.lang==='fr'&&english?.lang==='en'&&french.alternates.fr===fr&&french.alternates.en===en&&english.alternates.fr===fr&&english.alternates.en===en;
 }));
 for(const route of ['/accounts.html','/connexion.html','/api/admin/requests','/.env'])await check('private '+route,async()=>[403,404,410].includes((await get(origin+route)).status));
 await check('REC restricted',async()=>[401,403].includes((await get(rec+'/')).status));
 return {status:checks.every(c=>c.status==='PASS')?'PASS':'FAIL',pages_checked:urls.length,checks};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const result=await checkPublic();console.log(JSON.stringify(result,null,2));if(result.status!=='PASS')process.exitCode=1;
}
