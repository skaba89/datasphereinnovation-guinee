// Human sign-off record: checks structure and release binding, not truth of evidence.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
export const required=['ci_exact_sha','commercial_contact','legal_privacy_review','dns_proxy_review','rec_isolation','rollback_plan','owner_approval'];
const value=s=>typeof s==='string'&&s.trim().length>=3&&!/^(todo|tbd|pending|example|placeholder|a confirmer|à confirmer|non validé)$/i.test(s.trim());
export function validate(record,sha){
 const checks={};
 checks.revision=/^[a-f0-9]{40}$/.test(sha)&&record?.sha===sha;
 checks.domain=record?.domain==='dsig-consulting.com';
 checks.contact=record?.email==='contact@datasphere-innovation.net';
 for(const key of required){const item=record?.gates?.[key];checks[key]=item?.status==='PASS'&&value(item?.reviewer)&&value(item?.evidence);}
 const status=Object.values(checks).every(Boolean)?'PASS':'FAIL';
 return {status,checks,publication_authorized:status==='PASS'};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  if(process.argv.length!==4)throw Error('Usage: public-release-gate.mjs SHA PRIVATE_RECORD.json');
  const record=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
  const result=validate(record,process.argv[2]);console.log(JSON.stringify(result,null,2));if(result.status!=='PASS')process.exitCode=1;
 }catch{console.error('FAIL: invalid or missing private approval record');process.exitCode=1;}
}
