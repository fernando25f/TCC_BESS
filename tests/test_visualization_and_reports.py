import os
import unittest
import tempfile
import shutil
import pandas as pd
from typing import Dict, Any

from src.simulation.config import SimulationConfig
from src.simulation.core.engine import ScenarioResult
from src.simulation.core.circuit import CircuitManager
from src.simulation.visualization.plots import Plotter
from src.simulation.visualization.geo_map import GeoMapRenderer
from src.simulation.analysis.exporter import ReportExporter
from src.simulation.analysis.metrics import MetricsAnalyzer

class TestVisualizationAndReports(unittest.TestCase):
    """Bateria de testes unitários para os módulos de visualização gráfica e exportação de relatórios."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.config = SimulationConfig(
            diretorio_raiz=self.temp_dir,
            escopo="SUBESTACAO",
            passos_simulacao=96,
            passo_minutos=15
        )

        # Mock de CircuitManager com dados mínimos de trafos e alimentadores
        self.circuit = CircuitManager.__new__(CircuitManager)
        self.circuit.config = self.config
        self.circuit.trafos_subestacao = ["GOL-S-TRF-TR1", "GOL-S-TRF-TR2"]
        self.circuit.trafos_subestacao_info = {
            "GOL-S-TRF-TR1": {"pot_nom_mva": 50.0, "barra_secundaria": "SEC_TR1"},
            "GOL-S-TRF-TR2": {"pot_nom_mva": 50.0, "barra_secundaria": "SEC_TR2"}
        }
        self.circuit.trafo_sec_bus = {
            "GOL-S-TRF-TR1": "SEC_TR1",
            "GOL-S-TRF-TR2": "SEC_TR2"
        }
        self.circuit.dict_ctmt_info = {
            "5001996": {"nome": "GOIANIA LESTE-17", "trafo": "GOL-S-TRF-TR1"},
            "5001997": {"nome": "GOIANIA LESTE-18", "trafo": "GOL-S-TRF-TR2"}
        }
        self.circuit.todos_ctmt_info = self.circuit.dict_ctmt_info

        # Criação de resultados sintéticos para 96 passos
        curva_padrao_se = [20000.0 + i * 100.0 for i in range(96)]
        curva_gd_se = [15000.0 - i * 50.0 for i in range(96)]

        curva_tr1_p_padrao = [10000.0 + i * 50.0 for i in range(96)]
        curva_tr1_p_gd = [8000.0 - i * 30.0 for i in range(96)]
        curva_tr2_p_padrao = [10000.0 + i * 50.0 for i in range(96)]
        curva_tr2_p_gd = [7000.0 - i * 20.0 for i in range(96)]

        curva_tr1_v = [1.02 - 0.0002 * i for i in range(96)]
        curva_tr2_v = [1.01 - 0.0001 * i for i in range(96)]

        curva_ctmt_padrao = [2500.0] * 96
        # Simula fluxo reverso solar (potência negativa de 10:00 às 15:00)
        curva_ctmt_gd = [2500.0 if (i < 40 or i > 60) else -1800.0 for i in range(96)]

        df_tensoes = pd.DataFrame([
            {'barra': 'B_001', 'v_min_pu': 0.91, 'v_max_pu': 1.02, 'hora_v_min': '19:30', 'classificacao': 'SUBTENSAO', 'subtensao': True, 'sobretensao': False},
            {'barra': 'B_002', 'v_min_pu': 0.98, 'v_max_pu': 1.07, 'hora_v_min': '12:15', 'classificacao': 'SOBRETENSAO', 'subtensao': False, 'sobretensao': True},
            {'barra': 'B_003', 'v_min_pu': 0.99, 'v_max_pu': 1.03, 'hora_v_min': '14:00', 'classificacao': 'ADEQUADA', 'subtensao': False, 'sobretensao': False}
        ])

        self.res_padrao = ScenarioResult(
            nome_cenario="padrao",
            curva_subestacao_kw=curva_padrao_se,
            perfil_p_trafos_at={"GOL-S-TRF-TR1": curva_tr1_p_padrao, "GOL-S-TRF-TR2": curva_tr2_p_padrao},
            perfil_v_trafos_at={"GOL-S-TRF-TR1": curva_tr1_v, "GOL-S-TRF-TR2": curva_tr2_v},
            dados_trafos_at={
                "GOL-S-TRF-TR1": {"p_max_kw": 14750.0, "s_max_kva": 15500.0, "hora_pico": "20:00", "fp_pico": 0.95, "v_min_pu": 0.98, "v_max_pu": 1.02, "energia_kwh": 250000.0},
                "GOL-S-TRF-TR2": {"p_max_kw": 14750.0, "s_max_kva": 15500.0, "hora_pico": "20:00", "fp_pico": 0.95, "v_min_pu": 0.98, "v_max_pu": 1.02, "energia_kwh": 250000.0}
            },
            dados_ctmt={
                "5001996": {"curva_p_kw": curva_ctmt_padrao, "p_max_kw": 2500.0, "s_max_kva": 2600.0, "hora_pico": "20:00", "fp_pico": 0.95, "v_min_pu": 0.95, "v_max_pu": 1.02, "energia_kwh": 60000.0},
                "5001997": {"curva_p_kw": curva_ctmt_padrao, "p_max_kw": 2500.0, "s_max_kva": 2600.0, "hora_pico": "20:00", "fp_pico": 0.95, "v_min_pu": 0.95, "v_max_pu": 1.02, "energia_kwh": 60000.0}
            },
            p_max_se_kw=29500.0,
            hora_pico_se="20:00",
            energia_total_se_mwh=500.0,
            trafos_sobrecarregados=set(),
            registros_sobrecarga=[],
            convergiu_todas=True,
            passos_divergentes=[],
            tempo_segundos=1.25,
            dados_tensao_barras=df_tensoes,
            curvas_trafos_bt={
                "TR_BT_01": {
                    "curva_p_kw": [50.0] * 96,
                    "curva_v_pu": [1.0] * 96,
                    "kva_nom": 112.5,
                    "barra_bt": "BT_BAR_1"
                }
            }
        )

        self.res_gd = ScenarioResult(
            nome_cenario="com_gd",
            curva_subestacao_kw=curva_gd_se,
            perfil_p_trafos_at={"GOL-S-TRF-TR1": curva_tr1_p_gd, "GOL-S-TRF-TR2": curva_tr2_p_gd},
            perfil_v_trafos_at={"GOL-S-TRF-TR1": curva_tr1_v, "GOL-S-TRF-TR2": curva_tr2_v},
            dados_trafos_at={
                "GOL-S-TRF-TR1": {"p_max_kw": 12000.0, "s_max_kva": 12500.0, "hora_pico": "19:30", "fp_pico": 0.96, "v_min_pu": 0.99, "v_max_pu": 1.03, "energia_kwh": 200000.0},
                "GOL-S-TRF-TR2": {"p_max_kw": 11000.0, "s_max_kva": 11500.0, "hora_pico": "19:30", "fp_pico": 0.96, "v_min_pu": 0.99, "v_max_pu": 1.03, "energia_kwh": 190000.0}
            },
            dados_ctmt={
                "5001996": {"curva_p_kw": curva_ctmt_gd, "p_max_kw": 2500.0, "s_max_kva": 2600.0, "hora_pico": "19:30", "fp_pico": 0.95, "v_min_pu": 0.96, "v_max_pu": 1.05, "energia_kwh": 40000.0},
                "5001997": {"curva_p_kw": curva_ctmt_padrao, "p_max_kw": 2500.0, "s_max_kva": 2600.0, "hora_pico": "19:30", "fp_pico": 0.95, "v_min_pu": 0.96, "v_max_pu": 1.05, "energia_kwh": 55000.0}
            },
            p_max_se_kw=23000.0,
            hora_pico_se="19:30",
            energia_total_se_mwh=390.0,
            trafos_sobrecarregados=set(),
            registros_sobrecarga=[],
            convergiu_todas=True,
            passos_divergentes=[],
            tempo_segundos=1.15,
            info_sobrecarga={
                "cod_alimentador": "5001996",
                "modo": "BT_DISTRIBUTION",
                "potencia_total_extra_kw": 3500.0
            },
            curvas_trafos_bt={
                "TR_BT_01": {
                    "curva_p_kw": [50.0 if (i < 40 or i > 60) else -85.0 for i in range(96)],
                    "curva_v_pu": [1.00 if (i < 40 or i > 60) else 1.06 for i in range(96)],
                    "kva_nom": 112.5,
                    "barra_bt": "BT_BAR_1"
                }
            }
        )

        self.resultados = {
            'padrao': self.res_padrao,
            'com_gd': self.res_gd
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_plot_subestacao(self) -> None:
        """Valida geração do gráfico SVG de demanda agregada da subestação."""
        Plotter.plot_subestacao(self.resultados, self.config)
        arq_saida = os.path.join(self.config.pasta_graf_subestacao, "demanda_subestacao_24h.svg")
        self.assertTrue(os.path.exists(arq_saida), "Arquivo SVG da subestação não foi criado.")
        self.assertGreater(os.path.getsize(arq_saida), 1000)

    def test_plot_trafos_at_comparativo(self) -> None:
        """Garante que plot_trafos_at funciona com ambos os cenários sem NameError."""
        Plotter.plot_trafos_at(self.resultados, self.circuit, self.config)
        arq_mw = os.path.join(self.config.pasta_graf_subestacao, "carregamento_trafos_24h.svg")
        arq_v = os.path.join(self.config.pasta_graf_subestacao, "tensao_trafos_24h.svg")
        self.assertTrue(os.path.exists(arq_mw), "Gráfico MW dos trafos AT não foi gerado.")
        self.assertTrue(os.path.exists(arq_v), "Gráfico V dos trafos AT não foi gerado.")

    def test_plot_trafos_at_cenario_unico(self) -> None:
        """Garante que plot_trafos_at funciona com apenas um cenário presente no dicionário."""
        apenas_padrao = {'padrao': self.res_padrao}
        Plotter.plot_trafos_at(apenas_padrao, self.circuit, self.config)

        apenas_gd = {'com_gd': self.res_gd}
        Plotter.plot_trafos_at(apenas_gd, self.circuit, self.config)

    def test_plot_trafos_at_sem_trafos(self) -> None:
        """Garante retorno gracioso e sem exceções quando a lista de trafos da SE for vazia."""
        self.circuit.trafos_subestacao = []
        Plotter.plot_trafos_at(self.resultados, self.circuit, self.config)

    def test_plot_estresse_alimentador(self) -> None:
        """Valida gráfico de fluxo reverso e janelas de carga/descarga do BESS."""
        Plotter.plot_estresse_alimentador(self.resultados, self.circuit, self.config)
        arq_estresse = os.path.join(self.config.pasta_graf_subestacao, "perfil_estresse_alimentador_24h.svg")
        self.assertTrue(os.path.exists(arq_estresse), "Gráfico de estresse do alimentador não foi gerado.")

    def test_plot_trafos_distribuicao_sobrecarga(self) -> None:
        """Valida gráfico de potência e tensão de trafos de distribuição BT."""
        Plotter.plot_trafos_distribuicao_sobrecarga(self.resultados, self.circuit, self.config)
        arq_bt = os.path.join(self.config.pasta_graf_trafo_dist, "estresse_tr_bt_01_24h.svg")
        self.assertTrue(os.path.exists(arq_bt), "Gráfico de estresse do trafo BT não foi gerado.")

    def test_tolerancia_a_tamanhos_discrepantes_de_curva(self) -> None:
        """Garante que vetores com comprimentos menores que 96 não quebrem a plotagem."""
        res_curto = ScenarioResult(
            nome_cenario="padrao",
            curva_subestacao_kw=[100.0] * 50,  # 50 passos em vez de 96
            perfil_p_trafos_at={"GOL-S-TRF-TR1": [50.0] * 50},
            perfil_v_trafos_at={"GOL-S-TRF-TR1": [1.0] * 50},
            dados_trafos_at={},
            dados_ctmt={"5001996": {"curva_p_kw": [20.0] * 50}},
            p_max_se_kw=100.0,
            hora_pico_se="12:00",
            energia_total_se_mwh=1.0,
            trafos_sobrecarregados=set(),
            registros_sobrecarga=[],
            convergiu_todas=True,
            passos_divergentes=[],
            tempo_segundos=0.1
        )
        resultados_curtos = {'padrao': res_curto}
        Plotter.plot_subestacao(resultados_curtos, self.config)
        Plotter.plot_trafos_at(resultados_curtos, self.circuit, self.config)

    def test_exportar_relatorios_csv(self) -> None:
        """Garante que ReportExporter gera todos os relatórios CSV corretamente."""
        ReportExporter.exportar_relatorios(self.resultados, self.circuit, self.config)

        arq_cenarios = os.path.join(self.config.pasta_log_relatorios, "resumo_cenarios.csv")
        arq_trafos = os.path.join(self.config.pasta_log_relatorios, "trafos_at.csv")
        arq_ctmt = os.path.join(self.config.pasta_log_relatorios, "alimentadores_ctmt", ".csv") if False else os.path.join(self.config.pasta_log_relatorios, "alimentadores_ctmt.csv")
        arq_bess = os.path.join(self.config.pasta_log_relatorios, "dimensionamento_bess_estresse.csv")
        arq_bess_bt = os.path.join(self.config.pasta_log_relatorios, "dimensionamento_bess_trafos_bt.csv")
        arq_violacoes = os.path.join(self.config.pasta_log_relatorios, "violacoes_tensao_barras_padrao.csv")

        self.assertTrue(os.path.exists(arq_cenarios), "Relatório resumo_cenarios.csv não gerado.")
        self.assertTrue(os.path.exists(arq_trafos), "Relatório trafos_at.csv não gerado.")
        self.assertTrue(os.path.exists(arq_ctmt), "Relatório alimentadores_ctmt.csv não gerado.")
        self.assertTrue(os.path.exists(arq_bess), "Relatório dimensionamento_bess_estresse.csv não gerado.")
        self.assertTrue(os.path.exists(arq_bess_bt), "Relatório dimensionamento_bess_trafos_bt.csv não gerado.")
        self.assertTrue(os.path.exists(arq_violacoes), "Relatório violacoes_tensao_barras_padrao.csv não gerado.")

        # Valida que o BESS calculou potência e capacidade coerentes com o fluxo reverso
        df_bess = pd.read_csv(arq_bess, sep=';')
        self.assertEqual(df_bess.iloc[0]['Alimentador_Alvo'], 5001996)
        self.assertGreater(df_bess.iloc[0]['Pico_Fluxo_Reverso_Disjuntor_MW'], 1.0)
        self.assertGreater(df_bess.iloc[0]['BESS_Capacidade_Armazenamento_MWh'], 0.0)

    def test_metrics_analyzer_tabelas_vazias(self) -> None:
        """Garante esquema consistente mesmo para entradas vazias."""
        df_cen = MetricsAnalyzer.gerar_tabela_resumo_cenarios({})
        self.assertListEqual(list(df_cen.columns), MetricsAnalyzer.COLUNAS_CENARIOS)

        self.circuit.trafos_subestacao = []
        df_tr = MetricsAnalyzer.gerar_tabela_trafos_at({}, self.circuit)
        self.assertListEqual(list(df_tr.columns), MetricsAnalyzer.COLUNAS_TRAFOS_AT)

        self.circuit.dict_ctmt_info = {}
        df_ct = MetricsAnalyzer.gerar_tabela_ctmt({}, self.circuit)
        self.assertListEqual(list(df_ct.columns), MetricsAnalyzer.COLUNAS_CTMT)

    def test_geomap_renderer(self) -> None:
        """Valida que GeoMapRenderer processa arquivos DSS com SetBusXY no final e gera o PNG."""
        pasta_tr = os.path.join(self.config.pasta_modelo, "TR1")
        os.makedirs(pasta_tr, exist_ok=True)
        arq_dss = os.path.join(pasta_tr, "CTMT_5001996.dss")
        with open(arq_dss, "w", encoding="utf-8") as f:
            f.write("! 2. Linhas de Media Tensao (MT)\n")
            f.write("new line.L1 phases=3 bus1=B1.1.2.3 bus2=B2.1.2.3 r1=0.1 x1=0.2 length=1.0\n")
            f.write("! 6. Linhas de Baixa Tensao (BT)\n")
            f.write("new line.L2 phases=3 bus1=B2.1.2.3 bus2=B3.1.2.3 r1=0.5 x1=0.4 length=0.5\n")
            f.write("! 9. Coordenadas dos Barramentos\n")
            f.write("SetBusXY Bus=B1 X=-49.25 Y=-16.68\n")
            f.write("SetBusXY Bus=B2 X=-49.24 Y=-16.67\n")
            f.write("SetBusXY Bus=B3 X=-49.23 Y=-16.66\n")

        self.config.alvo = "TR1"
        self.config.escopo = "TRAFO_AT"
        GeoMapRenderer.renderizar_mapa(self.config)

        mapa_png = os.path.join(self.config.pasta_graf_mapa_rede, "mapa_rede_trafo_at_tr1.png")
        self.assertTrue(os.path.exists(mapa_png), "Arquivo PNG do mapa geográfico não foi gerado.")

if __name__ == "__main__":
    unittest.main()
