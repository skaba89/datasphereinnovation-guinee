import assert from 'node:assert/strict';
import fs from 'node:fs';
import {required,validate} from './public-release-gate.mjs';
import {legalReadiness} from './legal-content.mjs';
const legalOk={complete:true,missing:[]};
const sha='a'.repeat(40);
const blank=JSON.parse(fs.readFileSync(new URL('../deploy/public/release-gate.example.json',import.meta.url),'utf8'));
assert.equal(validate(blank,sha).status,'FAIL');
const valid={sha,domain:'dsig-consulting.com',email:'contact@dsig-consulting.com',gates:Object.fromEntries(required.map(key=>[key,{status:'PASS',reviewer:'Fixture reviewer',evidence:'Fixture evidence'}]))};
// All human gates PASS but repository legal identity is unconfirmed: publication must stay blocked.
const blocked=validate(valid,sha);
assert.equal(blocked.status,'FAIL');assert.equal(blocked.checks.legal_identity,false);assert.equal(blocked.publication_authorized,false);
assert.deepEqual(blocked.legal_missing,legalReadiness().missing);assert(blocked.legal_missing.includes('rccm'));
assert.equal(validate(valid,sha,{complete:false,missing:['nif']}).status,'FAIL');
assert.equal(validate(valid,sha,null).status,'FAIL');
assert.equal(validate(valid,sha,legalOk).status,'PASS');
for(const key of required){const broken=structuredClone(valid);delete broken.gates[key];assert.equal(validate(broken,sha,legalOk).status,'FAIL');}
for(const patch of [{sha:'b'.repeat(40)},{email:'test@dsig-consulting.com'},{email:'contact@datasphere-innovation.net'},{email:'contact@example.invalid'},{domain:'rec.dsig-consulting.com'}])assert.equal(validate({...valid,...patch},sha,legalOk).status,'FAIL');
const broken=structuredClone(valid);broken.gates.owner_approval.evidence='TODO';assert.equal(validate(broken,sha,legalOk).status,'FAIL');
console.log('PASS: public release gate, approval required, revision-bound and legal identity blocking');
