import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

export const referenceBrands=Object.freeze({
 'in-li':'In’li','interact-software':'Interact Software',amayas:'Amayas',keyrus:'Keyrus',
 sacem:'SACEM','mso-soft':'MSO-Soft',thales:'Thales Group',accor:'Accor',
 arcade:'Arcade (Keyrus)','prefecture-police':'Préfecture de Police de Paris',
 kiloutou:'Kiloutou',orano:'Orano (Areva)','dpd-france':'DPD France'
});

// Only explicitly reviewed artwork is published. Missing logos retain the readable name.
export function loadReferenceLogos(source){
 const manifest=JSON.parse(fs.readFileSync(path.join(source,'reference-logos.json'),'utf8'));
 if(!Array.isArray(manifest))throw Error('Invalid reference logo manifest');
 const seen=new Set();
 return manifest.map(entry=>{
  const {id,sourceUrl,sha256}=entry;
  if(!Object.hasOwn(referenceBrands,id)||seen.has(id))throw Error('Unknown or duplicate reference logo');
  seen.add(id);
  const url=new URL(sourceUrl);
  if(url.protocol!=='https:'||url.username||url.password)throw Error('Invalid logo provenance');
  if(!/^[a-f0-9]{64}$/.test(sha256))throw Error('Missing logo checksum');
  const file='reference-logos/'+id+'.png',full=path.join(source,file);
  const stat=fs.lstatSync(full);
  if(!stat.isFile()||stat.size>150*1024)throw Error('Invalid logo file: '+id);
  const bytes=fs.readFileSync(full);
  if(createHash('sha256').update(bytes).digest('hex')!==sha256)throw Error('Reference logo checksum mismatch: '+id);
  if(bytes.length<33||bytes.subarray(0,8).toString('hex')!=='89504e470d0a1a0a'||bytes.toString('ascii',12,16)!=='IHDR'||bytes.readUInt32BE(16)<1||bytes.readUInt32BE(20)<1||bytes.readUInt32BE(16)>1600||bytes.readUInt32BE(20)>1600)throw Error('Invalid PNG dimensions: '+id);
  return {id,file,sha256,name:referenceBrands[id],bytes};
 });
}

export function renderReferenceLogos(html,logos){
 for(const {name,file} of logos){
  const marker='<article><strong>'+name+'</strong>';
  if(html.split(marker).length!==2)throw Error('Missing or ambiguous reference card: '+name);
  html=html.replace(marker,'<article class="reference-with-logo"><div class="reference-logo"><img src="/'+file+'" alt="" width="160" height="64" loading="lazy" decoding="async"></div><strong>'+name+'</strong>');
 }
 return html;
}
