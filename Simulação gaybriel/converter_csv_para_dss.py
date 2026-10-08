import functools
import json
import pandas as pd
import os
import math
import re
import networkx as nx
import time

t_inicio_conversao = time.time()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuração de pastas dinâmicas e portáteis (relativas ao script ou à pasta raiz)
PASTA_PAI = os.path.dirname(BASE_DIR)

input_folder = os.path.join(BASE_DIR, "dados_goiania_leste")
if not os.path.exists(input_folder) and os.path.exists(os.path.join(PASTA_PAI, "dados_goiania_leste")):
    input_folder = os.path.join(PASTA_PAI, "dados_goiania_leste")

output_folder = os.path.join(BASE_DIR, "modelo_opendss")
if not os.path.exists(output_folder) and os.path.exists(os.path.join(PASTA_PAI, "modelo_opendss")):
    output_folder = os.path.join(PASTA_PAI, "modelo_opendss")

dict_folder = os.path.join(BASE_DIR, "dicionarios_bdgd")
if not os.path.exists(dict_folder) and os.path.exists(os.path.join(PASTA_PAI, "dicionarios_bdgd")):
    dict_folder = os.path.join(PASTA_PAI, "dicionarios_bdgd")

LINHA_CORTE = None
CTMT_CORTE = 5002188

os.makedirs(output_folder, exist_ok=True)
print("Iniciando conversao do CSV para DSS...")

untrat = pd.read_csv(os.path.join(input_folder, "03a_UNTRAT_trafos_subestacao.csv"))
eqtrat = pd.read_csv(os.path.join(input_folder, "03b_EQTRAT_dados_eletricos_trafos_sub.csv"))
ctmt = pd.read_csv(os.path.join(input_folder, "02_CTMT_alimentadores.csv"))
unsemt = pd.read_csv(os.path.join(input_folder, "15_UNSEMT_chaves_seccionadoras.csv"))
uncrmt = pd.read_csv(os.path.join(input_folder, "13_UNCRMT_capacitores_MT.csv"))
untrmt = pd.read_csv(os.path.join(input_folder, "07a_UNTRMT_trafos_distribuicao.csv"))
eqtrmt = pd.read_csv(os.path.join(input_folder, "07b_EQTRMT_dados_eletricos_trafos_dist.csv"))
ssdmt = pd.read_csv(os.path.join(input_folder, "04_SSDMT_linhas_MT.csv"))
ssdbt = pd.read_csv(os.path.join(input_folder, "05_SSDBT_linhas_BT.csv"))
segcon = pd.read_csv(os.path.join(input_folder, "06_SEGCON_condutores.csv"))
crvcrg = pd.read_csv(os.path.join(input_folder, "10_CRVCRG_curvas_de_carga.csv"))
ucbt = pd.read_csv(os.path.join(input_folder, "08_UCBT_consumidores_BT.csv"))
ucmt = pd.read_csv(os.path.join(input_folder, "09_UCMT_consumidores_MT.csv"))

ucbt = ucbt[ucbt['ARE_LOC'] == 'UB']
ucmt = ucmt[ucmt['ARE_LOC'] == 'UB']


