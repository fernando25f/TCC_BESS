import opendssdirect as dss
from typing import List, Dict, Any
from src.simulation.scenarios.base import ScenarioComponent
from src.simulation.core.circuit import CircuitManager

class BESSDeploymentComponent(ScenarioComponent):
    """
    Injeta fisicamente as baterias (elementos Storage) no circuito do OpenDSS.
    Recebe os comandos pré-calculados pelo BESSSizer.
    """
    
    def __init__(self, comandos_dss: List[str]) -> None:
        self.comandos_dss = comandos_dss

    def aplicar(self, circuit: CircuitManager) -> None:
        print(f"  [BESS] Injetando {len(self.comandos_dss)} baterias físicas no circuito...")
        for cmd in self.comandos_dss:
            dss.Command(cmd)
            
        # Recalcula as bases de tensão para garantir que os novos nós estejam corretos
        dss.Command("CalcVoltageBases")
