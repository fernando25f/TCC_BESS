"""
================================================================================
SIMULADOR INDIVIDUAL DOS TRANSFORMADORES DE FORÇA DA SUBESTAÇÃO (AT/MT)
Subestação Goiânia Leste (230 / 13,8 kV - 50 MVA cada)
COM SUPORTE A GERAÇÃO DISTRIBUÍDA (2026) E BATERIAS (BESS)
================================================================================
Permite simular o comportamento elétrico e geográfico de um ÚNICO transformador
de força da Subestação Goiânia Leste (TR1, TR2, TR3 ou TR4) sob 3 cenários do TCC:
  1. SEM GD: Apenas a curva de carga convencional (Caso Base)
  2. COM GD: Inclusão das usinas fotovoltaicas (UGBT e UGMT) de 2026
  3. COM BATERIA (BESS): Armazenamento de energia mitigando sobrecarga e pico
  4. COMPARATIVO: Simula os 3 cenários e plota gráficos comparativos sobrepostos!

Recursos incluídos:
  - Fluxo de potência diário quase-estático (24h - 96 passos de 15 min)
  - Curvas de Potência Ativa (MW), Aparente (MVA), Carregamento (%) e Tensão (PU)
  - Perfil de demanda individual de cada alimentador do transformador
  - MAPA GEOGRÁFICO VETORIAL (SVG/PNG) com a malha da rede, alimentadores, GDs e BESS
  - MAPA FÍSICO INTERATIVO (HTML Folium) com Satélite Real, alimentadores, GDs e BESS

Uso:
  python simular_trafo_subestacao.py --trafo TR1 --cenario comparativo
  python simular_trafo_subestacao.py --trafo TR2 --cenario com-gd
  python simular_trafo_subestacao.py --trafo TR3 --cenario bateria --bess-mw 15 --bess-mwh 45
  python simular_trafo_subestacao.py --trafo TR4 --cenario sem-gd
  python simular_trafo_subestacao.py --listar
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
# CONFIGURAÇÃO PADRÃO DO TRANSFORMADOR DA SUBESTAÇÃO ALVO E CENÁRIO
# ==============================================================================
# Escolha qual dos 4 transformadores de 50 MVA da SE Goiânia Leste deseja simular:
#   - "TR1" -> Barra 1783 (Alimenta Goiânia Leste 7, 8, 9, 10, 11 e 12)
#   - "TR2" -> Barra 4629 (Alimenta Goiânia Leste 13, 14, 15, 16, 17, 18, 19 e 20)
#   - "TR3" -> Barra 4630 (Alimenta Goiânia Leste 1, 2, 3, 4, 5 e 6)
#   - "TR4" -> Barra 6440 (Alimenta Goiânia Leste 21, 22, 23, 24, 25, 26 e 27)
TRAFO_SUBESTACAO = "TR3"

# Cenário de Simulação (TCC):
# Opções: 'comparativo', 'com-gd', 'sem-gd', 'bateria'
CENARIO_PADRAO = "comparativo"

# Dimensionamento padrão do BESS na Subestação (20% da potência do trafo de 50 MVA):
BESS_MW_PADRAO = 10.0   # 10.0 MW
BESS_MWH_PADRAO = 40.0  # 30.0 MWh (3 horas de autonomia em descarga máxima)

# Suavização contínua das curvas diárias (estilo artigo/TCC):
SUAVIZAR_CURVAS = True
# ==============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS_DIR = os.path.join(BASE_DIR, "dados_goiania_leste")
DICT_DIR = os.path.join(BASE_DIR, "dicionarios_bdgd")
GRAFICOS_DIR = os.path.join(BASE_DIR, "graficos")
SCRATCH_DIR = os.path.join(BASE_DIR, "scratch_dss")
os.makedirs(GRAFICOS_DIR, exist_ok=True)
os.makedirs(SCRATCH_DIR, exist_ok=True)

# Definição dos 4 transformadores de força da SE Goiânia Leste
CONFIG_TRAFOS_SE = {
    "TR1": {
        "nome_completo": "GOL-S-TRF-TR1",
        "barra_pri": "5001462",
        "barra_sec": "1783",
        "kv_pri": 230.0,
        "kv_sec": 13.8,
        "kva": 50000.0,
        "mva": 50.0,
        "xhl": 4.5,
        "loadloss": 0.278,
        "noloadloss": 0.037,
        "cor_tema": "#3498db"
    },
    "TR2": {
        "nome_completo": "GOL-S-TRF-TR2",
        "barra_pri": "5001462",
        "barra_sec": "4629",
        "kv_pri": 230.0,
        "kv_sec": 13.8,
        "kva": 50000.0,
        "mva": 50.0,
        "xhl": 4.5,
        "loadloss": 0.278,
        "noloadloss": 0.037,
        "cor_tema": "#9b59b6"
    },
    "TR3": {
        "nome_completo": "GOL-S-TRF-TR3",
        "barra_pri": "5001462",
        "barra_sec": "4630",
        "kv_pri": 230.0,
        "kv_sec": 13.8,
        "kva": 50000.0,
        "mva": 50.0,
        "xhl": 4.5,
        "loadloss": 0.278,
        "noloadloss": 0.037,
        "cor_tema": "#e67e22"
    },
    "TR4": {
        "nome_completo": "GOL-S-TRF-TR4",
        "barra_pri": "5001462",
        "barra_sec": "6440",
        "kv_pri": 230.0,
        "kv_sec": 13.8,
        "kva": 50000.0,
        "mva": 50.0,
        "xhl": 4.5,
        "loadloss": 0.278,
        "noloadloss": 0.037,
        "cor_tema": "#e74c3c"
    }
}

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

PALETA_ALIMENTADORES = [
    '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
    '#1abc9c', '#d35400', '#e84393', '#00cec9', '#fdcb6e'
]

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

# Curva de Despacho BESS da Subestação (96 pontos de 15 min):
# -1.0: Carga (10h00 às 14h15 - absorve excedente solar diurno na barra da SE)
# +1.0: Descarga (18h00 às 21h45 - alivia a ponta noturna, reduzindo o carregamento do trafo de 50 MVA)
MULT_BESS = [0.0] * 96
for h in range(40, 58):  # 10h00 às 14h15
    MULT_BESS[h] = -1.0
for h in range(72, 88):  # 18h00 às 21h45
    MULT_BESS[h] = 1.0


def parse_wkt_coords(wkt_str):
    if pd.isna(wkt_str) or not isinstance(wkt_str, str):
        return []
    coords = re.findall(r'([-]?\d+\.\d+)\s+([-]?\d+\.\d+)', wkt_str)
    return [(float(c[0]), float(c[1])) for c in coords]


def carregar_bases():
    print("Carregando bases de dados da Subestação Goiânia Leste e GD 2026...")
    df_sub = pd.read_csv(os.path.join(DADOS_DIR, "01_SUB_subestacao.csv"))
    df_ctmt = pd.read_csv(os.path.join(DADOS_DIR, "02_CTMT_alimentadores.csv"))
    df_segcon = pd.read_csv(os.path.join(DADOS_DIR, "06_SEGCON_condutores.csv"))
    df_ssdmt = pd.read_csv(os.path.join(DADOS_DIR, "04_SSDMT_linhas_MT.csv"))
    df_ssdbt = pd.read_csv(os.path.join(DADOS_DIR, "05_SSDBT_linhas_BT.csv"))
    df_untrmt = pd.read_csv(os.path.join(DADOS_DIR, "07a_UNTRMT_trafos_distribuicao.csv"))
    df_eqtrmt = pd.read_csv(os.path.join(DADOS_DIR, "07b_EQTRMT_dados_eletricos_trafos_dist.csv"))
    df_unsemt = pd.read_csv(os.path.join(DADOS_DIR, "15_UNSEMT_chaves_seccionadoras.csv"))
    df_uncrmt = pd.read_csv(os.path.join(DADOS_DIR, "13_UNCRMT_capacitores_MT.csv"))
    df_crvcrg = pd.read_csv(os.path.join(DADOS_DIR, "10_CRVCRG_curvas_de_carga.csv"))
    df_ucbt = pd.read_csv(os.path.join(DADOS_DIR, "08_UCBT_consumidores_BT.csv"), low_memory=False)
    df_ucmt = pd.read_csv(os.path.join(DADOS_DIR, "09_UCMT_consumidores_MT.csv"), low_memory=False)
    df_ugbt = pd.read_csv(os.path.join(DADOS_DIR, "11_UGBT_geracao_distribuida_BT.csv"), low_memory=False)
    df_ugmt = pd.read_csv(os.path.join(DADOS_DIR, "12_UGMT_geracao_distribuida_MT.csv"), low_memory=False)

    df_tten = pd.read_csv(os.path.join(DICT_DIR, "TTEN.csv"))
    dict_ten = dict(zip(df_tten['COD_ID'], df_tten['TEN'] / 1000.0))

    return {
        'sub': df_sub,
        'ctmt': df_ctmt,
        'segcon': df_segcon,
        'ssdmt': df_ssdmt,
        'ssdbt': df_ssdbt,
        'untrmt': df_untrmt,
        'eqtrmt': df_eqtrmt,
        'unsemt': df_unsemt,
        'uncrmt': df_uncrmt,
        'crvcrg': df_crvcrg,
        'ucbt': df_ucbt,
        'ucmt': df_ucmt,
        'ugbt': df_ugbt,
        'ugmt': df_ugmt,
        'dict_ten': dict_ten
    }


def listar_trafos_se(df_ctmt):
    print("\n" + "=" * 80)
    print("TRANSFORMADORES DE FORÇA DA SUBESTAÇÃO GOIÂNIA LESTE (230 / 13,8 kV - 50 MVA):")
    print("=" * 80)
    for chave, cfg in CONFIG_TRAFOS_SE.items():
        feeders = df_ctmt[df_ctmt['UNI_TR_AT'] == cfg['nome_completo']]
        nomes_f = [f"{r['NOME']} ({r['COD_ID']})" for _, r in feeders.iterrows()]
        print(f"[{chave}] -> {cfg['nome_completo']} | Barra MT: {cfg['barra_sec']} | Cap.: {cfg['mva']:.0f} MVA")
        print(f"       Alimentadores Atendidos ({len(feeders)}): {', '.join(nomes_f)}\n")
    print("=" * 80)


def simular_cenario_dss(cenario, tr_key, cfg, feeders_tr, ctmts, df_mt, df_trafos, df_bt,
                        df_ucbt, df_ucmt, df_ugbt, df_ugmt, df_se, df_cap, bases,
                        bess_mw=10.0, bess_mwh=30.0):
    """
    Constrói e executa no OpenDSS um cenário específico para o transformador da subestação:
      - 'sem_gd': apenas curvas de carga convencionais (Caso Base)
      - 'com_gd': inclusão das usinas fotovoltaicas (UGBT e UGMT) de 2026
      - 'bateria': inclusão da GD 2026 + Sistema BESS na barra 13.8 kV da SE
    """
    dict_r1 = dict(zip(bases['segcon']['COD_ID'], bases['segcon']['R1']))
    dict_x1 = dict(zip(bases['segcon']['COD_ID'], bases['segcon']['X1']))
    dict_cnom = dict(zip(bases['segcon']['COD_ID'], bases['segcon']['CNOM']))

    dict_eq_r = dict(zip(bases['eqtrmt']['UNI_TR_MT'], bases['eqtrmt']['R']))
    dict_eq_xhl = dict(zip(bases['eqtrmt']['UNI_TR_MT'], bases['eqtrmt']['XHL']))
    dict_ten = bases['dict_ten']

    dss_path = os.path.join(SCRATCH_DIR, f"Subestacao_{tr_key}_{cenario}.dss")

    with open(dss_path, "w", encoding="utf-8") as f:
        f.write(f"! ======================================================================\n")
        f.write(f"! MODELO SE GOIANIA LESTE - TRAFO {tr_key} ({cfg['nome_completo']})\n")
        f.write(f"! CENÁRIO: {cenario.upper()}\n")
        f.write(f"! ======================================================================\n")
        f.write("clear\n\n")

        # 1. Fonte equivalente de 230 kV
        f.write(f"new circuit.SE_Goiania_Leste_{tr_key} basekv={cfg['kv_pri']} bus1={cfg['barra_pri']} pu=1.05 phases=3\n\n")

        # 2. Curvas de Carga (Loadshapes)
        f.write("! Curvas de Carga Diarias ANEEL\n")
        cols_pot = [f"POT_{i:02d}" for i in range(1, 97)]
        horas_24 = np.arange(24)
        horas_96 = np.linspace(0, 24, 96, endpoint=False)

        for _, r_crv in bases['crvcrg'].iterrows():
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

        # Curva Solar e Curva BESS
        f.write(f"\nnew loadshape.Curva_Solar npts=96 interval=0.25 mult=({' '.join(f'{v:.4f}' for v in MULT_SOLAR)})\n")
        f.write(f"new loadshape.Curva_BESS npts=96 interval=0.25 mult=({' '.join(f'{v:.4f}' for v in MULT_BESS)})\n\n")

        # 3. Transformador de Força da Subestação (230 / 13,8 kV - 50 MVA)
        f.write("! Transformador de Forca da Subestacao (230 / 13.8 kV)\n")
        f.write(
            f"new transformer.{cfg['nome_completo']} phases=3 xhl={cfg['xhl']} windings=2 "
            f"%loadloss={cfg['loadloss']} %noloadloss={cfg['noloadloss']} kva={cfg['kva']}\n"
            f"~ wdg=1 bus={cfg['barra_pri']} conn=delta kv={cfg['kv_pri']}\n"
            f"~ wdg=2 bus={cfg['barra_sec']} conn=wye kv={cfg['kv_sec']}\n\n"
        )

        # 4. Disjuntores na cabeça dos alimentadores (ligando a barra 13.8 kV ao PAC inicial)
        f.write("! Disjuntores dos Alimentadores de MT\n")
        for _, r_f in feeders_tr.iterrows():
            fid = r_f['COD_ID']
            pac_ini = r_f['PAC_INI']
            f.write(f"new line.DJ_{fid} phases=3 bus1={cfg['barra_sec']} bus2={pac_ini} switch=y r1=1e-4 x1=1e-4 length=0.001 units=km\n")
        f.write("\n")

        # 5. Chaves Seccionadoras de MT
        f.write("! Chaves Seccionadoras de MT\n")
        for r_s in df_se.itertuples():
            f.write(f"new line.SC_{r_s.COD_ID} phases=3 bus1={r_s.PAC_1} bus2={r_s.PAC_2} switch=y r1=1e-4 x1=1e-4 length=0.001 units=km\n")
            if r_s.P_N_OPE == 'A':
                f.write(f"open line.SC_{r_s.COD_ID} 1\n")
        f.write("\n")

        # 6. Linhas de Média Tensão
        f.write("! Linhas de Media Tensao (13.8 kV)\n")
        for r_l in df_mt.itertuples():
            f_info = MAPA_FASES.get(r_l.FAS_CON, ('.1.2.3', 3, 'delta'))
            b1 = str(r_l.PAC_1) + f_info[0]
            b2 = str(r_l.PAC_2) + f_info[0]
            r1 = dict_r1.get(r_l.TIP_CND, 0.5)
            x1 = dict_x1.get(r_l.TIP_CND, 0.4)
            comp = max(0.001, round(r_l.COMP / 1000.0, 6))
            cnom = dict_cnom.get(r_l.TIP_CND, 200)
            f.write(f"new line.{r_l.COD_ID} phases={f_info[1]} bus1={b1} bus2={b2} r1={r1} x1={x1} length={comp} units=km normamps={cnom}\n")
        f.write("\n")

        # 7. Bancos de Capacitores de MT
        if not df_cap.empty:
            f.write("! Bancos de Capacitores MT\n")
            for r_c in df_cap.itertuples():
                f_info = MAPA_FASES.get(r_c.FAS_CON, ('.1.2.3', 3, 'wye'))
                b_c = str(r_c.PAC_1).lstrip('R') + f_info[0]
                f.write(f"new capacitor.{r_c.COD_ID} phases={f_info[1]} bus1={b_c} conn=wye kv=13.8 kvar={r_c.POT_NOM}\n")
            f.write("\n")

        # 8. Transformadores de Distribuição (MT/BT)
        f.write("! Transformadores de Distribuicao MT/BT\n")
        for r_t in df_trafos.itertuples():
            fp = MAPA_FASES.get(r_t.FAS_CON_P, ('.1.2.3', 3, 'delta'))
            fs = MAPA_FASES.get(r_t.FAS_CON_S, ('.1.2.3.0', 3, 'wye'))
            phases = fp[1]
            b1 = str(r_t.PAC_1) + fp[0]
            b2 = str(r_t.PAC_2) + fs[0]
            r = dict_eq_r.get(r_t.COD_ID, 1.0)
            xhl = dict_eq_xhl.get(r_t.COD_ID, 4.0)
            if phases == 3:
                kv1 = 13.8
                kv2 = 0.38
                conn1 = 'delta'
            else:
                kv1 = 7.96
                kv2 = 0.22
                conn1 = 'wye'
            f.write(f"new transformer.UNTRMT_{r_t.COD_ID} phases={phases} windings=2 %r={r} xhl={xhl} kva={r_t.POT_NOM}\n")
            f.write(f"~ wdg=1 bus={b1} conn={conn1} kv={kv1}\n")
            f.write(f"~ wdg=2 bus={b2} conn=wye kv={kv2}\n")
        f.write("\n")

        # 9. Linhas de Baixa Tensão
        f.write("! Linhas de Baixa Tensao (380 / 220 V)\n")
        for r_b in df_bt.itertuples():
            f_info = MAPA_FASES.get(r_b.FAS_CON, ('.1.2.3.0', 3, 'delta'))
            b1 = str(r_b.PAC_1) + f_info[0]
            b2 = str(r_b.PAC_2) + f_info[0]
            r1 = min(5.0, dict_r1.get(r_b.TIP_CND, 0.5))
            x1 = min(2.0, dict_x1.get(r_b.TIP_CND, 0.4))
            comp = max(0.001, round(r_b.COMP / 1000.0, 6))
            cnom = dict_cnom.get(r_b.TIP_CND, 100)
            f.write(f"new line.{r_b.COD_ID} phases={f_info[1]} bus1={b1} bus2={b2} r1={r1} x1={x1} length={comp} units=km normamps={cnom}\n")
        f.write("\n")

        # 10. Cargas BT
        f.write("! Consumidores de Baixa Tensao\n")
        pacs_bt_validos = set(df_bt['PAC_1'].astype(str)) | set(df_bt['PAC_2'].astype(str)) | set(df_trafos['PAC_2'].astype(str))
        dict_pac2_trafo = dict(zip(df_trafos['COD_ID'].astype(str), df_trafos['PAC_2'].astype(str)))

        for r_uc in df_ucbt.itertuples():
            cid = r_uc.COD_ID
            pn_con = str(r_uc.PN_CON)
            uni_tr = str(r_uc.UNI_TR_MT)
            pac_c = str(r_uc.PAC).lstrip('R')
            b_det = pn_con + uni_tr

            if b_det in pacs_bt_validos:
                b_alvo = b_det
            elif pac_c in pacs_bt_validos:
                b_alvo = pac_c
            else:
                b_alvo = dict_pac2_trafo.get(uni_tr, pac_c)

            f_info = MAPA_FASES.get(r_uc.FAS_CON, ('.1.2.3.0', 3, 'delta'))
            b_carga = b_alvo + f_info[0]
            kw = max(0.05, float(r_uc.CAR_INST) * 0.11)
            kv = dict_ten.get(r_uc.TEN_FORN, 0.22 if f_info[1] == 1 else 0.38)
            f.write(f"new load.UC_{cid} phases={f_info[1]} model=1 bus={b_carga} kv={kv} kw={kw:.3f} daily={r_uc.TIP_CC} vminpu=0.75\n")
        f.write("\n")

        # 11. Cargas MT
        f.write("! Consumidores de Media Tensao\n")
        for r_ucm in df_ucmt.itertuples():
            f_info = MAPA_FASES.get(r_ucm.FAS_CON, ('.1.2.3', 3, 'delta'))
            b_carga = str(r_ucm.PAC).lstrip('R') + f_info[0]
            kw = max(0.5, float(r_ucm.CAR_INST) * 0.15)
            f.write(f"new load.UCMT_{r_ucm.COD_ID} phases={f_info[1]} bus={b_carga} kv=13.8 kw={kw:.3f} daily={r_ucm.TIP_CC} vminpu=0.85\n")
        f.write("\n")

        # 12. Geração Distribuída Fotovoltaica (GD 2026)
        if cenario in ['com_gd', 'bateria']:
            f.write("! Geracao Distribuida em Baixa Tensao (UGBT - PVSYSTEM 2026)\n")
            for r_ug in df_ugbt.itertuples():
                cid = r_ug.COD_ID
                pn_con = str(r_ug.PN_CON)
                uni_tr = str(r_ug.UNI_TR_MT)
                pac_c = str(r_ug.PAC).lstrip('R')
                b_det = pn_con + uni_tr

                if b_det in pacs_bt_validos:
                    b_alvo = b_det
                elif pac_c in pacs_bt_validos:
                    b_alvo = pac_c
                else:
                    b_alvo = dict_pac2_trafo.get(uni_tr, pac_c)

                f_info = MAPA_FASES.get(str(r_ug.FAS_CON).strip(), ('.1.2.3.0', 3, 'delta'))
                b_gd = b_alvo + f_info[0]
                pot_kw = float(r_ug.POT_INST) if pd.notna(r_ug.POT_INST) and float(r_ug.POT_INST) > 0 else 5.0
                kv = dict_ten.get(r_ug.TEN_CON, 0.22 if f_info[1] == 1 else 0.38)
                f.write(
                    f"new PVSystem.GD_UGBT_{cid} phases={f_info[1]} bus1={b_gd} kv={kv} conn=wye "
                    f"pmpp={pot_kw:.2f} kva={pot_kw:.2f} pf=1.0 irradiance=1.0 daily=Curva_Solar %cutin=0.1 %cutout=0.1\n"
                )

            f.write("\n! Geracao Distribuida em Media Tensao (UGMT - PVSYSTEM 2026)\n")
            pacs_mt_validos = set(df_mt['PAC_1'].astype(str)) | set(df_mt['PAC_2'].astype(str))
            for r_ugm in df_ugmt.itertuples():
                pac = str(r_ugm.PAC).strip()
                pac_limpo = pac.lstrip('R')
                if pac in pacs_mt_validos:
                    b_alvo = pac
                elif pac_limpo in pacs_mt_validos:
                    b_alvo = pac_limpo
                else:
                    continue

                f_info = MAPA_FASES.get(str(r_ugm.FAS_CON).strip(), ('.1.2.3', 3, 'delta'))
                b_gd = b_alvo + f_info[0]
                pot_kw = float(r_ugm.POT_INST) if pd.notna(r_ugm.POT_INST) and float(r_ugm.POT_INST) > 0 else 50.0
                f.write(
                    f"new PVSystem.GD_UGMT_{r_ugm.COD_ID} phases={f_info[1]} bus1={b_gd} kv=13.8 conn=wye "
                    f"pmpp={pot_kw:.2f} kva={pot_kw:.2f} pf=1.0 irradiance=1.0 daily=Curva_Solar %cutin=0.1 %cutout=0.1\n"
                )
            f.write("\n")

        # 13. Sistema de Armazenamento por Bateria na Subestação (BESS)
        if cenario == 'bateria':
            kw_bess = float(bess_mw) * 1000.0
            kwh_bess = float(bess_mwh) * 1000.0
            f.write("! Sistema de Armazenamento por Baterias na Subestacao (BESS)\n")
            f.write(
                f"new Storage.BESS_SE_{tr_key} phases=3 bus1={cfg['barra_sec']}.1.2.3 kv={cfg['kv_sec']} "
                f"kwrated={kw_bess:.1f} kwhrated={kwh_bess:.1f} %stored=10 dispmode=follow daily=Curva_BESS "
                f"%reserve=10 %charge=80 %discharge=80\n\n"
            )

        # 14. Monitores de Potência e Tensão
        f.write("! Monitores de Potencia e Tensao\n")
        f.write(f"new monitor.mon_trafo_se element=transformer.{cfg['nome_completo']} terminal=2 mode=1 ppolar=no\n")
        f.write(f"new monitor.mon_tensao_se element=transformer.{cfg['nome_completo']} terminal=2 mode=0\n")

        for _, r_f in feeders_tr.iterrows():
            fid = r_f['COD_ID']
            f.write(f"new monitor.mon_ctmt_{fid} element=line.DJ_{fid} terminal=1 mode=1 ppolar=no\n")

    # Compilar e Executar no OpenDSS
    dss.Command(f'compile "{dss_path}"')
    dss.Command('Set voltagebases=[230.0, 13.8, 0.38, 0.22]')
    dss.Command('Calcvoltagebases')
    dss.Command('Set maxiterations=50')
    dss.Command('BatchEdit Load..* vminpu=0.70')

    dss.Command("set mode=daily stepsize=15m number=1")
    for i in range(1, 97):
        tap = 1.025 if 69 <= i <= 88 else 1.0
        dss.Command(f"Transformer.{cfg['nome_completo']}.wdg=2 tap={tap}")
        dss.Command("solve")

    # Extrair grandezas do monitor do transformador de força
    dss.Monitors.Name("mon_trafo_se")
    p1 = np.nan_to_num(dss.Monitors.Channel(1), nan=0.0)
    p2 = np.nan_to_num(dss.Monitors.Channel(3), nan=0.0)
    p3 = np.nan_to_num(dss.Monitors.Channel(5), nan=0.0)
    q1 = np.nan_to_num(dss.Monitors.Channel(2), nan=0.0)
    q2 = np.nan_to_num(dss.Monitors.Channel(4), nan=0.0)
    q3 = np.nan_to_num(dss.Monitors.Channel(6), nan=0.0)

    dss.Monitors.Name("mon_tensao_se")
    v1 = np.nan_to_num(dss.Monitors.Channel(1), nan=0.0)

    # Potência que sai do trafo em direção à barra de 13.8 kV:
    # No OpenDSS terminal 2, -(p1+p2+p3) é positivo para suprimento da carga e negativo para injeção reversa na MT/AT
    p_mw = -(p1 + p2 + p3) / 1000.0
    q_mvar = -(q1 + q2 + q3) / 1000.0
    s_mva = np.sqrt(p_mw**2 + q_mvar**2)
    carreg_pct = (s_mva / cfg['mva']) * 100.0

    v_base_fn = (cfg['kv_sec'] * 1000.0) / math.sqrt(3)
    v_pu = np.clip(v1 / v_base_fn, 0.70, 1.15)

    # Coletar curvas e picos de cada alimentador
    curvas_feeders = {}
    dados_feeders = []
    for _, r_f in feeders_tr.iterrows():
        fid = r_f['COD_ID']
        fnome = r_f['NOME']
        mon_name = f"mon_ctmt_{fid}"
        try:
            dss.Monitors.Name(mon_name)
            mp1 = np.nan_to_num(dss.Monitors.Channel(1), nan=0.0)
            mp2 = np.nan_to_num(dss.Monitors.Channel(3), nan=0.0)
            mp3 = np.nan_to_num(dss.Monitors.Channel(5), nan=0.0)
            mq1 = np.nan_to_num(dss.Monitors.Channel(2), nan=0.0)
            mq2 = np.nan_to_num(dss.Monitors.Channel(4), nan=0.0)
            mq3 = np.nan_to_num(dss.Monitors.Channel(6), nan=0.0)
            f_p_mw = np.abs(mp1 + mp2 + mp3) / 1000.0
            f_q_mvar = np.abs(mq1 + mq2 + mq3) / 1000.0
            f_s_mva = np.sqrt(f_p_mw**2 + f_q_mvar**2)
            curvas_feeders[fnome] = f_s_mva

            f_s_pico = float(np.max(f_s_mva))
            f_p_pico = float(np.max(f_p_mw))
            f_idx = int(np.argmax(f_s_mva))
            f_hora = f"{int(f_idx * 15 / 60):02d}:{int((f_idx * 15) % 60):02d}"

            dados_feeders.append({
                'Alimentador': fnome,
                'COD_ID': fid,
                'P_Pico_MW': f_p_pico,
                'S_Pico_MVA': f_s_pico,
                'Hora_Pico': f_hora,
                'Pct_Trafo': (f_s_pico / cfg['mva']) * 100.0
            })
        except Exception:
            pass

    return {
        'p_mw': p_mw,
        'q_mvar': q_mvar,
        's_mva': s_mva,
        'carreg_pct': carreg_pct,
        'v_pu': v_pu,
        'p_pico_mw': float(np.max(p_mw)),
        's_pico_mva': float(np.max(s_mva)),
        'carreg_max': float(np.max(carreg_pct)),
        'hora_pico': f"{int(np.argmax(s_mva) * 15 / 60):02d}:{int((np.argmax(s_mva) * 15) % 60):02d}",
        'curvas_feeders': curvas_feeders,
        'dados_feeders': dados_feeders
    }


def simular_trafo_se(tr_key, bases, cenario='comparativo', bess_mw=None, bess_mwh=None):
    tr_key = tr_key.upper().strip()
    if tr_key not in CONFIG_TRAFOS_SE:
        print(f"[ERRO] Transformador '{tr_key}' inválido! Escolha entre TR1, TR2, TR3 ou TR4.")
        return

    cfg = CONFIG_TRAFOS_SE[tr_key]
    df_ctmt = bases['ctmt']
    feeders_tr = df_ctmt[df_ctmt['UNI_TR_AT'] == cfg['nome_completo']]
    ctmts = [str(c).strip() for c in feeders_tr['COD_ID']]

    # Filtrar elementos que pertencem aos alimentadores deste transformador da SE
    df_mt = bases['ssdmt'][bases['ssdmt']['CTMT'].astype(str).isin(ctmts)]
    df_trafos = bases['untrmt'][bases['untrmt']['CTMT'].astype(str).isin(ctmts)]
    trafos_ids = set(df_trafos['COD_ID'].astype(str))

    df_bt = bases['ssdbt'][bases['ssdbt']['UNI_TR_MT'].astype(str).isin(trafos_ids)]
    df_ucbt = bases['ucbt'][bases['ucbt']['UNI_TR_MT'].astype(str).isin(trafos_ids)]
    df_ucmt = bases['ucmt'][bases['ucmt']['CTMT'].astype(str).isin(ctmts)]
    df_ugbt = bases['ugbt'][bases['ugbt']['UNI_TR_MT'].astype(str).isin(trafos_ids)]
    df_ugmt = bases['ugmt'][bases['ugmt']['CTMT'].astype(str).isin(ctmts)]
    df_se = bases['unsemt'][bases['unsemt']['CTMT'].astype(str).isin(ctmts)]
    df_cap = bases['uncrmt'][bases['uncrmt']['CTMT'].astype(str).isin(ctmts)]

    pot_gd_bt_mw = df_ugbt['POT_INST'].sum() / 1000.0 if not df_ugbt.empty else 0.0
    pot_gd_mt_mw = df_ugmt['POT_INST'].sum() / 1000.0 if not df_ugmt.empty else 0.0
    pot_gd_total_mw = pot_gd_bt_mw + pot_gd_mt_mw

    # Dimensionamento do BESS (padrão: 10 MW / 30 MWh se não especificado)
    kw_bess_mw = float(bess_mw) if bess_mw is not None else BESS_MW_PADRAO
    kwh_bess_mwh = float(bess_mwh) if bess_mwh is not None else BESS_MWH_PADRAO

    print("\n" + "=" * 85)
    print(f"ESTUDO DO TRANSFORMADOR DE FORÇA DA SUBESTAÇÃO: {tr_key} ({cfg['nome_completo']})")
    print("=" * 85)
    print(f"  * Capacidade Nominal:             {cfg['mva']:.0f} MVA (50.000 kVA)")
    print(f"  * Relação de Transformação:       {cfg['kv_pri']:.0f} kV / {cfg['kv_sec']:.1f} kV")
    print(f"  * Barra Primária (230 kV):        {cfg['barra_pri']}")
    print(f"  * Barra Secundária MT:             {cfg['barra_sec']}")
    print(f"  * Alimentadores Atendidos:        {len(feeders_tr)}")
    print(f"  * Linhas de Média Tensão:          {len(df_mt):,}")
    print(f"  * Transformadores MT/BT:           {len(df_trafos):,}")
    print(f"  * Linhas de Baixa Tensão:          {len(df_bt):,}")
    print(f"  * Consumidores Atendidos:          {len(df_ucbt):,} BT e {len(df_ucmt)} MT")
    print(f"  * Geração Distribuída (2026):      {len(df_ugbt):,} usinas BT ({pot_gd_bt_mw:.2f} MW) + {len(df_ugmt)} usinas MT ({pot_gd_mt_mw:.2f} MW)")
    print(f"  * Potência GD Total:               {pot_gd_total_mw:.2f} MW ({(pot_gd_total_mw/cfg['mva'])*100:.1f}% da capacidade do trafo)")
    print(f"  * Sistema BESS Subestação:         {kw_bess_mw:.1f} MW / {kwh_bess_mwh:.1f} MWh (Conexão: Barra MT {cfg['barra_sec']})")
    print(f"  * Modo de Simulação Selecionado:   {cenario.upper()}")
    print("=" * 85)

    cenarios_a_rodar = ['sem_gd', 'com_gd', 'bateria'] if cenario == 'comparativo' else [cenario.replace('-', '_')]
    resultados = {}

    for c in cenarios_a_rodar:
        print(f" -> Simulando cenário [{c.upper()}] no OpenDSS (96 passos de 15 min)...")
        resultados[c] = simular_cenario_dss(
            c, tr_key, cfg, feeders_tr, ctmts, df_mt, df_trafos, df_bt,
            df_ucbt, df_ucmt, df_ugbt, df_ugmt, df_se, df_cap, bases,
            kw_bess_mw, kwh_bess_mwh
        )

    # Tabela Resumo Executiva dos Cenários
    print("\n" + "=" * 98)
    print(f"{'CENÁRIO':<16} | {'P_PICO (MW)':<12} | {'S_PICO (MVA)':<12} | {'CARREG_MAX':<12} | {'P_MEIO-DIA (MW)':<16} | {'FLUXO REVERSO?':<15} | {'V_MIN/V_MAX (PU)':<16}")
    print("-" * 98)
    for c, res in resultados.items():
        p_pico = res['p_pico_mw']
        s_pico = res['s_pico_mva']
        carreg_max = res['carreg_max']
        p_meio_dia = res['p_mw'][48]  # 12h00
        fluxo_rev = "SIM (Injeção)" if min(res['p_mw']) < 0 else "NÃO"
        v_min = min(res['v_pu'])
        v_max = max(res['v_pu'])
        print(f"{c.upper():<16} | {p_pico:<12.2f} | {s_pico:<12.2f} | {carreg_max:<11.1f}% | {p_meio_dia:<16.2f} | {fluxo_rev:<15} | {v_min:.3f} / {v_max:.3f}")
    print("=" * 98)

    # Detalhamento dos Alimentadores (do cenário com maior detalhe disponível)
    cenario_ref = 'bateria' if 'bateria' in resultados else ('com_gd' if 'com_gd' in resultados else 'sem_gd')
    df_res_feeders = pd.DataFrame(resultados[cenario_ref]['dados_feeders']).sort_values(by='S_Pico_MVA', ascending=False)

    print(f"\nDETALHAMENTO DOS ALIMENTADORES ATENDIDOS PELO {tr_key} (CENÁRIO: {cenario_ref.upper()}):")
    print(f"{'Alimentador':<20} | {'COD_ID':<10} | {'P Pico (MW)':<12} | {'S Pico (MVA)':<12} | {'% Trafo':<10} | {'Horário':<8}")
    print("-" * 80)
    for _, rf in df_res_feeders.iterrows():
        print(f"{rf['Alimentador']:<20} | {rf['COD_ID']:<10} | {rf['P_Pico_MW']:<12.2f} | {rf['S_Pico_MVA']:<12.2f} | {rf['Pct_Trafo']:<9.1f}% | {rf['Hora_Pico']:<8}")
    print("=" * 80)

    # --- 1. GRÁFICO COMPARATIVO DE CARREGAMENTO DO TRANSFORMADOR DA SE ---
    horas = np.array([i * 0.25 for i in range(96)])
    h_plot = np.linspace(0, 24, 384, endpoint=False) if SUAVIZAR_CURVAS else horas

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.5, 7.8), sharex=True)

    cores = {'sem_gd': '#e53e3e', 'com_gd': '#dd6b20', 'bateria': '#2b6cb0'}
    estilos = {'sem_gd': '--', 'com_gd': '-', 'bateria': '-'}
    labels = {
        'sem_gd': '1. Sem GD (Caso Base)',
        'com_gd': '2. Com GD Solar 2026',
        'bateria': f'3. Com GD + Bateria BESS ({kw_bess_mw:.0f} MW / {kwh_bess_mwh:.0f} MWh)'
    }

    # Gráfico 1: Demanda Ativa Líquida (MW)
    for c, res in resultados.items():
        p_plot = PchipInterpolator(horas, res['p_mw'])(h_plot) if SUAVIZAR_CURVAS else res['p_mw']
        ax1.plot(h_plot, p_plot, label=labels.get(c, c), color=cores.get(c, 'black'),
                 linestyle=estilos.get(c, '-'), linewidth=2.2)

    ax1.axhline(0, color='gray', linestyle=':', alpha=0.7, label='Zero (Fluxo Reverso se < 0)')
    ax1.axhline(cfg['mva'], color='#718096', linestyle='-.', alpha=0.85, label=f'Capacidade Nominal ({cfg["mva"]:.0f} MVA)')
    ax1.set_ylabel('Potência Líquida no Trafo (MW)', fontsize=11, fontweight='bold')
    ax1.set_title(
        f'Subestação Goiânia Leste - Desempenho Diário do Transformador {tr_key} (50 MVA) - Comparativo TCC',
        fontsize=12, fontweight='bold', pad=10
    )
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=8.5, framealpha=0.95, edgecolor='#cbd5e1')

    # Gráfico 2: Tensão na Barra Secundária MT (13,8 kV) em PU
    for c, res in resultados.items():
        v_plot = PchipInterpolator(horas, res['v_pu'])(h_plot) if SUAVIZAR_CURVAS else res['v_pu']
        ax2.plot(h_plot, v_plot, label=labels.get(c, c), color=cores.get(c, 'black'),
                 linestyle=estilos.get(c, '-'), linewidth=2.0)

    ax2.axhline(0.93, color='#e53e3e', linestyle=':', label='Limite Mínimo ANEEL (0.93 PU)')
    ax2.axhline(1.05, color='#e53e3e', linestyle=':', label='Limite Máximo ANEEL (1.05 PU)')
    ax2.set_xlabel('Hora do Dia (h)', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Tensão Barra 13,8 kV (PU)', fontsize=11, fontweight='bold')
    ax2.set_ylim(0.92, 1.06)
    ax2.set_xticks(np.arange(0, 25, 2))
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=8.5, framealpha=0.95, edgecolor='#cbd5e1')

    plt.tight_layout()
    caminho_grafico_svg = os.path.join(GRAFICOS_DIR, f"Curva_Carregamento_{tr_key}_50MVA_24h.svg")
    caminho_grafico_png = os.path.join(GRAFICOS_DIR, f"Curva_Carregamento_{tr_key}_50MVA_24h.png")
    caminho_estudo_svg = os.path.join(GRAFICOS_DIR, f"Curva_Carregamento_{tr_key}_estudo_gd_bateria.svg")
    caminho_estudo_png = os.path.join(GRAFICOS_DIR, f"Curva_Carregamento_{tr_key}_estudo_gd_bateria.png")
    plt.savefig(caminho_grafico_svg, format='svg', bbox_inches='tight')
    plt.savefig(caminho_grafico_png, dpi=200, bbox_inches='tight')
    plt.savefig(caminho_estudo_svg, format='svg', bbox_inches='tight')
    plt.savefig(caminho_estudo_png, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"\n[GRÁFICO 1] Curvas comparativas de carregamento e tensão salvas em:\n  -> '{caminho_grafico_svg}'\n  -> '{caminho_grafico_png}'")

    # --- 2. GRÁFICO COMPARATIVO DOS ALIMENTADORES DESTE TRANSFORMADOR ---
    plt.figure(figsize=(11, 6))
    curvas_f_plot = resultados[cenario_ref]['curvas_feeders']
    for i, (fnome, f_curva) in enumerate(curvas_f_plot.items()):
        cor = PALETA_ALIMENTADORES[i % len(PALETA_ALIMENTADORES)]
        if SUAVIZAR_CURVAS:
            curva_interp = np.clip(PchipInterpolator(horas, f_curva)(h_plot), 0.0, None)
            plt.plot(h_plot, curva_interp, label=fnome, color=cor, linewidth=1.8)
        else:
            plt.plot(horas, f_curva, label=fnome, color=cor, linewidth=1.8)

    plt.xlabel('Hora do Dia (h)', fontsize=11, fontweight='bold')
    plt.ylabel('Demanda Aparente (MVA)', fontsize=11, fontweight='bold')
    plt.title(
        f'Curva de Carga Diária dos Alimentadores do Transformador {tr_key} (SE Goiânia Leste) - {cenario_ref.upper()}',
        fontsize=12, fontweight='bold', pad=10
    )
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.xticks(np.arange(0, 25, 2))
    plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
    plt.tight_layout()
    grafico_feeders_svg = os.path.join(GRAFICOS_DIR, f"Curva_Alimentadores_{tr_key}_24h.svg")
    grafico_feeders_png = os.path.join(GRAFICOS_DIR, f"Curva_Alimentadores_{tr_key}_24h.png")
    plt.savefig(grafico_feeders_svg, format='svg', bbox_inches='tight')
    plt.savefig(grafico_feeders_png, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"[GRÁFICO 2] Curva comparativa dos alimentadores salva em:\n  -> '{grafico_feeders_svg}'\n  -> '{grafico_feeders_png}'")

    # --- 3. MAPA GEOGRÁFICO VETORIAL EXCLUSIVO (SVG / PNG) ---
    print(f"\nGerando Mapa Geográfico exclusivo para o setor atendido pelo {tr_key}...")
    fig, ax = plt.subplots(figsize=(13, 11), facecolor='#0f172a')
    ax.set_facecolor('#0f172a')

    # Plota linhas de Baixa Tensão (em verde suave transparente)
    for r_b in df_bt.itertuples():
        pts = parse_wkt_coords(r_b.geometria_wkt)
        if len(pts) >= 2:
            lons = [p[0] for p in pts]
            lats = [p[1] for p in pts]
            ax.plot(lons, lats, color='#2ecc71', linewidth=0.35, alpha=0.35, zorder=2)

    # Plota linhas de Média Tensão (com cores individuais por alimentador)
    mapa_cores_ctmt = {}
    for i, c_id in enumerate(ctmts):
        mapa_cores_ctmt[str(c_id)] = PALETA_ALIMENTADORES[i % len(PALETA_ALIMENTADORES)]

    pac_mt_coords = {}
    for r_m in df_mt.itertuples():
        pts = parse_wkt_coords(r_m.geometria_wkt)
        if len(pts) >= 2:
            lons = [p[0] for p in pts]
            lats = [p[1] for p in pts]
            cor_c = mapa_cores_ctmt.get(str(r_m.CTMT), '#3498db')
            ax.plot(lons, lats, color=cor_c, linewidth=1.1, alpha=0.85, zorder=4)
            pac_mt_coords[str(r_m.PAC_1)] = (pts[0][0], pts[0][1])
            pac_mt_coords[str(r_m.PAC_2)] = (pts[-1][0], pts[-1][1])
            pac_mt_coords[str(r_m.PAC_1).lstrip('R')] = (pts[0][0], pts[0][1])
            pac_mt_coords[str(r_m.PAC_2).lstrip('R')] = (pts[-1][0], pts[-1][1])

    # Plota os transformadores de distribuição MT/BT
    trafos_lon, trafos_lat = [], []
    dict_trafo_coords = {}
    for r_t in df_trafos.itertuples():
        if not pd.isna(r_t.longitude) and not pd.isna(r_t.latitude):
            lo, la = float(r_t.longitude), float(r_t.latitude)
            trafos_lon.append(lo)
            trafos_lat.append(la)
            dict_trafo_coords[str(r_t.COD_ID)] = (lo, la)

    if trafos_lon:
        ax.scatter(trafos_lon, trafos_lat, c='#f1c40f', s=6, alpha=0.5, zorder=5, edgecolors='none', label='Trafos MT/BT')

    # Plota as usinas de Geração Distribuída Solar (BT e MT)
    gds_lons, gds_lats = [], []
    for r_ug in df_ugbt.itertuples():
        tr_id = str(r_ug.UNI_TR_MT)
        if tr_id in dict_trafo_coords:
            gds_lons.append(dict_trafo_coords[tr_id][0])
            gds_lats.append(dict_trafo_coords[tr_id][1])

    for r_ugm in df_ugmt.itertuples():
        pac_m = str(r_ugm.PAC).strip().lstrip('R')
        if pac_m in pac_mt_coords:
            gds_lons.append(pac_mt_coords[pac_m][0])
            gds_lats.append(pac_mt_coords[pac_m][1])

    if gds_lons:
        ax.scatter(gds_lons, gds_lats, c='#f39c12', s=24, alpha=0.85, marker='*', zorder=6,
                   edgecolors='#78350f', linewidths=0.4, label=f'Usinas GD Solar ({pot_gd_total_mw:.1f} MW)')

    # Plota a posição da Subestação Goiânia Leste
    se_wkt = bases['sub']['geometria_wkt'].iloc[0]
    se_pts = parse_wkt_coords(se_wkt)
    if se_pts:
        se_lon = np.mean([p[0] for p in se_pts])
        se_lat = np.mean([p[1] for p in se_pts])
        ax.scatter([se_lon], [se_lat], c='#ff2a2a', s=180, marker='*', zorder=10, edgecolors='white', linewidths=1.2, label='SE Goiânia Leste')
        ax.annotate(
            f"SE Goiânia Leste\n[{tr_key} - 50 MVA]",
            xy=(se_lon, se_lat),
            xytext=(12, 12),
            textcoords='offset points',
            color='white',
            fontsize=9.5,
            fontweight='bold',
            bbox=dict(boxstyle="round,pad=0.3", fc="#e74c3c", ec="white", lw=1, alpha=0.9),
            zorder=11
        )

        # Plota marcador do BESS na subestação se aplicável
        if cenario in ['bateria', 'comparativo']:
            ax.scatter([se_lon + 0.001], [se_lat + 0.001], c='#27ae60', s=160, marker='s', zorder=12,
                       edgecolors='white', linewidths=1.2, label=f'BESS ({kw_bess_mw:.0f} MW / {kwh_bess_mwh:.0f} MWh)')
            ax.annotate(
                f"BESS Subestação\n[{kw_bess_mw:.0f} MW / {kwh_bess_mwh:.0f} MWh]",
                xy=(se_lon + 0.001, se_lat + 0.001),
                xytext=(-15, -25),
                textcoords='offset points',
                color='white',
                fontsize=8.5,
                fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc="#27ae60", ec="white", lw=1, alpha=0.9),
                zorder=13
            )

    # Legenda dos alimentadores e componentes
    legend_handles = []
    for _, r_f in feeders_tr.iterrows():
        c_id = str(r_f['COD_ID'])
        cor = mapa_cores_ctmt.get(c_id, '#3498db')
        legend_handles.append(mlines.Line2D([], [], color=cor, linewidth=2, label=f"{r_f['NOME']}"))

    legend_handles.append(mlines.Line2D([], [], color='#2ecc71', linewidth=1.5, label=f"Rede BT ({len(df_bt):,} trechos)"))
    legend_handles.append(mlines.Line2D([], [], color='#f1c40f', marker='o', linestyle='None', markersize=4, label=f"Trafos MT/BT ({len(df_trafos):,})"))
    if gds_lons:
        legend_handles.append(mlines.Line2D([], [], color='#f39c12', marker='*', linestyle='None', markersize=9,
                                            markeredgecolor='#78350f', label=f"GD Solar 2026 ({pot_gd_total_mw:.1f} MW)"))
    legend_handles.append(mlines.Line2D([], [], color='#ff2a2a', marker='*', linestyle='None', markersize=10, markeredgecolor='white', label="Subestação"))
    if cenario in ['bateria', 'comparativo']:
        legend_handles.append(mlines.Line2D([], [], color='#27ae60', marker='s', linestyle='None', markersize=8, markeredgecolor='white', label=f"BESS ({kw_bess_mw:.0f} MW)"))

    ax.legend(
        handles=legend_handles,
        loc='upper left',
        fontsize=8.5,
        facecolor='#1e293b',
        edgecolor='#475569',
        labelcolor='white',
        framealpha=0.92
    )

    ax.set_title(
        f'Malha Geográfica da Rede - Subestação Goiânia Leste\n'
        f'Setor Atendido pelo Transformador {tr_key} (50 MVA) | {len(feeders_tr)} Alimentadores | {pot_gd_total_mw:.2f} MW GD Solar | BESS {kw_bess_mw:.0f} MW',
        color='white', fontsize=12, fontweight='bold', pad=15
    )
    ax.set_xlabel('Longitude', color='#94a3b8', fontsize=10)
    ax.set_ylabel('Latitude', color='#94a3b8', fontsize=10)
    ax.tick_params(colors='#94a3b8', labelsize=8.5)
    for spine in ax.spines.values():
        spine.set_color('#334155')
    ax.set_aspect('equal')

    plt.tight_layout()
    mapa_svg = os.path.join(GRAFICOS_DIR, f"Mapa_Geografico_{tr_key}.svg")
    mapa_png = os.path.join(GRAFICOS_DIR, f"Mapa_Geografico_{tr_key}.png")
    plt.savefig(mapa_svg, format='svg', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.savefig(mapa_png, dpi=200, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"[MAPA VETORIAL SVG/PNG] Mapa geográfico exclusivo salvo em:\n  -> '{mapa_svg}'\n  -> '{mapa_png}'")

    # --- 4. MAPA FÍSICO INTERATIVO NO SATÉLITE E RUAS (FOLIUM / LEAFLET) ---
    if se_pts:
        print(f"\nGerando Mapa Físico Interativo no Satélite para o {tr_key}...")
        m_se = folium.Map(
            location=[se_lat, se_lon],
            zoom_start=14,
            tiles=None
        )
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri World Imagery',
            name='🛰️ Satélite Real (Esri)',
            overlay=False,
            control=True
        ).add_to(m_se)

        folium.TileLayer(
            tiles='OpenStreetMap',
            name='🗺️ Mapa de Ruas (OpenStreetMap)',
            overlay=False,
            control=True
        ).add_to(m_se)

        # Alimentadores MT em cores distintas
        for _, r_f in feeders_tr.iterrows():
            fid = str(r_f['COD_ID'])
            fnome = str(r_f['NOME'])
            cor_f = mapa_cores_ctmt.get(fid, '#3498db')
            fg_f = folium.FeatureGroup(name=f"⚡ MT: {fnome} ({fid})", show=True)
            linhas_feed = df_mt[df_mt['CTMT'].astype(str) == fid]
            for r_m in linhas_feed.itertuples():
                pts_m = parse_wkt_coords(r_m.geometria_wkt)
                if len(pts_m) >= 2:
                    coords_m = [(p[1], p[0]) for p in pts_m]
                    folium.PolyLine(
                        locations=coords_m,
                        color=cor_f,
                        weight=3.5,
                        opacity=0.85,
                        tooltip=f"{fnome} | Trecho: {r_m.COD_ID}"
                    ).add_to(fg_f)
            fg_f.add_to(m_se)

        # Marcador da Subestação
        popup_se = f"""
        <div style="font-family: Arial, sans-serif; min-width: 250px;">
            <h4 style="margin: 0 0 8px 0; color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 4px;">
                ⚡ Subestação Goiânia Leste
            </h4>
            <b>Transformador:</b> {tr_key} ({cfg['nome_completo']})<br>
            <b>Capacidade:</b> {cfg['mva']:.0f} MVA (50.000 kVA)<br>
            <b>Tensão Primária / Secundária:</b> 230 kV / 13,8 kV<br>
            <b>Barra MT Secundária:</b> {cfg['barra_sec']}<br>
            <b>Alimentadores Atendidos:</b> {len(feeders_tr)}<br>
            <b>Potência GD Solar Total:</b> <span style="color: #27ae60; font-weight: bold;">{pot_gd_total_mw:.2f} MW</span><br>
            <b>Pico Máximo Observado:</b> {resultados[cenario_ref]['s_pico_mva']:.2f} MVA ({resultados[cenario_ref]['carreg_max']:.1f}%)
        </div>
        """
        folium.Marker(
            location=[se_lat, se_lon],
            popup=folium.Popup(popup_se, max_width=320),
            tooltip=f"⚡ SE Goiânia Leste [{tr_key} - 50 MVA]",
            icon=folium.Icon(color='red', icon='bolt', prefix='fa')
        ).add_to(m_se)

        # Marcador do BESS na Subestação
        if cenario in ['bateria', 'comparativo']:
            popup_bess = f"""
            <div style="font-family: Arial, sans-serif; min-width: 240px; font-size: 13px;">
                <h4 style="margin: 0 0 8px 0; color: #27ae60; border-bottom: 2px solid #27ae60; padding-bottom: 4px;">
                    🔋 Sistema de Baterias BESS (Subestação)
                </h4>
                <b>Transformador:</b> {tr_key} ({cfg['nome_completo']})<br>
                <b>Potência Nominal:</b> {kw_bess_mw:.1f} MW ({kw_bess_mw*1000:.0f} kW)<br>
                <b>Capacidade de Armazenamento:</b> {kwh_bess_mwh:.1f} MWh ({kwh_bess_mwh*1000:.0f} kWh)<br>
                <b>Ponto de Conexão:</b> Barra MT {cfg['barra_sec']} (13,8 kV)<br>
                <b>Estratégia:</b> Absorve geração solar das 10h às 14h15 e injeta na ponta noturna das 18h às 21h45
            </div>
            """
            folium.Marker(
                location=[se_lat + 0.0003, se_lon + 0.0003],
                popup=folium.Popup(popup_bess, max_width=320),
                tooltip=f"🔋 Bateria BESS SE [{kw_bess_mw:.0f} MW / {kwh_bess_mwh:.0f} MWh]",
                icon=folium.Icon(color='green', icon='battery-full', prefix='fa')
            ).add_to(m_se)

        # Marcadores das Usinas GD Solar agrupadas em Cluster de Alta Performance
        fg_gd = folium.FeatureGroup(name=f"☀️ GD Solar ({len(df_ugbt) + len(df_ugmt)} usinas - {pot_gd_total_mw:.2f} MW)", show=True)
        cluster_gd = plugins.MarkerCluster(name="Cluster GD Solar").add_to(fg_gd)

        for r_ug in df_ugbt.itertuples():
            tr_id = str(r_ug.UNI_TR_MT)
            if tr_id in dict_trafo_coords:
                lo_g, la_g = dict_trafo_coords[tr_id]
                pot_kw = float(r_ug.POT_INST) if pd.notna(r_ug.POT_INST) else 5.0
                popup_ug = f"""
                <div style="font-family: Arial, sans-serif; font-size: 12px; min-width: 200px;">
                    <b style="color: #d35400;">☀️ GD Solar BT (2026)</b><br>
                    <b>Código CEG:</b> {r_ug.CEG_GD}<br>
                    <b>Potência:</b> {pot_kw:.2f} kW<br>
                    <b>Trafo MT/BT:</b> UNTRMT_{tr_id}<br>
                    <b>Bairro:</b> {getattr(r_ug, 'BRR', 'N/A')}
                </div>
                """
                folium.Marker(
                    location=[la_g, lo_g],
                    popup=folium.Popup(popup_ug, max_width=250),
                    tooltip=f"☀️ GD BT: {pot_kw:.1f} kW",
                    icon=folium.Icon(color='orange', icon='sun-o', prefix='fa')
                ).add_to(cluster_gd)

        for r_ugm in df_ugmt.itertuples():
            pac_m = str(r_ugm.PAC).strip().lstrip('R')
            if pac_m in pac_mt_coords:
                lo_g, la_g = pac_mt_coords[pac_m]
                pot_kw = float(r_ugm.POT_INST) if pd.notna(r_ugm.POT_INST) else 50.0
                popup_ugm = f"""
                <div style="font-family: Arial, sans-serif; font-size: 12px; min-width: 200px;">
                    <b style="color: #e67e22;">☀️ GD Solar MT (2026)</b><br>
                    <b>Código CEG:</b> {r_ugm.CEG_GD}<br>
                    <b>Potência:</b> {pot_kw:.2f} kW<br>
                    <b>Alimentador:</b> {r_ugm.CTMT}<br>
                    <b>Bairro:</b> {getattr(r_ugm, 'BRR', 'N/A')}
                </div>
                """
                folium.Marker(
                    location=[la_g, lo_g],
                    popup=folium.Popup(popup_ugm, max_width=250),
                    tooltip=f"☀️ GD MT: {pot_kw:.1f} kW",
                    icon=folium.Icon(color='darkred', icon='bolt', prefix='fa')
                ).add_to(cluster_gd)

        fg_gd.add_to(m_se)

        folium.LayerControl(collapsed=False).add_to(m_se)
        plugins.Fullscreen(position='topright').add_to(m_se)

        caminho_se_html = os.path.join(GRAFICOS_DIR, f"Subestacao_{tr_key}_mapa_fisico.html")
        m_se.save(caminho_se_html)
        print(f"[MAPA FÍSICO INTERATIVO] Salvo em Satélite Real e Ruas:\n  -> '{caminho_se_html}'\n")


if __name__ == "__main__":
    t_inicio = time.time()
    parser = argparse.ArgumentParser(description="Simulador individual dos 4 transformadores de força da SE Goiânia Leste com GD 2026 e BESS.")
    parser.add_argument("--trafo", type=str, default=None, choices=['TR1', 'TR2', 'TR3', 'TR4'],
                        help="Transformador da SE: TR1, TR2, TR3 ou TR4 (default: TR1)")
    parser.add_argument("--cenario", type=str, default=CENARIO_PADRAO, choices=['comparativo', 'com-gd', 'sem-gd', 'bateria'],
                        help="Cenário de simulação: comparativo, com-gd, sem-gd, bateria (default: comparativo)")
    parser.add_argument("--bess-mw", type=float, default=None, help="Potência do BESS em MW na SE (default: 10 MW)")
    parser.add_argument("--bess-mwh", type=float, default=None, help="Capacidade do BESS em MWh na SE (default: 30 MWh)")
    parser.add_argument("--listar", action="store_true", help="Lista os 4 transformadores e seus alimentadores")

    args = parser.parse_args()
    bases = carregar_bases()

    if args.listar:
        listar_trafos_se(bases['ctmt'])
    else:
        trafo_alvo = args.trafo if args.trafo is not None else TRAFO_SUBESTACAO
        simular_trafo_se(trafo_alvo, bases, cenario=args.cenario, bess_mw=args.bess_mw, bess_mwh=args.bess_mwh)

    tempo_total = time.time() - t_inicio
    minutos = int(tempo_total // 60)
    segundos = tempo_total % 60
    print("\n" + "=" * 70)
    if minutos > 0:
        print(f"[TEMPO DE EXECUÇÃO] Simulação concluída em {minutos}m {segundos:.2f}s ({tempo_total:.2f} s)!")
    else:
        print(f"[TEMPO DE EXECUÇÃO] Simulação concluída em {segundos:.2f} segundos!")
    print("=" * 70 + "\n")