def podar_elementos_jusante(linha_corte=LINHA_CORTE, ctmt_alvo=CTMT_CORTE):
    global ssdmt, unsemt, untrmt, ssdbt, ucbt, ucmt, uncrmt
    if linha_corte is None:
        print("[PODA TOPOLÓGICA] LINHA_CORTE desativada (None). Todos os elementos serão mantidos.")
        return

    linha_corte_str = str(linha_corte).strip()

    if ctmt_alvo is None:
        m_l = ssdmt[ssdmt['COD_ID'].astype(str) == linha_corte_str]
        if not m_l.empty:
            ctmt_alvo = m_l.iloc[0]['CTMT']
        else:
            m_s = unsemt[unsemt['COD_ID'].astype(str) == linha_corte_str]
            if not m_s.empty:
                ctmt_alvo = m_s.iloc[0]['CTMT']

    if ctmt_alvo is None:
        print(f"[AVISO PODA] Linha ou chave '{linha_corte_str}' não encontrada em nenhum CTMT.")
        return

    ctmt_str = str(ctmt_alvo).strip()
    print("\n======================================================================")
    print(f"[PODA TOPOLÓGICA] Executando corte na linha/chave: {linha_corte_str} (CTMT: {ctmt_str})")
    print("======================================================================")

    ctmt_match = ctmt[ctmt['COD_ID'].astype(str) == ctmt_str]
    if ctmt_match.empty:
        print(f"[ERRO PODA] Alimentador {ctmt_str} não encontrado na tabela CTMT.")
        return
    pac_ini_str = str(ctmt_match.iloc[0]['PAC_INI']).strip()

    ssdmt_f = ssdmt[ssdmt['CTMT'].astype(str) == ctmt_str]
    unsemt_f = unsemt[unsemt['CTMT'].astype(str) == ctmt_str]
    untrmt_f = untrmt[untrmt['CTMT'].astype(str) == ctmt_str]
    ssdbt_f = ssdbt[ssdbt['CTMT'].astype(str) == ctmt_str]
    ucbt_f = ucbt[ucbt['CTMT'].astype(str) == ctmt_str]
    ucmt_f = ucmt[ucmt['CTMT'].astype(str) == ctmt_str]
    if 'CTMT' in uncrmt.columns:
        uncrmt_f = uncrmt[uncrmt['CTMT'].astype(str) == ctmt_str]
    else:
        uncrmt_f = uncrmt

    G = nx.Graph()
    aresta_corte = None

    for row in ssdmt_f.itertuples():
        cid_str = str(row.COD_ID).strip()
        p1 = str(row.PAC_1).strip()
        p2 = str(row.PAC_2).strip()
        if cid_str == linha_corte_str:
            aresta_corte = (p1, p2, 'Linha MT')
        else:
            G.add_edge(p1, p2, tipo='linha_mt', id=cid_str)

    for row in unsemt_f.itertuples():
        cid_str = str(row.COD_ID).strip()
        p1 = str(row.PAC_1).strip()
        p2 = str(row.PAC_2).strip()
        if cid_str == linha_corte_str or f"SC_{cid_str}" == linha_corte_str:
            aresta_corte = (p1, p2, 'Chave MT')
        else:
            G.add_edge(p1, p2, tipo='chave_mt', id=cid_str)

    for row in untrmt_f.itertuples():
        p1 = str(row.PAC_1).strip()
        p2 = str(row.PAC_2).strip()
        G.add_edge(p1, p2, tipo='trafo_dist', id=str(row.COD_ID).strip())

    for row in ssdbt_f.itertuples():
        p1 = str(row.PAC_1).strip()
        p2 = str(row.PAC_2).strip()
        G.add_edge(p1, p2, tipo='linha_bt', id=str(row.COD_ID).strip())

    if not aresta_corte:
        print(f"[AVISO PODA] Linha ou chave '{linha_corte_str}' não encontrada no CTMT {ctmt_str}.")
        print("             Nenhum elemento foi podado.")
        return

    p1_corte, p2_corte, tipo_corte = aresta_corte
    print(f"[OK] Elemento de corte ({tipo_corte}) localizado entre as barras '{p1_corte}' e '{p2_corte}'.")

    if pac_ini_str in G:
        nos_ativos = nx.node_connected_component(G, pac_ini_str)
    else:
        componentes = list(nx.connected_components(G))
        comp_com_p1 = [c for c in componentes if p1_corte in c]
        if comp_com_p1:
            nos_ativos = comp_com_p1[0]
        elif componentes:
            nos_ativos = max(componentes, key=len)
        else:
            nos_ativos = set()

    todos_nos = set(G.nodes()).union({p1_corte, p2_corte})
    nos_jusante = todos_nos - nos_ativos

    linhas_mt_remover = set(ssdmt_f[(~ssdmt_f['PAC_1'].astype(str).isin(nos_ativos)) | (~ssdmt_f['PAC_2'].astype(str).isin(nos_ativos)) | (ssdmt_f['COD_ID'].astype(str) == linha_corte_str)]['COD_ID'].astype(str))
    chaves_mt_remover = set(unsemt_f[(~unsemt_f['PAC_1'].astype(str).isin(nos_ativos)) | (~unsemt_f['PAC_2'].astype(str).isin(nos_ativos)) | (unsemt_f['COD_ID'].astype(str) == linha_corte_str) | ('SC_' + unsemt_f['COD_ID'].astype(str) == linha_corte_str)]['COD_ID'].astype(str))
    trafos_remover = set(untrmt_f[~untrmt_f['PAC_1'].astype(str).isin(nos_ativos)]['COD_ID'].astype(str))
    linhas_bt_remover = set(ssdbt_f[(~ssdbt_f['PAC_1'].astype(str).isin(nos_ativos)) | (~ssdbt_f['PAC_2'].astype(str).isin(nos_ativos))]['COD_ID'].astype(str))
    ucbt_remover = set(ucbt_f[ucbt_f['UNI_TR_MT'].astype(str).isin(trafos_remover)]['COD_ID'].astype(str))
    ucmt_remover = set(ucmt_f[(~ucmt_f['PAC'].astype(str).isin(nos_ativos)) & (~ucmt_f['PN_CON'].astype(str).isin(nos_ativos))]['COD_ID'].astype(str))

    if not uncrmt_f.empty:
        uncrmt_remover = set(uncrmt_f[~uncrmt_f['PAC_1'].astype(str).isin(nos_ativos)]['COD_ID'].astype(str))
    else:
        uncrmt_remover = set()

    ssdmt = ssdmt[~ssdmt['COD_ID'].astype(str).isin(linhas_mt_remover)].copy()
    unsemt = unsemt[~unsemt['COD_ID'].astype(str).isin(chaves_mt_remover)].copy()
    untrmt = untrmt[~untrmt['COD_ID'].astype(str).isin(trafos_remover)].copy()
    ssdbt = ssdbt[~ssdbt['COD_ID'].astype(str).isin(linhas_bt_remover)].copy()
    ucbt = ucbt[~ucbt['COD_ID'].astype(str).isin(ucbt_remover)].copy()
    ucmt = ucmt[~ucmt['COD_ID'].astype(str).isin(ucmt_remover)].copy()
    if uncrmt_remover:
        uncrmt = uncrmt[~uncrmt['COD_ID'].astype(str).isin(uncrmt_remover)].copy()

    print("----------------------------------------------------------------------")
    print(f"RESUMO DA PODA TOPOLÓGICA NO ALIMENTADOR {ctmt_str}:")
    print(f"  * Barras ativas mantidas (a montante): {len(nos_ativos)}")
    print(f"  * Barras eliminadas (a jusante):      {len(nos_jusante)}")
    print(f"  * Linhas MT eliminadas:                {len(linhas_mt_remover)}")
    print(f"  * Chaves MT eliminadas:                {len(chaves_mt_remover)}")
    print(f"  * Trafos MT/BT eliminados:             {len(trafos_remover)}")
    print(f"  * Linhas BT eliminadas:                {len(linhas_bt_remover)}")
    print(f"  * Cargas BT eliminadas:                {len(ucbt_remover)}")
    print(f"  * Cargas MT eliminadas:                {len(ucmt_remover)}")
    print("----------------------------------------------------------------------\n")


