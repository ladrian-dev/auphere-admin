from nexus_api.core.metrics import counters


def test_counter_starts_at_zero():
    counters.reset()
    assert counters.get("foo") == 0


def test_counter_incr_default_one():
    counters.reset()
    counters.incr("foo")
    counters.incr("foo")
    assert counters.get("foo") == 2


def test_counter_incr_custom_amount():
    counters.reset()
    counters.incr("bar", 5)
    counters.incr("bar", 3)
    assert counters.get("bar") == 8


def test_counter_snapshot():
    counters.reset()
    counters.incr("a")
    counters.incr("b", 2)
    snap = counters.snapshot()
    assert snap == {"a": 1, "b": 2}


def test_counter_reset():
    counters.incr("x")
    counters.reset()
    assert counters.snapshot() == {}
