"""
================================================================================
EXTRATOR DE DADOS BDGD (ESRI Geodatabase .gdb -> CSVs OpenDSS)
Concessionária: Equatorial Goiás (DIST: 6072)
Subestação Alvo: Goiânia Leste (SUB: 5001462)
================================================================================
Este script lê a base oficial da BDGD no formato .gdb (ex: Equatorial_GO_6072_2025-12-31_V11.gdb),
filtra todos os elementos elétricos e geográficos da Subestação Goiânia Leste e
exporta os 17 arquivos CSV padronizados para a pasta 'dados_goiania_leste/',
prontos para serem convertidos para OpenDSS via 'converter_csv_para_dss.py'
e 'gerar_circuitos_ctmt.py'.
================================================================================
"""

import os
import sys
import shutil
import time
import pandas as pd
import geopandas as gpd
import pyogrio

# Diretórios base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)  # Garante caminho relativo para evitar problemas de codificação com GDAL

# Configurações
GDB_PADRAO = "Equatorial_GO_6072_2025-12-31_V11.gdb"
SUB_ID = "5001462"  # Subestação Goiânia Leste
OUTPUT_DIR = os.path.join(BASE_DIR, "dados_goiania_leste")
BACKUP_DIR = os.path.join(BASE_DIR, "dados_goiania_leste_2023_backup")


def localizar_gdb():
    """Localiza o arquivo .gdb no diretório de trabalho."""
    if os.path.exists(GDB_PADRAO):
        return GDB_PADRAO
    gdbs = [f for f in os.listdir(BASE_DIR) if f.endswith(".gdb")]
    if gdbs:
        print(f"[INFO] GDB padrão não encontrado, utilizando: {gdbs[0]}")
        return gdbs[0]
    raise FileNotFoundError("Nenhum arquivo .gdb encontrado na pasta de simulação.")


def fazer_backup():
    """Garante backup dos dados existentes caso o usuário queira restaurar."""
    if os.path.exists(OUTPUT_DIR) and not os.path.exists(BACKUP_DIR):
        print(f"[BACKUP] Criando backup de segurança dos dados anteriores em '{os.path.basename(BACKUP_DIR)}'...")
        shutil.copytree(OUTPUT_DIR, BACKUP_DIR)
        print("[BACKUP] Concluído com sucesso.")