podar_elementos_jusante(LINHA_CORTE, CTMT_CORTE)

tten = pd.read_csv(os.path.join(dict_folder, 'TTEN.csv'))
dict_ten = dict(zip(tten['COD_ID'], tten['TEN'] / 1000))

tpotrtv = pd.read_csv(os.path.join(dict_folder, 'TPOTRTV.csv'))
dict_potrtv = dict(zip(tpotrtv['COD_ID'], tpotrtv['POT']))

mapa_fases = {
    'ABC': ('.1.2.3', 3, 'delta'),
    'A': ('.1', 1, 'wye'),
    'B': ('.2', 1, 'wye'),
    'C': ('.3', 1, 'wye'),
    'AB': ('.1.2', 2, 'delta'),
    'BC': ('.2.3', 2, 'delta'),
    'CA': ('.3.1', 2, 'delta'),
    'ABCN': ('.1.2.3.0', 3, 'delta'),
    'AN': ('.1.0', 1, 'wye'),
    'BN': ('.2.0', 1, 'wye'),
    'CN': ('.3.0', 1, 'wye'),
    'ABN': ('.1.2.0', 3, 'delta'),
    'BCN': ('.2.3.0', 3, 'delta'),
    'CAN': ('.3.1.0', 3, 'delta'),
    'N': ('.0', 1, 'wye'),
}


def gerar_transformador_at():
    with open(os.path.join(output_folder, 'transformador_AT.dss'), 'w') as f:
        for index, row in untrat.iterrows():
            nome = row['COD_ID']
            per_fer = eqtrat.loc[eqtrat['COD_ID'] == row['COD_ID'], 'PER_FER'].values[0]
            per_tot = eqtrat.loc[eqtrat['COD_ID'] == row['COD_ID'], 'PER_TOT'].values[0]
            kv1 = dict_ten[eqtrat.loc[eqtrat['COD_ID'] == row['COD_ID'], 'TEN_PRI'].values[0]]
            kv2 = dict_ten[eqtrat.loc[eqtrat['COD_ID'] == row['COD_ID'], 'TEN_SEC'].values[0]]
            xhl = 4.5
            kva = row['POT_NOM'] * 1000
            barra1 = row['BARR_1']
            barra2 = row['BARR_2']
            conn1 = 'delta'
            conn2 = 'wye'

            f.write(
                f"new transformer.{nome} phases=3 xhl={xhl} windings=2 %loadloss={per_tot} %noloadloss={per_fer} kva={kva}\n"
                f"~ wdg=1 bus={barra1} conn={conn1} kv={kv1}\n"
                f"~ wdg=2 bus={barra2} conn={conn2} kv={kv2}"
            )
            f.write('\n')


def gerar_disjuntores_mt():
    with open(os.path.join(output_folder, 'disjuntores_mt.dss'), 'w') as f:
        for index, row in ctmt.iterrows():
            nome = row['COD_ID']
            barra1 = row['BARR']
            barra2 = row['PAC_INI']
            f.write(
                f"new line.DJ_{nome} phases=3 bus1={barra1} bus2={barra2}\n"
                f"~ switch=y r1=1e-4 x1=1e-4 length=0.001 units=km"
            )
            f.write('\n')


def gerar_seccionadoras_mt():
    with open(os.path.join(output_folder, 'seccionadoras_mt.dss'), 'w') as f:
        for index, row in unsemt.iterrows():
            nome = row['COD_ID']
            barra1 = row['PAC_1']
            barra2 = row['PAC_2']
            f.write(
                f"new line.SC_{nome} phases=3 bus1={barra1} bus2={barra2}\n"
                f"~ switch=y r1=1e-4 x1=1e-4 length=0.001 units=km"
            )
            f.write('\n')
            if row['P_N_OPE'] == 'A':
                f.write(f"open line.SC_{nome} 1\n")


