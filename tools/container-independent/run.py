#!/usr/bin/python3
"""Independent container smoke probe; all host paths and Docker objects are owned by this run."""
import argparse,hashlib,json,os,pathlib,re,selectors,shutil,socket,subprocess,tempfile,time,urllib.error,urllib.request
from ws_fixture import WebSocket
argp=argparse.ArgumentParser();argp.add_argument('--repo',required=True);argp.add_argument('--state',required=True);argp.add_argument('--rcc-release',required=True);argp.add_argument('--reuse-image',help='immutable sha256 image ID to reuse instead of rebuilding');argp.add_argument('--playwright-module');argp.add_argument('--go',default='go');a=argp.parse_args()
repo=pathlib.Path(a.repo).resolve();base=pathlib.Path(a.state).resolve();assert str(base).startswith('/tmp/mindfs-container-independent-')
source=base/'source-home';private=base/'private-home'
if not source.exists():
 (source/'.config/mindfs').mkdir(parents=True);(source/'.codex/sessions').mkdir(parents=True)
 providers=[dict(id='provider-v'+str(i),name='Fixture provider '+str(i),baseUrl='http://127.0.0.1:9/provider-v'+str(i),apiKey='not-a-real-key',protocols=['openai-compatible'],modelFamilies=['openai'],models=['fixture-model'],createdAt='2026-11-09T00:00:00Z',updatedAt='2026-11-09T00:00:00Z') for i in [1,2]]
 (source/'.config/mindfs/api-providers.json').write_text(json.dumps(providers,indent=2)+'\n')
 (source/'.config/mindfs/preferences.json').write_text(json.dumps({'session_naming':{'disabled':True},'agents':{'codex':{'last_config_selection':{'type':'api_provider','id':'provider-v1','name':'Fixture provider 1'}}}})+'\n')
 (source/'.codex/config.toml').write_text('# independent fixture provider-v1\nmodel = "fixture-model"\nmodel_provider = "fixture"\n[model_providers.fixture]\nname = "Fixture"\nbase_url = "http://127.0.0.1:9/provider-v1"\nwire_api = "responses"\n')
 (source/'.codex/auth.json').write_text('{"OPENAI_API_KEY":"not-a-real-key"}\n')
 (source/'.codex/sessions/history-do-not-copy.txt').write_text('unrelated fake history\n')
 for filename in ['local-cli-tokens.json','registry.json','credentials.json']:(source/'.config/mindfs'/filename).write_text('{"fixture":"must-not-be-copied"}\n')
project=base/'project';project.mkdir(exist_ok=True);(project/'.mindfs').mkdir(exist_ok=True);(project/'.mindfs/public-sentinel').write_text('public-metadata-must-stay\n')
source_sha=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
name='mindfs-independent-'+base.name.rsplit('-',1)[-1].lower();image=name+':test';evidence=base/'evidence';evidence.mkdir(exist_ok=True)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
env={k:v for k,v in os.environ.items() if not k.startswith(('MINDFS_','MINDFS_RCC_','COMPOSE_','RCC_'))}
env.update(MINDFS_VERSION='independent-'+source_sha[:12],MINDFS_CONTAINER_HOME=str(private),MINDFS_PROJECT_DIR=str(project),MINDFS_CONTAINER_PORT=str(port),MINDFS_UID=str(os.getuid()),MINDFS_GID=str(os.getgid()),RCC_RELEASE_DIR=str(pathlib.Path(a.rcc_release).resolve()),RCC_NODE_ID='external-fixture-node',DOCKER_CONFIG=str(base/'docker-config'))
(base/'docker-config').mkdir(exist_ok=True);(base/'empty.env').touch()
override=base/'compose.independent.yaml';override.write_text('services:\n  mindfs:\n    image: '+image+'\n    environment:\n      INDEPENDENT_CODEX_LOG: /home/mindfs/.local/state/independent-codex.jsonl\n      RCC_NODE_ID: external-fixture-node\n      HTTP_PROXY: http://127.0.0.1:9\n      HTTPS_PROXY: http://127.0.0.1:9\n      NO_PROXY: 127.0.0.1,localhost\n    volumes:\n      - type: bind\n        source: '+str(base/'fixtures')+'\n        target: /fixtures\n        read_only: true\n        bind:\n          create_host_path: false\n')
compose=['bash',str(repo/'deploy/container/compose.sh'),'-f',str(override),'-p',name,'--env-file',str(base/'empty.env')]
checks=[];result={'name':name,'port':port,'image':image,'state':str(base),'source_sha':source_sha,'checks':checks};cid=None

def run(args,ok=True,timeout=120,**kwargs):
 r=subprocess.run(args,env=env,text=True,capture_output=True,timeout=timeout,**kwargs)
 if ok:assert r.returncode==0,(args,r.returncode,r.stdout[-4000:],r.stderr[-4000:])
 return r

