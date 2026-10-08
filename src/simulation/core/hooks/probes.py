import math
from typing import Dict, List, Set, Tuple, Any, Optional
import opendssdirect as dss
import numpy as np
import pandas as pd

from src.simulation.core.hooks.base import SimulationProbe
from src.simulation.core.circuit import CircuitManager
from src.simulation.config import SimulationConfig
from src.simulation.core.stats import ElementStats

class SubstationProbe(SimulationProbe):
    """Sonda que monitora os transformadores da subestação e o fluxo de potência total."""
    
    def __init__(self):
        self.circuit: Optional[CircuitManager] = None
        self.curva_subestacao_kw: List[float] = []
        self.perfil_p_trafos_at: Dict[str, List[float]] = {}
        self.perfil_v_trafos_at: Dict[str, List[float]] = {}
        self.dados_trafos_at: Dict[str, ElementStats] = {}

    def setup(self, circuit: CircuitManager, config: SimulationConfig) -> None:
        self.circuit = circuit
        self.perfil_p_trafos_at = {tr: [] for tr in circuit.trafos_subestacao}
        self.perfil_v_trafos_at = {tr: [] for tr in circuit.trafos_subestacao}
        self.dados_trafos_at = {tr: ElementStats() for tr in circuit.trafos_subestacao}

    def on_step(self, passo: int, hora_str: str) -> None:
        if not self.circuit: return
        p_se_kw = -dss.Circuit.TotalPower()[0]
        self.curva_subestacao_kw.append(p_se_kw)

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

            stats = self.dados_trafos_at[tr]
            stats.energia_kwh += p_tr_kw * 0.25
            self.perfil_p_trafos_at[tr].append(p_tr_kw)
            self.perfil_v_trafos_at[tr].append(v_med_step)
            
            if v_min_step < stats.v_min_pu: stats.v_min_pu = v_min_step
            if v_max_step > stats.v_max_pu: stats.v_max_pu = v_max_step

            if s_tr_kva > stats.s_max_kva:
                stats.s_max_kva = s_tr_kva
                stats.p_max_kw = p_tr_kw
                stats.q_at_pmax = q_tr_kvar
                stats.hora_pico = hora_str
                stats.fp_pico = fp_tr

    def finalize(self) -> Any:
        # p_max_se e hora_pico_se podem ser calculados aqui ou no engine
        p_max_se = max(self.curva_subestacao_kw) if self.curva_subestacao_kw else 0.0
        energia_total_se = (sum(self.curva_subestacao_kw) * 0.25 / 1000.0) if self.curva_subestacao_kw else 0.0
        
        # Encontra a hora do pico
        idx_p = self.curva_subestacao_kw.index(p_max_se) if self.curva_subestacao_kw else 0
        min_p = (idx_p + 1) * 15 # Assumindo 15min fixo
        hora_pico_se = f"{(min_p // 60) % 24:02d}:{min_p % 60:02d}" if self.curva_subestacao_kw else "--:--"

        return {
            'curva_subestacao_kw': self.curva_subestacao_kw,
            'perfil_p_trafos_at': self.perfil_p_trafos_at,
            'perfil_v_trafos_at': self.perfil_v_trafos_at,
            'dados_trafos_at': self.dados_trafos_at,
            'p_max_se_kw': p_max_se,
            'hora_pico_se': hora_pico_se,
            'energia_total_se_mwh': energia_total_se
        }


class FeederProbe(SimulationProbe):
    """Sonda que monitora os disjuntores dos alimentadores (CTMT)."""
    
    def __init__(self):
        self.circuit: Optional[CircuitManager] = None
        self.dados_ctmt: Dict[str, ElementStats] = {}

    def setup(self, circuit: CircuitManager, config: SimulationConfig) -> None:
        self.circuit = circuit
        self.dados_ctmt = {cod_id: ElementStats() for cod_id in circuit.dict_ctmt_info.keys()}

    def on_step(self, passo: int, hora_str: str) -> None:
        if not self.circuit: return
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

            stats = self.dados_ctmt[cod_id]
            stats.energia_kwh += p_dj_kw * 0.25
            stats.curva_p_kw.append(p_dj_kw)
            
            if min(v_pus_dj) < stats.v_min_pu: stats.v_min_pu = min(v_pus_dj)
            if max(v_pus_dj) > stats.v_max_pu: stats.v_max_pu = max(v_pus_dj)

            if s_dj_kva > stats.s_max_kva:
                stats.s_max_kva = s_dj_kva
                stats.p_max_kw = p_dj_kw
                stats.q_at_pmax = q_dj_kvar
                stats.hora_pico = hora_str
                stats.fp_pico = fp_dj

    def finalize(self) -> Any:
        return self.dados_ctmt


