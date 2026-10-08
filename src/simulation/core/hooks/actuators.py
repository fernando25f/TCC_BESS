import opendssdirect as dss
from typing import Dict, Any, Optional

from src.simulation.core.circuit import CircuitManager
from src.simulation.config import SimulationConfig
from src.simulation.core.hooks.base import SimulationController

class BESSRealTimeController(SimulationController):
    """
    Controlador em Malha Fechada (Real-Time) para Baterias.
    Lê o fluxo de potência do elemento monitorado e atua no BESS correspondente
    para manter os limites de fluxo reverso e pico de carga, preservando 
    os limites de SoC (10% a 90%) e forçando descarga noturna.
    """
    
    def __init__(self, regras_bess: Dict[str, Dict[str, Any]]) -> None:
        """
        regras_bess: Dict mapeando nome do Storage para suas regras.
        Ex: {
            "BESS_TR1": {
                "monitor": "Transformer.TR1",
                "limite_reverso_kw": -100.0,
                "limite_pico_kw": 500.0,
                "kw_rated": 250.0
            }
        }
        """
        self.regras_bess = regras_bess
        self.config: Optional[SimulationConfig] = None
        self.circuit: Optional[CircuitManager] = None

    def setup(self, circuit: CircuitManager, config: SimulationConfig) -> None:
        self.circuit = circuit
        self.config = config
        
        # Garante que as baterias iniciem com 10% de carga e estado IDLING
        for nome_bess in self.regras_bess.keys():
            dss.Command(f"edit Storage.{nome_bess} %stored=10 state=IDLING")

    def prepare_measurement(self) -> None:
        """Coloca o BESS em IDLING para ler a rede em seu estado natural."""
        for nome_bess in self.regras_bess.keys():
            dss.Command(f"edit Storage.{nome_bess} state=IDLING")

    def actuate(self, passo: int, hora_str: str) -> None:
        partes = hora_str.split(":")
        h = int(partes[0])
        m = int(partes[1]) if len(partes) > 1 else 0
        
        for nome_bess, regras in self.regras_bess.items():
            elemento_monitor = regras["monitor"]
            lim_reverso = regras["limite_reverso_kw"]
            lim_pico = regras["limite_pico_kw"]
            inversor_kw = regras["kw_rated"]
            
            # 1. Lê a potência fluindo no elemento monitorado
            dss.Circuit.SetActiveElement(elemento_monitor)
            if elemento_monitor.lower() == "vsource.source":
                p_atual = -dss.Circuit.TotalPower()[0]
            else:
                powers = dss.CktElement.Powers()
                num_phases = dss.CktElement.NumPhases()
                num_phases = dss.CktElement.NumPhases()
                p_atual = sum(powers[0:(num_phases*2):2]) if powers else 0.0
            
            float_hour = h + m / 60.0
            
            # 2. Lê o SoC da bateria
            dss.Circuit.SetActiveElement(f"Storage.{nome_bess}")
            soc_atual = float(dss.Properties.Value("%stored"))
            
            # 3. Lógica de Atuação
            if p_atual < lim_reverso and soc_atual < 90.0:
                # O BESS carrega o máximo possível para garantir que estará cheio, 
                # contanto que não crie um novo pico de demanda na rede
                margem_ate_pico = lim_pico - p_atual
                charge_kw = min(inversor_kw, margem_ate_pico)
                
                pct_charge = (charge_kw / inversor_kw) * 100
                pct_charge = max(0.0, min(pct_charge, 100.0))
                
                if pct_charge > 0:
                    dss.Command(f"edit Storage.{nome_bess} state=CHARGING %Charge={pct_charge}")
                else:
                    dss.Command(f"edit Storage.{nome_bess} state=IDLING")
                
            elif soc_atual > 10.0 and (p_atual > lim_pico or float_hour >= 18.5):
                # Descarga proativa noturna tenta zerar a carga vista pelo monitor se h >= 18.5
                alvo = lim_pico if float_hour < 18.5 else 0.0
                excesso_kw = p_atual - alvo
                
                if excesso_kw > 0:
                    pct_discharge = (excesso_kw / inversor_kw) * 100
                    pct_discharge = min(pct_discharge, 100.0)
                    dss.Command(f"edit Storage.{nome_bess} state=DISCHARGING %Discharge={pct_discharge}")
                else:
                    dss.Command(f"edit Storage.{nome_bess} state=IDLING")
            else:
                dss.Command(f"edit Storage.{nome_bess} state=IDLING")
