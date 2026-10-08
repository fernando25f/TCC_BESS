import pandas as pd
from typing import Dict
from src.simulation.core.engine import ScenarioResult
from src.simulation.core.circuit import CircuitManager

class MetricsAnalyzer:
    """Calcula e formata métricas elétricas agregadas por cenário."""

    COLUNAS_CENARIOS = [
        'Cenário', 'Pico_SE_MW', 'Hora_Pico', 'Energia_Total_MWh',
        'Trafos_Sobrecarga', 'Convergência', 'Tempo_s'
    ]

    COLUNAS_TRAFOS_AT = [
        'Cenário', 'Trafo', 'Pot_Nom_MVA', 'P_Max_MW', 'S_Max_MVA',
        'Carreg_Pct', 'Hora_Pico', 'FP_Pico', 'V_Min_pu', 'V_Max_pu', 'Energia_MWh'
    ]

    COLUNAS_CTMT = [
        'Cenário', 'Cod_CTMT', 'Nome_Alimentador', 'Trafo_Origem',
        'P_Max_MW', 'S_Max_MVA', 'Hora_Pico', 'FP_Pico', 'V_Min_pu', 'V_Max_pu', 'Energia_MWh'
    ]

    @classmethod
    def gerar_tabela_resumo_cenarios(cls, resultados: Dict[str, ScenarioResult]) -> pd.DataFrame:
        linhas = []
        for c_nome, res in resultados.items():
            linhas.append({
                'Cenário': c_nome.upper(),
                'Pico_SE_MW': round(res.p_max_se_kw / 1000.0, 2),
                'Hora_Pico': res.hora_pico_se,
                'Energia_Total_MWh': round(res.energia_total_se_mwh, 2),
                'Trafos_Sobrecarga': len(res.trafos_sobrecarregados),
                'Convergência': "100% OK" if res.convergiu_todas else f"Falha ({len(res.passos_divergentes)}p)",
                'Tempo_s': round(res.tempo_segundos, 2)
            })
        return pd.DataFrame(linhas) if linhas else pd.DataFrame(columns=cls.COLUNAS_CENARIOS)

    @classmethod
    def gerar_tabela_trafos_at(cls, resultados: Dict[str, ScenarioResult], circuit: CircuitManager) -> pd.DataFrame:
        linhas = []
        for c_nome, res in resultados.items():
            for tr in circuit.trafos_subestacao:
                info = res.dados_trafos_at.get(tr)
                info_meta = circuit.trafos_subestacao_info.get(tr, {})
                pot_nom_mva = info_meta.get("pot_nom_mva", 50.0)
                s_max_mva = (info.s_max_kva / 1000.0) if info else 0.0
                carreg_pct = (s_max_mva / pot_nom_mva * 100.0) if pot_nom_mva > 0 else 0.0
                tr_short = tr.split('-')[-1] if '-' in tr else tr

                linhas.append({
                    'Cenário': c_nome.upper(),
                    'Trafo': tr_short,
                    'Pot_Nom_MVA': pot_nom_mva,
                    'P_Max_MW': round(info.p_max_kw / 1000.0, 2) if info else 0.0,
                    'S_Max_MVA': round(s_max_mva, 2),
                    'Carreg_Pct': round(carreg_pct, 1),
                    'Hora_Pico': info.hora_pico if info else '',
                    'FP_Pico': round(info.fp_pico, 3) if info else 1.0,
                    'V_Min_pu': round(info.v_min_pu, 3) if info else 1.0,
                    'V_Max_pu': round(info.v_max_pu, 3) if info else 1.0,
                    'Energia_MWh': round(info.energia_kwh / 1000.0, 2) if info else 0.0
                })
        return pd.DataFrame(linhas) if linhas else pd.DataFrame(columns=cls.COLUNAS_TRAFOS_AT)

    @classmethod
    def gerar_tabela_ctmt(cls, resultados: Dict[str, ScenarioResult], circuit: CircuitManager) -> pd.DataFrame:
        linhas = []
        for c_nome, res in resultados.items():
            for cod_id in circuit.dict_ctmt_info.keys():
                info = res.dados_ctmt.get(cod_id)
                info_ctmt = circuit.dict_ctmt_info.get(cod_id, {})
                trafo_origem = info_ctmt.get('trafo', '').split('-')[-1]

                linhas.append({
                    'Cenário': c_nome.upper(),
                    'Cod_CTMT': cod_id,
                    'Nome_Alimentador': info_ctmt.get('nome', cod_id),
                    'Trafo_Origem': trafo_origem,
                    'P_Max_MW': round(info.p_max_kw / 1000.0, 2) if info else 0.0,
                    'S_Max_MVA': round(info.s_max_kva / 1000.0, 2) if info else 0.0,
                    'Hora_Pico': info.hora_pico if info else '',
                    'FP_Pico': round(info.fp_pico, 3) if info else 1.0,
                    'V_Min_pu': round(info.v_min_pu, 3) if info else 1.0,
                    'V_Max_pu': round(info.v_max_pu, 3) if info else 1.0,
                    'Energia_MWh': round(info.energia_kwh / 1000.0, 2) if info else 0.0
                })
        return pd.DataFrame(linhas) if linhas else pd.DataFrame(columns=cls.COLUNAS_CTMT)
