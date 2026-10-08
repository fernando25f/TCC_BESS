# ==============================================================================
# SIMULAÇÃO DIÁRIA DA SUBESTAÇÃO GOIÂNIA LESTE (OPENDSS)
# Análise de Impacto da Geração Distribuída Solar Fotovoltaica
# ==============================================================================

import os
import json
import math
import time
import pandas as pd
import opendssdirect as dss
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from matplotlib.collections import LineCollection

t_inicio_global = time.time()

# ------------------------------------------------------------------------------
# 1. PARÂMETROS DE CONTROLE DA SIMULAÇÃO
# ------------------------------------------------------------------------------
# Modos disponíveis: 'comparativa', 'com_gd', 'padrao'
MODO_ANALISE = 'comparativa'

# Carregamento e Demanda
FATOR_DEMANDA = 0.11        # Fração da carga instalada (ex: 0.11 = 11%)

# Geração Distribuída Solar Fotovoltaica
FATOR_GD = 1.0              # Escala da GD (1.0 = 100% da BDGD)
MES_SOLAR = "Abril"         # "Abril" (Média Anual), "Julho" (Inverno), "Outubro" (Chuvoso)
TIPO_CURVA_GD = "STC"       # "STC" (1000 W/m²) ou "PicoUnitario" (normalizado em 1.0)

# Limites Normativos de Tensão (PRODIST / ANEEL)
LIMITE_SUBTENSAO_PU = 0.93  # Limite inferior adequado (0.93 pu)
LIMITE_SOBRETENSAO_PU = 1.05 # Limite superior adequado (1.05 pu)

META_SIMULACAO = f"FD = {FATOR_DEMANDA*100:.0f}%"
if MODO_ANALISE in ['com_gd', 'comparativa']:
    META_SIMULACAO += f" | GD = x{FATOR_GD:.1f} ({MES_SOLAR})"

# ------------------------------------------------------------------------------
# 2. DIRETÓRIOS E ARQUIVOS DO CIRCUITO
# ------------------------------------------------------------------------------
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_modelo = os.path.join(diretorio_atual, "modelo_opendss")

pasta_graficos_tcc = os.path.join(diretorio_atual, "graficos_TCC")
pasta_logs_tcc     = os.path.join(diretorio_atual, "logs_TCC")

pasta_graf_subestacao = os.path.join(pasta_graficos_tcc, "subestacao")
pasta_graf_trafo_dist = os.path.join(pasta_graficos_tcc, "trafo_distribuicao")
pasta_graf_mapa_rede  = os.path.join(pasta_graficos_tcc, "mapa_rede")

pasta_log_divergencia = os.path.join(pasta_logs_tcc, "divergencia")
pasta_log_monitores   = os.path.join(pasta_logs_tcc, "monitores")
pasta_log_relatorios  = os.path.join(pasta_logs_tcc, "relatorios")

for p in [pasta_graf_subestacao, pasta_graf_trafo_dist, pasta_graf_mapa_rede,
          pasta_log_divergencia, pasta_log_monitores, pasta_log_relatorios]:
    os.makedirs(p, exist_ok=True)

def caminho_sem_sobrescrever(pasta, nome_base, extensao):
    caminho = os.path.join(pasta, f"{nome_base}.{extensao}")
    if not os.path.exists(caminho):
        return caminho
    v = 2
    while True:
        caminho = os.path.join(pasta, f"{nome_base}_v{v}.{extensao}")
        if not os.path.exists(caminho):
            return caminho
        v += 1

arquivo_transformador_AT = os.path.join(pasta_modelo, "transformador_AT.dss")
arquivo_disjuntores_mt   = os.path.join(pasta_modelo, "disjuntores_mt.dss")
arquivo_seccionadoras_mt = os.path.join(pasta_modelo, "seccionadoras_mt.dss")
arquivo_capacitores_mt   = os.path.join(pasta_modelo, "capacitores_mt.dss")
arquivo_transformador_MT = os.path.join(pasta_modelo, "transformador_MT.dss")
arquivo_linhas_mt        = os.path.join(pasta_modelo, "linhas_mt.dss")
arquivo_linhas_bt        = os.path.join(pasta_modelo, "linhas_bt.dss")
arquivo_curva_carga      = os.path.join(pasta_modelo, "curva_carga.dss")
arquivo_carga_bt         = os.path.join(pasta_modelo, "carga_bt.dss")
arquivo_carga_mt         = os.path.join(pasta_modelo, "carga_mt.dss")
arquivo_buscoords        = os.path.join(pasta_modelo, "buscoords.dss")
arquivo_monitores        = os.path.join(pasta_modelo, "monitores.dss")
arquivo_curva_solar      = os.path.join(pasta_modelo, "curva_solar.dss")
arquivo_gd               = os.path.join(pasta_modelo, "geracao_distribuida.dss")
arquivo_alimentadores_json = os.path.join(pasta_modelo, "alimentadores_info.json")

# Informações da Subestação e Alimentadores
dict_ctmt_info = {}
trafos_subestacao_info = {}
if os.path.exists(arquivo_alimentadores_json):
    with open(arquivo_alimentadores_json, "r", encoding="utf-8") as fj:
        metadados = json.load(fj)
        dict_ctmt_info = metadados.get("alimentadores", {})
        trafos_subestacao_info = metadados.get("trafos_subestacao", {})