def extrair_dados(gdb_path):
    t_inicio = time.time()
    print("=" * 75)
    print("INICIANDO EXTRAÇÃO DE DADOS BDGD PARA SUBESTAÇÃO GOIÂNIA LESTE")
    print(f"Base de Dados: {gdb_path}")
    print(f"Subestação Alvo (SUB): {SUB_ID}")
    print(f"Pasta de Destino: {OUTPUT_DIR}")
    print("=" * 75)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    resumo_extracao = []

    # -------------------------------------------------------------------------
    # 01. SUB - Subestação
    # -------------------------------------------------------------------------
    print("\n[1/17] Extraindo SUB (Subestação)...")
    try:
        gdf_sub = gpd.read_file(gdb_path, layer="SUB", where=f"COD_ID = '{SUB_ID}'")
        if not gdf_sub.empty:
            gdf_sub["geometria_wkt"] = gdf_sub.geometry.to_wkt()
            df_sub = pd.DataFrame(gdf_sub.drop(columns=["geometry"]))
        else:
            df_sub = pd.DataFrame()
        caminho_csv = os.path.join(OUTPUT_DIR, "01_SUB_subestacao.csv")
        df_sub.to_csv(caminho_csv, index=False)
        print(f"  -> 01_SUB_subestacao.csv salvo com {len(df_sub)} registro(s).")
        resumo_extracao.append(("01_SUB_subestacao.csv", len(df_sub)))
    except Exception as e:
        print(f"  [ERRO SUB]: {e}")

    # -------------------------------------------------------------------------
    # 02a & 02b. UNTRAT / EQTRAT - Transformadores da Subestação
    # -------------------------------------------------------------------------
    print("\n[2/17] Extraindo UNTRAT e EQTRAT (Transformadores AT/MT da Subestação)...")
    df_untrat = pyogrio.read_dataframe(gdb_path, layer="UNTRAT", where=f"SUB = '{SUB_ID}'")
    
    if df_untrat.empty:
        # A Subestação Goiânia Leste é uma subestação de transmissão (Rede Básica / DIT).
        # Na BDGD de distribuição, os transformadores de 230/13.8 kV não vêm nesta camada.
        # Mantemos os 4 transformadores de interconexão modelados para a SE Goiânia Leste (TR1 a TR4).
        print("  [NOTA] UNTRAT não possui registros para esta SE no GDB (SE de Transmissão/Rede Básica).")
        print("         Preservando os 4 transformadores de alimentação 230/13.8 kV da SE Goiânia Leste...")
        caminho_orig_untrat = os.path.join(BACKUP_DIR, "03a_UNTRAT_trafos_subestacao.csv")
        caminho_orig_eqtrat = os.path.join(BACKUP_DIR, "03b_EQTRAT_dados_eletricos_trafos_sub.csv")
        df_untrat = pd.read_csv(caminho_orig_untrat)
        df_eqtrat = pd.read_csv(caminho_orig_eqtrat)
    else:
        untrat_ids = set(df_untrat["COD_ID"].astype(str))
        df_eqtrat_all = pyogrio.read_dataframe(gdb_path, layer="EQTRAT")
        df_eqtrat = df_eqtrat_all[df_eqtrat_all["UNI_TR_AT"].astype(str).isin(untrat_ids)]

    df_untrat.to_csv(os.path.join(OUTPUT_DIR, "03a_UNTRAT_trafos_subestacao.csv"), index=False)
    df_eqtrat.to_csv(os.path.join(OUTPUT_DIR, "03b_EQTRAT_dados_eletricos_trafos_sub.csv"), index=False)
    print(f"  -> 03a_UNTRAT_trafos_subestacao.csv: {len(df_untrat)} trafo(s).")
    print(f"  -> 03b_EQTRAT_dados_eletricos_trafos_sub.csv: {len(df_eqtrat)} registro(s).")
    resumo_extracao.append(("03a_UNTRAT_trafos_subestacao.csv", len(df_untrat)))
    resumo_extracao.append(("03b_EQTRAT_dados_eletricos_trafos_sub.csv", len(df_eqtrat)))

    # -------------------------------------------------------------------------
    # 03. CTMT - Alimentadores MT
    # -------------------------------------------------------------------------
    print("\n[3/17] Extraindo CTMT (Alimentadores de Média Tensão)...")
    df_ctmt = pyogrio.read_dataframe(gdb_path, layer="CTMT", where=f"SUB = '{SUB_ID}'")
    
    # Vincula o alimentador ao transformador AT correspondente com base no barramento (BARR -> BARR_2 do UNTRAT)
    mapa_barr_trafo = {
        str(r['BARR_2']).strip(): str(r['COD_ID']).strip()
        for _, r in df_untrat.iterrows()
        if 'BARR_2' in r and pd.notna(r['BARR_2'])
    }
    if 'UNI_TR_AT' in df_ctmt.columns:
        df_ctmt['UNI_TR_AT'] = df_ctmt.apply(
            lambda r: str(r['UNI_TR_AT']).strip() if pd.notna(r['UNI_TR_AT']) and str(r['UNI_TR_AT']).strip() != ''
            else mapa_barr_trafo.get(str(r['BARR']).strip(), ''),
            axis=1
        )
    caminho_csv = os.path.join(OUTPUT_DIR, "02_CTMT_alimentadores.csv")
    df_ctmt.to_csv(caminho_csv, index=False)
    print(f"  -> 02_CTMT_alimentadores.csv salvo com {len(df_ctmt)} alimentador(es) associados aos trafos AT.")
    resumo_extracao.append(("02_CTMT_alimentadores.csv", len(df_ctmt)))

    # -------------------------------------------------------------------------
    # 04. SSDMT - Linhas de Média Tensão (com geometria WKT)
    # -------------------------------------------------------------------------
    print("\n[4/17] Extraindo SSDMT (Segmentos de Rede MT com geometria)...")
    gdf_ssdmt = gpd.read_file(gdb_path, layer="SSDMT", where=f"SUB = '{SUB_ID}'")
    gdf_ssdmt["geometria_wkt"] = gdf_ssdmt.geometry.to_wkt()
    df_ssdmt = pd.DataFrame(gdf_ssdmt.drop(columns=["geometry"]))
    df_ssdmt.to_csv(os.path.join(OUTPUT_DIR, "04_SSDMT_linhas_MT.csv"), index=False)
    print(f"  -> 04_SSDMT_linhas_MT.csv salvo com {len(df_ssdmt)} trechos de MT.")
    resumo_extracao.append(("04_SSDMT_linhas_MT.csv", len(df_ssdmt)))

    # -------------------------------------------------------------------------
    # 05. SSDBT - Linhas de Baixa Tensão (com geometria WKT)
    # -------------------------------------------------------------------------
    print("\n[5/17] Extraindo SSDBT (Segmentos de Rede BT com geometria)...")
    gdf_ssdbt = gpd.read_file(gdb_path, layer="SSDBT", where=f"SUB = '{SUB_ID}'")
    gdf_ssdbt["geometria_wkt"] = gdf_ssdbt.geometry.to_wkt()
    df_ssdbt = pd.DataFrame(gdf_ssdbt.drop(columns=["geometry"]))
    df_ssdbt.to_csv(os.path.join(OUTPUT_DIR, "05_SSDBT_linhas_BT.csv"), index=False)
    print(f"  -> 05_SSDBT_linhas_BT.csv salvo com {len(df_ssdbt)} trechos de BT.")
    resumo_extracao.append(("05_SSDBT_linhas_BT.csv", len(df_ssdbt)))

    # -------------------------------------------------------------------------
    # 06. SEGCON - Catálogo de Condutores
    # -------------------------------------------------------------------------
    print("\n[6/17] Extraindo SEGCON (Catálogo de Condutores)...")
    df_segcon = pyogrio.read_dataframe(gdb_path, layer="SEGCON")
    df_segcon.to_csv(os.path.join(OUTPUT_DIR, "06_SEGCON_condutores.csv"), index=False)
    print(f"  -> 06_SEGCON_condutores.csv salvo com {len(df_segcon)} tipos de condutor.")
    resumo_extracao.append(("06_SEGCON_condutores.csv", len(df_segcon)))

    # -------------------------------------------------------------------------
    # 07a. UNTRMT - Transformadores de Distribuição MT/BT
    # -------------------------------------------------------------------------
    print("\n[7/17] Extraindo UNTRMT (Transformadores de Distribuição MT/BT)...")
    gdf_untrmt = gpd.read_file(gdb_path, layer="UNTRMT", where=f"SUB = '{SUB_ID}'")
    gdf_untrmt["longitude"] = gdf_untrmt.geometry.x
    gdf_untrmt["latitude"] = gdf_untrmt.geometry.y
    df_untrmt = pd.DataFrame(gdf_untrmt.drop(columns=["geometry"]))
    df_untrmt.to_csv(os.path.join(OUTPUT_DIR, "07a_UNTRMT_trafos_distribuicao.csv"), index=False)
    print(f"  -> 07a_UNTRMT_trafos_distribuicao.csv salvo com {len(df_untrmt)} trafos de distribuição.")
    resumo_extracao.append(("07a_UNTRMT_trafos_distribuicao.csv", len(df_untrmt)))

    untrmt_ids = set(df_untrmt["COD_ID"].astype(str))

    # -------------------------------------------------------------------------
    # 07b. EQTRMT - Dados Elétricos dos Transformadores de Distribuição
    # -------------------------------------------------------------------------
    print("\n[8/17] Extraindo EQTRMT (Dados Elétricos dos Trafos de Distribuição)...")
    df_eqtrmt_all = pyogrio.read_dataframe(gdb_path, layer="EQTRMT")
    df_eqtrmt = df_eqtrmt_all[df_eqtrmt_all["UNI_TR_MT"].astype(str).isin(untrmt_ids)]
    df_eqtrmt.to_csv(os.path.join(OUTPUT_DIR, "07b_EQTRMT_dados_eletricos_trafos_dist.csv"), index=False)
    print(f"  -> 07b_EQTRMT_dados_eletricos_trafos_dist.csv salvo com {len(df_eqtrmt)} registros elétricos.")
    resumo_extracao.append(("07b_EQTRMT_dados_eletricos_trafos_dist.csv", len(df_eqtrmt)))

    # -------------------------------------------------------------------------
    # 08. UCBT - Consumidores de Baixa Tensão
    # -------------------------------------------------------------------------
    print("\n[9/17] Extraindo UCBT (Consumidores de Baixa Tensão)...")
    df_ucbt = pyogrio.read_dataframe(gdb_path, layer="UCBT_tab", where=f"SUB = '{SUB_ID}'")
    df_ucbt.to_csv(os.path.join(OUTPUT_DIR, "08_UCBT_consumidores_BT.csv"), index=False)
    print(f"  -> 08_UCBT_consumidores_BT.csv salvo com {len(df_ucbt)} unidades consumidoras BT.")
    resumo_extracao.append(("08_UCBT_consumidores_BT.csv", len(df_ucbt)))

    # -------------------------------------------------------------------------
    # 09. UCMT - Consumidores de Média Tensão
    # -------------------------------------------------------------------------
    print("\n[10/17] Extraindo UCMT (Consumidores de Média Tensão)...")
    df_ucmt = pyogrio.read_dataframe(gdb_path, layer="UCMT_tab", where=f"SUB = '{SUB_ID}'")
    df_ucmt.to_csv(os.path.join(OUTPUT_DIR, "09_UCMT_consumidores_MT.csv"), index=False)
    print(f"  -> 09_UCMT_consumidores_MT.csv salvo com {len(df_ucmt)} unidades consumidoras MT.")
    resumo_extracao.append(("09_UCMT_consumidores_MT.csv", len(df_ucmt)))

    # -------------------------------------------------------------------------
    # 10. CRVCRG - Curvas de Carga Típicas ANEEL
    # -------------------------------------------------------------------------
    print("\n[11/17] Extraindo CRVCRG (Curvas de Carga)...")
    df_crvcrg = pyogrio.read_dataframe(gdb_path, layer="CRVCRG")
    df_crvcrg.to_csv(os.path.join(OUTPUT_DIR, "10_CRVCRG_curvas_de_carga.csv"), index=False)
    print(f"  -> 10_CRVCRG_curvas_de_carga.csv salvo com {len(df_crvcrg)} curvas de carga.")
    resumo_extracao.append(("10_CRVCRG_curvas_de_carga.csv", len(df_crvcrg)))

    # -------------------------------------------------------------------------
    # 11. UGBT - Geração Distribuída em Baixa Tensão
    # -------------------------------------------------------------------------
    print("\n[12/17] Extraindo UGBT (Geração Distribuída em BT)...")
    try:
        df_ugbt = pyogrio.read_dataframe(gdb_path, layer="UGBT_tab", where=f"SUB = '{SUB_ID}'")
    except Exception:
        df_ugbt = pyogrio.read_dataframe(gdb_path, layer="UGBT_tab")
        if "SUB" in df_ugbt.columns:
            df_ugbt = df_ugbt[df_ugbt["SUB"].astype(str) == SUB_ID]

    caminho_ugbt = os.path.join(OUTPUT_DIR, "11_UGBT_geracao_distribuida_BT.csv")
    if df_ugbt.empty and os.path.exists(caminho_ugbt) and os.path.getsize(caminho_ugbt) > 10000:
        print("  [NOTA] Camada UGBT_tab veio vazia no GDB da distribuidora.")
        print("         Preservando dados enriquecidos de GD BT (2026) já extraídos com ANEEL...")
        df_ugbt = pd.read_csv(caminho_ugbt)
    else:
        df_ugbt.to_csv(caminho_ugbt, index=False)

    print(f"  -> 11_UGBT_geracao_distribuida_BT.csv salvo com {len(df_ugbt)} usinas GD BT.")
    resumo_extracao.append(("11_UGBT_geracao_distribuida_BT.csv", len(df_ugbt)))

    # -------------------------------------------------------------------------
    # 12. UGMT - Geração Distribuída em Média Tensão
    # -------------------------------------------------------------------------
    print("\n[13/17] Extraindo UGMT (Geração Distribuída em MT)...")
    df_ugmt = pyogrio.read_dataframe(gdb_path, layer="UGMT_tab", where=f"SUB = '{SUB_ID}'")
    df_ugmt.to_csv(os.path.join(OUTPUT_DIR, "12_UGMT_geracao_distribuida_MT.csv"), index=False)
    print(f"  -> 12_UGMT_geracao_distribuida_MT.csv salvo com {len(df_ugmt)} usinas GD MT.")
    resumo_extracao.append(("12_UGMT_geracao_distribuida_MT.csv", len(df_ugmt)))

    # -------------------------------------------------------------------------
    # 13. UNCRMT - Bancos de Capacitores MT
    # -------------------------------------------------------------------------
    print("\n[14/17] Extraindo UNCRMT (Bancos de Capacitores MT)...")
    gdf_uncrmt = gpd.read_file(gdb_path, layer="UNCRMT", where=f"SUB = '{SUB_ID}'")
    if not gdf_uncrmt.empty:
        gdf_uncrmt["longitude"] = gdf_uncrmt.geometry.x
        gdf_uncrmt["latitude"] = gdf_uncrmt.geometry.y
        df_uncrmt = pd.DataFrame(gdf_uncrmt.drop(columns=["geometry"]))
    else:
        df_uncrmt = pd.DataFrame()
    df_uncrmt.to_csv(os.path.join(OUTPUT_DIR, "13_UNCRMT_capacitores_MT.csv"), index=False)
    print(f"  -> 13_UNCRMT_capacitores_MT.csv salvo com {len(df_uncrmt)} bancos de capacitores.")
    resumo_extracao.append(("13_UNCRMT_capacitores_MT.csv", len(df_uncrmt)))

    # -------------------------------------------------------------------------
    # 14. BAR - Barramentos
    # -------------------------------------------------------------------------
    print("\n[15/17] Extraindo BAR (Barramentos)...")
    df_bar = pyogrio.read_dataframe(gdb_path, layer="BAR", where=f"SUB = '{SUB_ID}'")
    df_bar.to_csv(os.path.join(OUTPUT_DIR, "14_BAR_barramentos.csv"), index=False)
    print(f"  -> 14_BAR_barramentos.csv salvo com {len(df_bar)} barras.")
    resumo_extracao.append(("14_BAR_barramentos.csv", len(df_bar)))

    # -------------------------------------------------------------------------
    # 15. UNSEMT - Chaves Seccionadoras de Média Tensão
    # -------------------------------------------------------------------------
    print("\n[16/17] Extraindo UNSEMT (Chaves Seccionadoras MT)...")
    gdf_unsemt = gpd.read_file(gdb_path, layer="UNSEMT", where=f"SUB = '{SUB_ID}'")
    gdf_unsemt["geometry"] = gdf_unsemt.geometry.to_wkt()
    df_unsemt = pd.DataFrame(gdf_unsemt)
    df_unsemt.to_csv(os.path.join(OUTPUT_DIR, "15_UNSEMT_chaves_seccionadoras.csv"), index=False)
    print(f"  -> 15_UNSEMT_chaves_seccionadoras.csv salvo com {len(df_unsemt)} chaves seccionadoras.")
    resumo_extracao.append(("15_UNSEMT_chaves_seccionadoras.csv", len(df_unsemt)))

    t_total = time.time() - t_inicio
    print("\n" + "=" * 75)
    print(f"EXTRAÇÃO CONCLUÍDA EM {t_total:.1f} SEGUNDOS!")
    print("=" * 75)
    print(f"{'Arquivo CSV':<45} | {'Registros 2025':>15}")
    print("-" * 65)
    for arq, qtd in resumo_extracao:
        print(f"{arq:<45} | {qtd:>15}")
    print("=" * 75)


if __name__ == "__main__":
    gdb = localizar_gdb()
    fazer_backup()
    extrair_dados(gdb)
