import unittest
from src.simulation.config import SimulationConfig
from src.simulation.core.circuit import CircuitManager
from src.simulation.exceptions import FeederNotFoundError

class TestCircuitResolver(unittest.TestCase):

    def setUp(self):
        cfg = SimulationConfig()
        self.circuit = CircuitManager(cfg)
        self.circuit.dict_ctmt_info = {
            "5001996": {"nome": "GOIANIA LESTE-17", "trafo": "GOL-S-TRF-TR2", "barra": "4629"},
            "5002409": {"nome": "GOIANIA LESTE-1", "trafo": "GOL-S-TRF-TR3", "barra": "4630"},
            "5001992": {"nome": "GOIANIA LESTE-10", "trafo": "GOL-S-TRF-TR1", "barra": "1783"},
        }

    def test_resolver_alimentador_por_codigo(self):
        cod, nome = self.circuit.resolver_alimentador("5001996")
        self.assertEqual(cod, "5001996")
        self.assertEqual(nome, "GOIANIA LESTE-17")

        cod, nome = self.circuit.resolver_alimentador("5002409")
        self.assertEqual(cod, "5002409")
        self.assertEqual(nome, "GOIANIA LESTE-1")

    def test_resolver_alimentador_por_nome_completo(self):
        cod, nome = self.circuit.resolver_alimentador("GOIANIA LESTE-17")
        self.assertEqual(cod, "5001996")
        self.assertEqual(nome, "GOIANIA LESTE-17")

    def test_resolver_alimentador_case_insensitive(self):
        cod, nome = self.circuit.resolver_alimentador("goiania leste-10")
        self.assertEqual(cod, "5001992")
        self.assertEqual(nome, "GOIANIA LESTE-10")

    def test_resolver_alimentador_por_nome_parcial(self):
        cod, nome = self.circuit.resolver_alimentador("LESTE-17")
        self.assertEqual(cod, "5001996")
        self.assertEqual(nome, "GOIANIA LESTE-17")

    def test_resolver_alimentador_vazio_ou_none(self):
        with self.assertRaises(FeederNotFoundError):
            self.circuit.resolver_alimentador(None)

    def test_resolver_alimentador_inexistente(self):
        with self.assertRaises(FeederNotFoundError):
            self.circuit.resolver_alimentador("INEXISTENTE_XYZ")

    def test_resolver_alimentador_sem_metadados(self):
        cfg = SimulationConfig()
        circuit = CircuitManager(cfg)
        circuit.dict_ctmt_info = {}
        circuit.todos_ctmt_info = {}
        with self.assertRaises(FeederNotFoundError):
            circuit.resolver_alimentador("5001996")
if __name__ == "__main__":
    unittest.main()
