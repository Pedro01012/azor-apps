"""Confere o motor de pré-sets contra centenas de milhares de combinações de hardware.

Uso: runtime\\python.exe tools\\testar_presets.py
Não toca no Windows: só monta os pré-sets em memória e valida as regras de segurança.
"""
from pathlib import Path
import itertools
import sys
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
os.environ.setdefault('AZOR_DATA_DIR', tempfile.mkdtemp(prefix='azor-teste-'))

from azor_modules import presets as P, engine, policy  # noqa: E402

CPUS = ["Intel(R) Core(TM) i5-13400F", "Intel(R) Core(TM) i3-12100F", "Intel(R) Core(TM) i7-12700H",
        "Intel(R) Core(TM) i5-1135G7", "Intel(R) Core(TM) i5-4460", "Intel(R) Core(TM) Ultra 7 265K",
        "AMD Ryzen 7 7800X3D 8-Core Processor", "AMD Ryzen 9 7950X3D 16-Core Processor",
        "AMD Ryzen 5 5600G with Radeon Graphics", "AMD Ryzen 7 7840HS", "AMD Ryzen 5 3600 6-Core Processor", "CPU X"]
GPUS = [["NVIDIA GeForce RTX 4060 Laptop GPU", "Intel(R) UHD Graphics"], ["NVIDIA GeForce RTX 3060"],
        ["NVIDIA GeForce GTX 1650"], ["NVIDIA GeForce GTX 970"], ["AMD Radeon RX 7800 XT"], ["AMD Radeon RX 6600"],
        ["AMD Radeon RX 580"], ["Intel(R) Arc(TM) A770 Graphics"], ["AMD Radeon(TM) Graphics"],
        ["Intel(R) UHD Graphics 770"], []]
DISKS = [{"bus": "NVMe"}, {"bus": "SATA", "media": "SSD"}, {"bus": "SATA", "media": "HDD"}, {}]
NETS = [[{"name": "Ethernet", "desc": "", "media": "802.3"}], [{"name": "Wi-Fi", "desc": "", "media": "Native 802.11"}], []]


def main():
    ids = {t.id for t in engine._all_tasks()}
    count, errors, keys = 0, [], set()
    for cpu, gpu, ram, disk, laptop, build, net, single, streamer, mode in itertools.product(
            CPUS, GPUS, (4, 8, 16, 32, 64), DISKS, (False, True), (19045, 26100), NETS, (False, True), (False, True),
            ("auto", "maximo", "agressivo")):
        facts = {"cpu": {"name": cpu, "threads": 4 if "4460" in cpu else 12, "topology": {}},
                 "gpus": [{"name": g} for g in gpu], "ram": {"gb": ram, "single_channel": single},
                 "disk": disk, "battery": laptop, "chassis": [10 if laptop else 3], "build": build, "nics": net,
                 "streamer": streamer, "display": {"max_hz": 144}}
        p = P.build_from_facts(facts, mode)
        count += 1
        keys.add(p["key"])
        unknown = [t for t in list(p["skip"]) + list(p["add"]) if t not in ids]
        if unknown:
            errors.append(f"{p['key']}: ajuste inexistente {unknown}")
        if set(p["skip"]) & set(p["add"]):
            errors.append(f"{p['key']}: o mesmo ajuste ligado e protegido")
        if mode != "auto" and p["add"]:
            errors.append(f"{p['key']}: extras fora do modo Automático")
        if laptop and not {"global_timer_resolution", "hibernate_off", "nvme_idle_never"} <= set(p["skip"]):
            errors.append(f"{p['key']}: notebook sem proteção de bateria")
        if "x3d_dual" in p["key"] and "power_plan" not in p["skip"]:
            errors.append(f"{p['key']}: X3D de dois CCDs com Alto desempenho")
        if streamer and "fullscreen_exclusive" not in p["skip"]:
            errors.append(f"{p['key']}: live sem preservar o overlay")
        if not [t for t in ids if policy.in_batch(t, p["base"], p)[0]]:
            errors.append(f"{p['key']}: lote vazio")
    print(f"{count} combinações, {len(keys)} pré-sets distintos, {len(errors)} erro(s).")
    for e in errors[:20]:
        print(" -", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
