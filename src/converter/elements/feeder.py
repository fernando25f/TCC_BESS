import os
import math
import re
from typing import Dict, Any, List, Tuple
import pandas as pd
from src.converter.elements.base import BaseElementConverter, MAPA_FASES, obter_fase_e_tensao_bt
from src.converter.elements.substation import SubstationConverter
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

class FeederConverter(BaseElementConverter):
    """Gera arquivos consolidados CTMT_<id>.dss por alimentador dentro da pasta de cada TR."""

    def converter(self, repo: BDGDRepository, config: ConverterConfig) -> None:
        # PACs válidos e mapa secundário global para evitar perda de cargas/GD conectadas a trafos
        pacs_validos_bt_global = set(repo.ssdbt['PAC_1'].dropna().astype(str)).union(
            set(repo.ssdbt['PAC_2'].dropna().astype(str))
        ).union(set(repo.untrmt['PAC_2'].dropna().astype(str)))
        mapa_trafo_sec_global = dict(zip(repo.untrmt['COD_ID'].astype(str), repo.untrmt['PAC_2'].astype(str)))
        mapa_tr_ctmt = dict(zip(repo.untrmt['COD_ID'].astype(str), repo.untrmt['CTMT'].astype(str)))
        pacs_validos_mt_global = set(repo.ssdmt['PAC_1'].astype(str)) | set(repo.ssdmt['PAC_2'].astype(str))

        ssdmt_grp = self._agrupar_por_ctmt(repo.ssdmt)
        ssdbt_grp = self._agrupar_por_ctmt(repo.ssdbt)
        unsemt_grp = self._agrupar_por_ctmt(repo.unsemt)
        uncrmt_grp = self._agrupar_por_ctmt(repo.uncrmt) if not repo.uncrmt.empty else {}
        untrmt_grp = self._agrupar_por_ctmt(repo.untrmt)
        ucbt_grp = self._agrupar_uc_por_ctmt_efetivo(repo.ucbt, mapa_tr_ctmt)
        ucmt_grp = self._agrupar_por_ctmt(repo.ucmt) if not repo.ucmt.empty else {}
        ugbt_grp = self._agrupar_uc_por_ctmt_efetivo(repo.ugbt, mapa_tr_ctmt)
        ugmt_grp = self._agrupar_por_ctmt(repo.ugmt) if not repo.ugmt.empty else {}

        # Dicionários de consulta O(1)
        segcon_r1 = dict(zip(repo.segcon['COD_ID'], repo.segcon['R1']))
        segcon_x1 = dict(zip(repo.segcon['COD_ID'], repo.segcon['X1']))
        segcon_cnom = dict(zip(repo.segcon['COD_ID'], repo.segcon['CNOM']))

        eqtrmt_r = dict(zip(repo.eqtrmt['UNI_TR_MT'], repo.eqtrmt['R']))
        eqtrmt_xhl = dict(zip(repo.eqtrmt['UNI_TR_MT'], repo.eqtrmt['XHL']))
        eqtrmt_tpri = dict(zip(repo.eqtrmt['UNI_TR_MT'], repo.eqtrmt['TEN_PRI']))
        eqtrmt_tsec = dict(zip(repo.eqtrmt['UNI_TR_MT'], repo.eqtrmt['TEN_SEC']))

        for _, ctmt_row in repo.ctmt.iterrows():
            cod_id = str(ctmt_row['COD_ID']).strip()
            tr_pai = str(ctmt_row['UNI_TR_AT']).strip()
            tr_short = SubstationConverter.obter_identificador_trafo(tr_pai)
            nome_ctmt = str(ctmt_row['NOME']).strip() if 'NOME' in ctmt_row and pd.notna(ctmt_row['NOME']) else f"CTMT_{cod_id}"
            barr_sec = str(ctmt_row['BARR']).strip()
            pac_ini = str(ctmt_row['PAC_INI']).strip()

            pasta_tr = os.path.join(config.pasta_saida, tr_short)
            os.makedirs(pasta_tr, exist_ok=True)
            caminho_arquivo = os.path.join(pasta_tr, f"CTMT_{cod_id}.dss")

            ssdmt_f = ssdmt_grp.get(cod_id, pd.DataFrame())
            ssdbt_f = ssdbt_grp.get(cod_id, pd.DataFrame())
            unsemt_f = unsemt_grp.get(cod_id, pd.DataFrame())
            uncrmt_f = uncrmt_grp.get(cod_id, pd.DataFrame())
            untrmt_f = untrmt_grp.get(cod_id, pd.DataFrame())
            ucbt_f = ucbt_grp.get(cod_id, [])
            ucmt_f = ucmt_grp.get(cod_id, pd.DataFrame())
            ugbt_f = ugbt_grp.get(cod_id, [])
            ugmt_f = ugmt_grp.get(cod_id, pd.DataFrame())

            coords_map: Dict[str, Tuple[str, str]] = {}
            self._extrair_coordenadas(ssdmt_f, coords_map)
            self._extrair_coordenadas(ssdbt_f, coords_map)

            with open(caminho_arquivo, "w", encoding="utf-8") as f:
                f.write("! ==============================================================================\n")
                f.write(f"! ALIMENTADOR CTMT_{cod_id} - {nome_ctmt}\n")
                f.write(f"! Subestacao: Trafo {tr_short} ({tr_pai}) | Barra MT: {barr_sec} -> PAC_INI: {pac_ini}\n")
                f.write("! ==============================================================================\n\n")

                # 1. Disjuntor de saida
                f.write("! 1. Disjuntor de Saida MT do Alimentador\n")
                f.write(f"new line.DJ_{cod_id} phases=3 bus1={barr_sec} bus2={pac_ini} switch=y r1=1e-4 x1=1e-4 length=0.001 units=km\n\n")

                # 2. Linhas de Media Tensao (MT)
                if not ssdmt_f.empty:
                    f.write("! 2. Linhas de Media Tensao (MT)\n")
                    for row in ssdmt_f.itertuples():
                        nome = row.COD_ID
                        fas_info = MAPA_FASES.get(getattr(row, 'FAS_CON', 'ABC'), ('.1.2.3', 3, 'delta'))
                        phases = fas_info[1]
                        barra1 = str(row.PAC_1) + fas_info[0]
                        barra2 = str(row.PAC_2) + fas_info[0]
                        tip_cnd = getattr(row, 'TIP_CND', None)
                        r1 = segcon_r1.get(tip_cnd, 0.5)
                        x1 = segcon_x1.get(tip_cnd, 0.4)
                        corr_nom = segcon_cnom.get(tip_cnd, 200.0)
                        comp = max(0.001, round(float(row.COMP) / 1000.0, 6))
                        f.write(f"new line.{nome} phases={phases} bus1={barra1} bus2={barra2} r1={r1} x1={x1} length={comp} units=km normamps={corr_nom}\n")
                    f.write("\n")

                # 3. Chaves Seccionadoras MT
                if not unsemt_f.empty:
                    f.write("! 3. Chaves Seccionadoras MT\n")
                    for row in unsemt_f.itertuples():
                        nome = row.COD_ID
                        fas_info = MAPA_FASES.get(getattr(row, 'FAS_CON', 'ABC'), ('.1.2.3', 3, 'delta'))
                        phases = fas_info[1]
                        barra1 = str(row.PAC_1) + fas_info[0]
                        barra2 = str(row.PAC_2) + fas_info[0]
                        f.write(f"new line.SC_{nome} phases={phases} bus1={barra1} bus2={barra2} switch=y r1=1e-4 x1=1e-4 length=0.001 units=km\n")
                        if getattr(row, 'P_N_OPE', 'F') == 'A':
                            f.write(f"open line.SC_{nome} 1\n")
                    f.write("\n")

                # 4. Capacitores MT
                if not uncrmt_f.empty:
                    f.write("! 4. Bancos de Capacitores MT\n")
                    for row in uncrmt_f.itertuples():
                        nome = row.COD_ID
                        fas_info = MAPA_FASES.get(getattr(row, 'FAS_CON', 'ABC'), ('.1.2.3', 3, 'wye'))
                        barra1 = str(row.PAC_1).lstrip('R') + fas_info[0]
                        phases = fas_info[1]
                        kvar = repo.dict_potrtv.get(getattr(row, 'POT_NOM', None), 0.0)
                        f.write(f"new capacitor.{nome} phases={phases} bus1={barra1} conn=wye kv=13.8 kvar={kvar}\n")
                    f.write("\n")

                # 5. Transformadores de Distribuicao MT/BT
                if not untrmt_f.empty:
                    f.write("! 5. Transformadores MT/BT de Distribuicao\n")
                    for row in untrmt_f.itertuples():
                        nome = str(row.COD_ID)
                        fas_p = getattr(row, 'FAS_CON_P', 'ABC')
                        fas_s = getattr(row, 'FAS_CON_S', 'ABC')
                        phases = MAPA_FASES.get(fas_p, ('.1.2.3', 3, 'delta'))[1]
                        conn1 = MAPA_FASES.get(fas_p, ('.1.2.3', 3, 'delta'))[2]
                        barra1 = str(row.PAC_1) + MAPA_FASES.get(fas_p, ('.1.2.3', 3, 'delta'))[0]
                        pac2 = str(row.PAC_2)
                        barra2 = pac2 + MAPA_FASES.get(fas_s, ('.1.2.3', 3, 'wye'))[0]

                        r = eqtrmt_r.get(nome, 1.5)
                        xhl = eqtrmt_xhl.get(nome, 3.5)
                        ten_pri_cod = eqtrmt_tpri.get(nome)
                        ten_sec_cod = eqtrmt_tsec.get(nome)
                        kv1 = repo.dict_ten.get(ten_pri_cod, 13.8)
                        kv2 = repo.dict_ten.get(ten_sec_cod, 0.38)
                        kva = float(row.POT_NOM)

                        if phases == 3:
                            if kv1 > 30.0:
                                kv1 = 13.8
                            elif kv1 < 10.0:
                                kv1 = round(kv1 * math.sqrt(3), 2)
                            if kv2 < 0.30:
                                kv2 = 0.38
                            f.write(f"new transformer.UNTRMT_{nome} phases={phases} windings=2 %r={r} xhl={xhl} kva={kva}\n")
                            f.write(f"~ wdg=1 bus={barra1} conn={conn1} kv={kv1}\n")
                            f.write(f"~ wdg=2 bus={barra2} conn=wye kv={kv2}\n\n")
                        elif phases == 1:
                            if kv1 > 15.0:
                                kv1 = 7.96
                            if kv2 > 0.40:
                                r_half = round(r / 2.0, 3)
                                xlt = round(xhl * 0.7, 2)
                                f.write(f"new transformer.UNTRMT_{nome} phases=1 windings=3 %r={r} xhl={xhl} xht={xhl} xlt={xlt} kva={kva}\n")
                                f.write(f"~ wdg=1 bus={barra1} conn=wye kv={kv1} kva={kva} %r={r_half}\n")
                                f.write(f"~ wdg=2 bus={pac2}.1.0 conn=wye kv=0.22 kva={kva} %r={r_half}\n")
                                f.write(f"~ wdg=3 bus={pac2}.0.2 conn=wye kv=0.22 kva={kva} %r={r_half}\n\n")
                            else:
                                f.write(f"new transformer.UNTRMT_{nome} phases=1 windings=2 %r={r} xhl={xhl} kva={kva}\n")
                                f.write(f"~ wdg=1 bus={barra1} conn=wye kv={kv1}\n")
                                f.write(f"~ wdg=2 bus={barra2} conn=wye kv={kv2}\n\n")

                # 6. Linhas de Baixa Tensao (BT)
                if not ssdbt_f.empty:
                    f.write("! 6. Linhas de Baixa Tensao (BT)\n")
                    for row in ssdbt_f.itertuples():
                        nome = row.COD_ID
                        fas_info = MAPA_FASES.get(getattr(row, 'FAS_CON', 'ABC'), ('.1.2.3', 3, 'wye'))
                        phases = fas_info[1]
                        barra1 = str(row.PAC_1) + fas_info[0]
                        barra2 = str(row.PAC_2) + fas_info[0]
                        tip_cnd = getattr(row, 'TIP_CND', None)
                        r1 = segcon_r1.get(tip_cnd, 1.2)
                        x1 = segcon_x1.get(tip_cnd, 0.35)
                        corr_nom = segcon_cnom.get(tip_cnd, 100.0)
                        comp = max(0.001, round(float(row.COMP) / 1000.0, 6))
                        f.write(f"new line.{nome} phases={phases} bus1={barra1} bus2={barra2} r1={r1} x1={x1} length={comp} units=km normamps={corr_nom}\n")
                    f.write("\n")

                # 7. Cargas Consumidoras de Baixa Tensao (BT)
                if ucbt_f:
                    f.write("! 7. Cargas Consumidoras de Baixa Tensao (BT)\n")
                    for row in ucbt_f:
                        pn_con = str(row.PN_CON)
                        uni_tr_mt = str(row.UNI_TR_MT)
                        pac_limpo = str(row.PAC).lstrip('R')
                        barra_detalhada = pn_con + uni_tr_mt

                        if barra_detalhada in pacs_validos_bt_global:
                            barra_calc = barra_detalhada
                        elif pac_limpo in pacs_validos_bt_global:
                            barra_calc = pac_limpo
                        elif uni_tr_mt in mapa_trafo_sec_global and mapa_trafo_sec_global[uni_tr_mt] in pacs_validos_bt_global:
                            barra_calc = mapa_trafo_sec_global[uni_tr_mt]
                        else:
                            continue

                        kw = max(0.01, round(float(row.CAR_INST), 3))
                        nodes, phases, conn, kv = obter_fase_e_tensao_bt(row.FAS_CON, kw)
                        barra = barra_calc + nodes
                        loadshape = row.TIP_CC
                        f.write(f"new load.UCBT_{row.COD_ID} phases={phases} model=1 bus={barra} kv={kv} conn={conn} kw={kw} daily={loadshape} vminpu=0.85\n")
                    f.write("\n")

                # 8. Cargas Consumidoras de Media Tensao (MT)
                if not ucmt_f.empty:
                    ucmt_dedup = ucmt_f.drop_duplicates(subset=['COD_ID'])
                    f.write("! 8. Cargas Consumidoras de Media Tensao (MT)\n")
                    for row in ucmt_dedup.itertuples(index=False):
                        pac = str(row.PAC).lstrip('R')
                        pn_con = str(row.PN_CON)
                        barra_calc = None
                        if pn_con in pacs_validos_mt_global:
                            barra_calc = pn_con
                        elif pac in pacs_validos_mt_global:
                            barra_calc = pac
                        if not barra_calc:
                            continue
                        fas_info = MAPA_FASES.get(row.FAS_CON, ('.1.2.3', 3, 'delta'))
                        barra = barra_calc + fas_info[0]
                        phases = fas_info[1]
                        kv = repo.dict_ten.get(getattr(row, 'TEN_FORN', None), 13.8)
                        kw = max(0.1, round(float(row.CAR_INST), 3))
                        loadshape = row.TIP_CC
                        f.write(f"new load.UCMT_{row.COD_ID} phases={phases} model=1 bus={barra} kv={kv} kw={kw} daily={loadshape} vminpu=0.85\n")
                    f.write("\n")

                # 9. Geracao Distribuida (GD) Solar Existente
                if ugbt_f or not ugmt_f.empty:
                    f.write("! 9. Geracao Distribuida (GD) Solar Existente\n")
                    if ugbt_f:
                        for row in ugbt_f:
                            pn_con = str(row.PN_CON).strip()
                            uni_tr_mt = str(row.UNI_TR_MT).strip()
                            pac_limpo = str(row.PAC).lstrip('R').strip()
                            barra_detalhada = pn_con + uni_tr_mt
                            if barra_detalhada in pacs_validos_bt_global:
                                barra_calc = barra_detalhada
                            elif pac_limpo in pacs_validos_bt_global:
                                barra_calc = pac_limpo
                            elif uni_tr_mt in mapa_trafo_sec_global and mapa_trafo_sec_global[uni_tr_mt] in pacs_validos_bt_global:
                                barra_calc = mapa_trafo_sec_global[uni_tr_mt]
                            else:
                                continue
                            kw = float(row.POT_INST)
                            if kw <= 0.0:
                                continue
                            nodes, phases, conn, kv = obter_fase_e_tensao_bt(row.FAS_CON, kw)
                            barra = barra_calc + nodes
                            cod_id_gd = str(row.COD_ID).strip()
                            f.write(f"new PVSystem.GD_UGBT_{cod_id_gd} phases={phases} bus1={barra} kv={kv} conn={conn} pmpp={kw:.2f} kva={kw:.2f} pf=1.0 irradiance=1.0 daily=Curva_Solar_Abril %cutin=0.1 %cutout=0.1\n")

                    if not ugmt_f.empty and not ssdmt_f.empty:
                        pacs_validos_mt = set(ssdmt_f['PAC_1'].dropna().astype(str)).union(set(ssdmt_f['PAC_2'].dropna().astype(str)))
                        for row in ugmt_f.itertuples(index=False):
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
                            kv = repo.dict_ten.get(getattr(row, 'TEN_FORN', None), 13.8)
                            cod_id_gd = str(row.COD_ID).strip()
                            f.write(f"new PVSystem.GD_UGMT_{cod_id_gd} phases={phases} bus1={barra} kv={kv} conn=delta pmpp={kw:.2f} kva={kw:.2f} pf=1.0 irradiance=1.0 daily=Curva_Solar_Abril %cutin=0.1 %cutout=0.1\n")
                    f.write("\n")

                # 10. Coordenadas dos Barramentos (Bus Coordinates)
                if coords_map:
                    f.write("! 10. Coordenadas Geograficas dos Barramentos deste Alimentador\n")
                    f.write("MakeBusList\n")
                    for pac, (lon, lat) in coords_map.items():
                        f.write(f"SetBusXY Bus={pac} X={lon} Y={lat}\n")

    @staticmethod
    def _agrupar_por_ctmt(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Agrupa DataFrame por código CTMT para acesso em tempo constante O(1)."""
        if df.empty or 'CTMT' not in df.columns:
            return {}
        return {str(k).strip(): v for k, v in df.groupby(df['CTMT'].astype(str).str.strip())}

    @staticmethod
    def _agrupar_uc_por_ctmt_efetivo(df: pd.DataFrame, mapa_tr_ctmt: Dict[str, str]) -> Dict[str, List[Any]]:
        """Agrupa cargas/GD pelo CTMT efetivo de seu transformador para garantir conexão física correta."""
        if df.empty:
            return {}
        grupos: Dict[str, List[Any]] = {}
        for row in df.itertuples(index=False):
            uni_tr = str(getattr(row, 'UNI_TR_MT', '')).strip()
            ctmt_efetivo = mapa_tr_ctmt.get(uni_tr, str(getattr(row, 'CTMT', '')).strip())
            grupos.setdefault(ctmt_efetivo, []).append(row)
        return grupos

    @staticmethod
    def _extrair_coordenadas(df: pd.DataFrame, coords_map: Dict[str, Tuple[str, str]]) -> None:
        if df.empty or 'geometria_wkt' not in df.columns:
            return
        for row in df.itertuples():
            pac1 = str(getattr(row, 'PAC_1', '')).lstrip('R')
            pac2 = str(getattr(row, 'PAC_2', '')).lstrip('R')
            pts = re.findall(r'([-]?\d+\.\d+)\s+([-]?\d+\.\d+)', str(getattr(row, 'geometria_wkt', '')))
            if len(pts) >= 2:
                if pac1 and pac1 not in coords_map:
                    coords_map[pac1] = pts[0]
                if pac2 and pac2 not in coords_map:
                    coords_map[pac2] = pts[-1]
