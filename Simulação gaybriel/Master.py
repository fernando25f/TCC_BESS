import os
import re
import math
import time
import pandas as pd

t_inicio = time.time()
# pyrefly: ignore [missing-import]
import opendssdirect as dss
# pyrefly: ignore [missing-import]
from opendssdirect import Transformers
# pyrefly: ignore [missing-import]
import matplotlib.pyplot as plt
# pyrefly: ignore [missing-import]
import matplotlib.lines as mlines


def caminho_sem_sobrescrever(pasta, nome_base, extensao):
    caminho = os.path.join(pasta, f"{nome_base}.{extensao}")
    if not os.path.exists(caminho):
        return caminho
    versao = 2
    while True:
        caminho = os.path.join(pasta, f"{nome_base}_v{versao}.{extensao}")
        if not os.path.exists(caminho):
            return caminho
        versao += 1


diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_graficos = os.path.join(diretorio_atual, "graficos")
os.makedirs(pasta_graficos, exist_ok=True)

arquivo_transformador_AT = os.path.join(diretorio_atual, "modelo_opendss", "transformador_AT.dss")
arquivo_disjuntores_mt = os.path.join(diretorio_atual, "modelo_opendss", "disjuntores_mt.dss")
arquivo_seccionadoras_mt = os.path.join(diretorio_atual, "modelo_opendss", "seccionadoras_mt.dss")
arquivo_capacitores_mt = os.path.join(diretorio_atual, "modelo_opendss", "capacitores_mt.dss")
arquivo_transformador_MT = os.path.join(diretorio_atual, "modelo_opendss", "transformador_MT.dss")
arquivo_linhas_mt = os.path.join(diretorio_atual, "modelo_opendss", "linhas_mt.dss")
arquivo_linhas_bt = os.path.join(diretorio_atual, "modelo_opendss", "linhas_bt.dss")
arquivo_curva_carga = os.path.join(diretorio_atual, "modelo_opendss", "curva_carga.dss")
arquivo_carga_bt = os.path.join(diretorio_atual, "modelo_opendss", "carga_bt.dss")
arquivo_carga_mt = os.path.join(diretorio_atual, "modelo_opendss", "carga_mt.dss")
arquivo_curva_solar = os.path.join(diretorio_atual, "modelo_opendss", "curva_solar.dss")
arquivo_gd = os.path.join(diretorio_atual, "modelo_opendss", "geracao_distribuida.dss")
arquivo_buscoords = os.path.join(diretorio_atual, "modelo_opendss", "buscoords.dss")
arquivo_ctmt_csv = os.path.join(diretorio_atual, "dados_goiania_leste", "02_CTMT_alimentadores.csv")

# ==============================================================================
# CENÁRIO DE SIMULAÇÃO (TCC):
# ==============================================================================
# True  -> Simula COM Geração Distribuída fotovoltaica (Base 2026 com 4.138 usinas)
# False -> Simula SEM Geração Distribuída (Caso Base convencional)
HABILITAR_GD = True
# ==============================================================================

dict_ctmt_info = {}
if os.path.exists(arquivo_ctmt_csv):
    df_ctmt_meta = pd.read_csv(arquivo_ctmt_csv, usecols=['COD_ID', 'NOME', 'UNI_TR_AT', 'BARR'])
    for _, row in df_ctmt_meta.iterrows():
        dict_ctmt_info[str(row['COD_ID']).strip()] = {
            'nome': str(row['NOME']).strip(),
            'trafo': str(row['UNI_TR_AT']).strip(),
            'barra': str(row['BARR']).strip()
        }

print("============================================================")
print("INICIALIZANDO SIMULAÇÃO OPENDSS")
print("============================================================")

dss.Command("clear")
dss.Command("new circuit.Subestacao_Goiania_Leste basekv=230 bus1=5001462 pu=1.05 phases=3")

dss.Command(f'redirect "{arquivo_transformador_AT}"')
nomes_trafos_AT = dss.Transformers.AllNames()
print(f"\n[OK] Transformadores AT carregados: {len(nomes_trafos_AT)}")

dss.Command(f'redirect "{arquivo_disjuntores_mt}"')
nomes_disjuntores_mt = dss.Lines.AllNames()
print(f"\n[OK] Disjuntores MT carregados: {len(nomes_disjuntores_mt)}")

dss.Command(f'redirect "{arquivo_seccionadoras_mt}"')
nomes_seccionadoras_mt = dss.Lines.AllNames()
print(f"\n[OK] Seccionadoras MT carregadas: {len(nomes_seccionadoras_mt) - len(nomes_disjuntores_mt)}")

dss.Command(f'redirect "{arquivo_transformador_MT}"')
nomes_trafos_MT = dss.Transformers.AllNames()
print(f"\n[OK] Transformadores MT carregados: {len(nomes_trafos_MT) - len(nomes_trafos_AT)}")

dss.Command(f'redirect "{arquivo_linhas_mt}"')
nomes_linhas_mt = dss.Lines.AllNames()
print(f"\n[OK] Linhas MT carregadas: {len(nomes_linhas_mt) - len(nomes_seccionadoras_mt)}\n")

if os.path.exists(arquivo_capacitores_mt):
    dss.Command(f'redirect "{arquivo_capacitores_mt}"')
    nomes_caps = dss.Capacitors.AllNames()
    print(f"[OK] Bancos de Capacitores MT carregados: {len(nomes_caps)}\n")

dss.Command(f'redirect "{arquivo_linhas_bt}"')
nomes_linhas_bt = dss.Lines.AllNames()
print(f"\n[OK] Linhas BT carregadas: {len(nomes_linhas_bt) - len(nomes_linhas_mt)}\n")

dss.Command(f'redirect "{arquivo_curva_carga}"')
nomes_curva_carga = dss.LoadShape.AllNames()
print(f"\n[OK] Curvas de carga carregadas: {len(nomes_curva_carga)}\n")

