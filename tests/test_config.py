import unittest
from src.simulation.config import SimulationConfig

class TestSimulationConfig(unittest.TestCase):

    def test_config_initialization(self):
        config = SimulationConfig()
        self.assertEqual(config.passos_simulacao, 96)
        self.assertEqual(config.passo_minutos, 15)
        self.assertIsInstance(config.controle_tap_ativo, bool)
        self.assertEqual(config.fator_sobrecarga_alvo, 1.50)
        self.assertEqual(config.alimentador_alvo, "5001996")

    def test_cronograma_tap(self):
        config = SimulationConfig(controle_tap_ativo=True)
        # Horário normal (madrugada/dia)
        self.assertEqual(config.obter_tap_alvo(10), 1.000)
        self.assertEqual(config.obter_tap_alvo(70), 1.000)

        # Patamar 1 (18:30 às 19:15) -> Passos 74 a 77
        self.assertEqual(config.obter_tap_alvo(74), 1.050)
        self.assertEqual(config.obter_tap_alvo(77), 1.050)

        # Patamar 2 (19:30 às 20:15) -> Passos 78 a 81
        self.assertEqual(config.obter_tap_alvo(78), 1.100)
        self.assertEqual(config.obter_tap_alvo(81), 1.100)

        # Patamar 3 (20:30 às 21:15) -> Passos 82 a 85
        self.assertEqual(config.obter_tap_alvo(82), 1.050)
        self.assertEqual(config.obter_tap_alvo(85), 1.050)

        # Retorno ao normal a partir das 21:30 -> Passos >= 86
        self.assertEqual(config.obter_tap_alvo(86), 1.000)
        self.assertEqual(config.obter_tap_alvo(96), 1.000)

    def test_controle_tap_desativado(self):
        config = SimulationConfig(controle_tap_ativo=False)
        self.assertEqual(config.obter_tap_alvo(79), 1.000)

    def test_retrocompatibilidade_properties(self):
        config = SimulationConfig(alimentador_alvo="5002409", trafo_alvo="UNTRMT_123")
        self.assertEqual(config.alimentador_alvo_manual, "5002409")
        self.assertEqual(config.trafo_alvo_manual, "UNTRMT_123")

    def test_escopo_config(self):
        config_default = SimulationConfig()
        self.assertEqual(config_default.escopo, "SUBESTACAO")
        self.assertIsNone(config_default.alvo)

        config_tr = SimulationConfig(escopo="TRAFO_AT", alvo="TR2")
        self.assertEqual(config_tr.escopo, "TRAFO_AT")
        self.assertEqual(config_tr.alvo, "TR2")

        config_feeder = SimulationConfig(escopo="ALIMENTADOR", alvo="5001996")
        self.assertEqual(config_feeder.escopo, "ALIMENTADOR")
        self.assertEqual(config_feeder.alvo, "5001996")

if __name__ == "__main__":
    unittest.main()
