import os
from dataclasses import dataclass, field
from typing import Optional, Union

@dataclass
class ConverterConfig:
    """Configurações e parâmetros do pipeline de conversão BDGD para OpenDSS."""

    diretorio_raiz: str = field(default_factory=lambda: os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    # Pastas e identificação da subestação (configuráveis)
    pasta_entrada: str = "dados_goiania_leste"
    pasta_saida: str = "goiania_leste_dss"
    pasta_dicionarios: str = "dicionarios_bdgd"
    nome_subestacao: Optional[str] = None

    # Filtros operacionais
    trafo_at_alvo: Optional[str] = None
    linha_corte: Optional[Union[int, str]] = None
    ctmt_corte: Optional[Union[int, str]] = None
    somente_urbano: bool = True

    def __post_init__(self):
        if not os.path.isabs(self.pasta_entrada):
            self.pasta_entrada = os.path.join(self.diretorio_raiz, self.pasta_entrada)
        if not os.path.isabs(self.pasta_saida):
            self.pasta_saida = os.path.join(self.diretorio_raiz, self.pasta_saida)
        if not os.path.isabs(self.pasta_dicionarios):
            self.pasta_dicionarios = os.path.join(self.diretorio_raiz, self.pasta_dicionarios)

        os.makedirs(self.pasta_saida, exist_ok=True)
