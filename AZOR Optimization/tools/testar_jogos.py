"""Confere a edição dos arquivos de jogo (Minecraft e CS2) em pastas temporárias.

Uso: runtime\\python.exe tools\\testar_jogos.py
Não toca em jogo nenhum: cria arquivos de mentira, aplica, confere, volta.
"""
from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
os.environ.setdefault('AZOR_DATA_DIR', tempfile.mkdtemp(prefix='azor-teste-'))

from azor_modules import gameconfig as G  # noqa: E402

MC = ("version:3465\nautoJump:false\nmaxFps:120\nenableVsync:true\nrenderDistance:16\nsimulationDistance:12\n"
      "entityShadows:true\nparticles:0\ngraphicsMode:2\nentityDistanceScaling:1.0\nbiomeBlendRadius:2\n"
      "key_key.attack:key.mouse.left\nkey_key.jump:key.keyboard.space\nrenderClouds:\"true\"\nlang:pt_br\n")
CS = ('"video.cfg"\n{\n\t"setting.mat_vsync"\t\t"1"\n\t"setting.videocfg_shadow_quality"\t\t"3"\n'
      '\t"setting.videocfg_dynamic_shadows"\t\t"1"\n\t"setting.videocfg_particle_detail"\t\t"2"\n'
      '\t"setting.videocfg_ao_detail"\t\t"2"\n\t"setting.msaa_samples"\t\t"4"\n\t"setting.r_csgo_cmaa_enable"\t\t"0"\n'
      '\t"setting.fullscreen"\t\t"1"\n}\n')

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


class FakeCore:
    def __init__(self, data_dir, running=()):
        self.DATA_DIR = data_dir
        self.running = list(running)
        self.events = []

    def _process_names(self):
        return self.running

    def journal(self, event, **fields):
        self.events.append(event)


def main():
    # 1. Minecraft, só o cálculo
    plan = G.plan_text("colon", MC, G.MINECRAFT, "fps")
    new = plan["text"]
    check("maxFps:260" in new and "enableVsync:false" in new and "renderDistance:8" in new, "mc: valores novos")
    check("particles:2" in new and "graphicsMode:0" in new and "entityShadows:false" in new, "mc: valores novos 2")
    check("key_key.attack:key.mouse.left" in new and "lang:pt_br" in new and 'renderClouds:"true"' in new, "mc: o resto intacto")
    check("fancyGraphics" not in new and "useVbo" not in new, "mc: não inventou chave")
    check({"fancyGraphics", "useVbo"} <= set(plan["missing"]), "mc: chaves ausentes reportadas")
    check(G.plan_text("colon", new, G.MINECRAFT, "fps")["changes"] == [], "mc: aplicar 2x não muda nada")
    crlf = G.plan_text("colon", MC.replace("\n", "\r\n"), G.MINECRAFT, "fps")["text"]
    check(crlf.count("\r\n") == MC.count("\n") and "\n" not in crlf.replace("\r\n", ""), "mc: fim de linha CRLF preservado")
    odd = G.plan_text("colon", "maxFps:\"abc\"\nrenderDistance:oito\n", G.MINECRAFT, "fps")
    check(len(odd["skipped"]) == 2 and not odd["changes"], "mc: formato estranho é pulado")
    eq = G.plan_text("colon", MC, G.MINECRAFT, "equilibrado")["text"]
    check("renderDistance:12" in eq and "graphicsMode:1" in eq, "mc: nível equilibrado")

    # 2. CS2
    plan = G.plan_text("kv", CS, G.CS2, "fps")
    new = plan["text"]
    check('"setting.mat_vsync"\t\t"0"' in new and '"setting.videocfg_shadow_quality"\t\t"0"' in new, "cs2: valores novos")
    check('"setting.msaa_samples"\t\t"0"' in new and '"setting.r_csgo_cmaa_enable"\t\t"1"' in new, "cs2: msaa e cmaa")
    check('"setting.fullscreen"\t\t"1"' in new and new.startswith('"video.cfg"\n{'), "cs2: o resto intacto")
    eq = G.plan_text("kv", CS, G.CS2, "equilibrado")["text"]
    check('"setting.msaa_samples"\t\t"4"' in eq, "cs2: equilibrado não mexe no MSAA")

    # 3. Fluxo completo com arquivos de mentira
    tmp = Path(tempfile.mkdtemp(prefix="azor-jogos-"))
    opts = tmp / "options.txt"
    opts.write_bytes(MC.encode("utf-8"))
    core = FakeCore(tmp / "dados")
    core.DATA_DIR.mkdir()
    G.GAMES["minecraft"]["files"] = lambda c: [opts]
    G.GAMES["cs2"]["files"] = lambda c: []

    scan = G.scan(core)
    check(len(scan["games"]) == 1 and scan["games"][0]["pending"] > 5 and not scan["games"][0]["applied"], "scan: achou e prevê")

    core.running = ["javaw.exe"]
    check(not G.apply(core, "minecraft")["ok"] and opts.read_bytes() == MC.encode(), "jogo aberto: recusa e não grava")
    core.running = []

    r = G.apply(core, "minecraft")
    check(r["ok"] and r["changes"] and "maxFps:260" in opts.read_text(), "apply: grava")
    first_backups = sorted((core.DATA_DIR / "gamecfg_backups").iterdir())
    check(len(first_backups) == 1 and first_backups[0].read_bytes() == MC.encode(), "apply: backup é o original")
    check(G.scan(core)["games"][0]["applied"], "scan: marca como aplicado")

    r2 = G.apply(core, "minecraft")
    check(r2["ok"] and not r2.get("changes"), "apply 2x: nada a mudar")
    r3 = G.apply(core, "minecraft", "equilibrado")
    check(r3["ok"] and "renderDistance:12" in opts.read_text(), "apply: trocar de nível")
    check(len(list((core.DATA_DIR / "gamecfg_backups").iterdir())) == 1, "apply: continua com UM backup, o original")

    core.running = ["javaw.exe"]
    check(not G.restore(core, "minecraft")["ok"], "restore: recusa com o jogo aberto")
    core.running = []
    r4 = G.restore(core, "minecraft")
    check(r4["ok"] and opts.read_bytes() == MC.encode(), "restore: devolve o original byte a byte")
    check(not G.scan(core)["games"][0]["applied"], "restore: limpa o estado")
    check(not G.restore(core, "minecraft")["ok"], "restore sem backup: avisa")

    # 4. Arquivo que não é UTF-8 não pode ser tocado
    bad = tmp / "latin.txt"
    bad.write_bytes("maxFps:60\nnome:ação\n".encode("latin-1"))
    G.GAMES["minecraft"]["files"] = lambda c: [bad]
    before = bad.read_bytes()
    r5 = G.apply(core, "minecraft")
    check(not r5["ok"] and bad.read_bytes() == before, "latin-1: não mexe")

    check(not G.apply(core, "zzz")["ok"], "jogo desconhecido")

    print(f"{len(failures)} falha(s).")
    for f in failures:
        print(" -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
