import unittest
from src.simulation.exceptions import (
    SimulationError,
    CircuitLoadError,
    SimulationConvergenceError,
    FeederNotFoundError
)

class TestExceptions(unittest.TestCase):

    def test_exceptions_hierarchy(self):
        self.assertTrue(issubclass(CircuitLoadError, SimulationError))
        self.assertTrue(issubclass(SimulationConvergenceError, SimulationError))
        self.assertTrue(issubclass(FeederNotFoundError, SimulationError))
        self.assertTrue(issubclass(SimulationError, Exception))

    def test_raise_circuit_load_error(self):
        with self.assertRaises(CircuitLoadError) as ctx:
            raise CircuitLoadError("Arquivo DSS essencial ausente.")
        self.assertIn("Arquivo DSS essencial ausente.", str(ctx.exception))

    def test_raise_simulation_convergence_error(self):
        with self.assertRaises(SimulationConvergenceError) as ctx:
            raise SimulationConvergenceError("Fluxo divergiu no passo 15.")
        self.assertIn("Fluxo divergiu no passo 15.", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
