import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Dict, Tuple, Optional

from src.simulation.exceptions import ConfigurationError

MINUTOS_DIA = 24 * 60
ESCOPOS_VALIDOS = frozenset({"SUBESTACAO", "TRAFO_AT", "ALIMENTADOR"})


@lru_cache(maxsize=None)
def hhmm_para_minutos(hhmm: str) -> int:
    """Converte 'HH:MM' (00:00 a 24:00) em minutos desde a meia-noite."""
    try:
        horas_str, minutos_str = hhmm.split(":")
        horas, minutos = int(horas_str), int(minutos_str)
    except ValueError as erro:
        raise ConfigurationError(f"Horário '{hhmm}' inválido; use o formato 'HH:MM'.") from erro
    total = horas * 60 + minutos
    if not (0 <= minutos < 60 and 0 <= total <= MINUTOS_DIA):
        raise ConfigurationError(f"Horário '{hhmm}' fora do intervalo 00:00–24:00.")
    return total


@dataclass
class SimulationConfig:
    # Configurações da Subestação / Rede
    nome_subestacao: str = "Goiânia Leste"
    sigla_subestacao: str = "GOL"
    barra_slack: str = "5001462"
    kv_slack: float = 230.0
    pu_slack: float = 1.0
    bases_tensao_kv: List[float] = field(default_factory=lambda: [230.0, 13.8, 0.38])

    # Escopo da Simulação (Hierárquico)
    escopo: str = "SUBESTACAO"          # "SUBESTACAO", "TRAFO_AT" ou "ALIMENTADOR"
    alvo: Optional[str] = None         # Ex: "TR1" (para TRAFO_AT), "5001996" (para ALIMENTADOR), ou None (SE)

    # Parâmetros de simulação
    fator_demanda: float = 0.11
    fator_gd: float = 1.0
    mes_solar: str = "Abril"
    tipo_curva_gd: str = "PicoUnitario"
    limite_subtensao_pu: float = 0.93
    limite_sobretensao_pu: float = 1.05
    passos_simulacao: int = 0           # 0 = dia completo (1440 / passo_minutos)
    passo_minutos: int = 15
    sobrescrever_arquivos: bool = True
    interromper_em_divergencia: bool = True

    # Controle Dinâmico Escalonado de Tap nos Transformadores AT (Subestação)
    # Janelas em horário de relógio (inclusivas) para independerem do tamanho do passo.
    controle_tap_ativo: bool = False
    tap_normal: float = 1.000
    cronograma_tap: Dict[Tuple[str, str], float] = field(default_factory=lambda: {
        ("18:30", "19:15"): 1.050,
        ("19:30", "20:15"): 1.100,
        ("20:30", "21:15"): 1.050,
    })

    def obter_tap_alvo(self, passo: int) -> float:
        """Retorna o tap desejado para o passo da simulação conforme o cronograma."""
        if not self.controle_tap_ativo:
            return self.tap_normal
        minuto_do_dia = passo * self.passo_minutos
        for (inicio, fim), tap in self.cronograma_tap.items():
            if hhmm_para_minutos(inicio) <= minuto_do_dia <= hhmm_para_minutos(fim):
                return tap
        return self.tap_normal

    # Módulo Adicional de Sobrecarga Solar Concentrada (Estudo de BESS)
    sobrecarga_solar_ativa: bool = True
    modo_sobrecarga: str = "MT_FEEDER"  # 'MT_FEEDER', 'BT_DISTRIBUTION', 'HYBRID'
    fator_sobrecarga_alvo: float = 1.50  # 150% da capacidade nominal instalada no alimentador
    alimentador_alvo: str = "5001996"    # Código (ex: "5001996") ou Nome (ex: "GOIANIA LESTE-17")
    trafo_alvo: Optional[str] = None     # Trafo específico para BT. Se None, seleciona os maiores trafos

    # Diretórios base
    diretorio_raiz: str = field(default_factory=lambda: os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    pasta_modelo: str = field(init=False)
    pasta_graficos_tcc: str = field(init=False)
    pasta_logs_tcc: str = field(init=False)

    # Subdiretórios
    pasta_graf_subestacao: str = field(init=False)
    pasta_graf_trafo_dist: str = field(init=False)
    pasta_graf_mapa_rede: str = field(init=False)
    pasta_log_divergencia: str = field(init=False)
    pasta_log_relatorios: str = field(init=False)

    def __post_init__(self):
        self._validar_e_normalizar_parametros()

        pasta_hierarquica = os.path.join(self.diretorio_raiz, "goiania_leste_dss")
        pasta_opendss = os.path.join(self.diretorio_raiz, "opendss")

        tem_hierarquico = os.path.exists(os.path.join(pasta_hierarquica, "alimentadores_info.json"))
        tem_opendss = os.path.exists(os.path.join(pasta_opendss, "transformador_AT.dss")) or os.path.exists(os.path.join(pasta_opendss, "alimentadores_info.json"))

        if tem_hierarquico:
            self.pasta_modelo = pasta_hierarquica
        elif tem_opendss:
            self.pasta_modelo = pasta_opendss
        else:
            self.pasta_modelo = os.path.join(self.diretorio_raiz, "modelo_opendss")

        self.pasta_graficos_tcc = os.path.join(self.diretorio_raiz, "graficos_TCC")
        self.pasta_logs_tcc = os.path.join(self.diretorio_raiz, "logs_TCC")

        self.pasta_graf_subestacao = os.path.join(self.pasta_graficos_tcc, "subestacao")
        self.pasta_graf_trafo_dist = os.path.join(self.pasta_graficos_tcc, "trafo_distribuicao")
        self.pasta_graf_mapa_rede = os.path.join(self.pasta_graficos_tcc, "mapa_rede")

        self.pasta_log_divergencia = os.path.join(self.pasta_logs_tcc, "divergencia")
        self.pasta_log_relatorios = os.path.join(self.pasta_logs_tcc, "relatorios")

        for pasta in [self.pasta_graf_subestacao, self.pasta_graf_trafo_dist, self.pasta_graf_mapa_rede,
                      self.pasta_log_divergencia, self.pasta_log_relatorios]:
            os.makedirs(pasta, exist_ok=True)

    @property
    def id_subestacao_sanitizado(self) -> str:
        tabela = str.maketrans("áàãâéêíóôõúçÁÀÃÂÉÊÍÓÔÕÚÇ ", "aaaaeeioooucaaaaeeiooouc_")
        return self.nome_subestacao.translate(tabela)

    @property
    def meta_simulacao(self) -> str:
        return f"FD = {self.fator_demanda*100:.0f}% | GD = x{self.fator_gd:.1f} ({self.mes_solar})"

    def _validar_e_normalizar_parametros(self) -> None:
        if self.escopo.upper() not in ESCOPOS_VALIDOS:
            raise ConfigurationError(
                f"Escopo '{self.escopo}' inválido. Use um de: {', '.join(sorted(ESCOPOS_VALIDOS))}."
            )

        # Loadshapes diários exigem passo que divida o dia inteiro, senão o último instante não fecha em 24:00
        if self.passo_minutos <= 0 or MINUTOS_DIA % self.passo_minutos != 0:
            raise ConfigurationError(
                f"passo_minutos={self.passo_minutos} deve ser divisor positivo de 1440 (ex.: 1, 5, 15, 60)."
            )
        if self.passos_simulacao == 0:
            self.passos_simulacao = MINUTOS_DIA // self.passo_minutos
        if not 0 < self.passos_simulacao * self.passo_minutos <= MINUTOS_DIA:
            raise ConfigurationError(
                f"passos_simulacao={self.passos_simulacao} com passo de {self.passo_minutos} min "
                f"excede 24 h ou é não positivo."
            )

        for inicio, fim in self.cronograma_tap:
            if hhmm_para_minutos(inicio) > hhmm_para_minutos(fim):
                raise ConfigurationError(f"Janela de tap ({inicio}, {fim}) tem início após o fim.")

    @property
    def passo_horas(self) -> float:
        """Duração do passo em horas (Δt usado na integração de energia: kWh = kW · Δt)."""
        return self.passo_minutos / 60.0

    @property
    def vetor_tempo_horas(self) -> List[float]:
        return [step * self.passo_horas for step in range(1, self.passos_simulacao + 1)]

    def formatar_hora_passo(self, passo: int) -> str:
        """Converte o índice do passo (1..N, fim do intervalo) em 'HH:MM'; passo <= 0 indica ausência de registro."""
        if passo <= 0:
            return "--:--"
        minutos = int(passo) * self.passo_minutos
        if minutos >= MINUTOS_DIA:
            return "24:00"
        return f"{minutos // 60:02d}:{minutos % 60:02d}"

    def obter_caminho_saida(self, pasta: str, nome_base: str, extensao: str) -> str:
        """Retorna o caminho de saída (sobrescrevendo ou versionando conforme configurado)."""
        if self.sobrescrever_arquivos:
            return os.path.join(pasta, f"{nome_base}.{extensao}")
        return self._caminho_sem_sobrescrever(pasta, nome_base, extensao)

    def _caminho_sem_sobrescrever(self, pasta: str, nome_base: str, extensao: str) -> str:
        caminho = os.path.join(pasta, f"{nome_base}.{extensao}")
        if not os.path.exists(caminho):
            return caminho
        v = 2
        while True:
            caminho = os.path.join(pasta, f"{nome_base}_v{v}.{extensao}")
            if not os.path.exists(caminho):
                return caminho
            v += 1

    def relpath(self, caminho: str) -> str:
        """Retorna caminho relativo curto a partir da raiz do projeto para logs limpos."""
        return os.path.relpath(caminho, self.diretorio_raiz)

    @property
    def alimentador_alvo_manual(self) -> str:
        return self.alimentador_alvo

    @property
    def trafo_alvo_manual(self) -> Optional[str]:
        return self.trafo_alvo
