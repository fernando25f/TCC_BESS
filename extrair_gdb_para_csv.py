"""
Ponto de entrada para extração de camadas da BDGD (GDB) para tabelas CSV.
Permite extrair qualquer subestação definindo os parâmetros diretamente
na configuração ou via argumentos de linha de comando.
"""
import sys
import argparse
from src.extractor.config import ExtractorConfig
from src.extractor.service import GdbExtractorService

def parse_args():
    parser = argparse.ArgumentParser(description="Extrator BDGD (GDB) para CSV")
    parser.add_argument("--gdb", type=str, default="ENEL_GO-30-04-2023.gdb", help="Caminho do arquivo .gdb da BDGD")
    parser.add_argument("--sub", type=str, default="5001462", help="Código da subestação (COD_ID da camada SUB)")
    parser.add_argument("--saida", type=str, default="dados_goiania_leste", help="Pasta de destino para os CSVs")
    return parser.parse_args()

def main():
    if len(sys.argv) > 1:
        args = parse_args()
        config = ExtractorConfig(
            caminho_gdb=args.gdb,
            codigo_subestacao=args.sub,
            pasta_saida=args.saida
        )
    else:
        # Configuração padrão: altere os valores abaixo para analisar outra subestação
        config = ExtractorConfig(
            caminho_gdb="ENEL_GO-30-04-2023.gdb",  # Base GDB da distribuidora
            codigo_subestacao="5001462",           # Ex: 5001462 (Goiânia Leste)
            pasta_saida="goiania_leste"      # Pasta de saída dos CSVs
        )

    service = GdbExtractorService(config)
    service.extrair()

if __name__ == "__main__":
    main()
