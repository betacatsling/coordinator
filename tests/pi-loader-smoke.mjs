// Optional offline smoke against an existing Pi installation. No Pi session,
// provider, credential store, GitHub request, or third-party install is started.
import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { readFile } from 'node:fs/promises';

const root=process.argv[2];
if (!root) throw new Error('Pass the absolute path to an existing Pi package');
const {loadExtensions}=await import(pathToFileURL(path.join(root,'dist/core/extensions/loader.js')).href);
const loaded=await loadExtensions([path.resolve('extensions/github-project/index.ts')],process.cwd());
assert.deepEqual(loaded.errors,[]);assert.equal(loaded.extensions.length,1);
const tools=[...loaded.extensions[0].tools.values()];
assert.equal(tools.length,4);
const {Value}=await import(pathToFileURL(path.join(root,'node_modules/typebox/build/value/index.mjs')).href)
  .catch(async()=>import(pathToFileURL(path.join(root,'node_modules/typebox/build/value/index.js')).href));
const definition=tools.find(tool=>tool.definition.name === 'github_project_status').definition;
assert.equal(Value.Check(definition.parameters,{issueId:'I',expectedRevision:'revision',expectedStatusId:null,stage:'done'}),true);
assert.equal(Value.Check(definition.parameters,{issueId:'I',expectedRevision:'revision',expectedStatusId:null,stage:'unknown'}),false);
const read=tools.find(tool=>tool.definition.name === 'github_project_read').definition;
assert.equal(Value.Check(read.parameters,{}),true);
assert.equal(Value.Check(read.parameters,{issueId:'I'}),true);
assert.equal(Value.Check(read.parameters,{issueId:5}),false);
assert.equal(tools.some(tool=>tool.definition.name === 'github_issue_read'),false);
const version=JSON.parse(await readFile(path.join(root,'package.json'),'utf8')).version;
console.log(JSON.stringify({piVersion:version,extensions:loaded.extensions.length,tools:tools.map(t=>t.definition.name),schemaChecks:'passed',liveSessionStarted:false}));
