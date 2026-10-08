import networkx as nx
import pandas as pd
from typing import Optional, Union, Set
from src.converter.repository import BDGDRepository

class TopologyService:
    """Serviço de análise e poda topológica em redes de distribuição com NetworkX."""

    @staticmethod
    def podar_jusante(repo: BDGDRepository, linha_corte: Optional[Union[int, str]], ctmt_alvo: Optional[Union[int, str]] = None):
        """
        Constrói o grafo elétrico do alimentador e elimina elementos a jusante
        do ponto de corte especificado (linha ou chave).
        """
        if linha_corte is None:
            return

        linha_corte_str = str(linha_corte).strip()

        # Autodetecção do alimentador caso não informado
        if ctmt_alvo is None:
            m_l = repo.ssdmt[repo.ssdmt['COD_ID'].astype(str) == linha_corte_str]
            if not m_l.empty:
                ctmt_alvo = m_l.iloc[0]['CTMT']
            else:
                m_s = repo.unsemt[repo.unsemt['COD_ID'].astype(str) == linha_corte_str]
                if not m_s.empty:
                    ctmt_alvo = m_s.iloc[0]['CTMT']

        if ctmt_alvo is None:
            print(f"  [AVISO PODA] Linha ou chave '{linha_corte_str}' não encontrada.")
            return

        ctmt_str = str(ctmt_alvo).strip()

        ctmt_match = repo.ctmt[repo.ctmt['COD_ID'].astype(str) == ctmt_str]
        if ctmt_match.empty:
            print(f"  [AVISO PODA] Alimentador {ctmt_str} não encontrado na tabela CTMT.")
            return
        pac_ini_str = str(ctmt_match.iloc[0]['PAC_INI']).strip()

        ssdmt_f = repo.ssdmt[repo.ssdmt['CTMT'].astype(str) == ctmt_str]
        unsemt_f = repo.unsemt[repo.unsemt['CTMT'].astype(str) == ctmt_str]
        untrmt_f = repo.untrmt[repo.untrmt['CTMT'].astype(str) == ctmt_str]
        ssdbt_f = repo.ssdbt[repo.ssdbt['CTMT'].astype(str) == ctmt_str]
        ucbt_f = repo.ucbt[repo.ucbt['CTMT'].astype(str) == ctmt_str]
        ucmt_f = repo.ucmt[repo.ucmt['CTMT'].astype(str) == ctmt_str] if not repo.ucmt.empty else pd.DataFrame()
        uncrmt_f = repo.uncrmt[repo.uncrmt['CTMT'].astype(str) == ctmt_str] if not repo.uncrmt.empty and 'CTMT' in repo.uncrmt.columns else pd.DataFrame()

        G = nx.Graph()
        aresta_corte = None

        for row in ssdmt_f.itertuples():
            cid_str = str(row.COD_ID).strip()
            p1, p2 = str(row.PAC_1).strip(), str(row.PAC_2).strip()
            if cid_str == linha_corte_str:
                aresta_corte = (p1, p2, 'Linha MT')
            else:
                G.add_edge(p1, p2, tipo='linha_mt', id=cid_str)

        for row in unsemt_f.itertuples():
            cid_str = str(row.COD_ID).strip()
            p1, p2 = str(row.PAC_1).strip(), str(row.PAC_2).strip()
            if cid_str == linha_corte_str or f"SC_{cid_str}" == linha_corte_str:
                aresta_corte = (p1, p2, 'Chave MT')
            else:
                G.add_edge(p1, p2, tipo='chave_mt', id=cid_str)

        for row in untrmt_f.itertuples():
            p1, p2 = str(row.PAC_1).strip(), str(row.PAC_2).strip()
            G.add_edge(p1, p2, tipo='trafo_dist', id=str(row.COD_ID).strip())

        for row in ssdbt_f.itertuples():
            p1, p2 = str(row.PAC_1).strip(), str(row.PAC_2).strip()
            G.add_edge(p1, p2, tipo='linha_bt', id=str(row.COD_ID).strip())

        if not aresta_corte:
            print(f"  [AVISO PODA] Linha ou chave '{linha_corte_str}' não encontrada no CTMT {ctmt_str}.")
            return

        p1_corte, p2_corte, _ = aresta_corte

        if pac_ini_str in G:
            nos_ativos = nx.node_connected_component(G, pac_ini_str)
        else:
            componentes = list(nx.connected_components(G))
            comp_com_p1 = [c for c in componentes if p1_corte in c]
            nos_ativos = comp_com_p1[0] if comp_com_p1 else (max(componentes, key=len) if componentes else set())

        linhas_mt_remover = set(ssdmt_f[
            ~ssdmt_f['PAC_1'].astype(str).isin(nos_ativos) |
            ~ssdmt_f['PAC_2'].astype(str).isin(nos_ativos) |
            (ssdmt_f['COD_ID'].astype(str) == linha_corte_str)
        ]['COD_ID'].astype(str))

        chaves_mt_remover = set(unsemt_f[
            ~unsemt_f['PAC_1'].astype(str).isin(nos_ativos) |
            ~unsemt_f['PAC_2'].astype(str).isin(nos_ativos) |
            (unsemt_f['COD_ID'].astype(str) == linha_corte_str) |
            (f"SC_" + unsemt_f['COD_ID'].astype(str) == linha_corte_str)
        ]['COD_ID'].astype(str))

        trafos_remover = set(untrmt_f[
            ~untrmt_f['PAC_1'].astype(str).isin(nos_ativos)
        ]['COD_ID'].astype(str))

        linhas_bt_remover = set(ssdbt_f[
            ~ssdbt_f['PAC_1'].astype(str).isin(nos_ativos) |
            ~ssdbt_f['PAC_2'].astype(str).isin(nos_ativos)
        ]['COD_ID'].astype(str))

        ucbt_remover = set(ucbt_f[
            ucbt_f['UNI_TR_MT'].astype(str).isin(trafos_remover)
        ]['COD_ID'].astype(str))

        ucmt_remover = set(ucmt_f[
            ~ucmt_f['PAC'].astype(str).isin(nos_ativos) &
            ~ucmt_f['PN_CON'].astype(str).isin(nos_ativos)
        ]['COD_ID'].astype(str)) if not ucmt_f.empty else set()

        uncrmt_remover = set(uncrmt_f[
            ~uncrmt_f['PAC_1'].astype(str).isin(nos_ativos)
        ]['COD_ID'].astype(str)) if not uncrmt_f.empty else set()

        # Atualização controlada no repositório
        repo.ssdmt = repo.ssdmt[~repo.ssdmt['COD_ID'].astype(str).isin(linhas_mt_remover)].copy()
        repo.unsemt = repo.unsemt[~repo.unsemt['COD_ID'].astype(str).isin(chaves_mt_remover)].copy()
        repo.untrmt = repo.untrmt[~repo.untrmt['COD_ID'].astype(str).isin(trafos_remover)].copy()
        repo.ssdbt = repo.ssdbt[~repo.ssdbt['COD_ID'].astype(str).isin(linhas_bt_remover)].copy()
        repo.ucbt = repo.ucbt[~repo.ucbt['COD_ID'].astype(str).isin(ucbt_remover)].copy()
        if not repo.ucmt.empty and ucmt_remover:
            repo.ucmt = repo.ucmt[~repo.ucmt['COD_ID'].astype(str).isin(ucmt_remover)].copy()
        if not repo.uncrmt.empty and uncrmt_remover:
            repo.uncrmt = repo.uncrmt[~repo.uncrmt['COD_ID'].astype(str).isin(uncrmt_remover)].copy()
