import { spawn } from 'node:child_process';

// Authentication stays inside gh. No token files, environment values, or
// credentials are inspected or copied by this extension.
export function ghGraphQL(query, variables = {}, signal) {
  return new Promise((resolve, reject) => {
    const child = spawn('gh', ['api', '--hostname', 'github.com', 'graphql', '--input', '-'],
      {stdio:['pipe','pipe','pipe'], signal});
    let stdout = ''; let size = 0; let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; child.kill(); }, 45000);
    const finishError = () => reject(new Error(timedOut ? 'GitHub request timed out' : 'GitHub request failed; check gh access locally'));
    child.stdout.on('data', chunk => {
      size += chunk.length;
      if (size > 64 * 1024 * 1024) child.kill();
      else stdout += chunk.toString('utf8');
    });
    child.stderr.resume(); // Never echo potentially sensitive gh diagnostics.
    child.on('error', () => {clearTimeout(timer); finishError();});
    child.on('close', code => {
      clearTimeout(timer);
      if (code !== 0 || timedOut || size > 64 * 1024 * 1024) return finishError();
      try {
        const result = JSON.parse(stdout);
        if (result.errors?.length || !result.data) throw new Error('GitHub GraphQL request rejected');
        resolve(result.data);
      } catch { reject(new Error('GitHub returned an invalid or rejected response')); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({query, variables}));
  });
}

const projectQuery = `query($id:ID!,$cursor:String){node(id:$id){... on ProjectV2{
  id title url
  fields(first:100){pageInfo{hasNextPage endCursor} nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}
  items(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{
    id fieldValues(first:100){pageInfo{hasNextPage endCursor} nodes{... on ProjectV2ItemFieldSingleSelectValue{optionId field{... on ProjectV2SingleSelectField{id}}}}}
    content{__typename ... on Issue{id number repository{nameWithOwner}}}
  }}
}}}`;
const issueQuery = `query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){issue(number:$number){
  __typename id number title body url state author{login} repository{nameWithOwner}
  comments(first:100){pageInfo{hasNextPage endCursor} nodes{id body url author{login}}}
}}}`;
const commentQuery = `query($owner:String!,$name:String!,$number:Int!,$cursor:String){repository(owner:$owner,name:$name){issue(number:$number){
  id repository{nameWithOwner}
  comments(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{id body url author{login}}}
}}}`;

function nextCursor(connection, seen) {
  const cursor = connection?.pageInfo?.endCursor;
  if (!cursor || seen.has(cursor)) throw new Error('GitHub pagination did not advance');
  seen.add(cursor); return cursor;
}

export class GitHub {
  constructor(query = ghGraphQL) { this.query = query; }
  async fetchProject(config, signal) {
    let project; let cursor = null; const items = []; const seen = new Set();
    do {
      const page = (await this.query(projectQuery, {id:config.projectId, cursor}, signal)).node;
      if (!page || page.id !== config.projectId || !page.items?.pageInfo || !Array.isArray(page.items.nodes))
        throw new Error('Selected Project is unavailable');
      project = page; items.push(...page.items.nodes);
      if (!page.items.pageInfo.hasNextPage) break;
      cursor = nextCursor(page.items, seen);
    } while (true);
    const [owner,name]=config.repository.split('/');
    for (const item of items) {
      const member = item?.content;
      // Project membership only exposes IDs/numbers/repository metadata. Body
      // and comments are fetched solely through the fixed repository endpoint.
      if (member?.__typename !== 'Issue' || member.repository?.nameWithOwner !== config.repository) continue;
      const variables={owner,name,number:member.number};
      const issue=(await this.query(issueQuery,variables,signal)).repository?.issue;
      if (!issue || issue.id !== member.id || issue.__typename !== 'Issue' || issue.repository?.nameWithOwner !== config.repository)
        throw new Error('Issue identity/repository changed during scoped read');
      item.content=issue;
      const comments = issue.comments;
      if (!comments?.pageInfo || !Array.isArray(comments.nodes)) throw new Error('Issue comments unavailable');
      const commentCursors = new Set();
      while (comments.pageInfo.hasNextPage) {
        const after = nextCursor(comments, commentCursors);
        const scoped=(await this.query(commentQuery, {...variables,cursor:after}, signal)).repository?.issue;
        if (!scoped || scoped.id !== issue.id || scoped.repository?.nameWithOwner !== config.repository)
          throw new Error('Issue identity/repository changed during comment pagination');
        const page=scoped.comments;
        if (!page?.pageInfo || !Array.isArray(page.nodes)) throw new Error('Issue comments unavailable');
        comments.nodes.push(...page.nodes); comments.pageInfo = page.pageInfo;
      }
    }
    project.items = {nodes:items, pageInfo:{hasNextPage:false}};
    return project;
  }
  async viewer(signal) {
    const login = (await this.query('query { viewer { login } }', {}, signal)).viewer?.login;
    if (!login) throw new Error('GitHub viewer unavailable');
    return login;
  }
  async addComment(issueId, body, signal) {
    const data = await this.query(`mutation($id:ID!,$body:String!){addComment(input:{subjectId:$id,body:$body}){commentEdge{node{id}}}}`,
      {id:issueId, body}, signal);
    const id = data.addComment?.commentEdge?.node?.id;
    if (!id) throw new Error('Comment write not confirmed');
    return id;
  }
  async setStatus(config, issue, optionId, signal) {
    const data = await this.query(`mutation($project:ID!,$item:ID!,$field:ID!,$option:String!){updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:{singleSelectOptionId:$option}}){projectV2Item{id}}}`,
      {project:config.projectId, item:issue.itemId, field:config.statusField.id, option:optionId}, signal);
    if (data.updateProjectV2ItemFieldValue?.projectV2Item?.id !== issue.itemId) throw new Error('Status write not confirmed');
  }
}
