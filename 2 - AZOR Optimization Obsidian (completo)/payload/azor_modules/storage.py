"""Sistema de arquivos: menos escrita de metadado.

Nada aqui apaga arquivo -- isso e o modulo de manutencao. Aqui sao dois ajustes
de comportamento do NTFS, ambos lidos e escritos pelo proprio fsutil do Windows,
ambos confirmados por releitura.

O segundo item nem e um tweak: e conserto. Programa "otimizador" desligando TRIM
e uma das causas mais comuns de SSD que fica lento com o tempo, e o AZOR religa
quando encontra assim.
"""
from __future__ import annotations

from .base import OptimizationTask, internal_disk_media

MODULE = {
    "id": "storage",
    "label": "Sistema de arquivos",
    "description": "Comportamento do NTFS, lido e gravado pelo fsutil e confirmado por releitura. O reparo de TRIM mudou para o módulo Reparo.",
    "automatic": True,
}

PREFETCH_PARAMS = r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters"

KEYS = {
    "prefetcher_ssd_off": [("HKLM", PREFETCH_PARAMS, "EnablePrefetcher")],
}


def tasks():
    # ---------------- Ultimo acesso ----------------
    def last_access_compat(core, ctx):
        if not core.is_admin():
            return False, "Alterar o comportamento do NTFS exige o AZOR aberto como administrador."
        state = core.ntfs_last_access_state()
        value = state.get("value")
        if value is None:
            return False, "O fsutil não respondeu o estado de último acesso; preservado."
        if state.get("disabled"):
            return False, f"A atualização de último acesso já está desligada (valor {value})."
        return True, (f"Atualização de último acesso ligada (valor {value}). Cada leitura de arquivo "
                      "gera também uma escrita de metadado.")

    def last_access_apply(core, ctx):
        # 1 = desligado por decisao do usuario (nao "gerenciado pelo sistema"),
        # que e o unico valor que o Windows nao volta a mudar sozinho.
        return core.set_ntfs_last_access_verified(1)

    def last_access_verify(core, ctx):
        state = core.ntfs_last_access_state()
        ok = bool(state.get("disabled"))
        return ok, (f"fsutil relido: último acesso desligado (valor {state.get('value')})." if ok
                    else f"O fsutil ainda reporta valor {state.get('value')}.")

    def last_access_revert(core, ctx):
        saved = core.baseline_state().get("ntfs_last_access") or {}
        original = saved.get("value")
        if not isinstance(original, int):
            return False, ("O baseline não registrou o comportamento anterior de último acesso; "
                           "nada foi alterado por suposição.")
        return core.set_ntfs_last_access_verified(original)

    # ---------------- nome curto 8.3 ----------------
    def short_name_compat(core, ctx):
        if not core.is_admin():
            return False, "Alterar o comportamento do NTFS exige o AZOR aberto como administrador."
        state = core.ntfs_8dot3_state()
        value = state.get("value")
        if value is None:
            return False, "O fsutil não respondeu o estado de nome curto 8.3; preservado."
        if state.get("disabled_everywhere"):
            return False, "A criação de nome curto 8.3 já está desligada em todos os volumes."
        return True, (f"Criação de nome curto 8.3 no modo {value}. Cada arquivo novo em pasta "
                      "grande custa uma busca extra de nome.")

    def short_name_apply(core, ctx):
        return core.set_ntfs_8dot3_verified(1)

    def short_name_verify(core, ctx):
        state = core.ntfs_8dot3_state()
        ok = bool(state.get("disabled_everywhere"))
        return ok, (f"fsutil relido: nome curto 8.3 desligado (valor {state.get('value')})." if ok
                    else f"O fsutil ainda reporta valor {state.get('value')}.")

    def short_name_revert(core, ctx):
        saved = core.baseline_state().get("ntfs_8dot3") or {}
        original = saved.get("value")
        if not isinstance(original, int):
            return False, ("O baseline não registrou o comportamento anterior de nome curto 8.3; "
                           "nada foi alterado por suposição.")
        return core.set_ntfs_8dot3_verified(original)

    # ---------------- MSI na controladora de armazenamento ----------------
    def storage_msi_compat(core, ctx):
        if not core.is_admin():
            return False, "Este ajuste grava no Enum do dispositivo e exige o AZOR como administrador."
        devices = core.pci_instances("SCSIAdapter", "pci:storage")
        if not devices:
            return False, "Nenhuma controladora de armazenamento no barramento PCI foi encontrada."
        state = core.device_msi_state(devices)
        if state.get("all_on"):
            return False, "A controladora de armazenamento deste PC já usa interrupção por mensagem."
        return True, "Controladora(s): " + ", ".join(d["name"] for d in devices) + "."

    def storage_msi_apply(core, ctx):
        return core.set_device_msi_verified(core.pci_instances("SCSIAdapter", "pci:storage"), True)

    def storage_msi_verify(core, ctx):
        state = core.device_msi_state(core.pci_instances("SCSIAdapter", "pci:storage"))
        ok = bool(state.get("all_on"))
        return ok, ("MSISupported relido como 1 na controladora de armazenamento." if ok
                    else "Nem toda controladora confirmou MSISupported=1.")

    def storage_msi_revert(core, ctx):
        keys = [("HKLM", core._msi_path(d["instance"]), "MSISupported")
                for d in core.pci_instances("SCSIAdapter", "pci:storage")]
        if not keys:
            return False, "Nenhuma controladora para reverter."
        return core.revert_registry_from_baseline(keys, "storage_msi")

    # ---------------- Prefetcher ----------------
    def prefetch_compat(core, ctx):
        entry = core.reg_read("HKLM", PREFETCH_PARAMS, "EnablePrefetcher")
        if entry.get("exists") and entry.get("value") == 0:
            return False, "O Prefetcher já está desligado."
        media = internal_disk_media(core)
        if not media:
            return False, "O tipo de mídia dos discos não pôde ser confirmado; o Prefetcher fica intocado."
        mecanicos = [m for m in media if m != "SSD"]
        if mecanicos:
            return False, ("Há disco não-sólido neste PC. Em HD mecânico o Prefetcher reduz de "
                           "verdade o tempo de carregamento, então ele fica preservado.")
        if not core.is_admin():
            return False, "Somente SSD neste PC, mas alterar o Prefetcher exige o AZOR como administrador."
        return True, "Somente armazenamento sólido: o pré-carregamento pode ser testado desligado."

    def prefetch_apply(core, ctx):
        return core.write_registry_values_verified(
            [{"root": "HKLM", "path": PREFETCH_PARAMS, "name": "EnablePrefetcher", "value": 0}])

    def prefetch_verify(core, ctx):
        entry = core.reg_read("HKLM", PREFETCH_PARAMS, "EnablePrefetcher")
        ok = entry.get("exists") and entry.get("value") == 0
        return ok, ("Prefetcher relido como desligado." if ok
                    else f"O Windows reporta EnablePrefetcher = {entry.get('value')}.")

    def prefetch_revert(core, ctx):
        return core.revert_registry_from_baseline(KEYS["prefetcher_ssd_off"], "prefetcher_ssd_off")

    return [
        OptimizationTask(
            "prefetcher_ssd_off", "Testar o PC sem o pré-carregamento (somente SSD)", MODULE["id"],
            "Disco / Pré-carregamento", ("competitive",), risk="experimental", automatic=False,
            restart=True,
            description="O Prefetcher lê antes o que o Windows acha que você vai abrir. Em disco "
                        "mecânico isso vale muito; em SSD, o ganho encolhe e sobra o custo de I/O em "
                        "segundo plano. Como o resultado varia por máquina, este item é um teste A/B "
                        "seu — aplique, use o PC dois dias e reverta se não sentir diferença.",
            apply=prefetch_apply, verify=prefetch_verify, revert=prefetch_revert,
            compatible=prefetch_compat, tags=("ssd", "disk", "ab-test", "restart"),
            source="EnablePrefetcher em HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager"
                   "\\Memory Management\\PrefetchParameters — referência de registro do Windows. "
                   "3 = padrão (aplicativos e boot), 0 = desligado.",
            trade_off="A primeira abertura de programas grandes pode ficar mais lenta. O AZOR não "
                      "promete ganho aqui: em boa parte dos SSDs modernos a diferença não aparece na "
                      "medição. Exige reiniciar.",
            metric="I/O de disco em repouso",
            relations=[{"kind": "combina", "id": "sysmain_ssd_off",
                        "note": "São as duas metades do mesmo mecanismo: o serviço que decide o que "
                                "pré-carregar e a chave que liga o pré-carregamento. Testar um sem o "
                                "outro dá resultado pela metade."}],
        ),
        OptimizationTask(
            "storage_msi", "Interrupção por mensagem (MSI) na controladora do SSD", MODULE["id"],
            "Disco / Interrupção", ("competitive",), risk="high", restart=True, automatic=False,
            description="Faz a controladora NVMe/AHCI sinalizar interrupções por mensagem em vez de "
                        "compartilhar linha IRQ. Reduz latência de DPC do armazenamento, que é o que "
                        "aparece como engasgo ao carregar textura no meio da partida.",
            apply=storage_msi_apply, verify=storage_msi_verify, revert=storage_msi_revert,
            compatible=storage_msi_compat, tags=("ssd", "dpc", "manual", "restart"),
            source="MSI/MSI-X em PCI Express — chave MSISupported em ...\\Enum\\PCI\\<instância>"
                   "\\Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties.",
            trade_off="Mesmo risco do MSI na GPU, com um agravante: se a controladora do disco não "
                      "inicializar, o PC não sobe. A reversão existe e funciona, mas teria de ser feita "
                      "pelo Modo de Segurança. Alto risco, clique explícito, e só com ponto de "
                      "restauração criado antes.",
            metric="Latência de DPC do driver de armazenamento",
        ),
        OptimizationTask(
            "ntfs_short_names_off", "Parar de criar nomes curtos 8.3", MODULE["id"],
            "Disco / NTFS", ("competitive", "campanha", "stream"), risk="low",
            description="Para cada arquivo criado, o NTFS também monta um nome no formato antigo "
                        "PROGRA~1. Em pasta com dezenas de milhares de arquivos — cache de shader, "
                        "pasta de compilação — esse trabalho extra aparece. Não é um ajuste de FPS: "
                        "o ganho está em criação de arquivo, não em quadro renderizado.",
            apply=short_name_apply, verify=short_name_verify, revert=short_name_revert,
            compatible=short_name_compat, tags=("ntfs", "disk"),
            source="fsutil behavior set disable8dot3 — referência do fsutil, Microsoft Learn. "
                   "0 = todos os volumes, 1 = nenhum, 2 = por volume (padrão do Windows), "
                   "3 = todos menos o do sistema.",
            trade_off="Programas de 16 bits e instaladores muito antigos que dependem de caminho "
                      "curto podem falhar. Os nomes curtos já existentes continuam funcionando; só "
                      "os novos deixam de ser criados.",
            metric="Tempo de criação de arquivo em diretório grande",
        ),
        OptimizationTask(
            "ntfs_last_access_off", "Parar de gravar a hora do último acesso", MODULE["id"],
            "Disco / NTFS", ("competitive", "campanha", "stream"), risk="low",
            description="Cada leitura de arquivo também escreve um metadado com a hora do acesso. "
                        "Desligar tira uma escrita de disco de todo carregamento de textura e shader.",
            apply=last_access_apply, verify=last_access_verify, revert=last_access_revert,
            compatible=last_access_compat, tags=("ntfs", "disk"),
            source="fsutil behavior set disablelastaccess - referência do fsutil, Microsoft Learn. "
                   "0/2 = ligado, 1/3 = desligado; 2 e 3 são as variantes 'gerenciadas pelo sistema'.",
            trade_off="Programas de backup incremental e de limpeza que decidem por 'último acesso' "
                      "perdem esse critério e passam a usar a data de modificação. Nenhum jogo usa.",
            metric="Escritas de disco em repouso e durante carregamento",
        ),
    ]
