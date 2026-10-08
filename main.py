"""
Ponto de entrada principal da simulação da Subestação Goiânia Leste no OpenDSS.
"""
import time
from src.simulation.config import SimulationConfig
from src.simulation.core.circuit import CircuitManager
from src.simulation.core.engine import SimulationEngine
from src.simulation.scenarios.base import Scenario
from src.simulation.scenarios.standard import DisableDistributedGenerationComponent
from src.simulation.scenarios.solar import EnableSolarGenerationComponent
from src.simulation.scenarios.solar_overload import SolarOverloadInjector
from src.simulation.visualization.plots import Plotter
from src.simulation.visualization.geo_map import GeoMapRenderer
from src.simulation.bess.sizing import BESSSizer
from src.simulation.scenarios.bess_deployment import BESSDeploymentComponent
from src.simulation.core.hooks.actuators import BESSRealTimeController
from src.simulation.analysis.exporter import ReportExporter

def main():
    t_inicio = time.time()

    # Escopo da Simulação:
    # - "SUBESTACAO" : Simula toda a subestação (4 trafos AT e 27 alimentadores)
    # - "TRAFO_AT"   : Simula 1 transformador AT isolado (ex: alvo="TR1", "TR2", "TR3", "TR4")
    # - "ALIMENTADOR": Simula 1 alimentador isolado (ex: alvo="5001996")
    config = SimulationConfig(
        escopo = "TRAFO_AT",
        alvo = "TR2",
        controle_tap_ativo = False,
        sobrecarga_solar_ativa = True,
        bess_ativo = True,
        bess_posicionamento = "BASE_ALIMENTADOR", # "BASE_ALIMENTADOR" ou "TRAFOS_SOBRECARREGADOS"
        modo_sobrecarga = "MT_FEEDER",
        alimentador_alvo = "5001996",
        fator_sobrecarga_alvo = 1.5
    )
    config.criar_pastas_saida()
    circuit = CircuitManager(config)
    engine = SimulationEngine(circuit, config)

    # Cenário Padrão
    cenario_padrao = Scenario("padrao", components=[
        DisableDistributedGenerationComponent()
    ])

    # Cenário com GD
    componentes_gd = [EnableSolarGenerationComponent(config)]
    if config.sobrecarga_solar_ativa:
        componentes_gd.append(SolarOverloadInjector(config))
    cenario_gd = Scenario("com_gd", components=componentes_gd)

    res_padrao = engine.run_scenario(cenario_padrao)
    res_gd = engine.run_scenario(cenario_gd)

    resultados = {
        'padrao': res_padrao,
        'com_gd': res_gd
    }

    # Cenário com BESS (Se ativado)
    if config.bess_ativo:
        print("\n[MAIN] Dimensionando BESS a partir dos resultados com GD...")
        comandos_dss, regras_bess = BESSSizer.dimensionar(res_gd, config, circuit)
        
        # O BESS precisa operar numa rede COM GD e COM a sobrecarga ativa
        componentes_bess = [
            EnableSolarGenerationComponent(config)
        ]
        if config.sobrecarga_solar_ativa:
            componentes_bess.append(SolarOverloadInjector(config))
            
        componentes_bess.append(BESSDeploymentComponent(comandos_dss))
        
        actuators = [BESSRealTimeController(regras_bess)]
        
        cenario_bess = Scenario("com_bess", components=componentes_bess, actuators=actuators)
        res_bess = engine.run_scenario(cenario_bess)
        
        resultados['com_bess'] = res_bess

    ReportExporter.exportar_relatorios(resultados, circuit, config)

    Plotter.plot_subestacao(resultados, config)
    Plotter.plot_trafos_at(resultados, circuit, config)
    if config.sobrecarga_solar_ativa:
        Plotter.plot_estresse_alimentador(resultados, circuit, config)
        Plotter.plot_trafos_distribuicao_sobrecarga(resultados, circuit, config)
    GeoMapRenderer.renderizar_mapa(config)

    tempo_total = time.time() - t_inicio
    print(f"\nTEMPO TOTAL DE EXECUÇÃO: {int(tempo_total // 60)}m {tempo_total % 60:.2f}s\n")

if __name__ == "__main__":
    main()
