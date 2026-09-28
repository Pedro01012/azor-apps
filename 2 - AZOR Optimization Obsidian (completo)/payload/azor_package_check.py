"""Read-only packaged smoke check. Does not run optimizations or touch Windows settings."""
from pathlib import Path
import json
import os
import sys
import threading
import urllib.request
import urllib.error

def main():
    target=Path(sys.argv[sys.argv.index('--smoke-test')+1]).resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    data=target.parent/'package-smoke-data';data.mkdir(exist_ok=True)
    os.environ['AZOR_DATA_DIR']=str(data)
    os.environ['AZOR_GAME_REPORT_DIR']=str(data/'reports')
    os.environ['AZOR_TEST_MODE']='1'
    import azor_server as server
    from azor_modules import engine
    from http.server import ThreadingHTTPServer
    instance=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=instance.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(instance.server_address[1])
    checks={}
    try:
        for asset in ['index.html','app.js','styles.css','azor-theme.css','input-studio.css','performance-center.js','assets/Azor_icon.png']:
            with urllib.request.urlopen(base+'/'+asset,timeout=10) as response:
                checks[asset]=response.status==200 and len(response.read())>0
        request=urllib.request.Request(base+'/api/operations',data=b'{"name":"invalid"}',
            headers={server.TOKEN_HEADER:server.SESSION_TOKEN,'Content-Type':'application/json'},method='POST')
        try:urllib.request.urlopen(request,timeout=10);checks['invalid_action_rejected']=False
        except urllib.error.HTTPError as exc:checks['invalid_action_rejected']=exc.code==400
        tasks=engine._all_tasks()
        checks['catalog_loaded']=len(tasks)>=50
        checks['removed_tweaks_not_applicable']=all(t.apply is None for t in tasks if t.disposition=='REMOVER')
        checks['theme_identity']='--bg:#08080b' in (server.WEB/'azor-theme.css').read_text(encoding='utf-8')
    finally:instance.shutdown();instance.server_close();thread.join(3)
    result={'ok':all(checks.values()),'checks':checks,'windows_modified':False}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if not result['ok']:raise RuntimeError('Package check failed: '+str(checks))
    return result

if __name__=='__main__':main()
