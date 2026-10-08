import unittest
from unittest.mock import patch, MagicMock
from src.simulation.config import SimulationConfig
from src.simulation.core.circuit import CircuitManager

class TestSimulationScopes(unittest.TestCase):

    def test_escopo_subestacao_inicializacao(self):
        cfg = SimulationConfig(escopo="SUBESTACAO")
        circuit = CircuitManager(cfg)
        self.assertGreater(len(circuit.trafos_subestacao), 0)
        self.assertGreater(len(circuit.dict_ctmt_info), 0)

    def test_escopo_trafo_at_filtragem(self):
        cfg = SimulationConfig(escopo="TRAFO_AT", alvo="TR1")
        circuit = CircuitManager(cfg)
        self.assertEqual(len(circuit.trafos_subestacao), 1)
        self.assertIn("GOL-S-TRF-TR1", circuit.trafos_subestacao[0])
        for cod, info in circuit.dict_ctmt_info.items():
            self.assertEqual(info.get("pasta_tr"), "TR1")

    def test_escopo_alimentador_filtragem(self):
        cfg = SimulationConfig(escopo="ALIMENTADOR", alvo="5001996")
        circuit = CircuitManager(cfg)
        self.assertEqual(len(circuit.trafos_subestacao), 0)
        self.assertEqual(len(circuit.dict_ctmt_info), 1)
        self.assertIn("5001996", circuit.dict_ctmt_info)

    def test_escopo_trafo_at_tr2(self):
        cfg = SimulationConfig(escopo="TRAFO_AT", alvo="TR2")
        circuit = CircuitManager(cfg)
        self.assertEqual(len(circuit.trafos_subestacao), 1)
        self.assertIn("TR2", circuit.trafos_subestacao[0])
        # O alimentador 5001996 pertence ao TR2
        self.assertIn("5001996", circuit.dict_ctmt_info)

if __name__ == "__main__":
    unittest.main()
