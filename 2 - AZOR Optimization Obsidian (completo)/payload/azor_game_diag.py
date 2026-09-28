from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import azor_core as core

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT.parent
STATE_FILE = core.DATA_DIR / "game_diagnostic_state.json"


def _report_dir() -> Path:
    override = os.environ.get("AZOR_GAME_REPORT_DIR") or os.environ.get("AZOR_REPORT_DIR")
    candidates = [Path(override)] if override else [core.DATA_DIR / "reports" / "games"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "AzorOptimization" / "Relatorios")
    candidates.append(core.DATA_DIR.parent / "Relatorios")
    for p in candidates:
        try:
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".azor_write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return p
        except Exception:
            continue
    return core.DATA_DIR


REPORT_DIR = _report_dir()


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _stamp() -> str:
    return time.strftime("%Y-%m-%d_%H-%M-%S")


def _slug(value: str, fallback: str = "sessao") -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip())
    return s.strip("_")[:60] or fallback


def _float(v: Any) -> Optional[float]:
    if v in (None, "", "NA", "N/A", "[Not Supported]", "[Not Available]"):
        return None
    try:
        x = float(str(v).replace(",", "."))
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _avg(values: List[Any]) -> Optional[float]:
    xs = [x for x in (_float(v) for v in values) if x is not None]
    return round(statistics.fmean(xs), 3) if xs else None


def _maximum(values: List[Any]) -> Optional[float]:
    xs = [x for x in (_float(v) for v in values) if x is not None]
    return round(max(xs), 3) if xs else None


def _minimum(values: List[Any]) -> Optional[float]:
    xs = [x for x in (_float(v) for v in values) if x is not None]
    return round(min(xs), 3) if xs else None


