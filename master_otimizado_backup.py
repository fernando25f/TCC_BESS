# ==============================================================================
# MASTER OTIMIZADO DE SIMULAÇÃO - SUBESTAÇÃO GOIÂNIA LESTE (OPENDSS)
# ==============================================================================
# Este script executa a simulação diária (Daily 24h, 96 passos de 15 min) de
# toda a rede elétrica da Subestação Goiânia Leste (27 alimentadores CTMT),
# aplicando técnicas avançadas de desempenho computacional e depuração:
#
#   1. ISOLAMENTO TOTAL DE CSVs: Lê exclusivamente os arquivos compilados .dss
#      e o arquivo de metadados 'alimentadores_info.json' na pasta 'modelo_opendss/'.
#      Nenhuma leitura na pasta de dados brutos (CSVs) é realizada aqui.
#   2. RENDERIZAÇÃO EM LOTE (LineCollection): Desenho de dezenas de milhares
#      de linhas elétricas em menos de 1 segundo (aceleração de ~60x).
#   3. CACHE ESTÁTICO DE DADOS: Consulta parâmetros fixos (kVA de trafos, fases)
#      apenas uma vez, evitando centenas de milhares de chamadas de API no pico.
#   4. CONTROLE DE TAP PONTUAL: Ajusta o tap do transformador apenas nos
#      momentos de transição (17h15 e 22h15), eliminando comandos redundantes.
#   5. AUDITORIA NÓ A NÓ EM MEMÓRIA: Extração rápida de tensões e conectividade
#      física em estruturas de tuplas sem consultas duplicadas à API.
#   6. PAINEL DE DEPURAÇÃO E DIAGNÓSTICO: Rastreamento detalhado de tempo por
#      etapa e identificação imediata dos trechos elétricos mais críticos.
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

# Marcação de tempo inicial total
t_inicio_global = time.time()

# ==============================================================================
# 1. PAINEL DE CONTROLE - PARÂMETROS DA SIMULAÇÃO (AJUSTES DO USUÁRIO)
# Configure aqui os parâmetros desejados para cada cenário antes de executar:
# ==============================================================================

# [A] CARREGAMENTO E FATOR DE DEMANDA (FD)
# ------------------------------------------------------------------------------
# Fator aplicado sobre a carga instalada total da rede (100% CAR_INST gerada no DSS):
FATOR_DEMANDA = 0.11        # Ex: 0.11 = 11.0% da Carga Instalada (0.15 = 15.0%, etc.)

# [B] GERAÇÃO DISTRIBUÍDA (GD SOLAR FOTOVOLTAICA)
# ------------------------------------------------------------------------------
HABILITAR_GD = True         # True: simula com as usinas solares; False: sem GD
FATOR_GD = 2.5              # Multiplicador de escala da GD (1.0 = 100% da BDGD, 2.5 = 250%, etc.)
MES_SOLAR = "Abril"         # "Abril" (Média Anual), "Julho" (Inverno Seco - Pico), "Outubro" (Chuvoso)
TIPO_CURVA_GD = "STC"       # "STC" (base 1000 W/m² real) ou "PicoUnitario" (pico normalizado em 1.0)

# [C] SISTEMA DE ARMAZENAMENTO POR BATERIA (BESS)
# ------------------------------------------------------------------------------
HABILITAR_BESS = False       # True: com sistema de baterias BESS; False: sem BESS

# [D] CONTROLE DE TAP DOS TRANSFORMADORES DA SUBESTAÇÃO (AT/MT 230/13.8 kV)
# ------------------------------------------------------------------------------
TAP_NORMAL = 1.000          # Tap base fora do horário de pico
TAP_PICO = 1.035            # Tap elevado durante o horário de pico
PASSO_INICIO_PICO = 72      # Passo de início da elevação do tap (72 * 15 min = 18:00h)
RETORNAR_TAP_NORMAL = False # False: mantém o tap elevado até 24h; True: retorna ao normal em PASSO_FIM_PICO
PASSO_FIM_PICO = 96         # Passo final (96 = 24:00h se RETORNAR_TAP_NORMAL=False; 88 = 22:00h se True)

# [E] EXPORTAÇÃO E MONITORAMENTO EM DISCO
# ------------------------------------------------------------------------------
SALVAR_MONITORES_CSV = False  # True: grava os arquivos CSV 'Subestacao_Goiania_Leste_Mon_*.csv' em logs_TCC/monitores
                              # False: mantém medições em memória RAM para os gráficos sem poluir o disco com CSVs

# [F] LIMITES DE CONFORMIDADE DE TENSÃO (CRITÉRIOS DOS RELATÓRIOS)
# ------------------------------------------------------------------------------
LIMITE_SUBTENSAO_PU = 0.90    # Tensão fora do padrão inferior (< 0.90 PU - Tensão Precária)
LIMITE_SOBRETENSAO_PU = 1.10  # Tensão fora do padrão superior (> 1.10 PU - Tensão Precária)

# ==============================================================================
# 2. CONFIGURAÇÃO DE DIRETÓRIOS E ESTRUTURA DE SAÍDA (TCC)
# ==============================================================================
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
pasta_modelo = os.path.join(diretorio_atual, "modelo_opendss")

# Pastas principais organizadas para o TCC
pasta_graficos_tcc = os.path.join(diretorio_atual, "graficos_TCC")
pasta_logs_tcc     = os.path.join(diretorio_atual, "logs_TCC")

# Subpastas de Gráficos:
pasta_graf_subestacao = os.path.join(pasta_graficos_tcc, "subestacao")
pasta_graf_trafo_dist = os.path.join(pasta_graficos_tcc, "trafo_distribuicao")
pasta_graf_mapa_rede  = os.path.join(pasta_graficos_tcc, "mapa_rede")

# Subpastas de Logs e Relatórios:
pasta_log_divergencia = os.path.join(pasta_logs_tcc, "divergencia")
pasta_log_monitores   = os.path.join(pasta_logs_tcc, "monitores")
pasta_log_relatorios  = os.path.join(pasta_logs_tcc, "relatorios")

# Criação automática de todas as subpastas
for p in [pasta_graf_subestacao, pasta_graf_trafo_dist, pasta_graf_mapa_rede,
          pasta_log_divergencia, pasta_log_monitores, pasta_log_relatorios]:
    os.makedirs(p, exist_ok=True)

pasta_saida = pasta_graficos_tcc
pasta_graficos = pasta_logs_tcc

# Tags formatadas para relatórios e títulos de gráficos
fd_val = FATOR_DEMANDA * 100
FD_PCT_STR = f"{int(fd_val)}%" if fd_val.is_integer() else f"{fd_val:.1f}%"
GD_TAG = f"GD: Curva {MES_SOLAR} (x{FATOR_GD:.1f})" if HABILITAR_GD else "Sem GD"

# Subtítulo descritivo com parâmetros de simulação para os gráficos
gd_desc = f"True x{FATOR_GD:g}" if HABILITAR_GD else "False"
bess_desc = "True" if HABILITAR_BESS else "False"
SUBTITULO_PARAMETROS = f"FD = {FD_PCT_STR} | GD = {gd_desc} | BESS = {bess_desc}"

