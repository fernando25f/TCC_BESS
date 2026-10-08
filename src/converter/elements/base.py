from abc import ABC, abstractmethod
import pandas as pd
from typing import Tuple, Optional, Any
from src.converter.config import ConverterConfig
from src.converter.repository import BDGDRepository

MAPA_FASES = {
    'ABC': ('.1.2.3', 3, 'delta'),
    'A': ('.1', 1, 'wye'),
    'B': ('.2', 1, 'wye'),
    'C': ('.3', 1, 'wye'),
    'AB': ('.1.2', 2, 'delta'),
    'BC': ('.2.3', 2, 'delta'),
    'CA': ('.3.1', 2, 'delta'),
    'ABCN': ('.1.2.3.0', 3, 'delta'),
    'AN': ('.1.0', 1, 'wye'),
    'BN': ('.2.0', 1, 'wye'),
    'CN': ('.3.0', 1, 'wye'),
    'ABN': ('.1.2.0', 3, 'delta'),
    'BCN': ('.2.3.0', 3, 'delta'),
    'CAN': ('.3.1.0', 3, 'delta'),
    'ACN': ('.1.3.0', 2, 'wye')
}

def obter_fase_e_tensao_bt(fas_con: Any, pot_kw: Optional[float] = None) -> Tuple[str, int, str, float]:
    """Retorna nós, número de fases, conexão e tensão nominal kV para elementos BT."""
    fas_str = str(fas_con).strip().upper() if pd.notna(fas_con) else ""

    if fas_str in ('AN', 'A'):
        return ('.1.0', 1, 'wye', 0.22)
    elif fas_str in ('BN', 'B'):
        return ('.2.0', 1, 'wye', 0.22)
    elif fas_str in ('CN', 'C'):
        return ('.3.0', 1, 'wye', 0.22)
    elif fas_str in ('ABN', 'AB'):
        return ('.1.2.0', 2, 'wye', 0.38)
    elif fas_str in ('BCN', 'BC'):
        return ('.2.3.0', 2, 'wye', 0.38)
    elif fas_str in ('CAN', 'CA'):
        return ('.3.1.0', 2, 'wye', 0.38)
    elif fas_str in ('ACN', 'AC'):
        return ('.1.3.0', 2, 'wye', 0.38)
    elif fas_str == 'ABC':
        return ('.1.2.3', 3, 'wye', 0.38)
    elif fas_str == 'ABCN':
        return ('.1.2.3.0', 3, 'wye', 0.38)
    else:
        if pot_kw is not None and float(pot_kw) <= 8.0:
            return ('.1.0', 1, 'wye', 0.22)
        return ('.1.2.3.0', 3, 'wye', 0.38)

class BaseElementConverter(ABC):
    """Classe base abstrata para geradores de elementos OpenDSS a partir da BDGD."""

    @abstractmethod
    def converter(self, repo: BDGDRepository, config: ConverterConfig):
        """Converte dados da BDGD e escreve os respectivos arquivos .dss."""
        pass
