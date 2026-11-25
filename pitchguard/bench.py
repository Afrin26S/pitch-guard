"""How fast is the fast lane?   python -m pitchguard.bench"""
import statistics
import time

from .kb import load_calls, load_rulebook
from .rules import check_turn


def main(reps: int = 300):
    rb = load_rulebook()
    turns = [(t.text, c.scenario) for c in load_calls() for t in c.turns if t.speaker == "bot"]
    for text, sc in turns:                     # warm the regex cache
        check_turn(text, sc, rb)
    samples = []
    for _ in range(reps):
        for text, sc in turns:
            t0 = time.perf_counter()
            check_turn(text, sc, rb)
            samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    q = lambda p: samples[int(len(samples) * p) - 1]
    print(f"{len(samples)} checks | median {statistics.median(samples):.3f} ms | p95 {q(0.95):.3f} ms | p99 {q(0.99):.3f} ms | max {samples[-1]:.3f} ms")


if __name__ == "__main__":
    main()
