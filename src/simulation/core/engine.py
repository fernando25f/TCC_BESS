from __future__ import annotations
import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Any, Optional
import opendssdirect as dss
import numpy as np
import pandas as pd

from src.simulation.config import SimulationConfig
from src.simulation.core.circuit import CircuitManager
from src.simulation.scenarios.base import Scenario
from src.simulation.scenarios.solar_overload import SolarOverloadInjector
from src.simulation.exceptions import SimulationConvergenceError
from src.simulation.core.stats import ElementStats

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
        cache_trafos = self.circuit.mapear_trafos_mt()

        dss.Command(f"set mode=daily stepsize={self.config.passo_minutos}m maxiterations=50 number=1 hour=0 sec=0")

        rastrear_tensao = (scenario.nome == "padrao")
        buses_fase: List[str] = []
        indices_fase: Optional[np.ndarray] = None
        num_nodes = 0
        v_min_arr: Optional[np.ndarray] = None
        step_min_arr: Optional[np.ndarray] = None
        v_max_arr: Optional[np.ndarray] = None
        step_max_arr: Optional[np.ndarray] = None

        if rastrear_tensao:
            node_names = dss.Circuit.AllNodeNames()
            indices_fase = np.array([idx for idx, name in enumerate(node_names) if not name.endswith('.0')], dtype=np.int32)
            buses_fase = [node_names[idx].split('.')[0] for idx in indices_fase]
            num_nodes = len(indices_fase)
            v_min_arr = np.full(num_nodes, 999.0, dtype=np.float32)
            step_min_arr = np.zeros(num_nodes, dtype=np.int16)
            v_max_arr = np.full(num_nodes, 0.0, dtype=np.float32)
            step_max_arr = np.zeros(num_nodes, dtype=np.int16)

        curva_subestacao_kw: List[float] = []
        perfil_p_trafos_at: Dict[str, List[float]] = {tr: [] for tr in self.circuit.trafos_subestacao}
        perfil_v_trafos_at: Dict[str, List[float]] = {tr: [] for tr in self.circuit.trafos_subestacao}

        dados_trafos_at: Dict[str, ElementStats] = {tr: ElementStats() for tr in self.circuit.trafos_subestacao}
        dados_ctmt: Dict[str, ElementStats] = {cod_id: ElementStats() for cod_id in self.circuit.dict_ctmt_info.keys()}

        # Rastreamento das curvas 24h de P(kW), Q(kvar) e V(pu) dos trafos BT monitorados
        trafos_bt_alvos = SolarOverloadInjector.obter_trafos_alvo_bt(self.circuit, self.config)
        curvas_trafos_bt: Dict[str, Dict[str, Any]] = {
            t_nome: {
                'kva_nom': kva,
                'barra_bt': sec_b.split('.')[0],
                'curva_p_kw': [],
                'curva_q_kvar': [],
                'curva_v_pu': []
            }
            for t_nome, kva, sec_b in trafos_bt_alvos
        }

        trafos_sobrecarregados: Set[str] = set()
        registros_sobrecarga: List[Tuple[Any, ...]] = []
        passos_divergentes: List[int] = []
        convergiu_todas = True

        tap_atual = self.config.tap_normal

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

            dss.Solution.Solve()

            if not dss.Solution.Converged():
                convergiu_todas = False
                passos_divergentes.append(i)
                if self.config.interromper_em_divergencia:
                    raise SimulationConvergenceError(f"Fluxo de potência divergiu no passo {i} ({hora_str}h).")

            # Rastreamento vetorizado de extremos de tensão no instante atual
            if rastrear_tensao and num_nodes > 0:
                mags = np.array(dss.Circuit.AllBusMagPu(), dtype=np.float32)[indices_fase]
                valid_mask = mags > 0.50

                mask_min = (mags < v_min_arr) & valid_mask
                v_min_arr[mask_min] = mags[mask_min]
                step_min_arr[mask_min] = i

                mask_max = (mags > v_max_arr) & valid_mask
                v_max_arr[mask_max] = mags[mask_max]
                step_max_arr[mask_max] = i

            p_se_kw = -dss.Circuit.TotalPower()[0]
            curva_subestacao_kw.append(p_se_kw)

            self._monitorar_trafos_mt(cache_trafos, hora_str, trafos_sobrecarregados, registros_sobrecarga)
            self._monitorar_trafos_at(hora_str, dados_trafos_at, perfil_p_trafos_at, perfil_v_trafos_at)
            self._monitorar_alimentadores_ctmt(hora_str, dados_ctmt)

            # Monitora curvas 24h dos trafos BT sob estudo
            for t_nome, dados_tr in curvas_trafos_bt.items():
                dss.Circuit.SetActiveElement(f"transformer.{t_nome}")
                pwrs = dss.CktElement.Powers()
                p_kw = sum(pwrs[k * 2] for k in range(3))
                q_kvar = sum(pwrs[k * 2 + 1] for k in range(3))
                dados_tr['curva_p_kw'].append(p_kw)
                dados_tr['curva_q_kvar'].append(q_kvar)

                dss.Circuit.SetActiveBus(dados_tr['barra_bt'])
                pu_mags = dss.Bus.puVmagAngle()
                num_nodes_bt = len(dss.Bus.Nodes())
                v_pu = (sum(pu_mags[2 * k] for k in range(num_nodes_bt)) / num_nodes_bt) if (pu_mags and num_nodes_bt > 0) else 1.0
                dados_tr['curva_v_pu'].append(v_pu)

        p_max_se = max(curva_subestacao_kw) if curva_subestacao_kw else 0.0
        idx_p = curva_subestacao_kw.index(p_max_se) if curva_subestacao_kw else 0
        min_p = (idx_p + 1) * self.config.passo_minutos
        hora_pico_se = f"{(min_p // 60) % 24:02d}:{min_p % 60:02d}" if curva_subestacao_kw else "--:--"
        energia_total_se = (sum(curva_subestacao_kw) * 0.25 / 1000.0) if curva_subestacao_kw else 0.0

        duracao = time.time() - t0
        print(f"  [OK] Concluído em {duracao:.2f}s | Pico: {p_max_se/1000:.2f} MW às {hora_pico_se} | Energia: {energia_total_se:.2f} MWh")

        dados_tensao_barras: Optional[pd.DataFrame] = None
        if rastrear_tensao and num_nodes > 0:
            dados_tensao_barras = self._processar_tensao_barras(
                buses_fase, v_min_arr, step_min_arr, v_max_arr, step_max_arr
            )

        return ScenarioResult(
            nome_cenario=scenario.nome,
            curva_subestacao_kw=curva_subestacao_kw,
            perfil_p_trafos_at=perfil_p_trafos_at,
            perfil_v_trafos_at=perfil_v_trafos_at,
            dados_trafos_at=dados_trafos_at,
            dados_ctmt=dados_ctmt,
            p_max_se_kw=p_max_se,
            hora_pico_se=hora_pico_se,
            energia_total_se_mwh=energia_total_se,
            trafos_sobrecarregados=trafos_sobrecarregados,
            registros_sobrecarga=registros_sobrecarga,
            convergiu_todas=convergiu_todas,
            passos_divergentes=passos_divergentes,
            tempo_segundos=duracao,
            dados_tensao_barras=dados_tensao_barras,
            info_sobrecarga=getattr(scenario, 'info_sobrecarga', None),
            curvas_trafos_bt=curvas_trafos_bt
        )

    def _converter_passo_para_hora(self, passo: int) -> str:
        if passo <= 0:
            return "--:--"
        minutos = passo * self.config.passo_minutos
        h = (minutos // 60) % 24
        m = minutos % 60
        return f"{h:02d}:{m:02d}" if minutos < 24 * 60 else "24:00"

    def _processar_tensao_barras(
        self,
        buses_fase: List[str],
        v_min_arr: np.ndarray,
        step_min_arr: np.ndarray,
        v_max_arr: np.ndarray,
        step_max_arr: np.ndarray
    ) -> pd.DataFrame:
        df_nodes = pd.DataFrame({
            'barra': buses_fase,
            'v_min': v_min_arr,
            'passo_min': step_min_arr,
            'v_max': v_max_arr,
            'passo_max': step_max_arr
        })

        idx_min = df_nodes.groupby('barra')['v_min'].idxmin()
        df_min = df_nodes.loc[idx_min, ['barra', 'v_min', 'passo_min']]

        idx_max = df_nodes.groupby('barra')['v_max'].idxmax()
        df_max = df_nodes.loc[idx_max, ['barra', 'v_max', 'passo_max']]

        df_barras = pd.merge(df_min, df_max, on='barra')
        df_barras['hora_v_min'] = df_barras['passo_min'].apply(self._converter_passo_para_hora)
        df_barras['hora_v_max'] = df_barras['passo_max'].apply(self._converter_passo_para_hora)
        df_barras['v_min_pu'] = df_barras['v_min'].round(4)
        df_barras['v_max_pu'] = df_barras['v_max'].round(4)
        df_barras['delta_v_pu'] = (df_barras['v_max_pu'] - df_barras['v_min_pu']).round(4)

        sub = df_barras['v_min_pu'] < self.config.limite_subtensao_pu
        sob = df_barras['v_max_pu'] > self.config.limite_sobretensao_pu

        df_barras['subtensao'] = sub
        df_barras['sobretensao'] = sob

        conditions = [
            sub & sob,
            sub & ~sob,
            ~sub & sob
        ]
        choices = ['AMBAS', 'SUBTENSAO', 'SOBRETENSAO']
        df_barras['classificacao'] = np.select(conditions, choices, default='ADEQUADA')

        return df_barras[[
            'barra', 'v_min_pu', 'hora_v_min', 'v_max_pu', 'hora_v_max',
            'delta_v_pu', 'subtensao', 'sobretensao', 'classificacao'
        ]]

    def _monitorar_trafos_mt(
        self,
        cache_trafos: Dict[str, Dict[str, Any]],
        hora_str: str,
        trafos_sobrecarregados: Set[str],
        registros_sobrecarga: List[Tuple[Any, ...]]
    ) -> None:
        for t_nome, info_tr in cache_trafos.items():
            dss.Transformers.Name(t_nome)
            powers = dss.CktElement.Powers()
            np_tr = dss.CktElement.NumConductors()
            pt = sum(powers[k * 2] for k in range(np_tr))
            qt = sum(powers[k * 2 + 1] for k in range(np_tr))
            s2 = pt**2 + qt**2
            if s2 > info_tr['limite_kva2']:
                cod_id_tr = info_tr['cod_id']
                trafos_sobrecarregados.add(cod_id_tr)
                s_kva = math.sqrt(s2)
                pct = (s_kva / info_tr['kva_nom']) * 100.0
                registros_sobrecarga.append((cod_id_tr, hora_str, s_kva, info_tr['kva_nom'], pct))

    def _monitorar_trafos_at(
        self,
        hora_str: str,
        dados_trafos_at: Dict[str, ElementStats],
        perfil_p_trafos_at: Dict[str, List[float]],
        perfil_v_trafos_at: Dict[str, List[float]]
    ) -> None:
        for tr in self.circuit.trafos_subestacao:
            dss.Circuit.SetActiveElement(f"transformer.{tr}")
            powers_tr = dss.CktElement.Powers()
            p_tr_kw = sum(powers_tr[2 * k] for k in range(3))
            q_tr_kvar = sum(powers_tr[2 * k + 1] for k in range(3))
            s_tr_kva = math.sqrt(p_tr_kw**2 + q_tr_kvar**2)
            fp_tr = (p_tr_kw / s_tr_kva) if s_tr_kva > 0 else 1.0

            sec_bus = self.circuit.trafo_sec_bus[tr]
            dss.Circuit.SetActiveBus(sec_bus)
            pu_nodes = dss.Bus.puVmagAngle()
            v_pus = [pu_nodes[2 * k] for k in range(len(dss.Bus.Nodes()))] if pu_nodes else [1.0]
            v_min_step = min(v_pus)
            v_max_step = max(v_pus)
            v_med_step = (sum(v_pus) / len(v_pus)) if v_pus else 1.0

            dados_trafos_at[tr].energia_kwh += p_tr_kw * 0.25
            perfil_p_trafos_at[tr].append(p_tr_kw)
            perfil_v_trafos_at[tr].append(v_med_step)
            if v_min_step < dados_trafos_at[tr].v_min_pu:
                dados_trafos_at[tr].v_min_pu = v_min_step
            if v_max_step > dados_trafos_at[tr].v_max_pu:
                dados_trafos_at[tr].v_max_pu = v_max_step

            if s_tr_kva > dados_trafos_at[tr].s_max_kva:
                dados_trafos_at[tr].s_max_kva = s_tr_kva
                dados_trafos_at[tr].p_max_kw = p_tr_kw
                dados_trafos_at[tr].q_at_pmax = q_tr_kvar
                dados_trafos_at[tr].hora_pico = hora_str
                dados_trafos_at[tr].fp_pico = fp_tr

    def _monitorar_alimentadores_ctmt(self, hora_str: str, dados_ctmt: Dict[str, ElementStats]) -> None:
        for cod_id in self.circuit.dict_ctmt_info.keys():
            dss.Circuit.SetActiveElement(f"line.DJ_{cod_id}")
            powers_dj = dss.CktElement.Powers()
            p_dj_kw = sum(powers_dj[2 * k] for k in range(3))
            q_dj_kvar = sum(powers_dj[2 * k + 1] for k in range(3))
            s_dj_kva = math.sqrt(p_dj_kw**2 + q_dj_kvar**2)
            fp_dj = (p_dj_kw / s_dj_kva) if s_dj_kva > 0 else 1.0

            barra_ctmt = self.circuit.dict_ctmt_info[cod_id]['barra']
            dss.Circuit.SetActiveBus(barra_ctmt)
            pu_nodes_dj = dss.Bus.puVmagAngle()
            v_pus_dj = [pu_nodes_dj[2 * k] for k in range(len(dss.Bus.Nodes()))] if pu_nodes_dj else [1.0]

            dados_ctmt[cod_id].energia_kwh += p_dj_kw * 0.25
            dados_ctmt[cod_id].curva_p_kw.append(p_dj_kw)
            if min(v_pus_dj) < dados_ctmt[cod_id].v_min_pu:
                dados_ctmt[cod_id].v_min_pu = min(v_pus_dj)
            if max(v_pus_dj) > dados_ctmt[cod_id].v_max_pu:
                dados_ctmt[cod_id].v_max_pu = max(v_pus_dj)

            if s_dj_kva > dados_ctmt[cod_id].s_max_kva:
                dados_ctmt[cod_id].s_max_kva = s_dj_kva
                dados_ctmt[cod_id].p_max_kw = p_dj_kw
                dados_ctmt[cod_id].q_at_pmax = q_dj_kvar
                dados_ctmt[cod_id].hora_pico = hora_str
                dados_ctmt[cod_id].fp_pico = fp_dj
