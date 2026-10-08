import os
import numpy as np
import pandas as pd
from src.converter.elements.base import BaseElementConverter, MAPA_FASES, obter_fase_e_tensao_bt
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

class SolarConverter(BaseElementConverter):
    """Gera curvas solares horárias (96 pontos) e usinas fotovoltaicas (PVSystem) em BT e MT."""

    def converter(self, repo: BDGDRepository, config: ConverterConfig):
        self._gerar_curvas_solares(config)
        self._gerar_geracao_distribuida(repo, config)

    def _gerar_curvas_solares(self, config: ConverterConfig):
        dados_solar = {
            "Curva_Solar_Abril": [0, 0, 0, 0, 0, 0, 68, 353, 521, 624, 676, 655, 591, 522, 465, 416, 363, 215, 0, 0, 0, 0, 0, 0],
            "Curva_Solar_Julho": [0, 0, 0, 0, 0, 0, 0, 402, 645, 753, 813, 821, 801, 760, 711, 649, 566, 248, 0, 0, 0, 0, 0, 0],
            "Curva_Solar_Outubro": [0, 0, 0, 0, 0, 0, 127, 281, 402, 492, 546, 540, 507, 458, 393, 333, 280, 167, 0, 0, 0, 0, 0, 0]
        }

        caminho = os.path.join(config.pasta_saida, "curva_solar.dss")
        x_24 = np.arange(24) + 0.5
        x_96 = np.arange(1, 97) * 0.25

        with open(caminho, "w", encoding="utf-8") as f:
            for nome_curva, valores in dados_solar.items():
                interp_96 = np.interp(x_96, x_24, valores)
                interp_96[x_96 < 5.75] = 0.0
                interp_96[x_96 > 18.5] = 0.0

                # 1. Normalização STC (1000 W/m² = 1.0 pu)
                mult_stc = [round(float(v) / 1000.0, 4) for v in interp_96]
                tx_stc = " ".join(f"{x:.4f}" for x in mult_stc)
                f.write(f"new loadshape.{nome_curva} npts=96 interval=0.25 mult=({tx_stc})\n")

                # 2. Normalização pelo pico unitário
                pico = max(interp_96)
                mult_pico = [round(float(v) / pico, 4) if pico > 0 else 0.0 for v in interp_96]
                tx_pico = " ".join(f"{x:.4f}" for x in mult_pico)
                f.write(f"new loadshape.{nome_curva}_PicoUnitario npts=96 interval=0.25 mult=({tx_pico})\n\n")

    def _gerar_geracao_distribuida(self, repo: BDGDRepository, config: ConverterConfig, curva_padrao: str = "Curva_Solar_Abril"):
        caminho = os.path.join(config.pasta_saida, "geracao_distribuida.dss")

        pacs_ssdbt = set(repo.ssdbt['PAC_1'].dropna().astype(str)).union(set(repo.ssdbt['PAC_2'].dropna().astype(str)))
        pacs_untrmt_sec = set(repo.untrmt['PAC_2'].dropna().astype(str))
        pacs_validos_bt = pacs_ssdbt.union(pacs_untrmt_sec)
        mapa_trafo_sec = dict(zip(repo.untrmt['COD_ID'].astype(str), repo.untrmt['PAC_2'].astype(str)))

        with open(caminho, "w", encoding="utf-8") as f:
            # UGBT
            if not repo.ugbt.empty:
                for row in repo.ugbt.itertuples(index=False):
                    pn_con = str(row.PN_CON).strip()
                    uni_tr_mt = str(row.UNI_TR_MT).strip()
                    pac_limpo = str(row.PAC).lstrip('R').strip()
                    barra_detalhada = pn_con + uni_tr_mt

                    if barra_detalhada in pacs_validos_bt:
                        barra_calc = barra_detalhada
                    elif pac_limpo in pacs_validos_bt:
                        barra_calc = pac_limpo
                    elif uni_tr_mt in mapa_trafo_sec and mapa_trafo_sec[uni_tr_mt] in pacs_validos_bt:
                        barra_calc = mapa_trafo_sec[uni_tr_mt]
                    else:
                        continue

                    kw = float(row.POT_INST)
                    if kw <= 0.0:
                        continue

                    nodes, phases, conn, kv = obter_fase_e_tensao_bt(row.FAS_CON, kw)
                    barra = barra_calc + nodes
                    cod_id = str(row.COD_ID).strip()
                    f.write(f"new PVSystem.GD_UGBT_{cod_id} phases={phases} bus1={barra} kv={kv} conn={conn} pmpp={kw:.2f} kva={kw:.2f} pf=1.0 irradiance=1.0 daily={curva_padrao} %cutin=0.1 %cutout=0.1\n")

            # UGMT
            if not repo.ugmt.empty:
                pacs_ssdmt = set(repo.ssdmt['PAC_1'].dropna().astype(str)).union(set(repo.ssdmt['PAC_2'].dropna().astype(str)))
                pacs_untrmt_pri = set(repo.untrmt['PAC_1'].dropna().astype(str))
                pacs_validos_mt = pacs_ssdmt.union(pacs_untrmt_pri)

                for row in repo.ugmt.itertuples(index=False):
                    pac_str = str(row.PAC).strip()
                    if pac_str in pacs_validos_mt:
                        barra_calc = pac_str
                    else:
                        pn_str = str(row.PN_CON).strip()
                        cand = [p for p in pacs_validos_mt if p.startswith(pn_str)]
                        if cand:
                            barra_calc = cand[0]
                        else:
                            continue

                    kw = float(row.POT_INST)
                    if kw <= 0.0:
                        continue

                    fas_info = MAPA_FASES.get(row.FAS_CON, ('.1.2.3', 3, 'delta'))
                    barra = barra_calc + fas_info[0]
                    phases = fas_info[1]
                    kv = repo.dict_ten.get(row.TEN_CON, 13.8)
                    cod_id = str(row.COD_ID).strip()
                    f.write(f"new PVSystem.GD_UGMT_{cod_id} phases={phases} bus1={barra} kv={kv} conn=wye pmpp={kw:.2f} kva={kw:.2f} pf=1.0 irradiance=1.0 daily={curva_padrao} %cutin=0.1 %cutout=0.1\n")