def gerar_capacitores_mt():
    print("Gerando bancos de capacitores MT...")
    with open(os.path.join(output_folder, 'capacitores_mt.dss'), 'w') as f:
        for index, row in uncrmt.iterrows():
            nome = row['COD_ID']
            fases_info = mapa_fases.get(row['FAS_CON'], ('.1.2.3', 3, 'wye'))
            barra1 = str(row['PAC_1']).lstrip('R') + fases_info[0]
            phases = fases_info[1]
            conn = 'wye'
            kv = 13.8
            kvar = dict_potrtv.get(row['POT_NOM'], 0.0)
            f.write(
                f"new capacitor.{nome} phases={phases} bus1={barra1} conn={conn} kv={kv} kvar={kvar}\n"
            )
    print(f"[OK] Capacitores MT gerados: {len(uncrmt)}")


def gerar_transformador_mt():
    print("Gerando transformadores MT/BT com sanitização de tensões e modelagem Split-Phase (Center-Tap)...")
    cont_split_phase = 0
    cont_sanit_pri = 0
    cont_sanit_sec = 0

    with open(os.path.join(output_folder, 'transformador_MT.dss'), 'w') as f:
        for index, row in untrmt.iterrows():
            nome = row['COD_ID']
            phases = mapa_fases[row['FAS_CON_P']][1]
            conn1 = mapa_fases[row['FAS_CON_P']][2]
            barra1 = str(row['PAC_1']) + mapa_fases[row['FAS_CON_P']][0]
            pac2 = str(row['PAC_2'])
            barra2 = pac2 + mapa_fases[row['FAS_CON_S']][0]
            r = eqtrmt.loc[eqtrmt['UNI_TR_MT'] == row['COD_ID'], 'R'].values[0]
            xhl = eqtrmt.loc[eqtrmt['UNI_TR_MT'] == row['COD_ID'], 'XHL'].values[0]
            kv1 = dict_ten[eqtrmt.loc[eqtrmt['UNI_TR_MT'] == row['COD_ID'], 'TEN_PRI'].values[0]]
            kv2 = dict_ten[eqtrmt.loc[eqtrmt['UNI_TR_MT'] == row['COD_ID'], 'TEN_SEC'].values[0]]
            kva = row['POT_NOM']

            if phases == 3:
                if kv1 > 30.0:
                    kv1 = 13.8
                    cont_sanit_pri += 1
                elif kv1 < 10.0:
                    kv1 = round(kv1 * math.sqrt(3), 2)
                    cont_sanit_pri += 1

                if kv2 < 0.3:
                    kv2 = 0.38
                    cont_sanit_sec += 1

                f.write(
                    f"new transformer.UNTRMT_{nome} phases={phases} windings=2 %r={r} xhl={xhl} kva={kva}\n"
                    f"~ wdg=1 bus={barra1} conn={conn1} kv={kv1}\n"
                    f"~ wdg=2 bus={barra2} conn=wye kv={kv2}\n"
                )
            elif phases == 1:
                if kv1 > 15.0:
                    kv1 = 7.96
                    cont_sanit_pri += 1

                if kv2 > 0.4:
                    r_half = round(r / 2.0, 3)
                    xlt = round(xhl * 0.7, 2)
                    f.write("".join([
                        "new transformer.UNTRMT_",
                        f"{nome}",
                        " phases=1 windings=3 %r=",
                        f"{r}",
                        " xhl=",
                        f"{xhl}",
                        " xht=",
                        f"{xhl}",
                        " xlt=",
                        f"{xlt}",
                        " kva=",
                        f"{kva}",
                        "\n~ wdg=1 bus=",
                        f"{barra1}",
                        " conn=wye kv=",
                        f"{kv1}",
                        " kva=",
                        f"{kva}",
                        " %r=",
                        f"{r_half}",
                        "\n~ wdg=2 bus=",
                        f"{pac2}",
                        ".1.0 conn=wye kv=0.22 kva=",
                        f"{kva}",
                        " %r=",
                        f"{r_half}",
                        "\n~ wdg=3 bus=",
                        f"{pac2}",
                        ".0.2 conn=wye kv=0.22 kva=",
                        f"{kva}",
                        " %r=",
                        f"{r_half}",
                        "\n"
                    ]))
                    cont_split_phase += 1
                else:
                    f.write(
                        f"new transformer.UNTRMT_{nome} phases=1 windings=2 %r={r} xhl={xhl} kva={kva}\n"
                        f"~ wdg=1 bus={barra1} conn=wye kv={kv1}\n"
                        f"~ wdg=2 bus={barra2} conn=wye kv={kv2}\n"
                    )

    print("[OK] Transformadores MT gerados com sucesso:")
    print(f"  - Trafos Split-Phase (Center-Tap 220/440V - 3 Enrolamentos): {cont_split_phase}")
    print(f"  - Trafos com primário sanitizado para 13.8 kV / 7.96 kV: {cont_sanit_pri}")
    print(f"  - Trafos trifásicos com secundário sanitizado para 380 V (0.38 kV): {cont_sanit_sec}")


