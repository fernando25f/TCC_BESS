"""
Ponto de entrada para conversão dos dados tabulares da BDGD para modelos OpenDSS.
Permite executar a conversão para qualquer subestação definindo os parâmetros
diretamente na configuração ou via argumentos de linha de comando.
"""
import sys
import argparse
from src.converter.config import ConverterConfig
from src.converter.builder import DssModelBuilder

def parse_args():
    parser = argparse.ArgumentParser(description="Conversor BDGD para OpenDSS")
    parser.add_argument("--entrada", type=str, default="dados_goiania_leste", help="Pasta com CSVs da BDGD")
    parser.add_argument("--saida", type=str, default="goiania_leste_dss", help="Pasta de saída para os scripts DSS")
    parser.add_argument("--subestacao", type=str, default=None, help="Nome/identificador da subestação (opcional)")
    parser.add_argument("--trafo-alvo", type=str, default=None, help="Código do trafo AT para isolar circuito")
    parser.add_argument("--linha-corte", type=str, default=None, help="Linha de corte para poda topológica")
    parser.add_argument("--ctmt-corte", type=str, default=None, help="Código do alimentador para a poda")
    parser.add_argument("--somente-urbano", action="store_true", default=True, help="Filtrar apenas cargas urbanas (UB)")
    return parser.parse_args()

def main():
    if len(sys.argv) > 1:
        args = parse_args()
        config = ConverterConfig(
            pasta_entrada=args.entrada,
            pasta_saida=args.saida,
            nome_subestacao=args.subestacao,
            trafo_at_alvo=args.trafo_alvo,
            linha_corte=args.linha_corte,
            ctmt_corte=args.ctmt_corte,
            somente_urbano=args.somente_urbano
        )
    else:
        # Configuração padrão: modifique as variáveis abaixo para qualquer subestação
        config = ConverterConfig(
            pasta_entrada="dados_goiania_leste",    # Pasta com os CSVs da BDGD da subestação
            pasta_saida="goiania_leste_dss",        # Pasta de destino dos scripts OpenDSS
            nome_subestacao=None,                   # None para auto-detectar ou str customizada
            trafo_at_alvo=None,                     # Ex: 'GOL-S-TRF-TR2' ou None para subestação completa
            linha_corte=None,                       # Ex: 53742031 ou None para desativar poda topológica
            ctmt_corte=None,                        # Alimentador alvo para a poda (se linha_corte for usada)
            somente_urbano=True                     # Mantém escopo urbano (ARE_LOC == 'UB')
        )

    builder = DssModelBuilder(config)
    builder.construir_modelo()

if __name__ == "__main__":
    main()
