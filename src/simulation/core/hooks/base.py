from abc import ABC, abstractmethod
from typing import Any
from src.simulation.core.circuit import CircuitManager
from src.simulation.config import SimulationConfig

class SimulationProbe(ABC):
    """Sonda passiva que lê métricas da simulação passo-a-passo."""
    
    @abstractmethod
    def setup(self, circuit: CircuitManager, config: SimulationConfig) -> None:
        """Chamado ANTES do loop temporal (alocação de arrays, mapeamento de handles)."""
        pass

    @abstractmethod
    def on_step(self, passo: int, hora_str: str) -> None:
        """Chamado a CADA PASSO do loop temporal, DEPOIS da convergência do solver."""
        pass

    @abstractmethod
    def finalize(self) -> Any:
        """Processa e retorna os dados coletados no fim da simulação."""
        pass

class SimulationController(ABC):
    """Atuador ativo que modifica dinamicamente propriedades do circuito durante a simulação."""
    
    @abstractmethod
    def setup(self, circuit: CircuitManager, config: SimulationConfig) -> None:
        """Chamado ANTES do loop temporal."""
        pass

    @abstractmethod
    def actuate(self, passo: int, hora_str: str) -> None:
        """Chamado a CADA PASSO do loop temporal, ANTES da solução do solver."""
        pass
