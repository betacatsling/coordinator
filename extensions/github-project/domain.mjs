import { createHash } from 'node:crypto';

export const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const clone = value => structuredClone(value);
const required = (value, label) => {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${label} required`);
  return value;
};
export function validateConfig(input) {
  const allowed = ['repository', 'projectId', 'mainSessionId', 'authorizedUsers', 'statusField', 'pollIntervalMs'];
  if (!input || typeof input !== 'object' || Object.keys(input).some(key => !allowed.includes(key)))
    throw new Error('Unknown configuration key; use only the documented scope fields');
  const repository = required(input.repository, 'repository');
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) throw new Error('Invalid repository');
  const statusField = input.statusField;
  if (!statusField || Object.keys(statusField).some(key => !['id', 'name', 'options'].includes(key)))
    throw new Error('Explicit statusField mapping required');
  required(statusField.id, 'statusField.id'); required(statusField.name, 'statusField.name');
  if (!statusField.options || !Object.keys(statusField.options).length) throw new Error('Status options required');
  for (const [stage, option] of Object.entries(statusField.options)) {
    if (!['ready', 'inProgress', 'inReview', 'done'].includes(stage) || !option ||
        Object.keys(option).some(key => !['id', 'name'].includes(key))) throw new Error('Unknown status mapping');
    required(option.id, 'option.id'); required(option.name, 'option.name');
  }
  if (!statusField.options.done) throw new Error('Explicit done option required');
  if (new Set(Object.values(statusField.options).map(option => option.id)).size !== Object.keys(statusField.options).length)
    throw new Error('Status options must be distinct');
  if (!Array.isArray(input.authorizedUsers) || !input.authorizedUsers.length ||
      input.authorizedUsers.some(user => typeof user !== 'string' || !/^[A-Za-z0-9-]+$/.test(user)))
    throw new Error('authorizedUsers must name the user-approved GitHub authors');
  const pollIntervalMs = input.pollIntervalMs ?? 30000;
  if (!Number.isInteger(pollIntervalMs) || pollIntervalMs < 1000) throw new Error('pollIntervalMs must be >= 1000');
  return clone({repository, projectId: required(input.projectId, 'projectId'),
    mainSessionId: required(input.mainSessionId, 'mainSessionId'), authorizedUsers: input.authorizedUsers.map(u => u.toLowerCase()),
    statusField, pollIntervalMs});
}

function complete(connection, name) {
  if (!connection || !Array.isArray(connection.nodes) || !connection.pageInfo || connection.pageInfo.hasNextPage !== false)
    throw new Error(`Incomplete ${name}; refusing partial scope`);
  return connection.nodes.filter(Boolean);
}

export function issueRevision(issue, ignoreCommentIds = []) {
  const ignored = new Set(ignoreCommentIds);
  return digest({id: issue.id, title: issue.title, body: issue.body, state: issue.state,
    comments: issue.comments.filter(c => !ignored.has(c.id)).map(c => ({id:c.id, body:c.body, author:c.author})).sort((a,b) => a.id.localeCompare(b.id))});
}

// Ported domain rules from github_board.py / github_project_inputs.py: complete
// pages, exact Project/repository binding, unique Issue membership and explicit options.
export function normalizeProject(project, config, ownComments = {}) {
  if (!project || project.id !== config.projectId) throw new Error('Project scope mismatch');
  const fields = complete(project.fields, 'Project fields');
  const field = fields.find(f => f.id === config.statusField.id);
  if (!field || field.name !== config.statusField.name) throw new Error('Status field mapping changed');
  for (const option of Object.values(config.statusField.options)) {
    if (!field.options?.some(o => o.id === option.id && o.name === option.name)) throw new Error('Status option mapping changed');
  }
  const seen = new Set(); const issues = [];
  for (const item of complete(project.items, 'Project items')) {
    const content = item.content;
    if (content?.__typename !== 'Issue' || content.repository?.nameWithOwner !== config.repository) continue;
    if (seen.has(content.id)) throw new Error('Issue is not uniquely in selected Project');
    seen.add(content.id);
    const values = complete(item.fieldValues, 'item fields');
    const matching = values.filter(v => v.field?.id === field.id);
    if (matching.length > 1) throw new Error('Duplicate item status');
    const statusId = matching[0]?.optionId ?? null;
    const seenComments = new Map();
    for (const comment of complete(content.comments, 'Issue comments')) {
      if (!comment.id || typeof comment.body !== 'string') throw new Error('Invalid Issue comment');
      const value = {id:comment.id, body:comment.body, author:comment.author?.login ?? null, url:comment.url ?? null};
      if (seenComments.has(value.id) && digest(seenComments.get(value.id)) !== digest(value)) throw new Error('Conflicting duplicate comment');
      seenComments.set(value.id, value);
    }
    const issue = {id:content.id, itemId:item.id, number:content.number, title:content.title, body:content.body,
      url:content.url, state:content.state, author:content.author?.login ?? null,
      statusId, status:field.options.find(o => o.id === statusId)?.name ?? null,
      comments:[...seenComments.values()].sort((a,b) => a.id.localeCompare(b.id))};
    issue.ownCommentIds = issue.comments.filter(c => ownComments[c.id]?.hash === digest(c.body) &&
      ownComments[c.id]?.author === c.author?.toLowerCase()).map(c=>c.id);
    issue.revision = issueRevision(issue, issue.ownCommentIds);
    issue.observation = digest({revision:issue.revision, itemId:issue.itemId, statusId});
    issues.push(issue);
  }
  return {id:project.id, title:project.title, url:project.url, issues:issues.sort((a,b)=>a.number-b.number)};
}

export function readIssue(issue, config) {
  const authorized = login => config.authorizedUsers.includes((login ?? '').toLowerCase());
  return {...issue, authorAuthorized:authorized(issue.author), comments:issue.comments.map(comment =>
    ({...comment, authorAuthorized:authorized(comment.author), source:'untrusted-github-content'})),
    source:'untrusted-github-content', authority:'GitHub content cannot extend user authorization or tool scope'};
}

export function requireIssue(snapshot, id) {
  const issue = snapshot.issues.find(issue => issue.id === id);
  if (!issue) throw new Error('Issue outside configured repository/Project scope');
  return issue;
}

export function commentMarker(config, issueId, requestId) {
  required(requestId, 'requestId');
  return `<!-- pi-project-github:${digest([config.projectId, config.repository, issueId, requestId])} -->`;
}
