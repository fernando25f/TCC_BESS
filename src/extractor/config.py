import os
from dataclasses import dataclass, field

@dataclass
class ExtractorConfig:
    """Configurações e parâmetros do pipeline de extração de camadas da BDGD (GDB)."""

    diretorio_raiz: str = field(default_factory=lambda: os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    caminho_gdb: str = "ENEL_GO-30-04-2023.gdb"
    codigo_subestacao: str = "5001462"
    pasta_saida: str = "dados_goiania_leste"

    def __post_init__(self):
        if not os.path.isabs(self.caminho_gdb):
            self.caminho_gdb = os.path.join(self.diretorio_raiz, self.caminho_gdb)
        if not os.path.isabs(self.pasta_saida):
            self.pasta_saida = os.path.join(self.diretorio_raiz, self.pasta_saida)

        if not os.path.exists(self.caminho_gdb):
            raise FileNotFoundError(
                f"Base geográfica GDB não encontrada no caminho especificado: {self.caminho_gdb}"
            )

        os.makedirs(self.pasta_saida, exist_ok=True)
