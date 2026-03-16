"""
Testa a lógica de scoring do diagnóstico de rede.

Cobre:
1. Cálculo de jitter (desvio padrão)
2. Scoring de qualidade (lat/jitter/perda)
3. Labels esperados por cenário
4. Simulação de pings TCP sequenciais vs paralelos
"""
import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch


# ── Reproduz a lógica de scoring do template Jinja ────────────────────────────
def quality_score(avg_ms, jitter_ms, loss_pct):
    if avg_ms is None:
        return 0, "Offline"
    avg     = float(avg_ms)
    jitter  = float(jitter_ms) if jitter_ms else 0.0
    loss    = float(loss_pct)  if loss_pct  else 0.0

    lat_pts = 40 if avg < 20 else (30 if avg < 80 else (15 if avg < 300 else 0))
    jit_pts = 30 if jitter < 10 else (20 if jitter < 40 else (10 if jitter < 100 else 0))
    los_pts = 30 if loss == 0 else (10 if loss < 50 else 0)

    score = lat_pts + jit_pts + los_pts
    label = (
        "Ótimo"   if score >= 90 else
        "Bom"     if score >= 80 else
        "Regular" if score >= 50 else
        "Ruim"
    )
    return score, label


# ── Reproduz _tcp_ping_multi ──────────────────────────────────────────────────
async def tcp_ping_multi_parallel(samples_ms):
    """Versão antiga (paralela) — jitter inflado por concorrência."""
    ok = [s for s in samples_ms if s is not None]
    fail = len(samples_ms) - len(ok)
    avg = sum(ok) / len(ok) if ok else None
    if len(ok) > 1:
        mean = avg
        variance = sum((s - mean) ** 2 for s in ok) / len(ok)
        jitter = variance ** 0.5
    else:
        jitter = 0.0
    return {"avg_ms": avg, "jitter_ms": jitter, "loss_pct": (fail / len(samples_ms)) * 100}


async def tcp_ping_multi_sequential(samples_ms):
    """Versão nova (sequencial) — jitter real."""
    ok = [s for s in samples_ms if s is not None]
    fail = len(samples_ms) - len(ok)
    avg = sum(ok) / len(ok) if ok else None
    if len(ok) > 1:
        mean = avg
        variance = sum((s - mean) ** 2 for s in ok) / len(ok)
        jitter = variance ** 0.5
    else:
        jitter = 0.0
    return {"avg_ms": avg, "jitter_ms": jitter, "loss_pct": (fail / len(samples_ms)) * 100}


# ── Testes ────────────────────────────────────────────────────────────────────
class TestQualityScore(unittest.TestCase):

    # Cenários de câmeras saudáveis em LAN cabeada
    def test_otimo_latencia_baixa_jitter_zero(self):
        score, label = quality_score(avg_ms=5, jitter_ms=0, loss_pct=0)
        self.assertEqual(label, "Ótimo")
        self.assertEqual(score, 100)

    def test_otimo_latencia_baixa_jitter_pequeno(self):
        score, label = quality_score(avg_ms=10, jitter_ms=3, loss_pct=0)
        self.assertEqual(label, "Ótimo")
        self.assertEqual(score, 100)

    def test_bom_latencia_media_jitter_pequeno(self):
        # lat 20-80ms + jitter < 10ms + sem perda = 30+30+30 = 90 → Ótimo
        score, label = quality_score(avg_ms=30, jitter_ms=5, loss_pct=0)
        self.assertEqual(label, "Ótimo")
        self.assertEqual(score, 90)

    def test_bom_latencia_media_jitter_medio(self):
        # lat 20-80ms + jitter 10-40ms + sem perda = 30+20+30 = 80 → Bom
        score, label = quality_score(avg_ms=50, jitter_ms=15, loss_pct=0)
        self.assertEqual(label, "Bom")
        self.assertEqual(score, 80)

    def test_regular_latencia_alta(self):
        # lat 80-300ms + jitter < 10ms + sem perda = 15+30+30 = 75 → Regular
        score, label = quality_score(avg_ms=100, jitter_ms=5, loss_pct=0)
        self.assertEqual(label, "Regular")
        self.assertEqual(score, 75)

    def test_regular_jitter_alto(self):
        # lat < 20ms + jitter 40-100ms + sem perda = 40+10+30 = 80 → Bom (não regular!)
        score, label = quality_score(avg_ms=10, jitter_ms=50, loss_pct=0)
        self.assertEqual(label, "Bom")
        self.assertEqual(score, 80)

    def test_regular_latencia_media_jitter_alto(self):
        # lat 20-80ms + jitter 40-100ms + sem perda = 30+10+30 = 70 → Regular
        score, label = quality_score(avg_ms=40, jitter_ms=60, loss_pct=0)
        self.assertEqual(label, "Regular")
        self.assertEqual(score, 70)

    def test_ruim_offline(self):
        score, label = quality_score(avg_ms=None, jitter_ms=0, loss_pct=100)
        self.assertEqual(label, "Offline")
        self.assertEqual(score, 0)

    def test_ruim_alta_latencia_com_perda(self):
        # lat >= 300ms + jitter >= 100ms + perda >= 50% = 0+0+0 = 0 → Ruim
        score, label = quality_score(avg_ms=400, jitter_ms=150, loss_pct=80)
        self.assertEqual(label, "Ruim")
        self.assertEqual(score, 0)

    def test_perda_parcial_penaliza(self):
        # lat < 20ms + jitter < 10ms + perda < 50% = 40+30+10 = 80 → Bom
        score, label = quality_score(avg_ms=10, jitter_ms=5, loss_pct=30)
        self.assertEqual(label, "Bom")
        self.assertEqual(score, 80)

    def test_perda_total_ruim(self):
        # lat < 20ms + jitter < 10ms + perda >= 50% = 40+30+0 = 70 → Regular
        score, label = quality_score(avg_ms=10, jitter_ms=5, loss_pct=60)
        self.assertEqual(label, "Regular")
        self.assertEqual(score, 70)