class TrafoMTProbe(SimulationProbe):
    """Sonda que rastreia sobrecargas térmicas nos transformadores de distribuição (MT)."""
    
    def __init__(self):
        self.cache_trafos: Dict[str, Dict[str, Any]] = {}
        self.trafos_sobrecarregados: Set[str] = set()
        self.registros_sobrecarga: List[Tuple[Any, ...]] = []

    def setup(self, circuit: CircuitManager, config: SimulationConfig) -> None:
        self.cache_trafos = circuit.mapear_trafos_mt()

    def on_step(self, passo: int, hora_str: str) -> None:
        for t_nome, info_tr in self.cache_trafos.items():
            dss.Transformers.Name(t_nome)
            powers = dss.CktElement.Powers()
            np_tr = dss.CktElement.NumConductors()
            pt = sum(powers[k * 2] for k in range(np_tr))
            qt = sum(powers[k * 2 + 1] for k in range(np_tr))
            s2 = pt**2 + qt**2
            if s2 > info_tr['limite_kva2']:
                cod_id_tr = info_tr['cod_id']
                self.trafos_sobrecarregados.add(cod_id_tr)
                s_kva = math.sqrt(s2)
                pct = (s_kva / info_tr['kva_nom']) * 100.0
                self.registros_sobrecarga.append((cod_id_tr, hora_str, s_kva, info_tr['kva_nom'], pct))

    def finalize(self) -> Any:
        return {
            'trafos_sobrecarregados': self.trafos_sobrecarregados,
            'registros_sobrecarga': self.registros_sobrecarga
        }


class TrafoBTProbe(SimulationProbe):
    """Sonda para coletar as curvas 24h dos trafos sob estresse da GD na Baixa Tensão."""
    
    def __init__(self, alvos_bt: List[Tuple[str, float, str]]):
        self.alvos_bt = alvos_bt
        self.curvas_trafos_bt: Dict[str, Dict[str, Any]] = {}

    def setup(self, circuit: CircuitManager, config: SimulationConfig) -> None:
        self.curvas_trafos_bt = {
            t_nome: {
                'kva_nom': kva,
                'barra_bt': sec_b.split('.')[0],
                'curva_p_kw': [],
                'curva_q_kvar': [],
                'curva_v_pu': []
            }
            for t_nome, kva, sec_b in self.alvos_bt
        }

    def on_step(self, passo: int, hora_str: str) -> None:
        for t_nome, dados_tr in self.curvas_trafos_bt.items():
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

    def finalize(self) -> Any:
        return self.curvas_trafos_bt


class VoltageProbe(SimulationProbe):
    """Sonda vetorizada que varre todas as barras do circuito para detectar limites máximos e mínimos."""
    
    def __init__(self):
        self.config: Optional[SimulationConfig] = None
        self.buses_fase: List[str] = []
        self.indices_fase: Optional[np.ndarray] = None
        self.num_nodes: int = 0
        self.v_min_arr: Optional[np.ndarray] = None
        self.step_min_arr: Optional[np.ndarray] = None
        self.v_max_arr: Optional[np.ndarray] = None
        self.step_max_arr: Optional[np.ndarray] = None

    def setup(self, circuit: CircuitManager, config: SimulationConfig) -> None:
        self.config = config
        node_names = dss.Circuit.AllNodeNames()
        self.indices_fase = np.array([idx for idx, name in enumerate(node_names) if not name.endswith('.0')], dtype=np.int32)
        self.buses_fase = [node_names[idx].split('.')[0] for idx in self.indices_fase]
        self.num_nodes = len(self.indices_fase)
        
        self.v_min_arr = np.full(self.num_nodes, 999.0, dtype=np.float32)
        self.step_min_arr = np.zeros(self.num_nodes, dtype=np.int16)
        self.v_max_arr = np.full(self.num_nodes, 0.0, dtype=np.float32)
        self.step_max_arr = np.zeros(self.num_nodes, dtype=np.int16)

    def on_step(self, passo: int, hora_str: str) -> None:
        if self.num_nodes == 0: return
        mags = np.array(dss.Circuit.AllBusMagPu(), dtype=np.float32)[self.indices_fase]
        valid_mask = mags > 0.50

        mask_min = (mags < self.v_min_arr) & valid_mask
        self.v_min_arr[mask_min] = mags[mask_min]
        self.step_min_arr[mask_min] = passo

        mask_max = (mags > self.v_max_arr) & valid_mask
        self.v_max_arr[mask_max] = mags[mask_max]
        self.step_max_arr[mask_max] = passo

    def _converter_passo_para_hora(self, passo: int) -> str:
        if passo <= 0: return "--:--"
        minutos = passo * self.config.passo_minutos
        h = (minutos // 60) % 24
        m = minutos % 60
        return f"{h:02d}:{m:02d}" if minutos < 24 * 60 else "24:00"

    def finalize(self) -> Optional[pd.DataFrame]:
        if self.num_nodes == 0: return None
        
        df_nodes = pd.DataFrame({
            'barra': self.buses_fase,
            'v_min': self.v_min_arr,
            'passo_min': self.step_min_arr,
            'v_max': self.v_max_arr,
            'passo_max': self.step_max_arr
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

        conditions = [sub & sob, sub & ~sob, ~sub & sob]
        choices = ['AMBAS', 'SUBTENSAO', 'SOBRETENSAO']
        df_barras['classificacao'] = np.select(conditions, choices, default='ADEQUADA')

        return df_barras[[
            'barra', 'v_min_pu', 'hora_v_min', 'v_max_pu', 'hora_v_max',
            'delta_v_pu', 'subtensao', 'sobretensao', 'classificacao'
        ]]
