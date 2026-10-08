"""
Resolução estrita de alvos de simulação (alimentadores e transformadores AT) a partir dos metadados.
Nunca substitui o alvo por um valor padrão: identificadores inválidos ou ambíguos geram exceção.
"""
from __future__ import annotations

from typing import Any, List, Mapping, Optional, Tuple

from src.simulation.exceptions import (
    AmbiguousFeederError,
    FeederNotFoundError,
    TransformerNotFoundError,
)

Metadados = Mapping[str, Mapping[str, Any]]


def _normalizar(valor: Optional[str]) -> str:
    return str(valor).strip() if valor is not None else ""


def _nome_alimentador(cod: str, info: Mapping[str, Any]) -> str:
    return str(info.get("nome", cod))


def _descrever_alimentadores(codigos: List[str], alimentadores: Metadados) -> str:
    return ", ".join(f"{cod} ({_nome_alimentador(cod, alimentadores[cod])})" for cod in codigos)


def resolver_alimentador(alvo: Optional[str], alimentadores: Metadados) -> Tuple[str, str]:
    """Resolve (código, nome) por código exato, nome exato ou trecho de nome que seja único."""
    alvo_str = _normalizar(alvo)
    if not alvo_str:
        raise FeederNotFoundError("Nenhum alimentador alvo foi informado na configuração.")
    if not alimentadores:
        raise FeederNotFoundError(
            f"Alimentador '{alvo_str}' não pode ser resolvido: nenhum alimentador carregado no escopo."
        )

    if alvo_str in alimentadores:
        return alvo_str, _nome_alimentador(alvo_str, alimentadores[alvo_str])

    alvo_upper = alvo_str.upper()
    nomes = {cod: _nome_alimentador(cod, info).strip().upper() for cod, info in alimentadores.items()}
    exatos = [cod for cod, nome in nomes.items() if nome == alvo_upper]
    parciais = [cod for cod, nome in nomes.items() if alvo_upper in nome]

    # Nome exato tem precedência para que "GOIANIA LESTE-1" não colida com "GOIANIA LESTE-17"
    for candidatos in (exatos, parciais):
        if len(candidatos) == 1:
            cod = candidatos[0]
            return cod, _nome_alimentador(cod, alimentadores[cod])
        if len(candidatos) > 1:
            raise AmbiguousFeederError(
                f"Alimentador '{alvo_str}' é ambíguo; corresponde a: "
                f"{_descrever_alimentadores(candidatos, alimentadores)}. Use o código ou o nome completo."
            )

    raise FeederNotFoundError(
        f"Alimentador '{alvo_str}' não encontrado. Disponíveis: "
        f"{_descrever_alimentadores(list(alimentadores), alimentadores)}."
    )


def resolver_trafo_at(alvo: Optional[str], trafos: Metadados) -> Tuple[str, Mapping[str, Any]]:
    """Resolve (nome completo, metadados) do trafo AT pelo identificador curto (ex.: 'TR1') ou nome completo."""
    alvo_str = _normalizar(alvo)
    if not alvo_str:
        raise TransformerNotFoundError('O escopo TRAFO_AT exige um alvo explícito (ex.: alvo="TR1").')

    alvo_upper = alvo_str.upper()
    for nome, info in trafos.items():
        if alvo_upper in (nome.upper(), str(info.get("identificador", "")).upper()):
            return nome, info

    disponiveis = ", ".join(str(info.get("identificador", nome)) for nome, info in trafos.items())
    raise TransformerNotFoundError(
        f"Transformador AT '{alvo_str}' não encontrado. Disponíveis: {disponiveis or 'nenhum'}."
    )
