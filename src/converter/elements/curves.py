import os
import numpy as np
from src.converter.elements.base import BaseElementConverter
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

class CurvesConverter(BaseElementConverter):
    """Gera curvas temporais de carga (CRVCRG) e solar na raiz do modelo."""

    def converter(self, repo: BDGDRepository, config: ConverterConfig) -> None:
        self._gerar_curvas_carga(repo, config)
        self._gerar_curvas_solares(config)

    def _gerar_curvas_carga(self, repo: BDGDRepository, config: ConverterConfig) -> None:
        caminho = os.path.join(config.pasta_saida, "curva_carga.dss")
        cols_pot = [f'POT_{i:02d}' for i in range(1, 97)]

        with open(caminho, "w", encoding="utf-8") as f:
            f.write("! Curvas de Carga Diarias (Loadshapes 96 pontos - 15 min)\n\n")
            for _, row in repo.crvcrg.iterrows():
                if row['TIP_DIA'] == 'DU':
                    nome = row['COD_ID']
                    max_pot = max(row[col] for col in cols_pot)
                    divisor = 100.0 if max_pot > 5.0 else 1.0

                    valores = [f"{round(row[f'POT_{i:02d}'] / divisor, 4)}" for i in range(1, 97)]
                    tx = " ".join(valores)
                    f.write(f"new loadshape.{nome} npts=96 interval=0.25 mult=({tx})\n")

    def _gerar_curvas_solares(self, config: ConverterConfig) -> None:
        dados_solar = {
            "Curva_Solar_Abril": [0, 0, 0, 0, 0, 0, 68, 353, 521, 624, 676, 655, 591, 522, 465, 416, 363, 215, 0, 0, 0, 0, 0, 0],
            "Curva_Solar_Julho": [0, 0, 0, 0, 0, 0, 0, 402, 645, 753, 813, 821, 801, 760, 711, 649, 566, 248, 0, 0, 0, 0, 0, 0],
            "Curva_Solar_Outubro": [0, 0, 0, 0, 0, 0, 127, 281, 402, 492, 546, 540, 507, 458, 393, 333, 280, 167, 0, 0, 0, 0, 0, 0]
        }

        caminho = os.path.join(config.pasta_saida, "curva_solar.dss")
        x_24 = np.arange(24) + 0.5
        x_96 = np.arange(1, 97) * 0.25

        with open(caminho, "w", encoding="utf-8") as f:
            f.write("! Curvas de Irradiacao Solar Normalizadas (96 pontos - 15 min)\n\n")
            for nome_curva, valores in dados_solar.items():
                interp_96 = np.interp(x_96, x_24, valores)
                interp_96[x_96 < 5.75] = 0.0
                interp_96[x_96 > 18.5] = 0.0

                mult_stc = [round(float(v) / 1000.0, 4) for v in interp_96]
                tx_stc = " ".join(f"{x:.4f}" for x in mult_stc)
                f.write(f"new loadshape.{nome_curva} npts=96 interval=0.25 mult=({tx_stc})\n")

                pico = max(interp_96)
                mult_pico = [round(float(v) / pico, 4) if pico > 0 else 0.0 for v in interp_96]
                tx_pico = " ".join(f"{x:.4f}" for x in mult_pico)
                f.write(f"new loadshape.{nome_curva}_PicoUnitario npts=96 interval=0.25 mult=({tx_pico})\n\n")