dss.Command(f'redirect "{arquivo_carga_bt}"')
nomes_carga_bt = dss.Loads.AllNames()
print(f"\n[OK] Cargas BT carregadas: {len(nomes_carga_bt)}\n")

if os.path.exists(arquivo_carga_mt):
    dss.Command(f'redirect "{arquivo_carga_mt}"')
    print(f"\n[OK] Cargas MT carregadas: {len(dss.Loads.AllNames()) - len(nomes_carga_bt)}\n")

if HABILITAR_GD:
    if os.path.exists(arquivo_curva_solar):
        dss.Command(f'redirect "{arquivo_curva_solar}"')
        print(f"\n[OK] Curvas solares carregadas!")
    if os.path.exists(arquivo_gd):
        dss.Command(f'redirect "{arquivo_gd}"')
        nomes_pv = dss.PVsystems.AllNames()
        print(f"\n[OK] Geração Distribuída (GD 2026) carregada: {len(nomes_pv)} usinas fotovoltaicas (PVSYSTEM)!\n")
else:
    print("\n[INFO] Simulação configurada SEM GD (Caso Base).\n")

if os.path.exists(arquivo_buscoords):
    dss.Command(f'Buscoords "{arquivo_buscoords}"')
    print("\n[OK] Coordenadas (Buscoords) carregadas!\n")

erro = dss.Error.Description()
if erro:
    print(f"[ERRO DE SINTAXE]: {erro}")
else:
    print("[OK] Sintaxe aceita sem erros pelo OpenDSS!")

dss.Command("Set voltagebases=[230.0, 13.8, 0.38]")
dss.Command("Calcvoltagebases")

dss.Command("new monitor.mon_subestacao element=vsource.source terminal=1 mode=1 ppolar=no")

trafos_subestacao = ['GOL-S-TRF-TR1', 'GOL-S-TRF-TR2', 'GOL-S-TRF-TR3', 'GOL-S-TRF-TR4']
trafo_sec_bus = {
    'GOL-S-TRF-TR1': '1783',
    'GOL-S-TRF-TR2': '4629',
    'GOL-S-TRF-TR3': '4630',
    'GOL-S-TRF-TR4': '6440'
}

for tr in trafos_subestacao:
    tr_short = tr.replace("GOL-S-TRF-", "")
    dss.Command(f'new monitor.mon_tr_{tr_short}_pot element=transformer.{tr} terminal=2 mode=1 ppolar=no')
    dss.Command(f'new monitor.mon_tr_{tr_short}_vi element=transformer.{tr} terminal=2 mode=0')

for cod_id in dict_ctmt_info.keys():
    dss.Command(f'new monitor.mon_ctmt_{cod_id}_pot element=line.DJ_{cod_id} terminal=1 mode=1 ppolar=no')
    dss.Command(f'new monitor.mon_ctmt_{cod_id}_vi element=line.DJ_{cod_id} terminal=1 mode=0')

print(f"[OK] Monitores instalados no OpenDSS: 1 Subestação + {len(trafos_subestacao) * 2} Trafos AT (P e V) + {len(dict_ctmt_info) * 2} Alimentadores CTMT (P e V)")

dss.Command("set mode=daily stepsize=0.25h maxiterations=50 number=1")
print("\n[SIMULAÇÃO] Iniciando fluxo de carga diário (24h) com passos de 15 min...")

convergiu_todas = True
tabela_potencia = []

dados_trafos_at = {
    tr: {
        'p_max_kw': 0.0,
        's_max_kva': 0.0,
        'q_at_pmax': 0.0,
        'hora_pico': '',
        'fp_pico': 1.0,
        'v_min_pu': 999.0,
        'v_max_pu': 0.0,
        'energia_kwh': 0.0
    }
    for tr in trafos_subestacao
}

perfil_p_trafos = {tr: [] for tr in trafos_subestacao}

dados_ctmt = {
    cod_id: {
        'p_max_kw': 0.0,
        's_max_kva': 0.0,
        'q_at_pmax': 0.0,
        'hora_pico': '',
        'fp_pico': 1.0,
        'v_min_pu': 999.0,
        'v_max_pu': 0.0,
        'energia_kwh': 0.0
    }
    for cod_id in dict_ctmt_info.keys()
}

arquivo_divergencia = caminho_sem_sobrescrever(pasta_graficos, "barras_divergencia", "csv")
with open(arquivo_divergencia, 'w') as f_div:
    f_div.write("PASSO,HORA,BARRA,TENSAO_PU\n")

barras_colapsadas_dia = set()
trafos_sobrecarregados = set()
trafos_mt_nomes = [t for t in dss.Transformers.AllNames() if t.startswith("untrmt_")]

TAP_NORMAL = 1.0
TAP_PICO = 1.025
PASSO_INICIO_PICO = 69
PASSO_FIM_PICO = 88

