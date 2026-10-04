#!/usr/bin/env python3
"""Pure normalization of selected Project Issue bodies and user-authored comments."""
import hashlib
import json

def normalize_project(project, selected_node_id, user_login, result_comment_ids=(), selected_repository=None):
    if project.get('id') != selected_node_id:
        raise ValueError('Project identity does not match the selected binding')
    ignored=set(result_comment_ids);tasks=[]
    items=project.get('items',{})
    if items.get('pageInfo',{}).get('hasNextPage'):
        raise ValueError('Incomplete Project page; fetch all pages before normalization')
    for item in items.get('nodes',[]):
        issue=item.get('content') or {}
        if issue.get('__typename')!='Issue':continue
        if selected_repository and (issue.get('repository') or {}).get('nameWithOwner') != selected_repository:
            continue
        comments=issue.get('comments',{})
        if comments.get('pageInfo',{}).get('hasNextPage'):
            raise ValueError('Incomplete Issue comment page; fetch all pages before normalization')
        body=issue.get('body','') if (issue.get('author') or {}).get('login','').lower()==user_login.lower() else ''
        accepted=[{'id':c['id'],'body':c.get('body','')} for c in comments.get('nodes',[])
                  if c.get('id') not in ignored and (c.get('author') or {}).get('login','').lower()==user_login.lower()]
        if not body.strip() and not any(c['body'].strip() for c in accepted):continue
        accepted.sort(key=lambda c:c['id'])
        revision={'issue_id':issue['id'],'body':body,'comments':accepted}
        digest=hashlib.sha256(json.dumps(revision,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        tasks.append({'issue_id':issue['id'],'url':issue.get('url'),'instructions':body,
                      'user_comments':accepted,'revision_hash':digest})
    return tasks
