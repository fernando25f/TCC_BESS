"""
Leitura de grandezas elétricas do circuito OpenDSS ativo.
Centraliza a indexação dos vetores do OpenDSS, cujo layout depende do número de condutores de cada elemento.
"""
from __future__ import annotations

from typing import List, Tuple

import opendssdirect as dss

from src.simulation.exceptions import ElementNotFoundError

_NOS_DE_FASE = frozenset({1, 2, 3})


def ativar_elemento(nome_completo: str) -> None:
    """Ativa um elemento pelo nome completo (ex.: 'transformer.TR1'), falhando se ele não existir."""
    if dss.Circuit.SetActiveElement(nome_completo) < 0:
        raise ElementNotFoundError(f"Elemento '{nome_completo}' não existe no circuito ativo.")


def ler_potencia_terminal(terminal: int = 1) -> Tuple[float, float]:
    """Retorna (P_kW, Q_kvar) totais que entram pelo terminal informado do elemento ativo."""
    n_terminais = dss.CktElement.NumTerminals()
    if not 1 <= terminal <= n_terminais:
        raise ValueError(
            f"Terminal {terminal} inválido para '{dss.CktElement.Name()}' ({n_terminais} terminais)."
        )

    # Powers() vem como [P, Q] por condutor, agrupado por terminal. Usar o número de fases como
    # passo quebra em trafos 1φ/2φ, cujo terminal tem mais condutores que fases (ex.: fase-fase ou neutro).
    n_condutores = dss.CktElement.NumConductors()
    inicio = 2 * n_condutores * (terminal - 1)
    trecho = dss.CktElement.Powers()[inicio:inicio + 2 * n_condutores]
    return float(sum(trecho[0::2])), float(sum(trecho[1::2]))


def ler_potencia_elemento(nome_completo: str, terminal: int = 1) -> Tuple[float, float]:
    """Ativa o elemento e retorna (P_kW, Q_kvar) no terminal informado."""
    ativar_elemento(nome_completo)
    return ler_potencia_terminal(terminal)


def ler_tensoes_fase_pu(barra: str) -> List[float]:
    """Retorna os módulos de tensão (pu) dos nós de fase 1–3 da barra, desconsiderando neutros."""
    if dss.Circuit.SetActiveBus(barra) < 0:
        raise ElementNotFoundError(f"Barra '{barra}' não existe no circuito ativo.")

    nos = dss.Bus.Nodes()
    modulos = dss.Bus.puVmagAngle()[0::2]
    tensoes = [float(v) for no, v in zip(nos, modulos) if no in _NOS_DE_FASE]
    if not tensoes:
        raise ElementNotFoundError(f"Barra '{barra}' não possui nós de fase (1, 2 ou 3).")
    return tensoes
