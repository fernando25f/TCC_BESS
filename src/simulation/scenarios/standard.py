from __future__ import annotations
import opendssdirect as dss
from src.simulation.scenarios.base import ScenarioComponent
from src.simulation.core.circuit import CircuitManager

class DisableDistributedGenerationComponent(ScenarioComponent):
    """Desliga geradores fotovoltaicos e distribuídos para manter apenas o carregamento de cargas puras."""

    def aplicar(self, circuit: CircuitManager) -> None:
        dss.Command("batchedit pvsystem..* enabled=no")
        dss.Command("batchedit generator..* enabled=no")
