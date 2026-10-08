from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Any, Optional
import opendssdirect as dss
import pandas as pd

from src.simulation.config import SimulationConfig
from src.simulation.core.circuit import CircuitManager
from src.simulation.scenarios.base import Scenario
from src.simulation.scenarios.solar_overload import SolarOverloadInjector
from src.simulation.exceptions import SimulationConvergenceError
from src.simulation.core.stats import ElementStats

from src.simulation.core.hooks import (
    SimulationProbe, 
    SimulationController, 
    SubstationProbe, 
    FeederProbe, 
    TrafoMTProbe, 
    TrafoBTProbe, 
    VoltageProbe
)

@dataclass
class ScenarioResult:
    nome_cenario: str
    curva_subestacao_kw: List[float]
    perfil_p_trafos_at: Dict[str, List[float]]
    perfil_v_trafos_at: Dict[str, List[float]]
    dados_trafos_at: Dict[str, ElementStats]
    dados_ctmt: Dict[str, ElementStats]
    p_max_se_kw: float
    hora_pico_se: str
    energia_total_se_mwh: float
    trafos_sobrecarregados: Set[str]
    registros_sobrecarga: List[Tuple[Any, ...]]
    convergiu_todas: bool
    passos_divergentes: List[int]
    tempo_segundos: float
    dados_tensao_barras: Optional[pd.DataFrame] = None
    info_sobrecarga: Optional[Dict[str, Any]] = None
    curvas_trafos_bt: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class SimulationEngine:
    """Motor de simulação temporal no domínio diário (Daily)."""

    def __init__(self, circuit_manager: CircuitManager, config: SimulationConfig) -> None:
        self.circuit: CircuitManager = circuit_manager
        self.config: SimulationConfig = config

    def run_scenario(self, scenario: Scenario) -> ScenarioResult:
        print(f"\n[ENGINE] Executando cenário: {scenario.nome.upper()}")
        t0 = time.time()

        self.circuit.carregar_circuito_base()
        scenario.aplicar(self.circuit)
        self.circuit.configurar_bases_e_demanda()
        self.circuit.inicializar_solucao()

        dss.Command(f"set mode=daily stepsize={self.config.passo_minutos}m maxiterations=50 number=1 hour=0 sec=0")

        # 1. Instanciar e Preparar Sondas
        sonda_subestacao = SubstationProbe()
        sonda_alimentadores = FeederProbe()
        sonda_trafos_mt = TrafoMTProbe()
        
        trafos_bt_alvos = SolarOverloadInjector.obter_trafos_alvo_bt(self.circuit, self.config)
        sonda_trafos_bt = TrafoBTProbe(trafos_bt_alvos)
        
        sondas: List[SimulationProbe] = [sonda_subestacao, sonda_alimentadores, sonda_trafos_mt, sonda_trafos_bt]
        
        rastrear_tensao = (scenario.nome == "padrao")
        sonda_tensao = None
        if rastrear_tensao:
            sonda_tensao = VoltageProbe()
            sondas.append(sonda_tensao)

        for sonda in sondas:
            sonda.setup(self.circuit, self.config)

        if hasattr(scenario, 'actuators') and scenario.actuators:
            for actuator in scenario.actuators:
                actuator.setup(self.circuit, self.config)

        passos_divergentes: List[int] = []
        convergiu_todas = True
        tap_atual = self.config.tap_normal

        # 2. Loop Temporal Puro
        for i in range(1, self.config.passos_simulacao + 1):
            minutos_totais = i * self.config.passo_minutos
            h = (minutos_totais // 60) % 24
            m = minutos_totais % 60
            hora_str = f"{h:02d}:{m:02d}" if minutos_totais < 24 * 60 else "24:00"

            # Controle dinâmico escalonado de tap nos transformadores AT
            if self.config.controle_tap_ativo:
                tap_alvo = self.config.obter_tap_alvo(i)
                if tap_alvo != tap_atual:
                    self.circuit.ajustar_tap_trafos_subestacao(tap_alvo)
                    print(f"  [CONTROLE DE TAP] {hora_str}h: Ajustando tap dos trafos AT de {tap_atual:.3f} para {tap_alvo:.3f}...")
                    tap_atual = tap_alvo

            # 1. Prepara a rede para medição "limpa" (ex: desliga baterias temporariamente)
            if hasattr(scenario, 'actuators') and scenario.actuators:
                for actuator in scenario.actuators:
                    if hasattr(actuator, 'prepare_measurement'):
                        actuator.prepare_measurement()

            # 2. Resolve sem controle para "ler o presente" (medidor em tempo real) natural
            dss.Solution.SolveNoControl()

            # 3. Atuadores reagem ao estado atual natural
            if hasattr(scenario, 'actuators') and scenario.actuators:
                for actuator in scenario.actuators:
                    actuator.actuate(i, hora_str)

            # 4. Resolve a física final com as ações do atuador (e avança o tempo)
            dss.Solution.Solve()

            if not dss.Solution.Converged():
                convergiu_todas = False
                passos_divergentes.append(i)
                if self.config.interromper_em_divergencia:
                    raise SimulationConvergenceError(f"Fluxo de potência divergiu no passo {i} ({hora_str}h).")

            # 3. Avisa todas as sondas que o tempo avançou
            for sonda in sondas:
                sonda.on_step(i, hora_str)

        # 4. Finalização e Extração dos Dados
        res_subestacao = sonda_subestacao.finalize()
        res_mt = sonda_trafos_mt.finalize()

        duracao = time.time() - t0
        print(f"  [OK] Concluído em {duracao:.2f}s | Pico: {res_subestacao['p_max_se_kw']/1000:.2f} MW às {res_subestacao['hora_pico_se']} | Energia: {res_subestacao['energia_total_se_mwh']:.2f} MWh")

        return ScenarioResult(
            nome_cenario=scenario.nome,
            curva_subestacao_kw=res_subestacao['curva_subestacao_kw'],
            perfil_p_trafos_at=res_subestacao['perfil_p_trafos_at'],
            perfil_v_trafos_at=res_subestacao['perfil_v_trafos_at'],
            dados_trafos_at=res_subestacao['dados_trafos_at'],
            p_max_se_kw=res_subestacao['p_max_se_kw'],
            hora_pico_se=res_subestacao['hora_pico_se'],
            energia_total_se_mwh=res_subestacao['energia_total_se_mwh'],
            
            dados_ctmt=sonda_alimentadores.finalize(),
            
            trafos_sobrecarregados=res_mt['trafos_sobrecarregados'],
            registros_sobrecarga=res_mt['registros_sobrecarga'],
            
            curvas_trafos_bt=sonda_trafos_bt.finalize(),
            
            dados_tensao_barras=sonda_tensao.finalize() if sonda_tensao else None,
            
            info_sobrecarga=getattr(scenario, 'info_sobrecarga', None),
            convergiu_todas=convergiu_todas,
            passos_divergentes=passos_divergentes,
            tempo_segundos=duracao
        )
