"""Fabrica de tweaks de registro declarativos.

Antes, cada tweak de registro escrevia tres funcoes a mao (aplicar, verificar,
reverter) e a lista de chaves aparecia numa quarta. Quatro copias da mesma
informacao, e a reversao quebrava quando uma delas ficava para tras -- foi
exatamente o que aconteceu com transparencia, widgets e sugestoes, que anunciavam
`reversible: true` sem chave nenhuma no baseline.

Aqui a declaracao e uma so:

    RegSpec(id="...", values=[V("HKCU", r"...", "Nome", 1)], ...)

e dela saem, sem chance de divergir:
  - `apply`   grava e RELE cada valor;
  - `verify`  confere a releitura;
  - `revert`  devolve o valor anterior ao AZOR, vindo do baseline;
  - `KEYS`    a lista que o baseline captura.

Um tweak declarado assim nao consegue mentir sobre ser reversivel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .base import OptimizationTask


@dataclass(frozen=True)
class V:
    """Um valor de registro que um tweak grava."""
    root: str
    path: str
    name: str
    value: Any

    def as_dict(self) -> Dict[str, Any]:
        return {"root": self.root, "path": self.path, "name": self.name, "value": self.value}

    def key(self) -> Tuple[str, str, str]:
        return (self.root, self.path, self.name)


@dataclass(frozen=True)
class RegSpec:
    id: str
    name: str
    category: str
    profiles: Sequence[str]
    values: Sequence[V]
    description: str
    source: str
    trade_off: str
    metric: str = ""
    risk: str = "low"
    restart: bool = False
    automatic: bool = True
    tags: Sequence[str] = field(default_factory=tuple)
    compatible: Optional[Callable[[Any, Dict[str, Any]], Tuple[bool, str]]] = None
    # Alguns tweaks precisam de valores diferentes por perfil (o mesmo ajuste que
    # ajuda o competitivo pode estrangular o encoder de quem faz live). Quando
    # existe, esta funcao decide os valores a partir do contexto ja resolvido.
    values_for: Optional[Callable[[Dict[str, Any]], Sequence[V]]] = None
    # Texto extra mostrado depois de aplicar, quando o efeito so vale no proximo boot.
    restart_note: str = ""
    relations: Sequence[Dict[str, str]] = field(default_factory=tuple)

    def resolve(self, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
        values = self.values_for(ctx) if self.values_for else self.values
        return [v.as_dict() for v in values]

    def keys(self) -> List[Tuple[str, str, str]]:
        """Toda chave que este tweak pode escrever, incluindo variantes por perfil.

        As variantes entram tambem: o baseline precisa cobrir o que QUALQUER
        perfil grava, nao so o que o perfil de hoje grava.
        """
        seen, out = set(), []
        pools: List[Sequence[V]] = [self.values]
        if self.values_for:
            for profile in ("safe", "competitive", "campanha", "stream"):
                try:
                    pools.append(self.values_for({"resolved_profile": profile}))
                except Exception:
                    pass
        for pool in pools:
            for v in pool:
                key = (v.root, v.path.casefold(), v.name.casefold())
                if key in seen:
                    continue
                seen.add(key)
                out.append(v.key())
        return out


def build(spec: RegSpec) -> OptimizationTask:
    def apply(core, ctx):
        ok, detail = core.write_registry_values_verified(spec.resolve(ctx))
        if ok and spec.restart:
            detail = (detail.rstrip(". ") + ". " + (spec.restart_note or
                      "Só passa a valer depois de reiniciar o Windows.")).strip()
        return ok, detail

    def verify(core, ctx):
        return core.verify_registry_values(spec.resolve(ctx))

    def revert(core, ctx):
        return core.revert_registry_from_baseline(spec.keys(), spec.id)

    return OptimizationTask(
        spec.id, spec.name, _module_of(spec), spec.category, tuple(spec.profiles),
        risk=spec.risk, reversible=True, restart=spec.restart, automatic=spec.automatic,
        description=spec.description, apply=apply, verify=verify, revert=revert,
        compatible=spec.compatible, tags=tuple(spec.tags) + ("registry", "declarative"),
        source=spec.source, trade_off=spec.trade_off, metric=spec.metric,
        relations=tuple(spec.relations),
        registry_keys=tuple(spec.keys()),
    )


_CURRENT_MODULE = {"id": "registry"}


def _module_of(spec: RegSpec) -> str:
    return _CURRENT_MODULE["id"]


def compile_specs(module_id: str, specs: Sequence[RegSpec]) -> Tuple[List[OptimizationTask], Dict[str, List[Tuple[str, str, str]]]]:
    """Devolve as tasks e o mapa de chaves na mesma passada.

    O mapa de chaves e o que o `azor_core.tracked_registry()` le para montar a
    captura do baseline. Ele sai da mesma declaracao que produziu o apply, entao
    nao existe o caso "o tweak grava uma chave que o baseline nao guarda".
    """
    tasks, keys = [], {}
    for spec in specs:
        _CURRENT_MODULE["id"] = module_id
        tasks.append(build(spec))
        keys[spec.id] = spec.keys()
    return tasks, keys
