import importlib.util,sys,types,tempfile,threading,ast
from pathlib import Path
root=Path(sys.argv[1])
for p in root.rglob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
profile=tempfile.TemporaryDirectory();settings={'api_url':'https://example.invalid','access_token':'fake','enabled':True,'resume_enabled':False,'completion_threshold':90,'progress_sync_interval':30}
class Addon:
 def getAddonInfo(self,k):return {'path':str(root),'profile':profile.name,'version':'0.2.2'}[k]
 def getSettingString(self,k):return str(settings.get(k,''))
 def getSettingBool(self,k):return bool(settings.get(k,False))
 def getSettingInt(self,k):return settings.get(k,0)
 def setSettingString(self,k,v):settings[k]=v
sys.modules['xbmcaddon']=types.SimpleNamespace(Addon=Addon)
sys.modules['xbmc']=types.SimpleNamespace(LOGINFO=1,LOGWARNING=2,LOGDEBUG=0,log=lambda *a:None,Monitor=object)
sys.modules['xbmcgui']=types.SimpleNamespace(Dialog=lambda:types.SimpleNamespace(notification=lambda *a,**k:None))
sys.modules['xbmcvfs']=types.SimpleNamespace(translatePath=lambda x:x,mkdirs=lambda x:None)
sys.path.insert(0,str(root/'resources/lib'))
import api
spec=importlib.util.spec_from_file_location('replay_service',root/'service.py');service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
def item(n,p,watched=False):return dict(mediaType='movie',tmdbId=n,percentage=p,positionSeconds=p*10,durationSeconds=1000,watched=watched)
api._write_outbox([item(1,10)])
sent=[];api._post_progress=lambda b,t,p:(sent.append(p) or True,False)
assert api.sync_progress(item(1,50))
assert sent[-1]['percentage']==50 and api._read_outbox()==[]
api._write_outbox([item(1,100,True)])
assert api.sync_progress(item(1,20)) and sent[-1]['watched']
api._write_outbox([item(n,10) for n in range(100)])
calls=[];api._post_progress=lambda *a:(calls.append(1) and False,True)
assert not api.flush_pending_progress() and len(calls)==1 and len(api._read_outbox())==100
api._write_outbox([item(1,10)]);entered=threading.Event();release=threading.Event()
def slow(*args):entered.set();assert release.wait(3);return True,False
api._post_progress=slow
t=threading.Thread(target=api.flush_pending_progress);t.start();assert entered.wait(2)
q=threading.Thread(target=lambda:api.queue_progress(item(2,40)));q.start();release.set();t.join(3);q.join(3)
assert not t.is_alive() and not q.is_alive() and api._read_outbox()==[item(2,40)]
tracker=service.PlaybackTracker();tracker.payload=item(1,10);tracker.signature='old';tracker.source_key=('old',);tracker.playing_file='old.mkv';tracker.position_seconds=120;tracker.duration_seconds=1000;tracker.player_active=True
tracker._active_video_player_id=lambda:1;tracker._payload_for_item=lambda i:(None,None)
saved=[];service.sync_progress=lambda p:saved.append(p) or True
service.json_rpc=lambda method,params: {'item':{'file':'new.mkv'}} if method=='Player.GetItem' else {'time':{'seconds':30},'totaltime':{'minutes':20}}
tracker.poll();assert tracker.payload is None and saved and saved[0]['tmdbId']==1
print('PASS Kodi: syntax; stale queue; completion preservation; bounded retries; concurrent flush; unrecognized next title')
profile.cleanup()
