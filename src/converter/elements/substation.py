import os
import re
import json
import pandas as pd
from typing import Dict, Any
from src.converter.elements.base import BaseElementConverter
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

class SubstationConverter(BaseElementConverter):
    """Gera diretórios dos trafos AT, scripts trafo_TRx.dss e metadados estruturados."""

    def converter(self, repo: BDGDRepository, config: ConverterConfig) -> None:
        self._gerar_pastas_e_trafos_at(repo, config)
        self._gerar_metadados_json(repo, config)

    def _obter_nome_subestacao(self, repo: BDGDRepository, config: ConverterConfig) -> str:
        if config.nome_subestacao:
            return config.nome_subestacao

        if not repo.untrat.empty and 'SUB' in repo.untrat.columns:
            sub_id = str(repo.untrat['SUB'].dropna().iloc[0]).strip()
            if sub_id:
                return f"Subestacao_{sub_id}"

        nome_pasta = os.path.basename(os.path.normpath(config.pasta_entrada))
        return nome_pasta.replace("dados_", "Subestacao_").capitalize()

    @staticmethod
    def obter_identificador_trafo(tr_nome: str) -> str:
        """Extrai identificador curto do transformador (ex: 'GOL-S-TRF-TR1' -> 'TR1')."""
        return re.sub(r'^[A-Za-z0-9]+-S-TRF-', '', str(tr_nome).strip())

    def _gerar_pastas_e_trafos_at(self, repo: BDGDRepository, config: ConverterConfig) -> None:
        for _, row in repo.untrat.iterrows():
            nome_trafo = str(row['COD_ID']).strip()
            tr_short = self.obter_identificador_trafo(nome_trafo)
            pasta_tr = os.path.join(config.pasta_saida, tr_short)
            os.makedirs(pasta_tr, exist_ok=True)

            caminho_dss = os.path.join(pasta_tr, f"trafo_{tr_short}.dss")
            per_fer = repo.eqtrat.loc[repo.eqtrat['COD_ID'] == nome_trafo, 'PER_FER'].values[0]
            per_tot = repo.eqtrat.loc[repo.eqtrat['COD_ID'] == nome_trafo, 'PER_TOT'].values[0]
            kv1 = repo.dict_ten[repo.eqtrat.loc[repo.eqtrat['COD_ID'] == nome_trafo, 'TEN_PRI'].values[0]]
            kv2 = repo.dict_ten[repo.eqtrat.loc[repo.eqtrat['COD_ID'] == nome_trafo, 'TEN_SEC'].values[0]]
            xhl = 4.5
            kva = row['POT_NOM'] * 1000
            barra1 = row['BARR_1']
            barra2 = row['BARR_2']

            with open(caminho_dss, "w", encoding="utf-8") as f:
                f.write(f"! Transformador AT {nome_trafo} ({tr_short}) da Subestacao\n")
                f.write(f"new transformer.{nome_trafo} phases=3 xhl={xhl} windings=2 %loadloss={per_tot} %noloadloss={per_fer} kva={kva}\n")
                f.write(f"~ wdg=1 bus={barra1} conn=delta kv={kv1}\n")
                f.write(f"~ wdg=2 bus={barra2} conn=wye kv={kv2}\n")

    def _gerar_metadados_json(self, repo: BDGDRepository, config: ConverterConfig) -> None:
        caminho_json = os.path.join(config.pasta_saida, "alimentadores_info.json")
        dados_metadados: Dict[str, Any] = {
            "subestacao": self._obter_nome_subestacao(repo, config),
            "trafos_subestacao": {},
            "alimentadores": {}
        }

        for _, row in repo.untrat.iterrows():
            tr_nome = str(row['COD_ID']).strip()
            tr_short = self.obter_identificador_trafo(tr_nome)
            dados_metadados["trafos_subestacao"][tr_nome] = {
                "identificador": tr_short,
                "pasta": tr_short,
                "arquivo_dss": f"{tr_short}/trafo_{tr_short}.dss",
                "barra_primaria": str(row['BARR_1']).strip(),
                "barra_secundaria": str(row['BARR_2']).strip(),
                "pot_nom_mva": float(row['POT_NOM']) if 'POT_NOM' in row and pd.notna(row['POT_NOM']) else 50.0
            }

        for _, row in repo.ctmt.iterrows():
            cod_id = str(row['COD_ID']).strip()
            tr_pai = str(row['UNI_TR_AT']).strip()
            tr_short = self.obter_identificador_trafo(tr_pai)
            dados_metadados["alimentadores"][cod_id] = {
                "nome": str(row['NOME']).strip(),
                "trafo": tr_pai,
                "pasta_tr": tr_short,
                "arquivo_dss": f"{tr_short}/CTMT_{cod_id}.dss",
                "barra": str(row['BARR']).strip(),
                "pac_ini": str(row['PAC_INI']).strip()
            }

        with open(caminho_json, "w", encoding="utf-8") as fj:
            json.dump(dados_metadados, fj, indent=2, ensure_ascii=False)