def gerar_linhas_mt():
    with open(os.path.join(output_folder, 'linhas_mt.dss'), 'w') as f:
        for index, row in ssdmt.iterrows():
            nome = row['COD_ID']
            fase_info = mapa_fases.get(row['FAS_CON'], ('.1.2.3', 3, 'delta'))
            phases = fase_info[1]
            barra1 = str(row['PAC_1']) + fase_info[0]
            barra2 = str(row['PAC_2']) + fase_info[0]
            r1 = segcon.loc[segcon['COD_ID'] == row['TIP_CND'], 'R1'].values[0]
            x1 = segcon.loc[segcon['COD_ID'] == row['TIP_CND'], 'X1'].values[0]
            comp = round(row['COMP'] / 1000, 6)
            corr_nom = segcon.loc[segcon['COD_ID'] == row['TIP_CND'], 'CNOM'].values[0]

            if comp < 0.001:
                comp = 0.001

            f.write(
                f"new line.{nome} phases={phases} bus1={barra1} bus2={barra2}\n"
                f"~ r1={r1} x1={x1} length={comp} units=km normamps={corr_nom}"
            )
            f.write('\n')


def gerar_linhas_bt():
    with open(os.path.join(output_folder, 'linhas_bt.dss'), 'w') as f:
        for index, row in ssdbt.iterrows():
            nome = row['COD_ID']
            fase_info = mapa_fases.get(row['FAS_CON'], ('.1.2.3.0', 3, 'delta'))
            phases = fase_info[1]
            barra1 = str(row['PAC_1']) + fase_info[0]
            barra2 = str(row['PAC_2']) + fase_info[0]
            r1 = segcon.loc[segcon['COD_ID'] == row['TIP_CND'], 'R1'].values[0]
            x1 = segcon.loc[segcon['COD_ID'] == row['TIP_CND'], 'X1'].values[0]
            comp = round(row['COMP'] / 1000, 6)
            corr_nom = segcon.loc[segcon['COD_ID'] == row['TIP_CND'], 'CNOM'].values[0]

            if r1 > 5.0:
                r1 = 5.0
            if x1 > 2.0:
                x1 = 2.0
            if comp < 0.001:
                comp = 0.001

            f.write(
                f"new line.{nome} phases={phases} bus1={barra1} bus2={barra2}\n"
                f"~ r1={r1} x1={x1} length={comp} units=km normamps={corr_nom}"
            )
            f.write('\n')


def gerar_loadshapes():
    cols_pot = [f"POT_{i:02d}" for i in range(1, 97)]
    with open(os.path.join(output_folder, 'curva_carga.dss'), 'w') as f:
        for index, row in crvcrg.iterrows():
            if row['TIP_DIA'] == 'DU':
                nome = row['COD_ID']
                npts = 96
                interval = 0.25
                max_pot = max(row[col] for col in cols_pot)
                if max_pot > 5.0:
                    divisor = 100.0
                else:
                    divisor = 1.0

                tx = ""
                for i in range(1, 97):
                    val = row['POT_' + ('0' if i < 10 else '') + f"{i}"] / divisor
                    tx += f"{round(val, 4)} "

                f.write(
                    f"new loadshape.{nome} npts={npts} interval={interval}\n"
                    f"~ mult=({tx})"
                )
                f.write('\n')


def gerar_carga_bt():
    print("Gerando cargas BT com verificação de PAC e Fallback...")
    pacs_ssdbt = set(ssdbt['PAC_1'].dropna().astype(str)).union(set(ssdbt['PAC_2'].dropna().astype(str)))
    pacs_untrmt_sec = set(untrmt['PAC_2'].dropna().astype(str))
    pacs_validos_bt = pacs_ssdbt.union(pacs_untrmt_sec)

    mapa_trafo_sec = dict(zip(untrmt['COD_ID'].astype(str), untrmt['PAC_2'].astype(str)))

    conectados_direto = 0
    conectados_pac = 0
    conectados_fallback = 0
    descartados = 0

    colunas_ene = [f"ENE_{i:02d}" for i in range(1, 13)]
    ucbt['ENE_MED'] = ucbt[colunas_ene].mean(axis=1)
    ucbt['KW_CALC'] = ucbt['CAR_INST'] * 0.11

    with open(os.path.join(output_folder, 'carga_bt.dss'), 'w') as f:
        for row in ucbt.itertuples(index=False):
            pn_con = str(row.PN_CON)
            uni_tr_mt = str(row.UNI_TR_MT)
            pac_limpo = str(row.PAC).lstrip('R')
            barra_detalhada = pn_con + uni_tr_mt

            if barra_detalhada in pacs_validos_bt:
                barra_calc = barra_detalhada
                conectados_direto += 1
            elif pac_limpo in pacs_validos_bt:
                barra_calc = pac_limpo
                conectados_pac += 1
            elif uni_tr_mt in mapa_trafo_sec and mapa_trafo_sec[uni_tr_mt] in pacs_validos_bt:
                barra_calc = mapa_trafo_sec[uni_tr_mt]
                conectados_fallback += 1
            else:
                descartados += 1
                continue

            fase_info = mapa_fases.get(row.FAS_CON, ('.1.2.3.0', 3, 'delta'))
            barra = barra_calc + fase_info[0]
            phases = fase_info[1]
            kv = dict_ten.get(row.TEN_FORN, 0.22)
            kw = max(0.01, round(row.KW_CALC, 3))
            loadshape = row.TIP_CC

            f.write(
                f"new load.UCBT_{row.COD_ID} phases={phases} model=1 bus={barra} kv={kv} kw={kw} daily={loadshape} vminpu=0.85\n"
            )

    print("[OK] Cargas BT geradas com sucesso:")
    print(f"  - Conectadas no poste exato (PN_CON + UNI_TR_MT): {conectados_direto}")
    print(f"  - Conectadas pelo PAC limpo: {conectados_pac}")
    print(f"  - Conectadas via Fallback no secundário do trafo: {conectados_fallback}")
    print(f"  - Cargas órfãs descartadas (sem trafo/rede): {descartados}")


