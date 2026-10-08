from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Any, Optional
from src.simulation.config import SimulationConfig

if TYPE_CHECKING:
    from src.simulation.core.circuit import CircuitManager

class ScenarioComponent(ABC):
    """Interface para componentes independentes (peças de Lego) que modificam o circuito."""
    
    @abstractmethod
    def aplicar(self, circuit: CircuitManager) -> Any:
        pass

from src.simulation.core.hooks.base import SimulationController

class Scenario:
    """Contêiner que executa uma lista de componentes por composição."""
    
    def __init__(self, nome: str, components: List[ScenarioComponent], actuators: Optional[List[SimulationController]] = None) -> None:
        self.nome = nome
        self.components = components
        self.actuators: List[SimulationController] = actuators or []
        self.info_sobrecarga: Optional[dict] = None

    def aplicar(self, circuit: CircuitManager) -> None:
        for comp in self.components:
            res = comp.aplicar(circuit)
            if res and isinstance(res, dict) and 'potencia_total_extra_kw' in res:
                self.info_sobrecarga = res
