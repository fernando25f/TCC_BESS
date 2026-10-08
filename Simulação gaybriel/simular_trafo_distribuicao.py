"""
================================================================================
SIMULADOR INDIVIDUAL DE TRANSFORMADOR DE DISTRIBUIÇÃO (MT/BT)
COM SUPORTE A GD (2026) E BATERIAS (BESS)
================================================================================
Permite simular e comparar o comportamento elétrico detalhado de um ÚNICO
transformador de distribuição (MT/BT) sob 3 cenários de estudo para o TCC:
  1. SEM GD: Apenas a curva de carga dos consumidores (Caso Base)
  2. COM GD: Inclusão dos sistemas fotovoltaicos (PVSystem) de 2026
  3. COM BATERIA (BESS): Armazenamento de energia mitigando fluxo reverso e pico
  4. COMPARATIVO: Simula os 3 cenários e plota gráficos comparativos sobrepostos!

Uso:
  python simular_trafo_distribuicao.py --trafo 5459374 --cenario comparativo
  python simular_trafo_distribuicao.py --trafo 5459374 --cenario com-gd
  python simular_trafo_distribuicao.py --trafo 5459374 --cenario bateria
  python simular_trafo_distribuicao.py --trafo 5459374 --cenario sem-gd
  python simular_trafo_distribuicao.py --top-gd
  python simular_trafo_distribuicao.py --top-cargas
================================================================================
"""

import os
import sys
import time
import math
import re
import argparse
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
import opendssdirect as dss
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import folium
from folium import plugins

# ==============================================================================
# CONFIGURAÇÃO PADRÃO DO TRANSFORMADOR ALVO E CENÁRIO
# ==============================================================================
# "5459374" -> 500 kVA (34 usinas GD BT = 243.28 kW de solar instalado - Excelente para estudo!)
# "5307864" -> 300 kVA (17 usinas GD BT = 240.70 kW de solar instalado - 80% de penetração!)
# "5270903" -> 75 kVA  (382 clientes BT - Trafo sobrecarregado no pico)
# "5575468" -> 1000 kVA (303 clientes BT)
COD_ID_TRAFO = "5288271"

# Opções de cenário: 'comparativo', 'com-gd', 'sem-gd', 'bateria'
CENARIO_PADRAO = "comparativo"

# Suavização das curvas:
# True  -> Interpola os degraus horários da ANEEL/BDGD tornando o gráfico contínuo e suave
# False -> Mantém os degraus horários brutos da BDGD
SUAVIZAR_CURVAS = True
# ==============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS_DIR = os.path.join(BASE_DIR, "dados_goiania_leste")
DICT_DIR = os.path.join(BASE_DIR, "dicionarios_bdgd")
GRAFICOS_DIR = os.path.join(BASE_DIR, "graficos")
SCRATCH_DIR = os.path.join(BASE_DIR, "scratch_dss")
os.makedirs(GRAFICOS_DIR, exist_ok=True)
os.makedirs(SCRATCH_DIR, exist_ok=True)

