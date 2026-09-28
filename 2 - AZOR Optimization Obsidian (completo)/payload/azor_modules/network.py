"""Rede: latencia do adaptador ativo, e um reparo do que outros 'otimizadores' quebram.

O modulo continua sem prometer ping menor. Distancia ate o servidor e roteamento
nao mudam com registro, e qualquer app que diga o contrario esta vendendo ilusao.
O que da para fazer -- e o que esta aqui -- e tirar atraso que o proprio PC
adiciona depois que o pacote ja chegou: agrupamento de ACK, moderacao de
interrupcao, economia de energia da placa.

Tudo age apenas no adaptador que carrega a rota padrao. Mexer em placa que nao
esta em uso e barulho no relatorio.
"""
from __future__ import annotations

from .base import OptimizationTask

MODULE = {
    "id": "network",
    "label": "Rede",
    "description": "Latência do adaptador em uso: ACK sem atraso, sem moderação de interrupção, sem economia de energia. Sem promessa de ping magico.",
    "automatic": True,
}

# As chaves de Nagle vivem sob o GUID da interface, que so existe nesta maquina.
# Elas entram no baseline por `azor_core._dynamic_registry_keys()`, que enumera
# todas as interfaces TCP/IP registradas -- por isso KEYS aqui fica vazio sem que
# isso signifique "sem cobertura".
KEYS: dict = {}


def _adapter(core, ctx):
    return core.active_network_adapter()


def _require_adapter(core, ctx):
    adapter = _adapter(core, ctx)
    if not adapter.get("alias"):
        return False, "Nenhum adaptador com rota padrão foi encontrado; nada foi alterado."
    return True, f"Adaptador ativo: {adapter['alias']} ({adapter.get('description') or 'sem descrição'})."


def _require_adapter_admin(core, ctx):
    ok, detail = _require_adapter(core, ctx)
    if not ok:
        return ok, detail
    if not core.is_admin():
        return False, "Este ajuste grava em HKLM e exige o AZOR aberto como administrador."
    return True, detail


def _require_property(keyword: str, label: str):
    def check(core, ctx):
        ok, detail = _require_adapter(core, ctx)
        if not ok:
            return ok, detail
        adapter = _adapter(core, ctx)
        if core.nic_property_value(adapter["alias"], keyword) is None:
            return False, (f"O driver de {adapter['alias']} não expoe {label}. Nem toda placa expoe, e o "
                           "AZOR não inventa a propriedade: o item fica preservado.")
        return True, f"{label} disponível em {adapter['alias']}."
    return check


def _baseline(core, section):
    return core.baseline_state().get(section)


