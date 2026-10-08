import os
import time
import geopandas as gpd
from src.extractor.config import ExtractorConfig
from src.extractor.geometry import GeometryProcessor

class GdbExtractorService:
    """Orquestrador da extração de camadas da BDGD filtradas para uma subestação."""

    def __init__(self, config: ExtractorConfig):
        self.config = config
        self.processor = GeometryProcessor()

    def extrair(self):
        """Executa o pipeline completo de extração da subestação."""
        t0_total = time.time()
        print("\n" + "=" * 70)
        print("EXTRAÇÃO DE DADOS DA BDGD (GDB)")
        print(f"Subestação (COD_ID): {self.config.codigo_subestacao}")
        print(f"Arquivo GDB:        {self.config.caminho_gdb}")
        print(f"Pasta de Saída:     {self.config.pasta_saida}")
        print("=" * 70)

        # 1. Subestação (SUB)
        self._extrair_camada_direta(
            layer="SUB",
            coluna_filtro="COD_ID",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="SUB.csv",
            descricao="Subestação"
        )

        # 2. Alimentadores MT (CTMT)
        self._extrair_camada_direta(
            layer="CTMT",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="CTMT.csv",
            descricao="Alimentadores da subestação"
        )

        # 3. Transformadores AT/MT (UNTRAT + EQTRAT)
        untrat_filtrado = self._extrair_camada_direta(
            layer="UNTRAT",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="UNTRAT.csv",
            descricao="Trafos AT/MT (localização e potência)"
        )
        codigos_untrat = set(untrat_filtrado["COD_ID"].tolist()) if not untrat_filtrado.empty else set()
        self._extrair_camada_relacional(
            layer="EQTRAT",
            coluna_filtro="UNI_TR_AT",
            valores_permitidos=codigos_untrat,
            nome_arquivo="EQTRAT.csv",
            descricao="Dados elétricos dos trafos AT/MT"
        )

        # 4. Linhas de Média Tensão (SSDMT)
        ssdmt_filtrado = self._extrair_camada_direta(
            layer="SSDMT",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="SSDMT.csv",
            descricao="Segmentos de linha MT"
        )
        tipos_cnd_mt = set(ssdmt_filtrado["TIP_CND"].dropna().unique()) if not ssdmt_filtrado.empty else set()

        # 5. Linhas de Baixa Tensão (SSDBT)
        ssdbt_filtrado = self._extrair_camada_direta(
            layer="SSDBT",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="SSDBT.csv",
            descricao="Segmentos de linha BT"
        )
        tipos_cnd_bt = set(ssdbt_filtrado["TIP_CND"].dropna().unique()) if not ssdbt_filtrado.empty else set()

        # 6. Catálogo de Condutores (SEGCON)
        todos_tipos_cnd = tipos_cnd_mt | tipos_cnd_bt
        self._extrair_camada_relacional(
            layer="SEGCON",
            coluna_filtro="COD_ID",
            valores_permitidos=todos_tipos_cnd,
            nome_arquivo="SEGCON.csv",
            descricao="Catálogo de condutores usados"
        )

        # 7. Transformadores MT/BT de Distribuição (UNTRMT + EQTRMT)
        untrmt_filtrado = self._extrair_camada_direta(
            layer="UNTRMT",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="UNTRMT.csv",
            descricao="Trafos MT/BT (localização)"
        )
        codigos_untrmt = set(untrmt_filtrado["COD_ID"].tolist()) if not untrmt_filtrado.empty else set()
        self._extrair_camada_relacional(
            layer="EQTRMT",
            coluna_filtro="UNI_TR_MT",
            valores_permitidos=codigos_untrmt,
            nome_arquivo="EQTRMT.csv",
            descricao="Dados elétricos trafos MT/BT"
        )

        # 8. Consumidores BT (UCBT_tab)
        ucbt_filtrado = self._extrair_camada_direta(
            layer="UCBT_tab",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="UCBT.csv",
            descricao="Unidades consumidoras BT"
        )
        tipos_curva_bt = set(ucbt_filtrado["TIP_CC"].dropna().unique()) if not ucbt_filtrado.empty else set()

        # 9. Consumidores MT (UCMT_tab)
        ucmt_filtrado = self._extrair_camada_direta(
            layer="UCMT_tab",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="UCMT.csv",
            descricao="Unidades consumidoras MT"
        )
        tipos_curva_mt = set(ucmt_filtrado["TIP_CC"].dropna().unique()) if not ucmt_filtrado.empty else set()

        # 10. Curvas de Carga (CRVCRG)
        todas_curvas = tipos_curva_bt | tipos_curva_mt
        self._extrair_camada_relacional(
            layer="CRVCRG",
            coluna_filtro="COD_ID",
            valores_permitidos=todas_curvas,
            nome_arquivo="CRVCRG.csv",
            descricao="Curvas de carga (perfis 24h)"
        )

        # 11. Geração Distribuída BT (UGBT_tab)
        self._extrair_camada_direta(
            layer="UGBT_tab",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="UGBT.csv",
            descricao="Geração distribuída BT"
        )

        # 12. Geração Distribuída MT (UGMT_tab)
        self._extrair_camada_direta(
            layer="UGMT_tab",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="UGMT.csv",
            descricao="Geração distribuída MT"
        )

        # 13. Bancos de Capacitores MT (UNCRMT)
        self._extrair_camada_direta(
            layer="UNCRMT",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="UNCRMT.csv",
            descricao="Bancos de capacitores MT"
        )

        # 14. Barramentos (BAR)
        self._extrair_camada_direta(
            layer="BAR",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="BAR.csv",
            descricao="Barramentos da subestação"
        )

        # 15. Chaves Seccionadoras (UNSEMT)
        self._extrair_camada_direta(
            layer="UNSEMT",
            coluna_filtro="SUB",
            valor_filtro=self.config.codigo_subestacao,
            nome_arquivo="UNSEMT.csv",
            descricao="Chaves seccionadoras MT"
        )

        duracao_total = time.time() - t0_total
        self._imprimir_resumo(duracao_total)

    def _extrair_camada_direta(self, layer: str, coluna_filtro: str, valor_filtro: str, nome_arquivo: str, descricao: str):
        t0 = time.time()
        caminho_saida = os.path.join(self.config.pasta_saida, nome_arquivo)
        gdf = gpd.read_file(self.config.caminho_gdb, layer=layer)
        filtrado = gdf[gdf[coluna_filtro].astype(str) == str(valor_filtro)]
        self.processor.processar_e_salvar_csv(filtrado, caminho_saida, descricao)
        print(f"     [Tempo camada: {time.time() - t0:.1f}s]")
        return filtrado

    def _extrair_camada_relacional(self, layer: str, coluna_filtro: str, valores_permitidos: set, nome_arquivo: str, descricao: str):
        t0 = time.time()
        caminho_saida = os.path.join(self.config.pasta_saida, nome_arquivo)
        gdf = gpd.read_file(self.config.caminho_gdb, layer=layer)
        valores_str = {str(v) for v in valores_permitidos}
        filtrado = gdf[gdf[coluna_filtro].astype(str).isin(valores_str)]
        self.processor.processar_e_salvar_csv(filtrado, caminho_saida, descricao)
        print(f"     [Tempo camada: {time.time() - t0:.1f}s]")
        return filtrado

    def _imprimir_resumo(self, duracao_total: float):
        print("\n" + "=" * 70)
        print("RESUMO DA EXTRAÇÃO")
        print("=" * 70)
        print(f"  Subestação:    {self.config.codigo_subestacao}")
        print(f"  Pasta de saída: {self.config.pasta_saida}")
        print(f"  Tempo total:   {duracao_total:.1f}s ({duracao_total / 60:.1f} min)")
        print()
        arquivos = sorted(os.listdir(self.config.pasta_saida))
        print(f"  Arquivos gerados ({len(arquivos)}):")
        for arq in arquivos:
            caminho_arq = os.path.join(self.config.pasta_saida, arq)
            if os.path.isfile(caminho_arq):
                tamanho = os.path.getsize(caminho_arq)
                if tamanho > 1_000_000:
                    print(f"    → {arq} ({tamanho / 1_000_000:.1f} MB)")
                else:
                    print(f"    → {arq} ({tamanho / 1_000:.1f} KB)")
        print("\n[OK] Extração concluída com sucesso!")