def caminho_sem_sobrescrever(pasta, nome_base, extensao):
    """Retorna um caminho de arquivo que não sobrescreve existentes.
    Se 'nome_base.extensao' já existe, tenta 'nome_base_v2.extensao', _v3, etc."""
    caminho = os.path.join(pasta, f"{nome_base}.{extensao}")
    if not os.path.exists(caminho):
        return caminho
    versao = 2
    while True:
        caminho = os.path.join(pasta, f"{nome_base}_v{versao}.{extensao}")
        if not os.path.exists(caminho):
            return caminho
        versao += 1

# Caminhos dos arquivos de modelo OpenDSS (.dss)
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

# Carregamento de metadados compilados pelo conversor (sem tocar em CSVs brutos)
dict_ctmt_info = {}
trafos_subestacao_info = {}
if os.path.exists(arquivo_alimentadores_json):
    with open(arquivo_alimentadores_json, "r", encoding="utf-8") as fj:
        metadados = json.load(fj)
        dict_ctmt_info = metadados.get("alimentadores", {})
        trafos_subestacao_info = metadados.get("trafos_subestacao", {})
else:
    print(f"[AVISO] Arquivo {arquivo_alimentadores_json} não encontrado.")
    print("Execute 'converter_csv_para_dss.py' para gerar os metadados compilados.")

# Lista dos 4 transformadores da subestação (AT/MT - 230/13.8 kV) e suas barras secundárias
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

print("=" * 70)
print("INICIALIZANDO SIMULAÇÃO OPENDSS (VERSÃO OTIMIZADA)")
print("=" * 70)
t_inicio_carga = time.time()

# ------------------------------------------------------------------------------
# 2. CARREGAMENTO E COMPILAÇÃO DO CIRCUITO NO OPENDSS
# ------------------------------------------------------------------------------
dss.Command("clear")

# Criar o circuito base: Barra da subestação (5001462) com tensão nominal de 230 kV
dss.Command("new circuit.Subestacao_Goiania_Leste basekv=230 bus1=5001462 pu=1.05 phases=3")

# Carregamento modular dos componentes através de comandos 'redirect'
dss.Command(f'redirect "{arquivo_transformador_AT}"')
num_trafos_at = dss.Transformers.Count()
print(f"[OK] Transformadores AT carregados: {num_trafos_at}")

dss.Command(f'redirect "{arquivo_disjuntores_mt}"')
num_dj_mt = dss.Lines.Count()
print(f"[OK] Disjuntores MT carregados: {num_dj_mt}")

dss.Command(f'redirect "{arquivo_seccionadoras_mt}"')
num_sec_mt = dss.Lines.Count() - num_dj_mt
print(f"[OK] Seccionadoras MT carregadas: {num_sec_mt}")

dss.Command(f'redirect "{arquivo_transformador_MT}"')
num_trafos_mt = dss.Transformers.Count() - num_trafos_at
print(f"[OK] Transformadores MT carregados: {num_trafos_mt}")

dss.Command(f'redirect "{arquivo_linhas_mt}"')
num_linhas_mt = dss.Lines.Count() - num_sec_mt - num_dj_mt
print(f"[OK] Linhas MT carregadas: {num_linhas_mt}")

if os.path.exists(arquivo_capacitores_mt):
    dss.Command(f'redirect "{arquivo_capacitores_mt}"')
    print(f"[OK] Bancos de Capacitores MT carregados: {dss.Capacitors.Count()}")

dss.Command(f'redirect "{arquivo_linhas_bt}"')
num_linhas_bt = dss.Lines.Count() - (num_linhas_mt + num_sec_mt + num_dj_mt)
print(f"[OK] Linhas BT carregadas: {num_linhas_bt}")

dss.Command(f'redirect "{arquivo_curva_carga}"')
print(f"[OK] Curvas de carga (LoadShapes) carregadas: {dss.LoadShape.Count()}")

dss.Command(f'redirect "{arquivo_carga_bt}"')
num_cargas_bt = dss.Loads.Count()
print(f"[OK] Cargas BT carregadas: {num_cargas_bt}")

if os.path.exists(arquivo_carga_mt):
    dss.Command(f'redirect "{arquivo_carga_mt}"')
    num_cargas_mt = dss.Loads.Count() - num_cargas_bt
    print(f"[OK] Cargas MT carregadas: {num_cargas_mt}")

if os.path.exists(arquivo_buscoords):
    dss.Command(f'Buscoords "{arquivo_buscoords}"')
    print("[OK] Coordenadas geográficas (Buscoords) carregadas!")

# Carregar monitores compilados diretamente pelo conversor
if os.path.exists(arquivo_monitores):
    dss.Command(f'redirect "{arquivo_monitores}"')
    print(f"[OK] Monitores elétricos carregados via '{os.path.basename(arquivo_monitores)}': {dss.Monitors.Count()}")
else:
    # Fallback caso o arquivo monitores.dss ainda não tenha sido gerado
    print("[AVISO] Arquivo monitores.dss não encontrado. Criando monitores essenciais dinamicamente...")
    dss.Command("new monitor.mon_subestacao element=vsource.source terminal=1 mode=1 ppolar=no")
    for tr in trafos_subestacao:
        tr_short = tr.replace("GOL-S-TRF-", "")
        dss.Command(f"new monitor.mon_tr_{tr_short}_pot element=transformer.{tr} terminal=2 mode=1 ppolar=no")
        dss.Command(f"new monitor.mon_tr_{tr_short}_vi element=transformer.{tr} terminal=2 mode=0")
    for cod_id in dict_ctmt_info.keys():
        dss.Command(f"new monitor.mon_ctmt_{cod_id}_pot element=line.DJ_{cod_id} terminal=1 mode=1 ppolar=no")
        dss.Command(f"new monitor.mon_ctmt_{cod_id}_vi element=line.DJ_{cod_id} terminal=1 mode=0")

# Carregar curvas solares e usinas de Geração Distribuída (GD)
if HABILITAR_GD:
    if os.path.exists(arquivo_curva_solar):
        dss.Command(f'redirect "{arquivo_curva_solar}"')
    if os.path.exists(arquivo_gd):
        dss.Command(f'redirect "{arquivo_gd}"')
        # Configurar a curva diária solicitada pelo usuário (Abril, Julho ou Outubro)
        sufixo = "_PicoUnitario" if TIPO_CURVA_GD == "PicoUnitario" else ""
        nome_curva_ativa = f"Curva_Solar_{MES_SOLAR}{sufixo}"
        num_pv = dss.PVsystems.Count()
        pot_total_gd_kw = 0.0
        if num_pv > 0:
            for pv_nome in dss.PVsystems.AllNames():
                dss.PVsystems.Name(pv_nome)
                dss.PVsystems.daily(nome_curva_ativa)
                if FATOR_GD != 1.0:
                    dss.PVsystems.Pmpp(dss.PVsystems.Pmpp() * FATOR_GD)
                    dss.PVsystems.kVARated(dss.PVsystems.kVARated() * FATOR_GD)
                pot_total_gd_kw += dss.PVsystems.Pmpp()
        num_gen = dss.Generators.Count()
        if num_gen > 0:
            for g_nome in dss.Generators.AllNames():
                dss.Generators.Name(g_nome)
                dss.Generators.daily(nome_curva_ativa)
                if FATOR_GD != 1.0:
                    dss.Generators.kW(dss.Generators.kW() * FATOR_GD)
                pot_total_gd_kw += dss.Generators.kW()
        num_gd = num_pv + num_gen
        print(f"[OK] Geração Distribuída carregada: {num_gd} usinas solares ativas ({num_pv} PVSystems, {num_gen} Generators)")
        print(f"     -> Fator de GD: {FATOR_GD:.2f}x | Potência Total GD: {pot_total_gd_kw/1000:.2f} MW (Curva: {nome_curva_ativa})")
    else:
        print("[AVISO] Arquivo geracao_distribuida.dss não encontrado. Simulação prosseguirá sem GD.")
