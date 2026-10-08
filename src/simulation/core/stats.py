from dataclasses import dataclass, field
from typing import List

@dataclass
class ElementStats:
    """Estatísticas operacionais detalhadas de um elemento do circuito."""
    p_max_kw: float = 0.0
    s_max_kva: float = 0.0
    q_at_pmax: float = 0.0
    hora_pico: str = '--:--'
    fp_pico: float = 1.0
    v_min_pu: float = 999.0
    v_max_pu: float = 0.0
    energia_kwh: float = 0.0
    curva_p_kw: List[float] = field(default_factory=list)