MAPA_FASES = {
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

# Curva de irradiação solar de Goiânia (Abril - 96 passos de 15 min normalizada no pico = 1.0)
MULT_SOLAR = [
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0251, 0.0503,
    0.0754, 0.1006, 0.206, 0.3114, 0.4168, 0.5222, 0.5843, 0.6464, 0.7086, 0.7707, 0.8088, 0.8469,
    0.885, 0.9231, 0.9423, 0.9615, 0.9808, 1.0, 0.9922, 0.9845, 0.9767, 0.9689, 0.9453, 0.9216,
    0.8979, 0.8743, 0.8487, 0.8232, 0.7977, 0.7722, 0.7511, 0.73, 0.7089, 0.6879, 0.6697, 0.6516,
    0.6335, 0.6154, 0.5958, 0.5762, 0.5566, 0.537, 0.4822, 0.4275, 0.3728, 0.318, 0.2385, 0.159,
    0.0795, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
]

# Curva de Despacho BESS (96 pontos):
# -1.0: Carga (10h00 às 14h30 - absorve excedente solar)
# +1.0: Descarga (18h00 às 21h30 - alivia o pico noturno)
MULT_BESS = [0.0] * 96
for h in range(40, 58):  # 10h00 às 14h15
    MULT_BESS[h] = -1.0
for h in range(72, 88):  # 18h00 às 21h45
    MULT_BESS[h] = 1.0


def carregar_bases():
    print("Carregando tabelas da BDGD e GD 2026...")
    untrmt = pd.read_csv(os.path.join(DADOS_DIR, "07a_UNTRMT_trafos_distribuicao.csv"))
    eqtrmt = pd.read_csv(os.path.join(DADOS_DIR, "07b_EQTRMT_dados_eletricos_trafos_dist.csv"))
    ssdbt = pd.read_csv(os.path.join(DADOS_DIR, "05_SSDBT_linhas_BT.csv"))
    ucbt = pd.read_csv(os.path.join(DADOS_DIR, "08_UCBT_consumidores_BT.csv"))
    ugbt = pd.read_csv(os.path.join(DADOS_DIR, "11_UGBT_geracao_distribuida_BT.csv"))
    segcon = pd.read_csv(os.path.join(DADOS_DIR, "06_SEGCON_condutores.csv"))
    crvcrg = pd.read_csv(os.path.join(DADOS_DIR, "10_CRVCRG_curvas_de_carga.csv"))

    tten = pd.read_csv(os.path.join(DICT_DIR, "TTEN.csv"))
    dict_ten = dict(zip(tten['COD_ID'], tten['TEN'] / 1000.0))

    return untrmt, eqtrmt, ssdbt, ucbt, ugbt, segcon, crvcrg, dict_ten


def listar_top_gd(ugbt, untrmt, top=15):
    print("\n" + "=" * 95)
    print(f"TOP {top} TRANSFORMADORES COM MAIOR CAPACIDADE INSTALADA DE GD SOLAR (BT 2026):")
    print("=" * 95)
    resumo = ugbt.groupby('UNI_TR_MT').agg(
        qtd_gd=('COD_ID', 'count'),
        pot_total_kw=('POT_INST', 'sum'),
        pot_media_kw=('POT_INST', 'mean')
    ).sort_values(by='pot_total_kw', ascending=False).head(top)

    print(f"{'COD_ID Trafo':<14} | {'CTMT (Alimentador)':<20} | {'Pot Trafo (kVA)':<16} | {'Qtd GDs':<9} | {'Pot GD Total (kW)':<18} | {'Penetração (%)':<14}")
    print("-" * 95)
    for tr_id, row in resumo.iterrows():
        tr_info = untrmt[untrmt['COD_ID'].astype(str) == str(tr_id)]
        if not tr_info.empty:
            ctmt = tr_info.iloc[0]['CTMT']
            pot_tr = float(tr_info.iloc[0]['POT_NOM'])
            pen_pct = (row['pot_total_kw'] / pot_tr) * 100.0 if pot_tr > 0 else 0.0
            print(f"{str(tr_id):<14} | {str(ctmt):<20} | {pot_tr:<16.1f} | {row['qtd_gd']:<9} | {row['pot_total_kw']:<18.2f} | {pen_pct:<14.1f}%")
        else:
            print(f"{str(tr_id):<14} | {'-':<20} | {'-':<16} | {row['qtd_gd']:<9} | {row['pot_total_kw']:<18.2f} | {'-':<14}")
    print("=" * 95)


def listar_top_cargas(untrmt, ucbt, top=10):
    print("\n" + "=" * 80)
    print(f"TOP {top} TRANSFORMADORES COM MAIOR NÚMERO DE CONSUMIDORES (BT):")
    print("=" * 80)
    contagem = ucbt['UNI_TR_MT'].astype(str).value_counts().head(top)
    print(f"{'COD_ID Trafo':<15} | {'Alimentador (CTMT)':<20} | {'Potência (kVA)':<15} | {'Nº de Clientes':<15}")
    print("-" * 80)
    for cod_id, qtd in contagem.items():
        tr_info = untrmt[untrmt['COD_ID'].astype(str) == cod_id]
        if not tr_info.empty:
            ctmt = tr_info.iloc[0]['CTMT']
            pot = tr_info.iloc[0]['POT_NOM']
            print(f"{cod_id:<15} | {ctmt:<20} | {pot:<15.1f} | {qtd:<15}")
        else:
            print(f"{cod_id:<15} | {'Desconhecido':<20} | {'-':<15} | {qtd:<15}")
    print("=" * 80)


def simular_cenario_dss(cenario, cod_id_str, untrmt, eqtrmt, ssdbt, ucbt, ugbt, segcon, crvcrg, dict_ten, bess_kw=None, bess_kwh=None):
    tr_match = untrmt[untrmt['COD_ID'].astype(str) == cod_id_str]
    if tr_match.empty:
        raise ValueError(f"Transformador '{cod_id_str}' não encontrado.")

    row_tr = tr_match.iloc[0]
    pot_nom = float(row_tr['POT_NOM'])
    pac_pri = str(row_tr['PAC_1']).strip()
    pac_sec = str(row_tr['PAC_2']).strip()
    fases_p = str(row_tr['FAS_CON_P']).strip()
    fases_s = str(row_tr['FAS_CON_S']).strip()

    eq_match = eqtrmt[eqtrmt['UNI_TR_MT'].astype(str) == cod_id_str]
    row_eq = eq_match.iloc[0]
    r = float(row_eq['R'])
    xhl = float(row_eq['XHL'])
    kv_pri = dict_ten.get(row_eq['TEN_PRI'], 13.8)
    kv_sec = dict_ten.get(row_eq['TEN_SEC'], 0.38)

    linhas_bt = ssdbt[ssdbt['UNI_TR_MT'].astype(str) == cod_id_str]
    cargas_bt = ucbt[ucbt['UNI_TR_MT'].astype(str) == cod_id_str]
    gds_bt = ugbt[ugbt['UNI_TR_MT'].astype(str) == cod_id_str]

    dss_file = os.path.join(SCRATCH_DIR, f"Trafo_{cod_id_str}_{cenario}.dss")
    with open(dss_file, "w", encoding="utf-8") as f:
        f.write(f"! Cenario: {cenario} - Trafo UNTRMT_{cod_id_str}\nclear\n\n")
        f.write(f"new circuit.Trafo_{cod_id_str} basekv={kv_pri} bus1=BARRA_FONTE_MT pu=1.00 phases=3\n\n")

        # Curvas de Carga Diárias
        cols_pot = [f"POT_{i:02d}" for i in range(1, 97)]
        horas_24 = np.arange(24)
        horas_96 = np.linspace(0, 24, 96, endpoint=False)
        for _, r_crv in crvcrg.iterrows():
            if r_crv['TIP_DIA'] == 'DU':
                c_id = r_crv['COD_ID']
                raw_vals = [r_crv[col] for col in cols_pot]
                max_pot = max(raw_vals)
                divisor = 100.0 if max_pot > 5.0 else 1.0
                norm_vals = np.array(raw_vals) / divisor
                if SUAVIZAR_CURVAS:
                    vals_24 = norm_vals[0::4]
                    interp = PchipInterpolator(np.append(horas_24, 24), np.append(vals_24, vals_24[0]))
                    suave_vals = np.clip(interp(horas_96), 0.0, None)
                    mult_vals = [f"{v:.4f}" for v in suave_vals]
                else:
                    mult_vals = [f"{v:.4f}" for v in norm_vals]
                f.write(f"new loadshape.{c_id} npts=96 interval=0.25 mult=({' '.join(mult_vals)})\n")

        # Curvas Solar e BESS
        f.write(f"\nnew loadshape.Curva_Solar npts=96 interval=0.25 mult=({' '.join(f'{v:.4f}' for v in MULT_SOLAR)})\n")
        f.write(f"new loadshape.Curva_BESS npts=96 interval=0.25 mult=({' '.join(f'{v:.4f}' for v in MULT_BESS)})\n\n")

        # Transformador
        fases_info_p = MAPA_FASES.get(fases_p, ('.1.2.3', 3, 'delta'))
        fases_info_s = MAPA_FASES.get(fases_s, ('.1.2.3.0', 3, 'wye'))
        num_phases = fases_info_p[1]
        barra_pri = "BARRA_FONTE_MT" + fases_info_p[0]
        barra_sec = pac_sec + fases_info_s[0]

        if num_phases == 3:
            f.write(
                f"new transformer.TR_{cod_id_str} phases=3 windings=2 %r={r} xhl={xhl} kva={pot_nom}\n"
                f"~ wdg=1 bus={barra_pri} conn={fases_info_p[2]} kv={kv_pri}\n"
                f"~ wdg=2 bus={barra_sec} conn=wye kv={kv_sec}\n\n"
            )
        else:
            f.write(
                f"new transformer.TR_{cod_id_str} phases=1 windings=2 %r={r} xhl={xhl} kva={pot_nom}\n"
                f"~ wdg=1 bus={barra_pri} conn=wye kv={kv_pri/math.sqrt(3):.2f}\n"
                f"~ wdg=2 bus={barra_sec} conn=wye kv={kv_sec:.3f}\n\n"
            )

        # Linhas BT
        for _, r_l in linhas_bt.iterrows():
            lid = r_l['COD_ID']
            f_info = MAPA_FASES.get(r_l['FAS_CON'], ('.1.2.3.0', 3, 'delta'))
            b1 = str(r_l['PAC_1']) + f_info[0]
            b2 = str(r_l['PAC_2']) + f_info[0]
            tip_cnd = r_l['TIP_CND']
            match_seg = segcon[segcon['COD_ID'] == tip_cnd]
            r1 = float(match_seg['R1'].values[0]) if not match_seg.empty else 1.0
            x1 = float(match_seg['X1'].values[0]) if not match_seg.empty else 0.1
            comp = max(0.001, round(float(r_l['COMP']) / 1000.0, 6))
            f.write(f"new line.BT_{lid} phases={f_info[1]} bus1={b1} bus2={b2} r1={r1} x1={x1} length={comp} units=km\n")

        # Cargas BT
        pacs_validos = set(linhas_bt['PAC_1'].astype(str)) | set(linhas_bt['PAC_2'].astype(str)) | {pac_sec}
        for _, r_c in cargas_bt.iterrows():
            cid = r_c['COD_ID']
            pn_con = str(r_c['PN_CON'])
            uni_tr = str(r_c['UNI_TR_MT'])
            pac_c = str(r_c['PAC']).lstrip('R')
            b_det = pn_con + uni_tr
            b_alvo = b_det if b_det in pacs_validos else (pac_c if pac_c in pacs_validos else pac_sec)
            f_info = MAPA_FASES.get(r_c['FAS_CON'], ('.1.2.3.0', 3, 'delta'))
            b_carga = b_alvo + f_info[0]
            kw = max(0.05, float(r_c['CAR_INST']) * 0.11)
            f.write(f"new load.UC_{cid} phases={f_info[1]} bus={b_carga} kv={kv_sec} kw={kw:.3f} daily={r_c['TIP_CC']} vminpu=0.85\n")

        # Geração Distribuída (PVSystem)
        if cenario in ['com_gd', 'bateria']:
            f.write("\n! Geração Distribuída Fotovoltaica (GD BT 2026)\n")
            for _, r_gd in gds_bt.iterrows():
                cid = r_gd['COD_ID']
                pn_con = str(r_gd['PN_CON'])
                uni_tr = str(r_gd['UNI_TR_MT'])
                pac_c = str(r_gd['PAC']).lstrip('R')
                b_det = pn_con + uni_tr
                b_alvo = b_det if b_det in pacs_validos else (pac_c if pac_c in pacs_validos else pac_sec)
                f_info = MAPA_FASES.get(r_gd['FAS_CON'], ('.1.2.3.0', 3, 'delta'))
                b_gd = b_alvo + f_info[0]
                pot_kw = float(r_gd['POT_INST'])
                f.write(
                    f"new PVSystem.GD_{cid} phases={f_info[1]} bus1={b_gd} kv={kv_sec} conn=wye "
                    f"pmpp={pot_kw:.2f} kva={pot_kw:.2f} pf=1.0 irradiance=1.0 daily=Curva_Solar %cutin=0.1 %cutout=0.1\n"
                )

        # Sistema de Baterias (BESS)
        if cenario == 'bateria':
            # Dimensionamento do BESS (padrão: 25% da potência do trafo, 2h a 3h de autonomia)
            kw_b = bess_kw if bess_kw else max(25.0, round(pot_nom * 0.25, 1))
            kwh_b = bess_kwh if bess_kwh else round(kw_b * 3.0, 1)
            f.write(f"\n! Sistema de Armazenamento por Bateria (BESS)\n")
            f.write(
                f"new Storage.BESS phases={num_phases} bus1={barra_sec} kv={kv_sec} "
                f"kwrated={kw_b} kwhrated={kwh_b} %stored=50 dispmode=follow daily=Curva_BESS "
                f"%reserve=10 %charge=100 %discharge=100\n"
            )

        # Monitores
        f.write(f"\nnew monitor.mon_trafo element=transformer.TR_{cod_id_str} terminal=2 mode=1 ppolar=no\n")
        f.write(f"new monitor.mon_tensao element=transformer.TR_{cod_id_str} terminal=2 mode=0\n")

    # Executar Simulação no OpenDSS
    dss.Command(f'compile "{dss_file}"')
    dss.Command("set mode=daily stepsize=15m number=96")
    dss.Command("solve")

    # Coletar Resultados
    dss.Monitors.Name("mon_trafo")
    p1 = dss.Monitors.Channel(1)
    p2 = dss.Monitors.Channel(3)
    p3 = dss.Monitors.Channel(5)
    q1 = dss.Monitors.Channel(2)
    q2 = dss.Monitors.Channel(4)
    q3 = dss.Monitors.Channel(6)

    dss.Monitors.Name("mon_tensao")
    v1 = dss.Monitors.Channel(1)
    v2 = dss.Monitors.Channel(3)
    v3 = dss.Monitors.Channel(5)

    v_base_fn = (kv_sec * 1000.0) / math.sqrt(3) if num_phases == 3 else kv_sec * 1000.0
    v1_pu = [v / v_base_fn for v in v1]
    v2_pu = [v / v_base_fn for v in v2] if len(v2) > 0 else []
    v3_pu = [v / v_base_fn for v in v3] if len(v3) > 0 else []

    # Potência Ativa que flui do trafo para a rede (positiva para consumo, negativa para injeção reversa)
    p_net = [-1.0 * (a + b + c) for a, b, c in zip(p1, p2, p3)]
    q_net = [-1.0 * (a + b + c) for a, b, c in zip(q1, q2, q3)]
    s_net = [math.sqrt(p**2 + q**2) for p, q in zip(p_net, q_net)]
    carreg_pct = [(s / pot_nom) * 100.0 for s in s_net]

    return {
        'p_net': p_net,
        'q_net': q_net,
        's_net': s_net,
        'carreg_pct': carreg_pct,
        'v1_pu': v1_pu,
        'v2_pu': v2_pu,
        'v3_pu': v3_pu,
        'pot_nom': pot_nom,
        'qtd_gds': len(gds_bt),
        'pot_gd_total': gds_bt['POT_INST'].sum() if not gds_bt.empty else 0.0,
        'qtd_clientes': len(cargas_bt)
    }


def simular_trafo(cod_id_str, cenario='comparativo', bess_kw=None, bess_kwh=None):
    untrmt, eqtrmt, ssdbt, ucbt, ugbt, segcon, crvcrg, dict_ten = carregar_bases()

    tr_match = untrmt[untrmt['COD_ID'].astype(str) == cod_id_str]
    if tr_match.empty:
        print(f"[ERRO] Transformador '{cod_id_str}' não encontrado.")
        return

    pot_nom = float(tr_match.iloc[0]['POT_NOM'])
    linhas_bt = ssdbt[ssdbt['UNI_TR_MT'].astype(str) == cod_id_str]
    gds_bt = ugbt[ugbt['UNI_TR_MT'].astype(str) == cod_id_str]
    cargas_bt = ucbt[ucbt['UNI_TR_MT'].astype(str) == cod_id_str]

    print("\n" + "=" * 80)
    print(f"ESTUDO DO TRANSFORMADOR DE DISTRIBUIÇÃO: UNTRMT_{cod_id_str}")
    print("=" * 80)
    print(f"  * Potência Nominal:               {pot_nom:.1f} kVA")
    print(f"  * Clientes Atendidos (UCBT):      {len(cargas_bt)}")
    print(f"  * Usinas GD Solar (2026):         {len(gds_bt)} unidades")
    print(f"  * Capacidade Instalada GD Solar:  {gds_bt['POT_INST'].sum():.2f} kW ({gds_bt['POT_INST'].sum()/pot_nom*100:.1f}% da capacidade do trafo)")
    print(f"  * Modo de Simulação Selecionado:  {cenario.upper()}")
    print("=" * 80)

    cenarios_a_rodar = ['sem_gd', 'com_gd', 'bateria'] if cenario == 'comparativo' else [cenario.replace('-', '_')]
    resultados = {}

    for c in cenarios_a_rodar:
        print(f" -> Simulando cenário [{c.upper()}] no OpenDSS (96 passos de 15 min)...")
        resultados[c] = simular_cenario_dss(c, cod_id_str, untrmt, eqtrmt, ssdbt, ucbt, ugbt, segcon, crvcrg, dict_ten, bess_kw, bess_kwh)

    # Tabela Resumo dos Cenários
    print("\n" + "=" * 90)
    print(f"{'CENÁRIO':<16} | {'P_PICO (kW)':<12} | {'CARREG_MAX':<12} | {'P_MEIO-DIA (kW)':<16} | {'FLUXO REVERSO?':<15} | {'V_MIN/V_MAX (PU)':<16}")
    print("-" * 90)
    for c, res in resultados.items():
        p_pico = max(res['p_net'])
        carreg_max = max(res['carreg_pct'])
        p_meio_dia = res['p_net'][48] # 12h00
        fluxo_rev = "SIM (Injeção)" if min(res['p_net']) < 0 else "NÃO"
        v_min = min(res['v1_pu'])
        v_max = max(res['v1_pu'])
        print(f"{c.upper():<16} | {p_pico:<12.1f} | {carreg_max:<11.1f}% | {p_meio_dia:<16.1f} | {fluxo_rev:<15} | {v_min:.3f} / {v_max:.3f}")
    print("=" * 90)

    # Plotagem de Gráficos Comparativos
    horas = np.array([i * 0.25 for i in range(96)])
    h_plot = np.linspace(0, 24, 384, endpoint=False) if SUAVIZAR_CURVAS else horas

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.5, 7.8), sharex=True)

    cores = {'sem_gd': '#e53e3e', 'com_gd': '#dd6b20', 'bateria': '#2b6cb0'}
    estilos = {'sem_gd': '--', 'com_gd': '-', 'bateria': '-'}
    labels = {
        'sem_gd': '1. Sem GD (Caso Base)',
        'com_gd': '2. Com GD Solar 2026',
        'bateria': '3. Com GD + Bateria BESS'
    }

    # Gráfico 1: Curva de Potência Ativa (P)
    for c, res in resultados.items():
        p_plot = np.clip(PchipInterpolator(horas, res['p_net'])(h_plot), None, None) if SUAVIZAR_CURVAS else res['p_net']
        ax1.plot(h_plot, p_plot, label=labels.get(c, c), color=cores.get(c, 'black'), linestyle=estilos.get(c, '-'), linewidth=2.2)

    ax1.axhline(0, color='gray', linestyle=':', alpha=0.7, label='Zero (Fluxo Reverso se < 0)')
    ax1.axhline(pot_nom, color='#718096', linestyle='-.', alpha=0.8, label=f'Potência Nominal ({pot_nom:.0f} kVA)')
    ax1.set_ylabel('Potência Líquida no Trafo (kW)', fontsize=11, fontweight='bold')
    ax1.set_title(f'Desempenho Diário do Trafo UNTRMT_{cod_id_str} ({pot_nom:.0f} kVA) - Comparativo TCC', fontsize=12, fontweight='bold', pad=10)
    ax1.grid(True, linestyle='--', alpha=0.6)
    # Legenda compacta posicionada à direita fora da área de curvas para não sobrepor o pico noturno
    ax1.legend(bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=8.5, framealpha=0.95, edgecolor='#cbd5e1')

    # Gráfico 2: Tensão no Secundário (PU)
    for c, res in resultados.items():
        v_plot = PchipInterpolator(horas, res['v1_pu'])(h_plot) if SUAVIZAR_CURVAS else res['v1_pu']
        ax2.plot(h_plot, v_plot, label=labels.get(c, c), color=cores.get(c, 'black'), linestyle=estilos.get(c, '-'), linewidth=2.0)

    ax2.axhline(0.93, color='#e53e3e', linestyle=':', label='Limite Mínimo ANEEL (0.93 PU)')
    ax2.axhline(1.05, color='#e53e3e', linestyle=':', label='Limite Máximo ANEEL (1.05 PU)')
    ax2.set_xlabel('Hora do Dia (h)', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Tensão no Secundário (PU)', fontsize=11, fontweight='bold')
    ax2.set_ylim(0.92, 1.06)
    ax2.set_xticks(np.arange(0, 25, 2))
    ax2.grid(True, linestyle='--', alpha=0.6)
    # Legenda compacta posicionada à direita fora da área de curvas para não sobrepor a tensão base
    ax2.legend(bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=8.5, framealpha=0.95, edgecolor='#cbd5e1')

    plt.tight_layout()
    caminho_grafico = os.path.join(GRAFICOS_DIR, f"Trafo_{cod_id_str}_estudo_gd_bateria.svg")
    caminho_png = os.path.join(GRAFICOS_DIR, f"Trafo_{cod_id_str}_estudo_gd_bateria.png")
    plt.savefig(caminho_grafico, format='svg', bbox_inches='tight')
    plt.savefig(caminho_png, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"\n[GRÁFICO SALVO] Gráfico com as curvas comparativas do TCC salvo em:\n  -> '{caminho_grafico}'\n  -> '{caminho_png}'")

    # Gerar Mapa Físico Interativo (Satélite / Ruas) e Mapa Vetorial SVG
    gerar_mapas_geograficos(cod_id_str, tr_match.iloc[0], linhas_bt, cargas_bt, gds_bt, cenario, bess_kw, bess_kwh)


def parse_wkt_multilinestring(wkt):
    if pd.isna(wkt) or not isinstance(wkt, str):
        return []
    matches = re.findall(r'([-]?\d+\.\d+)\s+([-]?\d+\.\d+)', wkt)
    return [(float(lat), float(lon)) for lon, lat in matches]


def parse_wkt_points(wkt):
    if pd.isna(wkt) or not isinstance(wkt, str):
        return []
    matches = re.findall(r'([-]?\d+\.\d+)\s+([-]?\d+\.\d+)', wkt)
    return [(float(lon), float(lat)) for lon, lat in matches]


def gerar_mapas_geograficos(cod_id_str, row_tr, linhas_bt, cargas_bt, gds_bt, cenario='comparativo', bess_kw=None, bess_kwh=None):
    lat_tr = float(row_tr['latitude'])
    lon_tr = float(row_tr['longitude'])
    pot_nom = float(row_tr['POT_NOM'])
    ctmt = str(row_tr['CTMT'])
    pot_gd_total = gds_bt['POT_INST'].sum() if not gds_bt.empty else 0.0

    # 1. Mapa Físico Interativo (Folium / Leaflet com Satélite e Ruas)
    m = folium.Map(
        location=[lat_tr, lon_tr],
        zoom_start=18,
        tiles=None
    )
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',
        name='🛰️ Satélite Real (Esri)',
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles='OpenStreetMap',
        name='🗺️ Mapa de Ruas (OpenStreetMap)',
        overlay=False,
        control=True
    ).add_to(m)

    all_lats, all_lons = [lat_tr], [lon_tr]
    pac_coords = {}
    fg_linhas = folium.FeatureGroup(name=f'⚡ Rede de Baixa Tensão ({len(linhas_bt)} trechos)', show=True)

    for _, l in linhas_bt.iterrows():
        coords = parse_wkt_multilinestring(l.get('geometria_wkt'))
        if coords:
            for lat, lon in coords:
                all_lats.append(lat)
                all_lons.append(lon)
            if len(coords) >= 2:
                pac_coords[str(l['PAC_1'])] = coords[0]
                pac_coords[str(l['PAC_2'])] = coords[-1]
                pn1 = str(l.get('PN_CON_1', ''))
                pn2 = str(l.get('PN_CON_2', ''))
                if pn1: pac_coords[pn1] = coords[0]
                if pn2: pac_coords[pn2] = coords[-1]
            folium.PolyLine(
                locations=coords,
                color='#00d2d3',
                weight=4.5,
                opacity=0.9,
                tooltip=f"Trecho BT: {l['COD_ID']} | Fase: {l.get('FAS_CON', 'BT')} | Comp: {l.get('COMP', 0):.1f}m"
            ).add_to(fg_linhas)
    fg_linhas.add_to(m)

    popup_tr = f"""
    <div style="font-family: Arial, sans-serif; min-width: 240px; font-size: 13px;">
        <h4 style="margin: 0 0 8px 0; color: #d63031; border-bottom: 2px solid #d63031; padding-bottom: 4px;">
            ⚡ Transformador UNTRMT_{cod_id_str}
        </h4>
        <b>Potência Nominal:</b> {pot_nom:.1f} kVA<br>
        <b>Alimentador MT:</b> {ctmt}<br>
        <b>Clientes Conectados:</b> {len(cargas_bt)} UCs<br>
        <b>Usinas GD Solar (2026):</b> {len(gds_bt)} unidades<br>
        <b>Potência Solar Total:</b> <span style="color: #27ae60; font-weight: bold;">{pot_gd_total:.2f} kW</span><br>
        <b>Penetração Solar:</b> {(pot_gd_total/pot_nom)*100:.1f}%<br>
        <b>Coordenadas:</b> {lat_tr:.6f}, {lon_tr:.6f}
    </div>
    """
    folium.Marker(
        location=[lat_tr, lon_tr],
        popup=folium.Popup(popup_tr, max_width=320),
        tooltip=f"⚡ Transformador UNTRMT_{cod_id_str} ({pot_nom:.0f} kVA)",
        icon=folium.Icon(color='red', icon='bolt', prefix='fa')
    ).add_to(m)

    if not gds_bt.empty:
        fg_gd = folium.FeatureGroup(name=f'☀️ Usinas GD Solar ({len(gds_bt)} un - {pot_gd_total:.1f} kW)', show=True)
        idx_offset = 0
        for _, g in gds_bt.iterrows():
            pac_g = str(g['PAC']).lstrip('R')
            pn_g = str(g.get('PN_CON', ''))
            if pac_g in pac_coords:
                coord_gd = pac_coords[pac_g]
            elif pn_g in pac_coords:
                coord_gd = pac_coords[pn_g]
            else:
                idx_offset += 1
                coord_gd = (lat_tr + (idx_offset % 5 - 2) * 0.00012, lon_tr + (idx_offset // 5 - 2) * 0.00012)

            popup_gd = f"""
            <div style="font-family: Arial, sans-serif; min-width: 220px; font-size: 13px;">
                <h4 style="margin: 0 0 6px 0; color: #f39c12; border-bottom: 2px solid #f39c12; padding-bottom: 4px;">
                    ☀️ Microgerador Solar Fotovoltaico
                </h4>
                <b>Código ANEEL (CEG):</b> {g['CEG_GD']}<br>
                <b>Potência Instalada:</b> <span style="color: #27ae60; font-weight: bold;">{float(g['POT_INST']):.2f} kW</span><br>
                <b>Fase Conexão:</b> {g.get('FAS_CON', 'BT')}<br>
                <b>Bairro:</b> {g.get('BRR', 'N/A')}<br>
                <b>Data Conexão:</b> {g.get('DAT_CON', 'N/A')}
            </div>
            """
            folium.Marker(
                location=coord_gd,
                popup=folium.Popup(popup_gd, max_width=300),
                tooltip=f"☀️ GD Solar: {g['CEG_GD']} ({float(g['POT_INST']):.1f} kW)",
                icon=folium.Icon(color='orange', icon='sun-o', prefix='fa')
            ).add_to(fg_gd)
        fg_gd.add_to(m)

    if cenario in ['bateria', 'comparativo']:
        kw_b = bess_kw if bess_kw else max(25.0, round(pot_nom * 0.25, 1))
        kwh_b = bess_kwh if bess_kwh else round(kw_b * 3.0, 1)
        popup_bess = f"""
        <div style="font-family: Arial, sans-serif; min-width: 220px; font-size: 13px;">
            <h4 style="margin: 0 0 6px 0; color: #27ae60; border-bottom: 2px solid #27ae60; padding-bottom: 4px;">
                🔋 Sistema de Baterias (BESS)
            </h4>
            <b>Potência Nominal:</b> {kw_b:.1f} kW<br>
            <b>Capacidade de Armazenamento:</b> {kwh_b:.1f} kWh<br>
            <b>Ponto de Conexão:</b> Barramento Secundário BT do Trafo<br>
            <b>Estratégia:</b> Absorve pico solar (10h-14h) e injeta no pico noturno (18h-21h)
        </div>
        """
        folium.Marker(
            location=[lat_tr + 0.00004, lon_tr + 0.00004],
            popup=folium.Popup(popup_bess, max_width=300),
            tooltip=f"🔋 Bateria BESS ({kw_b:.0f} kW / {kwh_b:.0f} kWh)",
            icon=folium.Icon(color='green', icon='battery-full', prefix='fa')
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    plugins.Fullscreen(position='topright').add_to(m)
    if len(all_lats) > 1:
        m.fit_bounds([[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]])

    caminho_html = os.path.join(GRAFICOS_DIR, f"Trafo_{cod_id_str}_mapa_fisico.html")
    m.save(caminho_html)
    print(f"[MAPA FÍSICO INTERATIVO] Salvo em Satélite Real e Ruas:\n  -> '{caminho_html}'")

    # 2. Mapa Geográfico Vetorial Estático (SVG de alta resolução para TCC)
    fig, ax = plt.subplots(figsize=(10, 8))
    for _, l in linhas_bt.iterrows():
        pts = parse_wkt_points(l.get('geometria_wkt'))
        if len(pts) >= 2:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.plot(xs, ys, color='#2b6cb0', linewidth=2.5, alpha=0.85, zorder=2)
            ax.scatter(xs, ys, color='#718096', s=20, zorder=3)

    if not gds_bt.empty:
        idx = 0
        for _, g in gds_bt.iterrows():
            pac_g = str(g['PAC']).lstrip('R')
            pn_g = str(g.get('PN_CON', ''))
            if pac_g in pac_coords:
                coord = (pac_coords[pac_g][1], pac_coords[pac_g][0])
            elif pn_g in pac_coords:
                coord = (pac_coords[pn_g][1], pac_coords[pn_g][0])
            else:
                idx += 1
                coord = (lon_tr + (idx % 5 - 2) * 0.00012, lat_tr + (idx // 5 - 2) * 0.00012)
            ax.scatter(coord[0], coord[1], color='#d69e2e', edgecolors='#744210', s=130, marker='*', zorder=5)

    ax.scatter(lon_tr, lat_tr, color='#e53e3e', edgecolors='black', s=220, marker='s', zorder=6)
    if cenario in ['bateria', 'comparativo']:
        ax.scatter(lon_tr + 0.00004, lat_tr + 0.00004, color='#38a169', edgecolors='black', s=180, marker='^', zorder=7)

    ax.set_title(
        f"Malha Geográfica de Baixa Tensão - Trafo UNTRMT_{cod_id_str} ({pot_nom:.0f} kVA)\n"
        f"Alimentador MT {ctmt} | {len(cargas_bt)} Consumidores | {len(gds_bt)} Usinas GD Solar ({pot_gd_total:.1f} kW)",
        fontsize=11, fontweight='bold'
    )
    ax.set_xlabel("Longitude (graus)", fontsize=10)
    ax.set_ylabel("Latitude (graus)", fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.5)

    leg_trafo = mlines.Line2D([], [], color='#e53e3e', marker='s', markersize=9, markeredgecolor='black', linestyle='None', label=f'Transformador MT/BT ({pot_nom:.0f} kVA)')
    leg_linha = mlines.Line2D([], [], color='#2b6cb0', linewidth=2.5, label=f'Rede Aérea BT ({len(linhas_bt)} trechos)')
    leg_gd = mlines.Line2D([], [], color='#d69e2e', marker='*', markersize=11, markeredgecolor='#744210', linestyle='None', label=f'Usinas GD Solar ({len(gds_bt)} un - {pot_gd_total:.1f} kW)')
    handles = [leg_trafo, leg_linha, leg_gd]
    if cenario in ['bateria', 'comparativo']:
        leg_bat = mlines.Line2D([], [], color='#38a169', marker='^', markersize=9, markeredgecolor='black', linestyle='None', label=f'Bateria BESS ({bess_kw if bess_kw else pot_nom*0.25:.0f} kW)')
        handles.append(leg_bat)

    ax.legend(handles=handles, loc='best', fontsize=8.5, framealpha=0.92, edgecolor='#cbd5e1')
    plt.tight_layout()
    caminho_svg = os.path.join(GRAFICOS_DIR, f"Trafo_{cod_id_str}_mapa_geografico.svg")
    caminho_png = os.path.join(GRAFICOS_DIR, f"Trafo_{cod_id_str}_mapa_geografico.png")
    plt.savefig(caminho_svg, format='svg', bbox_inches='tight')
    plt.savefig(caminho_png, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"[MAPA VETORIAL SVG/PNG] Salvo para relatório do TCC:\n  -> '{caminho_svg}'\n  -> '{caminho_png}'\n")


if __name__ == "__main__":
    t_inicio = time.time()
    parser = argparse.ArgumentParser(description="Simulador de Transformador com GD Solar 2026 e Baterias (BESS).")
    parser.add_argument("--trafo", type=str, default=None, help="COD_ID do transformador (ex: 5459374)")
    parser.add_argument("--cenario", type=str, default=CENARIO_PADRAO, choices=['comparativo', 'com-gd', 'sem-gd', 'bateria'],
                        help="Cenário de simulação: comparativo, com-gd, sem-gd, bateria (default: comparativo)")
    parser.add_argument("--top-gd", action="store_true", help="Lista os transformadores com mais GD fotovoltaica em 2026")
    parser.add_argument("--top-cargas", action="store_true", help="Lista os transformadores com maior número de clientes")
    parser.add_argument("--bess-kw", type=float, default=None, help="Potência do BESS em kW (ex: 100)")
    parser.add_argument("--bess-kwh", type=float, default=None, help="Capacidade do BESS em kWh (ex: 300)")

    args = parser.parse_args()

    if args.top_gd:
        untrmt, eqtrmt, ssdbt, ucbt, ugbt, segcon, crvcrg, dict_ten = carregar_bases()
        listar_top_gd(ugbt, untrmt, top=15)
    elif args.top_cargas:
        untrmt, eqtrmt, ssdbt, ucbt, ugbt, segcon, crvcrg, dict_ten = carregar_bases()
        listar_top_cargas(untrmt, ucbt, top=15)
    else:
        trafo_alvo = args.trafo if args.trafo is not None else COD_ID_TRAFO
        simular_trafo(trafo_alvo, cenario=args.cenario, bess_kw=args.bess_kw, bess_kwh=args.bess_kwh)

    tempo_total = time.time() - t_inicio
    minutos = int(tempo_total // 60)
    segundos = tempo_total % 60
    print("\n" + "=" * 70)
    if minutos > 0:
        print(f"[TEMPO DE EXECUÇÃO] Simulação concluída em {minutos}m {segundos:.2f}s ({tempo_total:.2f} s)!")
    else:
        print(f"[TEMPO DE EXECUÇÃO] Simulação concluída em {segundos:.2f} segundos!")
    print("=" * 70 + "\n")
