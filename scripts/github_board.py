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
    if config.get('manual_dispatch'):
        field=next((f for f in fields.get('nodes',[]) if f.get('id')==b['status_field_id']),None)
        option=next((o for o in (field or {}).get('options',[]) if o['id']==b.get('triage_option_id')),None)
        if not option or option['name']!=b.get('triage_option_name'):raise ValueError('Explicit batch requires verified triage option mapping')
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


def manually_authorized(config, task, card):
    approval=config.get('manual_dispatch') or {}
    return bool(approval.get('id') and approval.get('tasks',{}).get(task['issue_id'])==task['revision_hash'] and not card.get('excluded') and card.get('status_option_id')==config['board'].get('triage_option_id'))


def select_tasks(project, config, tasks, observations):
    members=board_members(project,config);selected=[]
    for issue_id in set(observations)-set(members):observations[issue_id]['eligible']=False
    for issue_id,value in members.items():
        previous=observations.get(issue_id,{'eligible':False,'generation':0})
        generation=previous['generation']+(1 if value['eligible'] and not previous['eligible'] else 0)
        observations[issue_id]=dict(value,generation=generation)
    for task in tasks:
        observed=observations.get(task['issue_id'],{})
        manual=manually_authorized(config,task,observed)
        if not observed.get('eligible') and not manual:continue
        task=dict(task);task['ready_generation']=observed['generation']
        task['dispatch_key']=hashlib.sha256((task['issue_id']+'\0'+task['revision_hash']+'\0'+('manual:'+config['manual_dispatch']['id'] if manual else str(observed['generation']))).encode()).hexdigest()
        if manual:task['manual_dispatch_id']=config['manual_dispatch']['id']
        selected.append(task)
    return selected


def assert_claimable(project, config, task):
    card=board_members(project,config).get(task['issue_id'],{})
    if not card.get('eligible') and not manually_authorized(config,task,card):raise ValueError('Card is no longer an eligible TODO/待做 task; do not claim')


def assert_workflow_status(project, config, task, stages):
    """Require a verified, non-excluded card at an explicitly allowed stage."""
    card = board_members(project, config).get(task['issue_id'])
    mapping = config.get('writeback', {}).get('status') or {}
    if not card or card['excluded'] or mapping.get('field_id') != config['board']['status_field_id']:
        raise ValueError('Card is no longer in the owned workflow scope')
    field = next((f for f in project['fields']['nodes'] if f.get('id') == mapping['field_id']), {})
    options = {o['id']: o['name'] for o in field.get('options', [])}
    allowed = []
    for stage in stages:
        option = mapping.get(stage + '_option_id')
        if not option or options.get(option) != mapping.get(stage + '_option_name'):
            raise ValueError('Unknown/changed workflow status; refusing guess')
        allowed.append(option)
    if card['status_option_id'] not in allowed:
        raise ValueError('Card is no longer in the expected owned workflow status')
    return card