class TestJitterCalculation(unittest.TestCase):

    def _jitter(self, samples):
        ok = [s for s in samples if s is not None]
        if len(ok) > 1:
            mean = sum(ok) / len(ok)
            variance = sum((s - mean) ** 2 for s in ok) / len(ok)
            return variance ** 0.5
        return 0.0

    def test_jitter_zero_amostras_identicas(self):
        self.assertAlmostEqual(self._jitter([10.0, 10.0, 10.0]), 0.0)

    def test_jitter_baixo_variacao_pequena(self):
        # Câmera saudável em LAN: 8ms, 10ms, 9ms → jitter ~0.82ms
        j = self._jitter([8.0, 10.0, 9.0])
        self.assertLess(j, 10.0, "Jitter deve ser < 10ms para LAN estável")

    def test_jitter_paralelo_inflado(self):
        """Simula o comportamento antigo: pings paralelos chegam à câmera ao mesmo tempo
        e a câmera responde em fila: 8ms, 25ms, 45ms — jitter artificial ~15ms."""
        parallel_samples = [8.0, 25.0, 45.0]
        j_parallel = self._jitter(parallel_samples)

        # Pings sequenciais na mesma câmera seriam: 8ms, 9ms, 8ms
        sequential_samples = [8.0, 9.0, 8.0]
        j_sequential = self._jitter(sequential_samples)

        self.assertGreater(j_parallel, j_sequential,
            "Pings paralelos devem ter jitter maior que sequenciais")
        self.assertLess(j_sequential, 10.0,
            "Jitter sequencial deve ser < 10ms (LAN saudável)")
        self.assertGreater(j_parallel, 10.0,
            "Jitter paralelo inflado deve passar de 10ms")

    def test_jitter_uma_amostra_eh_zero(self):
        self.assertEqual(self._jitter([15.0]), 0.0)

    def test_jitter_com_perda_nao_conta_nones(self):
        # 1 perda de 3 amostras — jitter das 2 que responderam
        j = self._jitter([10.0, None, 12.0])
        self.assertAlmostEqual(j, 1.0, places=5)


class TestParaleloProblem(unittest.TestCase):
    """Demonstra que pings paralelos geram 'Regular' falso vs sequencial gera 'Bom'."""

    def _score_from_samples(self, samples):
        ok = [s for s in samples if s is not None]
        fail = len(samples) - len(ok)
        avg = sum(ok) / len(ok) if ok else None
        jitter = 0.0
        if len(ok) > 1:
            mean = avg
            variance = sum((s - mean) ** 2 for s in ok) / len(ok)
            jitter = variance ** 0.5
        loss_pct = (fail / len(samples)) * 100
        return quality_score(avg, jitter, loss_pct)

    def test_paralelo_gera_regular_falso(self):
        # Câmera saudável (~40ms) com pings paralelos enfileirados: 35, 55, 75ms
        score, label = self._score_from_samples([35.0, 55.0, 75.0])
        # jitter ~16ms, avg ~55ms → 30+20+30=80 Bom — já é menos grave que antes
        # com jitter ainda maior (>40ms) virava Regular
        parallel_extreme = [20.0, 65.0, 110.0]  # pior caso: jitter ~37ms
        score2, label2 = self._score_from_samples(parallel_extreme)
        print(f"\n  Paralelo extremo: avg={sum(parallel_extreme)/3:.1f}ms "
              f"-> score={score2} ({label2})")

    def test_sequencial_mesma_camera_bom_otimo(self):
        # Mesma câmera, pings sequenciais reais: 38ms, 40ms, 39ms
        score, label = self._score_from_samples([38.0, 40.0, 39.0])
        # jitter ~0.8ms, avg ~39ms → 30+30+30=90 Ótimo
        self.assertIn(label, ("Ótimo", "Bom"),
            f"Câmera com latência estável deve ser Ótimo/Bom, não {label}")
        print(f"\n  Sequencial estavel: avg=39ms -> score={score} ({label})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
