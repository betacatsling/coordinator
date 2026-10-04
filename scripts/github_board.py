#!/usr/bin/env python3
"""Explicit verified TODO-view scope and status transition admission."""
import hashlib


def board_members(project, config):
    if project.get('id')!=config['project_node_id']:raise ValueError('Board Project scope mismatch')
    if project.get('items',{}).get('pageInfo',{}).get('hasNextPage'):raise ValueError('Incomplete Project items')
    b=config['board'];views=project.get('views',{})
    if views.get('pageInfo',{}).get('hasNextPage'):raise ValueError('Incomplete Project views')
    view=next((v for v in views.get('nodes',[]) if v.get('id')==b['view_id']),None)
    if not view or view.get('filter')!=b['view_filter'] or view.get('layout')!='BOARD_LAYOUT':raise ValueError('Selected board view/filter changed; refuse broader intake')
    fields=project.get('fields',{})
    if fields.get('pageInfo',{}).get('hasNextPage'):raise ValueError('Incomplete Project fields')
    for field_key,option_key,name_key in [('status_field_id','ready_option_id','ready_option_name'),('type_field_id','excluded_type_option_id','excluded_type_option_name')]:
        field=next((f for f in fields.get('nodes',[]) if f.get('id')==b[field_key]),None)
        option=next((o for o in (field or {}).get('options',[]) if o['id']==b[option_key]),None)
        if not option or option['name']!=b[name_key]:raise ValueError('Board option mapping changed; refuse guessed scope')
    members={}
    for item in project['items']['nodes']:
        issue=item.get('content') or {}
        if issue.get('__typename')!='Issue' or issue.get('repository',{}).get('nameWithOwner')!=config['repository']:continue
        if issue['id'] in members:raise ValueError('Issue is not uniquely in selected Project')
        values=item.get('fieldValues',{})
        if values.get('pageInfo',{}).get('hasNextPage'):raise ValueError('Incomplete board item fields')
        options={v.get('field',{}).get('id'):v.get('optionId') for v in values.get('nodes',[])}
        excluded=options.get(b['type_field_id'])==b['excluded_type_option_id']
        ready=options.get(b['status_field_id'])==b['ready_option_id']
        members[issue['id']]={'eligible':ready and not excluded,'excluded':excluded,'status_option_id':options.get(b['status_field_id']),'item_id':item['id']}
    return members


def select_tasks(project, config, tasks, observations):
    members=board_members(project,config);selected=[]
    for issue_id in set(observations)-set(members):observations[issue_id]['eligible']=False
    for issue_id,value in members.items():
        previous=observations.get(issue_id,{'eligible':False,'generation':0})
        generation=previous['generation']+(1 if value['eligible'] and not previous['eligible'] else 0)
        observations[issue_id]=dict(value,generation=generation)
    for task in tasks:
        observed=observations.get(task['issue_id'],{})
        if not observed.get('eligible'):continue
        task=dict(task);task['ready_generation']=observed['generation']
        task['dispatch_key']=hashlib.sha256((task['issue_id']+'\0'+task['revision_hash']+'\0'+str(observed['generation'])).encode()).hexdigest()
        selected.append(task)
    return selected


def assert_claimable(project, config, task):
    if not board_members(project,config).get(task['issue_id'],{}).get('eligible'):raise ValueError('Card is no longer an eligible TODO/待做 task; do not claim')
