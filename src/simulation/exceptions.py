"""
Exceções customizadas de domínio para a simulação da rede elétrica.
Garante tratamento de falhas específico e fail-fast em estados inválidos.
"""

class SimulationError(Exception):
    """Exceção base para erros ocorridos durante o ciclo de simulação."""
    pass

class CircuitLoadError(SimulationError):
    """Lançada quando arquivos essenciais do circuito OpenDSS não são encontrados ou estão corrompidos."""
    pass

class SimulationConvergenceError(SimulationError):
    """Lançada quando o fluxo de potência do OpenDSS diverge durante a resolução temporal."""
    pass

class FeederNotFoundError(SimulationError):
    """Lançada quando um alimentador solicitado não é encontrado no modelo da rede."""
    pass

class AmbiguousFeederError(SimulationError):
    """Lançada quando o identificador informado corresponde a mais de um alimentador."""
    pass

class TransformerNotFoundError(SimulationError):
    """Lançada quando o transformador AT solicitado não existe nos metadados da subestação."""
    pass

class ElementNotFoundError(SimulationError):
    """Lançada quando um elemento ou barra não existe no circuito OpenDSS ativo."""
    pass

class ConfigurationError(SimulationError):
    """Lançada quando parâmetros de SimulationConfig são inválidos ou inconsistentes entre si."""
    pass
