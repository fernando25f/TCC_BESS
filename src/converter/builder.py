import time
from typing import List
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository
from src.converter.topology import TopologyService
from src.converter.elements import (
    BaseElementConverter,
    CurvesConverter,
    SubstationConverter,
    FeederConverter
)

class DssModelBuilder:
    """Orquestrador do pipeline de geração hierárquica do modelo OpenDSS."""

    def __init__(self, config: ConverterConfig):
        self.config = config
        self.conversores: List[BaseElementConverter] = [
            CurvesConverter(),
            SubstationConverter(),
            FeederConverter()
        ]

    def construir_modelo(self) -> None:
        t0 = time.time()
        print(f"[CONVERSOR] Iniciando conversão hierárquica BDGD -> OpenDSS...")
        print(f"  Entrada: {self.config.pasta_entrada}")
        print(f"  Destino: {self.config.pasta_saida}")

        repo = BDGDRepository(self.config)

        if self.config.linha_corte is not None:
            TopologyService.podar_jusante(repo, self.config.linha_corte, self.config.ctmt_corte)

        for conversor in self.conversores:
            conversor.converter(repo, self.config)

        duracao = time.time() - t0
        print(f"[OK] Modelo OpenDSS hierárquico gerado com sucesso em {duracao:.2f}s na pasta: {self.config.pasta_saida}")
