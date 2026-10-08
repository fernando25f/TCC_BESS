import os
import math
from src.converter.elements.base import BaseElementConverter, MAPA_FASES
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

class DistributionTransformerConverter(BaseElementConverter):
    """Gera transformadores MT/BT com sanitização de tensões e modelagem Split-Phase (Center-Tap)."""

    def converter(self, repo: BDGDRepository, config: ConverterConfig):
        caminho = os.path.join(config.pasta_saida, "transformador_MT.dss")

        with open(caminho, "w", encoding="utf-8") as f:
            for _, row in repo.untrmt.iterrows():
                nome = row['COD_ID']
                fas_p = row['FAS_CON_P']
                fas_s = row['FAS_CON_S']

                phases = MAPA_FASES[fas_p][1]
                conn1 = MAPA_FASES[fas_p][2]
                barra1 = str(row['PAC_1']) + MAPA_FASES[fas_p][0]
                pac2 = str(row['PAC_2'])
                barra2 = pac2 + MAPA_FASES[fas_s][0]

                r = repo.eqtrmt.loc[repo.eqtrmt['UNI_TR_MT'] == nome, 'R'].values[0]
                xhl = repo.eqtrmt.loc[repo.eqtrmt['UNI_TR_MT'] == nome, 'XHL'].values[0]
                kv1 = repo.dict_ten[repo.eqtrmt.loc[repo.eqtrmt['UNI_TR_MT'] == nome, 'TEN_PRI'].values[0]]
                kv2 = repo.dict_ten[repo.eqtrmt.loc[repo.eqtrmt['UNI_TR_MT'] == nome, 'TEN_SEC'].values[0]]
                kva = row['POT_NOM']

                # Sanitização e modelagem por número de fases
                if phases == 3:
                    if kv1 > 30.0:
                        kv1 = 13.8
                    elif kv1 < 10.0:
                        kv1 = round(kv1 * math.sqrt(3), 2)

                    if kv2 < 0.30:
                        kv2 = 0.38

                    f.write(f"new transformer.UNTRMT_{nome} phases={phases} windings=2 %r={r} xhl={xhl} kva={kva}\n")
                    f.write(f"~ wdg=1 bus={barra1} conn={conn1} kv={kv1}\n")
                    f.write(f"~ wdg=2 bus={barra2} conn=wye kv={kv2}\n\n")

                elif phases == 1:
                    if kv1 > 15.0:
                        kv1 = 7.96

                    # Modelagem Center-Tap Split-Phase (220/440V - 3 enrolamentos)
                    if kv2 > 0.40:
                        r_half = round(r / 2.0, 3)
                        xlt = round(xhl * 0.7, 2)
                        f.write(f"new transformer.UNTRMT_{nome} phases=1 windings=3 %r={r} xhl={xhl} xht={xhl} xlt={xlt} kva={kva}\n")
                        f.write(f"~ wdg=1 bus={barra1} conn=wye kv={kv1} kva={kva} %r={r_half}\n")
                        f.write(f"~ wdg=2 bus={pac2}.1.0 conn=wye kv=0.22 kva={kva} %r={r_half}\n")
                        f.write(f"~ wdg=3 bus={pac2}.0.2 conn=wye kv=0.22 kva={kva} %r={r_half}\n\n")
                    else:
                        f.write(f"new transformer.UNTRMT_{nome} phases=1 windings=2 %r={r} xhl={xhl} kva={kva}\n")
                        f.write(f"~ wdg=1 bus={barra1} conn=wye kv={kv1}\n")
                        f.write(f"~ wdg=2 bus={barra2} conn=wye kv={kv2}\n\n")