else:
    print("[GD] Geração Distribuída desativada por configuração (HABILITAR_GD = False).")

# Validação de sintaxe
erro = dss.Error.Description()
if erro:
    print(f"[ERRO DE SINTAXE OPENDSS]: {erro}")
else:
    print("[OK] Sintaxe aceita sem erros pelo motor OpenDSS!")

dss.Command("Set voltagebases=[230.0, 13.8, 0.38]")
dss.Command("Calcvoltagebases")

# Ajuste dinâmico de carregamento no OpenDSS conforme o Fator de Demanda configurado
# Como os arquivos .dss contêm 100% da Carga Instalada, LoadMult é o próprio FATOR_DEMANDA
dss.Command(f"Set LoadMult={FATOR_DEMANDA:.4f}")
print(f"[DEMANDA] Fator de Demanda configurado: {FD_PCT_STR} (LoadMult OpenDSS: {FATOR_DEMANDA:.4f})")

# Inicialização da rede: Resolve o fluxo em modo Snapshot para energizar toda a rede,
# montar a matriz de admitância nodal (Ybus) e inicializar as tensões de todas as barras
dss.Command("set mode=snapshot")
dss.Command("solve")
p_ini_mw = -dss.Circuit.TotalPower()[0] / 1000.0
print(f"[OK] Fluxo estático inicial (Snapshot) resolvido: Rede energizada ({p_ini_mw:.2f} MW).")

t_fim_carga = time.time()
print(f"[TEMPO] Carregamento completo do circuito: {t_fim_carga - t_inicio_carga:.2f} s")

# ------------------------------------------------------------------------------
# 3. PRÉ-COMPUTAÇÃO (CACHE) DE PROPRIEDADES ESTÁTICAS PARA ALTO DESEMPENHO
# ------------------------------------------------------------------------------
# Armazena a potência nominal de placa (kVA) e número de fases dos transformadores
# de distribuição em memória para não consultar a API repetidas vezes no laço diário.
trafos_mt_nomes = [t for t in dss.Transformers.AllNames() if t.startswith('untrmt_')]
cache_trafos_mt = {}
for t_nome in trafos_mt_nomes:
    dss.Transformers.Name(t_nome)
    kva_nom = dss.Transformers.kVA()
    if kva_nom > 0:
        cache_trafos_mt[t_nome] = {
            'cod_id': t_nome.replace('untrmt_', ''),
            'kva_nom': kva_nom,
            'np': dss.CktElement.NumPhases(),
            'limite_kva': kva_nom * 1.25,
            'limite_kva2': (kva_nom * 1.25) ** 2  # Usado para evitar raiz quadrada (math.sqrt)
        }

# ------------------------------------------------------------------------------
# 4. CONFIGURAÇÃO DO FLUXO DE CARGA DIÁRIO (24h - 96 PASSOS DE 15 MIN)
# ------------------------------------------------------------------------------
# 1. Resolução estática preliminar (Snapshot):
# Obrigatório no OpenDSS para energizar as barras e inicializar a matriz de admitância nodal (Ybus).
# Sem essa inicialização estática, as cargas model=1 não conseguem calcular corrente e a rede 
# permanece com fluxo nulo (0 MW) até receber alguma mutação de circuito (como a troca de tap às 18h).
dss.Command("set mode=snapshot")
dss.Solution.Solve()

dss.Command("set mode=daily stepsize=0.25h maxiterations=50 number=1 hour=0 sec=0")
print("\n[SIMULAÇÃO] Iniciando fluxo de carga diário (24h) com passos de 15 min...")
t_inicio_sim = time.time()

convergiu_todas = True
passos_divergentes = []
tabela_potencia = []

# Estruturas para registrar as medições dos transformadores AT
dados_trafos_at = {tr: {
    'p_max_kw': 0.0, 's_max_kva': 0.0, 'q_at_pmax': 0.0,
    'hora_pico': '', 'fp_pico': 1.0,
    'v_min_pu': 999.0, 'v_max_pu': 0.0,
    'energia_kwh': 0.0
} for tr in trafos_subestacao}
perfil_p_trafos = {tr: [] for tr in trafos_subestacao}
perfil_v_trafos = {tr: [] for tr in trafos_subestacao}

# Estruturas para registrar as medições dos 27 CTMTs
dados_ctmt = {cod_id: {
    'p_max_kw': 0.0, 's_max_kva': 0.0, 'q_at_pmax': 0.0,
    'hora_pico': '', 'fp_pico': 1.0,
    'v_min_pu': 999.0, 'v_max_pu': 0.0,
    'energia_kwh': 0.0
} for cod_id in dict_ctmt_info.keys()}

# Lista para registro em memória de divergências (só grava em disco se houver divergência)
registros_divergencia = []

barras_colapsadas_dia = set()
trafos_sobrecarregados = set()
registros_sobrecarga = []  # Lista detalhada: (trafo, hora, kVA_medido, kVA_nominal, percentual)

# Parâmetros de Controle de Tap por Horário nos Transformadores da SE (definidos no painel do topo)
# TAP_NORMAL, TAP_PICO, PASSO_INICIO_PICO, PASSO_FIM_PICO configurados no início do script

