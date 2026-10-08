import opendssdirect as dss
from typing import Dict, Any, Tuple, List
from src.simulation.core.engine import ScenarioResult
from src.simulation.core.circuit import CircuitManager
from src.simulation.config import SimulationConfig

class BESSSizer:
    """
    Analisa os resultados da rede estressada (Sem BESS) e dimensiona
    algoritmicamente os BESSs necessários (kW, kWh).
    Retorna os comandos DSS de injeção e o dicionário de regras de controle.
    """
    
    @classmethod
    def dimensionar(cls, res_gd: ScenarioResult, config: SimulationConfig, circuit: CircuitManager) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
        comandos_dss = []
        regras_bess = {}
        
        if config.bess_posicionamento == "BASE_ALIMENTADOR":
            # Dimensiona para a subestação global
            p_min_se = min(res_gd.curva_subestacao_kw) # Valor negativo alto (ex: -1995 kW)
            p_max_se = max(res_gd.curva_subestacao_kw)
            
            # Limite Reverso será 0 (não permite exportação para AT) ou configurável. Vamos usar 0 para garantir absorção total.
            lim_reverso = 0.0
            
            if p_min_se < lim_reverso:
                excesso_kw = abs(p_min_se - lim_reverso)
                # Adiciona margem de 20%
                kw_inversor = round(excesso_kw * 1.2, 0)
                
                # Para calcular kWh, idealmente integrar a área sob a curva negativa.
                # Simplificação agressiva: assumir que o pico dura equivalente a 4 horas plenas.
                kwh_capacidade = round(kw_inversor * 4.0, 0)
                
                # Extrair alimentador alvo para conectar o BESS no tronco
                info_sb = res_gd.info_sobrecarga or {}
                cod_alvo = info_sb.get('cod_alimentador')
                if not cod_alvo:
                    cod_alvo, _ = circuit.resolver_alimentador(config.alimentador_alvo)
                
                info_ctmt = circuit.dict_ctmt_info.get(cod_alvo, {})
                bus_alvo = info_ctmt.get('pac_ini')
                linha_tronco = info_ctmt.get('arquivo_dss', '').replace('.dss', '').split('/')[-1]
                
                if not bus_alvo:
                    bus_alvo = config.barra_slack
                    kv_base = config.kv_slack
                    nome_bess = "BESS_SE"
                else:
                    nome_bess = f"BESS_CTMT_{cod_alvo}"
                    kv_base = 13.8 # Pode ser ajustado conforme a rede real
                
                elemento_monitor = "Vsource.source"
                
                comandos_dss.append(
                    f"New Storage.{nome_bess} Bus1={bus_alvo} kV={kv_base} kWrated={kw_inversor} kWhrated={kwh_capacidade} state=IDLING"
                )
                
                regras_bess[nome_bess] = {
                    "monitor": elemento_monitor,
                    "limite_reverso_kw": lim_reverso,
                    "limite_pico_kw": p_max_se * 0.9, # Peak shaving de 10% do pico maximo
                    "kw_rated": kw_inversor
                }
        
        elif config.bess_posicionamento == "TRAFOS_SOBRECARREGADOS":
            # Distribui BESS nos trafos de distribuição que tiveram sobrecarga
            # Precisamos extrair da rede quais trafos sofreram.
            # (A implementação exata depende de como res_gd mapeia os trafos)
            # Para manter simples, iteramos sobre os sobrecarregados mapeados.
            for nome_trafo in res_gd.trafos_sobrecarregados:
                # Usa propriedades fixas genéricas para cada trafo BT sobrecarregado (Simplificação inicial)
                dss.Circuit.SetActiveElement(f"Transformer.{nome_trafo}")
                kv_base = dss.CktElement.BusNames()[0].split(".")[0] # Simplificação
                # Obter kVA do trafo seria ideal. Vamos fixar um valor protótipo:
                kw_inversor = 100.0
                kwh_capacidade = 400.0
                
                bus_alvo = dss.CktElement.BusNames()[0]
                
                nome_bess = f"BESS_{nome_trafo}"
                comandos_dss.append(
                    f"New Storage.{nome_bess} Bus1={bus_alvo} kV=13.8 kWrated={kw_inversor} kWhrated={kwh_capacidade} state=IDLING"
                )
                
                regras_bess[nome_bess] = {
                    "monitor": f"Transformer.{nome_trafo}",
                    "limite_reverso_kw": -10.0,
                    "limite_pico_kw": 112.5, # Ex: Trafo de 112.5 kVA
                    "kw_rated": kw_inversor
                }
                
        return comandos_dss, regras_bess
