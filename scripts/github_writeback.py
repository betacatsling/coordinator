#!/usr/bin/env python3
"""Scoped, retry-safe claim/result comments and verified Project option updates."""
import hashlib
import re


def marker_prefix(config, issue_id, kind='result'):
    if kind not in {'result','claim'}:raise ValueError('Unknown workflow marker')
    key=hashlib.sha256((config['project_node_id']+'\0'+config['repository']+'\0'+issue_id).encode()).hexdigest()[:24]
    return '<!-- project-delegation-'+kind+':'+key+':'


def is_result_comment(body, config, issue_id):
    return bool(re.search(re.escape(marker_prefix(config,issue_id))+r'[0-9a-f]{64} -->',body))


def is_workflow_comment(body, config, issue_id):
    return any(re.search(re.escape(marker_prefix(config,issue_id,kind))+r'[0-9a-f]{64} -->',body) for kind in ['result','claim'])


def validate_scope(config, task, live_project, query):
    from github_project_inputs import normalize_project
    if live_project.get('id')!=config['project_node_id']:raise ValueError('Write-back Project scope mismatch')
    matching=[i for i in live_project['items']['nodes'] if (i.get('content') or {}).get('id')==task['issue_id']]
    if len(matching)!=1:raise ValueError('Issue is not uniquely in selected Project')
    item=matching[0];issue=item['content']
    if issue.get('__typename')!='Issue' or issue.get('repository',{}).get('nameWithOwner')!=config['repository']:raise ValueError('Write-back repository scope mismatch')
    ignored=[c['id'] for c in issue['comments']['nodes'] if c.get('author',{}).get('login','').lower()==config['user_login'].lower() and is_workflow_comment(c.get('body',''),config,task['issue_id'])]
    current=normalize_project(live_project,config['project_node_id'],config['user_login'],ignored,config['repository'])
    match=next((t for t in current if t['issue_id']==task['issue_id']),None)
    if not match or match['revision_hash']!=task['revision_hash']:raise ValueError('Issue revision changed; refusing stale write-back')
    viewer=query('query { viewer { login } }')['viewer']['login']
    if viewer.lower()!=config['user_login'].lower():raise ValueError('Write-back authenticated author mismatch')
    return item,issue,viewer


def status_operations(config, item, query, stage):
    mapping=config.get('writeback',{}).get('status');key=stage+'_option_id'
    if not mapping or key not in mapping:return []
    fields=query('query($id:ID!){node(id:$id){... on ProjectV2{fields(first:100){pageInfo{hasNextPage} nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}}}}',id=config['project_node_id'])['node']['fields']
    if fields['pageInfo']['hasNextPage']:raise ValueError('Incomplete fields mapping')
    field=next((f for f in fields['nodes'] if f.get('id')==mapping['field_id']),None)
    option=next((o for o in (field or {}).get('options',[]) if o['id']==mapping[key]),None)
    if not option or option['name']!=mapping[stage+'_option_name']:raise ValueError('Unknown/changed Project status; refusing guess')
    current=next((v.get('optionId') for v in item.get('fieldValues',{}).get('nodes',[]) if v.get('field',{}).get('id')==field['id']),None)
    return [] if current==option['id'] else [{'operation':'set_status','item_id':item['id'],'field_id':field['id'],'option_id':option['id']}]


def apply(config, task, operations, comment_id, query, dry_run):
    if not dry_run:
        for op in operations:
            if op['operation']=='add_comment':
                comment_id=query('mutation($id:ID!,$body:String!){addComment(input:{subjectId:$id,body:$body}){commentEdge{node{id}}}}',id=task['issue_id'],body=op['body'])['addComment']['commentEdge']['node']['id']
            elif op['operation']=='update_comment':
                query('mutation($id:ID!,$body:String!){updateIssueComment(input:{id:$id,body:$body}){issueComment{id}}}',id=comment_id,body=op['body'])
            else:
                query('mutation($project:ID!,$item:ID!,$field:ID!,$option:String!){updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:{singleSelectOptionId:$option}}){projectV2Item{id}}}',project=config['project_node_id'],item=op['item_id'],field=op['field_id'],option=op['option_id'])
    return {'dry_run':dry_run,'operations':operations,'comment_id':comment_id}


def own_comment(issue, viewer, marker):
    existing=[c for c in issue['comments']['nodes'] if marker in c.get('body','') and c.get('author',{}).get('login','').lower()==viewer.lower()]
    if len(existing)>1:raise ValueError('Duplicate own workflow markers; reconcile explicitly')
    return existing[0] if existing else None


def write_claim(config, task, live_project, query, dry_run=True):
    item,issue,viewer=validate_scope(config,task,live_project,query)
    marker=marker_prefix(config,task['issue_id'],'claim')+task.get('dispatch_key',task['revision_hash'])+' -->'
    existing=own_comment(issue,viewer,marker)
    # A recovered claim must not regress a later status or post another comment.
    if existing:return {'dry_run':dry_run,'operations':[],'comment_id':existing['id'],'recovered':True}
    if config.get('board'):
        from github_board import assert_claimable
        assert_claimable(live_project,config,task)
    number=issue.get('number') or (task.get('url') or '').rstrip('/').split('/')[-1]
    body=marker+'\n已领取，开始协调处理。\n\n任务标识：#'+str(number)+' / '+task.get('dispatch_key',task['revision_hash'])[:12]+'。后续会在此 Issue 更新执行与验收结果。'
    status=status_operations(config,item,query,'claimed')
    # Validate the mapping first, then set status before commenting, allowing safe recovery.
    return apply(config,task,status+[{'operation':'add_comment','body':body,'comment_id':None}],None,query,dry_run)


def write_result(config, task, live_project, result, report, accepted, query, dry_run=True):
    item,issue,viewer=validate_scope(config,task,live_project,query)
    marker=marker_prefix(config,task['issue_id'])+task.get('dispatch_key',task['revision_hash'])+' -->'
    existing=own_comment(issue,viewer,marker)
    body=marker+'\n'+('验收通过（隔离工作区，尚未合并）。' if accepted else '协调结果（尚未完成实现）。')+'\n\n'+str(result)[:1800]
    if report.get('url'):body+='\n\n[HTML 报告]('+report['url']+')'
    else:body+='\n\nHTML 报告已生成，私有访问地址尚未配置。'
    operations=[];comment_id=existing['id'] if existing else None
    if not existing or existing.get('body')!=body:operations.append({'operation':'update_comment' if existing else 'add_comment','body':body,'comment_id':comment_id})
    if accepted:operations+=status_operations(config,item,query,'accepted')
    return apply(config,task,operations,comment_id,query,dry_run)


def write_executor_session(config, task, live_project, thread_id, query, dry_run=True):
    import uuid
    if str(uuid.UUID(thread_id))!=thread_id:raise ValueError('Actual executor native ID required')
    item,issue,viewer=validate_scope(config,task,live_project,query)
    marker=marker_prefix(config,task['issue_id'],'claim')+task.get('dispatch_key',task['revision_hash'])+' -->'
    existing=own_comment(issue,viewer,marker)
    if not existing:raise ValueError('No owned claim; refuse new executor notice')
    label='执行会话：`'+thread_id+'`'
    body=existing['body']
    if label in body:return {'dry_run':dry_run,'operations':[],'comment_id':existing['id']}
    # Append once to the same claim; no extra comment per polling/recovery.
    operations=[{'operation':'update_comment','body':body+'\n\n'+label,'comment_id':existing['id']}]
    return apply(config,task,operations,existing['id'],query,dry_run)
