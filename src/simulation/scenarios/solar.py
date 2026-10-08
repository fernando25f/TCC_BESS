from __future__ import annotations
import os
import opendssdirect as dss
from src.simulation.config import SimulationConfig
from src.simulation.core.circuit import CircuitManager
from src.simulation.scenarios.base import ScenarioComponent

class EnableSolarGenerationComponent(ScenarioComponent):
    """Ativa as usinas fotovoltaicas e aplica os parâmetros de imunidade e curvas diárias."""

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def aplicar(self, circuit: CircuitManager) -> None:
        gd_file = os.path.join(self.config.pasta_modelo, "GD_geradores.dss")
        if os.path.exists(gd_file):
            dss.Command(f'redirect "{gd_file}"')
        else:
            dss.Command("batchedit pvsystem..* enabled=yes")
            dss.Command("batchedit generator..* enabled=yes")

        # Previne desconexão abrupta de inversores fotovoltaicos à noite ou por sobretensão extrema no estudo
        dss.Command("batchedit pvsystem..* %cutin=0 %cutout=0 Vmaxpu=2.0 Vminpu=0.5 irradiance=1.0")

        sufixo = "_PicoUnitario" if self.config.tipo_curva_gd == "PicoUnitario" else ""
        nome_curva = f"Curva_Solar_{self.config.mes_solar}{sufixo}"

        dss.LoadShape.Name(nome_curva)
        mults_solar = list(dss.LoadShape.PMult())
        if mults_solar:
            dss.LoadShape.PMult([max(m, 1e-7) for m in mults_solar])

        for pv in dss.PVsystems.AllNames():
            dss.PVsystems.Name(pv)
            dss.PVsystems.daily(nome_curva)
            if self.config.fator_gd != 1.0:
                dss.PVsystems.Pmpp(dss.PVsystems.Pmpp() * self.config.fator_gd)
                dss.PVsystems.kVARated(dss.PVsystems.kVARated() * self.config.fator_gd)