# ------------------------------------------------------------------------------
# 5. LAÇO TEMPORAL DE 96 PASSOS (OTIMIZADO)
# ------------------------------------------------------------------------------
for i in range(1, 97):
    # CONTROLE DE TAP: Apenas uma mudança pontual no passo 72 (18:00h).
    # BUG OPENDSS: Quando PVSystems estão presentes no circuito, qualquer mudança de tap de
    # transformador (que força rebuild da Ybus) APÓS o primeiro rebuild pode congelar os ponteiros
    # internos dos LoadShapes, causando uma curva de carga constante ("degrau").
    # Solução: o tap é elevado às 18:00h e permanece em 1.05 até o fim da simulação (24:00h).
    # O impacto elétrico nas últimas 2h (22:00-24:00) é desprezível (<5% de elevação de tensão).
    if i == PASSO_INICIO_PICO:
        for tr in trafos_subestacao:
            dss.Command(f"Transformer.{tr}.wdg=2 tap={TAP_PICO}")
        print(f"  [CONTROLE DE TAP] Horário de pico (18:00h): Elevando tap para {TAP_PICO:.3f}...")
    elif RETORNAR_TAP_NORMAL and i == PASSO_FIM_PICO:
        for tr in trafos_subestacao:
            dss.Command(f"Transformer.{tr}.wdg=2 tap={TAP_NORMAL}")
        print(f"  [CONTROLE DE TAP] Fim do pico ({PASSO_FIM_PICO*0.25:.1f}h): Retornando tap para {TAP_NORMAL:.3f}...")

    # Chamada nativa direta em C para resolução do fluxo de potência (mais rápida que dss.Command("Solve"))
    dss.Solution.Solve()

    if not dss.Solution.Converged():
        print(f"  [ALERTA] Fluxo divergiu no passo {i:02d}!")
        convergiu_todas = False
        passos_divergentes.append(i)

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

            for b in bus_pu_valid:
                registros_divergencia.append((i, hora_div, b[0], b[1]))
                if b[1] < 0.90:
                    barras_colapsadas_dia.add(b[0])

    # Calcular a hora atual do passo
    minutos_totais = i * 15
    h = (minutos_totais // 60) % 24
    m = minutos_totais % 60
    hora_str = f"{h:02d}:{m:02d}"
    if minutos_totais == 24 * 60:
        hora_str = "24:00"

    # OTIMIZAÇÃO DE SOBRECARGA: Registra todos os eventos de sobrecarga (>125%) com horário
    for t_nome, info_tr in cache_trafos_mt.items():
        cod_id_tr = info_tr['cod_id']
        dss.Transformers.Name(t_nome)
        powers = dss.CktElement.Powers()
        n_fases = info_tr['np']
        pt = sum(powers[k * 2] for k in range(n_fases))
        qt = sum(powers[k * 2 + 1] for k in range(n_fases))
        s2 = pt**2 + qt**2
        if s2 > info_tr['limite_kva2']:
            trafos_sobrecarregados.add(cod_id_tr)
            s_kva = math.sqrt(s2)
            pct = (s_kva / info_tr['kva_nom']) * 100.0
            registros_sobrecarga.append((cod_id_tr, hora_str, s_kva, info_tr['kva_nom'], pct))

    # Potência total da subestação no instante atual
    p_kw = -dss.Circuit.TotalPower()[0]
    tabela_potencia.append((hora_str, p_kw))

    # Log periódico de progresso no console (a cada 8 passos / 2h, e no pico)
    if i % 8 == 1 or i in (PASSO_INICIO_PICO, PASSO_FIM_PICO):
        print(f"  -> Passo {i:02d}/96 ({hora_str}h): P_SE = {p_kw/1000:6.2f} MW | Convergiu: {dss.Solution.Converged()}")

    # Monitoramento dos Transformadores AT da SE
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
        perfil_p_trafos[tr].append(p_tr_kw)
        perfil_v_trafos[tr].append(v_med_step)
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

    # Monitoramento dos 27 Alimentadores (CTMTs)
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

# Salvar buffers dos monitores nativos apenas se a flag estiver ativada
if SALVAR_MONITORES_CSV:
    dss.Command(f'cd "{pasta_log_monitores}"')
    dss.Command("Save")
    dss.Command(f'cd "{diretorio_atual}"')

t_fim_sim = time.time()
print(f"[TEMPO] Simulação de 24h (96 passos) concluída em: {t_fim_sim - t_inicio_sim:.2f} s")

# Exportar CSV de divergências APENAS se houver ocorrência de divergência
if registros_divergencia:
    arquivo_divergencia = caminho_sem_sobrescrever(pasta_log_divergencia, "barras_divergencia", "csv")
    with open(arquivo_divergencia, "w", encoding="utf-8") as f_div:
        f_div.write("PASSO,HORA,BARRA,TENSAO_PU\n")
        for reg in registros_divergencia:
            f_div.write(f"{reg[0]},{reg[1]},{reg[2]},{reg[3]:.6f}\n")
    print(f"[ARQUIVO] Relatório de divergências salvo em:\n  -> '{arquivo_divergencia}'")

# Exportar CSV detalhado de sobrecarga dos transformadores MT
if registros_sobrecarga:
    arq_sobrecarga = caminho_sem_sobrescrever(pasta_log_relatorios, "Relatorio_Sobrecarga_Trafos_MT", "csv")
    with open(arq_sobrecarga, "w", encoding="utf-8") as f_sc:
        f_sc.write("TRANSFORMADOR,HORA,S_MEDIDO_KVA,S_NOMINAL_KVA,CARREGAMENTO_PCT\n")
        for reg in registros_sobrecarga:
            f_sc.write(f"{reg[0]},{reg[1]},{reg[2]:.2f},{reg[3]:.2f},{reg[4]:.1f}\n")
    print(f"[ARQUIVO] Relatório de sobrecarga dos transformadores MT salvo em:\n  -> '{arq_sobrecarga}'")

if convergiu_todas:
    print("[OK] Simulação de 24h concluída com 100% de convergência!")
else:
    print(f"[ALERTA] Divergência em {len(passos_divergentes)} passos: {passos_divergentes}")

# ------------------------------------------------------------------------------
# 6. RELATÓRIO EXECUTIVO DE DESEMPENHO E CARREGAMENTO
# ------------------------------------------------------------------------------
p_max_hora, p_max_kw = max(tabela_potencia, key=lambda x: x[1]) if tabela_potencia else ("--", 0.0)
p_final_hora, p_final_kw = tabela_potencia[-1] if tabela_potencia else ("--", 0.0)
energia_total_se_mwh = sum(p for _, p in tabela_potencia) * 0.25 / 1000.0

linhas_relatorio = []
linhas_relatorio.append("=" * 115)
linhas_relatorio.append("                        RELATÓRIO DE CARREGAMENTO E DESEMPENHO DA SUBESTAÇÃO GOIÂNIA LESTE")
linhas_relatorio.append("=" * 115)
linhas_relatorio.append(f"  * Potência Ativa Máxima de Pico (SE): {p_max_kw:,.2f} kW ({p_max_kw/1000:.2f} MW) registrada às {p_max_hora}")
linhas_relatorio.append(f"  * Potência Ativa no Fim do Dia (24h): {p_final_kw:,.2f} kW ({p_final_kw/1000:.2f} MW)")
linhas_relatorio.append(f"  * Energia Total Fornecida no Dia:     {energia_total_se_mwh:,.2f} MWh/dia")
linhas_relatorio.append(f"  * Estado de Convergência do Fluxo:    {'100% CONVERGIDO (96/96 Passos)' if convergiu_todas else f'DIVERGÊNCIA DETECTADA ({len(passos_divergentes)} passos)'}")
linhas_relatorio.append("=" * 115)

# Tabela dos Transformadores AT
linhas_relatorio.append("\n" + "-" * 115)
linhas_relatorio.append("TABELA 1: CARREGAMENTO E TENSÃO DOS TRANSFORMADORES DA SUBESTAÇÃO (AT/MT - 230 / 13.8 kV)")
linhas_relatorio.append("-" * 115)
header_tr = f"{'Transformador':<15} | {'Barra MT':<8} | {'N° CTMTs':<8} | {'Cap. (MVA)':<10} | {'P Pico (MW)':<11} | {'S Pico (MVA)':<12} | {'Carreg. (%)':<12} | {'FP Pico':<8} | {'Faixa V (PU)':<13} | {'Status':<12}"
linhas_relatorio.append(header_tr)
linhas_relatorio.append("-" * 115)

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
        'Transformador': tr,
        'Identificador': tr_short,
        'Barra_MT': sec_bus,
        'Num_Alimentadores': n_ctmt,
        'Capacidade_MVA': cap_mva,
        'P_Pico_MW': round(p_pico_mw, 3),
        'S_Pico_MVA': round(s_pico_mva, 3),
        'Carregamento_Pct': round(carreg_pct, 2),
        'FP_Pico': round(fp_pico, 3),
        'Hora_Pico': info['hora_pico'],
        'V_Min_PU': round(info['v_min_pu'], 4),
        'V_Max_PU': round(info['v_max_pu'], 4),
        'Energia_MWh_Dia': round(info['energia_kwh'] / 1000.0, 2),
        'Status': status
    })
