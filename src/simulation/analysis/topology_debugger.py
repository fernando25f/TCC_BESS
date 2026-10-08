import os
import collections
from typing import Dict, List, Set, Tuple, Any, Optional
import pandas as pd
import opendssdirect as dss
from src.simulation.config import SimulationConfig
from src.simulation.core.circuit import CircuitManager
from src.simulation.core.engine import ScenarioResult

class TopologyDebugger:
    """
    Módulo de diagnóstico topológico para identificar elementos causadores de perturbações
    e rastrear o efeito cascata de quedas de tensão na rede de distribuição.
    """

    @classmethod
    def analisar_e_exportar(
        cls,
        res_padrao: ScenarioResult,
        circuit: CircuitManager,
        config: SimulationConfig
    ) -> Optional[pd.DataFrame]:
        """
        Executa a análise topológica de causa-raiz para as violações do caso padrão
        e salva o relatório de depuração.
        """
        if res_padrao.dados_tensao_barras is None:
            return None

        df_barras = res_padrao.dados_tensao_barras
        dict_vmin = dict(zip(df_barras['barra'].astype(str).str.lower(), df_barras['v_min_pu']))
        dict_hora = dict(zip(df_barras['barra'].astype(str).str.lower(), df_barras['hora_v_min']))
        dict_sub = dict(zip(df_barras['barra'].astype(str).str.lower(), df_barras['subtensao']))

        # 1. Constrói grafo de conectividade da rede física
        adj = cls._construir_grafo(config)

        # 2. Constrói a árvore radial a partir da Subestação (BFS)
        pai, elem_pai, filhos = cls._construir_arvore_radial(adj, circuit, config)

        # 3. Mapeia cargas conectadas a cada barra da rede
        cargas_por_barra = cls._mapear_cargas_por_barra()

        # 4. Identifica as raízes causadoras das subtensões
        df_raizes = cls._identificar_raizes_subtensao(
            df_barras=df_barras,
            dict_vmin=dict_vmin,
            dict_hora=dict_hora,
            dict_sub=dict_sub,
            pai=pai,
            elem_pai=elem_pai,
            filhos=filhos,
            cargas_por_barra=cargas_por_barra
        )

        if df_raizes.empty:
            return df_raizes

        # 5. Ordena por impacto (número de barras afetadas a jusante e queda local)
        df_raizes = df_raizes.sort_values(
            by=['barras_afetadas_jusante', 'queda_local_delta_v'],
            ascending=[False, False]
        )

        # 6. Exporta relatório CSV
        arq_saida = config.obter_caminho_saida(
            config.pasta_log_relatorios, "depuracao_origem_violacoes", "csv"
        )
        df_raizes.to_csv(arq_saida, index=False, sep=';', encoding='utf-8')

        total_violadas = df_barras['subtensao'].sum()
        total_raizes = len(df_raizes)
        media_cascata = (total_violadas / total_raizes) if total_raizes > 0 else 0

        print(f"  [OK] Relatório de depuração topológica salvo: {config.relpath(arq_saida)}")
        print(f"    Diagnóstico: {total_violadas} barras com subtensão originadas em apenas {total_raizes} elementos raiz.")
        print(f"    Efeito cascata médio: ~{media_cascata:.1f} barras afetadas por elemento causador.")

        # Top 3 maiores causadores no terminal
        top_impacto = df_raizes.head(3)
        for _, row in top_impacto.iterrows():
            print(f"      • {row['elemento_origem']} ({row['tipo_elemento']}) [Trafo: {row['trafo_montante']}]: causou {row['barras_afetadas_jusante']} barras violadas ({row['total_cargas_ramo']} cargas) | Pior no ramo: {row['pior_v_no_ramo']:.4f} pu)")

        return df_raizes

    @staticmethod
    def _construir_grafo(config: SimulationConfig) -> Dict[str, List[Tuple[str, str, str]]]:
        """Extrai a conectividade de todas as Linhas e Transformadores do OpenDSS."""
        adj = collections.defaultdict(list)

        # Mapeia linhas e seccionadoras
        for l_name in dss.Lines.AllNames():
            dss.Lines.Name(l_name)
            bus1 = dss.Lines.Bus1().split('.')[0].lower()
            bus2 = dss.Lines.Bus2().split('.')[0].lower()
            if bus1 != bus2:
                tipo = "SECCIONADORA" if l_name.lower().startswith("sc_") else "LINHA"
                adj[bus1].append((bus2, f"Line.{l_name}", tipo))
                adj[bus2].append((bus1, f"Line.{l_name}", tipo))

        # Mapeia transformadores AT e MT
        for t_name in dss.Transformers.AllNames():
            dss.Transformers.Name(t_name)
            buses = [b.split('.')[0].lower() for b in dss.CktElement.BusNames()]
            if len(buses) >= 2:
                bus1 = buses[0]
                tipo = "TRAFO_AT" if t_name.lower().startswith(config.sigla_subestacao.lower()) else "TRAFO_MT"
                for bus2 in buses[1:]:
                    if bus1 != bus2:
                        adj[bus1].append((bus2, f"Transformer.{t_name}", tipo))
                        adj[bus2].append((bus1, f"Transformer.{t_name}", tipo))

        return adj

    @staticmethod
    def _construir_arvore_radial(
        adj: Dict[str, List[Tuple[str, str, str]]],
        circuit: CircuitManager,
        config: SimulationConfig
    ) -> Tuple[Dict[str, Optional[str]], Dict[str, Tuple[str, str]], Dict[str, List[str]]]:
        """
        Executa busca em largura (BFS) a partir da Subestação para orientar a topologia montante -> jusante.
        """
        slack = config.barra_slack.split('.')[0].lower()
        pai: Dict[str, Optional[str]] = {slack: None}
        elem_pai: Dict[str, Tuple[str, str]] = {}
        filhos: Dict[str, List[str]] = collections.defaultdict(list)

        queue = collections.deque([slack])
        while queue:
            u = queue.popleft()
            for v, el_nome, el_tipo in adj.get(u, []):
                if v not in pai:
                    pai[v] = u
                    elem_pai[v] = (el_nome, el_tipo)
                    filhos[u].append(v)
                    queue.append(v)

        # Fallback de contingência para secundários da SE não conectados
        sec_buses = getattr(circuit, 'trafo_sec_bus', {}) or {}
        for sec_b in sec_buses.values():
            b_sec = sec_b.split('.')[0].lower()
            if b_sec not in pai:
                pai[b_sec] = None
                queue.append(b_sec)
                while queue:
                    u = queue.popleft()
                    for v, el_nome, el_tipo in adj.get(u, []):
                        if v not in pai:
                            pai[v] = u
                            elem_pai[v] = (el_nome, el_tipo)
                            filhos[u].append(v)
                            queue.append(v)

        return pai, elem_pai, filhos

    @staticmethod
    def _mapear_cargas_por_barra() -> Dict[str, int]:
        """Mapeia o total de unidades consumidoras/cargas conectadas a cada barra."""
        cargas_por_barra = collections.defaultdict(int)
        flag = dss.Loads.First()
        while flag > 0:
            buses = dss.CktElement.BusNames()
            if buses:
                bus = buses[0].split('.')[0].lower()
                cargas_por_barra[bus] += 1
            flag = dss.Loads.Next()
        return cargas_por_barra

    @staticmethod
    def _buscar_primeiro_trafo_montante(
        no_inicial: str,
        el_proprio_nome: str,
        el_proprio_tipo: str,
        pai: Dict[str, Optional[str]],
        elem_pai: Dict[str, Tuple[str, str]]
    ) -> Tuple[str, str]:
        """Rastreia montante até localizar o primeiro transformador (distribuição ou subestação)."""
        if el_proprio_tipo in ("TRAFO_MT", "TRAFO_AT"):
            return el_proprio_nome, el_proprio_tipo

        curr = no_inicial
        while curr is not None:
            el_info = elem_pai.get(curr)
            if el_info:
                nome, tipo = el_info
                if tipo in ("TRAFO_MT", "TRAFO_AT"):
                    return nome, tipo
            curr = pai.get(curr)

        return "NAO_ENCONTRADO", "N/A"

    @classmethod
    def _identificar_raizes_subtensao(
        cls,
        df_barras: pd.DataFrame,
        dict_vmin: Dict[str, float],
        dict_hora: Dict[str, str],
        dict_sub: Dict[str, bool],
        pai: Dict[str, Optional[str]],
        elem_pai: Dict[str, Tuple[str, str]],
        filhos: Dict[str, List[str]],
        cargas_por_barra: Dict[str, int]
    ) -> pd.DataFrame:
        """
        Identifica barras que violaram o limite de subtensão mas cujo nó montante (pai)
        estava dentro da conformidade, calculando a cascata gerada na subárvore.
        """
        raizes_violacao = []

        for _, row in df_barras.iterrows():
            if not row['subtensao']:
                continue

            b_nome = str(row['barra']).lower()
            v_min = row['v_min_pu']
            p_nome = pai.get(b_nome)

            if p_nome is None:
                continue

            v_pai = dict_vmin.get(p_nome, 1.0)

            # Barra raiz: o nó pai estava em conformidade (ou é fonte/slack com v >= 0.93)
            if v_pai >= 0.93:
                # Normaliza referência caso o nó montante apresente anomalia de base de tensão (> 2.0 pu)
                v_pai_ref = 1.0 if v_pai > 2.0 else v_pai
                delta_v = round(v_pai_ref - v_min, 4)
                el_nome, el_tipo = elem_pai.get(b_nome, ("DESCONHECIDO", "DESCONHECIDO"))

                tr_nome, tr_tipo = cls._buscar_primeiro_trafo_montante(
                    no_inicial=p_nome,
                    el_proprio_nome=el_nome,
                    el_proprio_tipo=el_tipo,
                    pai=pai,
                    elem_pai=elem_pai
                )

                tot_desc, viol_desc, tot_cargas, pior_desc = cls._analisar_subarvore(
                    raiz_no=b_nome,
                    filhos=filhos,
                    dict_vmin=dict_vmin,
                    dict_sub=dict_sub,
                    cargas_por_barra=cargas_por_barra
                )

                raizes_violacao.append({
                    'elemento_origem': el_nome,
                    'tipo_elemento': el_tipo,
                    'trafo_montante': tr_nome,
                    'tipo_trafo_montante': tr_tipo,
                    'barra_montante': p_nome,
                    'v_montante_pu': round(v_pai, 4),
                    'barra_raiz': b_nome,
                    'v_raiz_pu': v_min,
                    'queda_local_delta_v': delta_v,
                    'hora_violacao': row['hora_v_min'],
                    'barras_afetadas_jusante': viol_desc,
                    'total_barras_ramo': tot_desc,
                    'total_cargas_ramo': tot_cargas,
                    'pior_v_no_ramo': pior_desc
                })

        return pd.DataFrame(raizes_violacao)

    @staticmethod
    def _analisar_subarvore(
        raiz_no: str,
        filhos: Dict[str, List[str]],
        dict_vmin: Dict[str, float],
        dict_sub: Dict[str, bool],
        cargas_por_barra: Dict[str, int]
    ) -> Tuple[int, int, int, float]:
        """Percorre a subárvore a jusante computando quantidade de barras, cargas e o pior afundamento."""
        stack = [raiz_no]
        total = 0
        violadas = 0
        total_cargas = 0
        pior_v = dict_vmin.get(raiz_no, 1.0)

        while stack:
            curr = stack.pop()
            total += 1
            total_cargas += cargas_por_barra.get(curr, 0)
            v_curr = dict_vmin.get(curr, 1.0)
            if dict_sub.get(curr, False):
                violadas += 1
            if v_curr < pior_v:
                pior_v = v_curr
            stack.extend(filhos.get(curr, []))

        return total, violadas, total_cargas, round(pior_v, 4)
