// Public release hygiene: inspect tracked files and new non-ignored files.
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
const files=execFileSync('git',['ls-files','--cached','--others','--exclude-standard','-z'],{encoding:'utf8'}).split('\0').filter(Boolean);
const rules=[
  /\/(?:Users|home)\/[A-Za-z0-9_.-]+\//,
  /libfile[_-][a-f0-9]{16,}/i,
  /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i,
  /\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
];
let failures=0;
for(const file of new Set(files)) {
  let data;try {data=readFileSync(file);}catch(error){if(error.code==='ENOENT')continue;throw error;}
  if(data.includes(0) || /(?:^|\/)(?:\.env(?:\..*)?|auth\.json|credentials|.*\.log)$/.test(file)) {
    console.error(`Unexpected private/binary file: ${file}`);failures++;continue;
  }
  if(rules.some(rule=>rule.test(data.toString('utf8')))) {
    console.error(`Potential sensitive content: ${file}`);failures++;
  }
}
if(failures)process.exit(1);
console.log('Release hygiene passed (paths, identifiers, credential patterns, private files).');