linhas_relatorio.append("-" * 115)

# Tabela dos Alimentadores MT (CTMTs)
linhas_relatorio.append("\n" + "-" * 135)
linhas_relatorio.append("TABELA 2: CARREGAMENTO E TENSÃO DOS ALIMENTADORES DE MÉDIA TENSÃO (27 CTMTs - 13.8 kV)")
linhas_relatorio.append("-" * 135)
header_ctmt = f"{'Alimentador (Nome)':<20} | {'Código ID':<10} | {'Trafo SE':<9} | {'P Pico (kW)':<12} | {'S Pico (kVA)':<13} | {'% Trafo':<8} | {'FP Pico':<8} | {'Hora Pico':<10} | {'Faixa V (PU)':<14} | {'Energia (MWh)':<13}"
linhas_relatorio.append(header_ctmt)
linhas_relatorio.append("-" * 135)

tabela_ctmt_dados = []
ctmt_ordenados = sorted(
    dict_ctmt_info.keys(),
    key=lambda c: (dict_ctmt_info[c]['trafo'], -dados_ctmt[c]['s_max_kva'])
)

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

# Exportar tabelas estruturadas em CSV na pasta logs_TCC/relatorios/
df_rel_trafos = pd.DataFrame(tabela_tr_dados)
arquivo_csv_trafos = caminho_sem_sobrescrever(pasta_log_relatorios, "Relatorio_Carregamento_Trafos_AT", "csv")
df_rel_trafos.to_csv(arquivo_csv_trafos, index=False, sep=';', encoding='utf-8')

df_rel_ctmt = pd.DataFrame(tabela_ctmt_dados)
arquivo_csv_ctmt = caminho_sem_sobrescrever(pasta_log_relatorios, "Relatorio_Carregamento_Alimentadores_CTMT", "csv")
df_rel_ctmt.to_csv(arquivo_csv_ctmt, index=False, sep=';', encoding='utf-8')
print(f"[ARQUIVO] Planilhas executivas salvas em:\n  -> '{arquivo_csv_trafos}'\n  -> '{arquivo_csv_ctmt}'")

# Exportar metadados do cenário executado em modelo_opendss/
meta_cenario = {
    "data_execucao": time.strftime("%Y-%m-%d %H:%M:%S"),
    "fator_demanda": FATOR_DEMANDA,
    "fator_demanda_str": FD_PCT_STR,
    "geracao_distribuida": {
        "habilitada": HABILITAR_GD,
        "fator_gd": FATOR_GD,
        "mes_solar": MES_SOLAR,
        "tipo_curva": TIPO_CURVA_GD
    },
    "potencia_max_kw": p_max_kw,
    "hora_pico": p_max_hora,
    "energia_total_dia_mwh": energia_total_se_mwh,
    "convergencia_100_pct": convergiu_todas,
    "total_passos_divergentes": len(passos_divergentes)
}
with open(os.path.join(pasta_modelo, "metadados_cenario.json"), "w", encoding="utf-8") as f_meta:
    json.dump(meta_cenario, f_meta, indent=4, ensure_ascii=False)

# ------------------------------------------------------------------------------
# 7. GRÁFICO COMPARATIVO DOS TRANSFORMADORES DA SUBESTAÇÃO (AT/MT)
# ------------------------------------------------------------------------------
try:
    plt.figure(figsize=(12, 6))
    tempo_horas_tr = [(step * 0.25) for step in range(1, 97)]
    cores_tr = {'GOL-S-TRF-TR1': '#e74c3c', 'GOL-S-TRF-TR2': '#3498db', 'GOL-S-TRF-TR3': '#2ecc71', 'GOL-S-TRF-TR4': '#9b59b6'}

    for tr in trafos_subestacao:
        tr_short = tr.replace("GOL-S-TRF-", "")
        curva_mw = [p / 1000.0 for p in perfil_p_trafos[tr]]
        p_max_tr_mw = dados_trafos_at[tr]['p_max_kw'] / 1000.0
        plt.plot(tempo_horas_tr, curva_mw, label=f"{tr_short} (Pico: {p_max_tr_mw:.1f} MW)",
                 color=cores_tr.get(tr, '#333333'), linewidth=2)

    plt.axhline(y=50.0, color='#e67e22', linestyle='--', linewidth=1.5, label='Capacidade Nominal (50 MVA)')
    plt.title(f"Carregamento Diário dos Transformadores (AT/MT)\n{SUBTITULO_PARAMETROS}", fontsize=12, fontweight='bold')
    plt.xlabel("Hora do Dia (h)", fontsize=11)
    plt.ylabel("Potência Ativa (MW)", fontsize=11)
    plt.xticks(range(1, 25))
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='upper left', fontsize=10)
    plt.tight_layout()

    output_grafico_trafos = caminho_sem_sobrescrever(pasta_graf_subestacao, "Curva_Carregamento_Trafos_AT_24h", "svg")
    plt.savefig(output_grafico_trafos, format='svg')
    plt.close()
    print(f"[GRÁFICO] Curva comparativa de carregamento dos transformadores salva em:\n  -> '{output_grafico_trafos}'")
except Exception as e_plot:
    print(f"[AVISO] Não foi possível salvar gráfico comparativo de trafos: {e_plot}")

# ------------------------------------------------------------------------------
# 7B. GRÁFICO EXCLUSIVO DE TENSÃO DOS TRANSFORMADORES DA SUBESTAÇÃO (AT/MT)
# ------------------------------------------------------------------------------
try:
    plt.figure(figsize=(12, 6))
    for tr in trafos_subestacao:
        tr_short = tr.replace("GOL-S-TRF-", "")
        curva_v = perfil_v_trafos[tr]
        v_min_tr = dados_trafos_at[tr]['v_min_pu']
        v_max_tr = dados_trafos_at[tr]['v_max_pu']
        plt.plot(tempo_horas_tr, curva_v, label=f"{tr_short} (Mín: {v_min_tr:.3f} | Máx: {v_max_tr:.3f} PU)",
                 color=cores_tr.get(tr, '#333333'), linewidth=2)

    # Faixas de conformidade PRODIST (Média Tensão: 0.93 a 1.05 PU)
    plt.axhline(y=1.05, color='#e74c3c', linestyle='--', linewidth=1.3, label='Limite Superior Adequado (1.05 PU)')
    plt.axhline(y=1.00, color='#7f8c8d', linestyle=':', linewidth=1.0, label='Tensão Nominal Base (1.00 PU)')
    plt.axhline(y=0.93, color='#e74c3c', linestyle='--', linewidth=1.3, label='Limite Inferior Adequado (0.93 PU)')

    # Destaque para a janela de atuação do Tap configurada
    h_inicio_tap = PASSO_INICIO_PICO * 0.25
    h_fim_tap = (PASSO_FIM_PICO * 0.25) if RETORNAR_TAP_NORMAL else 24.0
    label_tap = f'Tap Elevado ({TAP_PICO:.3f} PU) das {int(h_inicio_tap):02d}h às {int(h_fim_tap):02d}h'
    plt.axvspan(h_inicio_tap, h_fim_tap, color='#f39c12', alpha=0.12, label=label_tap)

    plt.title(f"Tensão Secundária nos Transformadores (13,8 kV)\n{SUBTITULO_PARAMETROS}", fontsize=12, fontweight='bold')
    plt.xlabel("Hora do Dia (h)", fontsize=11)
    plt.ylabel("Tensão no Barramento Secundário (PU)", fontsize=11)
    plt.xticks(range(1, 25))
    plt.ylim(0.91, 1.07)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='lower left', fontsize=9, framealpha=0.9)
    plt.tight_layout()

    output_grafico_v_trafos = caminho_sem_sobrescrever(pasta_graf_subestacao, "Curva_Tensao_Trafos_AT_24h", "svg")
    plt.savefig(output_grafico_v_trafos, format='svg')
    plt.close()
    print(f"[GRÁFICO] Curva exclusiva de tensão dos transformadores salva em:\n  -> '{output_grafico_v_trafos}'")