def _percentile(values: List[Any], q: float) -> Optional[float]:
    xs = sorted(x for x in (_float(v) for v in values) if x is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return round(xs[0], 3)
    pos = max(0.0, min(1.0, q)) * (len(xs) - 1)
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return round(xs[lo], 3)
    frac = pos - lo
    return round(xs[lo] * (1 - frac) + xs[hi] * frac, 3)


def _safe_json_write(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _find_fortnite_process() -> Dict[str, Any]:
    if os.name != "nt":
        return {"running": False, "pid": None, "name": None}
    script = r"""
$p=Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -like 'FortniteClient-Win64-Shipping*'} | Sort-Object Id | Select-Object -First 1
if($p){[pscustomobject]@{running=$true;pid=[int]$p.Id;name=[string]$p.ProcessName;path=try{$p.Path}catch{$null}}}else{[pscustomobject]@{running=$false;pid=$null;name=$null;path=$null}}
"""
    try:
        data = core.powershell_json(script, timeout=8) or {}
        return data if isinstance(data, dict) else {"running": False, "pid": None, "name": None}
    except Exception as e:
        core.log(f"GameDiag Fortnite process detection failed: {e}")
        return {"running": False, "pid": None, "name": None, "error": str(e)}


def _presentmon_candidates() -> List[Path]:
    out: List[Path] = []
    for p in [
        ROOT / "tools" / "PresentMon.exe",
        ROOT / "tools" / "PresentMon-2.5.1-x64.exe",
        ROOT / "external" / "PresentMon" / "PresentMon.exe",
        ROOT / "PresentMon.exe",
    ]:
        out.append(p)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        azor_tools = Path(local) / "AzorOptimization" / "Tools"
        out.extend([azor_tools / "PresentMon.exe", azor_tools / "PresentMon-2.5.1-x64.exe"])
    found = shutil.which("PresentMon") or shutil.which("PresentMon.exe")
    if found:
        out.append(Path(found))
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if not base:
            continue
        b = Path(base)
        out.extend([
            b / "Intel" / "PresentMon" / "PresentMon.exe",
            b / "PresentMon" / "PresentMon.exe",
            b / "Intel" / "PresentMon" / "PresentMon-2.5.1-x64.exe",
        ])
    unique: List[Path] = []
    seen = set()
    for p in out:
        k = str(p).lower()
        if k not in seen:
            seen.add(k); unique.append(p)
    return unique


def presentmon_status() -> Dict[str, Any]:
    for p in _presentmon_candidates():
        try:
            if p.is_file() and p.stat().st_size > 100_000:
                return {"available": True, "path": str(p), "mode": "headless_etw", "overlay": False, "injection": False}
        except Exception:
            pass
    return {"available": False, "path": None, "mode": "unavailable", "overlay": False, "injection": False}


def setup_presentmon() -> Dict[str, Any]:
    """Enable the optional headless ETW frame collector after an explicit click."""
    current = presentmon_status()
    if current.get("available"):
        return {"ok": True, "detail": "Captura de FPS/frametime já está disponível.", "presentmon": current}
    if os.name != "nt":
        return {"ok": False, "detail": "A configuração automática do coletor está disponível somente no Windows.", "presentmon": current}
    local = os.environ.get("LOCALAPPDATA")
    tools = (Path(local) / "AzorOptimization" / "Tools") if local else (core.DATA_DIR.parent / "Tools")
    tools.mkdir(parents=True, exist_ok=True)
    dest = tools / "PresentMon-2.5.1-x64.exe"
    tmp = tools / "PresentMon.download"
    url = "https://github.com/GameTechDev/PresentMon/releases/download/v2.5.1/PresentMon-2.5.1-x64.exe"
    expected = "9bec3083069f58f911e6a512f4806db51a27bd096103087bc1d05ef54c80a191"
    qtmp = str(tmp).replace("'", "''")
    qdest = str(dest).replace("'", "''")
    ps = """
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Invoke-WebRequest -UseBasicParsing -Uri '__URL__' -OutFile '__TMP__'
$h=(Get-FileHash -Algorithm SHA256 -LiteralPath '__TMP__').Hash.ToLowerInvariant()
if($h -ne '__HASH__'){ throw "SHA256 inesperado: $h" }
Move-Item -Force -LiteralPath '__TMP__' -Destination '__DEST__'
""".replace("__URL__", url).replace("__TMP__", qtmp).replace("__HASH__", expected).replace("__DEST__", qdest)
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=120,
            creationflags=core.CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            detail = (r.stderr or r.stdout or "Falha ao baixar o coletor oficial.").strip()[-800:]
            return {"ok": False, "detail": detail, "presentmon": presentmon_status()}
        st = presentmon_status()
        if not st.get("available"):
            return {"ok": False, "detail": "O arquivo foi baixado, mas o AZOR não conseguiu validar a disponibilidade do coletor.", "presentmon": st}
        return {"ok": True, "detail": "Captura de FPS, 1% Low e frametime ativada. O coletor roda sem overlay e sem injeção.", "presentmon": st}
    except Exception as e:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": False, "detail": str(e), "presentmon": presentmon_status()}


class _PresentMonCapture:
    def __init__(self, pid: int, out_csv: Path):
        self.pid = int(pid)
        self.out_csv = out_csv
        self.proc: Optional[subprocess.Popen] = None
        self.session_name = f"AzorGameDiag_{os.getpid()}_{self.pid}"
        self.binary: Optional[Path] = None
        self.error: Optional[str] = None

    def start(self) -> bool:
        st = presentmon_status()
        if not st.get("available"):
            self.error = "PresentMon não está disponível dentro desta instalação."
            return False
        self.binary = Path(str(st["path"]))
        args = [
            str(self.binary),
            "--process_id", str(self.pid),
            "--output_file", str(self.out_csv),
            "--no_console_stats",
            "--no_track_input",
            "--v1_metrics",
            "--session_name", self.session_name,
            "--stop_existing_session",
            "--terminate_on_proc_exit",
        ]
        kwargs: Dict[str, Any] = {"cwd": str(self.out_csv.parent), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = core.CREATE_NO_WINDOW
        try:
            self.proc = subprocess.Popen(args, **kwargs)
            time.sleep(0.8)
            if self.proc.poll() is not None:
                self.error = f"PresentMon encerrou ao iniciar (código {self.proc.returncode})."
                return False
            core.log(f"GameDiag PresentMon started headless pid={self.pid} csv={self.out_csv}")
            return True
        except Exception as e:
            self.error = str(e)
            core.log(f"GameDiag PresentMon failed to start: {e}")
            return False

    def stop(self) -> None:
        if not self.proc:
            return
        try:
            if self.proc.poll() is None and self.binary:
                args = [str(self.binary), "--terminate_existing_session", "--session_name", self.session_name, "--no_csv", "--no_console_stats"]
                kwargs: Dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
                if os.name == "nt": kwargs["creationflags"] = core.CREATE_NO_WINDOW
                try:
                    subprocess.run(args, timeout=6, **kwargs)
                except Exception:
                    pass
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.terminate()
        except Exception as e:
            core.log(f"GameDiag PresentMon stop warning: {e}")


def _make_sampler_script(path: Path, target_pid: int) -> None:
    # One long-lived PowerShell process is intentionally used instead of starting a
    # new PowerShell process every second. This reduces diagnostic overhead.
    script = r'''param([int]$TargetPid)
$ErrorActionPreference='SilentlyContinue'
$logical=[Environment]::ProcessorCount
while($true){
  try{
    $cpuRows=@(Get-CimInstance Win32_PerfFormattedData_Counters_ProcessorInformation | Where-Object {$_.Name -notmatch '_Total' -and $_.Name -match '^\d+,\d+$'} | Select-Object Name,PercentProcessorUtility,ProcessorFrequency)
    if(-not $cpuRows -or $cpuRows.Count -eq 0){
      $cpuRows=@(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor | Where-Object {$_.Name -ne '_Total'} | Select-Object @{N='Name';E={$_.Name}},@{N='PercentProcessorUtility';E={$_.PercentProcessorTime}},@{N='ProcessorFrequency';E={$null}})
    }
    $cpuTotal=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor | Where-Object {$_.Name -eq '_Total'} | Select-Object -First 1
    $os=Get-CimInstance Win32_OperatingSystem | Select-Object -First 1 TotalVisibleMemorySize,FreePhysicalMemory
    $disk=Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Where-Object {$_.Name -eq '_Total'} | Select-Object -First 1 PercentDiskTime,DiskReadBytesPersec,DiskWriteBytesPersec,AvgDiskQueueLength
    $netRows=@(Get-CimInstance Win32_PerfFormattedData_Tcpip_NetworkInterface | Select-Object BytesReceivedPersec,BytesSentPersec)
    $rx=0.0;$tx=0.0;foreach($n in $netRows){$rx+=[double]$n.BytesReceivedPersec;$tx+=[double]$n.BytesSentPersec}
    $p=Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object {[int]$_.IDProcess -eq $TargetPid} | Select-Object -First 1 Name,IDProcess,PercentProcessorTime,WorkingSetPrivate,IOReadBytesPersec,IOWriteBytesPersec,IODataBytesPersec,ThreadCount,HandleCount
    $top=@(Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object {[int]$_.IDProcess -gt 0 -and $_.Name -notin @('_Total','Idle')} | Sort-Object {[double]$_.PercentProcessorTime} -Descending | Select-Object -First 10 Name,IDProcess,PercentProcessorTime,WorkingSetPrivate)
    $gpu=0.0
    try{$g=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | Where-Object {$_.Name -match ('pid_'+$TargetPid+'_')} | Select-Object UtilizationPercentage);foreach($x in $g){$gpu+=[double]$x.UtilizationPercentage}}catch{}
    $gmem=$null
    try{$gm=Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object {$_.Name -match ('pid_'+$TargetPid+'_')} | Select-Object -First 1 DedicatedUsage,SharedUsage;$gmem=$gm}catch{}
    $obj=[pscustomobject]@{
      utc_ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();
      cpu_total=if($cpuTotal){[double]$cpuTotal.PercentProcessorTime}else{$null};
      cpu_cores=@($cpuRows);
      ram_total_kb=if($os){[double]$os.TotalVisibleMemorySize}else{$null};
      ram_free_kb=if($os){[double]$os.FreePhysicalMemory}else{$null};
      disk_percent=if($disk){[double]$disk.PercentDiskTime}else{$null};
      disk_read_bps=if($disk){[double]$disk.DiskReadBytesPersec}else{$null};
      disk_write_bps=if($disk){[double]$disk.DiskWriteBytesPersec}else{$null};
      disk_queue=if($disk){[double]$disk.AvgDiskQueueLength}else{$null};
      net_rx_bps=$rx;net_tx_bps=$tx;
      fortnite=$p;
      fortnite_gpu_percent=[math]::Min(100.0,$gpu);
      fortnite_gpu_dedicated_bytes=if($gmem){[double]$gmem.DedicatedUsage}else{$null};
      fortnite_gpu_shared_bytes=if($gmem){[double]$gmem.SharedUsage}else{$null};
      top=$top;logical_processors=$logical
    }
    $obj | ConvertTo-Json -Depth 5 -Compress
  }catch{[pscustomobject]@{utc_ms=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();error=$_.Exception.Message} | ConvertTo-Json -Compress}
  Start-Sleep -Milliseconds 1000
}
'''
    path.write_text(script, encoding="utf-8-sig")


def _frametime_histogram(intervals: List[float], buckets: int = 26) -> List[Dict[str, Any]]:
    """Bucket frame intervals so the UI can draw the real distribution.

    The window is clipped to the 99.5th percentile: a couple of 900 ms hitches
    would otherwise flatten every meaningful bar into the first column. The
    frames past the clip are still counted, in the overflow bucket.
    """
    if len(intervals) < 8:
        return []
    ordered = sorted(intervals)
    hi = ordered[max(0, int(len(ordered) * 0.995) - 1)]
    lo = ordered[0]
    if hi <= lo:
        return []
    width = (hi - lo) / buckets
    counts = [0] * buckets
    overflow = 0
    for v in intervals:
        if v > hi:
            overflow += 1
            continue
        idx = min(buckets - 1, int((v - lo) / width)) if width > 0 else 0
        counts[idx] += 1
    out = [{
        "from_ms": round(lo + i * width, 2),
        "to_ms": round(lo + (i + 1) * width, 2),
        "count": counts[i],
    } for i in range(buckets)]
    if overflow:
        out.append({"from_ms": round(hi, 2), "to_ms": None, "count": overflow, "overflow": True})
    return out


def _frametime_timeline(intervals: List[float], points: int = 180) -> List[float]:
    """Downsample the session keeping the worst frame in each slot.

    Averaging would erase exactly what the user came here to see, so each slot
    reports its slowest frame - a spike stays a spike.
    """
    if not intervals:
        return []
    if len(intervals) <= points:
        return [round(v, 2) for v in intervals]
    size = len(intervals) / points
    out = []
    for i in range(points):
        start = int(i * size)
        end = max(start + 1, int((i + 1) * size))
        out.append(round(max(intervals[start:end]), 2))
    return out


def _parse_presentmon_csv(path: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "available": False, "source": "PresentMon ETW", "frames": 0,
        "fps_avg": None, "fps_1_low": None, "fps_0_1_low": None,
        "frametime_avg_ms": None, "frametime_p95_ms": None, "frametime_p99_ms": None,
        "frametime_max_ms": None, "stutter_events": 0,
    }
    if not path.is_file() or path.stat().st_size < 20:
        return result
    intervals: List[float] = []
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                v = None
                for key in ("MsBetweenPresents", "MsBetweenDisplayChange", "MsBetweenSimulationStart", "MsBetweenAppStart", "FrameTime"):
                    if key in row:
                        v = _float(row.get(key))
                        if v is not None and v > 0:
                            break
                if v is not None and 0 < v < 5000:
                    intervals.append(v)
        if len(intervals) < 3:
            return result
        fps = [1000.0 / x for x in intervals if x > 0]
        # "1% low" is the average FPS of the slowest 1% of frame intervals.
        slow_n = max(1, int(math.ceil(len(intervals) * 0.01)))
        slow_01_n = max(1, int(math.ceil(len(intervals) * 0.001)))
        slow = sorted(intervals, reverse=True)[:slow_n]
        slow01 = sorted(intervals, reverse=True)[:slow_01_n]
        median = statistics.median(intervals)
        threshold = max(20.0, median * 2.0)
        result.update({
            "available": True,
            "frames": len(intervals),
            "fps_avg": round(1000.0 / statistics.fmean(intervals), 2),
            "fps_1_low": round(1000.0 / statistics.fmean(slow), 2) if slow else None,
            "fps_0_1_low": round(1000.0 / statistics.fmean(slow01), 2) if slow01 else None,
            "frametime_avg_ms": round(statistics.fmean(intervals), 3),
            "frametime_p95_ms": _percentile(intervals, 0.95),
            "frametime_p99_ms": _percentile(intervals, 0.99),
            "frametime_max_ms": round(max(intervals), 3),
            "stutter_events": sum(1 for x in intervals if x >= threshold),
            "stutter_threshold_ms": round(threshold, 3),
            "frametime_median_ms": round(median, 3),
            "histogram": _frametime_histogram(intervals),
            "timeline": _frametime_timeline(intervals),
        })
    except Exception as e:
        result["error"] = str(e)
    return result


def _summarize_samples(samples: List[Dict[str, Any]], frame: Dict[str, Any]) -> Dict[str, Any]:
    cpu = [s.get("cpu_total") for s in samples]
    ram = [s.get("ram_percent") for s in samples]
    disk = [s.get("disk_percent") for s in samples]
    fcpu = [s.get("fortnite_cpu_percent") for s in samples]
    fgpu = [s.get("fortnite_gpu_percent") for s in samples]
    gpu = [s.get("gpu", {}).get("usage") for s in samples]
    gpu_temp = [s.get("gpu", {}).get("temp_c") for s in samples]
    gpu_clock = [s.get("gpu", {}).get("clock_mhz") for s in samples]
    gpu_vram = [s.get("gpu", {}).get("vram_used_mb") for s in samples]
    cpu_temp = [s.get("cpu_temp_c") for s in samples]
    f_ram = [s.get("fortnite_ram_mb") for s in samples]
    core_peaks: Dict[str, float] = {}
    core_avgs: Dict[str, List[float]] = {}
    clock_avgs: Dict[str, List[float]] = {}
    for s in samples:
        for c in s.get("cpu_cores") or []:
            name = str(c.get("name") or "")
            u = _float(c.get("usage")); mhz = _float(c.get("clock_mhz"))
            if u is not None:
                core_peaks[name] = max(core_peaks.get(name, 0.0), u)
                core_avgs.setdefault(name, []).append(u)
            if mhz is not None:
                clock_avgs.setdefault(name, []).append(mhz)
    core_summary = [{"core": k, "avg_percent": _avg(core_avgs.get(k, [])), "max_percent": round(v, 2), "avg_clock_mhz": _avg(clock_avgs.get(k, []))} for k, v in sorted(core_peaks.items(), key=lambda kv: kv[0])]
    top_counts: Dict[str, Dict[str, Any]] = {}
    for s in samples:
        for p in s.get("top_processes") or []:
            name = str(p.get("name") or "Processo")
            ent = top_counts.setdefault(name, {"name": name, "hits": 0, "cpu": [], "ram": []})
            ent["hits"] += 1
            if _float(p.get("cpu_percent")) is not None: ent["cpu"].append(float(p["cpu_percent"]))
            if _float(p.get("memory_mb")) is not None: ent["ram"].append(float(p["memory_mb"]))
    top = sorted(({"name": v["name"], "samples": v["hits"], "avg_cpu_percent": _avg(v["cpu"]), "max_ram_mb": _maximum(v["ram"])} for v in top_counts.values()), key=lambda x: (x.get("avg_cpu_percent") or 0, x.get("max_ram_mb") or 0), reverse=True)[:12]
    return {
        "sample_count": len(samples),
        "duration_s": round((samples[-1].get("utc_ms", 0) - samples[0].get("utc_ms", 0)) / 1000.0, 1) if len(samples) >= 2 else 0,
        "cpu": {"avg_percent": _avg(cpu), "max_percent": _maximum(cpu), "temp_max_c": _maximum(cpu_temp), "cores": core_summary},
        "ram": {"avg_percent": _avg(ram), "max_percent": _maximum(ram)},
        "disk": {"avg_percent": _avg(disk), "max_percent": _maximum(disk)},
        "gpu": {"avg_percent": _avg(gpu), "max_percent": _maximum(gpu), "temp_max_c": _maximum(gpu_temp), "clock_avg_mhz": _avg(gpu_clock), "vram_max_mb": _maximum(gpu_vram)},
        "fortnite": {"cpu_avg_percent": _avg(fcpu), "cpu_max_percent": _maximum(fcpu), "gpu_avg_percent": _avg(fgpu), "gpu_max_percent": _maximum(fgpu), "ram_max_mb": _maximum(f_ram)},
        "frames": frame,
        "top_processes": top,
    }


def _interpret(summary: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    frames = summary.get("frames") or {}
    cpu = summary.get("cpu") or {}; gpu = summary.get("gpu") or {}; ram = summary.get("ram") or {}; fort = summary.get("fortnite") or {}
    core_max = max([_float(c.get("max_percent")) or 0 for c in cpu.get("cores") or []] or [0])
    gpu_avg = _float(gpu.get("avg_percent")); gpu_max = _float(gpu.get("max_percent")); ram_max = _float(ram.get("max_percent"))
    if frames.get("available"):
        st = int(frames.get("stutter_events") or 0)
        if st:
            out.append({"severity":"warn", "code":"frametime", "text":f"Foram detectados {st} picos de frametime acima do limiar da sessão."})
        else:
            out.append({"severity":"good", "code":"frametime", "text":"A captura de frames não encontrou picos relevantes pelo limiar automático da sessão."})
    else:
        out.append({"severity":"info", "code":"frames_unavailable", "text":"FPS/frametime não foram medidos porque o coletor ETW PresentMon não está disponível nesta instalação; o AZOR não inventa esses valores."})
    if core_max >= 95 and (gpu_avg is None or gpu_avg < 90):
        out.append({"severity":"warn", "code":"cpu_limit", "text":"Um ou mais núcleos da CPU chegaram muito perto de 100% enquanto a GPU manteve folga; há sinal de limitação por CPU em parte da sessão."})
    elif gpu_avg is not None and gpu_avg >= 95:
        out.append({"severity":"info", "code":"gpu_limit", "text":"A GPU ficou próxima da utilização máxima durante boa parte da sessão; a carga pode estar limitada pela GPU nesse cenário."})
    else:
        out.append({"severity":"good", "code":"load_balance", "text":"Não apareceu um gargalo contínuo óbvio apenas pelas médias de CPU/GPU."})
    if ram_max is not None and ram_max >= 90:
        out.append({"severity":"warn", "code":"ram_pressure", "text":f"A RAM chegou a {ram_max:.1f}% de uso; paginação pode piorar a consistência do frametime."})
    if _float(gpu.get("temp_max_c")) is not None and float(gpu["temp_max_c"]) >= 85:
        out.append({"severity":"warn", "code":"gpu_temp", "text":f"A GPU chegou a {float(gpu['temp_max_c']):.0f}°C; vale verificar refrigeração e clocks antes de aplicar mais ajustes."})
    if _float(cpu.get("temp_max_c")) is not None and float(cpu["temp_max_c"]) >= 90:
        out.append({"severity":"warn", "code":"cpu_temp", "text":f"A CPU chegou a {float(cpu['temp_max_c']):.0f}°C durante a coleta."})
    if _float(fort.get("cpu_max_percent")) is not None:
        out.append({"severity":"info", "code":"fortnite_process", "text":f"Pico de CPU do processo do Fortnite: {float(fort['cpu_max_percent']):.1f}% do processador total."})
    return out


def _comparison(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    def get(d: Dict[str, Any], path: Tuple[str, ...]) -> Optional[float]:
        cur: Any = d
        for k in path:
            if not isinstance(cur, dict): return None
            cur = cur.get(k)
        return _float(cur)
    metrics = [
        ("FPS médio", ("frames","fps_avg"), True, "fps"),
        ("1% Low", ("frames","fps_1_low"), True, "fps"),
        ("Frametime médio", ("frames","frametime_avg_ms"), False, "ms"),
        ("P99 frametime", ("frames","frametime_p99_ms"), False, "ms"),
        ("CPU média", ("cpu","avg_percent"), False, "%"),
        ("GPU média", ("gpu","avg_percent"), None, "%"),
        ("RAM média", ("ram","avg_percent"), False, "%"),
    ]
    rows=[]
    for label,path,higher,unit in metrics:
        b=get(before,path); a=get(after,path)
        delta=round(a-b,3) if a is not None and b is not None else None
        improved=None
        if delta is not None and higher is not None:
            improved = delta > 0 if higher else delta < 0
        rows.append({"metric":label,"before":b,"after":a,"delta":delta,"unit":unit,"improved":improved})
    return {"rows":rows,"generated_at":_ts()}


def _html_report(report: Dict[str, Any]) -> str:
    s=report.get("summary") or {}; f=s.get("frames") or {}; cpu=s.get("cpu") or {}; gpu=s.get("gpu") or {}; ram=s.get("ram") or {}; fort=s.get("fortnite") or {}
    findings=report.get("findings") or []
    def val(v, suffix=""):
        return "Indisponível" if v is None else f"{v}{suffix}"
    rows="".join(f"<tr><td>{x.get('code','')}</td><td>{x.get('severity','')}</td><td>{x.get('text','')}</td></tr>" for x in findings)
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>AZOR Diagnóstico em Jogo</title><style>body{{font-family:Segoe UI,Arial;background:#0b0b10;color:#eee;margin:32px}}h1,h2{{color:#e75cff}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}.card{{background:#15151d;border:1px solid #2c2c39;border-radius:12px;padding:16px}}b{{font-size:24px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;border-bottom:1px solid #2b2b37;text-align:left}}small{{color:#aaa}}</style></head><body><h1>AZOR — Diagnóstico em Jogo</h1><p>{report.get('label','')} • {report.get('started_at','')} → {report.get('ended_at','')}</p><div class="grid"><div class="card"><small>FPS MÉDIO</small><br><b>{val(f.get('fps_avg'))}</b></div><div class="card"><small>1% LOW</small><br><b>{val(f.get('fps_1_low'))}</b></div><div class="card"><small>FRAMETIME</small><br><b>{val(f.get('frametime_avg_ms'),' ms')}</b></div><div class="card"><small>CPU</small><br><b>{val(cpu.get('avg_percent'),'%')}</b></div><div class="card"><small>GPU</small><br><b>{val(gpu.get('avg_percent'),'%')}</b></div><div class="card"><small>RAM</small><br><b>{val(ram.get('avg_percent'),'%')}</b></div><div class="card"><small>FORTNITE CPU</small><br><b>{val(fort.get('cpu_avg_percent'),'%')}</b></div></div><h2>Análise</h2><table><tr><th>Código</th><th>Nível</th><th>Interpretação</th></tr>{rows}</table><h2>Observação de medição</h2><p>O AZOR marca sensores ausentes como indisponíveis. A captura de FPS/frametime usa ETW em modo headless quando o PresentMon está disponível; não há overlay nem injeção no processo do jogo.</p></body></html>'''


class GameDiagnosticManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.state: Dict[str, Any] = {"status":"idle","running":False,"waiting_for_game":False,"samples":0,"reports_dir":str(REPORT_DIR),"presentmon":presentmon_status()}
        self.samples: List[Dict[str, Any]] = []
        self.session_dir: Optional[Path] = None
        self.sampler: Optional[subprocess.Popen] = None
        self.presentmon: Optional[_PresentMonCapture] = None
        self.last_report: Optional[Dict[str, Any]] = None
        self._save_state()

    def _save_state(self) -> None:
        try: _safe_json_write(STATE_FILE, self.status())
        except Exception: pass

    def status(self) -> Dict[str, Any]:
        with self.lock:
            st=dict(self.state)
            st["samples"] = len(self.samples)
            st["presentmon"] = presentmon_status()
            st["reports_dir"] = str(REPORT_DIR)
            if self.last_report:
                st["last_report"] = {k:self.last_report.get(k) for k in ("label","started_at","ended_at","report_json","report_html","summary","comparison")}
            return st

    def start(self, label: str="antes", customer: str="") -> Dict[str, Any]:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return {"ok":False,"detail":"Já existe uma análise em andamento.","status":self.status()}
            self.stop_event.clear(); self.samples=[]; self.last_report=None
            label = "depois" if str(label).lower().startswith("dep") else "antes"
            folder = REPORT_DIR / f"{_stamp()}_{_slug(customer or 'Cliente')}_{label}"
            folder.mkdir(parents=True, exist_ok=True)
            self.session_dir=folder
            self.state={"status":"waiting","running":True,"waiting_for_game":True,"label":label,"customer":customer,"started_at":_ts(),"game_started_at":None,"game_pid":None,"detail":"Aguardando Fortnite...","reports_dir":str(REPORT_DIR),"session_dir":str(folder),"presentmon":presentmon_status()}
            self.thread=threading.Thread(target=self._worker,name="AzorGameDiagnostic",daemon=True);self.thread.start();self._save_state()
            return {"ok":True,"detail":"Diagnóstico iniciado. O AZOR está aguardando o Fortnite.","status":self.status()}

    def stop(self) -> Dict[str, Any]:
        self.stop_event.set()
        th=self.thread
        if th and th.is_alive() and th is not threading.current_thread():
            th.join(timeout=12)
        return {"ok":True,"detail":"Coleta finalizada.","status":self.status(),"report":self.last_report}

    def _worker(self) -> None:
        try:
            proc={}
            while not self.stop_event.is_set():
                proc=_find_fortnite_process()
                if proc.get("running") and proc.get("pid"):
                    break
                time.sleep(2)
            if self.stop_event.is_set():
                with self.lock:self.state.update({"status":"cancelled","running":False,"waiting_for_game":False,"detail":"Diagnóstico cancelado antes do Fortnite iniciar."});self._save_state();return
            pid=int(proc["pid"])
            with self.lock:self.state.update({"status":"capturing","waiting_for_game":False,"game_pid":pid,"game_name":proc.get("name"),"game_started_at":_ts(),"detail":"Fortnite detectado. Coletando telemetria..."});self._save_state()
            assert self.session_dir is not None
            ps1=self.session_dir/"azor_sampler.ps1"; _make_sampler_script(ps1,pid)
            pm_csv=self.session_dir/"frames_presentmon.csv"
            self.presentmon=_PresentMonCapture(pid,pm_csv); pm_ok=self.presentmon.start()
            if not pm_ok:
                with self.lock:self.state["presentmon_error"]=self.presentmon.error
            args=["powershell.exe","-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(ps1),"-TargetPid",str(pid)]
            kwargs: Dict[str, Any]={"stdout":subprocess.PIPE,"stderr":subprocess.DEVNULL,"text":True,"encoding":"utf-8","errors":"replace","bufsize":1}
            if os.name=="nt":kwargs["creationflags"]=core.CREATE_NO_WINDOW
            self.sampler=subprocess.Popen(args,**kwargs)
            last_gpu=0.0; last_hw=0.0; hw={}; gpu={}; raw_file=self.session_dir/"samples.jsonl"
            with raw_file.open("a",encoding="utf-8") as raw:
                while not self.stop_event.is_set():
                    if self.sampler.poll() is not None: break
                    line=self.sampler.stdout.readline() if self.sampler.stdout else ""
                    if not line:
                        time.sleep(0.05); continue
                    try:d=json.loads(line)
                    except Exception:continue
                    if d.get("error"):
                        core.log("GameDiag sampler warning: "+str(d.get("error")));continue
                    now=time.time()
                    if now-last_gpu>=2.0:
                        try: gpu=core._nvidia_snapshot()
                        except Exception: gpu={}
                        last_gpu=now
                    if now-last_hw>=8.0:
                        try: hw=core._hardware_monitor_snapshot()
                        except Exception: hw={}
                        last_hw=now
                    total=_float(d.get("ram_total_kb"));free=_float(d.get("ram_free_kb"));ram_pct=round((1-free/total)*100,2) if total and free is not None else None
                    logical=max(1,int(d.get("logical_processors") or os.cpu_count() or 1))
                    f=d.get("fortnite") or {}; f_cpu=_float(f.get("PercentProcessorTime")); f_cpu_norm=round(min(100.0,f_cpu/logical),2) if f_cpu is not None else None
                    cores=[]
                    for c in d.get("cpu_cores") or []:
                        cores.append({"name":str(c.get("Name") or c.get("name") or ""),"usage":_float(c.get("PercentProcessorUtility") if "PercentProcessorUtility" in c else c.get("usage")),"clock_mhz":_float(c.get("ProcessorFrequency") if "ProcessorFrequency" in c else c.get("clock_mhz"))})
                    tops=[]
                    for p in d.get("top") or []:
                        pcpu=_float(p.get("PercentProcessorTime")); tops.append({"name":str(p.get("Name") or ""),"pid":p.get("IDProcess"),"cpu_percent":round(min(100.0,pcpu/logical),2) if pcpu is not None else None,"memory_mb":round((_float(p.get("WorkingSetPrivate")) or 0)/(1024**2),1)})
                    sample={"utc_ms":d.get("utc_ms"),"cpu_total":_float(d.get("cpu_total")),"cpu_cores":cores,"cpu_temp_c":_float(hw.get("cpu_temp_c")),"ram_percent":ram_pct,"ram_used_gb":round((total-free)*1024/(1024**3),2) if total and free is not None else None,"disk_percent":_float(d.get("disk_percent")),"disk_read_mbps":round((_float(d.get("disk_read_bps")) or 0)*8/1_000_000,3),"disk_write_mbps":round((_float(d.get("disk_write_bps")) or 0)*8/1_000_000,3),"disk_queue":_float(d.get("disk_queue")),"net_down_mbps":round((_float(d.get("net_rx_bps")) or 0)*8/1_000_000,3),"net_up_mbps":round((_float(d.get("net_tx_bps")) or 0)*8/1_000_000,3),"fortnite_cpu_percent":f_cpu_norm,"fortnite_ram_mb":round((_float(f.get("WorkingSetPrivate")) or 0)/(1024**2),1) if f else None,"fortnite_io_mbps":round((_float(f.get("IODataBytesPersec")) or 0)*8/1_000_000,3) if f else None,"fortnite_gpu_percent":_float(d.get("fortnite_gpu_percent")),"fortnite_vram_mb":round((_float(d.get("fortnite_gpu_dedicated_bytes")) or 0)/(1024**2),1),"gpu":gpu,"top_processes":tops}
                    with self.lock:
                        self.samples.append(sample)
                        if len(self.samples)>7200:self.samples=self.samples[-7200:]
                        self.state.update({"samples":len(self.samples),"last_sample_at":_ts(),"live":{"cpu":sample["cpu_total"],"gpu":gpu.get("usage") if isinstance(gpu,dict) else None,"ram":sample["ram_percent"],"fortnite_cpu":sample["fortnite_cpu_percent"],"fortnite_gpu":sample["fortnite_gpu_percent"],"cpu_temp":sample["cpu_temp_c"],"gpu_temp":gpu.get("temp_c") if isinstance(gpu,dict) else None}})
                    raw.write(json.dumps(sample,ensure_ascii=False,default=str)+"\n");raw.flush()
                    # If Fortnite exited, finish automatically after at least a few samples.
                    if not f and len(self.samples)>=3:
                        break
            self._finalize(pm_csv,pm_ok)
        except Exception as e:
            core.log(f"GameDiag fatal: {e}")
            with self.lock:self.state.update({"status":"error","running":False,"waiting_for_game":False,"detail":str(e)});self._save_state()
        finally:
            try:
                if self.sampler and self.sampler.poll() is None:self.sampler.terminate()
            except Exception:pass
            try:
                if self.presentmon:self.presentmon.stop()
            except Exception:pass

    def _finalize(self, pm_csv: Path, pm_ok: bool) -> None:
        with self.lock:self.state.update({"status":"finalizing","detail":"Finalizando relatório..."})
        try:
            if self.presentmon:self.presentmon.stop()
            time.sleep(0.4)
        except Exception:pass
        frame=_parse_presentmon_csv(pm_csv) if pm_ok else _parse_presentmon_csv(pm_csv)
        summary=_summarize_samples(list(self.samples),frame) if self.samples else {"sample_count":0,"frames":frame}
        findings=_interpret(summary)
        report={"schema":"azor.game-diagnostic/1","label":self.state.get("label"),"customer":self.state.get("customer"),"started_at":self.state.get("started_at"),"game_started_at":self.state.get("game_started_at"),"ended_at":_ts(),"game_pid":self.state.get("game_pid"),"summary":summary,"findings":findings,"presentmon":presentmon_status(),"frame_capture_started":bool(pm_ok),"reports_dir":str(REPORT_DIR)}
        assert self.session_dir is not None
        json_path=self.session_dir/"Relatorio_AZOR.json";txt_path=self.session_dir/"Relatorio_AZOR.txt";html_path=self.session_dir/"Relatorio_AZOR.html"
        _safe_json_write(json_path,report)
        txt_lines=["AZOR - DIAGNOSTICO EM JOGO",f"Sessao: {report['label']}",f"Inicio: {report['started_at']}",f"Fim: {report['ended_at']}","",json.dumps(summary,ensure_ascii=False,indent=2),"","ANALISE"]+[f"[{x['severity'].upper()}] {x['text']}" for x in findings]
        txt_path.write_text("\n".join(txt_lines),encoding="utf-8")
        html_path.write_text(_html_report(report),encoding="utf-8")
        report.update({"report_json":str(json_path),"report_txt":str(txt_path),"report_html":str(html_path),"session_dir":str(self.session_dir)})
        comparison=self._write_comparison_if_possible(report)
        if comparison:
            report["comparison"]=comparison
            _safe_json_write(json_path,report)
        with self.lock:
            self.last_report=report;self.state.update({"status":"completed","running":False,"waiting_for_game":False,"ended_at":report["ended_at"],"detail":"Relatório salvo na pasta Relatorios.","report_json":str(json_path),"report_html":str(html_path),"summary":summary,"comparison":comparison});self._save_state()
        core.log(f"GameDiag report saved: {json_path}")

    def _write_comparison_if_possible(self, current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            # Generate only after the just-finished DEPOIS session, paired with the
            # most recent earlier ANTES session for the same customer identifier.
            if str(current.get("label") or "") != "depois":
                return None
            customer=_slug(str(current.get("customer") or "Cliente"))
            current_dir=Path(str(current.get("session_dir") or self.session_dir or ""))
            current_json=current_dir/"Relatorio_AZOR.json"
            current_mtime=current_json.stat().st_mtime if current_json.is_file() else time.time()
            peers=[]
            for p in REPORT_DIR.glob(f"*_{customer}_antes"):
                j=p/"Relatorio_AZOR.json"
                if not j.is_file():
                    continue
                try:
                    mtime=j.stat().st_mtime
                    if mtime > current_mtime:
                        continue
                    d=json.loads(j.read_text(encoding="utf-8"))
                    if d.get("label")=="antes":
                        peers.append((mtime,d,p))
                except Exception:
                    pass
            if not peers:
                return None
            peers.sort(key=lambda x:x[0], reverse=True)
            before=peers[0][1]
            comp=_comparison(before.get("summary") or {},current.get("summary") or {})
            payload={"schema":"azor.game-comparison/1","customer":current.get("customer"),"before":before.get("started_at"),"after":current.get("started_at"),**comp}
            out=REPORT_DIR/f"Comparativo_{customer}.json"
            _safe_json_write(out,payload)
            payload["path"]=str(out)
            return payload
        except Exception as e:
            core.log(f"GameDiag comparison warning: {e}")
            return None



MANAGER = GameDiagnosticManager()


def status() -> Dict[str, Any]:
    return MANAGER.status()


def start(label: str="antes", customer: str="") -> Dict[str, Any]:
    return MANAGER.start(label, customer)


def stop() -> Dict[str, Any]:
    return MANAGER.stop()


def setup_frame_capture() -> Dict[str, Any]:
    return setup_presentmon()


def list_reports(limit: int=12) -> Dict[str, Any]:
    rows=[]
    try:
        for j in sorted(REPORT_DIR.glob("*/Relatorio_AZOR.json"),key=lambda p:p.stat().st_mtime,reverse=True)[:max(1,min(50,int(limit)))]:
            try:
                d=json.loads(j.read_text(encoding="utf-8"));s=d.get("summary") or {};f=s.get("frames") or {}
                rows.append({"label":d.get("label"),"customer":d.get("customer"),"started_at":d.get("started_at"),"ended_at":d.get("ended_at"),"fps_avg":f.get("fps_avg"),"fps_1_low":f.get("fps_1_low"),"frametime_ms":f.get("frametime_avg_ms"),"samples":s.get("sample_count"),"path":str(j.parent)})
            except Exception:continue
    except Exception as e:return {"ok":False,"error":str(e),"reports":[]}
    return {"ok":True,"reports":rows,"reports_dir":str(REPORT_DIR)}
