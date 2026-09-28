"""One source of truth for the AC settings written and checked by AZOR.

Os valores são os da auditoria do plano (DESENVOLVIMENTO.md, "O plano de energia
estava cobrando 1% low"): quem faz o clock subir em ~1 ms é o Speed Shift/CPPC
com preferência de desempenho (EPP 0) e boost Agressivo (2), não o mínimo
travado. O mínimo fica em 5% para a CPU esfriar fora do jogo e ter folga térmica
para sustentar o turbo, e o resfriamento é Ativo (ventoinha antes de cortar clock).

Uma refatoração tinha deixado o boost em 1 (Habilitado) - abaixo do padrão do
próprio Alto desempenho de onde o plano é copiado - e parado de gravar o EPP,
enquanto o Guardian ainda esperava 2 e 0. O app gravava um valor e reprovava o
próprio plano em seguida.
"""
POWER_SETTINGS = (
    ("cpu_min_ac", "SUB_PROCESSOR", "PROCTHROTTLEMIN", 5, "CPU minimum state"),
    ("cpu_max_ac", "SUB_PROCESSOR", "PROCTHROTTLEMAX", 100, "CPU maximum state"),
    ("epp_ac", "SUB_PROCESSOR", "PERFEPP", 0, "Processor energy performance preference"),
    ("boost_mode_ac", "SUB_PROCESSOR", "PERFBOOSTMODE", 2, "Processor performance boost mode (aggressive)"),
    ("cooling_policy_ac", "SUB_PROCESSOR", "SYSCOOLPOL", 1, "System cooling policy (active)"),
)
POWER_EXPECTED = {key: value for key, subgroup, setting, value, label in POWER_SETTINGS}