except Exception as e_plot_v:
    print(f"[AVISO] Não foi possível salvar gráfico de tensão dos transformadores: {e_plot_v}")

# ------------------------------------------------------------------------------
# 8. AUDITORIA NÓ A NÓ OTIMIZADA E CHECAGEM DE CONECTIVIDADE EM MEMÓRIA
# ------------------------------------------------------------------------------
print("\n[AUDITORIA] Analisando perfil de tensão detalhado em todos os nós da rede...")
t_inicio_audit = time.time()
bnames = dss.Circuit.AllBusNames()

# OTIMIZAÇÃO: Coleta em tuplas estruturadas reduz em mais de 90% a sobrecarga de memória do Python
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
                v_esperada = 230000.0 / (3.0**0.5)
            elif v_real > 1000.0:
                nivel_fisico = "MT (13.8 kV)"
                v_esperada = 13800.0 / (3.0**0.5)
            else:
                nivel_fisico = "BT (380/220 V)"
                v_esperada = 220.0

            pu_real = v_real / v_esperada
            pu_dss = (v_real / v_base_dss_v) if v_base_dss_v > 0 else 0.0

            if (v_real > 1000.0 and v_base_dss_v < 1000.0) or (v_real < 1000.0 and v_base_dss_v > 1000.0):
                categoria = "Inconsistência de Base OpenDSS (Falso PU)"
            elif pu_real < LIMITE_SUBTENSAO_PU:
                categoria = f"Subtensão (< {LIMITE_SUBTENSAO_PU:.2f} PU - Precária/Fora do Padrão)"
            elif pu_real > LIMITE_SOBRETENSAO_PU:
                categoria = f"Sobretensão (> {LIMITE_SOBRETENSAO_PU:.2f} PU - Precária/Fora do Padrão)"
            else:
                categoria = f"Tensão Adequada ({LIMITE_SUBTENSAO_PU:.2f} a {LIMITE_SOBRETENSAO_PU:.2f} PU)"

        registros_auditoria.append((
            b, no, nivel_fisico, round(v_real, 2), round(v_base_dss_v, 2),
            round(v_esperada, 2), round(pu_dss, 4), round(pu_real, 4), categoria
        ))

colunas_auditoria = [
    'Barra', 'Fase', 'Nivel_Fisico', 'Tensao_Real_V', 'Base_OpenDSS_V',
    'Base_Esperada_V', 'PU_OpenDSS', 'PU_Real', 'Classificacao'
]
df_auditoria = pd.DataFrame(registros_auditoria, columns=colunas_auditoria)

# Salvar relatório detalhado em CSV em logs_TCC/relatorios/
arquivo_auditoria = caminho_sem_sobrescrever(pasta_log_relatorios, "Relatorio_Tensoes_Detalhadas", "csv")
df_auditoria.to_csv(arquivo_auditoria, index=False, sep=';', encoding='utf-8')
print(f"[ARQUIVO] Relatório detalhado de todas as barras e nós salvo em:\n  -> '{arquivo_auditoria}'")

# Estatísticas dos nós ativos
nos_ativos = df_auditoria[df_auditoria['Tensao_Real_V'] >= 10.0]
nos_subtensao = df_auditoria[df_auditoria['Classificacao'].str.startswith("Subtensão")]
nos_sobretensao = df_auditoria[df_auditoria['Classificacao'].str.startswith("Sobretensão")]
nos_erro_base = df_auditoria[df_auditoria['Classificacao'] == "Inconsistência de Base OpenDSS (Falso PU)"]
nos_normais = df_auditoria[df_auditoria['Classificacao'].str.startswith("Tensão Adequada")]
nos_abertos = df_auditoria[df_auditoria['Classificacao'] == "Fase Aberta / Desenergizada (<10 V)"]

print("\n" + "=" * 65)
print("RESUMO EXECUTIVO DO PERFIL DE TENSÃO:")
print(f"Total de nós elétricos avaliados: {len(df_auditoria):,}")
print(f"  [OK] Nós com Tensão Adequada ({LIMITE_SUBTENSAO_PU:.2f} - {LIMITE_SOBRETENSAO_PU:.2f} PU):  {len(nos_normais):>6} ({len(nos_normais)/len(df_auditoria)*100:.1f}%)")
print(f"  [--] Fases Abertas / Desenergizadas (<10 V):       {len(nos_abertos):>6} ({len(nos_abertos)/len(df_auditoria)*100:.1f}%)")
print(f"  [!!] Inconsistências de Base OpenDSS (Falso PU):   {len(nos_erro_base):>6} ({len(nos_erro_base)/len(df_auditoria)*100:.1f}%)")
print(f"  [ALERTA] Subtensões Precárias (< {LIMITE_SUBTENSAO_PU:.2f} PU):    {len(nos_subtensao):>6} ({len(nos_subtensao)/len(df_auditoria)*100:.1f}%)")
print(f"  [ALERTA] Sobretensões Precárias (> {LIMITE_SOBRETENSAO_PU:.2f} PU):  {len(nos_sobretensao):>6} ({len(nos_sobretensao)/len(df_auditoria)*100:.1f}%)")
print("-" * 65)

if not nos_ativos.empty:
    idx_min = nos_ativos['PU_Real'].idxmin()
    idx_max = nos_ativos['PU_Real'].idxmax()
    print(f"Tensão Mínima Real (Nós Ativos): {nos_ativos.loc[idx_min, 'PU_Real']:.4f} PU ({nos_ativos.loc[idx_min, 'Tensao_Real_V']:.1f} V na barra {nos_ativos.loc[idx_min, 'Barra']}.{nos_ativos.loc[idx_min, 'Fase']})")
    print(f"Tensão Máxima Real (Nós Ativos): {nos_ativos.loc[idx_max, 'PU_Real']:.4f} PU ({nos_ativos.loc[idx_max, 'Tensao_Real_V']:.1f} V na barra {nos_ativos.loc[idx_max, 'Barra']}.{nos_ativos.loc[idx_max, 'Fase']})")
print("=" * 65)

# OTIMIZAÇÃO DE CONECTIVIDADE FÍSICA:
# Em vez de ler o CSV '05_SSDBT_linhas_BT.csv' do disco e fazer 50.000 chamadas adicionais à API,
# extraímos os dados instantaneamente a partir do 'df_auditoria' que já está na memória!
# Considera todas as barras pertencentes à BT (Base_Esperada_V <= 500 V), incluindo as desenergizadas a jusante de chaves
barras_bt_auditadas = set(df_auditoria[df_auditoria['Base_Esperada_V'] <= 500.0]['Barra'])
barras_bt_energizadas = len(df_auditoria[
    (df_auditoria['Base_Esperada_V'] <= 500.0) &
    (df_auditoria['Tensao_Real_V'] > 50.0)
]['Barra'].unique())

