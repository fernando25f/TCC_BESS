import os
import re
import pandas as pd
from typing import List, Tuple, Any
from src.converter.elements.base import BaseElementConverter
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

class GeoCoordinatesConverter(BaseElementConverter):
    """Extrai coordenadas geográficas de trechos de rede e gera o arquivo buscoords.dss."""

    def converter(self, repo: BDGDRepository, config: ConverterConfig):
        caminho_saida = os.path.join(config.pasta_saida, "buscoords.dss")
        coords_map = {}

        for df in [repo.ssdmt, repo.ssdbt]:
            if df.empty or 'geometria_wkt' not in df.columns:
                continue
            for row in df.itertuples():
                pac1 = str(getattr(row, 'PAC_1', '')).lstrip('R')
                pac2 = str(getattr(row, 'PAC_2', '')).lstrip('R')
                pts = self._parse_wkt_line(getattr(row, 'geometria_wkt', ''))
                if len(pts) >= 2:
                    if pac1 not in coords_map:
                        coords_map[pac1] = pts[0]
                    if pac2 not in coords_map:
                        coords_map[pac2] = pts[-1]

        with open(caminho_saida, "w", encoding="utf-8") as f:
            for pac, (lon, lat) in coords_map.items():
                f.write(f"{pac}, {lon}, {lat}\n")

    @staticmethod
    def _parse_wkt_line(wkt: Any) -> List[Tuple[str, str]]:
        if pd.isna(wkt):
            return []
        return re.findall(r'([-]?\d+\.\d+)\s+([-]?\d+\.\d+)', str(wkt))
