from __future__ import annotations
import os
import json
from typing import Dict, Any, List, Mapping, Tuple, Optional
import opendssdirect as dss

from src.simulation.config import SimulationConfig
from src.simulation.core.target_resolver import resolver_alimentador as resolver_alimentador_estrito
from src.simulation.core.target_resolver import resolver_trafo_at
from src.simulation.exceptions import (
    AmbiguousFeederError,
    CircuitLoadError,
    ConfigurationError,
    FeederNotFoundError,
)

class CircuitManager:
    """Encapsula operações com a rede elétrica no OpenDSS, suportando múltiplos escopos hierárquicos."""

    def __init__(self, config: SimulationConfig) -> None:
        self.config: SimulationConfig = config
        self.cache_trafos_mt: Dict[str, Dict[str, Any]] = {}
        self.dict_trafos_por_alimentador: Dict[str, List[Tuple[str, float, str]]] = {}
        self.dict_ctmt_info: Dict[str, Any] = {}
        self.trafos_subestacao_info: Dict[str, Any] = {}
        self.trafos_subestacao: List[str] = []
        self.trafo_sec_bus: Dict[str, str] = {}
        self.todos_ctmt_info: Dict[str, Any] = {}
        self.todos_trafos_subestacao_info: Dict[str, Any] = {}
        self._carregar_metadados_subestacao()

    def _carregar_metadados_subestacao(self) -> None:
        caminho_json = os.path.join(self.config.pasta_modelo, "alimentadores_info.json")
        if os.path.exists(caminho_json):
            with open(caminho_json, "r", encoding="utf-8") as fj:
                dados = json.load(fj)
                self.todos_ctmt_info = dados.get("alimentadores", {})
                self.todos_trafos_subestacao_info = dados.get("trafos_subestacao", {})

                # Normaliza pasta_tr para compatibilidade com json legado
                for cod, info in self.todos_ctmt_info.items():
                    if "pasta_tr" not in info and "trafo" in info:
                        tr_str = str(info["trafo"]).replace("GOL-S-TRF-", "")
                        info["pasta_tr"] = tr_str.split("-")[-1]
        else:
            sigla = self.config.sigla_subestacao
            self.todos_trafos_subestacao_info = {
                f"{sigla}-S-TRF-TR1": {"identificador": "TR1", "pasta": "TR1", "barra_primaria": self.config.barra_slack, "barra_secundaria": "1783", "pot_nom_mva": 50.0},
                f"{sigla}-S-TRF-TR2": {"identificador": "TR2", "pasta": "TR2", "barra_primaria": self.config.barra_slack, "barra_secundaria": "4629", "pot_nom_mva": 50.0},
                f"{sigla}-S-TRF-TR3": {"identificador": "TR3", "pasta": "TR3", "barra_primaria": self.config.barra_slack, "barra_secundaria": "4630", "pot_nom_mva": 50.0},
                f"{sigla}-S-TRF-TR4": {"identificador": "TR4", "pasta": "TR4", "barra_primaria": self.config.barra_slack, "barra_secundaria": "6440", "pot_nom_mva": 50.0}
            }

        escopo = self.config.escopo.upper()
        if escopo == "ALIMENTADOR":
            cod_alvo, _ = resolver_alimentador_estrito(
                self.config.alvo or self.config.alimentador_alvo, self.todos_ctmt_info
            )
            self.trafos_subestacao_info = {}
            self.trafos_subestacao = []
            self.trafo_sec_bus = {}
            self.dict_ctmt_info = {cod_alvo: self.todos_ctmt_info[cod_alvo]}

        elif escopo == "TRAFO_AT":
            tr_nome, tr_info = resolver_trafo_at(self.config.alvo, self.todos_trafos_subestacao_info)
            self.trafos_subestacao_info = {tr_nome: dict(tr_info)}
            self.trafos_subestacao = [tr_nome]
            self.trafo_sec_bus = {tr_nome: self._campo_obrigatorio(tr_info, "barra_secundaria", tr_nome)}
            tr_short = tr_info.get("identificador", tr_nome)
            self.dict_ctmt_info = {
                cod: info for cod, info in self.todos_ctmt_info.items()
                if info.get("pasta_tr") == tr_short or info.get("trafo") == tr_nome
            }
            if not self.dict_ctmt_info:
                raise CircuitLoadError(
                    f"Nenhum alimentador associado ao transformador {tr_nome} em alimentadores_info.json."
                )

        elif escopo == "SUBESTACAO":
            self.trafos_subestacao_info = dict(self.todos_trafos_subestacao_info)
            self.trafos_subestacao = list(self.trafos_subestacao_info.keys())
            self.trafo_sec_bus = {
                tr: self._campo_obrigatorio(info, "barra_secundaria", tr)
                for tr, info in self.trafos_subestacao_info.items()
            }
            self.dict_ctmt_info = dict(self.todos_ctmt_info)

        else:
            raise ConfigurationError(
                f"Escopo '{self.config.escopo}' inválido. Use SUBESTACAO, TRAFO_AT ou ALIMENTADOR."
            )

    @staticmethod
    def _campo_obrigatorio(info: Mapping[str, Any], campo: str, contexto: str) -> str:
        valor = info.get(campo)
        if valor in (None, ""):
            raise CircuitLoadError(f"Campo obrigatório '{campo}' ausente nos metadados de '{contexto}'.")
        return str(valor)

    def resolver_alimentador(self, alvo: Optional[str]) -> Tuple[str, str]:
        """Resolve (código, nome) do alimentador dentro do escopo carregado, sem fallback."""
        try:
            return resolver_alimentador_estrito(alvo, self.dict_ctmt_info)
        except FeederNotFoundError as erro_no_escopo:
            mensagem_fora_escopo = self._descrever_alvo_fora_do_escopo(alvo)
            if mensagem_fora_escopo is None:
                raise
            raise FeederNotFoundError(mensagem_fora_escopo) from erro_no_escopo

    def _descrever_alvo_fora_do_escopo(self, alvo: Optional[str]) -> Optional[str]:
        """Diferencia 'não existe' de 'existe em outro trafo AT' para orientar o ajuste da configuração."""
        fora_do_escopo = {
            cod: info for cod, info in self.todos_ctmt_info.items() if cod not in self.dict_ctmt_info
        }
        try:
            cod, nome = resolver_alimentador_estrito(alvo, fora_do_escopo)
        except (FeederNotFoundError, AmbiguousFeederError):
            return None
        trafo_origem = fora_do_escopo[cod].get("pasta_tr") or fora_do_escopo[cod].get("trafo", "?")
        return (
            f"Alimentador {cod} ({nome}) pertence ao {trafo_origem}, fora do escopo atual "
            f"(escopo={self.config.escopo}, alvo={self.config.alvo}). Ajuste 'alimentador_alvo' na configuração."
        )

    def carregar_circuito_base(self) -> None:
        """Inicializa o circuito no OpenDSS adaptando a fonte e arquivos conforme o escopo selecionado."""
        dss.Command("clear")

        # Verifica se o modelo na pasta possui a estrutura hierárquica por pastas de TR
        pastas_tr_existentes = [d for d in ["TR1", "TR2", "TR3", "TR4"] if os.path.isdir(os.path.join(self.config.pasta_modelo, d))]
        is_hierarquico = len(pastas_tr_existentes) > 0

        if is_hierarquico:
            self._carregar_circuito_hierarquico()
        else:
            self._carregar_circuito_legado()

    def _carregar_circuito_hierarquico(self) -> None:
        escopo = self.config.escopo.upper()

        # 1. Curvas compartilhadas: a de carga é obrigatória (todas as cargas a referenciam);
        #    a solar é opcional aqui porque o SolarScenario valida sua existência.
        self._redirect_obrigatorio(os.path.join(self.config.pasta_modelo, "curva_carga.dss"), "Curvas de carga")
        arq_curva_solar = os.path.join(self.config.pasta_modelo, "curva_solar.dss")
        if os.path.exists(arq_curva_solar):
            dss.Command(f'redirect "{arq_curva_solar}"')

        # 2. Inicializa a fonte Slack e topologia baseado no escopo
        if escopo == "ALIMENTADOR":
            cod_alvo = next(iter(self.dict_ctmt_info.keys()))
            ctmt_info = self.dict_ctmt_info[cod_alvo]
            barra_dj = self._campo_obrigatorio(ctmt_info, "barra", cod_alvo)
            dss.Command(f"new circuit.CTMT_{cod_alvo} basekv=13.8 bus1={barra_dj} pu={self.config.pu_slack} phases=3 MVAsc3=500 MVAsc1=437.5")
            self._redirect_obrigatorio(self._caminho_ctmt(cod_alvo, ctmt_info), f"Alimentador {cod_alvo}")

        elif escopo == "TRAFO_AT":
            tr_nome = next(iter(self.trafos_subestacao_info.keys()))
            tr_info = self.trafos_subestacao_info[tr_nome]
            barra_pri = tr_info.get("barra_primaria", self.config.barra_slack)
            tr_short = self._campo_obrigatorio(tr_info, "identificador", tr_nome)
            dss.Command(f"new circuit.Trafo_{tr_short} basekv={self.config.kv_slack} bus1={barra_pri} pu={self.config.pu_slack} phases=3 MVAsc3=8000 MVAsc1=7000 X1R1=12 X0R0=12")

            self._redirect_obrigatorio(self._caminho_trafo(tr_nome, tr_info), f"Transformador {tr_nome}")
            for cod_id, ctmt_info in self.dict_ctmt_info.items():
                self._redirect_obrigatorio(self._caminho_ctmt(cod_id, ctmt_info), f"Alimentador {cod_id}")

        else:
            # SUBESTACAO completa
            nome_ckt = f"Subestacao_{self.config.id_subestacao_sanitizado}"
            dss.Command(f"new circuit.{nome_ckt} basekv={self.config.kv_slack} bus1={self.config.barra_slack} pu={self.config.pu_slack} phases=3 MVAsc3=8000 MVAsc1=7000 X1R1=12 X0R0=12")

            for tr_nome, tr_info in self.trafos_subestacao_info.items():
                self._redirect_obrigatorio(self._caminho_trafo(tr_nome, tr_info), f"Transformador {tr_nome}")
            for cod_id, ctmt_info in self.dict_ctmt_info.items():
                self._redirect_obrigatorio(self._caminho_ctmt(cod_id, ctmt_info), f"Alimentador {cod_id}")

    @staticmethod
    def _redirect_obrigatorio(caminho: str, descricao: str) -> None:
        # Arquivo ausente removeria carga/geração da rede sem aviso, distorcendo todos os resultados
        if not os.path.exists(caminho):
            raise CircuitLoadError(f"{descricao}: arquivo não encontrado em {caminho}")
        dss.Command(f'redirect "{caminho}"')

    def _caminho_trafo(self, tr_nome: str, tr_info: Mapping[str, Any]) -> str:
        arq_rel = tr_info.get("arquivo_dss")
        if not arq_rel:
            tr_short = self._campo_obrigatorio(tr_info, "identificador", tr_nome)
            arq_rel = f"{tr_short}/trafo_{tr_short}.dss"
        return os.path.join(self.config.pasta_modelo, arq_rel)

    def _caminho_ctmt(self, cod_id: str, ctmt_info: Mapping[str, Any]) -> str:
        arq_rel = ctmt_info.get("arquivo_dss")
        if not arq_rel:
            pasta_tr = self._campo_obrigatorio(ctmt_info, "pasta_tr", cod_id)
            arq_rel = f"{pasta_tr}/CTMT_{cod_id}.dss"
        return os.path.join(self.config.pasta_modelo, arq_rel)

    def _carregar_circuito_legado(self) -> None:
        nome_ckt = f"Subestacao_{self.config.id_subestacao_sanitizado}"
        dss.Command(f"new circuit.{nome_ckt} basekv={self.config.kv_slack} bus1={self.config.barra_slack} pu={self.config.pu_slack} phases=3 MVAsc3=8000 MVAsc1=7000 X1R1=12 X0R0=12")

        arquivos_obrigatorios = [
            "transformador_AT.dss",
            "disjuntores_mt.dss",
            "seccionadoras_mt.dss",
            "transformador_MT.dss",
            "linhas_mt.dss",
            "linhas_bt.dss",
            "curva_carga.dss",
            "carga_bt.dss"
        ]
        for arq in arquivos_obrigatorios:
            caminho = os.path.join(self.config.pasta_modelo, arq)
            if not os.path.exists(caminho):
                raise CircuitLoadError(f"Arquivo base obrigatório não encontrado: {caminho}")
            dss.Command(f'redirect "{caminho}"')

        for arq in ["capacitores_mt.dss", "carga_mt.dss"]:
            caminho = os.path.join(self.config.pasta_modelo, arq)
            if os.path.exists(caminho):
                dss.Command(f'redirect "{caminho}"')

        buscoords = os.path.join(self.config.pasta_modelo, "buscoords.dss")
        if os.path.exists(buscoords):
            dss.Command(f'Buscoords "{buscoords}"')

    def configurar_bases_e_demanda(self) -> None:
        """Configura tensões nominais de base e fator global de carga."""
        dss.Command(f"Set voltagebases={self.config.bases_tensao_kv}")
        dss.Command("Calcvoltagebases")
        dss.Command(f"Set LoadMult={self.config.fator_demanda:.4f}")

    def inicializar_solucao(self) -> None:
        """Executa snapshot inicial para fatoração matricial da Ybus."""
        dss.Command("set mode=snapshot")
        dss.Solution.Solve()

    def mapear_trafos_mt(self) -> Dict[str, Dict[str, Any]]:
        """Mapeia e indexa em hash map todos os transformadores MT da rede para consultas O(1)."""
        nomes_trafos = [t for t in dss.Transformers.AllNames() if t.startswith('untrmt_')]
        cache: Dict[str, Dict[str, Any]] = {}
        trafos_por_ctmt: Dict[str, List[Tuple[str, float, str]]] = {cod: [] for cod in self.dict_ctmt_info.keys()}

        for t_nome in nomes_trafos:
            dss.Transformers.Name(t_nome)
            kva = dss.Transformers.kVA()
            if kva > 0:
                buses = dss.CktElement.BusNames()
                sec_bus = buses[1] if len(buses) > 1 else ''
                cache[t_nome] = {
                    'cod_id': t_nome.replace('untrmt_', ''),
                    'kva_nom': kva,
                    'limite_kva2': (kva * 1.25) ** 2,
                    'barra_bt': sec_bus,
                    'bus_clean': sec_bus.split('.')[0]
                }

                for cod in trafos_por_ctmt.keys():
                    if any(cod in b for b in buses):
                        trafos_por_ctmt[cod].append((t_nome, kva, sec_bus))
                        break

        self.cache_trafos_mt = cache
        self.dict_trafos_por_alimentador = trafos_por_ctmt
        return cache

    def obter_trafos_do_alimentador(self, cod_alimentador: str) -> List[Tuple[str, float, str]]:
        """Retorna transformadores de distribuição do alimentador em tempo O(1) via índice hash."""
        if not self.dict_trafos_por_alimentador:
            self.mapear_trafos_mt()
        return self.dict_trafos_por_alimentador.get(cod_alimentador, [])

    def ajustar_tap_trafos_subestacao(self, tap: float) -> None:
        """Ajusta a posição de tap no secundário (wdg=2) de todos os transformadores AT presentes no escopo."""
        for tr in self.trafos_subestacao:
            dss.Command(f"Transformer.{tr}.wdg=2 tap={tap:.4f}")
