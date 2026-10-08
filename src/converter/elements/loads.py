import os
import pandas as pd
from src.converter.elements.base import BaseElementConverter, MAPA_FASES, obter_fase_e_tensao_bt
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

class LoadConverter(BaseElementConverter):
    """Gera curvas de carga diárias (LoadShapes) e cargas consumidoras de BT e MT."""

    def converter(self, repo: BDGDRepository, config: ConverterConfig):
        self._gerar_loadshapes(repo, config)
        self._gerar_carga_bt(repo, config)
        self._gerar_carga_mt(repo, config)

    def _gerar_loadshapes(self, repo: BDGDRepository, config: ConverterConfig):
        caminho = os.path.join(config.pasta_saida, "curva_carga.dss")
        cols_pot = [f'POT_{i:02d}' for i in range(1, 97)]

        with open(caminho, "w", encoding="utf-8") as f:
            for _, row in repo.crvcrg.iterrows():
                if row['TIP_DIA'] == 'DU':
                    nome = row['COD_ID']
                    max_pot = max(row[col] for col in cols_pot)
                    divisor = 100.0 if max_pot > 5.0 else 1.0

                    valores = [f"{round(row[f'POT_{i:02d}'] / divisor, 4)}" for i in range(1, 97)]
                    tx = " ".join(valores)
                    f.write(f"new loadshape.{nome} npts=96 interval=0.25 mult=({tx})\n")

    def _gerar_carga_bt(self, repo: BDGDRepository, config: ConverterConfig):
        caminho = os.path.join(config.pasta_saida, "carga_bt.dss")

        pacs_ssdbt = set(repo.ssdbt['PAC_1'].dropna().astype(str)).union(set(repo.ssdbt['PAC_2'].dropna().astype(str)))
        pacs_untrmt_sec = set(repo.untrmt['PAC_2'].dropna().astype(str))
        pacs_validos_bt = pacs_ssdbt.union(pacs_untrmt_sec)
        mapa_trafo_sec = dict(zip(repo.untrmt['COD_ID'].astype(str), repo.untrmt['PAC_2'].astype(str)))

        with open(caminho, "w", encoding="utf-8") as f:
            for row in repo.ucbt.itertuples(index=False):
                pn_con = str(row.PN_CON)
                uni_tr_mt = str(row.UNI_TR_MT)
                pac_limpo = str(row.PAC).lstrip('R')
                barra_detalhada = pn_con + uni_tr_mt

                # Hierarquia de conexão
                if barra_detalhada in pacs_validos_bt:
                    barra_calc = barra_detalhada
                elif pac_limpo in pacs_validos_bt:
                    barra_calc = pac_limpo
                elif uni_tr_mt in mapa_trafo_sec and mapa_trafo_sec[uni_tr_mt] in pacs_validos_bt:
                    barra_calc = mapa_trafo_sec[uni_tr_mt]
                else:
                    continue

                kw = max(0.01, round(float(row.CAR_INST), 3))
                nodes, phases, conn, kv = obter_fase_e_tensao_bt(row.FAS_CON, kw)
                barra = barra_calc + nodes
                loadshape = row.TIP_CC

                f.write(f"new load.UCBT_{row.COD_ID} phases={phases} model=1 bus={barra} kv={kv} conn={conn} kw={kw} daily={loadshape} vminpu=0.85\n")

    def _gerar_carga_mt(self, repo: BDGDRepository, config: ConverterConfig):
        if repo.ucmt.empty:
            return

        caminho = os.path.join(config.pasta_saida, "carga_mt.dss")
        pacs_validos = set(repo.ssdmt['PAC_1'].astype(str)) | set(repo.ssdmt['PAC_2'].astype(str))

        ucmt_dedup = repo.ucmt.drop_duplicates(subset=['COD_ID'])

        with open(caminho, "w", encoding="utf-8") as f:
            for row in ucmt_dedup.itertuples(index=False):
                pac = str(row.PAC).lstrip('R')
                pn_con = str(row.PN_CON)

                barra_calc = None
                if pn_con in pacs_validos:
                    barra_calc = pn_con
                elif pac in pacs_validos:
                    barra_calc = pac

                if not barra_calc:
                    continue

                fas_info = MAPA_FASES.get(row.FAS_CON, ('.1.2.3', 3, 'delta'))
                barra = barra_calc + fas_info[0]
                phases = fas_info[1]
                kv = repo.dict_ten.get(row.TEN_FORN, 13.8)
                kw = max(0.1, round(float(row.CAR_INST), 3))
                loadshape = row.TIP_CC

                f.write(f"new load.UCMT_{row.COD_ID} phases={phases} model=1 bus={barra} kv={kv} kw={kw} daily={loadshape} vminpu=0.85\n")