if trafos_subestacao_info:
    trafos_subestacao = list(trafos_subestacao_info.keys())
    trafo_sec_bus = {tr: dados["barra_secundaria"] for tr, dados in trafos_subestacao_info.items()}
else:
    trafos_subestacao = ["GOL-S-TRF-TR1", "GOL-S-TRF-TR2", "GOL-S-TRF-TR3", "GOL-S-TRF-TR4"]
    trafo_sec_bus = {
        "GOL-S-TRF-TR1": "1783",
        "GOL-S-TRF-TR2": "4629",
        "GOL-S-TRF-TR3": "4630",
        "GOL-S-TRF-TR4": "6440"
    }

# Transformadores críticos de referência inicial (atualizados dinamicamente na simulação com GD)
TOP_5_TRAFOS_REVERSO_DEFAULT = [
    {'trafo': 'untrmt_5522590', 'cod_id': '5522590', 'kva': 225.0, 'p_rev_kw': 253.66, 'barra_bt': '89257225522590.1.2.3.0', 'fases': 3, 'kv': 0.38},
    {'trafo': 'untrmt_5522592', 'cod_id': '5522592', 'kva': 225.0, 'p_rev_kw': 236.29, 'barra_bt': '89257745522592.1.2.3.0', 'fases': 3, 'kv': 0.38},
    {'trafo': 'untrmt_5522588', 'cod_id': '5522588', 'kva': 225.0, 'p_rev_kw': 193.59, 'barra_bt': '89257195522588.1.2.3.0', 'fases': 3, 'kv': 0.38},
    {'trafo': 'untrmt_5307863', 'cod_id': '5307863', 'kva': 300.0, 'p_rev_kw': 192.60, 'barra_bt': '83107145307863-365.1.2.3.0', 'fases': 3, 'kv': 0.38},
    {'trafo': 'untrmt_5612289', 'cod_id': '5612289', 'kva': 300.0, 'p_rev_kw': 185.71, 'barra_bt': '83149735612289-774.1.2.3.0', 'fases': 3, 'kv': 0.38}
]
TOP_5_TRAFOS_REVERSO = list(TOP_5_TRAFOS_REVERSO_DEFAULT)

