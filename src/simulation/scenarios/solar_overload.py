from __future__ import annotations
from typing import Dict, List, Tuple, Any
import opendssdirect as dss

from src.simulation.config import SimulationConfig
from src.simulation.core.circuit import CircuitManager
from src.simulation.scenarios.base import ScenarioComponent

class SolarOverloadInjector(ScenarioComponent):
    """Injeta usinas solares adicionais para provocar sobrecarga e fluxo reverso controlados."""

    def __init__(self, config: SimulationConfig) -> None:
        self.config: SimulationConfig = config

    def identificar_alimentador_alvo(self, circuit: CircuitManager) -> Tuple[str, str]:
        """Identifica o alimentador alvo a partir da variável configurada (aceita código ou nome)."""
        return circuit.resolver_alimentador(self.config.alimentador_alvo)

    @classmethod
    def obter_trafos_alvo_bt(cls, circuit: CircuitManager, config: SimulationConfig) -> List[Tuple[str, float, str]]:
        """
        Retorna a lista de tuplas (t_nome, kva_nom, barra_bt) dos trafos que receberão sobrecarga em BT.
        Permite ao engine monitorar suas curvas 24h tanto no caso PADRAO quanto no COM_GD.
        """
        if not config.sobrecarga_solar_ativa or config.modo_sobrecarga.upper() not in ["BT_DISTRIBUTION", "HYBRID"]:
            return []

        cod_alvo, _ = circuit.resolver_alimentador(config.alimentador_alvo)
        trafos_alimentador = list(circuit.obter_trafos_do_alimentador(cod_alvo))

        if config.trafo_alvo:
            alvo_tr = config.trafo_alvo.lower()
            return [t for t in trafos_alimentador if alvo_tr in t[0].lower()]

        trafos_alimentador.sort(key=lambda x: x[1], reverse=True)
        return trafos_alimentador[:4]

    def aplicar(self, circuit: CircuitManager) -> Dict[str, Any]:
        """Aplica as usinas solares adicionais conforme o modo de sobrecarga configurado."""
        cod_alvo, nome_alvo = self.identificar_alimentador_alvo(circuit)
        modo = self.config.modo_sobrecarga.upper()

        sufixo = "_PicoUnitario" if self.config.tipo_curva_gd == "PicoUnitario" else ""
        nome_curva = f"Curva_Solar_{self.config.mes_solar}{sufixo}"

        dss.Command("MakeBusList")
        all_buses = dss.Circuit.AllBusNames()
        feeder_buses = [b for b in all_buses if b.endswith(cod_alvo)]

        # Consulta em tempo O(1) dos transformadores associados a este alimentador
        trafos_alimentador = circuit.obter_trafos_do_alimentador(cod_alvo)
        cap_trafos_feeder_kva = sum(t[1] for t in trafos_alimentador) if trafos_alimentador else 14000.0

        plantas_injetadas: List[Dict[str, Any]] = []
        pot_total_kw = 0.0

        print(f"\n  [SOBRECARGA SOLAR] Injetando usinas extras no alimentador {nome_alvo} ({cod_alvo}) | Modo: {modo}")

        # Injeção em Média Tensão (MT_FEEDER ou HYBRID)
        if modo in ["MT_FEEDER", "HYBRID"]:
            buses_3ph: List[str] = []
            for b in feeder_buses:
                dss.Circuit.SetActiveBus(b)
                nodes = dss.Bus.Nodes()
                # Apenas seleciona barras 100% trifásicas
                if 1 in nodes and 2 in nodes and 3 in nodes:
                    buses_3ph.append(b)

            if buses_3ph:
                # Pega as PRIMEIRAS barras (logo após o disjuntor) para evitar chaves abertas no fim do ramo
                alvos_mt = buses_3ph[:3] if len(buses_3ph) >= 3 else buses_3ph
                pot_alvo_feeder_kw = cap_trafos_feeder_kva * self.config.fator_sobrecarga_alvo
                pot_usina_kw = pot_alvo_feeder_kw / len(alvos_mt)

                for idx, bus in enumerate(alvos_mt):
                    nome_pv = f"UFV_EXTRA_MT_{idx+1}"
                    cmd = (
                        f"new PVSystem.{nome_pv} phases=3 bus1={bus}.1.2.3 kv=13.8 "
                        f"conn=wye pmpp={pot_usina_kw:.1f} kva={pot_usina_kw:.1f} pf=1.0 "
                        f"daily={nome_curva} %cutin=0 %cutout=0"
                    )
                    dss.Command(cmd)
                    plantas_injetadas.append({
                        'nome': nome_pv, 'nivel': 'MT (13.8 kV)', 'barra': bus, 'kw': pot_usina_kw
                    })
                    pot_total_kw += pot_usina_kw
                    print(f"    • Usina MT {nome_pv}: {pot_usina_kw/1000:.2f} MW injetada na barra {bus}")

        # Injeção em Baixa Tensão (BT_DISTRIBUTION ou HYBRID)
        trafos_selecionados_bt: List[Tuple[str, float, str]] = []
        if modo in ["BT_DISTRIBUTION", "HYBRID"]:
            trafos_selecionados_bt = self.obter_trafos_alvo_bt(circuit, self.config)

            for idx, (t_nome, kva_nom, sec_bus) in enumerate(trafos_selecionados_bt):
                pot_bt_kw = kva_nom * self.config.fator_sobrecarga_alvo
                
                # Descobre as propriedades elétricas reais do secundário do transformador
                dss.Circuit.SetActiveElement(f"transformer.{t_nome}")
                fases_tr = dss.CktElement.NumPhases()
                dss.Transformers.Wdg(2)
                kv_sec = dss.Transformers.kV()
                
                sec_clean = sec_bus.split('.')[0]
                nome_pv = f"UFV_EXTRA_BT_{idx+1}"
                
                # Se for fase-neutro ou fase-fase-neutro, usa a string exata dos nós de secundário (sec_bus)
                cmd = (
                    f"new PVSystem.{nome_pv} phases={fases_tr} bus1={sec_bus} kv={kv_sec} "
                    f"conn=wye pmpp={pot_bt_kw:.1f} kva={pot_bt_kw:.1f} pf=1.0 "
                    f"daily={nome_curva} %cutin=0 %cutout=0"
                )
                dss.Command(cmd)
                plantas_injetadas.append({
                    'nome': nome_pv, 'nivel': f'BT ({kv_sec} kV)', 'barra': sec_clean, 'kw': pot_bt_kw,
                    'trafo_associado': t_nome
                })
                pot_total_kw += pot_bt_kw
                print(f"    • Usina BT {nome_pv} ({fases_tr}φ): {pot_bt_kw:.1f} kW no secundário do trafo {t_nome} ({kva_nom:.0f} kVA)")

        print(f"  [SOBRECARGA SOLAR] Total extra instalado: {pot_total_kw/1000:.2f} MW em {len(plantas_injetadas)} usinas.")

        return {
            'cod_alimentador': cod_alvo,
            'nome_alimentador': nome_alvo,
            'modo': modo,
            'potencia_total_extra_kw': pot_total_kw,
            'plantas_injetadas': plantas_injetadas,
            'trafos_monitorados': [t[0] for t in trafos_selecionados_bt]
        }
