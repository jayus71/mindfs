#!/usr/bin/env python3
"""Independent actual RCC/official Claude VM fixture driver; no production access."""
import argparse, hashlib, json, os, pathlib, subprocess, sys, time
sys.dont_write_bytecode = True

p=argparse.ArgumentParser()
p.add_argument('--rcc-source',type=pathlib.Path,required=True)
p.add_argument('--state',type=pathlib.Path,required=True)
p.add_argument('--rcc',type=pathlib.Path,required=True)
p.add_argument('--test-binary',type=pathlib.Path)
p.add_argument('action',choices=['setup','basic','resume','question','terminate','cancel-resume'])
a=p.parse_args()
sys.path.insert(0,str(a.rcc_source/'tools/reset-s3'))
import integration, integration_vm
f=integration.Fixture(argparse.Namespace(state=a.state,rcc=a.rcc))
if a.action=='setup':
    f.services();f.account();f.mock(empty=True)
    print('Independent isolated actual RCC fixture configured')
    sys.exit(0)
assert a.test_binary
steps=[]
if a.action in ('question','cancel-resume'):
    steps=[{'name':'Write','input':{'file_path':str(f.project/'permission-created.txt'),'content':'MINDFS_RCC_NODE_WRITE\n'}}, {'name':'Read','input':{'file_path':str(f.project/'permission-created.txt')}}, {'name':'Bash','input':{'command':'cat permission-created.txt; printf MINDFS_RCC_NODE_BASH'}}, {'name':'AskUserQuestion','input':{'questions':[{'question':'Pick a color?','header':'Color','options':[{'label':'Blue','description':'Blue option'},{'label':'Red','description':'Red option'}],'multiSelect':False}]}}]
f.mock(empty=True)
f.remote('runtime',['python3','-c','import pathlib,sys;p=pathlib.Path("/opt/rcc87s3/mock-steps.json");p.write_text(sys.stdin.read());p.chmod(0o444)'],json.dumps(steps))
# Restart the mock so it loads this scenario's controlled sequence.
f.remote('runtime',['systemctl','restart','rcc87s3-mock.service'])
url=f.remote('runtime',['python3','-c','import pathlib,time;p=pathlib.Path("/srv/rcc87s3/home/alice/mock-url");time.sleep(1);print(p.read_text().strip())']).stdout.strip()
f.guest('settings',{'name':'alice','env':{'ANTHROPIC_BASE_URL':url,'ANTHROPIC_API_KEY':'s0-mock-only'}})
env=dict(os.environ,RCC_INDEPENDENT_STATE=str(a.state),RCC_INDEPENDENT_BINARY=str(a.rcc),RCC_INDEPENDENT_SCENARIO=a.action,HOME=str(a.state/'client-home'))
start=time.monotonic()
result=subprocess.run([str(a.test_binary),'-test.run','^TestRCCIndependentActualIntegration$','-test.v','-test.timeout','240s'],env=env,capture_output=True,text=True,timeout=250)
record={'scenario':a.action,'exit':result.returncode,'elapsed':round(time.monotonic()-start,3),'stdout':result.stdout,'stderr':result.stderr}
rows=json.loads(f.remote('runtime',['python3','-c','import json,pathlib;p=pathlib.Path("/srv/rcc87s3/home/alice/mock-requests.jsonl");print(json.dumps([json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []))']).stdout)
record['mock_requests']=len(rows)
text=json.dumps(rows)
record['prompt_observed']='MINDFS_RCC_'+a.action+'_FIRST' in text
if a.action=='basic':record['second_prompt_observed']='MINDFS_RCC_BASIC_SECOND' in text
if a.action=='resume':record['previous_remote_history_observed']='MINDFS_RCC_basic_FIRST' in text and 'MINDFS_RCC_BASIC_SECOND' in text
if a.action=='question':
    record['answer_observed']='Blue' in text
    record['bash_observed']='MINDFS_RCC_NODE_BASH' in text
    record['node_created']=f.remote('node',['cat',str(f.project/'permission-created.txt')],check=False).stdout=='MINDFS_RCC_NODE_WRITE\n'
    record['host_created']=(f.project/'permission-created.txt').exists()
    assert not record['host_created']
record['status']='passed' if result.returncode==0 else 'failed'
if a.action not in ('terminate','cancel-resume') and not record['prompt_observed']:record['status']='failed'
if a.action=='basic' and not record['second_prompt_observed']:record['status']='failed'
if a.action=='resume' and not record['previous_remote_history_observed']:record['status']='failed'
if a.action=='cancel-resume':record['resumed_prompt_observed']='MINDFS_RCC_CANCEL_RESUMED' in text
if a.action=='question' and not(record['answer_observed'] and record['node_created']):record['status']='failed'
(a.state/('mindfs-'+a.action+'-result.json')).write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
sys.exit(0 if record['status']=='passed' else 1)