def gerar_carga_mt():
    print("Gerando cargas MT...")
    arquivo_ucmt = os.path.join(input_folder, '09_UCMT_consumidores_MT.csv')
    if not os.path.exists(arquivo_ucmt):
        print(f"[AVISO] Arquivo {arquivo_ucmt} não encontrado. Ignorando UCMT.")
        return

    col_ene = [f"ENE_{i:02d}" for i in range(1, 13)]
    cols = ['COD_ID', 'PN_CON', 'PAC', 'TIP_CC', 'FAS_CON', 'TEN_FORN', 'CAR_INST'] + col_ene
    ucmt = pd.read_csv(arquivo_ucmt, usecols=cols)
    ucmt['ENE_MED'] = ucmt[col_ene].mean(axis=1)
    ucmt['KW_CALC'] = ucmt['CAR_INST'] * 0.11
    ucmt = ucmt.drop_duplicates(subset=['COD_ID'])

    ssdmt = pd.read_csv(os.path.join(input_folder, '04_SSDMT_linhas_MT.csv'), usecols=['PAC_1', 'PAC_2'])
    pacs_validos = set(ssdmt['PAC_1'].astype(str)) | set(ssdmt['PAC_2'].astype(str))

    conectados = 0
    descartados = 0

    with open(os.path.join(output_folder, 'carga_mt.dss'), 'w') as f:
        for row in ucmt.itertuples():
            pac = str(row.PAC).lstrip('R')
            pn_con = str(row.PN_CON)
            barra_calc = None

            if pn_con in pacs_validos:
                barra_calc = pn_con
            elif pac in pacs_validos:
                barra_calc = pac

            if not barra_calc:
                descartados += 1
                continue

            conectados += 1
            fase_info = mapa_fases.get(row.FAS_CON, ('.1.2.3', 3, 'delta'))
            barra = barra_calc + fase_info[0]
            phases = fase_info[1]
            kv = dict_ten.get(row.TEN_FORN, 13.8)
            kw = max(0.1, round(row.KW_CALC, 3))
            loadshape = row.TIP_CC

            f.write(
                f"new load.UCMT_{row.COD_ID} phases={phases} model=1 bus={barra} kv={kv} kw={kw} daily={loadshape} vminpu=0.85\n"
            )

    print(f"[OK] Cargas MT geradas com sucesso: {conectados} (descartadas: {descartados})")


