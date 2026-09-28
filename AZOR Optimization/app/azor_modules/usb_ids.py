"""Quem fabricou o periférico, pelo código USB - e não pelo nome que o Windows mostra.

O nome que aparece no Gerenciador de Dispositivos e o do DRIVER. Um GameSir em
modo XInput vira "Controlador XBOX 360 para Windows" porque emula esse controle
para os jogos o reconhecerem; o próprio firmware responde "Xbox 360 Controller
for Windows" quando o Windows pergunta. O VID (vendor id) do USB e o único dado
que diz quem fez o aparelho.

Dois tipos de entrada na tabela:
  marca  o VID e da empresa que vende o produto (GameSir, Sony, 8BitDo...)
  chip   o VID e do fabricante do chip USB, usado por dezenas de marcas. Dizer
         a marca do produto a partir disso seria chute, então a tela diz "chip X".

So entram VIDs conferidos na lista publica de IDs USB (usb.ids). VID fora da
tabela aparece como código, sem nome inventado.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

USB_VENDORS: Dict[str, tuple] = {
    # Controles
    "045E": ("Microsoft", "marca"),
    "054C": ("Sony", "marca"),
    "057E": ("Nintendo", "marca"),
    "3537": ("GameSir", "marca"),
    "2DC8": ("8BitDo", "marca"),
    "0F0D": ("HORI", "marca"),
    "0E6F": ("PDP", "marca"),
    "24C6": ("PowerA", "marca"),
    "20D6": ("PowerA", "marca"),
    "044F": ("Thrustmaster", "marca"),
    "0738": ("Mad Catz", "marca"),
    # Mouse e teclado
    "1532": ("Razer", "marca"),
    "046D": ("Logitech", "marca"),
    "1038": ("SteelSeries", "marca"),
    "1B1C": ("Corsair", "marca"),
    "0951": ("Kingston (HyperX)", "marca"),
    "03F0": ("HP", "marca"),
    "3434": ("Keychron", "marca"),
    "413C": ("Dell", "marca"),
    "17EF": ("Lenovo", "marca"),
    # Chips usados por varias marcas
    "2563": ("ShanWan", "chip"),
    "0079": ("DragonRise", "chip"),
    "258A": ("Sino Wealth", "chip"),
    "25A7": ("Areson", "chip"),
    "04D9": ("Holtek", "chip"),
    "1A2C": ("China Resource Semico", "chip"),
    "093A": ("PixArt", "chip"),
    "1915": ("Nordic Semiconductor", "chip"),
    "0C45": ("Microdia", "chip"),
}

KIND_LABEL = {"controller": "controle", "mouse": "mouse", "keyboard": "teclado"}

# Nomes que o Windows usa quando nao sabe nada do aparelho. Com um desses, o
# fabricante pelo VID diz mais do que o nome.
_GENERIC_NAMES = (
    "hid", "dispositivo de entrada usb", "usb input device", "compatível com hid",
    "compativel com hid", "hid-compliant", "dispositivo de teclado", "keyboard device",
    "standard ps/2", "unknown", "controlador de jogo", "game controller", "gamepad",
)


def extract_vid_pid(dev_id: Any) -> Dict[str, Optional[str]]:
    match = re.search(r"VID_([0-9A-F]{4}).*PID_([0-9A-F]{4})", str(dev_id or ""), re.I)
    if not match:
        return {"vid": None, "pid": None}
    return {"vid": match.group(1).upper(), "pid": match.group(2).upper()}


def vendor(vid: Optional[str]) -> Optional[Dict[str, str]]:
    entry = USB_VENDORS.get(str(vid or "").upper())
    if not entry:
        return None
    return {"name": entry[0], "kind": entry[1]}


def looks_xinput(name: Any, cls: Any = "", ident: Any = "") -> bool:
    """O Windows esta falando com o aparelho pelo driver de Xbox 360 (XInput)?"""
    low = f"{name or ''} {cls or ''}".casefold()
    return (str(cls or "").casefold() in ("xnacomposite", "xboxcomposite")
            or "IG_" in str(ident or "").upper()
            or "xbox 360" in low or "xinput" in low)


def identify(kind: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Identidade honesta de um dispositivo detectado.

    Devolve o nome para a tela, o fabricante pelo VID e, quando o aparelho emula
    outro (um controle de terceiro em modo XInput), a explicacao do porque o
    Windows o chama pelo nome do controle emulado.
    """
    windows_name = str(entry.get("name") or "").strip()
    ids = extract_vid_pid(entry.get("id"))
    vid, pid = ids["vid"], ids["pid"]
    maker = vendor(vid)
    xinput = looks_xinput(windows_name, entry.get("class"), entry.get("id"))
    emulated = bool(kind == "controller" and xinput and vid and vid != "045E")
    low = windows_name.casefold()
    generic = not windows_name or any(g in low for g in _GENERIC_NAMES)
    label = KIND_LABEL.get(kind, kind)

    display = windows_name or label.capitalize()
    note = ""
    if maker and maker["kind"] == "marca":
        if emulated:
            display = f"{maker['name']} · {label} em modo XInput"
            note = (f"O Windows o chama de “{windows_name}” porque o {label} se apresenta como um controle "
                    f"de Xbox 360 (modo XInput) para os jogos o reconhecerem. Quem fabricou é a "
                    f"{maker['name']}: é o que diz o código USB dele (VID {vid}).")
        elif generic:
            display = f"{maker['name']} · {label}"
            note = f"Fabricante pelo código USB (VID {vid}); o Windows só informa um nome genérico."
    elif maker and maker["kind"] == "chip":
        note = (f"O código USB (VID {vid}) é do fabricante do chip, {maker['name']}, usado por várias "
                f"marcas. A marca do produto não chega ao Windows.")
    elif emulated:
        display = f"{label.capitalize()} em modo XInput"
        note = (f"O Windows o chama de “{windows_name}” porque ele se apresenta como um controle de "
                f"Xbox 360 (modo XInput). O código USB (VID {vid}) não está na tabela de fabricantes do AZOR.")

    return {
        "display_name": display,
        "windows_name": windows_name,
        "vid": vid,
        "pid": pid,
        "vendor": maker["name"] if maker else None,
        "vendor_kind": maker["kind"] if maker else None,
        "xinput": xinput,
        "emulated": emulated,
        "note": note,
        # So o desenho usa isto: controles da Sony tem os dois analogicos
        # lado a lado; o resto do mercado segue o layout assimetrico.
        "layout": "symmetric" if vid == "054C" else "asymmetric",
    }
