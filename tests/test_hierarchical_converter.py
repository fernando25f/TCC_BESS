import unittest
import os
from src.converter.config import ConverterConfig
from src.converter.elements.substation import SubstationConverter
from src.converter.elements.feeder import FeederConverter
import pandas as pd

class TestHierarchicalConverter(unittest.TestCase):

    def test_converter_config_defaults(self):
        config = ConverterConfig()
        self.assertTrue(config.pasta_saida.endswith("goiania_leste_dss"))
        self.assertTrue(config.pasta_entrada.endswith("dados_goiania_leste"))

    def test_obter_identificador_trafo(self):
        self.assertEqual(SubstationConverter.obter_identificador_trafo("GOL-S-TRF-TR1"), "TR1")
        self.assertEqual(SubstationConverter.obter_identificador_trafo("GOL-S-TRF-TR2"), "TR2")
        self.assertEqual(SubstationConverter.obter_identificador_trafo("GOL-S-TRF-TR3"), "TR3")
        self.assertEqual(SubstationConverter.obter_identificador_trafo("GOL-S-TRF-TR4"), "TR4")
        self.assertEqual(SubstationConverter.obter_identificador_trafo("SUB-S-TRF-TR1"), "TR1")
        self.assertEqual(SubstationConverter.obter_identificador_trafo("TR1"), "TR1")

    def test_agrupar_por_ctmt(self):
        df = pd.DataFrame({
            "COD_ID": ["1", "2", "3"],
            "CTMT": ["5001992", "5001992", "5001994"]
        })
        grupos = FeederConverter._agrupar_por_ctmt(df)
        self.assertIn("5001992", grupos)
        self.assertIn("5001994", grupos)
        self.assertEqual(len(grupos["5001992"]), 2)
        self.assertEqual(len(grupos["5001994"]), 1)

    def test_extrair_coordenadas(self):
        df = pd.DataFrame({
            "PAC_1": ["101", "102"],
            "PAC_2": ["102", "103"],
            "geometria_wkt": [
                "LINESTRING (-49.25 -16.68, -49.26 -16.69)",
                "LINESTRING (-49.26 -16.69, -49.27 -16.70)"
            ]
        })
        coords = {}
        FeederConverter._extrair_coordenadas(df, coords)
        self.assertIn("101", coords)
        self.assertIn("102", coords)
        self.assertIn("103", coords)
        self.assertEqual(coords["101"], ("-49.25", "-16.68"))
        self.assertEqual(coords["103"], ("-49.27", "-16.70"))

if __name__ == "__main__":
    unittest.main()
