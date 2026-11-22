import assert from 'node:assert/strict';
import fs from 'node:fs';
import {required,validate} from './public-release-gate.mjs';
const sha='a'.repeat(40);
const blank=JSON.parse(fs.readFileSync(new URL('../deploy/public/release-gate.example.json',import.meta.url),'utf8'));
assert.equal(validate(blank,sha).status,'FAIL');
const valid={sha,domain:'dsig-consulting.com',email:'fixture@dsig-consulting.com',gates:Object.fromEntries(required.map(key=>[key,{status:'PASS',reviewer:'Fixture reviewer',evidence:'Fixture evidence'}]))};
assert.equal(validate(valid,sha).status,'PASS');
for(const key of required){const broken=structuredClone(valid);delete broken.gates[key];assert.equal(validate(broken,sha).status,'FAIL');}
for(const patch of [{sha:'b'.repeat(40)},{email:'test@dsig-consulting.com'},{domain:'rec.dsig-consulting.com'}])assert.equal(validate({...valid,...patch},sha).status,'FAIL');
const broken=structuredClone(valid);broken.gates.owner_approval.evidence='TODO';assert.equal(validate(broken,sha).status,'FAIL');
console.log('PASS: public release gate, approval required and revision-bound');
