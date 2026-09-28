from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Tuple

# The four profiles the engine understands. "campanha" is the story/single-player
# profile: it prioritises stability and preserves visual fidelity and capture,
# so it is deliberately NOT a superset of "competitive".
# Os tres niveis principais sao SEGURO, COMPETITIVO e AZOR ULTRA. CAMPANHA e
# JOGO + LIVE continuam existindo: nao sao niveis de intensidade, sao perfis de
# USO (jogo single-player, jogo transmitindo) e ninguem perdeu funcao com a
# chegada do Ultra.
#
# O que o AZOR ULTRA e - e o que ele NAO e:
#
# Ele aplica exatamente o mesmo catalogo do COMPETITIVO. Nao ha um so tweak a
# mais, porque o competitivo ja aplica os 70 de 70 quando a maquina permite -
# nao sobrou nada para um nivel acima adicionar. Inventar um tweak so para o
# Ultra parecer maior seria placebo.
#
# A diferenca do Ultra e real e esta nos MOTORES DE SESSAO, que o competitivo
# deixa no padrao conservador:
#
#   competitivo : timer de latencia so durante o jogo, motores no padrao
#   ultra       : timer sempre ativo, motor de prioridade e de memoria ligados,
#                 plano de energia reforcado o tempo todo
#
# E uma diferenca de POSTURA, nao de quantidade - e a tela diz isso com todas as
# letras, para ninguem comprar Ultra achando que sao mais ajustes.
PROFILES: Tuple[str, ...] = ("safe", "competitive", "ultra", "campanha", "stream", "maximo", "agressivo")

PROFILE_LABELS = {
    "safe": "SEGURO",
    "competitive": "COMPETITIVO",
    "ultra": "AZOR ULTRA",
    "campanha": "CAMPANHA",
    "stream": "JOGO + LIVE",
    # Modos da tela inicial. Nao criam catalogo proprio: herdam o do competitivo
    # e mudam so quais itens entram no lote de um clique (policy.MAXIMO/AGRESSIVO).
    "maximo": "MÁXIMO",
    "agressivo": "AGRESSIVO",
}

# Perfis cujo catalogo e o do competitivo.
COMPETITIVE_FAMILY = frozenset(("competitive", "ultra", "maximo", "agressivo"))


ApplyFn = Callable[[Any, Dict[str, Any]], Tuple[bool, str]]
VerifyFn = Callable[[Any, Dict[str, Any]], Tuple[bool, str]]
RevertFn = Callable[[Any, Dict[str, Any]], Tuple[bool, str]]
CompatFn = Callable[[Any, Dict[str, Any]], Tuple[bool, str]]
AnalyzeFn = Callable[[Any, Dict[str, Any]], Dict[str, Any]]

# Every risk level the UI is allowed to render. "experimental" exists so a tweak
# whose result varies per machine can be offered as a measured A/B instead of
# being sold as an improvement.
RISK_LEVELS = ("low", "medium", "high", "experimental")
RISK_LABELS = {
    "low": "Seguro",
    "medium": "Moderado",
    "high": "Avançado",
    "experimental": "Experimental",
}


@dataclass(frozen=True)
class OptimizationTask:
    id: str
    name: str
    module: str
    category: str
    profiles: Sequence[str]
    risk: str = "low"
    reversible: bool = True
    restart: bool = False
    automatic: bool = True
    description: str = ""
    apply: Optional[ApplyFn] = None
    verify: Optional[VerifyFn] = None
    # Individual undo. A task without it must say so instead of pretending: the UI
    # reads `reversible` straight from whether this is present.
    revert: Optional[RevertFn] = None
    compatible: Optional[CompatFn] = None
    analyze: Optional[AnalyzeFn] = None
    tags: Sequence[str] = field(default_factory=tuple)
    # Documentation that justifies the tweak. No source, no tweak.
    source: str = ""
    # The honest cost of applying it: security, battery, temperature, compatibility.
    trade_off: str = ""
    # Which measured number this is supposed to move. "" means it moves none, and
    # the tweak is then a preference, not a performance claim.
    metric: str = ""
    # Como este tweak se relaciona com outros do catalogo. Existe porque um
    # arsenal de sessenta itens tem interacoes reais, e ate aqui elas viviam so na
    # cabeca de quem escreveu: "o timer de sessao quase nao alcanca o jogo sem o
    # timer global" e um fato que o usuario precisava adivinhar.
    # Cada entrada: {"kind": amplia|redundante|cuidado|combina, "id": ..., "note": ...}
    relations: Sequence[Dict[str, str]] = field(default_factory=tuple)
    registry_keys: Sequence[Tuple[str, str, str]] = field(default_factory=tuple)
    audit_reason: str = ""
    classification: str = "SITUACIONAL"
    disposition: str = "MELHORAR"
    requires_admin: bool = False
    min_windows_build: int = 19041
    power_changes: Sequence[Tuple[str, str, str, str, int]] = field(default_factory=tuple)

    def supports_profile(self, profile: str) -> bool:
        # O Ultra herda o catalogo do competitivo aqui, num lugar so, em vez de
        # somar "ultra" na declaracao das 70 tarefas - onde alguem esqueceria uma
        # e o nivel mais alto silenciosamente aplicaria menos que o de baixo.
        wanted = "competitive" if str(profile) in COMPETITIVE_FAMILY else str(profile)
        return wanted in set(self.profiles)

    def can_revert(self) -> bool:
        return self.revert is not None

    def risk_label(self) -> str:
        return RISK_LABELS.get(str(self.risk), str(self.risk))


def normalize_result(value: Any) -> Tuple[bool, str]:
    if isinstance(value, tuple) and len(value) >= 2:
        ok = value[0]
        return ok is True, str(value[1]) if isinstance(ok, bool) else "Resultado inválido: a ação não retornou confirmação booleana."
    if isinstance(value, dict):
        return value.get("ok") is True, str(value.get("detail", ""))
    if isinstance(value, bool):
        return value, ""
    return False, "Resultado inválido: confirmação explícita não recebida."



def internal_disk_media(core) -> list:
    """Tipo de mídia (SSD, HDD, UNSPECIFIED...) de cada disco interno.

    Disco USB, SD e MMC ficam de fora: um HD externo esquecido na porta não pode
    decidir a configuração do PC. Lista vazia significa "não foi possível
    confirmar", e quem chama deve preservar o padrão do Windows nesse caso.
    A chave é "Media", sem acento, como o storage_health() devolve.
    """
    health = core.storage_health() or {}
    internal = [d for d in (health.get("disks") or [])
                if isinstance(d, dict) and str(d.get("Bus") or "").upper() not in ("USB", "SD", "MMC")]
    return [str(d.get("Media") or "").strip().upper() for d in internal]


def only_solid_state(core) -> bool:
    media = internal_disk_media(core)
    return bool(media) and all(m == "SSD" for m in media)
