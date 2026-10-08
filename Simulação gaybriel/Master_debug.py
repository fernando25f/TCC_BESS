import os
import glob
import re
import time
from collections import Counter, defaultdict
import pandas as pd

try:
    import networkx as nx
except ImportError:
    print("[ERRO] A biblioteca 'networkx' não está instalada. Instale com: pip install networkx")
    exit(1)


def limpar_barra(nome_com_fase):
    if not nome_com_fase:
        return None
    return nome_com_fase.split('.')[0]


def extrair_barras_dss(arquivo, e_trafo=False):
    conexoes = []
    if not os.path.exists(arquivo):
        return conexoes
    with open(arquivo, 'r') as f:
        texto = f.read()

    if e_trafo:
        padrao = r'new\s+transformer\.([^\s]+).*?(?:~|\s)wdg=1\s+bus=([^\s]+).*?(?:~|\s)wdg=2\s+bus=([^\s]+)'
        matches = re.finditer(padrao, texto, re.IGNORECASE | re.DOTALL)
        for m in matches:
            nome = 'Trafo_' + m.group(1)
            b1 = limpar_barra(m.group(2))
            b2 = limpar_barra(m.group(3))
            conexoes.append((b1, b2, nome))
        return conexoes
    else:
        padrao = r'new\s+line\.([^\s]+).*?bus1=([^\s]+)\s+bus2=([^\s]+)'
        matches = re.finditer(padrao, texto, re.IGNORECASE | re.DOTALL)
        for m in matches:
            nome = 'Linha_' + m.group(1)
            b1 = limpar_barra(m.group(2))
            b2 = limpar_barra(m.group(3))
            conexoes.append((b1, b2, nome))
        return conexoes


