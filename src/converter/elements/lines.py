import os
from src.converter.elements.base import BaseElementConverter, MAPA_FASES
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

class LineConverter(BaseElementConverter):
    """Gera linhas de MT/BT, chaves seccionadoras e bancos de capacitores."""

    def converter(self, repo: BDGDRepository, config: ConverterConfig):
        self._gerar_linhas_mt(repo, config)
        self._gerar_seccionadoras_mt(repo, config)
        self._gerar_capacitores_mt(repo, config)
        self._gerar_linhas_bt(repo, config)

    def _gerar_linhas_mt(self, repo: BDGDRepository, config: ConverterConfig):
        caminho = os.path.join(config.pasta_saida, "linhas_mt.dss")
        with open(caminho, "w", encoding="utf-8") as f:
            for _, row in repo.ssdmt.iterrows():
                nome = row['COD_ID']
                fas_info = MAPA_FASES.get(row['FAS_CON'], ('.1.2.3', 3, 'delta'))
                phases = fas_info[1]
                barra1 = str(row['PAC_1']) + fas_info[0]
                barra2 = str(row['PAC_2']) + fas_info[0]

                tip_cnd = row['TIP_CND']
                cond_match = repo.segcon.loc[repo.segcon['COD_ID'] == tip_cnd]
                r1 = cond_match['R1'].values[0] if not cond_match.empty else 0.5
                x1 = cond_match['X1'].values[0] if not cond_match.empty else 0.4
                corr_nom = cond_match['CNOM'].values[0] if not cond_match.empty else 200.0

                comp = max(0.001, round(row['COMP'] / 1000.0, 6))

                f.write(f"new line.{nome} phases={phases} bus1={barra1} bus2={barra2} r1={r1} x1={x1} length={comp} units=km normamps={corr_nom}\n")

    def _gerar_seccionadoras_mt(self, repo: BDGDRepository, config: ConverterConfig):
        caminho = os.path.join(config.pasta_saida, "seccionadoras_mt.dss")
        with open(caminho, "w", encoding="utf-8") as f:
            for _, row in repo.unsemt.iterrows():
                nome = row['COD_ID']
                fas_info = MAPA_FASES.get(row['FAS_CON'], ('.1.2.3', 3, 'delta'))
                phases = fas_info[1]
                barra1 = str(row['PAC_1']) + fas_info[0]
                barra2 = str(row['PAC_2']) + fas_info[0]
                f.write(f"new line.SC_{nome} phases={phases} bus1={barra1} bus2={barra2} switch=y r1=1e-4 x1=1e-4 length=0.001 units=km\n")
                if row.get('P_N_OPE') == 'A':
                    f.write(f"open line.SC_{nome} 1\n")

    def _gerar_capacitores_mt(self, repo: BDGDRepository, config: ConverterConfig):
        if repo.uncrmt.empty:
            return
        caminho = os.path.join(config.pasta_saida, "capacitores_mt.dss")
        with open(caminho, "w", encoding="utf-8") as f:
            for _, row in repo.uncrmt.iterrows():
                nome = row['COD_ID']
                fas_info = MAPA_FASES.get(row['FAS_CON'], ('.1.2.3', 3, 'wye'))
                barra1 = str(row['PAC_1']).lstrip('R') + fas_info[0]
                phases = fas_info[1]
                kv = 13.8
                kvar = repo.dict_potrtv.get(row['POT_NOM'], 0.0)
                f.write(f"new capacitor.{nome} phases={phases} bus1={barra1} conn=wye kv={kv} kvar={kvar}\n")

    def _gerar_linhas_bt(self, repo: BDGDRepository, config: ConverterConfig):
        caminho = os.path.join(config.pasta_saida, "linhas_bt.dss")
        with open(caminho, "w", encoding="utf-8") as f:
            for _, row in repo.ssdbt.iterrows():
                nome = row['COD_ID']
                fas_info = MAPA_FASES.get(row['FAS_CON'], ('.1.2.3', 3, 'delta'))
                phases = fas_info[1]
                barra1 = str(row['PAC_1']) + fas_info[0]
                barra2 = str(row['PAC_2']) + fas_info[0]

                tip_cnd = row['TIP_CND']
                cond_match = repo.segcon.loc[repo.segcon['COD_ID'] == tip_cnd]
                r1 = cond_match['R1'].values[0] if not cond_match.empty else 1.0
                x1 = cond_match['X1'].values[0] if not cond_match.empty else 0.4
                corr_nom = cond_match['CNOM'].values[0] if not cond_match.empty else 100.0

                r1 = min(5.0, r1)
                x1 = min(2.0, x1)
                comp = max(0.001, round(row['COMP'] / 1000.0, 6))

                f.write(f"new line.{nome} phases={phases} bus1={barra1} bus2={barra2} r1={r1} x1={x1} length={comp} units=km normamps={corr_nom}\n")