def gerar_gd():
    print("Gerando geração distribuída (GD - Sistemas Fotovoltaicos)...")
    arquivo_ugbt = os.path.join(input_folder, '11_UGBT_geracao_distribuida_BT.csv')
    arquivo_ugmt = os.path.join(input_folder, '12_UGMT_geracao_distribuida_MT.csv')

    src_solar = os.path.join(output_folder, 'modelo_opendss', 'curva_solar.dss')
    dst_solar = os.path.join(output_folder, 'curva_solar.dss')
    if os.path.exists(src_solar) and not os.path.exists(dst_solar):
        import shutil
        shutil.copy(src_solar, dst_solar)

    pacs_validos_bt = set(ssdbt['PAC_1'].astype(str)) | set(ssdbt['PAC_2'].astype(str))
    pacs_validos_mt = set(ssdmt['PAC_1'].astype(str)) | set(ssdmt['PAC_2'].astype(str))
    mapa_trafo_sec = dict(zip(untrmt['COD_ID'].astype(str), untrmt['PAC_2'].astype(str)))

    total_ugbt = 0
    total_ugmt = 0
    pot_total_bt = 0.0
    pot_total_mt = 0.0

    caminho_gd = os.path.join(output_folder, 'geracao_distribuida.dss')
    with open(caminho_gd, 'w', encoding='utf-8') as f:
        f.write("! ==============================================================================\n")
        f.write("! GERACAO DISTRIBUIDA (GD) - SISTEMAS FOTOVOLTAICOS (PVSYSTEM) - BASE 2026\n")
        f.write("! Subestação Goiânia Leste (5001462) - ANEEL / BDGD Equatorial GO\n")
        f.write("! Curva Solar Referência: Curva_Solar_Abril\n")
        f.write("! ==============================================================================\n\n")

        if os.path.exists(arquivo_ugbt):
            ugbt = pd.read_csv(arquivo_ugbt)
            f.write("! --- MICROGERADORES FOTOVOLTAICOS EM BAIXA TENSAO (UGBT - PVSYSTEM) ---\n")
            for row in ugbt.itertuples(index=False):
                pn_con = str(row.PN_CON)
                uni_tr_mt = str(row.UNI_TR_MT)
                pac_limpo = str(row.PAC).lstrip('R')
                barra_detalhada = pn_con + uni_tr_mt

                if barra_detalhada in pacs_validos_bt:
                    barra_calc = barra_detalhada
                elif pac_limpo in pacs_validos_bt:
                    barra_calc = pac_limpo
                elif uni_tr_mt in mapa_trafo_sec and mapa_trafo_sec[uni_tr_mt] in pacs_validos_bt:
                    barra_calc = mapa_trafo_sec[uni_tr_mt]
                else:
                    continue

                fase_info = mapa_fases.get(str(row.FAS_CON).strip(), ('.1.2.3.0', 3, 'delta'))
                barra = barra_calc + fase_info[0]
                phases = fase_info[1]
                kv = dict_ten.get(row.TEN_CON, 0.22)
                pot_kw = float(row.POT_INST) if pd.notna(row.POT_INST) and float(row.POT_INST) > 0 else 5.0
                pmpp = round(pot_kw, 2)
                kva = pmpp

                f.write(
                    f"new PVSystem.GD_UGBT_{row.COD_ID} phases={phases} bus1={barra} kv={kv} conn=wye "
                    f"pmpp={pmpp} kva={kva} pf=1.0 irradiance=1.0 daily=Curva_Solar_Abril %cutin=0.1 %cutout=0.1\n"
                )
                total_ugbt += 1
                pot_total_bt += pmpp

        if os.path.exists(arquivo_ugmt):
            ugmt = pd.read_csv(arquivo_ugmt)
            f.write("\n! --- MINIGERADORES FOTOVOLTAICOS EM MEDIA TENSAO (UGMT - PVSYSTEM) ---\n")
            for row in ugmt.itertuples(index=False):
                pac = str(row.PAC).strip()
                pac_limpo = pac.lstrip('R')

                if pac in pacs_validos_mt:
                    barra_calc = pac
                elif pac_limpo in pacs_validos_mt:
                    barra_calc = pac_limpo
                else:
                    continue

                fase_info = mapa_fases.get(str(row.FAS_CON).strip(), ('.1.2.3', 3, 'delta'))
                barra = barra_calc + fase_info[0]
                phases = fase_info[1]
                pot_kw = float(row.POT_INST) if pd.notna(row.POT_INST) and float(row.POT_INST) > 0 else 50.0
                pmpp = round(pot_kw, 2)
                kva = pmpp
                kv = 13.8

                f.write(
                    f"new PVSystem.GD_UGMT_{row.COD_ID} phases={phases} bus1={barra} kv={kv} conn=wye "
                    f"pmpp={pmpp} kva={kva} pf=1.0 irradiance=1.0 daily=Curva_Solar_Abril %cutin=0.1 %cutout=0.1\n"
                )
                total_ugmt += 1
                pot_total_mt += pmpp

    print(f"[OK] GD gerada com sucesso: {total_ugbt} em BT ({pot_total_bt:.1f} kW) e {total_ugmt} em MT ({pot_total_mt:.1f} kW)")


def parse_wkt_line(wkt):
    if pd.isna(wkt):
        return []
    return re.findall(r'([-]?\d+\.\d+)\s+([-]?\d+\.\d+)', str(wkt))


def gerar_buscoords():
    print("Extraindo coordenadas geográficas para Buscoords...")
    coords_map = {}
    arquivos = ['04_SSDMT_linhas_MT.csv', '05_SSDBT_linhas_BT.csv']

    for arq in arquivos:
        filepath = os.path.join(input_folder, arq)
        if not os.path.exists(filepath):
            continue
        df = pd.read_csv(filepath, usecols=['PAC_1', 'PAC_2', 'geometria_wkt'])
        for row in df.itertuples():
            pac1 = str(row.PAC_1).lstrip('R')
            pac2 = str(row.PAC_2).lstrip('R')
            pts = parse_wkt_line(row.geometria_wkt)
            if len(pts) >= 2:
                if pac1 not in coords_map:
                    coords_map[pac1] = pts[0]
                if pac2 not in coords_map:
                    coords_map[pac2] = pts[-1]

    with open(os.path.join(output_folder, 'buscoords.dss'), 'w') as f:
        for pac, (lon, lat) in coords_map.items():
            f.write(f"{pac}, {lon}, {lat}\n")

    print(f"[OK] Buscoords.dss gerado com {len(coords_map)} nós mapeados.")


