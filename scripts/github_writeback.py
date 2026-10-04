#!/usr/bin/env python3
"""Scoped, retry-safe result comments and verified Project option updates."""
import hashlib
import re


def marker_prefix(config, issue_id):
    key=hashlib.sha256((config['project_node_id']+'\0'+config['repository']+'\0'+issue_id).encode()).hexdigest()[:24]
    return '<!-- project-delegation-result:'+key+':'


def is_result_comment(body, config, issue_id):
    prefix=marker_prefix(config,issue_id)
    return bool(re.search(re.escape(prefix)+r'[0-9a-f]{64} -->',body))


def write_result(config, task, live_project, result, report, accepted, query, dry_run=True):
    from github_project_inputs import normalize_project
    if live_project.get('id')!=config['project_node_id']:raise ValueError('Write-back Project scope mismatch')
    matching=[i for i in live_project['items']['nodes'] if (i.get('content') or {}).get('id')==task['issue_id']]
    if len(matching)!=1:raise ValueError('Issue is not uniquely in selected Project')
    item=matching[0];issue=item['content']
    if issue.get('__typename')!='Issue' or issue.get('repository',{}).get('nameWithOwner')!=config['repository']:raise ValueError('Write-back repository scope mismatch')
    ignored=[c['id'] for c in issue['comments']['nodes'] if c.get('author',{}).get('login','').lower()==config['user_login'].lower() and is_result_comment(c.get('body',''),config,task['issue_id'])]
    current=normalize_project(live_project,config['project_node_id'],config['user_login'],ignored,config['repository'])
    match=next((t for t in current if t['issue_id']==task['issue_id']),None)
    if not match or match['revision_hash']!=task['revision_hash']:raise ValueError('Issue revision changed; refusing stale write-back')
    viewer=query('query { viewer { login } }')['viewer']['login']
    if viewer.lower()!=config['user_login'].lower():raise ValueError('Write-back authenticated author mismatch')
    marker=marker_prefix(config,task['issue_id'])+task['revision_hash']+' -->'
    existing=[c for c in issue['comments']['nodes'] if marker in c.get('body','') and c.get('author',{}).get('login','').lower()==viewer.lower()]
    if len(existing)>1:raise ValueError('Duplicate own result markers; reconcile explicitly')
    body=marker+'\n'+('验收通过（隔离工作区，尚未合并）。' if accepted else '协调结果（尚未完成实现）。')+'\n\n'+str(result)[:1800]
    if report.get('url'):body+='\n\n[HTML 报告]('+report['url']+')'
    else:body+='\n\nHTML 报告已生成，私有访问地址尚未配置。'
    operations=[];comment_id=existing[0]['id'] if existing else None
    if not existing or existing[0].get('body')!=body:operations.append({'operation':'update_comment' if existing else 'add_comment','body':body,'comment_id':comment_id})
    mapping=config.get('writeback',{}).get('status')
    if mapping and accepted:
        fields=query('query($id:ID!){node(id:$id){... on ProjectV2{fields(first:100){pageInfo{hasNextPage} nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}}}}',id=config['project_node_id'])['node']['fields']
        if fields['pageInfo']['hasNextPage']:raise ValueError('Incomplete fields mapping')
        field=next((f for f in fields['nodes'] if f.get('id')==mapping['field_id']),None)
        option=next((o for o in (field or {}).get('options',[]) if o['id']==mapping['accepted_option_id']),None)
        if not option or option['name']!=mapping['accepted_option_name']:raise ValueError('Unknown/changed Project status; refusing guess')
        # A verified patch awaiting merge must not be advertised as Done.
        current_option=next((v.get('optionId') for v in item.get('fieldValues',{}).get('nodes',[]) if v.get('field',{}).get('id')==field['id']),None)
        if current_option!=option['id']:operations.append({'operation':'set_status','item_id':item['id'],'field_id':field['id'],'option_id':option['id']})
    if dry_run:return {'dry_run':True,'operations':operations,'comment_id':comment_id}
    for op in operations:
        if op['operation']=='add_comment':
            comment_id=query('mutation($id:ID!,$body:String!){addComment(input:{subjectId:$id,body:$body}){commentEdge{node{id}}}}',id=task['issue_id'],body=body)['addComment']['commentEdge']['node']['id']
        elif op['operation']=='update_comment':
            query('mutation($id:ID!,$body:String!){updateIssueComment(input:{id:$id,body:$body}){issueComment{id}}}',id=comment_id,body=body)
        else:
            query('mutation($project:ID!,$item:ID!,$field:ID!,$option:String!){updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:{singleSelectOptionId:$option}}){projectV2Item{id}}}',project=config['project_node_id'],item=op['item_id'],field=op['field_id'],option=op['option_id'])
    return {'dry_run':False,'operations':operations,'comment_id':comment_id}