# Conectividade dos trafos MT diretamente do OpenDSS (em memória)
trafos_mt = [t for t in dss.Transformers.AllNames() if t.startswith('untrmt_')]
barras_com_tensao_mt = set(df_auditoria[
    (df_auditoria['Nivel_Fisico'] == "MT (13.8 kV)") &
    (df_auditoria['Tensao_Real_V'] > 1000.0)
]['Barra'])

trafos_energizados = 0
for t in trafos_mt:
    dss.Transformers.Name(t)
    b_prim = dss.CktElement.BusNames()[0].split('.')[0]
    if b_prim in barras_com_tensao_mt:
        trafos_energizados += 1

print("\n" + "=" * 65)
print("RESUMO DE CONECTIVIDADE FÍSICA (EXTRAÇÃO EM MEMÓRIA):")
print(f"Transformadores MT energizados: {trafos_energizados} de {len(trafos_mt)} ({trafos_energizados/len(trafos_mt)*100:.1f}%)")
print(f"Barras de BT energizadas (~220V): {barras_bt_energizadas} de {len(barras_bt_auditadas)} ({barras_bt_energizadas/max(1, len(barras_bt_auditadas))*100:.1f}%)")
print("=" * 65)

t_fim_audit = time.time()
print(f"[TEMPO] Auditoria completa e conectividade física: {t_fim_audit - t_inicio_audit:.2f} s")

# ------------------------------------------------------------------------------
# 9. CURVA DE CARGA DA SUBESTAÇÃO (DUCK CURVE) VIA MONITOR NATIVO
# ------------------------------------------------------------------------------
dss.Monitors.Name("mon_subestacao")
ch_p1 = dss.Monitors.Channel(1)
ch_p2 = dss.Monitors.Channel(3)
ch_p3 = dss.Monitors.Channel(5)

if len(ch_p1) > 0:
    potencia_total_kw = [(p1 + p2 + p3) for p1, p2, p3 in zip(ch_p1, ch_p2, ch_p3)]
    if sum(potencia_total_kw) < 0:
        potencia_total_kw = [-p for p in potencia_total_kw]

    tempo_horas = [(step_i * 0.25) for step_i in range(1, len(potencia_total_kw) + 1)]

    plt.figure(figsize=(10, 6))
    plt.plot(tempo_horas, potencia_total_kw, marker='o', markersize=4, color='#ff7f0e', linewidth=2)
    plt.title(f"Demanda Total da Subestação (24h)\n{SUBTITULO_PARAMETROS}", fontsize=12, fontweight='bold')
    plt.xlabel("Hora do Dia (h)", fontsize=11)
    plt.ylabel("Potência Ativa (kW)", fontsize=11)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.xticks(range(1, 25))
    plt.tight_layout()

    output_svg = caminho_sem_sobrescrever(pasta_graf_subestacao, "Curva_Carga_Base", "svg")
    plt.savefig(output_svg, format='svg')
    plt.close()
    print(f"\n[GRÁFICO] Curva de carga salva em: '{output_svg}'.")

# ------------------------------------------------------------------------------
# 10. MAPA GEOGRÁFICO DA REDE COM RENDERIZAÇÃO VETORIAL EM LOTE (LineCollection)
# ------------------------------------------------------------------------------
# OTIMIZAÇÃO CRÍTICA: Em vez de ler múltiplos CSVs e chamar ax.plot() 50.000 vezes,
# o mapa lê as coordenadas de 'buscoords.dss' e desenha os trechos via 'LineCollection'.
# O tempo de geração cai de ~2 minutos para menos de 1 segundo!
print("\n[MAPA] Gerando mapa geográfico da rede via LineCollection (alto desempenho)...")
t_inicio_mapa = time.time()

