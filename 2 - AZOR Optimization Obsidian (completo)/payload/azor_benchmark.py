"""Short read-only samples. Never label these as FPS, DPC or input latency."""
import ctypes
from ctypes import wintypes
import os
import time

class Memory(ctypes.Structure):
    _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(name,ctypes.c_ulonglong) for name in ('total','available','commit_limit','commit_available','virtual_total','virtual_available','extended')]

def system_sample():
    result={'time':time.time(),'window_ms':200,'available':False,
            'fps':None,'dpc_us':None,'input_to_photon_ms':None,
            'note':'Amostra breve, não necessariamente em repouso. Não mede FPS, DPC ou latência física de input.'}
    if os.name!='nt':return result
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    def cpu():
        values=[wintypes.FILETIME() for _ in range(3)]
        if not kernel.GetSystemTimes(*(ctypes.byref(v) for v in values)):raise OSError('CPU indisponível.')
        return [(v.dwHighDateTime<<32)|v.dwLowDateTime for v in values]
    before=cpu();time.sleep(.2);after=cpu()
    delta=[b-a for a,b in zip(before,after)];total=delta[1]+delta[2]
    result['cpu_percent']=round(max(0,min(100,100*(1-delta[0]/total))),2) if total>0 else None
    mem=Memory();mem.length=ctypes.sizeof(mem)
    if kernel.GlobalMemoryStatusEx(ctypes.byref(mem)):
        result.update(ram_used_mb=round((mem.total-mem.available)/1048576,1),ram_available_mb=round(mem.available/1048576,1),memory_load_percent=mem.load)
    processes=(wintypes.DWORD*65536)();used=wintypes.DWORD()
    if ctypes.WinDLL('psapi').EnumProcesses(processes,ctypes.sizeof(processes),ctypes.byref(used)):
        result['processes']=used.value//ctypes.sizeof(wintypes.DWORD)
    result['available']=True
    return result

def compare(before,after):
    metrics=[]
    for key,label,unit in [('cpu_percent','CPU na amostra','%'),('ram_used_mb','RAM em uso','MB'),('processes','Processos','')]:
        a,b=before.get(key),after.get(key)
        if isinstance(a,(int,float)) and isinstance(b,(int,float)):
            metrics.append({'key':key,'label':label,'unit':unit,'before':a,'after':b,'delta':round(b-a,2)})
    return {'metrics':metrics,'causal_gain_confirmed':False,
            'note':'Variação observada em amostras curtas. Outros programas podem interferir. Ganho de FPS exige captura no mesmo jogo/cenário.'}