for i in range(1, 97):
    tap_atual = TAP_PICO if (PASSO_INICIO_PICO <= i <= PASSO_FIM_PICO) else TAP_NORMAL
    for tr in trafos_subestacao:
        dss.Command(f"Transformer.{tr}.wdg=2 tap={tap_atual}")

    if i == PASSO_INICIO_PICO:
        print(f"  [CONTROLE DE TAP] Horário de pico (17:15h): Elevando tap de todos os trafos AT para {TAP_PICO:.3f}...")
    elif i == PASSO_FIM_PICO + 1:
        print(f"  [CONTROLE DE TAP] Fim do pico (22:15h): Retornando tap de todos os trafos AT para {TAP_NORMAL:.3f}...")

    dss.Command("Solve")
    if not dss.Solution.Converged():
        print(f"  [ALERTA] Fluxo divergiu no passo {i:02d}!")
        convergiu_todas = False
        pu_mags = dss.Circuit.AllBusMagPu()
        bus_names = dss.Circuit.AllBusNames()
        if pu_mags and bus_names:
            bus_pu = list(zip(bus_names, pu_mags))
            bus_pu_valid = [b for b in bus_pu if b[1] > 0.001]
            bus_pu_valid.sort(key=lambda x: x[1])
            print("    -> Piores barras (pontos de colapso de tensão):")
            for b in bus_pu_valid[:3]:
                print(f"       Barra: {b[0]:<15} | Tensão: {b[1]:.4f} PU")
            minutos_totais = i * 15
            h_div = (minutos_totais // 60) % 24
            m_div = minutos_totais % 60
            hora_div = f"{h_div:02d}:{m_div:02d}"
            with open(arquivo_divergencia, 'a') as f_div:
                for b in bus_pu_valid:
                    f_div.write(f"{i},{hora_div},{b[0]},{b[1]:.6f}\n")
                    if b[1] < 0.9:
                        barras_colapsadas_dia.add(b[0])
    else:
        print(f"  [OK] Fluxo convergiu no passo {i:02d}!")

    if dss.Solution.Converged() and (68 <= i <= 88):
        for t_nome in trafos_mt_nomes:
            cod_id_tr = t_nome.replace("untrmt_", "")
            if cod_id_tr in trafos_sobrecarregados:
                continue
            dss.Transformers.Name(t_nome)
            kva_nom = dss.Transformers.kVA()
            if kva_nom <= 0:
                continue
            dss.Circuit.SetActiveElement(f"transformer.{t_nome}")
            powers = dss.CktElement.Powers()
            np = dss.CktElement.NumPhases()
            pt = sum(powers[2 * k] for k in range(np))
            qt = sum(powers[2 * k + 1] for k in range(np))
            s_calc = (pt**2 + qt**2) ** 0.5
            if s_calc > kva_nom * 1.25:
                trafos_sobrecarregados.add(cod_id_tr)

    p_kw = -dss.Circuit.TotalPower()[0]
    minutos_totais = i * 15
    h = (minutos_totais // 60) % 24
    m = minutos_totais % 60
    hora_str = f"{h:02d}:{m:02d}"
    if minutos_totais == 1440:
        hora_str = "24:00"
    tabela_potencia.append((hora_str, p_kw))

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

        dados_trafos_at[tr]['energia_kwh'] += p_tr_kw * 0.25
        perfil_p_trafos[tr].append(p_tr_kw)
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
        v_min_step_dj = min(v_pus_dj)
        v_max_step_dj = max(v_pus_dj)

        dados_ctmt[cod_id]['energia_kwh'] += p_dj_kw * 0.25
        if v_min_step_dj < dados_ctmt[cod_id]['v_min_pu']:
            dados_ctmt[cod_id]['v_min_pu'] = v_min_step_dj
        if v_max_step_dj > dados_ctmt[cod_id]['v_max_pu']:
            dados_ctmt[cod_id]['v_max_pu'] = v_max_step_dj
        if s_dj_kva > dados_ctmt[cod_id]['s_max_kva']:
            dados_ctmt[cod_id]['s_max_kva'] = s_dj_kva
            dados_ctmt[cod_id]['p_max_kw'] = p_dj_kw
            dados_ctmt[cod_id]['q_at_pmax'] = q_dj_kvar
            dados_ctmt[cod_id]['hora_pico'] = hora_str
            dados_ctmt[cod_id]['fp_pico'] = fp_dj

dss.Command("Save")

if convergiu_todas:
    print("\n[OK] Simulação de 24h (Daily) concluída com sucesso em todos os passos!")
else:
    print("\n[ALERTA] O fluxo de carga não convergiu em um ou mais passos do dia!")

print("\n==============================")
print("  HORA       POTÊNCIA (kW)")
print("==============================")
for hora, p_kw in tabela_potencia:
    print(f"  {hora}      {p_kw:.2f}")
print("==============================")

p_max_hora, p_max_kw = max(tabela_potencia, key=lambda x: x[1]) if tabela_potencia else ('--', 0.0)
p_final_hora, p_final_kw = tabela_potencia[-1] if tabela_potencia else ('--', 0.0)
energia_total_se_mwh = sum(p for _, p in tabela_potencia) * 0.25 / 1000.0

linhas_relatorio = []
linhas_relatorio.append("===================================================================================================================")
linhas_relatorio.append("                        RELATÓRIO DE CARREGAMENTO E DESEMPENHO DA SUBESTAÇÃO GOIÂNIA LESTE")
linhas_relatorio.append("===================================================================================================================")
linhas_relatorio.append(f"  * Potência Ativa Máxima de Pico (SE): {p_max_kw:,.2f} kW ({p_max_kw / 1000:.2f} MW) registrada às {p_max_hora}")
linhas_relatorio.append(f"  * Potência Ativa no Fim do Dia (24h): {p_final_kw:,.2f} kW ({p_final_kw / 1000:.2f} MW)")
linhas_relatorio.append(f"  * Energia Total Fornecida no Dia:     {energia_total_se_mwh:,.2f} MWh/dia")
linhas_relatorio.append(f"  * Estado de Convergência do Fluxo:    {'100% CONVERGIDO (96/96 Passos)' if convergiu_todas else 'DIVERGÊNCIA DETECTADA'}")
linhas_relatorio.append("===================================================================================================================")

linhas_relatorio.append("\n-------------------------------------------------------------------------------------------------------------------")
linhas_relatorio.append("TABELA 1: CARREGAMENTO E TENSÃO DOS TRANSFORMADORES DA SUBESTAÇÃO (AT/MT - 230 / 13.8 kV)")
linhas_relatorio.append("-------------------------------------------------------------------------------------------------------------------")
header_tr = f"{'Transformador':<15} | {'Barra MT':<8} | {'Nº CTMTs':<8} | {'Cap. (MVA)':<10} | {'P Pico (MW)':<11} | {'S Pico (MVA)':<12} | {'Carreg. (%)':<12} | {'FP Pico':<8} | {'Faixa V (PU)':<13} | {'Status':<12}"
linhas_relatorio.append(header_tr)
linhas_relatorio.append("-------------------------------------------------------------------------------------------------------------------")

tabela_tr_dados = []
for tr in trafos_subestacao:
    tr_short = tr.replace("GOL-S-TRF-", "")
    info = dados_trafos_at[tr]
    sec_bus = trafo_sec_bus[tr]
    n_ctmt = sum(1 for c in dict_ctmt_info.values() if c['trafo'] == tr)
    cap_mva = 50.0
    p_pico_mw = info['p_max_kw'] / 1000.0
    s_pico_mva = info['s_max_kva'] / 1000.0
    carreg_pct = (s_pico_mva / cap_mva) * 100.0
    fp_pico = info['fp_pico']
    v_faixa = f"{info['v_min_pu']:.3f} - {info['v_max_pu']:.3f}"

    if carreg_pct > 120.0:
        status = "Crítico (>120%)"
    elif carreg_pct > 100.0:
        status = "Alerta (>100%)"
    else:
        status = "Normal (OK)"

    linha = f"{tr_short:<15} | {sec_bus:<8} | {n_ctmt:<8} | {cap_mva:<10.1f} | {p_pico_mw:<11.2f} | {s_pico_mva:<12.2f} | {carreg_pct:<11.1f}% | {fp_pico:<8.3f} | {v_faixa:<13} | {status:<12}"
    linhas_relatorio.append(linha)

    tabela_tr_dados.append({
        'Transformador': tr_short,
        'Barra_Secundaria': sec_bus,
        'Num_Alimentadores': n_ctmt,
        'Capacidade_Nominal_MVA': cap_mva,
        'P_Pico_MW': round(p_pico_mw, 2),
        'S_Pico_MVA': round(s_pico_mva, 2),
        'Carregamento_Pct': round(carreg_pct, 1),
        'FP_Pico': round(fp_pico, 3),
        'Hora_Pico': info['hora_pico'],
        'V_Min_PU': round(info['v_min_pu'], 4),
        'V_Max_PU': round(info['v_max_pu'], 4),
        'Energia_MWh_Dia': round(info['energia_kwh'] / 1000.0, 2),
        'Status': status
    })

linhas_relatorio.append("-------------------------------------------------------------------------------------------------------------------")

linhas_relatorio.append("\n---------------------------------------------------------------------------------------------------------------------------------------")
linhas_relatorio.append("TABELA 2: CARREGAMENTO E TENSÃO DOS ALIMENTADORES DE MÉDIA TENSÃO (27 CTMTs - 13.8 kV)")
linhas_relatorio.append("---------------------------------------------------------------------------------------------------------------------------------------")
header_ctmt = f"{'Alimentador (Nome)':<20} | {'Código ID':<10} | {'Trafo SE':<9} | {'P Pico (kW)':<12} | {'S Pico (kVA)':<13} | {'% Trafo':<8} | {'FP Pico':<8} | {'Hora Pico':<10} | {'Faixa V (PU)':<14} | {'Energia (MWh)':<13}"
linhas_relatorio.append(header_ctmt)
linhas_relatorio.append("---------------------------------------------------------------------------------------------------------------------------------------")

tabela_ctmt_dados = []
ctmt_ordenados = sorted(dict_ctmt_info.keys(), key=lambda c: (dict_ctmt_info[c]['trafo'], -dados_ctmt[c]['s_max_kva']))

for cod_id in ctmt_ordenados:
    meta = dict_ctmt_info[cod_id]
    info = dados_ctmt[cod_id]
    nome_ctmt = meta['nome']
    trafo_curto = meta['trafo'].replace("GOL-S-TRF-", "")
    p_kw = info['p_max_kw']
    s_kva = info['s_max_kva']
    pct_trafo = (s_kva / 50000.0) * 100.0
    fp = info['fp_pico']
    h_pico = info['hora_pico']
    v_faixa = f"{info['v_min_pu']:.3f} - {info['v_max_pu']:.3f}"
    e_mwh = info['energia_kwh'] / 1000.0

    linha_c = f"{nome_ctmt:<20} | {cod_id:<10} | {trafo_curto:<9} | {p_kw:<12.1f} | {s_kva:<13.1f} | {pct_trafo:<7.1f}% | {fp:<8.3f} | {h_pico:<10} | {v_faixa:<14} | {e_mwh:<13.2f}"
    linhas_relatorio.append(linha_c)

    tabela_ctmt_dados.append({
        'Alimentador_Nome': nome_ctmt,
        'Codigo_ID': cod_id,
        'Trafo_Subestacao': meta['trafo'],
        'Barra_Cabeca': meta['barra'],
        'P_Pico_kW': round(p_kw, 2),
        'P_Pico_MW': round(p_kw / 1000.0, 3),
        'S_Pico_kVA': round(s_kva, 2),
        'S_Pico_MVA': round(s_kva / 1000.0, 3),
        'Carregamento_Trafo_Pct': round(pct_trafo, 2),
        'FP_Pico': round(fp, 3),
        'Hora_Pico': h_pico,
        'V_Min_PU': round(info['v_min_pu'], 4),
        'V_Max_PU': round(info['v_max_pu'], 4),
        'Energia_MWh_Dia': round(e_mwh, 2)
    })

linhas_relatorio.append("---------------------------------------------------------------------------------------------------------------------------------------")

linhas_relatorio.append("\n===================================================================================================================")
linhas_relatorio.append("NOTAS E GLOSSÁRIO DE TERMOS TÉCNICOS UTILIZADOS:")
linhas_relatorio.append("===================================================================================================================")
linhas_relatorio.append("  * PU (Por Unidade): Razão adimensional entre a tensão medida e a tensão base nominal (1.000 PU = 100% da tensão de 13,8 kV).")
linhas_relatorio.append("  * Potência Ativa (P, kW / MW): Potência que efetivamente realiza trabalho elétrico (iluminação, aquecimento, motores).")
linhas_relatorio.append("  * Potência Aparente (S, kVA / MVA): Potência total resultante (S = sqrt(P² + Q²)), que determina o limite térmico de trafos e cabos.")
linhas_relatorio.append("  * Fator de Potência (FP): Razão P / S (entre 0 e 1,000), indicando a eficiência com que a potência aparente é convertida em trabalho útil.")
linhas_relatorio.append("  * Carregamento (%): Relação percentual entre a Potência Aparente máxima observada e a Capacidade Nominal do transformador (50 MVA).")
linhas_relatorio.append("  * CTMT: Circuito de Distribuição em Média Tensão (Alimentador primário de 13,8 kV que atende aos bairros).")
linhas_relatorio.append("  * Tap: Posição reguladora da relação de transformação que ajusta o nível de tensão entregue ao secundário.")
linhas_relatorio.append("===================================================================================================================\n")

texto_relatorio_completo = "\n".join(linhas_relatorio)
print(texto_relatorio_completo)

arquivo_txt_relatorio = caminho_sem_sobrescrever(pasta_graficos, "Relatorio_Carregamento_Subestacao_Alimentadores", "txt")
with open(arquivo_txt_relatorio, 'w', encoding='utf-8') as f_txt:
    f_txt.write(texto_relatorio_completo)
print(f"[ARQUIVO] Relatório executivo completo em texto salvo em:\n  -> '{arquivo_txt_relatorio}'")

df_rel_trafos = pd.DataFrame(tabela_tr_dados)
arquivo_csv_trafos = caminho_sem_sobrescrever(pasta_graficos, "Relatorio_Carregamento_Trafos_AT", "csv")
df_rel_trafos.to_csv(arquivo_csv_trafos, index=False, sep=';', encoding='utf-8')

df_rel_ctmt = pd.DataFrame(tabela_ctmt_dados)
arquivo_csv_ctmt = caminho_sem_sobrescrever(pasta_graficos, "Relatorio_Carregamento_Alimentadores_CTMT", "csv")
df_rel_ctmt.to_csv(arquivo_csv_ctmt, index=False, sep=';', encoding='utf-8')

print(f"[ARQUIVO] Planilhas executivas CSV salvas em:\n  -> '{arquivo_csv_trafos}'\n  -> '{arquivo_csv_ctmt}'")

try:
    plt.figure(figsize=(12, 6))
    tempo_horas_tr = [step * 0.25 for step in range(1, 97)]
    cores_tr = {
        'GOL-S-TRF-TR1': '#e74c3c',
        'GOL-S-TRF-TR2': '#3498db',
        'GOL-S-TRF-TR3': '#2ecc71',
        'GOL-S-TRF-TR4': '#9b59b6'
    }
    for tr in trafos_subestacao:
        tr_short = tr.replace("GOL-S-TRF-", "")
        curva_mw = [p / 1000.0 for p in perfil_p_trafos[tr]]
        p_max_tr_mw = dados_trafos_at[tr]['p_max_kw'] / 1000.0
        plt.plot(
            tempo_horas_tr,
            curva_mw,
            label=f"{tr_short} (Pico: {p_max_tr_mw:.1f} MW)",
            color=cores_tr.get(tr, '#333333'),
            linewidth=2
        )
    plt.axhline(y=50.0, color='#e67e22', linestyle='--', linewidth=1.5, label='Capacidade Nominal (50 MVA)')
    plt.title('Curva de Carregamento Diário dos 4 Transformadores da Subestação (AT/MT 230/13.8 kV)', fontsize=13, fontweight='bold')
    plt.xlabel('Hora do Dia (h)', fontsize=11)
    plt.ylabel('Potência Ativa (MW)', fontsize=11)
    plt.xticks(range(1, 25))
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='upper right', fontsize=10)
    plt.tight_layout()

    output_grafico_trafos = caminho_sem_sobrescrever(pasta_graficos, "Curva_Carregamento_Trafos_AT_24h", "svg")
    plt.savefig(output_grafico_trafos, format='svg')
    plt.close()
    print(f"[GRÁFICO] Curva comparativa de carregamento dos transformadores salva em:\n  -> '{output_grafico_trafos}'")
except Exception as e_plot:
    print(f"[AVISO] Não foi possível salvar gráfico comparativo de trafos: {e_plot}")

print("\n[AUDITORIA] Analisando perfil de tensão detalhado em todos os nós da rede...")
bnames = dss.Circuit.AllBusNames()
registros_auditoria = []

for b in bnames:
    dss.Circuit.SetActiveBus(b)
    kv_base_dss = dss.Bus.kVBase()
    v_base_dss_v = kv_base_dss * 1000.0
    v_mag = dss.Bus.VMagAngle()
    nodes = dss.Bus.Nodes()
    for idx, no in enumerate(nodes):
        v_real = v_mag[2 * idx]
        if v_real < 10.0:
            categoria = "Fase Aberta / Desenergizada (<10 V)"
            nivel_fisico = "Desconectado"
            v_esperada = v_base_dss_v if v_base_dss_v > 0 else 220.0
            pu_real = 0.0
            pu_dss = 0.0
        else:
            if v_real > 50000.0:
                nivel_fisico = "AT (230 kV)"
                v_esperada = 132790.56191361393
            elif v_real > 1000.0:
                nivel_fisico = "MT (13.8 kV)"
                v_esperada = 7967.433714816836
            else:
                nivel_fisico = "BT (380/220 V)"
                v_esperada = 220.0

            pu_real = v_real / v_esperada
            pu_dss = (v_real / v_base_dss_v) if v_base_dss_v > 0 else 0.0

            # 3. Classificar com base nos critérios de conformidade (0.90 a 1.10 PU)
            LIMITE_SUBTENSAO_PU = 0.90
            LIMITE_SOBRETENSAO_PU = 1.10

            if (v_real > 1000.0 and v_base_dss_v < 1000.0) or (v_real < 1000.0 and v_base_dss_v > 1000.0):
                categoria = "Inconsistência de Base OpenDSS (Falso PU)"
            elif pu_real < LIMITE_SUBTENSAO_PU:
                categoria = f"Subtensão (< {LIMITE_SUBTENSAO_PU:.2f} PU - Precária/Fora do Padrão)"
            elif pu_real > LIMITE_SOBRETENSAO_PU:
                categoria = f"Sobretensão (> {LIMITE_SOBRETENSAO_PU:.2f} PU - Precária/Fora do Padrão)"
            else:
                categoria = f"Tensão Adequada ({LIMITE_SUBTENSAO_PU:.2f} a {LIMITE_SOBRETENSAO_PU:.2f} PU)"

        registros_auditoria.append({
            'Barra': b,
            'Fase': no,
            'Nivel_Fisico': nivel_fisico,
            'Tensao_Real_V': round(v_real, 2),
            'Base_OpenDSS_V': round(v_base_dss_v, 2),
            'Base_Esperada_V': round(v_esperada, 2),
            'PU_OpenDSS': round(pu_dss, 4),
            'PU_Real': round(pu_real, 4),
            'Classificacao': categoria
        })

df_auditoria = pd.DataFrame(registros_auditoria)
arquivo_auditoria = caminho_sem_sobrescrever(pasta_graficos, "Relatorio_Tensoes_Detalhadas", "csv")
df_auditoria.to_csv(arquivo_auditoria, index=False, sep=';')
print(f"[ARQUIVO] Relatório detalhado de todas as barras e nós salvo em:\n  -> '{arquivo_auditoria}'")

nos_ativos = df_auditoria[df_auditoria['Tensao_Real_V'] >= 10.0]
nos_subtensao = df_auditoria[df_auditoria['Classificacao'].str.startswith("Subtensão")]
nos_sobretensao = df_auditoria[df_auditoria['Classificacao'].str.startswith("Sobretensão")]
nos_erro_base = df_auditoria[df_auditoria['Classificacao'] == 'Inconsistência de Base OpenDSS (Falso PU)']
nos_normais = df_auditoria[df_auditoria['Classificacao'].str.startswith("Tensão Adequada")]
nos_abertos = df_auditoria[df_auditoria['Classificacao'] == 'Fase Aberta / Desenergizada (<10 V)']

print("\n=================================================================")
print("RESUMO EXECUTIVO DO PERFIL DE TENSÃO:")
print(f"Total de nós elétricos avaliados: {len(df_auditoria):,}")
print(f"  [OK] Nós com Tensão Adequada ({LIMITE_SUBTENSAO_PU:.2f} - {LIMITE_SOBRETENSAO_PU:.2f} PU):  {len(nos_normais):>6} ({len(nos_normais)/len(df_auditoria)*100:.1f}%)")
print(f"  [--] Fases Abertas / Desenergizadas (<10 V):       {len(nos_abertos):>6} ({len(nos_abertos)/len(df_auditoria)*100:.1f}%)")
print(f"  [!!] Inconsistências de Base OpenDSS (Falso PU):   {len(nos_erro_base):>6} ({len(nos_erro_base)/len(df_auditoria)*100:.1f}%)")
print(f"  [ALERTA] Subtensões Precárias (< {LIMITE_SUBTENSAO_PU:.2f} PU):    {len(nos_subtensao):>6} ({len(nos_subtensao)/len(df_auditoria)*100:.1f}%)")
print(f"  [ALERTA] Sobretensões Precárias (> {LIMITE_SOBRETENSAO_PU:.2f} PU):  {len(nos_sobretensao):>6} ({len(nos_sobretensao)/len(df_auditoria)*100:.1f}%)")
print("-----------------------------------------------------------------")


if not nos_ativos.empty:
    idx_min = nos_ativos['PU_Real'].idxmin()
    idx_max = nos_ativos['PU_Real'].idxmax()
    print(f"Tensão Mínima Real (Nós Ativos): {nos_ativos.loc[idx_min, 'PU_Real']:.4f} PU ({nos_ativos.loc[idx_min, 'Tensao_Real_V']:.1f} V na barra {nos_ativos.loc[idx_min, 'Barra']}.{nos_ativos.loc[idx_min, 'Fase']})")
    print(f"Tensão Máxima Real (Nós Ativos): {nos_ativos.loc[idx_max, 'PU_Real']:.4f} PU ({nos_ativos.loc[idx_max, 'Tensao_Real_V']:.1f} V na barra {nos_ativos.loc[idx_max, 'Barra']}.{nos_ativos.loc[idx_max, 'Fase']})")
print("=================================================================")

if not nos_erro_base.empty:
    print("\n[ESCLARECIMENTO] Exemplos de nós com FALSO PU Alto por Inconsistência de Base:")
    print("  (A tensão real em Volts está correta na MT, mas a base usada pela ferramenta foi de BT)")
    print(nos_erro_base.sort_values(by='PU_OpenDSS', ascending=False).head(5)[['Barra', 'Fase', 'Nivel_Fisico', 'Tensao_Real_V', 'Base_OpenDSS_V', 'PU_OpenDSS', 'PU_Real']].to_string(index=False))

if not nos_subtensao.empty:
    print("\n[CRÍTICO] Top 5 Maiores Quedas de Tensão REAIS da Rede (Pontas de Ramal):")
    print(nos_subtensao.sort_values(by='PU_Real').head(5)[['Barra', 'Fase', 'Nivel_Fisico', 'Tensao_Real_V', 'Base_Esperada_V', 'PU_Real']].to_string(index=False))

trafos_mt = [t for t in dss.Transformers.AllNames() if t.startswith("untrmt_")]
def _is_trafo_energizado(t):
    dss.Transformers.Name(t)
    bnames = dss.CktElement.BusNames()
    if not bnames:
        return False
    dss.Circuit.SetActiveBus(bnames[0].split('.')[0])
    v = dss.Bus.VMagAngle()
    return bool(v and v[0] > 1000)

trafos_energizados = sum(1 for t in trafos_mt if _is_trafo_energizado(t))

ssdbt_caminho = os.path.join(diretorio_atual, 'dados_goiania_leste', '05_SSDBT_linhas_BT.csv')
if not os.path.exists(ssdbt_caminho):
    ssdbt_caminho = 'dados_goiania_leste/05_SSDBT_linhas_BT.csv'
ssdbt = pd.read_csv(ssdbt_caminho, usecols=['PAC_1', 'PAC_2'])
pacs_bt = set(ssdbt['PAC_1'].astype(str)) | set(ssdbt['PAC_2'].astype(str))
barras_bt_energizadas = 0
for b in pacs_bt:
    dss.Circuit.SetActiveBus(b)
    v_b = dss.Bus.VMagAngle()
    if v_b and v_b[0] > 50:
        barras_bt_energizadas += 1

print("\n=================================================================")
print("RESUMO DE CONECTIVIDADE FÍSICA:")
print(f"Transformadores MT energizados: {trafos_energizados} de {len(trafos_mt)} ({trafos_energizados/len(trafos_mt)*100:.1f}%)")
print(f"Barras de BT energizadas (~220V): {barras_bt_energizadas} de {len(pacs_bt)} ({barras_bt_energizadas/len(pacs_bt)*100:.1f}%)")
print("=================================================================")

dss.Monitors.Name("mon_subestacao")
ch_p1 = dss.Monitors.Channel(1)
ch_p2 = dss.Monitors.Channel(3)
ch_p3 = dss.Monitors.Channel(5)

if len(ch_p1) > 0:
    potencia_total_kw = [p1 + p2 + p3 for p1, p2, p3 in zip(ch_p1, ch_p2, ch_p3)]
    if sum(potencia_total_kw) < 0:
        potencia_total_kw = [-p for p in potencia_total_kw]

    tempo_horas = [i * 0.25 for i in range(1, len(potencia_total_kw) + 1)]

    plt.figure(figsize=(10, 6))
    plt.plot(tempo_horas, potencia_total_kw, marker='o', markersize=4, color='#ff7f0e', linewidth=2)
    plt.title('Curva de Carga Diária da Subestação (Duck Curve Base)')
    plt.xlabel('Hora do Dia')
    plt.ylabel('Potência Ativa (kW)')
    plt.grid(True)
    plt.xticks(range(1, 25))

    output_svg = caminho_sem_sobrescrever(pasta_graficos, "Curva_Carga_Base", "svg")
    plt.savefig(output_svg, format='svg')
    print(f"\n[GRÁFICO] Curva de carga salva em: '{output_svg}'.")


def parse_wkt_coords(wkt):
    if pd.isna(wkt):
        return []
    return [(float(lon), float(lat)) for lon, lat in re.findall(r'([-]?\d+\.\d+)\s+([-]?\d+\.\d+)', str(wkt))]


try:
    print("\n[MAPA] Gerando mapa geográfico da rede com linhas por nível de tensão...")

    csv_ssdmt = os.path.join(diretorio_atual, "dados_goiania_leste", "04_SSDMT_linhas_MT.csv")
    csv_ssdbt = os.path.join(diretorio_atual, "dados_goiania_leste", "05_SSDBT_linhas_BT.csv")
    csv_untrmt = os.path.join(diretorio_atual, "dados_goiania_leste", "07a_UNTRMT_trafos_distribuicao.csv")
    csv_eqtrmt = os.path.join(diretorio_atual, "dados_goiania_leste", "07b_EQTRMT_dados_eletricos_trafos_dist.csv")
    csv_buscoords = os.path.join(diretorio_atual, "modelo_opendss", "buscoords.dss")

    df_mt = pd.read_csv(csv_ssdmt, usecols=['COD_ID', 'geometria_wkt'])
    df_bt = pd.read_csv(csv_ssdbt, usecols=['COD_ID', 'geometria_wkt'])
    df_trafos = pd.read_csv(csv_untrmt, usecols=['COD_ID', 'PAC_1', 'PAC_2', 'POT_NOM'])
    df_eqtrmt = pd.read_csv(csv_eqtrmt, usecols=['UNI_TR_MT'])

    coords_map = {}
    with open(csv_buscoords, 'r') as fb:
        for line in fb:
            parts = line.strip().split(',')
            if len(parts) >= 3:
                pac = parts[0].strip()
                try:
                    lon = float(parts[1].strip())
                    lat = float(parts[2].strip())
                    coords_map[pac] = (lon, lat)
                except ValueError:
                    pass

    trafos_divergiram = set()
    mapa_pac_tr = {}
    for r in df_trafos.itertuples():
        tr_id = str(r.COD_ID).strip()
        p1 = str(r.PAC_1).strip()
        p2 = str(r.PAC_2).strip()
        mapa_pac_tr[p1] = tr_id
        mapa_pac_tr[p2] = tr_id
        mapa_pac_tr[p1 + 'b'] = tr_id
        mapa_pac_tr[p2 + 'b'] = tr_id

    for b in barras_colapsadas_dia:
        b_limpa = str(b).strip()
        if b_limpa in mapa_pac_tr:
            trafos_divergiram.add(mapa_pac_tr[b_limpa])
        elif b_limpa.endswith('b') and b_limpa[:-1] in mapa_pac_tr:
            trafos_divergiram.add(mapa_pac_tr[b_limpa[:-1]])

    print(f"  Transformadores com colapso/divergência de tensão: {len(trafos_divergiram)} de {len(trafos_mt_nomes)}")
    print(f"  Transformadores com sobrecarga ao longo do dia: {len(trafos_sobrecarregados)} de {len(trafos_mt_nomes)}")

    fig, ax = plt.subplots(figsize=(16, 12))
    ax.set_facecolor('#1a1a2e')
    fig.patch.set_facecolor('#0f0f23')

    for row in df_bt.itertuples():
        pts = parse_wkt_coords(row.geometria_wkt)
        if len(pts) >= 2:
            lons = [p[0] for p in pts]
            lats = [p[1] for p in pts]
            ax.plot(lons, lats, color='#2ecc71', linewidth=0.3, alpha=0.4)

    for row in df_mt.itertuples():
        pts = parse_wkt_coords(row.geometria_wkt)
        if len(pts) >= 2:
            lons = [p[0] for p in pts]
            lats = [p[1] for p in pts]
            ax.plot(lons, lats, color='#3498db', linewidth=0.8, alpha=0.7)

    trafos_normais_lon = []
    trafos_normais_lat = []
    trafos_sobre_lon = []
    trafos_sobre_lat = []
    trafos_div_lon = []
    trafos_div_lat = []

    for row in df_trafos.itertuples():
        pac1 = str(row.PAC_1).strip()
        cod_id = str(row.COD_ID).strip()
        if pac1 in coords_map:
            lon, lat = coords_map[pac1]
            if cod_id in trafos_divergiram:
                trafos_div_lon.append(lon)
                trafos_div_lat.append(lat)
            elif cod_id in trafos_sobrecarregados:
                trafos_sobre_lon.append(lon)
                trafos_sobre_lat.append(lat)
            else:
                trafos_normais_lon.append(lon)
                trafos_normais_lat.append(lat)

    if trafos_normais_lon:
        ax.scatter(trafos_normais_lon, trafos_normais_lat, c='#2ecc71', s=5, alpha=0.4, zorder=4, edgecolors='none')

    if trafos_sobre_lon:
        ax.scatter(trafos_sobre_lon, trafos_sobre_lat, c='#f39c12', s=22, alpha=0.85, zorder=6, edgecolors='white', linewidths=0.5, marker='^')

    if trafos_div_lon:
        ax.scatter(trafos_div_lon, trafos_div_lat, c='#ff2a2a', s=45, alpha=1.0, zorder=7, edgecolors='white', linewidths=0.8, marker='X')

    legenda_mt = mlines.Line2D([], [], color='#3498db', linewidth=2, label='Linhas MT (13,8 kV)')
    legenda_bt = mlines.Line2D([], [], color='#2ecc71', linewidth=1.5, label='Linhas BT (220/380 V)')
    legenda_trafo_ok = mlines.Line2D([], [], color='#2ecc71', marker='o', linestyle='None', markersize=5, label=f'Trafo Normal ({len(trafos_normais_lon)})')
    legenda_trafo_sob = mlines.Line2D([], [], color='#f39c12', marker='^', linestyle='None', markersize=7, markeredgecolor='white', markeredgewidth=0.5, label=f'Trafo Sobrecarregado ({len(trafos_sobre_lon)})')
    legenda_trafo_div = mlines.Line2D([], [], color='#ff2a2a', marker='X', linestyle='None', markersize=8, markeredgecolor='white', markeredgewidth=0.8, label=f'Trafo com Divergência ({len(trafos_div_lon)})')

    ax.legend(
        handles=[legenda_mt, legenda_bt, legenda_trafo_ok, legenda_trafo_sob, legenda_trafo_div],
        loc='upper left',
        fontsize=9,
        facecolor='#16213e',
        edgecolor='#e2e8f0',
        labelcolor='white',
        framealpha=0.9
    )

    ax.set_title(
        'Mapa Geográfico da Rede - SE Goiânia Leste\nLinhas por Nível de Tensão e Transformadores (Normais, Sobrecarregados e Divergentes)',
        color='white',
        fontsize=14,
        fontweight='bold',
        pad=15
    )
    ax.set_xlabel('Longitude', color='#a0aec0', fontsize=10)
    ax.set_ylabel('Latitude', color='#a0aec0', fontsize=10)
    ax.tick_params(colors='#a0aec0', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#2d3748')
    ax.set_aspect('equal')

    plt.tight_layout()
    output_mapa_svg = caminho_sem_sobrescrever(pasta_graficos, "Mapa_Rede_Tensao", "svg")
    plt.savefig(output_mapa_svg, format='svg', facecolor=fig.get_facecolor(), edgecolor='none')
    print(f"[GRÁFICO] Mapa da rede salvo com sucesso em:\n  -> '{output_mapa_svg}'.")
    plt.close('all')
except Exception as e:
    print(f"[ERRO] Falha ao gerar mapa geográfico: {e}")
    import traceback
    traceback.print_exc()

tempo_total = time.time() - t_inicio
minutos = int(tempo_total // 60)
segundos = tempo_total % 60
print("\n" + "=" * 70)
if minutos > 0:
    print(f"[TEMPO DE EXECUÇÃO] Simulação concluída em {minutos}m {segundos:.2f}s ({tempo_total:.2f} s)!")
else:
    print(f"[TEMPO DE EXECUÇÃO] Simulação concluída em {segundos:.2f} segundos!")
print("=" * 70 + "\n")