def comp(*args,**kwargs):return run(compose+list(args),**kwargs)
def dex(*args,**kwargs):return run(['docker','exec',cid,*args],**kwargs)
def record(name,**data):checks.append(dict(name=name,passed=True,**data))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_snapshot():return {str(p.relative_to(source)):dict(sha256=digest(p),mode=p.stat().st_mode&0o777) for p in source.rglob('*') if p.is_file()}
def api(path,body=None,method=None):
 req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if body is None else json.dumps(body).encode(),method=method,headers={'Content-Type':'application/json'})
 try:r=urllib.request.urlopen(req,timeout=10)
 except urllib.error.HTTPError as ex:r=ex
 with r:
  raw=r.read().decode()
  try:body=json.loads(raw)
  except json.JSONDecodeError:body=raw
  return r.status,dict(r.headers),body

def wait_ready():
 for _ in range(180):
  try:
   if api('/health')[0]==200 and api('/api/dirs')[0]==200:return
  except (OSError,urllib.error.URLError):pass
  time.sleep(.25)
 raise AssertionError('container service not ready')

def chat(content,key=None,agent='codex',expected_error=False):
 w=WebSocket(port);rid='independent-'+str(time.time_ns());payload={'root_id':project.name,'content':content,'type':'chat','agent':agent,'model':'fixture-model'}
 if key:payload['session_key']=key
 w.send({'id':rid,'type':'session.message','payload':payload});events=[]
 try:
  for _ in range(150):
   event=w.recv();events.append(event)
   if event.get('id')==rid and event.get('type')=='session.accepted':key=event['payload']['session_key']
   if event.get('id')==rid and event.get('type')=='session.done':break
  else:raise AssertionError('turn never completed')
 finally:w.close()
 errors=[x for x in events if x.get('error') or x.get('payload',{}).get('event',{}).get('type')=='error']
 if expected_error:return key,errors,events
 assert not errors,errors
 text=''.join(x.get('payload',{}).get('event',{}).get('data',{}).get('content','') for x in events if x.get('type')=='session.stream')
 assert 'fixture-response' in text,events
 return key,text