# ------------------------------------------------------------------------------
# 3. MOTOR DE SIMULAÇÃO DIÁRIA (24H - 96 PASSOS DE 15 MIN)
# ------------------------------------------------------------------------------
def executar_simulacao_cenario(nome_cenario, habilitar_gd=False, trafos_monitorados=None):
    print("\n" + "=" * 70)
    print(f"EXECUTANDO CENÁRIO: {nome_cenario.upper()}")
    print(f"  -> Geração Distribuída: {'Ativa (Fator ' + str(FATOR_GD) + 'x)' if habilitar_gd else 'Desativada (Base Padrão)'}")
    print("=" * 70)
    t_inicio_cenario = time.time()

    dss.Command("clear")
    dss.Command("new circuit.Subestacao_Goiania_Leste basekv=230 bus1=5001462 pu=1.05 phases=3")

    dss.Command(f'redirect "{arquivo_transformador_AT}"')
    dss.Command(f'redirect "{arquivo_disjuntores_mt}"')
    dss.Command(f'redirect "{arquivo_seccionadoras_mt}"')
    dss.Command(f'redirect "{arquivo_transformador_MT}"')
    dss.Command(f'redirect "{arquivo_linhas_mt}"')
    if os.path.exists(arquivo_capacitores_mt):
        dss.Command(f'redirect "{arquivo_capacitores_mt}"')
    dss.Command(f'redirect "{arquivo_linhas_bt}"')
    dss.Command(f'redirect "{arquivo_curva_carga}"')
    dss.Command(f'redirect "{arquivo_carga_bt}"')
    if os.path.exists(arquivo_carga_mt):
        dss.Command(f'redirect "{arquivo_carga_mt}"')
    if os.path.exists(arquivo_buscoords):
        dss.Command(f'Buscoords "{arquivo_buscoords}"')
    if os.path.exists(arquivo_monitores):
        dss.Command(f'redirect "{arquivo_monitores}"')

    # Configuração da GD Solar
    if habilitar_gd:
        if os.path.exists(arquivo_curva_solar):
            dss.Command(f'redirect "{arquivo_curva_solar}"')
        if os.path.exists(arquivo_gd):
            dss.Command(f'redirect "{arquivo_gd}"')
            sufixo = "_PicoUnitario" if TIPO_CURVA_GD == "PicoUnitario" else ""
            nome_curva_ativa = f"Curva_Solar_{MES_SOLAR}{sufixo}"
            for pv in dss.PVsystems.AllNames():
                dss.PVsystems.Name(pv)
                dss.PVsystems.daily(nome_curva_ativa)
                if FATOR_GD != 1.0:
                    dss.PVsystems.Pmpp(dss.PVsystems.Pmpp() * FATOR_GD)
                    dss.PVsystems.kVARated(dss.PVsystems.kVARated() * FATOR_GD)
            for g in dss.Generators.AllNames():
                dss.Generators.Name(g)
                dss.Generators.daily(nome_curva_ativa)
                if FATOR_GD != 1.0:
                    dss.Generators.kW(dss.Generators.kW() * FATOR_GD)

    dss.Command("Set voltagebases=[230.0, 13.8, 0.38]")
    dss.Command("Calcvoltagebases")
    dss.Command(f"Set LoadMult={FATOR_DEMANDA:.4f}")

    dss.Command("set mode=snapshot")
    dss.Solution.Solve()

    # Mapeamento dos transformadores MT
    trafos_mt_nomes = [t for t in dss.Transformers.AllNames() if t.startswith('untrmt_')]
    cache_trafos_mt = {}
    for t_nome in trafos_mt_nomes:
        dss.Transformers.Name(t_nome)
        kva_nom = dss.Transformers.kVA()
        if kva_nom > 0:
            buses = dss.CktElement.BusNames()
            sec_bus = buses[1] if len(buses) > 1 else ''
            cache_trafos_mt[t_nome] = {
                'cod_id': t_nome.replace('untrmt_', ''),
                'kva_nom': kva_nom,
                'np': dss.CktElement.NumPhases(),
                'limite_kva2': (kva_nom * 1.25) ** 2,
                'barra_bt': sec_bus,
                'bus_clean': sec_bus.split('.')[0]
            }

    dss.Command("set mode=daily stepsize=0.25h maxiterations=50 number=1 hour=0 sec=0")

    curva_subestacao_kw = []
    perfil_p_trafos_at = {tr: [] for tr in trafos_subestacao}
    perfil_v_trafos_at = {tr: [] for tr in trafos_subestacao}

    trafos_alvo = trafos_monitorados if trafos_monitorados else TOP_5_TRAFOS_REVERSO
    lista_nomes_alvo = [t['trafo'] for t in trafos_alvo]
    curva_top5_trafos = {t: [] for t in lista_nomes_alvo}
    curva_v_top5_trafos = {t: [] for t in lista_nomes_alvo}

    curvas_p_todos_trafos = {t: [] for t in cache_trafos_mt}
    curvas_v_todos_trafos = {}

    dados_trafos_at = {tr: {
        'p_max_kw': 0.0, 's_max_kva': 0.0, 'q_at_pmax': 0.0,
        'hora_pico': '', 'fp_pico': 1.0,
        'v_min_pu': 999.0, 'v_max_pu': 0.0, 'energia_kwh': 0.0
    } for tr in trafos_subestacao}

    dados_ctmt = {cod_id: {
        'p_max_kw': 0.0, 's_max_kva': 0.0, 'q_at_pmax': 0.0,
        'hora_pico': '', 'fp_pico': 1.0,
        'v_min_pu': 999.0, 'v_max_pu': 0.0, 'energia_kwh': 0.0
    } for cod_id in dict_ctmt_info.keys()}

    trafos_sobrecarregados = set()
    registros_sobrecarga = []
    passos_divergentes = []
    convergiu_todas = True

    # Simulação dos 96 passos de 15 minutos (24 horas)
    for i in range(1, 97):
        dss.Solution.Solve()

        if not dss.Solution.Converged():
            convergiu_todas = False
            passos_divergentes.append(i)

        minutos_totais = i * 15
        h = (minutos_totais // 60) % 24
        m = minutos_totais % 60
        hora_str = f"{h:02d}:{m:02d}" if minutos_totais < 24 * 60 else "24:00"

        # Potência total ativa consumida na Subestação
        p_se_kw = -dss.Circuit.TotalPower()[0]
        curva_subestacao_kw.append(p_se_kw)

        # Monitoramento dos transformadores MT de distribuição
        for t_nome, info_tr in cache_trafos_mt.items():
            dss.Transformers.Name(t_nome)
            powers = dss.CktElement.Powers()
            np_tr = info_tr['np']
            pt = sum(powers[k * 2] for k in range(np_tr))
            qt = sum(powers[k * 2 + 1] for k in range(np_tr))
            s2 = pt**2 + qt**2
            if s2 > info_tr['limite_kva2']:
                cod_id_tr = info_tr['cod_id']
                trafos_sobrecarregados.add(cod_id_tr)
                s_kva = math.sqrt(s2)
                pct = (s_kva / info_tr['kva_nom']) * 100.0
                registros_sobrecarga.append((cod_id_tr, hora_str, s_kva, info_tr['kva_nom'], pct))

            curvas_p_todos_trafos[t_nome].append(pt)
            if t_nome in curva_top5_trafos:
                curva_top5_trafos[t_nome].append(pt)

        # Monitoramento de tensão no primário MT
        for t_nome, info_tr in cache_trafos_mt.items():
            dss.Circuit.SetActiveElement(f"transformer.{t_nome}")
            bus_mt = dss.CktElement.BusNames()[0].split('.')[0]
            dss.Circuit.SetActiveBus(bus_mt)
            pu_nodes = dss.Bus.puVmagAngle()
            nodes = dss.Bus.Nodes()
            v_fases = [pu_nodes[2 * k] for k in range(len(nodes)) if nodes[k] in (1, 2, 3)]
            v_pu = max(v_fases) if v_fases else (pu_nodes[0] if pu_nodes else 1.0)

            if t_nome not in curvas_v_todos_trafos:
                curvas_v_todos_trafos[t_nome] = []
            curvas_v_todos_trafos[t_nome].append(v_pu)

            if t_nome in curva_v_top5_trafos:
                curva_v_top5_trafos[t_nome].append(v_pu)

        # Transformadores de AT da SE
        for tr in trafos_subestacao:
            dss.Circuit.SetActiveElement(f"transformer.{tr}")
            powers_tr = dss.CktElement.Powers()
            p_tr_kw = sum(powers_tr[2 * k] for k in range(3))
            q_tr_kvar = sum(powers_tr[2 * k + 1] for k in range(3))
            s_tr_kva = math.sqrt(p_tr_kw**2 + q_tr_kvar**2)
            fp_tr = (p_tr_kw / s_tr_kva) if s_tr_kva > 0 else 1.0

            sec_bus = trafo_sec_bus[tr]
            dss.Circuit.SetActiveBus(sec_bus)
            pu_nodes = dss.Bus.puVmagAngle()
            v_pus = [pu_nodes[2 * k] for k in range(len(dss.Bus.Nodes()))] if pu_nodes else [1.0]
            v_min_step = min(v_pus)
            v_max_step = max(v_pus)
            v_med_step = (sum(v_pus) / len(v_pus)) if v_pus else 1.0

            dados_trafos_at[tr]['energia_kwh'] += p_tr_kw * 0.25
            perfil_p_trafos_at[tr].append(p_tr_kw)
            perfil_v_trafos_at[tr].append(v_med_step)
            if v_min_step < dados_trafos_at[tr]['v_min_pu']:
                dados_trafos_at[tr]['v_min_pu'] = v_min_step
            if v_max_step > dados_trafos_at[tr]['v_max_pu']:
                dados_trafos_at[tr]['v_max_pu'] = v_max_step

            if s_tr_kva > dados_trafos_at[tr]['s_max_kva']:
                dados_trafos_at[tr]['s_max_kva'] = s_tr_kva
                dados_trafos_at[tr]['p_max_kw'] = p_tr_kw
                dados_trafos_at[tr]['q_at_pmax'] = q_tr_kvar
                dados_trafos_at[tr]['hora_pico'] = hora_str
                dados_trafos_at[tr]['fp_pico'] = fp_tr

        # Alimentadores CTMT
        for cod_id in dict_ctmt_info.keys():
            dss.Circuit.SetActiveElement(f"line.DJ_{cod_id}")
            powers_dj = dss.CktElement.Powers()
            p_dj_kw = sum(powers_dj[2 * k] for k in range(3))
            q_dj_kvar = sum(powers_dj[2 * k + 1] for k in range(3))
            s_dj_kva = math.sqrt(p_dj_kw**2 + q_dj_kvar**2)
            fp_dj = (p_dj_kw / s_dj_kva) if s_dj_kva > 0 else 1.0

            barra_ctmt = dict_ctmt_info[cod_id]['barra']
            dss.Circuit.SetActiveBus(barra_ctmt)
            pu_nodes_dj = dss.Bus.puVmagAngle()
            v_pus_dj = [pu_nodes_dj[2 * k] for k in range(len(dss.Bus.Nodes()))] if pu_nodes_dj else [1.0]

            dados_ctmt[cod_id]['energia_kwh'] += p_dj_kw * 0.25
            if min(v_pus_dj) < dados_ctmt[cod_id]['v_min_pu']:
                dados_ctmt[cod_id]['v_min_pu'] = min(v_pus_dj)
            if max(v_pus_dj) > dados_ctmt[cod_id]['v_max_pu']:
                dados_ctmt[cod_id]['v_max_pu'] = max(v_pus_dj)

            if s_dj_kva > dados_ctmt[cod_id]['s_max_kva']:
                dados_ctmt[cod_id]['s_max_kva'] = s_dj_kva
                dados_ctmt[cod_id]['p_max_kw'] = p_dj_kw
                dados_ctmt[cod_id]['q_at_pmax'] = q_dj_kvar
                dados_ctmt[cod_id]['hora_pico'] = hora_str
                dados_ctmt[cod_id]['fp_pico'] = fp_dj

    # Identificação dinâmica de trafos com fluxo reverso
    top_5_dinamico = []
    if nome_cenario == 'com_gd':
        trafos_reverso = []
        for t_nome, cp in curvas_p_todos_trafos.items():
            p_rev_max = max(0.0, max(-p for p in cp))
            if p_rev_max > 1.0:
                info_tr = cache_trafos_mt[t_nome]
                if info_tr['kva_nom'] <= 75.0:
                    continue
                idx_pico = cp.index(-p_rev_max)
                h_pico_rev = f"{((idx_pico + 1) * 15 // 60) % 24:02d}:{((idx_pico + 1) * 15 % 60):02d}"
                trafos_reverso.append({
                    'trafo': t_nome,
                    'cod_id': info_tr['cod_id'],
                    'kva': info_tr['kva_nom'],
                    'p_rev_kw': p_rev_max,
                    'p_rev_relativa': p_rev_max / info_tr['kva_nom'],
                    'barra_bt': info_tr['barra_bt'],
                    'bus_clean': info_tr['bus_clean'],
                    'fases': info_tr['np'],
                    'kv': 0.38 if info_tr['np'] >= 2 else 0.22,
                    'hora_pico_rev': h_pico_rev,
                    'curva_p': cp
                })
        trafos_reverso.sort(key=lambda x: x['p_rev_relativa'], reverse=True)
        top_5_dinamico = trafos_reverso[:5]

        for t_alvo in top_5_dinamico:
            tn = t_alvo['trafo']
            curva_top5_trafos[tn] = curvas_p_todos_trafos[tn]
            if tn in curvas_v_todos_trafos:
                curva_v_top5_trafos[tn] = curvas_v_todos_trafos[tn]

    # Indicadores globais da SE
    p_max_se_kw = max(curva_subestacao_kw)
    idx_pico = curva_subestacao_kw.index(p_max_se_kw)
    min_tot_pico = (idx_pico + 1) * 15
    hora_pico_se = f"{(min_tot_pico // 60) % 24:02d}:{min_tot_pico % 60:02d}"
    energia_total_se_mwh = sum(curva_subestacao_kw) * 0.25 / 1000.0

    t_fim_cenario = time.time()
    print(f"  [OK] Concluído em {t_fim_cenario - t_inicio_cenario:.2f}s | Pico SE: {p_max_se_kw/1000:.2f} MW às {hora_pico_se} | Energia: {energia_total_se_mwh:.2f} MWh")

    return {
        'nome_cenario': nome_cenario,
        'curva_subestacao_kw': curva_subestacao_kw,
        'perfil_p_trafos_at': perfil_p_trafos_at,
        'perfil_v_trafos_at': perfil_v_trafos_at,
        'curva_top5_trafos': curva_top5_trafos,
        'curva_v_top5_trafos': curva_v_top5_trafos,
        'trafos_monitorados': trafos_alvo,
        'top_5_dinamico': top_5_dinamico,
        'dados_trafos_at': dados_trafos_at,
        'dados_ctmt': dados_ctmt,
        'p_max_se_kw': p_max_se_kw,
        'hora_pico_se': hora_pico_se,
        'energia_total_se_mwh': energia_total_se_mwh,
        'trafos_sobrecarregados': trafos_sobrecarregados,
        'registros_sobrecarga': registros_sobrecarga,
        'convergiu_todas': convergiu_todas,
        'passos_divergentes': passos_divergentes,
        'tempo_segundos': t_fim_cenario - t_inicio_cenario,
        'curvas_p_todos_trafos': curvas_p_todos_trafos,
        'curvas_v_todos_trafos': curvas_v_todos_trafos
    }

# ------------------------------------------------------------------------------
# 4. EXECUÇÃO DOS CENÁRIOS
# ------------------------------------------------------------------------------
resultados_cenarios = {}

if MODO_ANALISE == 'comparativa':
    # 1. Simula cenário padrão primeiro
    res_padrao = executar_simulacao_cenario('padrao', habilitar_gd=False)
    resultados_cenarios['padrao'] = res_padrao

    # 2. Simula com GD depois e identifica os transformadores críticos
    res_gd = executar_simulacao_cenario('com_gd', habilitar_gd=True)
    resultados_cenarios['com_gd'] = res_gd

    top_5_dinamico = res_gd.get('top_5_dinamico', TOP_5_TRAFOS_REVERSO_DEFAULT)
    TOP_5_TRAFOS_REVERSO = top_5_dinamico

    # Vincula as curvas dos trafos identificados na GD ao cenário Padrão
    for t_alvo in top_5_dinamico:
        tn = t_alvo['trafo']
        if tn in res_padrao['curvas_p_todos_trafos']:
            res_padrao['curva_top5_trafos'][tn] = res_padrao['curvas_p_todos_trafos'][tn]
        if tn in res_padrao['curvas_v_todos_trafos']:
            res_padrao['curva_v_top5_trafos'][tn] = res_padrao['curvas_v_todos_trafos'][tn]

elif MODO_ANALISE == 'com_gd':
    res_gd = executar_simulacao_cenario('com_gd', habilitar_gd=True)
    resultados_cenarios['com_gd'] = res_gd
    if res_gd.get('top_5_dinamico'):
        TOP_5_TRAFOS_REVERSO = res_gd['top_5_dinamico']

elif MODO_ANALISE == 'padrao':
    res_padrao = executar_simulacao_cenario('padrao', habilitar_gd=False)
    resultados_cenarios['padrao'] = res_padrao

else:
    raise ValueError(f"Modo de análise '{MODO_ANALISE}' inválido. Opções: 'comparativa', 'com_gd', 'padrao'.")

# ------------------------------------------------------------------------------
# 5. CONFIGURAÇÃO VISUAL DE PLOTAGEM
# ------------------------------------------------------------------------------
tempo_horas = [(step * 0.25) for step in range(1, 97)]

CORES_CENARIOS = {
    'padrao': '#2b6cb0',  # Azul
    'com_gd': '#e53e3e'   # Vermelho
}

ESTILOS_CENARIOS = {
    'padrao': {'linestyle': '-', 'linewidth': 2.2, 'label': 'Rede Padrão (Sem GD)'},
    'com_gd': {'linestyle': '-', 'linewidth': 2.2, 'label': 'Com GD Solar FV'}
}

cenarios_plot = ['padrao', 'com_gd'] if MODO_ANALISE == 'comparativa' else [MODO_ANALISE]

# ------------------------------------------------------------------------------
# 6. GRÁFICO 1: DEMANDA TOTAL DA SUBESTAÇÃO (24H)
# ------------------------------------------------------------------------------
print("\n[GRÁFICOS] Gerando curva de demanda da Subestação...")
try:
    plt.figure(figsize=(11, 5.5))

    for c_nome in cenarios_plot:
        dados_c = resultados_cenarios[c_nome]
        curva_mw = [p / 1000.0 for p in dados_c['curva_subestacao_kw']]
        p_max = dados_c['p_max_se_kw'] / 1000.0
        h_pico = dados_c['hora_pico_se']
        label = f"{ESTILOS_CENARIOS[c_nome]['label']} [Pico: {p_max:.1f} MW às {h_pico}]"
        plt.plot(tempo_horas, curva_mw, color=CORES_CENARIOS[c_nome],
                 linewidth=ESTILOS_CENARIOS[c_nome]['linewidth'],
                 linestyle=ESTILOS_CENARIOS[c_nome]['linestyle'], label=label)

    plt.title(f"Demanda Total da Subestação Goiânia Leste (24h)\n{META_SIMULACAO}", fontsize=11, fontweight='bold')
    plt.xlabel("Hora do Dia (h)", fontsize=10)
    plt.ylabel("Potência Ativa Total (MW)", fontsize=10)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.xticks(range(1, 25))
    plt.axhline(0, color='black', linewidth=0.8, linestyle=':')
    plt.legend(loc='upper left', fontsize=9, framealpha=0.9)
    plt.tight_layout()

    nome_arq_se = f"Curva_Carga_Subestacao_{MODO_ANALISE}_24h"
    out_se_svg = caminho_sem_sobrescrever(pasta_graf_subestacao, nome_arq_se, "svg")
    plt.savefig(out_se_svg, format='svg')
    plt.close()
    print(f"  [OK] Gráfico da Subestação salvo: '{out_se_svg}'")
except Exception as e:
    print(f"  [ERRO] Falha ao plotar curva da subestação: {e}")

# ------------------------------------------------------------------------------
# 7. GRÁFICO 2: TRANSFORMADORES AT DA SUBESTAÇÃO (230/13.8 KV)
# ------------------------------------------------------------------------------
print("\n[GRÁFICOS] Gerando curvas dos transformadores AT da Subestação...")
try:
    cenario_ref = 'com_gd' if 'com_gd' in resultados_cenarios else 'padrao'
    dados_ref = resultados_cenarios[cenario_ref]

    # Carregamento Ativo (MW)
    plt.figure(figsize=(11, 5.5))
    cores_tr = {'GOL-S-TRF-TR1': '#e74c3c', 'GOL-S-TRF-TR2': '#3498db', 'GOL-S-TRF-TR3': '#2ecc71', 'GOL-S-TRF-TR4': '#9b59b6'}

    for tr in trafos_subestacao:
        tr_short = tr.replace("GOL-S-TRF-", "")
        curva_mw = [p / 1000.0 for p in dados_ref['perfil_p_trafos_at'][tr]]
        p_max_tr = dados_ref['dados_trafos_at'][tr]['p_max_kw'] / 1000.0
        plt.plot(tempo_horas, curva_mw, label=f"{tr_short} (Pico: {p_max_tr:.1f} MW)",
                 color=cores_tr.get(tr, '#333333'), linewidth=2.0)

    plt.axhline(y=50.0, color='#e67e22', linestyle='--', linewidth=1.3, label='Capacidade Nominal (50 MVA)')
    plt.title(f"Carregamento Diário dos Transformadores AT da SE (230/13.8 kV)\n{META_SIMULACAO}", fontsize=11, fontweight='bold')
    plt.xlabel("Hora do Dia (h)", fontsize=10)
    plt.ylabel("Potência Ativa (MW)", fontsize=10)
    plt.xticks(range(1, 25))
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='upper left', fontsize=9)
    plt.tight_layout()

    out_tr_at_svg = caminho_sem_sobrescrever(pasta_graf_subestacao, f"Curva_Carregamento_Trafos_AT_{cenario_ref}_24h", "svg")
    plt.savefig(out_tr_at_svg, format='svg')
    plt.close()

    # Perfil de Tensão Secundária (pu)
    plt.figure(figsize=(11, 5.5))
    for tr in trafos_subestacao:
        tr_short = tr.replace("GOL-S-TRF-", "")
        curva_v = dados_ref['perfil_v_trafos_at'][tr]
        v_min_tr = dados_ref['dados_trafos_at'][tr]['v_min_pu']
        v_max_tr = dados_ref['dados_trafos_at'][tr]['v_max_pu']
        plt.plot(tempo_horas, curva_v, label=f"{tr_short} (Mín: {v_min_tr:.3f} | Máx: {v_max_tr:.3f} pu)",
                 color=cores_tr.get(tr, '#333333'), linewidth=2.0)

    plt.axhline(y=LIMITE_SOBRETENSAO_PU, color='#e74c3c', linestyle='--', linewidth=1.2, label=f'Limite Superior Adequado ({LIMITE_SOBRETENSAO_PU} pu)')
    plt.axhline(y=1.00, color='#7f8c8d', linestyle=':', linewidth=0.8, label='Tensão Nominal Base (1.00 pu)')
    plt.axhline(y=LIMITE_SUBTENSAO_PU, color='#e74c3c', linestyle='--', linewidth=1.2, label=f'Limite Inferior Adequado ({LIMITE_SUBTENSAO_PU} pu)')

    plt.title(f"Tensão Secundária nos Transformadores AT da SE (13.8 kV)\n{META_SIMULACAO}", fontsize=11, fontweight='bold')
    plt.xlabel("Hora do Dia (h)", fontsize=10)
    plt.ylabel("Tensão Secundária (pu)", fontsize=10)
    plt.xticks(range(1, 25))
    plt.ylim(0.91, 1.07)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='lower left', fontsize=8.5, framealpha=0.9)
    plt.tight_layout()

    out_v_tr_svg = caminho_sem_sobrescrever(pasta_graf_subestacao, f"Curva_Tensao_Trafos_AT_{cenario_ref}_24h", "svg")
    plt.savefig(out_v_tr_svg, format='svg')
    plt.close()
    print(f"  [OK] Gráficos dos transformadores AT salvos: '{out_tr_at_svg}' e '{out_v_tr_svg}'")