def principal():
    t_inicio = time.time()
    diretorio_atual = os.path.dirname(os.path.abspath(__file__))
    pasta_graficos = os.path.join(diretorio_atual, 'graficos')
    pasta_dss = os.path.join(diretorio_atual, 'modelo_opendss')

    arquivo_barras = os.path.join(pasta_graficos, 'barras_divergentes_unicas.txt')
    arquivos_csv = glob.glob(os.path.join(pasta_graficos, 'barras_divergencia*.csv'))

    if arquivos_csv:
        ultimo_csv = max(arquivos_csv, key=os.path.getmtime)
        try:
            print(f"\n[0] Extraindo barras divergentes do CSV mais recente ({os.path.basename(ultimo_csv)})...")
            df_div = pd.read_csv(ultimo_csv)
            df_criticas = df_div[df_div['TENSAO_PU'] < 0.9]
            barras_unicas_extraidas = df_criticas['BARRA'].dropna().unique()
            pd.Series(barras_unicas_extraidas).to_csv(arquivo_barras, index=False, header=False)
            print(f"    -> {len(barras_unicas_extraidas)} barras únicas salvas em '{os.path.basename(arquivo_barras)}'.")
        except Exception as e:
            print(f"    [AVISO] Falha ao extrair barras do CSV ({e}). Usando arquivo existente.")

    if not os.path.exists(arquivo_barras):
        print(f"[ERRO] Arquivo {arquivo_barras} não encontrado.")
        return

    with open(arquivo_barras, 'r') as f:
        barras_unicas = [linha.strip() for linha in f.readlines() if linha.strip()]

    print(f"\n[1] Lendo lista de barras divergentes: {len(barras_unicas)} barras encontradas.")
    print("\n[2] Construindo topologia da rede a partir dos arquivos .dss...")

    G = nx.Graph()
    arquivos_linhas = ['linhas_mt.dss', 'linhas_bt.dss', 'disjuntores_mt.dss', 'seccionadoras_mt.dss']
    for arq in arquivos_linhas:
        caminho = os.path.join(pasta_dss, arq)
        conexoes = extrair_barras_dss(caminho, e_trafo=False)
        for b1, b2, nome in conexoes:
            G.add_edge(b1, b2, equipamento=nome)

    caminho_trafo = os.path.join(pasta_dss, 'transformador_MT.dss')
    conexoes_trafo = extrair_barras_dss(caminho_trafo, e_trafo=True)
    for b1, b2, nome in conexoes_trafo:
        G.add_edge(b1, b2, equipamento=nome)

    caminho_at = os.path.join(pasta_dss, 'transformador_AT.dss')
    conexoes_at = extrair_barras_dss(caminho_at, e_trafo=True)
    for b1, b2, nome in conexoes_at:
        G.add_edge(b1, b2, equipamento=nome)

    print(f"    -> Grafo criado com {G.number_of_nodes()} nós (barras) e {G.number_of_edges()} arestas (equipamentos).")

    barra_subestacao = '5001462'
    print("    -> Criando árvore de fluxo radial (BFS Tree) a partir da Subestação...")
    T_radial = nx.bfs_tree(G, source=barra_subestacao)

    print(f"\n[3] Identificando Caminhos e Barras Mães para {len(barras_unicas)} barras divergentes...")
    barras_validas = set()
    mapa_barras = {}
    for b in barras_unicas:
        b_limpa = b
        if b_limpa not in G and b_limpa.endswith('b'):
            b_limpa = b_limpa[:-1]
        if b_limpa in G:
            barras_validas.add(b_limpa)
            mapa_barras[b_limpa] = b

    caminhos_upstream = {}
    for b in barras_validas:
        try:
            caminhos_upstream[b] = nx.shortest_path(G, source=barra_subestacao, target=b)
        except nx.NetworkXNoPath:
            pass

    barras_maes = []
    for b in caminhos_upstream:
        caminho = caminhos_upstream[b]
        outras_no_caminho = set(caminho[:-1]).intersection(barras_validas)
        if not outras_no_caminho:
            barras_maes.append(b)

    print(f"    -> Concluído! Das {len(barras_validas)} barras analisadas, apenas {len(barras_maes)} são Barras Mães (raízes do colapso).")

    stats_tensao = {}
    arquivos_csv = glob.glob(os.path.join(pasta_graficos, 'barras_divergencia*.csv'))
    if arquivos_csv:
        ultimo_csv = max(arquivos_csv, key=os.path.getmtime)
        try:
            df_div = pd.read_csv(ultimo_csv)
            stats_raw = df_div.groupby('BARRA')['TENSAO_PU'].agg(['min', 'max']).to_dict('index')
            for b_cru, stats in stats_raw.items():
                b_cru_str = str(b_cru).strip()
                if b_cru_str.endswith('b') and b_cru_str not in G:
                    b_limpa = b_cru_str[:-1]
                else:
                    b_limpa = b_cru_str
                if b_limpa in barras_validas:
                    stats_tensao[b_limpa] = stats
        except Exception as e:
            print(f"[AVISO] Falha ao ler tensões extremas do CSV: {e}")

    pasta_bdgd = os.path.join(diretorio_atual, 'dados_goiania_leste')
    mapa_loc = {}
    arquivos_bdgd = [
        os.path.join(pasta_bdgd, '04_SSDMT_linhas_MT.csv'),
        os.path.join(pasta_bdgd, '05_SSDBT_linhas_BT.csv'),
        os.path.join(pasta_bdgd, '07a_UNTRMT_trafos_distribuicao.csv'),
        os.path.join(pasta_bdgd, '15_UNSEMT_chaves_seccionadoras.csv')
    ]
    print("\n[3.6] Cruzando dados com as planilhas da BDGD para descobrir localização (Urbano/Rural)...")
    try:
        for arq_bdgd in arquivos_bdgd:
            if os.path.exists(arq_bdgd):
                df_bdgd = pd.read_csv(arq_bdgd, usecols=['PAC_1', 'PAC_2', 'ARE_LOC'], dtype=str)
                for _, row in df_bdgd.iterrows():
                    b1 = str(row['PAC_1']).strip()
                    b2 = str(row['PAC_2']).strip()
                    loc = str(row['ARE_LOC']).strip().upper()
                    if loc not in ('UB', 'NU'):
                        continue
                    for b in (b1, b2):
                        if b in mapa_loc:
                            if loc == 'NU' and mapa_loc[b] == 'UB':
                                mapa_loc[b] = 'NU'
                        else:
                            mapa_loc[b] = loc
        print("    -> Mapeamento geográfico concluído com sucesso.")
    except Exception as e:
        print(f"[AVISO] Falha ao ler planilhas BDGD originais: {e}")

    mapa_ctmt_nomes = {}
    arq_ctmt = os.path.join(pasta_bdgd, '02_CTMT_alimentadores.csv')
    if os.path.exists(arq_ctmt):
        try:
            df_ctmt_bd = pd.read_csv(arq_ctmt, usecols=['COD_ID', 'NOME'], dtype=str)
            mapa_ctmt_nomes = dict(zip(df_ctmt_bd['COD_ID'].str.strip(), df_ctmt_bd['NOME'].str.strip()))
        except Exception as e:
            print(f"[AVISO] Falha ao ler 02_CTMT_alimentadores.csv: {e}")

    print("\n[3.7] Mapeando cargas conectadas (BT e MT) a partir dos arquivos .dss...")
    cargas_por_barra = defaultdict(lambda: {'bt': 0, 'mt': 0})

    def carregar_cargas_dss(nome_arq, tipo):
        caminho = os.path.join(pasta_dss, nome_arq)
        if not os.path.exists(caminho):
            return
        with open(caminho, 'r') as f:
            for l in f:
                if l.strip().lower().startswith('new load.'):
                    m = re.search(r'bus=([^\s.]+)', l, re.IGNORECASE)
                    if m:
                        cargas_por_barra[m.group(1).strip()][tipo] += 1

    carregar_cargas_dss('carga_bt.dss', 'bt')
    carregar_cargas_dss('carga_mt.dss', 'mt')
    print(f"    -> Mapeamento concluído: {len(cargas_por_barra)} nós com cargas identificados.")

    def gerar_linhas_relatorio(lista_barras, titulo_relatorio):
        linhas = []
        linhas.append('============================================================')
        linhas.append(titulo_relatorio)
        linhas.append(f"Total de Barras no Relatório: {len(lista_barras)}")
        linhas.append('============================================================\n')

        cont_loc = Counter()
        cont_nivel = Counter()
        cont_ctmt = Counter()

        for cont, b in enumerate(lista_barras, 1):
            linhas.append(f"--- ANÁLISE DA BARRA: {mapa_barras[b]} ({cont}/{len(lista_barras)}) ---")

            loc_sigla = mapa_loc.get(b)
            if not loc_sigla and b.endswith('b'):
                loc_sigla = mapa_loc.get(b[:-1])
            if not loc_sigla:
                loc_sigla = 'DESCONHECIDO'

            if loc_sigla == 'NU':
                loc_texto = 'ZONA RURAL (NU)'
            elif loc_sigla == 'UB':
                loc_texto = 'ZONA URBANA (UB)'
            else:
                loc_texto = 'NÃO ENCONTRADA na BDGD'

            linhas.append(f"Localização Geográfica: {loc_texto}")

            if b in stats_tensao:
                t_min = stats_tensao[b]['min']
                t_max = stats_tensao[b]['max']
                status = []
                if t_min < 0.9:
                    status.append(f"Queda de Tensão (Mín: {t_min:.4f} PU)")
                if t_max > 1.05:
                    status.append(f"Aumento Brusco (Máx: {t_max:.4f} PU)")
                if not status:
                    status.append(f"Oscilação Crítica (Mín {t_min:.4f} / Máx {t_max:.4f})")
                linhas.append(f"Tipo de Colapso: {' E '.join(status)}")

            if b not in caminhos_upstream:
                linhas.append("[ERRO] Caminho não isolado ou barra isolada da Subestação.\n")
                continue

            caminho_nos = caminhos_upstream[b]
            caminho_simplificado = []
            i = 0
            while i < len(caminho_nos) - 1:
                start_node = caminho_nos[i]
                current_node = caminho_nos[i + 1]
                merged_count = 1
                equip_names = [G.edges[(start_node, current_node)]['equipamento']]

                j = i + 1
                while j < len(caminho_nos) - 1:
                    node_j = caminho_nos[j]
                    next_node = caminho_nos[j + 1]
                    if G.degree(node_j) == 2:
                        equip_next = G.edges[(node_j, next_node)]['equipamento']
                        if equip_names[0].startswith('Linha_') and equip_next.startswith('Linha_'):
                            merged_count += 1
                            equip_names.append(equip_next)
                            j += 1
                            continue
                    break

                end_node = caminho_nos[j]
                if merged_count == 1:
                    nome_exibicao = equip_names[0]
                else:
                    nome_exibicao = f"{merged_count} Linhas Mescladas"

                caminho_simplificado.append((start_node, end_node, nome_exibicao, merged_count))
                i = j

            saltos_efetivos = len(caminho_simplificado)
            is_bt = False
            trafo_mt_bt = None
            distancia_trafo_bruta = 0
            distancia_trafo_efetiva = 0

            for n1, n2, equip, m_count in reversed(caminho_simplificado):
                if equip.startswith('Trafo_UNTRMT'):
                    is_bt = True
                    trafo_mt_bt = equip
                    break
                distancia_trafo_bruta += m_count
                distancia_trafo_efetiva += 1

            if is_bt:
                nivel_tensao = f"BAIXA TENSÃO (BT) -> Alimentada pelo {trafo_mt_bt} a {distancia_trafo_efetiva} saltos efetivos"
            else:
                nivel_tensao = 'MÉDIA TENSÃO (MT)'

            ctmt_cod = 'DESCONHECIDO'
            ctmt_nome = ''
            for n1, n2, equip, m_count in caminho_simplificado:
                if equip.startswith('Linha_DJ_'):
                    ctmt_cod = equip.replace('Linha_DJ_', '').strip()
                    ctmt_nome = mapa_ctmt_nomes.get(ctmt_cod, '')
                    break

            if ctmt_nome:
                ctmt_str = f"{ctmt_cod} ({ctmt_nome})"
            else:
                ctmt_str = f"{ctmt_cod}"

            linhas.append(f"Alimentador (CTMT): {ctmt_str}")
            linhas.append(f"Nível de Tensão: {nivel_tensao}")
            linhas.append(f"Distância da Subestação: {saltos_efetivos} saltos efetivos (Original bruto: {len(caminho_nos) - 1})")
            linhas.append("CAMINHO DE ALIMENTAÇÃO (UPSTREAM):")

            for i, (n1, n2, equip, count) in enumerate(caminho_simplificado):
                if i < 5 or i > len(caminho_simplificado) - 6:
                    linhas.append(f"  {i + 1:03d}. Barra {n1:15s} ---> (via {equip}) ---> Barra {n2}")
                elif i == 5:
                    linhas.append("       ... [trecho intermediário oculto] ...")

            try:
                if b in T_radial:
                    descendentes = list(nx.descendants(T_radial, b))
                else:
                    descendentes = []
            except Exception:
                descendentes = []

            subarvore = set(descendentes).union({b})
            cargas_diretas_bt = cargas_por_barra[b]['bt']
            cargas_diretas_mt = cargas_por_barra[b]['mt']
            cargas_sub_bt = sum(cargas_por_barra[no]['bt'] for no in subarvore)
            cargas_sub_mt = sum(cargas_por_barra[no]['mt'] for no in subarvore)
            cargas_total_impactadas = cargas_sub_bt + cargas_sub_mt

            linhas.append("IMPACTO DOWNSTREAM:")
            linhas.append(f"  - Barras dependentes a jusante: {len(descendentes)} barras")
            linhas.append(f"  - Cargas diretamente conectadas nesta barra: {cargas_diretas_bt + cargas_diretas_mt} ({cargas_diretas_bt} BT, {cargas_diretas_mt} MT)")
            linhas.append(f"  - TOTAL de cargas impactadas a jusante: {cargas_total_impactadas} unidades consumidoras ({cargas_sub_bt} BT, {cargas_sub_mt} MT)\n")

            cont_loc[loc_texto] += 1
            nivel_resumo = 'BAIXA TENSÃO (BT)' if 'BAIXA TENSÃO' in nivel_tensao else 'MÉDIA TENSÃO (MT)'
            cont_nivel[nivel_resumo] += 1
            cont_ctmt[ctmt_str] += 1

        total_b = len(lista_barras)
        linhas.append('============================================================')
        linhas.append(f"RESUMO ESTATÍSTICO CONSOLIDADO ({total_b} BARRAS)")
        linhas.append('============================================================')

        linhas.append('\n1. DIVERGÊNCIAS POR LOCALIZAÇÃO GEOGRÁFICA:')
        for loc, count in cont_loc.most_common():
            pct = (count / total_b * 100) if total_b > 0 else 0
            linhas.append(f"  - {loc:<25}: {count:3d} barras ({pct:5.1f}%)")

        linhas.append('\n2. DIVERGÊNCIAS POR NÍVEL DE TENSÃO:')
        for niv, count in cont_nivel.most_common():
            pct = (count / total_b * 100) if total_b > 0 else 0
            linhas.append(f"  - {niv:<25}: {count:3d} barras ({pct:5.1f}%)")

        linhas.append('\n3. DIVERGÊNCIAS POR ALIMENTADOR (CTMT):')
        for ct, count in cont_ctmt.most_common():
            pct = (count / total_b * 100) if total_b > 0 else 0
            linhas.append(f"  - {ct:<35}: {count:3d} barras ({pct:5.1f}%)")

        linhas.append('\n============================================================\n')
        return linhas

    print('\n[4] Gerando Relatórios...')
    relatorio_completo = gerar_linhas_relatorio(sorted(barras_validas), 'RELATÓRIO DE DEBUG DE TOPOLOGIA EM LOTE (COMPLETO)')
    relatorio_maes = gerar_linhas_relatorio(sorted(barras_maes), 'RELATÓRIO DE DEBUG DE TOPOLOGIA (BARRAS MÃES / CAUSAS RAIZ)')

    arquivo_completo = os.path.join(pasta_graficos, 'Relatorio_Divergencia_Completo.txt')
    with open(arquivo_completo, 'w', encoding='utf-8') as f:
        f.write('\n'.join(relatorio_completo))

    arquivo_maes = os.path.join(pasta_graficos, 'Relatorio_Divergencia_Maes.txt')
    with open(arquivo_maes, 'w', encoding='utf-8') as f:
        f.write('\n'.join(relatorio_maes))

    print(f"\n[SUCESSO] Relatório COMPLETO salvo em: {arquivo_completo}")
    print(f"[SUCESSO] Relatório de MÃES salvo em: {arquivo_maes}")

    tempo_total = time.time() - t_inicio
    minutos = int(tempo_total // 60)
    segundos = tempo_total % 60
    print("\n" + "=" * 70)
    if minutos > 0:
        print(f"[TEMPO DE EXECUÇÃO] Auditoria de topologia concluída em {minutos}m {segundos:.2f}s ({tempo_total:.2f} s)!")
    else:
        print(f"[TEMPO DE EXECUÇÃO] Auditoria de topologia concluída em {segundos:.2f} segundos!")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    principal()
