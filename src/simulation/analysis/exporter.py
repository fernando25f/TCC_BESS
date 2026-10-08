import pandas as pd
import numpy as np
from typing import Dict
from src.simulation.core.engine import ScenarioResult
from src.simulation.core.circuit import CircuitManager
from src.simulation.config import SimulationConfig
from src.simulation.analysis.metrics import MetricsAnalyzer
from src.simulation.analysis.topology_debugger import TopologyDebugger

class ReportExporter:
    """Exportação das tabelas de resultados em formato CSV."""

    @staticmethod
    def exportar_relatorio_violacoes_tensao(res_padrao: ScenarioResult, config: SimulationConfig) -> None:
        """Exporta relatório de violações de tensão por barra para o caso padrão."""
        if res_padrao.dados_tensao_barras is None or res_padrao.dados_tensao_barras.empty:
            return

        df_barras = res_padrao.dados_tensao_barras
        df_violadas = df_barras[df_barras['classificacao'] != 'ADEQUADA'].copy()

        # Prioriza barras com problemas em ambos os limites (gangorra de tensão), seguida por pior subtensão
        ordem_severidade = {'AMBAS': 0, 'SUBTENSAO': 1, 'SOBRETENSAO': 2}
        df_violadas['prioridade'] = df_violadas['classificacao'].map(ordem_severidade)
        df_violadas = df_violadas.sort_values(by=['prioridade', 'v_min_pu', 'v_max_pu'], ascending=[True, True, False])
        df_violadas = df_violadas.drop(columns=['prioridade'])

        arq_saida = config.obter_caminho_saida(config.pasta_log_relatorios, "violacoes_tensao_barras_padrao", "csv")
        df_violadas.to_csv(arq_saida, index=False, sep=';', encoding='utf-8')

        n_ambas = (df_violadas['classificacao'] == 'AMBAS').sum()
        n_sub = (df_violadas['classificacao'] == 'SUBTENSAO').sum()
        n_sob = (df_violadas['classificacao'] == 'SOBRETENSAO').sum()
        n_total = len(df_violadas)

        print(f"  [OK] Relatório de violações de tensão salvo: {config.relpath(arq_saida)}")
        print(f"    Total de barras violadas (caso padrão): {n_total} (AMBAS: {n_ambas}, SUBTENSÃO: {n_sub}, SOBRETENSÃO: {n_sob})")

    @staticmethod
    def exportar_relatorios(resultados: Dict[str, ScenarioResult], circuit: CircuitManager, config: SimulationConfig) -> None:
        df_cenarios = MetricsAnalyzer.gerar_tabela_resumo_cenarios(resultados)
        arq_cenarios = config.obter_caminho_saida(config.pasta_log_relatorios, "resumo_cenarios", "csv")
        df_cenarios.to_csv(arq_cenarios, index=False, sep=';', encoding='utf-8')
        print(f"\n  [OK] Relatório salvo: {config.relpath(arq_cenarios)}")

        df_trafos = MetricsAnalyzer.gerar_tabela_trafos_at(resultados, circuit)
        arq_trafos = config.obter_caminho_saida(config.pasta_log_relatorios, "trafos_at", "csv")
        df_trafos.to_csv(arq_trafos, index=False, sep=';', encoding='utf-8')
        print(f"  [OK] Relatório salvo: {config.relpath(arq_trafos)}")

        df_ctmt = MetricsAnalyzer.gerar_tabela_ctmt(resultados, circuit)
        arq_ctmt = config.obter_caminho_saida(config.pasta_log_relatorios, "alimentadores_ctmt", "csv")
        df_ctmt.to_csv(arq_ctmt, index=False, sep=';', encoding='utf-8')
        print(f"  [OK] Relatório salvo: {config.relpath(arq_ctmt)} ({len(circuit.dict_ctmt_info)} alimentadores)")

        if 'padrao' in resultados and resultados['padrao'].dados_tensao_barras is not None:
            ReportExporter.exportar_relatorio_violacoes_tensao(resultados['padrao'], config)
            TopologyDebugger.analisar_e_exportar(resultados['padrao'], circuit, config)

        if 'com_gd' in resultados and config.sobrecarga_solar_ativa:
            ReportExporter.exportar_relatorio_dimensionamento_bess(resultados, circuit, config)

    @staticmethod
    def exportar_relatorio_dimensionamento_bess(resultados: Dict[str, ScenarioResult], circuit: CircuitManager, config: SimulationConfig) -> None:
        """Exporta relatório com os parâmetros quantitativos para o dimensionamento do BESS."""
        res_gd = resultados.get('com_gd')
        res_padrao = resultados.get('padrao')
        if not res_gd or not res_padrao:
            return

        info_sb = res_gd.info_sobrecarga or {}
        cod_alvo = info_sb.get('cod_alimentador')
        if not cod_alvo:
            cod_alvo, _ = circuit.resolver_alimentador(config.alimentador_alvo)

        info_ctmt = circuit.dict_ctmt_info.get(cod_alvo, {})
        nome_alvo = info_ctmt.get('nome', f'CTMT_{cod_alvo}')

        curva_padrao = res_padrao.dados_ctmt.get(cod_alvo).curva_p_kw if res_padrao.dados_ctmt.get(cod_alvo) else []
        curva_gd = res_gd.dados_ctmt.get(cod_alvo).curva_p_kw if res_gd.dados_ctmt.get(cod_alvo) else []
        if curva_gd:
            p_rev_max_kw = max(0.0, -min(curva_gd)) if curva_gd else 0.0
            e_rev_kwh = sum(-p * 0.25 for p in curva_gd if p < 0)

            p_rev_max_mw = p_rev_max_kw / 1000.0
            e_rev_mwh = e_rev_kwh / 1000.0

            p_max_padrao_mw = max(curva_padrao) / 1000.0 if curva_padrao else 0.0
            p_max_gd_mw = max(curva_gd) / 1000.0 if curva_gd else 0.0

            p_bess_mw = p_rev_max_mw * 1.05
            e_bess_mwh = e_rev_mwh
            duracao_h = (e_bess_mwh / p_bess_mw) if p_bess_mw > 0 else 0.0

            df_bess = pd.DataFrame([{
                'Alimentador_Alvo': cod_alvo,
                'Nome_Alimentador': nome_alvo,
                'Modo_Sobrecarga': info_sb.get('modo', config.modo_sobrecarga),
                'Potencia_Solar_Extra_Instalada_MW': round(info_sb.get('potencia_total_extra_kw', 0.0) / 1000.0, 2),
                'Pico_Demanda_Padrao_MW': round(p_max_padrao_mw, 2),
                'Pico_Demanda_Com_GD_MW': round(p_max_gd_mw, 2),
                'Pico_Fluxo_Reverso_Disjuntor_MW': round(p_rev_max_mw, 2),
                'Energia_Excedente_Reversa_MWh': round(e_rev_mwh, 2),
                'BESS_Potencia_Inversor_PCS_MW': round(p_bess_mw, 2),
                'BESS_Capacidade_Armazenamento_MWh': round(e_bess_mwh, 2),
                'BESS_Autonomia_Nominal_h': round(duracao_h, 2)
            }])

            arq_bess = config.obter_caminho_saida(config.pasta_log_relatorios, "dimensionamento_bess_estresse", "csv")
            df_bess.to_csv(arq_bess, index=False, sep=';', encoding='utf-8')
            print(f"  [OK] Relatório de Dimensionamento BESS salvo: {config.relpath(arq_bess)}")

        # Relatório de BESS para Transformadores de Distribuição (quando houver trafos monitorados na BT)
        if res_gd.curvas_trafos_bt:
            linhas_bt = []
            for t_nome, dados_gd in res_gd.curvas_trafos_bt.items():
                dados_padrao = res_padrao.curvas_trafos_bt.get(t_nome, {})
                p_gd_kw = np.array(dados_gd.get('curva_p_kw', []))
                v_gd_pu = np.array(dados_gd.get('curva_v_pu', []))
                p_padrao_kw = np.array(dados_padrao.get('curva_p_kw', []))

                if len(p_gd_kw) == 0:
                    continue

                kva_nom = dados_gd.get('kva_nom', 112.0)
                barra_bt = dados_gd.get('barra_bt', '')
                p_rev_max = max(0.0, -float(np.min(p_gd_kw)))
                e_rev = sum(-p * 0.25 for p in p_gd_kw if p < 0)
                p_bess_bt = p_rev_max * 1.05
                e_bess_bt = e_rev
                dur_h = (e_bess_bt / p_bess_bt) if p_bess_bt > 0 else 0.0

                p_max_pad = float(np.max(p_padrao_kw)) if len(p_padrao_kw) else 0.0
                v_max_bt = float(np.max(v_gd_pu)) if len(v_gd_pu) else 1.0
                v_min_bt = float(np.min(v_gd_pu)) if len(v_gd_pu) else 1.0

                linhas_bt.append({
                    'Trafo_MT_BT': t_nome,
                    'Alimentador': cod_alvo,
                    'Potencia_Nominal_kVA': round(kva_nom, 1),
                    'Barra_BT': barra_bt,
                    'Pico_Demanda_Padrao_kW': round(p_max_pad, 2),
                    'Pico_Fluxo_Reverso_kW': round(p_rev_max, 2),
                    'Energia_Excedente_Reversa_kWh': round(e_rev, 2),
                    'BESS_Inversor_Recomendado_kW': round(p_bess_bt, 2),
                    'BESS_Capacidade_Bateria_kWh': round(e_bess_bt, 2),
                    'BESS_Autonomia_h': round(dur_h, 2),
                    'V_Max_BT_pu': round(v_max_bt, 4),
                    'V_Min_BT_pu': round(v_min_bt, 4)
                })

            if linhas_bt:
                df_bt = pd.DataFrame(linhas_bt)
                arq_bt = config.obter_caminho_saida(config.pasta_log_relatorios, "dimensionamento_bess_trafos_bt", "csv")
                df_bt.to_csv(arq_bt, index=False, sep=';', encoding='utf-8')
                print(f"  [OK] Relatório BESS Trafos BT salvo: {config.relpath(arq_bt)} ({len(linhas_bt)} trafos)")