except Exception as e:
    print(f"  [ERRO] Falha ao plotar transformadores AT: {e}")

# ------------------------------------------------------------------------------
# 9. GRÁFICO 4: MAPA GEOGRÁFICO DA REDE COM OS TRAFOS CRÍTICOS
# ------------------------------------------------------------------------------
print("\n[MAPA] Renderizando topologia geográfica da rede de distribuição...")
try:
    coords_map = {}
    if os.path.exists(arquivo_buscoords):
        with open(arquivo_buscoords, 'r') as fb:
            for line in fb:
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    try:
                        coords_map[parts[0].strip().upper()] = (float(parts[1]), float(parts[2]))
                    except ValueError:
                        continue

    segs_mt, segs_bt = [], []
    for arq, segs in [(arquivo_linhas_mt, segs_mt), (arquivo_linhas_bt, segs_bt)]:
        if os.path.exists(arq):
            with open(arq, 'r') as f:
                for line in f:
                    if line.startswith('new line.'):
                        parts = line.split()
                        b1 = next((p.split('=')[1].split('.')[0].upper() for p in parts if p.startswith('bus1=')), None)
                        b2 = next((p.split('=')[1].split('.')[0].upper() for p in parts if p.startswith('bus2=')), None)
                        if b1 and b2 and b1 in coords_map and b2 in coords_map:
                            segs.append([coords_map[b1], coords_map[b2]])

    fig, ax = plt.subplots(figsize=(15, 11))
    ax.set_facecolor('#1a1a2e')
    fig.patch.set_facecolor('#0f0f23')

    if segs_bt:
        ax.add_collection(LineCollection(segs_bt, colors='#2ecc71', linewidths=0.3, alpha=0.35))
    if segs_mt:
        ax.add_collection(LineCollection(segs_mt, colors='#3498db', linewidths=0.8, alpha=0.7))

    coords_top5_lon, coords_top5_lat = [], []
    for dados_tr in TOP_5_TRAFOS_REVERSO:
        b_limpa = dados_tr['barra_bt'].split('.')[0].upper()
        if b_limpa in coords_map:
            coords_top5_lon.append(coords_map[b_limpa][0])
            coords_top5_lat.append(coords_map[b_limpa][1])

    if coords_top5_lon:
        ax.scatter(coords_top5_lon, coords_top5_lat, c='#f1c40f', s=110, alpha=1.0,
                   zorder=8, edgecolors='white', linewidths=1.2, marker='*',
                   label='Transformadores com Maior Fluxo Reverso')

    leg_mt = mlines.Line2D([], [], color='#3498db', linewidth=2, label=f'Rede MT ({len(segs_mt):,} trechos)')
    leg_bt = mlines.Line2D([], [], color='#2ecc71', linewidth=1.5, label=f'Rede BT ({len(segs_bt):,} trechos)')
    handles_leg = [leg_mt, leg_bt]
    if coords_top5_lon:
        handles_leg.append(mlines.Line2D([], [], color='#f1c40f', marker='*', linestyle='None',
                                         markersize=11, markeredgecolor='white', label='Top 5 Trafos Fluxo Reverso'))

    ax.legend(handles=handles_leg, loc='upper left', fontsize=8.5, facecolor='#16213e',
              edgecolor='#e2e8f0', labelcolor='white', framealpha=0.9)

    ax.set_title("Topologia da Rede de Distribuição - Subestação Goiânia Leste\nIdentificação dos Pontos Críticos de Injeção Solar",
                 color='white', fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel("Longitude", color='#a0aec0', fontsize=9)
    ax.set_ylabel("Latitude", color='#a0aec0', fontsize=9)
    ax.tick_params(colors='#a0aec0', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#2d3748')
    ax.autoscale_view()
    ax.set_aspect('equal')
    plt.tight_layout()

    out_mapa_png = caminho_sem_sobrescrever(pasta_graf_mapa_rede, "Mapa_Rede_Goiania_Leste", "png")
    plt.savefig(out_mapa_png, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close('all')
    print(f"  [OK] Mapa salvo: '{out_mapa_png}'")
except Exception as e:
    print(f"  [ERRO] Falha ao gerar mapa geográfico: {e}")

# ------------------------------------------------------------------------------
# 10. RELATÓRIO EXECUTIVO E EXPORTAÇÃO DE RESULTADOS
# ------------------------------------------------------------------------------
print("\n" + "=" * 90)
print("                           RELATÓRIO COMPARATIVO DE CENÁRIOS")
print("=" * 90)

tabela_cenarios = []
for c_nome, dados_c in resultados_cenarios.items():
    tabela_cenarios.append({
        'Cenário': c_nome.upper(),
        'Pico_SE_MW': round(dados_c['p_max_se_kw'] / 1000.0, 2),
        'Hora_Pico': dados_c['hora_pico_se'],
        'Energia_Total_MWh': round(dados_c['energia_total_se_mwh'], 2),
        'Trafos_Sobrecarregados': len(dados_c['trafos_sobrecarregados']),
        'Convergência': "100% OK" if dados_c['convergiu_todas'] else f"Falha ({len(dados_c['passos_divergentes'])} passos)",
        'Tempo_Simulação_s': round(dados_c['tempo_segundos'], 2)
    })

df_cenarios = pd.DataFrame(tabela_cenarios)
print(df_cenarios.to_string(index=False))

# Relatório detalhado dos 5 transformadores mais críticos com fluxo reverso
print("\n" + "-" * 110)
print("COMPORTAMENTO DOS 5 TRANSFORMADORES COM MAIOR FLUXO REVERSO E IMPACTO NA TENSÃO:")
print("-" * 110)

tabela_top5 = []
for dados_tr in TOP_5_TRAFOS_REVERSO:
    t_nome = dados_tr['trafo']
    cap = dados_tr['kva']

    curva_pad = resultados_cenarios.get('padrao', {}).get('curva_top5_trafos', {}).get(t_nome, [0.0]*96)
    curva_gd  = resultados_cenarios.get('com_gd', {}).get('curva_top5_trafos', {}).get(t_nome, [0.0]*96)

    curva_v_pad = resultados_cenarios.get('padrao', {}).get('curva_v_top5_trafos', {}).get(t_nome, [1.0]*96)
    curva_v_gd  = resultados_cenarios.get('com_gd', {}).get('curva_v_top5_trafos', {}).get(t_nome, [1.0]*96)

    p_rev_max_gd = max(0.0, max(-p for p in curva_gd))
    e_rev_gd_kwh = sum(-p * 0.25 for p in curva_gd if p < 0)

    v_max_pad = max(curva_v_pad)
    v_max_gd  = max(curva_v_gd)
    status_tensao = f"Sobretensão ({v_max_gd:.3f} pu)" if v_max_gd > LIMITE_SOBRETENSAO_PU else f"Adequada ({v_max_gd:.3f} pu)"

    print(f"  * {t_nome:<16} ({cap:4.0f} kVA) | P_rev_máx: {p_rev_max_gd:6.1f} kW | E_reversa: {e_rev_gd_kwh:6.1f} kWh | V_máx: {v_max_pad:.3f} -> {v_max_gd:.3f} pu ({status_tensao})")

    tabela_top5.append({
        'Transformador': t_nome,
        'Codigo_ID': dados_tr['cod_id'],
        'Capacidade_kVA': cap,
        'Barra_BT': dados_tr['barra_bt'],
        'P_Pico_Reverso_kW': round(p_rev_max_gd, 2),
        'Energia_Reversa_kWh': round(e_rev_gd_kwh, 2),
        'V_Max_Padrao_pu': round(v_max_pad, 4),
        'V_Max_Com_GD_pu': round(v_max_gd, 4),
        'Variacao_Tensao_Delta_pu': round(v_max_gd - v_max_pad, 4),
        'Status_Tensao_PRODIST': status_tensao
    })

# Exportação para CSV
arq_csv_cenarios = caminho_sem_sobrescrever(pasta_log_relatorios, "Relatorio_Comparativo_Cenarios", "csv")
df_cenarios.to_csv(arq_csv_cenarios, index=False, sep=';', encoding='utf-8')

df_top5 = pd.DataFrame(tabela_top5)
arq_csv_top5 = caminho_sem_sobrescrever(pasta_log_relatorios, "Relatorio_Top5_Trafos_Fluxo_Reverso", "csv")
df_top5.to_csv(arq_csv_top5, index=False, sep=';', encoding='utf-8')

print("\n" + "=" * 90)
print(f"[ARQUIVOS] Planilhas salvas:\n  -> '{arq_csv_cenarios}'\n  -> '{arq_csv_top5}'")

tempo_total = time.time() - t_inicio_global
print(f"TEMPO TOTAL: {int(tempo_total // 60)}m {tempo_total % 60:.2f}s")
print("=" * 90 + "\n")
