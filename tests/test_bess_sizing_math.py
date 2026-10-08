import unittest

def calcular_dimensionamento_bess(curva_p_kw: list[float]) -> dict:
    """Implementação pura da fórmula de dimensionamento de BESS adotada no projeto."""
    if not curva_p_kw:
        return {
            'p_rev_max_kw': 0.0,
            'e_rev_kwh': 0.0,
            'p_bess_kw': 0.0,
            'e_bess_kwh': 0.0,
            'autonomia_h': 0.0
        }

    p_rev_max_kw = max(0.0, -float(min(curva_p_kw)))
    e_rev_kwh = sum(-p * 0.25 for p in curva_p_kw if p < 0)
    p_bess_kw = p_rev_max_kw * 1.05
    e_bess_kwh = e_rev_kwh
    duracao_h = (e_bess_kwh / p_bess_kw) if p_bess_kw > 0 else 0.0

    return {
        'p_rev_max_kw': round(p_rev_max_kw, 2),
        'e_rev_kwh': round(e_rev_kwh, 2),
        'p_bess_kw': round(p_bess_kw, 2),
        'e_bess_kwh': round(e_bess_kwh, 2),
        'autonomia_h': round(duracao_h, 2)
    }

class TestBessSizingMath(unittest.TestCase):

    def test_bess_sizing_com_fluxo_reverso(self):
        # 4 passos de -2000 kW * 0.25h cada = 2000 kWh = 2.0 MWh
        curva = [500.0] * 40 + [-2000.0] * 4 + [1000.0] * 52
        res = calcular_dimensionamento_bess(curva)

        self.assertEqual(res['p_rev_max_kw'], 2000.0)
        self.assertEqual(res['e_rev_kwh'], 2000.0)
        self.assertEqual(res['p_bess_kw'], 2100.0)
        self.assertEqual(res['e_bess_kwh'], 2000.0)
        self.assertEqual(res['autonomia_h'], round(2000.0 / 2100.0, 2))

    def test_bess_sizing_sem_fluxo_reverso(self):
        curva = [100.0, 200.0, 300.0, 500.0, 200.0]
        res = calcular_dimensionamento_bess(curva)

        self.assertEqual(res['p_rev_max_kw'], 0.0)
        self.assertEqual(res['e_rev_kwh'], 0.0)
        self.assertEqual(res['p_bess_kw'], 0.0)
        self.assertEqual(res['e_bess_kwh'], 0.0)
        self.assertEqual(res['autonomia_h'], 0.0)

    def test_bess_sizing_curva_vazia(self):
        res = calcular_dimensionamento_bess([])
        self.assertEqual(res['p_rev_max_kw'], 0.0)
        self.assertEqual(res['e_rev_kwh'], 0.0)
        self.assertEqual(res['p_bess_kw'], 0.0)

if __name__ == "__main__":
    unittest.main()
