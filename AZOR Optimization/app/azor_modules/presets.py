"""Pré-sets por hardware: o BOOST certo para cada combinação de peças.

Como funciona
-------------
Não dá para gravar "trilhões" de configurações prontas, e nem precisa: o que
muda de um PC para outro é decidido por poucas dimensões independentes. O AZOR
guarda na memória uma biblioteca de FAMÍLIAS por dimensão (processador, placa
de vídeo, memória, disco, formato, Windows, rede) e, para cada família, as
regras do que ligar, o que NÃO mexer e o que o técnico precisa fazer à mão.

Na hora do BOOST ele lê o PC, encaixa cada peça numa família e junta as regras.
Cada combinação possível (hoje são dezenas de milhares) resolve para um
pré-set único, com o motivo de cada decisão escrito para o cliente ler.

O pré-set reconhecido fica gravado (preset_memory.json): quando o mesmo PC
volta, o AZOR já sabe quem ele é; quando uma peça muda (placa de vídeo nova,
mais memória), a impressão digital muda e o pré-set é recalculado.

Regra de ouro: o pré-set só LIGA o que tem releitura e desfazer, e só DESLIGA
itens do lote quando aquela peça piora com eles (ex.: plano Alto desempenho
atrapalha o Ryzen X3D de dois CCDs; economia de energia desligada atrapalha o
Intel híbrido a mandar tarefas de fundo para os núcleos E).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Biblioteca: as famílias de cada dimensão
# ---------------------------------------------------------------------------
CPU_FAMILIES = {
    "intel_hybrid": ("Intel híbrido (núcleos P + E)", "Core 12ª a 14ª geração e Core Ultra de mesa."),
    "intel_hybrid_mobile": ("Intel híbrido de notebook", "Core 12ª geração em diante e Core Ultra de notebook."),
    "intel_classic": ("Intel clássico", "Core até a 11ª geração, e os de 12ª+ só com núcleos P."),
    "intel_mobile": ("Intel de notebook", "Core H/U/P sem núcleos E."),
    "amd_x3d_dual": ("Ryzen X3D de dois CCDs", "7900X3D, 7950X3D, 9900X3D, 9950X3D."),
    "amd_x3d": ("Ryzen X3D", "5800X3D, 5700X3D, 7800X3D, 9800X3D."),
    "amd_zen": ("Ryzen de mesa", "Ryzen 3000, 5000, 7000 e 9000."),
    "amd_apu": ("Ryzen com vídeo integrado (G)", "5600G, 5700G, 8600G, 8700G."),
    "amd_mobile": ("Ryzen de notebook", "Ryzen HS/H/HX/U e Ryzen AI."),
    "entry": ("Processador de entrada", "Até 4 threads: Pentium, Celeron, Athlon, i3/i5 antigos."),
    "unknown": ("Processador não identificado", "Regras gerais, sem ajuste por modelo."),
}
GPU_FAMILIES = {
    "nvidia_rtx40": ("NVIDIA RTX 40/50", "Frame Generation (DLSS 3/4) e Reflex."),
    "nvidia_rtx": ("NVIDIA RTX 20/30", "DLSS e Reflex."),
    "nvidia_gtx": ("NVIDIA GTX 10/16", "Pascal e Turing sem RT."),
    "nvidia_legacy": ("NVIDIA antiga", "GTX 900 e anteriores, MX de notebook."),
    "amd_rdna3": ("Radeon RX 7000/9000", "RDNA 3 e 4."),
    "amd_rdna": ("Radeon RX 5000/6000", "RDNA 1 e 2."),
    "amd_legacy": ("Radeon antiga", "RX 400/500, Vega, R9/R7."),
    "intel_arc": ("Intel Arc", "A e B series."),
    "igpu_amd": ("Só vídeo integrado AMD", "Radeon Graphics / 680M / 780M."),
    "igpu_intel": ("Só vídeo integrado Intel", "UHD, Iris Xe e Arc integrado."),
    "unknown": ("Placa de vídeo não identificada", "Regras gerais."),
}
RAM_FAMILIES = {
    "ram_4": ("Até 6 GB", "Pouca memória: cada processo a menos conta."),
    "ram_8": ("8 GB", "Limite para jogos atuais."),
    "ram_16": ("16 GB", "O padrão para jogar."),
    "ram_32": ("32 GB", "Folga para jogo + live."),
    "ram_64": ("64 GB ou mais", "Memória de sobra."),
}
DISK_FAMILIES = {
    "nvme": ("SSD NVMe", "Windows num SSD NVMe."),
    "sata_ssd": ("SSD SATA", "Windows num SSD SATA."),
    "hdd": ("HD mecânico", "Windows num HD de disco girando."),
    "unknown": ("Disco não identificado", "O serviço de armazenamento não respondeu."),
}
FORM_FAMILIES = {
    "desktop": ("Desktop", "PC de mesa na tomada."),
    "laptop": ("Notebook", "Bateria e calor limitam."),
}
OS_FAMILIES = {
    "win11": ("Windows 11", "Build 22000 ou mais nova."),
    "win10": ("Windows 10", "Build 19041 a 19045."),
}
NET_FAMILIES = {
    "ethernet": ("Cabo de rede", "Ping mais estável."),
    "wifi": ("Wi-Fi", "Ping varia com a distância e interferência."),
    "unknown": ("Rede não identificada", ""),
}
DIMENSIONS = (("cpu", CPU_FAMILIES), ("gpu", GPU_FAMILIES), ("ram", RAM_FAMILIES), ("disk", DISK_FAMILIES),
              ("form", FORM_FAMILIES), ("os", OS_FAMILIES), ("net", NET_FAMILIES))
# Chaves que mudam o resultado sem virar família: mudam as regras aplicadas.
FLAGS = ("single_channel", "xmp_off", "hybrid_graphics", "high_refresh", "streamer", "ddr5")

MEMORY_FILE = "preset_memory.json"
FACTS_FILE = "preset_facts.json"
FACTS_TTL = 600.0


def library() -> Dict[str, Any]:
    dims = [{"id": d, "families": [{"id": k, "label": v[0], "hint": v[1]} for k, v in fams.items()]}
            for d, fams in DIMENSIONS]
    total = 1
    for _d, fams in DIMENSIONS:
        total *= len(fams)
    return {"dimensions": dims, "flags": list(FLAGS), "combinations": total * (2 ** len(FLAGS))}


# ---------------------------------------------------------------------------
# Leitura do PC
# ---------------------------------------------------------------------------
_FACTS_SCRIPT = r"""
$ErrorActionPreference='SilentlyContinue'
$disk=$null
try {
  $letter=$env:SystemDrive.TrimEnd(':')
  $part=Get-Partition -DriveLetter $letter -ErrorAction Stop
  $pd=Get-PhysicalDisk | Where-Object { [string]$_.DeviceId -eq [string]$part.DiskNumber } | Select-Object -First 1
  if($pd){ $disk=[pscustomobject]@{Bus=[string]$pd.BusType;Media=[string]$pd.MediaType;Name=[string]$pd.FriendlyName} }
} catch {}
$mem=@(Get-CimInstance Win32_PhysicalMemory | Select-Object SMBIOSMemoryType,Speed,ConfiguredClockSpeed,Capacity)
$gpus=@(Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID,AdapterRAM)
$nics=@(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Select-Object Name,InterfaceDescription,PhysicalMediaType)
$board=Get-CimInstance Win32_BaseBoard | Select-Object -First 1 Manufacturer,Product
$chassis=@((Get-CimInstance Win32_SystemEnclosure).ChassisTypes)
[pscustomobject]@{Disk=$disk;Memory=$mem;Gpus=$gpus;Nics=$nics;Board=$board;Chassis=$chassis}
"""

LAPTOP_CHASSIS = {8, 9, 10, 11, 12, 14, 18, 21, 30, 31, 32}


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _vram_by_name(core) -> Dict[str, float]:
    """VRAM real (GB) por nome de placa. AdapterRAM do WMI trava em 4 GB."""
    out: Dict[str, float] = {}
    winreg = getattr(core, "winreg", None)
    if winreg is None:
        return out
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    for i in range(16):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, fr"{base}\{i:04d}", 0, winreg.KEY_READ) as k:
                try:
                    name = str(winreg.QueryValueEx(k, "DriverDesc")[0])
                except OSError:
                    continue
                size = None
                for value in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                    try:
                        raw = winreg.QueryValueEx(k, value)[0]
                        size = int.from_bytes(raw[:8], "little") if isinstance(raw, (bytes, bytearray)) else int(raw)
                        break
                    except (OSError, ValueError, TypeError):
                        continue
                if size:
                    out[name.lower()] = round(size / (1024 ** 3), 1)
        except OSError:
            continue
    return out


def collect(core, force: bool = False) -> Dict[str, Any]:
    """Tudo que o pré-set precisa saber do PC, numa leitura (cache de 10 min)."""
    path = Path(core.DATA_DIR) / FACTS_FILE
    if not force:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("_at") or 0) < FACTS_TTL:
                return cached
        except Exception:
            pass
    hp = core.hardware_profile(force)
    extra: Dict[str, Any] = {}
    if os.name == "nt":
        try:
            extra = core.powershell_json(_FACTS_SCRIPT, timeout=45) or {}
        except Exception as exc:
            core.log(f"preset facts read failed: {exc}")
    try:
        mem = core.memory_channels_state(force)
    except Exception:
        mem = {}
    try:
        display = core.display_refresh_state()
    except Exception:
        display = {}
    try:
        from azor_managers import WindowsDetection
        build = int(WindowsDetection.read().get("build") or 0)
    except Exception:
        build = 0
    disk = extra.get("Disk") if isinstance(extra.get("Disk"), dict) else {}
    if not disk:
        # Plano B: o que o driver de cada disco interno responde.
        try:
            from .base import internal_disk_media
            media = internal_disk_media(core)
            health = core.storage_health() or {}
            buses = [str(d.get("Bus") or "").upper() for d in health.get("disks") or [] if isinstance(d, dict)]
            if media and all(m == "SSD" for m in media):
                disk = {"Bus": "NVMe" if "NVME" in buses else "SATA", "Media": "SSD", "Name": ""}
            elif media and all(m == "HDD" for m in media):
                disk = {"Bus": "SATA", "Media": "HDD", "Name": ""}
        except Exception:
            disk = {}
    gpus = []
    vram = _vram_by_name(core) if os.name == "nt" else {}
    for g in _as_list(extra.get("Gpus")):
        if isinstance(g, dict) and g.get("Name"):
            name = str(g.get("Name")).strip()
            gpus.append({"name": name, "pnp": str(g.get("PNPDeviceID") or ""),
                         "vram_gb": vram.get(name.lower())})
    if not gpus:
        gpus = [{"name": n, "pnp": "", "vram_gb": None} for n in hp.get("gpus") or []]
    mem_types = [int(m.get("SMBIOSMemoryType") or 0) for m in _as_list(extra.get("Memory")) if isinstance(m, dict)]
    nics = [{"name": str(n.get("Name") or ""), "desc": str(n.get("InterfaceDescription") or ""),
             "media": str(n.get("PhysicalMediaType") or "")} for n in _as_list(extra.get("Nics")) if isinstance(n, dict)]
    chassis = [int(c) for c in _as_list(extra.get("Chassis")) if str(c).isdigit()]
    board = extra.get("Board") if isinstance(extra.get("Board"), dict) else {}
    try:
        streamer = bool(core.load_settings().get("streamer"))
    except Exception:
        streamer = False
    facts = {
        "cpu": {"name": str(hp.get("cpu") or ""), "cores": int(hp.get("cores") or 0),
                "threads": int(hp.get("logical_processors") or 0), "topology": hp.get("topology") or {}},
        "gpus": gpus,
        "ram": {"gb": float(hp.get("ram_gb") or mem.get("total_gb") or 0), "sticks": mem.get("sticks"),
                "single_channel": mem.get("single_channel"), "xmp_off": bool(mem.get("xmp_off")),
                "rated_mhz": mem.get("rated_mhz"), "configured_mhz": mem.get("configured_mhz"),
                "types": sorted(set(t for t in mem_types if t))},
        "disk": {"bus": str(disk.get("Bus") or ""), "media": str(disk.get("Media") or ""), "name": str(disk.get("Name") or "")},
        "battery": bool(hp.get("battery")), "chassis": chassis,
        "board": {"vendor": str(board.get("Manufacturer") or ""), "model": str(board.get("Product") or "")},
        "display": {"current_hz": display.get("current_hz"), "max_hz": display.get("max_hz")},
        "nics": nics, "build": build, "streamer": streamer,
        "_at": time.time(),
    }
    try:
        path.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return facts


# ---------------------------------------------------------------------------
# Classificação: cada peça numa família
# ---------------------------------------------------------------------------
_X3D_DUAL = {"7900", "7950", "9900", "9950"}


def classify_cpu(cpu: Dict[str, Any], laptop: bool) -> Tuple[str, Dict[str, Any]]:
    name = str(cpu.get("name") or "").lower()
    threads = int(cpu.get("threads") or 0)
    topo = cpu.get("topology") or {}
    info: Dict[str, Any] = {"model": cpu.get("name") or ""}
    if threads and threads <= 4:
        return "entry", info
    if "ryzen" in name or "amd" in name:
        m = re.search(r"ryzen\s+(?:ai\s+)?(?:\d+\s+)?(?:pro\s+)?(?:hx\s+)?(\d{3,4})([a-z0-9]*)", name)
        model, suffix = (m.group(1), m.group(2)) if m else ("", "")
        info.update(model=model, suffix=suffix)
        if "x3d" in suffix:
            return ("amd_x3d_dual" if model in _X3D_DUAL else "amd_x3d"), info
        if "ryzen ai" in name or re.search(r"(hs|hx|h|u)$", suffix) or laptop:
            return "amd_mobile", info
        if suffix.startswith("g"):
            return "amd_apu", info
        if "athlon" in name or "fx" in name.split():
            return "entry", info
        return "amd_zen", info
    if "intel" in name or "core" in name or "pentium" in name or "celeron" in name:
        if "pentium" in name or "celeron" in name:
            return "entry", info
        hybrid = topo.get("hybrid")
        gen = 0
        m = re.search(r"i[3579]-(\d{4,5})([a-z]*)", name)
        if m:
            digits, suffix = m.group(1), m.group(2)
            # 5 dígitos (12400) e 4 dígitos começando em 1 (1135G7, 1360P) têm a geração nos dois primeiros.
            gen = int(digits[:2]) if len(digits) == 5 or digits[0] == "1" else int(digits[0])
            info.update(generation=gen, suffix=suffix)
            if hybrid is None:
                tier = re.search(r"i([3579])-", name).group(1)
                hybrid = (gen >= 13 and tier in "579") or (gen == 12 and (tier in "79" or "k" in suffix))
        elif "ultra" in name:
            info.update(generation="ultra")
            if hybrid is None:
                hybrid = True
        mobile = laptop or bool(re.search(r"i[3579]-\d{4,5}(h|hx|hk|hs|u|p|g\d)\b", name)
                                or re.search(r"ultra\s+[3579]\s+\d{3}(h|hx|u|v)\b", name))
        if hybrid:
            return ("intel_hybrid_mobile" if mobile else "intel_hybrid"), info
        return ("intel_mobile" if mobile else "intel_classic"), info
    return "unknown", info


def classify_gpu(gpus: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    names = [str(g.get("name") or "") for g in gpus]
    low = [n.lower() for n in names if n and not re.search(r"basic display|virtual|parsec|remote|idd|spacedesk", n.lower())]
    dgpu, fam = None, None
    order = ["nvidia_rtx40", "nvidia_rtx", "amd_rdna3", "intel_arc", "amd_rdna", "nvidia_gtx", "amd_legacy", "nvidia_legacy"]
    found: Dict[str, str] = {}
    igpu = False
    for n in low:
        if "nvidia" in n or "geforce" in n or "quadro" in n:
            if re.search(r"rtx\s*(40|50)\d\d", n):
                found.setdefault("nvidia_rtx40", n)
            elif re.search(r"rtx\s*(20|30)\d\d|rtx\s*a\d|quadro rtx", n):
                found.setdefault("nvidia_rtx", n)
            elif re.search(r"gtx\s*(16|10)\d\d", n):
                found.setdefault("nvidia_gtx", n)
            else:
                found.setdefault("nvidia_legacy", n)
        elif "radeon" in n or "amd" in n:
            if re.search(r"rx\s*(7|9)\d{3}", n):
                found.setdefault("amd_rdna3", n)
            elif re.search(r"rx\s*(5|6)\d{3}", n):
                found.setdefault("amd_rdna", n)
            elif re.search(r"rx\s*[45]\d\d|vega\s*(56|64)|r9\s|r7\s|radeon vii", n):
                found.setdefault("amd_legacy", n)
            else:
                igpu = True  # "Radeon(TM) Graphics", 680M/780M/890M, Vega 8
        elif "intel" in n:
            if re.search(r"arc\(tm\)\s*[ab]\d|arc\s*[ab]\d{3}", n):
                found.setdefault("intel_arc", n)
            else:
                igpu = True  # UHD, Iris Xe, Arc integrado
    for key in order:
        if key in found:
            fam, dgpu = key, found[key]
            break
    info = {"model": next((n for n in names if n.lower() == dgpu), None) if dgpu else (names[0] if names else ""),
            "igpu": igpu, "hybrid_graphics": bool(fam and igpu),
            "vram_gb": next((g.get("vram_gb") for g in gpus if str(g.get("name") or "").lower() == dgpu), None)}
    if fam:
        return fam, info
    if any("radeon" in n or "amd" in n for n in low):
        return "igpu_amd", info
    if any("intel" in n for n in low):
        return "igpu_intel", info
    return "unknown", info


def classify_ram(gb: float) -> str:
    if gb and gb < 7:
        return "ram_4"
    if gb < 12:
        return "ram_8"
    if gb < 24:
        return "ram_16"
    if gb < 48:
        return "ram_32"
    return "ram_64"


def classify_disk(disk: Dict[str, Any]) -> str:
    bus, media = str(disk.get("bus") or "").upper(), str(disk.get("media") or "").upper()
    if bus == "NVME":
        return "nvme"
    if media == "SSD":
        return "sata_ssd"
    if media == "HDD":
        return "hdd"
    return "unknown"


def classify_net(nics: List[Dict[str, Any]]) -> str:
    if not nics:
        return "unknown"
    wired = [n for n in nics if "802.3" in n.get("media", "") or "ethernet" in (n["desc"] + n["name"]).lower()]
    if wired:
        return "ethernet"
    if any("802.11" in n.get("media", "") or "wi-fi" in (n["desc"] + n["name"]).lower()
           or "wireless" in n["desc"].lower() for n in nics):
        return "wifi"
    return "unknown"


def classify(facts: Dict[str, Any]) -> Dict[str, Any]:
    laptop = bool(facts.get("battery")) or bool(set(facts.get("chassis") or []) & LAPTOP_CHASSIS)
    cpu, cpu_info = classify_cpu(facts.get("cpu") or {}, laptop)
    gpu, gpu_info = classify_gpu(facts.get("gpus") or [])
    ram = facts.get("ram") or {}
    display = facts.get("display") or {}
    build = int(facts.get("build") or 0)
    return {
        "cpu": cpu, "gpu": gpu, "ram": classify_ram(float(ram.get("gb") or 0)), "disk": classify_disk(facts.get("disk") or {}),
        "form": "laptop" if laptop else "desktop", "os": "win11" if build >= 22000 else "win10",
        "net": classify_net(facts.get("nics") or []),
        "flags": {
            "single_channel": bool(ram.get("single_channel")), "xmp_off": bool(ram.get("xmp_off")),
            "hybrid_graphics": bool(gpu_info.get("hybrid_graphics")),
            "high_refresh": bool((display.get("max_hz") or 0) >= 120),
            "streamer": bool(facts.get("streamer")), "ddr5": 34 in (ram.get("types") or []) or 35 in (ram.get("types") or []),
        },
        "cpu_info": cpu_info, "gpu_info": gpu_info,
    }


# ---------------------------------------------------------------------------
# Regras: o que cada família muda no BOOST
# ---------------------------------------------------------------------------
class Decisions:
    def __init__(self):
        self.skip: Dict[str, str] = {}
        self.add: Dict[str, str] = {}
        self.notes: List[Dict[str, Any]] = []
        self.rules: List[str] = []

    def no(self, task_id: str, why: str):
        self.skip.setdefault(task_id, why)
        self.add.pop(task_id, None)

    def yes(self, task_id: str, why: str):
        if task_id not in self.skip:
            self.add.setdefault(task_id, why)

    def note(self, level: str, title: str, text: str, action: Optional[Dict[str, Any]] = None):
        self.notes.append({"level": level, "title": title, "text": text, "action": action})


RULES: List[Tuple[str, Callable[[Dict[str, Any], Decisions], bool]]] = []


def rule(name: str):
    def wrap(fn):
        RULES.append((name, fn))
        return fn
    return wrap


# ---- formato ---------------------------------------------------------------
@rule("Notebook: nada que derreta bateria ou esquente fechado")
def _laptop(c, d):
    if c["form"] != "laptop":
        return False
    d.no("global_timer_resolution", "Notebook: timer global de 0,5 ms gasta bateria o dia inteiro.")
    d.no("nvme_idle_never", "Notebook: SSD sempre acordado esquenta e gasta bateria.")
    d.no("usb_hub_power_off", "Notebook: portas USB sempre ligadas gastam bateria mesmo sem nada plugado.")
    d.no("hibernate_off", "Notebook: a hibernação salva seu trabalho quando a bateria acaba.")
    d.no("power_throttling_off", "Notebook: sem a economia do Windows, a bateria e a temperatura sofrem.")
    d.no("nic_interrupt_moderation_off", "Notebook: placa de rede sem espera gasta mais CPU e bateria.")
    d.no("lockscreen_off", "Notebook: a tela de bloqueio protege quando você fecha a tampa fora de casa.")
    d.no("location_off", "Notebook: a localização acerta o fuso horário quando você viaja.")
    d.note("action", "Jogue sempre na tomada",
           "Na bateria o notebook corta o processador e a placa de vídeo pela metade, com ou sem otimização. "
           "Ligue também o modo Desempenho/Turbo do software do fabricante (Armoury Crate, Vantage, Omen Gaming Hub, "
           "Dragon Center, NitroSense).")
    return True


@rule("Desktop: tudo no máximo o tempo todo")
def _desktop(c, d):
    if c["form"] != "desktop":
        return False
    d.yes("lockscreen_off", "Desktop: pula a tela de bloqueio (a senha continua pedida).")
    d.yes("location_off", "Desktop não muda de lugar: localização desligada tira um serviço do fundo.")
    return True


# ---- processador -------------------------------------------------------------
@rule("Intel híbrido: deixar o Windows mandar o fundo para os núcleos E")
def _intel_hybrid(c, d):
    if c["cpu"] not in ("intel_hybrid", "intel_hybrid_mobile"):
        return False
    d.no("power_throttling_off",
         "Intel híbrido: é a economia de energia do Windows que empurra Discord, navegador e updates para os "
         "núcleos E, deixando os núcleos P livres para o jogo. Desligar faria o fundo disputar com o jogo.")
    if c["os"] == "win10":
        d.note("warn", "Windows 11 rende mais neste processador",
               "O Windows 10 não conhece o Thread Director dos Intel 12ª geração em diante e às vezes joga o jogo "
               "nos núcleos E. No Windows 11 o 1% low sobe visivelmente.")
    return True


@rule("Ryzen X3D de dois CCDs: o Windows precisa estacionar o CCD sem 3D V-Cache")
def _x3d_dual(c, d):
    if c["cpu"] != "amd_x3d_dual":
        return False
    d.no("power_plan",
         "Ryzen X3D de dois CCDs: o driver da AMD só estaciona os núcleos sem 3D V-Cache no plano Equilibrado. "
         "Em Alto desempenho o jogo pode cair no CCD errado e perder FPS.")
    d.yes("game_mode", "Ryzen X3D: o Modo de Jogo é o sinal que o driver da AMD usa para mandar o jogo ao CCD certo.")
    d.note("action", "Instale o AMD Chipset Driver",
           "Ele traz o '3D V-Cache Performance Optimizer'. Não desinstale a Xbox Game Bar: é ela que diz ao Windows "
           "que um jogo abriu (o AZOR nunca remove a Game Bar).",
           {"kind": "link", "url": "https://www.amd.com/pt/support/download/drivers.html"})
    return True


@rule("Ryzen X3D: nada de overclock no processador")
def _x3d(c, d):
    if c["cpu"] != "amd_x3d":
        return False
    d.note("info", "X3D já vem no limite",
           "Deixe PBO e Curve Optimizer em Auto. O ganho do X3D vem do cache: memória com EXPO ligado e jogo no "
           "Modo de Jogo são o que importa.")
    return True


@rule("Ryzen: memória e Infinity Fabric")
def _ryzen(c, d):
    if c["cpu"] not in ("amd_zen", "amd_x3d", "amd_x3d_dual", "amd_apu"):
        return False
    if c["flags"]["xmp_off"]:
        d.note("action", "Ligue o EXPO/DOCP na BIOS",
               "No Ryzen a velocidade da memória também acelera o Infinity Fabric: é FPS e 1% low direto.",
               {"kind": "goto", "target": "hardware", "tab": "bios"})
    return True


@rule("Processador de entrada: cada ciclo de CPU vai para o jogo")
def _entry_cpu(c, d):
    if c["cpu"] != "entry":
        return False
    d.no("nic_interrupt_moderation_off", "Processador de 4 threads: placa de rede sem espera gera interrupção demais.")
    d.note("info", "Feche tudo antes de jogar",
           "Com 4 threads, navegador e Discord abertos disputam o processador com o jogo. O Modo Turbo abaixa a "
           "prioridade deles enquanto o jogo roda.")
    return True


# ---- placa de vídeo ------------------------------------------------------------
@rule("Placa antiga: sem agendamento de GPU por hardware")
def _gpu_legacy(c, d):
    if c["gpu"] not in ("nvidia_legacy", "amd_legacy"):
        return False
    d.no("hags", "Placa de vídeo antiga: o agendamento por hardware não é suportado ou causa travadinhas.")
    return True


@rule("RTX 40/50: agendamento por hardware obrigatório")
def _rtx40(c, d):
    if c["gpu"] != "nvidia_rtx40":
        return False
    d.yes("hags", "RTX 40/50: sem o agendamento de GPU por hardware o Frame Generation (DLSS 3/4) nem aparece no jogo.")
    d.note("info", "Ligue o Reflex nos jogos",
           "Reflex 'Ligado + Boost' corta o delay do sistema mais do que qualquer ajuste do Windows.")
    return True


@rule("NVIDIA: painel do driver")
def _nvidia(c, d):
    if not c["gpu"].startswith("nvidia"):
        return False
    d.note("info", "Painel NVIDIA por jogo",
           "Modo de gerenciamento de energia: Preferir desempenho máximo. Baixa latência: Ultra (ou Reflex no jogo). "
           "O caminho exato está em Hardware > Drivers.", {"kind": "goto", "target": "hardware", "tab": "drivers"})
    return True


@rule("Radeon: painel Adrenalin")
def _radeon(c, d):
    if c["gpu"] not in ("amd_rdna3", "amd_rdna", "amd_legacy"):
        return False
    d.note("info", "Adrenalin por jogo",
           "Anti-Lag ligado, Radeon Chill desligado, Aguardar atualização vertical desligado.",
           {"kind": "goto", "target": "hardware", "tab": "drivers"})
    return True


@rule("Só vídeo integrado: a memória RAM é a memória de vídeo")
def _igpu(c, d):
    if c["gpu"] not in ("igpu_intel", "igpu_amd"):
        return False
    d.no("all_games_gpu", "Só vídeo integrado: não existe placa dedicada para escolher.")
    d.note("action" if c["flags"]["single_channel"] else "info", "Dois pentes de RAM iguais",
           "O vídeo integrado usa a RAM como memória de vídeo. Dual channel (dois pentes) dá de 20% a 40% mais FPS; "
           "memória rápida (XMP/EXPO) soma mais.", {"kind": "goto", "target": "hardware"})
    return True


@rule("Notebook com duas placas: jogo sempre na dedicada")
def _hybrid_graphics(c, d):
    if not c["flags"]["hybrid_graphics"]:
        return False
    d.yes("all_games_gpu", "Duas placas de vídeo: força cada jogo encontrado na placa dedicada.")
    if c["form"] == "laptop":
        d.note("info", "Modo só-dedicada (MUX)",
               "Se o notebook tiver MUX Switch (Armoury Crate: 'Ultimate'/'dGPU'; Omen: 'Discrete'), ligue: "
               "tira o vídeo integrado do caminho e dá de 5% a 15% mais FPS.")
    return True


# ---- memória ----------------------------------------------------------------------
@rule("Pouca memória: menos coisa residente")
def _low_ram(c, d):
    if c["ram"] not in ("ram_4", "ram_8"):
        return False
    d.no("kernel_no_paging", "Pouca RAM: prender o núcleo do Windows na memória tiraria espaço do jogo.")
    d.no("memory_compression_off", "Pouca RAM: a compressão de memória é o que evita travadas quando ela enche.")
    d.note("warn", "A memória é o gargalo deste PC",
           "Com 8 GB o Windows e o jogo disputam cada megabyte. O BOOST tira o máximo de processos, e o Modo Turbo "
           "libera a memória em espera durante o jogo. Upgrade que mais dá resultado: 16 GB em dual channel.")
    return True


@rule("Memória de sobra: nada de compressão")
def _big_ram(c, d):
    if c["ram"] not in ("ram_32", "ram_64"):
        return False
    d.yes("memory_compression_off", "32 GB ou mais: sem comprimir memória o processador fica livre para o jogo.")
    return True


@rule("Memória em canal único ou lenta")
def _ram_config(c, d):
    hit = False
    if c["flags"]["single_channel"] and c["gpu"] not in ("igpu_intel", "igpu_amd"):
        d.note("action", "Memória trabalhando pela metade",
               "Só um pente (ou pentes nos slots errados): a banda de memória cai pela metade. Em jogos de "
               "processador (Valorant, CS2, Fortnite) o 1% low sofre.", {"kind": "goto", "target": "hardware"})
        hit = True
    if c["flags"]["xmp_off"] and c["cpu"] not in ("amd_zen", "amd_x3d", "amd_x3d_dual", "amd_apu"):
        d.note("action", "Ligue o XMP na BIOS",
               "A memória está rodando abaixo da velocidade dos pentes.", {"kind": "goto", "target": "hardware", "tab": "bios"})
        hit = True
    return hit


# ---- disco --------------------------------------------------------------------------
@rule("Windows em HD mecânico: tirar todo acesso de disco do fundo")
def _hdd(c, d):
    if c["disk"] != "hdd":
        return False
    d.yes("services_extreme", "HD mecânico: o indexador de pesquisa é o que mais trava o disco em segundo plano.")
    d.note("warn", "Um SSD é o maior upgrade deste PC",
           "Com o Windows em HD mecânico, carregamento e travadas ao abrir mapa só somem com um SSD. "
           "O BOOST corta o que mais usa o disco, mas não faz milagre.")
    return True


@rule("SSD NVMe no desktop: sem latência de acordar")
def _nvme_desktop(c, d):
    if not (c["disk"] == "nvme" and c["form"] == "desktop"):
        return False
    d.yes("nvme_idle_never", "NVMe no desktop: o SSD não entra em economia e responde na hora.")
    return True


# ---- sistema e rede ---------------------------------------------------------------
@rule("Wi-Fi: ping instável")
def _wifi(c, d):
    if c["net"] != "wifi":
        return False
    d.note("info", "Use cabo para jogar",
           "No Wi-Fi o ping varia com a distância e as redes vizinhas. Um cabo de rede corta picos e perda de pacote "
           "mais do que qualquer ajuste.")
    return True


@rule("Quem faz live: preservar overlay e encoder")
def _streamer(c, d):
    if not c["flags"]["streamer"]:
        return False
    d.no("fullscreen_exclusive", "Live: tela cheia exclusiva derruba o overlay do Discord e a captura de jogo do OBS.")
    d.no("fortnite_fullscreen_exclusive", "Live: tela cheia exclusiva no Fortnite atrapalha a captura.")
    return True


@rule("Windows sem enfeite: tudo que é inútil fora")
def _everyone(c, d):
    d.yes("keyboard_repeat_fast", "Teclado repetindo na velocidade máxima: menos delay em menu e chat.")
    d.yes("start_recommendations_off", "Menu Iniciar sem propaganda e sem 'recomendados'.")
    d.yes("login_blur_off", "Login sem efeito de desfoque.")
    d.yes("home_gallery_off", "Explorador abrindo direto em Este Computador, sem carregar a Galeria.")
    return True


# ---------------------------------------------------------------------------
# Montagem do pré-set
# ---------------------------------------------------------------------------
def _fingerprint(c: Dict[str, Any], facts: Dict[str, Any]) -> str:
    parts = [str(facts.get("cpu", {}).get("name")), "|".join(sorted(g.get("name", "") for g in facts.get("gpus") or [])),
             str(round(float(facts.get("ram", {}).get("gb") or 0))), c["disk"], c["form"], str(facts.get("board"))]
    return hashlib.sha1("§".join(parts).encode("utf-8")).hexdigest()[:16]


def build_from_facts(facts: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
    """Pura: fatos do PC -> pré-set. É o que os testes exercitam com milhares de combinações."""
    c = classify(facts)
    d = Decisions()
    for name, fn in RULES:
        if fn(c, d):
            d.rules.append(name)
    labels = {dim: fams.get(c[dim], fams.get("unknown", ("", "")))[0] for dim, fams in DIMENSIONS}
    key = ".".join([c["form"], c["cpu"], c["gpu"], c["ram"], c["disk"], c["os"], c["net"]])
    name = " · ".join([labels["form"], labels["cpu"], labels["gpu"], labels["ram"], labels["disk"]])
    chips = [
        {"dim": "form", "label": labels["form"], "detail": ""},
        {"dim": "cpu", "label": labels["cpu"], "detail": c["cpu_info"].get("model") or ""},
        {"dim": "gpu", "label": labels["gpu"], "detail": (c["gpu_info"].get("model") or "")
         + (f" · {c['gpu_info']['vram_gb']:g} GB" if c["gpu_info"].get("vram_gb") else "")},
        {"dim": "ram", "label": labels["ram"], "detail": ("DDR5" if c["flags"]["ddr5"] else "")
         + (" · canal único" if c["flags"]["single_channel"] else "")},
        {"dim": "disk", "label": labels["disk"], "detail": (facts.get("disk") or {}).get("name") or ""},
        {"dim": "os", "label": labels["os"], "detail": f"build {facts.get('build')}" if facts.get("build") else ""},
        {"dim": "net", "label": labels["net"], "detail": ""},
    ]
    auto = mode == "auto"
    return {
        "ok": True, "key": key, "name": name, "chips": chips, "classes": {k: c[k] for k in ("cpu", "gpu", "ram", "disk", "form", "os", "net")},
        "flags": c["flags"], "fingerprint": _fingerprint(c, facts),
        # Automático: a base é o Extremo, podado pelo que esta máquina não aguenta.
        "base": "agressivo" if auto else mode,
        "skip": d.skip,
        # Itens a mais só no Automático; nos modos manuais vale só a proteção (skip).
        "add": d.add if auto else {},
        "notes": d.notes, "rules": d.rules,
        "startup_extreme": True if auto else mode == "agressivo",
        "close_processes": True,
        "turbo": c["form"] == "desktop",
    }


def _memory_path(core) -> Path:
    return Path(core.DATA_DIR) / MEMORY_FILE


def _memory(core) -> Dict[str, Any]:
    try:
        data = json.loads(_memory_path(core).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve(core, mode: str = "auto", force: bool = False) -> Dict[str, Any]:
    """Pré-set deste PC, reconhecido pela memória do app quando ele já foi visto."""
    mode = mode if mode in ("auto", "maximo", "agressivo") else "auto"
    facts = collect(core, force)
    preset = build_from_facts(facts, mode)
    seen = _memory(core).get(preset["fingerprint"]) or {}
    preset["memory"] = {"known": bool(seen), "first_seen": seen.get("first_seen"),
                        "last_applied": seen.get("last_applied"), "applied_count": int(seen.get("applied_count") or 0),
                        "previous_key": seen.get("key")}
    preset["library"] = {"combinations": library()["combinations"]}
    preset["mode"] = mode
    return preset


def remember(core, preset: Dict[str, Any], applied: bool = False) -> None:
    data = _memory(core)
    entry = data.get(preset["fingerprint"]) or {"first_seen": time.time()}
    entry.update(key=preset["key"], name=preset["name"])
    if applied:
        entry["last_applied"] = time.time()
        entry["applied_count"] = int(entry.get("applied_count") or 0) + 1
    data[preset["fingerprint"]] = entry
    try:
        _memory_path(core).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def engine_view(preset: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """O pedaço que o motor de tweaks usa (sem os textos da tela)."""
    if not preset:
        return None
    return {"skip": dict(preset.get("skip") or {}), "add": dict(preset.get("add") or {}), "name": preset.get("name")}