compile_env=dict(env,CGO_ENABLED='0')
r=subprocess.run([a.go,'build','-o',str(base/'fake-codex'),str(pathlib.Path(__file__).with_name('fake_codex.go'))],env=compile_env,text=True,capture_output=True,timeout=120)
assert r.returncode==0,(r.stdout,r.stderr)
before=source_snapshot();original_project=digest(project/'.mindfs/public-sentinel')
try:
 # Exercise the delivered importer on fake source files, including explicit credential opt-ins.
 importer=[os.sys.executable,str(repo/'deploy/container/import-settings.py'),'--mindfs-config-dir',str(source/'.config/mindfs'),'--codex-home',str(source/'.codex'),'--destination',str(private),'--include-mindfs-providers','--include-codex-auth']
 r=run(importer);copied={str(p.relative_to(private)) for p in private.rglob('*') if p.is_file()}
 assert copied=={'.config/mindfs/api-providers.json','.config/mindfs/preferences.json','.codex/config.toml','.codex/auth.json'},copied
 assert source_snapshot()==before
 assert (private/'.codex/config.toml').read_bytes()==(source/'.codex/config.toml').read_bytes()
 assert all(p.stat().st_mode&0o777==(0o700 if p.is_dir() else 0o600) for p in [private,*private.rglob('*')])
 again=run(importer,ok=False);assert again.returncode!=0
 record('one-time allowlist import, permissions and immutable fake sources',files=sorted(copied),repeat_exit=again.returncode,source_sha256=before)
 # Supply fake app-server and a real, read-only RCC client release.
 (private/'.independent-fixture-owned').touch();(private/'.local/state').mkdir(parents=True,exist_ok=True)
 fixtures=base/'fixtures';fixtures.mkdir(exist_ok=True);shutil.copy2(base/'fake-codex',fixtures/'fake-codex')
 agents={'agents':[{'name':'codex','command':'/fixtures/fake-codex','protocol':'codex-sdk'},{'name':'rcc-invalid','command':'/opt/rcc/bin/rcc','protocol':'rcc','args':['--node','external-fixture-node','--independent-invalid-rcc-option']}]}
 (private/'.config/mindfs/agents.json').write_text(json.dumps(agents));(private/'.config/mindfs/agents.json').chmod(0o600)
 config=json.loads(comp('config','--format','json').stdout);service=config['services']['mindfs']
 assert not service.get('privileged') and service.get('network_mode')!='host'
 assert all(m.get('source') not in ('/var/run/docker.sock',str(pathlib.Path.home()),'/') for m in service['volumes'])
 assert service['ports'][0]['host_ip']=='127.0.0.1' and int(service['ports'][0]['published'])==port,service['ports']
 (evidence/'compose-config.json').write_text(json.dumps(config,indent=2)+'\n')
 if a.reuse_image:
  assert re.fullmatch('sha256:[a-f0-9]{64}',a.reuse_image),'--reuse-image requires an immutable image ID'
  assert run(['docker','image','inspect',a.reuse_image,'--format','{{.Id}}']).stdout.strip()==a.reuse_image
  run(['docker','tag',a.reuse_image,image]);result['reused_image_id']=a.reuse_image
 else:
  r=comp('build',timeout=1800);(evidence/'build.log').write_text(r.stdout+r.stderr)
 # Real packaged Codex: empty ephemeral HOME, no network, handshake only.
 handshake_name=name+'-codex-handshake'
 stderr=(evidence/'codex-offline-stderr.log').open('w')
 handshake=subprocess.Popen(['docker','run','--rm','-i','--name',handshake_name,'--network','none','--read-only','--tmpfs',f'/home/mindfs:rw,uid={os.getuid()},gid={os.getgid()},mode=0700','--tmpfs','/tmp:rw,mode=1777',image,'codex','app-server'],env=env,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr)
 try:
  request={'id':1,'method':'initialize','params':{'clientInfo':{'name':'mindfs-independent','version':'1.0.0'},'capabilities':{'experimentalApi':True}}}
  handshake.stdin.write(json.dumps(request)+'\n');handshake.stdin.flush()
  selector=selectors.DefaultSelector();selector.register(handshake.stdout,selectors.EVENT_READ)
  assert selector.select(timeout=20),'real Codex initialize timed out'
  response=json.loads(handshake.stdout.readline());assert response.get('id')==1 and 'result' in response,response
  offline_inspect=json.loads(run(['docker','inspect',handshake_name]).stdout)[0];assert offline_inspect['HostConfig']['NetworkMode']=='none' and all(m['Type']=='tmpfs' for m in offline_inspect['Mounts'])
  handshake.stdin.write(json.dumps({'method':'initialized'})+'\n');handshake.stdin.close();assert handshake.wait(timeout=10)==0
  record('real Codex app-server initializes offline with an empty private HOME',initialize_response=response,network_mode='none')
 finally:
  if handshake.poll() is None:run(['docker','rm','-f',handshake_name],ok=False)
  stderr.close()
 comp('up','-d','--no-build',timeout=120);cid=comp('ps','-q','mindfs').stdout.strip();assert re.fullmatch('[a-f0-9]+',cid),cid
 wait_ready()
 inspect=json.loads(run(['docker','inspect',cid]).stdout)[0];host=inspect['HostConfig'];assert not host['Privileged'] and host['NetworkMode']!='host'
 mounts=inspect['Mounts'];assert not any(m['Destination']=='/var/run/docker.sock' for m in mounts)
 assert next(m for m in mounts if m['Destination']=='/opt/rcc')['RW'] is False
 assert not any(str(source) in m['Source'] for m in mounts)
 assert api('/health')[2]=='ok';assert 'mindfs version:' in dex('mindfs','--version').stdout
 codex_version=dex('codex','--version').stdout.strip();assert 'codex-cli 0.162.1' in codex_version,codex_version
 html=api('/')[2];assert '<html' in html and re.search(r'<script[^>]+src=',html),html[:600]
 script=re.search(r'<script[^>]+src="([^"]+)"',html).group(1);status,_,js=api('/'+script.removeprefix('./').lstrip('/'));assert status==200 and len(js)>10000
 if a.playwright_module:
  browser=run(['node',str(pathlib.Path(__file__).with_name('browser_check.mjs')),a.playwright_module,f'http://127.0.0.1:{port}',str(evidence/'web.png')]);record('browser renders container web app',**json.loads(browser.stdout))
 record('delivered image and Compose start, original commands and web assets',container=cid,image_id=inspect['Image'],uid=inspect['Config']['User'],rcc_mount=next(m for m in mounts if m['Destination']=='/opt/rcc'),web_script=script,codex_version=codex_version)
 # The host's existing project metadata is masked by a private data volume.
 assert dex('test','!','-e',str(project/'.mindfs/public-sentinel')).returncode==0
 assert dex('test',str(project/'.mindfs'),'-ef','/home/mindfs/.workspace-metadata').returncode==0
 dirs=api('/api/dirs')[2];assert dirs[0]['id']==project.name,dirs
 assert api('/api/preferences/session-naming',{'disabled':True},'PUT')[0]==200
 key,text=chat('independent container first Codex turn');assert 'provider-v1' in text,text
 key2,text2=chat('independent container second Codex turn',key);assert key2==key and text2.endswith('2'),text2
 log=[json.loads(x) for x in (private/'.local/state/independent-codex.jsonl').read_text().splitlines()]
 starts=[x for x in log if x['kind']=='start'];assert starts and all(x['home']=='/home/mindfs' and x['codex_home']=='/home/mindfs/.codex' and x['argv'][1]=='app-server' for x in starts),starts
 assert any(x.get('method')=='thread/start' and x['params'].get('cwd')==str(project) for x in log)
 cli=dex('mindfs','--agents').stdout;assert 'codex' in cli and 'codex-sdk' in cli,cli
 record('actual MindFS Codex SDK starts fake app-server and completes two turns',session=key,app_server_starts=len(starts))
 # Container owns provider writes and persistence after the one-time copy.
 assert [x['id'] for x in api('/api/agent-api-providers')[2]]==['provider-v1','provider-v2']
 status,_,response=api('/api/agent-api-providers/switch',{'agent':'codex','provider_id':'provider-v2'});assert status==200,response
 assert 'provider-v2' in (private/'.codex/config.toml').read_text()
 key3,text3=chat('new process uses independent provider-v2');assert 'provider-v2' in text3,text3
 status,_,deleted=api('/api/agent-api-providers?id=provider-v1',method='DELETE');assert status==200,deleted
 assert [x['id'] for x in api('/api/agent-api-providers')[2]]==['provider-v2']
 assert source_snapshot()==before and digest(project/'.mindfs/public-sentinel')==original_project
 # Loading the actual mounted RCC executable and SDK error path needs no real login.
 helpresult=dex('/opt/rcc/bin/rcc','--help');assert 'rcc' in helpresult.stdout and '--node' in helpresult.stdout
 _,errors,events=chat('RCC mounted executable validation',agent='rcc-invalid',expected_error=True)
 assert errors and '客户端参数无效' in json.dumps(errors,ensure_ascii=False),events
 generated=json.loads((private/'.config/mindfs/container-rcc.json').read_text());assert generated['agents'][0]['args']==['--node','external-fixture-node'],generated
 record('real read-only RCC release loads, explicit node option and MindFS SDK diagnostic path',rcc_sha256=digest(pathlib.Path(a.rcc_release)/'bin/rcc'),connection='not requested; no container-node registration or external model session')
 (evidence/'pre-restart-sessions.json').write_text(json.dumps(api('/api/sessions?root='+project.name)[2],ensure_ascii=False,indent=2)+'\n')
 comp('restart','mindfs',timeout=90);wait_ready()
 assert [x['id'] for x in api('/api/agent-api-providers')[2]]==['provider-v2']
 agents=api('/api/agents')[2]['agents'];assert next(x for x in agents if x['name']=='codex')['last_config_selection']['id']=='provider-v2',agents
 assert key in [x['key'] for x in api('/api/sessions?root='+project.name)[2]['items']]
 _,resumed=chat('same persisted conversation after container restart',key);assert 'provider-v2' in resumed,resumed
 assert source_snapshot()==before and digest(project/'.mindfs/public-sentinel')==original_project
 record('provider changes, copied config and session DB persist across restart; source and host metadata unchanged',source_unchanged=True,public_metadata_sha256=original_project)
 old_cid=cid;comp('down','--remove-orphans',timeout=90);comp('up','-d','--no-build',timeout=120);cid=comp('ps','-q','mindfs').stdout.strip();assert cid!=old_cid;wait_ready()
 assert [x['id'] for x in api('/api/agent-api-providers')[2]]==['provider-v2']
 assert key in [x['key'] for x in api('/api/sessions?root='+project.name)[2]['items']]
 assert source_snapshot()==before and digest(project/'.mindfs/public-sentinel')==original_project
 record('new container retains the private volume state',old_container=old_cid,new_container=cid)

 result['passed']=True
except Exception as exc:
 result['passed']=False;result['failure']=repr(exc);raise
finally:
 if cid:
  try:(evidence/'container.log').write_text(comp('logs','--no-color','mindfs',ok=False).stdout)
  except Exception:pass
 try:comp('down','--remove-orphans',timeout=90)
 except Exception as exc:result['cleanup_failure']=repr(exc)
 result['remaining_owned_containers']=run(['docker','ps','-aq','--filter','label=com.docker.compose.project='+name],ok=False).stdout.split()
 result['remaining_owned_networks']=run(['docker','network','ls','-q','--filter','label=com.docker.compose.project='+name],ok=False).stdout.split()
 if result['remaining_owned_containers'] or result['remaining_owned_networks'] or result.get('cleanup_failure'):result['passed']=False
 (base/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