def tasks():
    # ---------------- Nagle ----------------
    def nagle_apply(core, ctx):
        adapter = _adapter(core, ctx)
        values = core.nagle_registry_values(adapter.get("guid_braced") or "")
        ok, detail = core.write_registry_values_verified(values)
        return ok, (detail + " Vale para o adaptador em uso; o efeito aparece na próxima conexão."
                    if ok else detail)

    def nagle_verify(core, ctx):
        adapter = _adapter(core, ctx)
        return core.verify_registry_values(core.nagle_registry_values(adapter.get("guid_braced") or ""))

    def nagle_revert(core, ctx):
        adapter = _adapter(core, ctx)
        guid = adapter.get("guid_braced") or ""
        keys = [(v["root"], v["path"], v["name"]) for v in core.nagle_registry_values(guid)]
        return core.revert_registry_from_baseline(keys, "nagle_off")

    # ---------------- Moderacao de interrupcao ----------------
    def moderation_apply(core, ctx):
        adapter = _adapter(core, ctx)
        core.baseline_backfill(f"nic_advanced:{adapter['alias']}",
                               core.nic_advanced_properties(adapter["alias"]))
        return core.set_nic_property_verified(adapter["alias"], "*InterruptModeration", "0")

    def moderation_verify(core, ctx):
        adapter = _adapter(core, ctx)
        value = core.nic_property_value(adapter["alias"], "*InterruptModeration")
        ok = str(value) == "0"
        return ok, ("Moderação de interrupção relida como desligada no driver." if ok
                    else f"O driver reporta moderação de interrupção = {value}.")

    def moderation_revert(core, ctx):
        adapter = _adapter(core, ctx)
        saved = _baseline(core, f"nic_advanced:{adapter['alias']}") or []
        original = next((r.get("value") for r in saved
                         if str(r.get("keyword", "")).casefold() == "*interruptmoderation"), None)
        if original is None:
            return False, ("O baseline não registrou o valor anterior de moderação de interrupção "
                           "deste adaptador; nada foi alterado por suposição.")
        return core.set_nic_property_verified(adapter["alias"], "*InterruptModeration", str(original))

    # ---------------- Economia de energia da placa ----------------
    def power_apply(core, ctx):
        adapter = _adapter(core, ctx)
        core.baseline_backfill(f"nic_power:{adapter['alias']}",
                               core.nic_power_management(adapter["alias"]))
        return core.set_nic_power_management_verified(adapter["alias"], False)

    def _power_state(core, alias):
        """Estado por cmdlet quando o driver publica; senao, pelo PnPCapabilities
        -- que e o interruptor real da aba Gerenciamento de Energia."""
        state = core.nic_power_management(alias)
        if state is not None:
            return state, "cmdlet"
        return core.nic_pnp_power_managed(alias), "PnPCapabilities"

    def power_verify(core, ctx):
        adapter = _adapter(core, ctx)
        state, source = _power_state(core, adapter["alias"])
        ok = state is False
        return ok, (f"O Windows não pode desligar a placa de rede para economizar; relido via {source}."
                    if ok else f"Estado lido via {source}: permissao de economia = {state}.")

    def power_revert(core, ctx):
        adapter = _adapter(core, ctx)
        if core.nic_power_management(adapter["alias"]) is None:
            key = core.nic_driver_key(adapter["alias"])
            if not key:
                return False, "A chave de driver deste adaptador não pode ser localizada."
            return core.revert_registry_from_baseline([("HKLM", key, "PnPCapabilities")], "nic_power_saving_off")
        original = _baseline(core, f"nic_power:{adapter['alias']}")
        if not isinstance(original, bool):
            return False, "O baseline não registrou o estado anterior de energia deste adaptador."
        return core.set_nic_power_management_verified(adapter["alias"], original)

    def power_compat(core, ctx):
        ok, detail = _require_adapter(core, ctx)
        if not ok:
            return ok, detail
        adapter = _adapter(core, ctx)
        state, source = _power_state(core, adapter["alias"])
        if state is None:
            return False, f"{adapter['alias']} não expoe gerenciamento de energia por nenhum caminho; preservado."
        if state is False:
            return False, f"O Windows já está impedido de desligar {adapter['alias']} ({source})."
        if source == "PnPCapabilities" and not core.is_admin():
            return False, ("Este driver só aceita a mudanca pela chave do dispositivo, o que exige o "
                           "AZOR aberto como administrador.")
        return True, detail + f" Caminho disponível: {source}."

    # ---------------- Ethernet verde / EEE ----------------
    # Todas sao formas de economizar energia degradando o link: EEE negocia pausa,
    # Green Ethernet reduz potencia, Gigabit Lite e Auto Disable Gigabit derrubam a
    # velocidade negociada. As tres familias produzem o mesmo sintoma: um pico
    # isolado de latencia quando o link precisa voltar ao normal.
    GREEN = ("*EEE", "EnableGreenEthernet", "AdvancedEEE", "PowerSavingMode",
             "GigaLite", "AutoDisableGigabit", "EnableSavePowerNow")

    def eee_present(core, ctx):
        ok, detail = _require_adapter(core, ctx)
        if not ok:
            return ok, detail
        adapter = _adapter(core, ctx)
        found = [k for k in GREEN if core.nic_property_value(adapter["alias"], k) is not None]
        if not found:
            return False, (f"O driver de {adapter['alias']} não expoe Energy Efficient Ethernet; "
                           "nada a desligar.")
        return True, f"Propriedade(s) de Ethernet verde encontradas: {', '.join(found)}."

    def eee_apply(core, ctx):
        adapter = _adapter(core, ctx)
        core.baseline_backfill(f"nic_advanced:{adapter['alias']}",
                               core.nic_advanced_properties(adapter["alias"]))
        done, failed = [], []
        for keyword in GREEN:
            if core.nic_property_value(adapter["alias"], keyword) is None:
                continue
            ok, detail = core.set_nic_property_verified(adapter["alias"], keyword, "0")
            (done if ok else failed).append(f"{keyword}: {detail}")
        if not done and not failed:
            return False, "Nenhuma propriedade de Ethernet verde estava exposta."
        return (not failed), ("; ".join(done) if not failed else "Não confirmado: " + "; ".join(failed))

    def eee_verify(core, ctx):
        adapter = _adapter(core, ctx)
        wrong = [k for k in GREEN
                 if core.nic_property_value(adapter["alias"], k) not in (None, "0")]
        ok = not wrong
        return ok, ("Ethernet verde relida como desligada no driver." if ok
                    else "Ainda ligado: " + ", ".join(wrong))

    def eee_revert(core, ctx):
        adapter = _adapter(core, ctx)
        saved = _baseline(core, f"nic_advanced:{adapter['alias']}") or []
        by_keyword = {str(r.get("keyword", "")).casefold(): r.get("value") for r in saved}
        done, unknown = [], []
        for keyword in GREEN:
            if core.nic_property_value(adapter["alias"], keyword) is None:
                continue
            original = by_keyword.get(keyword.casefold())
            if original is None:
                unknown.append(keyword)
                continue
            ok, _ = core.set_nic_property_verified(adapter["alias"], keyword, str(original))
            if ok:
                done.append(keyword)
        if unknown and not done:
            return False, "Sem baseline para: " + ", ".join(unknown) + ". Nada foi alterado por suposição."
        return bool(done), f"{len(done)} propriedade(s) devolvida(s) ao valor anterior ao AZOR."

    # ---------------- Receive Side Scaling ----------------
    def rss_compat(core, ctx):
        ok, detail = _require_adapter(core, ctx)
        if not ok:
            return ok, detail
        adapter = _adapter(core, ctx)
        state = core.nic_rss_state(adapter["alias"])
        if state is None:
            return False, f"O driver de {adapter['alias']} não expõe RSS; preservado."
        if state:
            return False, f"RSS já está ligado em {adapter['alias']}."
        if not core.is_admin():
            return False, (f"RSS está desligado em {adapter['alias']}. Ligá-lo exige o AZOR aberto "
                           "como administrador.")
        return True, f"RSS desligado em {adapter['alias']}: as interrupções de rede estão todas num núcleo só."

    def rss_apply(core, ctx):
        return core.set_nic_rss_verified(_adapter(core, ctx)["alias"], True)

    def rss_verify(core, ctx):
        state = core.nic_rss_state(_adapter(core, ctx)["alias"])
        ok = state is True
        return ok, ("RSS relido como ligado no driver." if ok else f"O driver reporta RSS = {state}.")

    def rss_revert(core, ctx):
        adapter = _adapter(core, ctx)
        original = _baseline(core, f"nic_rss:{adapter['alias']}")
        if not isinstance(original, bool):
            return False, "O baseline não registrou o estado anterior de RSS deste adaptador."
        return core.set_nic_rss_verified(adapter["alias"], original)

    return [
        OptimizationTask(
            "nic_rss_on", "Distribuir as interrupções de rede entre os núcleos",
            MODULE["id"], "Rede / CPU", ("competitive", "stream"), risk="low",
            description="Sem RSS, todo o processamento de rede cai num único núcleo — justamente o "
                        "que fica saturado quando o jogo também está usando. Com RSS, o trabalho se "
                        "espalha e para de competir no mesmo lugar.",
            apply=rss_apply, verify=rss_verify, revert=rss_revert, compatible=rss_compat,
            tags=("nic", "cpu", "latency"),
            source="Receive Side Scaling (RSS) — Enable-NetAdapterRss / Get-NetAdapterRss, módulo "
                   "NetAdapter do PowerShell. É recurso padrão do NDIS documentado pela Microsoft.",
            trade_off="Praticamente nenhum em PC de quatro núcleos ou mais. Em processador de dois "
                      "núcleos o ganho é pequeno, porque há pouco para onde espalhar.",
            metric="Uso de CPU do núcleo 0 sob tráfego e jitter de rede",
        ),
        OptimizationTask(
            "nagle_off", "Desligar o agrupamento de ACK (Nagle)", MODULE["id"], "Rede / Latência",
            ("competitive", "stream"), risk="medium",
            description="Grava TcpAckFrequency=1, TCPNoDelay=1 e TcpDelAckTicks=0 na interface que "
                        "carrega a rota padrão. O Windows deixa de segurar a confirmação esperando "
                        "juntar pacote, que é atraso puro para o trânsito pequeno e constante de um jogo.",
            apply=nagle_apply, verify=nagle_verify, revert=nagle_revert, compatible=_require_adapter_admin,
            tags=("tcp", "latency"),
            source="Parâmetros TCP/IP por interface (HKLM\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\"
                   "Parameters\\Interfaces\\{GUID}) - referência de registro TCP/IP da Microsoft; "
                   "TcpAckFrequency e o ajuste descrito no KB 328890.",
            trade_off="Mais pacotes pequenos na rede: em conexão muito limitada ou compartilhada, a "
                      "sobrecarga de cabeçalho pode custar um pouco de banda. Não altera roteamento nem "
                      "distância até o servidor - nenhum ajuste faz isso.",
            metric="Variação de latência em jogo (jitter)",
        ),
        OptimizationTask(
            "nic_interrupt_moderation_off", "Desligar a moderação de interrupção da placa de rede",
            MODULE["id"], "Rede / Latência", ("competitive",), risk="medium",
            description="A placa agrupa interrupções para poupar CPU, e esse agrupamento é atraso. "
                        "Desligado, cada pacote chega ao sistema assim que chega no fio.",
            apply=moderation_apply, verify=moderation_verify, revert=moderation_revert,
            compatible=_require_property("*InterruptModeration", "moderação de interrupção"),
            tags=("nic", "latency"),
            source="Propriedade avancada padronizada *InterruptModeration, definida pela Microsoft para "
                   "drivers NDIS; lida e escrita por Get/Set-NetAdapterAdvancedProperty.",
            trade_off="O uso de CPU do adaptador sobe sob tráfego alto, porque cada pacote gera "
                      "interrupção. Em máquina de 4 núcleos com download pesado ao mesmo tempo, isso é "
                      "perceptível.",
            metric="Jitter de rede e DPC do driver de rede",
        ),
        OptimizationTask(
            "nic_power_saving_off", "Impedir o Windows de desligar a placa de rede",
            MODULE["id"], "Rede / Energia", ("safe", "competitive", "campanha", "stream"), risk="low",
            description="Tira a permissao de 'o computador pode desligar este dispositivo para economizar "
                        "energia'. É a causa clássica de queda de conexão de alguns segundos no meio da "
                        "partida em placa Wi-Fi.",
            apply=power_apply, verify=power_verify, revert=power_revert, compatible=power_compat,
            tags=("nic", "power", "stability"),
            source="Set-NetAdapterPowerManagement -AllowComputerToTurnOffDevice (módulo NetAdapter do "
                   "PowerShell). Quando o driver não pública essa classe, o AZOR usa PnPCapabilities=24 "
                   "na chave de classe do adaptador, que é exatamenté o valor que a aba Gerenciamento "
                   "de Energia do Gerenciador de Dispositivos grava.",
            trade_off="Consumo levemente maior em repouso. Em notebook longe da tomada, alguns "
                      "miliwatts a mais.",
            metric="Quedas de conexão por sessão",
        ),
        OptimizationTask(
            "nic_green_ethernet_off", "Desligar a economia de energia do link Ethernet",
            MODULE["id"], "Rede / Energia", ("competitive", "stream"), risk="low",
            description="Energy Efficient Ethernet, Green Ethernet, Gigabit Lite e Auto Disable Gigabit "
                        "rebaixam o link quando ele fica ocioso e levam alguns microssegundos para "
                        "voltar. Em jogo, esse retorno aparece como pico isolado de latência. O AZOR "
                        "desliga apenas as que o seu driver realmente expoe.",
            apply=eee_apply, verify=eee_verify, revert=eee_revert, compatible=eee_present,
            tags=("nic", "latency"),
            source="IEEE 802.3az (Energy Efficient Ethernet) e propriedades equivalentes dos fabricantes "
                   "(*EEE, EnableGreenEthernet, AdvancedEEE, PowerSavingMode, GigaLite, "
                   "AutoDisableGigabit), lidas e escritas por Get/Set-NetAdapterAdvancedProperty.",
            trade_off="Alguns miliwatts a mais no adaptador e no switch. Sem efeito em Wi-Fi.",
            metric="Picos isolados de ping",
        ),
    ]