def gerar_monitores_e_metadados():
    print("Gerando monitores DSS e metadados dos alimentadores...")
    caminho_monitores = os.path.join(output_folder, 'monitores.dss')

    with open(caminho_monitores, 'w', encoding='utf-8') as f:
        f.write("! ==============================================================================\n")
        f.write("! MONITORES OPENDSS - SUBESTAÇÃO GOIÂNIA LESTE, TRAFOS AT E ALIMENTADORES CTMT\n")
        f.write("! Gerado automaticamente pelo script converter_csv_para_dss.py\n")
        f.write("! ==============================================================================\n\n")

        f.write("! Monitor na fonte principal (Subestacao)\n")
        f.write("new monitor.mon_subestacao element=vsource.source terminal=1 mode=1 ppolar=no\n\n")

        f.write("! Monitores nos Transformadores da Subestacao (AT/MT)\n")
        for _, row in untrat.iterrows():
            tr_nome = str(row['COD_ID']).strip()
            tr_short = tr_nome.replace('GOL-S-TRF-', '')
            f.write(f"new monitor.mon_tr_{tr_short}_pot element=transformer.{tr_nome} terminal=2 mode=1 ppolar=no\n")
            f.write(f"new monitor.mon_tr_{tr_short}_vi  element=transformer.{tr_nome} terminal=2 mode=0\n")
        f.write("\n")

        f.write("! Monitores nos 27 Alimentadores CTMT (Disjuntores MT de saida)\n")
        for _, row in ctmt.iterrows():
            cod_id = str(row['COD_ID']).strip()
            f.write(f"new monitor.mon_ctmt_{cod_id}_pot element=line.DJ_{cod_id} terminal=1 mode=1 ppolar=no\n")
            f.write(f"new monitor.mon_ctmt_{cod_id}_vi  element=line.DJ_{cod_id} terminal=1 mode=0\n")

        caminho_trafos_criticos = os.path.join(output_folder, 'trafos_criticos.json')
        trafos_monitorados_criticos = 0
        if os.path.exists(caminho_trafos_criticos):
            try:
                with open(caminho_trafos_criticos, 'r', encoding='utf-8') as f_crit:
                    dados_crit = json.load(f_crit)
                    trafos_criticos = dados_crit.get('trafos_criticos', [])
                    if trafos_criticos:
                        f.write("\n! ==============================================================================\n")
                        f.write(f"! Monitores direcionados nos {len(trafos_criticos)} transformadores MT/BT com subtensao critica\n")
                        f.write("! ==============================================================================\n")
                        for t_info in trafos_criticos:
                            tr_nome = t_info.get('trafo_dss', '')
                            tr_id = t_info.get('cod_id', tr_nome)
                            f.write(f"new monitor.mon_untrmt_{tr_id}_pot element=transformer.{tr_nome} terminal=2 mode=1 ppolar=no\n")
                            f.write(f"new monitor.mon_untrmt_{tr_id}_vi  element=transformer.{tr_nome} terminal=2 mode=0\n")
                            trafos_monitorados_criticos += 1
            except Exception as e_json:
                print(f"[AVISO] Não foi possível carregar trafos_criticos.json: {e_json}")

    caminho_json = os.path.join(output_folder, 'alimentadores_info.json')
    dados_metadados = {
        'subestacao': 'Subestacao_Goiania_Leste',
        'trafos_subestacao': {},
        'alimentadores': {}
    }

    for _, row in untrat.iterrows():
        tr_nome = str(row['COD_ID']).strip()
        tr_short = tr_nome.replace('GOL-S-TRF-', '')
        sec_bus = str(row['BARR_2']).strip()
        dados_metadados['trafos_subestacao'][tr_nome] = {
            'identificador': tr_short,
            'barra_secundaria': sec_bus,
            'pot_nom_mva': float(row['POT_NOM']) if 'POT_NOM' in row and pd.notna(row['POT_NOM']) else 50.0
        }

    for _, row in ctmt.iterrows():
        cod_id = str(row['COD_ID']).strip()
        dados_metadados['alimentadores'][cod_id] = {
            'nome': str(row['NOME']).strip(),
            'trafo': str(row['UNI_TR_AT']).strip(),
            'barra': str(row['BARR']).strip(),
            'pac_ini': str(row['PAC_INI']).strip()
        }

    with open(caminho_json, 'w', encoding='utf-8') as fj:
        json.dump(dados_metadados, fj, indent=2, ensure_ascii=False)

    print("[OK] monitores.dss gerado com sucesso.")
    if trafos_monitorados_criticos > 0:
        print(f"[OK] {trafos_monitorados_criticos} transformadores MT/BT com subtensão crítica incluídos com monitores de P, Q, V e I.")
    print(f"[OK] alimentadores_info.json gerado com {len(dados_metadados['alimentadores'])} alimentadores.")


if __name__ == '__main__':
    gerar_transformador_at()
    gerar_disjuntores_mt()
    gerar_seccionadoras_mt()
    gerar_capacitores_mt()
    gerar_transformador_mt()
    gerar_linhas_mt()
    gerar_linhas_bt()
    gerar_loadshapes()
    gerar_carga_bt()
    gerar_carga_mt()
    gerar_gd()
    gerar_buscoords()
    gerar_monitores_e_metadados()
    t_total = time.time() - t_inicio_conversao
    minutos = int(t_total // 60)
    segundos = t_total % 60
    print("\n" + "=" * 70)
    if minutos > 0:
        print(f"[CONCLUÍDO] Conversão finalizada com sucesso em {minutos}m {segundos:.2f}s ({t_total:.2f} segundos)!")
    else:
        print(f"[CONCLUÍDO] Conversão finalizada com sucesso em {segundos:.2f} segundos!")
    print("=" * 70 + "\n")
