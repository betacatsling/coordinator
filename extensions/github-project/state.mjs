import { mkdir, readFile, writeFile, rename, lstat, realpath } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { clone, digest } from './domain.mjs';

const scope = ({repository, projectId, mainSessionId, authorizedUsers, statusField}) => digest([
  repository, projectId, mainSessionId, [...new Set(authorizedUsers)].sort(), statusField.id, statusField.name,
  Object.entries(statusField.options).sort(([a],[b]) => a.localeCompare(b)).map(([stage,{id,name}]) => [stage,id,name]),
]);

export function newState(config) {
  return {schema:2, scope:scope(config),
    enabled:false, observed:null, pending:null, delivery:null, ownComments:{}, paused:false};
}
export function validateState(state, config) {
  if (!state || state.schema !== 2 || (state.scope !== scope(config) && state.scope !== digest(config)) ||
      typeof state.enabled !== 'boolean' || typeof state.paused !== 'boolean' || !state.ownComments ||
      (state.observed !== null && (typeof state.observed !== 'object' || Array.isArray(state.observed))) ||
      (state.pending !== null && (!state.pending?.id || !Array.isArray(state.pending.changes))) ||
      (state.delivery !== null && (!state.delivery?.id || !Array.isArray(state.delivery.changes))))
    throw new Error('Persisted state scope/schema mismatch; reconcile explicitly before rebinding');
  // Upgrade matching legacy fingerprints without dropping queued notices or read cursors.
  const {owner, ...current} = state;
  return clone({...current, scope:scope(config)});
}

export class FileState {
  constructor(cwd) { this.cwd = cwd; this.folder = path.join(cwd, '.pi'); this.file = path.join(this.folder, 'github-project-state.json'); }
  async assertPaths() {
    const root = await realpath(this.cwd);
    await mkdir(this.folder, {recursive:true});
    if ((await lstat(this.folder)).isSymbolicLink() || await realpath(this.folder) !== path.join(root, '.pi'))
      throw new Error('State directory must be a real workspace/.pi directory');
    try { if ((await lstat(this.file)).isSymbolicLink()) throw new Error('State file must not be a symlink'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  async load(config) {
    await this.assertPaths();
    try { return validateState(JSON.parse(await readFile(this.file, 'utf8')), config); }
    catch (error) { if (error.code === 'ENOENT') return newState(config); throw error; }
  }
  async save(state) {
    await this.assertPaths();
    const temporary = `${this.file}.${randomUUID()}.tmp`;
    await writeFile(temporary, JSON.stringify(state)+'\n', {mode:0o600, flag:'wx'});
    await rename(temporary, this.file);
  }
}
