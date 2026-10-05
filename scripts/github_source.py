#!/usr/bin/env python3
"""GitHub GraphQL transport and read-only project snapshot loading."""
import json
from pathlib import Path
import subprocess


def gh(query, **variables):
    cmd=['gh','api','graphql','-f','query='+query]
    for key,value in variables.items():
        if value is not None:cmd+=['-f',key+'='+str(value)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
    if r.returncode:raise RuntimeError(r.stderr.strip())
    value=json.loads(r.stdout)
    if value.get('errors'):raise RuntimeError('GitHub query rejected: '+json.dumps(value['errors']))
    return value['data']


def fetch(config):
    if config['source']['type']=='fixture':
        return json.loads(Path(config['source']['path']).read_text())
    if config['source']['type']!='github':raise ValueError('Unknown source type')
    query="""query($id:ID!,$cursor:String){
      node(id:$id){... on ProjectV2{
        id title url
        views(first:100){pageInfo{hasNextPage} nodes{id name filter layout}}
        fields(first:100){pageInfo{hasNextPage} nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}
        items(first:100,after:$cursor){
          pageInfo{hasNextPage endCursor} nodes{id fieldValues(first:100){pageInfo{hasNextPage} nodes{... on ProjectV2ItemFieldSingleSelectValue{optionId field{... on ProjectV2SingleSelectField{id}}}}} content{
            __typename ... on Issue{
              id number title body url state author{login} repository{nameWithOwner}
              comments(first:100){pageInfo{hasNextPage endCursor} nodes{id body author{login}}}
            }
          }}
        }
      }}
    }"""
    items=[];cursor=None;project=None
    while True:
        page=gh(query,id=config['project_node_id'],cursor=cursor)['node']
        if not page:raise ValueError('Selected node is not an accessible GitHub Project')
        project=page;items.extend(page['items']['nodes']);info=page['items']['pageInfo']
        if not info['hasNextPage']:break
        cursor=info['endCursor']
    for item in items:
        issue=item.get('content') or {}
        if issue.get('__typename')!='Issue':continue
        comments=issue['comments'];cursor=comments['pageInfo'].get('endCursor')
        while comments['pageInfo'].get('hasNextPage'):
            page=gh('''query($id:ID!,$cursor:String){node(id:$id){... on Issue{comments(first:100,after:$cursor){pageInfo{hasNextPage endCursor} nodes{id body author{login}}}}}}''',id=issue['id'],cursor=cursor)['node']['comments']
            comments['nodes'].extend(page['nodes']);comments['pageInfo']=page['pageInfo'];cursor=page['pageInfo'].get('endCursor')
    project['items']={'nodes':items,'pageInfo':{'hasNextPage':False}}
    return project

