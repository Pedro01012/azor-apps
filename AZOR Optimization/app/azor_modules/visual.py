"""Efeitos visuais do Windows no modo desempenho - de verdade.

A versão anterior gravava só VisualFXSetting=2, que é o botão de opção
selecionado na tela de Opções de Desempenho: o Windows não desliga animação
nenhuma por causa dele. O WinUtil gravava UserPreferencesMask direto no
registro, que só vale depois de sair e entrar.

Aqui cada efeito é desligado por SystemParametersInfo, a mesma chamada que a
tela do Windows usa: vale na hora, sem logoff, e o próprio Windows atualiza o
UserPreferencesMask. A suavização de fonte e as miniaturas ficam ligadas.
Os valores originais ficam num arquivo próprio para o desfazer.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

SPIF = 0x01 | 0x02  # SPIF_UPDATEINIFILE | SPIF_SENDCHANGE

# nome, SPI_GET, SPI_SET, como passar o valor no SET
BOOL_EFFECTS: Tuple[Tuple[str, int, int, str], ...] = (
    ("menu_animation", 0x1002, 0x1003, "pv"),
    ("combobox_animation", 0x1004, 0x1005, "pv"),
    ("listbox_smooth_scroll", 0x1006, 0x1007, "pv"),
    ("menu_fade", 0x1012, 0x1013, "pv"),
    ("selection_fade", 0x1014, 0x1015, "pv"),
    ("tooltip_animation", 0x1016, 0x1017, "pv"),
    ("tooltip_fade", 0x1018, 0x1019, "pv"),
    ("cursor_shadow", 0x101A, 0x101B, "pv"),
    ("drop_shadow", 0x1024, 0x1025, "pv"),
    ("client_area_animation", 0x1042, 0x1043, "pv"),
    ("drag_full_windows", 0x0026, 0x0025, "ui"),
)
SPI_GETANIMATION, SPI_SETANIMATION = 0x0048, 0x0049

REGISTRY_VALUES = (
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects", "VisualFXSetting", 3),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "TaskbarAnimations", 0),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "ListviewAlphaSelect", 0),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "ListviewShadow", 0),
    ("HKCU", r"Software\Microsoft\Windows\DWM", "EnableAeroPeek", 0),
)
ORIGINALS = "visual_effects_before.json"


class _ANIMATIONINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("iMinAnimate", ctypes.c_int)]


def _user32():
    if os.name != "nt":
        raise OSError("Windows only")
    fn = ctypes.windll.user32.SystemParametersInfoW
    fn.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    return fn


def read_effects() -> Dict[str, bool]:
    spi = _user32()
    out: Dict[str, bool] = {}
    for name, get, _set, _mode in BOOL_EFFECTS:
        value = ctypes.c_int(0)
        if spi(get, 0, ctypes.byref(value), 0):
            out[name] = bool(value.value)
    anim = _ANIMATIONINFO(ctypes.sizeof(_ANIMATIONINFO), 0)
    if spi(SPI_GETANIMATION, ctypes.sizeof(anim), ctypes.byref(anim), 0):
        out["minimize_animation"] = bool(anim.iMinAnimate)
    return out


def write_effects(values: Dict[str, bool]) -> List[str]:
    spi = _user32()
    failed: List[str] = []
    for name, _get, set_, mode in BOOL_EFFECTS:
        if name not in values:
            continue
        flag = 1 if values[name] else 0
        ok = spi(set_, flag, None, SPIF) if mode == "ui" else spi(set_, 0, ctypes.c_void_p(flag), SPIF)
        if not ok:
            failed.append(name)
    if "minimize_animation" in values:
        anim = _ANIMATIONINFO(ctypes.sizeof(_ANIMATIONINFO), 1 if values["minimize_animation"] else 0)
        if not spi(SPI_SETANIMATION, ctypes.sizeof(anim), ctypes.byref(anim), SPIF):
            failed.append("minimize_animation")
    return failed


def _originals_path(core) -> Path:
    return Path(core.DATA_DIR) / ORIGINALS


def _registry_dicts() -> List[Dict[str, Any]]:
    return [{"root": r, "path": p, "name": n, "value": v} for r, p, n, v in REGISTRY_VALUES]


def apply(core, ctx):
    before = read_effects()
    path = _originals_path(core)
    if not path.exists():
        # Primeira vez: é o estado anterior ao AZOR. Nunca é sobrescrito.
        path.write_text(json.dumps(before, indent=2), encoding="utf-8")
    failed = write_effects({name: False for name in before})
    ok_reg, reg_detail = core.write_registry_values_verified(_registry_dicts())
    if failed:
        return False, "O Windows recusou desligar: " + ", ".join(failed)
    if not ok_reg:
        return False, reg_detail
    return True, f"{len(before)} efeito(s) desligado(s) na hora; suavização de fonte preservada."


def verify(core, ctx):
    on = [name for name, value in read_effects().items() if value]
    ok_reg, reg_detail = core.verify_registry_values(_registry_dicts())
    ok = not on and ok_reg
    return ok, ("Animações e sombras relidas como desligadas." if ok
                else "Ainda ligados: " + ", ".join(on) if on else reg_detail)


def revert(core, ctx):
    path = _originals_path(core)
    if not path.exists():
        return False, "O AZOR não registrou como os efeitos estavam antes; nada foi alterado."
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"O registro dos efeitos originais está ilegível: {exc}"
    failed = write_effects({k: bool(v) for k, v in saved.items()})
    ok_reg, reg_detail = core.revert_registry_from_baseline([(r, p, n) for r, p, n, _ in REGISTRY_VALUES],
                                                            "visual_effects")
    if failed:
        return False, "Não voltaram: " + ", ".join(failed)
    return ok_reg, ("Efeitos visuais de volta como estavam." if ok_reg else reg_detail)