try:
    # 1. Carregar coordenadas de buscoords.dss
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

    # 2. Extrair segmentos de linhas MT a partir de 'linhas_mt.dss'
    segs_mt = []
    if os.path.exists(arquivo_linhas_mt):
        with open(arquivo_linhas_mt, 'r') as f:
            for line in f:
                if line.startswith('new line.'):
                    parts = line.split()
                    b1 = None
                    b2 = None
                    for p in parts:
                        if p.startswith('bus1='):
                            b1 = p.split('=')[1].split('.')[0].upper()
                        elif p.startswith('bus2='):
                            b2 = p.split('=')[1].split('.')[0].upper()
                    if b1 and b2 and b1 in coords_map and b2 in coords_map:
                        segs_mt.append([coords_map[b1], coords_map[b2]])

    # 3. Extrair segmentos de linhas BT a partir de 'linhas_bt.dss'
    segs_bt = []
    if os.path.exists(arquivo_linhas_bt):
        with open(arquivo_linhas_bt, 'r') as f:
            for line in f:
                if line.startswith('new line.'):
                    parts = line.split()
                    b1 = None
                    b2 = None
                    for p in parts:
                        if p.startswith('bus1='):
                            b1 = p.split('=')[1].split('.')[0].upper()
                        elif p.startswith('bus2='):
                            b2 = p.split('=')[1].split('.')[0].upper()
                    if b1 and b2 and b1 in coords_map and b2 in coords_map:
                        segs_bt.append([coords_map[b1], coords_map[b2]])

    # 4. Mapear transformadores MT com divergência e sobrecarga (direto da memória)
    trafos_divergiram = set()
    mapa_pac_tr = {}
    lista_trafos_coords = []

    for t_nome in trafos_mt_nomes:
        dss.Transformers.Name(t_nome)
        buses = dss.CktElement.BusNames()
        p1 = buses[0].split('.')[0].upper()
        p2 = buses[1].split('.')[0].upper() if len(buses) > 1 else p1
        cod_id = t_nome.replace('untrmt_', '')

        mapa_pac_tr[p1] = cod_id
        mapa_pac_tr[p2] = cod_id
        mapa_pac_tr[p1 + 'B'] = cod_id
        mapa_pac_tr[p2 + 'B'] = cod_id

        if p1 in coords_map:
            lista_trafos_coords.append((cod_id, coords_map[p1]))

    for b in barras_colapsadas_dia:
        b_limpa = str(b).strip().upper()
        if b_limpa in mapa_pac_tr:
            trafos_divergiram.add(mapa_pac_tr[b_limpa])
        elif b_limpa.endswith('B') and b_limpa[:-1] in mapa_pac_tr:
            trafos_divergiram.add(mapa_pac_tr[b_limpa[:-1]])

    print(f"  Transformadores com colapso/divergência de tensão: {len(trafos_divergiram)} de {len(trafos_mt_nomes)}")
    print(f"  Transformadores com sobrecarga ao longo do dia: {len(trafos_sobrecarregados)} de {len(trafos_mt_nomes)}")

    # 5. Criar a figura e plotar usando coleções em lote
    fig, ax = plt.subplots(figsize=(16, 12))
    ax.set_facecolor('#1a1a2e')
    fig.patch.set_facecolor('#0f0f23')

    # Adicionar todas as linhas de BT em um único lote (LineCollection)
    if segs_bt:
        lc_bt = LineCollection(segs_bt, colors='#2ecc71', linewidths=0.3, alpha=0.4)
        ax.add_collection(lc_bt)

    # Adicionar todas as linhas de MT em um único lote (LineCollection)
    if segs_mt:
        lc_mt = LineCollection(segs_mt, colors='#3498db', linewidths=0.8, alpha=0.7)
        ax.add_collection(lc_mt)

    # Categorização das coordenadas dos transformadores
    trafos_normais_lon = []
    trafos_normais_lat = []
    trafos_sobre_lon = []
    trafos_sobre_lat = []
    trafos_div_lon = []
    trafos_div_lat = []

    for cod_id, (lon, lat) in lista_trafos_coords:
        if cod_id in trafos_divergiram:
            trafos_div_lon.append(lon)
            trafos_div_lat.append(lat)
        elif cod_id in trafos_sobrecarregados:
            trafos_sobre_lon.append(lon)
            trafos_sobre_lat.append(lat)
        else:
            trafos_normais_lon.append(lon)
            trafos_normais_lat.append(lat)

    # Plotar os pontos de transformadores
    if trafos_normais_lon:
        ax.scatter(trafos_normais_lon, trafos_normais_lat,
                   c='#2ecc71', s=5, alpha=0.4, zorder=4, edgecolors='none')

    if trafos_sobre_lon:
        ax.scatter(trafos_sobre_lon, trafos_sobre_lat,
                   c='#f39c12', s=22, alpha=0.85, zorder=6, edgecolors='white',
                   linewidths=0.5, marker='^')

    if trafos_div_lon:
        ax.scatter(trafos_div_lon, trafos_div_lat,
                   c='#ff2a2a', s=45, alpha=1.0, zorder=7, edgecolors='white',
                   linewidths=0.8, marker='X')

    # Legenda
    legenda_mt = mlines.Line2D([], [], color='#3498db', linewidth=2, label=f'Linhas MT ({len(segs_mt):,} trechos)')
    legenda_bt = mlines.Line2D([], [], color='#2ecc71', linewidth=1.5, label=f'Linhas BT ({len(segs_bt):,} trechos)')
    legenda_trafo_ok = mlines.Line2D([], [], color='#2ecc71', marker='o', linestyle='None',
                                      markersize=5, label=f'Trafo Normal ({len(trafos_normais_lon)})')
    legenda_trafo_sob = mlines.Line2D([], [], color='#f39c12', marker='^', linestyle='None',
                                       markersize=7, markeredgecolor='white', markeredgewidth=0.5,
                                       label=f'Trafo Sobrecarregado ({len(trafos_sobre_lon)})')
    legenda_trafo_div = mlines.Line2D([], [], color='#ff2a2a', marker='X', linestyle='None',
                                       markersize=8, markeredgecolor='white', markeredgewidth=0.8,
                                       label=f'Trafo com Divergência ({len(trafos_div_lon)})')

    ax.legend(handles=[legenda_mt, legenda_bt, legenda_trafo_ok, legenda_trafo_sob, legenda_trafo_div],
              loc='upper left', fontsize=9, facecolor='#16213e', edgecolor='#e2e8f0',
              labelcolor='white', framealpha=0.9)

    ax.set_title(f"Mapa Geográfico da Rede de Distribuição\n{SUBTITULO_PARAMETROS}",
                 color='white', fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Longitude", color='#a0aec0', fontsize=10)
    ax.set_ylabel("Latitude", color='#a0aec0', fontsize=10)
    ax.tick_params(colors='#a0aec0', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#2d3748')
    ax.autoscale_view()
    ax.set_aspect('equal')

    plt.tight_layout()
    output_mapa_png = caminho_sem_sobrescrever(pasta_graf_mapa_rede, "Mapa_Rede_Tensao", "png")
    plt.savefig(output_mapa_png, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    print(f"[GRÁFICO] Mapa de alta definição salvo em:\n  -> '{output_mapa_png}'.")
    plt.close('all')

    t_fim_mapa = time.time()
    print(f"[TEMPO] Mapa geográfico gerado em: {t_fim_mapa - t_inicio_mapa:.2f} s")

except Exception as e:
    print(f"[ERRO] Falha ao gerar mapa geográfico: {e}")
    import traceback
    traceback.print_exc()

# ------------------------------------------------------------------------------
# 11. PAINEL DE DIAGNÓSTICO E PERFILAMENTO DE TEMPO (DEBUGGING)
# ------------------------------------------------------------------------------
t_fim_global = time.time()
tempo_total = t_fim_global - t_inicio_global

print("\n" + "=" * 75)
print("PAINEL DE DEPURAÇÃO E DIAGNÓSTICO DE DESEMPENHO:")
print("=" * 75)
print(f"  * Fator de Demanda Aplicado:                {FD_PCT_STR} (LoadMult: {FATOR_DEMANDA:.4f})")
print(f"  * Fator de Escala da GD (Geração Solar):    {FATOR_GD:.2f}x ({'Ativa' if HABILITAR_GD else 'Desativada'})")
print(f"  * Pasta de Saída dos Arquivos:              {pasta_saida}")
print(f"  * Tempo de Carregamento dos Arquivos DSS:  {t_fim_carga - t_inicio_carga:>6.2f} s")
print(f"  * Tempo da Simulação de 24h (96 passos):    {t_fim_sim - t_inicio_sim:>6.2f} s")
print(f"  * Tempo da Auditoria Nó por Nó:             {t_fim_audit - t_inicio_audit:>6.2f} s")
if 't_fim_mapa' in locals():
    print(f"  * Tempo da Geração do Mapa Geográfico:      {t_fim_mapa - t_inicio_mapa:>6.2f} s")
min_tot = int(tempo_total // 60)
sec_tot = tempo_total % 60
str_tot = f"{tempo_total:>6.2f} s ({min_tot}m {sec_tot:.2f}s)" if min_tot > 0 else f"{tempo_total:>6.2f} s"
print(f"  * TEMPO TOTAL DE PROCESSAMENTO:             {str_tot}")
print("-" * 75)
print("PONTOS DE ATENÇÃO PARA DEPURAÇÃO ELÉTRICA:")
if passos_divergentes:
    print(f"  [!] Passos com divergência: {passos_divergentes} (consulte 'barras_divergencia.csv')")
else:
    print("  [OK] Todos os 96 passos convergiram com sucesso!")
print(f"  [!] Total de transformadores sobrecarregados (>125%): {len(trafos_sobrecarregados)}")
if not nos_subtensao.empty:
    piores_barras = nos_subtensao.sort_values(by='PU_Real').head(3)
    print(f"  [!] Top 3 Nós com Maior Queda de Tensão (Subtensão Precária < {LIMITE_SUBTENSAO_PU:.2f} PU):")
    for _, r in piores_barras.iterrows():
        print(f"      - Barra: {r['Barra']}.{r['Fase']} | Tensão: {r['PU_Real']:.4f} PU ({r['Tensao_Real_V']:.1f} V)")

if barras_colapsadas_dia:
    arquivo_barras_unicas = caminho_sem_sobrescrever(pasta_log_divergencia, "barras_divergentes_unicas", "txt")
    with open(arquivo_barras_unicas, "w", encoding="utf-8") as f_bu:
        for b in sorted(barras_colapsadas_dia):
            f_bu.write(f"{b}\n")
    print(f"\n[ARQUIVO] Lista de barras com colapso salva em:\n  -> '{arquivo_barras_unicas}'")

print("=" * 75 + "\n")
