from rag_injection_lab.stats import fmt_cell, fmt_ci, percentile, wilson_interval


def test_wilson_limites_conhecidos():
    # k=0 em n=10: o limite superior precisa ficar bem abaixo de 50%
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0
    assert 0.2 < hi < 0.4
    # k=n: espelhado
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0
    assert 0.6 < lo < 0.8


def test_wilson_amostra_zero():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_intervalo_simetrico_na_medida():
    lo, hi = wilson_interval(5, 10)
    assert abs((lo + hi) / 2 - 0.5) < 0.01


def test_formatacao():
    assert fmt_cell(3, 4) == "3/4 (75%)"
    assert fmt_cell(0, 0) == "—"
    assert fmt_ci(1, 2) == "[9% – 91%]"


def test_percentil():
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([], 99) == 0.0
