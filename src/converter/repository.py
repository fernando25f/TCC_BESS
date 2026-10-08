import os
import pandas as pd
from typing import Dict, Optional, Tuple, Any
from src.converter.config import ConverterConfig

class BDGDRepository:
    """Repositório de dados tabulares da BDGD e tabelas de dicionários."""

    def __init__(self, config: ConverterConfig):
        self.config = config
        self.dict_ten: Dict[Any, float] = {}
        self.dict_potrtv: Dict[Any, float] = {}
        self._carregar_dicionarios()
        self._carregar_dados()

    def _validar_arquivo(self, *nomes_possiveis: str) -> str:
        for nome in nomes_possiveis:
            caminho = os.path.join(self.config.pasta_entrada, nome)
            if os.path.exists(caminho):
                return caminho
        raise FileNotFoundError(
            f"Arquivo obrigatório da BDGD não encontrado (procurado por: {', '.join(nomes_possiveis)}) na pasta: {self.config.pasta_entrada}"
        )

    def _obter_caminho_opcional(self, *nomes_possiveis: str) -> Optional[str]:
        for nome in nomes_possiveis:
            caminho = os.path.join(self.config.pasta_entrada, nome)
            if os.path.exists(caminho):
                return caminho
        return None

    def _carregar_dicionarios(self):
        caminho_tten = os.path.join(self.config.pasta_dicionarios, "TTEN.csv")
        if not os.path.exists(caminho_tten):
            raise FileNotFoundError(f"Dicionário TTEN não encontrado: {caminho_tten}")
        df_tten = pd.read_csv(caminho_tten)
        self.dict_ten = dict(zip(df_tten['COD_ID'], df_tten['TEN'] / 1000.0))

        caminho_tpot = os.path.join(self.config.pasta_dicionarios, "TPOTRTV.csv")
        if not os.path.exists(caminho_tpot):
            raise FileNotFoundError(f"Dicionário TPOTRTV não encontrado: {caminho_tpot}")
        df_tpot = pd.read_csv(caminho_tpot)
        self.dict_potrtv = dict(zip(df_tpot['COD_ID'], df_tpot['POT']))

    def _carregar_dados(self):
        self.untrat = pd.read_csv(self._validar_arquivo("UNTRAT.csv", "03a_UNTRAT_trafos_subestacao.csv"))
        self.eqtrat = pd.read_csv(self._validar_arquivo("EQTRAT.csv", "03b_EQTRAT_dados_eletricos_trafos_sub.csv"))
        self.ctmt = pd.read_csv(self._validar_arquivo("CTMT.csv", "02_CTMT_alimentadores.csv"))
        self.unsemt = pd.read_csv(self._validar_arquivo("UNSEMT.csv", "15_UNSEMT_chaves_seccionadoras.csv"))
        self.untrmt = pd.read_csv(self._validar_arquivo("UNTRMT.csv", "07a_UNTRMT_trafos_distribuicao.csv"))
        self.eqtrmt = pd.read_csv(self._validar_arquivo("EQTRMT.csv", "07b_EQTRMT_dados_eletricos_trafos_dist.csv"))
        self.ssdmt = pd.read_csv(self._validar_arquivo("SSDMT.csv", "04_SSDMT_linhas_MT.csv"))
        self.ssdbt = pd.read_csv(self._validar_arquivo("SSDBT.csv", "05_SSDBT_linhas_BT.csv"))
        self.segcon = pd.read_csv(self._validar_arquivo("SEGCON.csv", "06_SEGCON_condutores.csv"))
        self.crvcrg = pd.read_csv(self._validar_arquivo("CRVCRG.csv", "10_CRVCRG_curvas_de_carga.csv"))
        self.ucbt = pd.read_csv(self._validar_arquivo("UCBT.csv", "08_UCBT_consumidores_BT.csv"))

        arq_ucmt = self._obter_caminho_opcional("UCMT.csv", "09_UCMT_consumidores_MT.csv")
        self.ucmt = pd.read_csv(arq_ucmt) if arq_ucmt else pd.DataFrame()

        arq_uncrmt = self._obter_caminho_opcional("UNCRMT.csv", "13_UNCRMT_capacitores_MT.csv")
        self.uncrmt = pd.read_csv(arq_uncrmt) if arq_uncrmt else pd.DataFrame()

        arq_ugbt = self._obter_caminho_opcional("UGBT.csv", "11_UGBT_geracao_distribuida_BT.csv")
        self.ugbt = pd.read_csv(arq_ugbt) if arq_ugbt else pd.DataFrame()

        arq_ugmt = self._obter_caminho_opcional("UGMT.csv", "12_UGMT_geracao_distribuida_MT.csv")
        self.ugmt = pd.read_csv(arq_ugmt) if arq_ugmt else pd.DataFrame()

        if self.config.somente_urbano:
            self._aplicar_filtro_urbano()

        if self.config.trafo_at_alvo is not None:
            self._aplicar_filtro_trafo_at(self.config.trafo_at_alvo)

    def _aplicar_filtro_urbano(self):
        if 'ARE_LOC' in self.ucbt.columns:
            self.ucbt = self.ucbt[self.ucbt['ARE_LOC'] == 'UB'].copy()
        if not self.ucmt.empty and 'ARE_LOC' in self.ucmt.columns:
            self.ucmt = self.ucmt[self.ucmt['ARE_LOC'] == 'UB'].copy()

    def _aplicar_filtro_trafo_at(self, trafo_alvo: str):
        self.untrat = self.untrat[self.untrat['COD_ID'].astype(str) == trafo_alvo].copy()
        self.eqtrat = self.eqtrat[self.eqtrat['COD_ID'].astype(str) == trafo_alvo].copy()

        ctmt_alvos = self.ctmt[self.ctmt['UNI_TR_AT'].astype(str) == trafo_alvo]
        ctmt_lista = ctmt_alvos['COD_ID'].astype(str).tolist()
        self.ctmt = ctmt_alvos.copy()

        self.ssdmt = self.ssdmt[self.ssdmt['CTMT'].astype(str).isin(ctmt_lista)].copy()
        self.unsemt = self.unsemt[self.unsemt['CTMT'].astype(str).isin(ctmt_lista)].copy()
        if not self.uncrmt.empty and 'CTMT' in self.uncrmt.columns:
            self.uncrmt = self.uncrmt[self.uncrmt['CTMT'].astype(str).isin(ctmt_lista)].copy()
        self.untrmt = self.untrmt[self.untrmt['CTMT'].astype(str).isin(ctmt_lista)].copy()
        self.ssdbt = self.ssdbt[self.ssdbt['CTMT'].astype(str).isin(ctmt_lista)].copy()
        self.ucbt = self.ucbt[self.ucbt['CTMT'].astype(str).isin(ctmt_lista)].copy()
        if not self.ucmt.empty:
            self.ucmt = self.ucmt[self.ucmt['CTMT'].astype(str).isin(ctmt_lista)].copy()
        if not self.ugbt.empty:
            self.ugbt = self.ugbt[self.ugbt['CTMT'].astype(str).isin(ctmt_lista)].copy()
        if not self.ugmt.empty:
            self.ugmt = self.ugmt[self.ugmt['CTMT'].astype(str).isin(ctmt_lista)].copy()
