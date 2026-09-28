"""Optional native restore point, at most once per day; local snapshots remain mandatory."""
import time
from azor_modules.transactions import read,save
from azor_modules.base import normalize_result

def system_restore_once(core,now=None):
    now=time.time() if now is None else now
    path=core.DATA_DIR/'system_restore_policy.json'
    try:previous=read(path)
    except (ValueError,OSError):previous={}
    if 0<=now-float(previous.get('last_attempt',0))<86400:
        return {'ok':previous.get('ok') is True,'detail':previous.get('detail','Tentativa recente preservada.'),'cached':True}
    # Persist attempted time before calling Windows, including refusals.
    save(path,{'last_attempt':now,'ok':False,'detail':'Ponto nativo ainda não confirmado; backup local será usado.'})
    try:ok,detail=normalize_result(core.create_windows_restore_point('AZOR Optimization'))
    except Exception as exc:ok,detail=False,str(exc)
    result={'last_attempt':now,'ok':ok,'detail':detail}
    save(path,result)
    return result
