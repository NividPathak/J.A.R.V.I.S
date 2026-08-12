#!/usr/bin/env python3
"""Is the difference between two eval runs real, or noise?

    python evals/significance.py                       # baseline vs tuned
    python evals/significance.py a.json b.json

Both runs score the same held-out examples, so the comparison is paired and
McNemar's test applies: only the examples where the two disagree carry any
information about which is better. Agreements — however many — say nothing.

This exists because a raw delta between two small runs is easy to over-read.
The first fine-tune here looked +5.3pp better and was not significant at n=94.
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402

console = Console()
RESULTS = Path(__file__).parent / "results"


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — behaves near 0 and 1, unlike the normal approximation."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half) * 100, (centre + half) * 100


def mcnemar_exact(n01: int, n10: int) -> float:
    """Two-sided exact binomial McNemar. Exact rather than chi-square because the
    discordant counts here are small enough that the approximation misleads."""
    n = n01 + n10
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(n01, n10) + 1)) / (2 ** n)
    return min(2 * tail, 1.0)


def required_n(n01: int, n10: int, current_n: int, target_p: float = 0.05) -> int | None:
    """Roughly how many test examples would make this difference detectable,
    holding the observed discordance ratio fixed."""
    if n10 <= n01:
        return None
    for scale in range(1, 21):
        if mcnemar_exact(n01 * scale, n10 * scale) < target_p:
            return current_n * scale
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Paired significance test on two eval runs")
    ap.add_argument("baseline", nargs="?", default=RESULTS / "llm-llama31-8b-v2.json", type=Path)
    ap.add_argument("candidate", nargs="?", default=RESULTS / "tuned-v2-multiweighted.json", type=Path)
    args = ap.parse_args()

    for path in (args.baseline, args.candidate):
        if not path.exists():
            console.print(f"[red]missing:[/] {path}")
            return 1

    base, cand = (json.loads(p.read_text()) for p in (args.baseline, args.candidate))
    b = {r["utterance"]: r["correct"] for r in base["results"]}
    c = {r["utterance"]: r["correct"] for r in cand["results"]}
    shared = sorted(set(b) & set(c))
    if not shared:
        console.print("[red]The two runs share no examples — not a paired comparison.[/]")
        return 1
    if len(shared) < len(b) or len(shared) < len(c):
        console.print(f"[yellow]Comparing the {len(shared)} examples both runs scored.[/]")

    n01 = sum(1 for k in shared if b[k] and not c[k])   # baseline only
    n10 = sum(1 for k in shared if not b[k] and c[k])   # candidate only
    bk, ck, n = sum(b[k] for k in shared), sum(c[k] for k in shared), len(shared)
    p = mcnemar_exact(n01, n10)

    console.print(f"\n[bold]{base['router']}[/]  vs  [bold]{cand['router']}[/]   n={n}\n")
    for label, correct, run in (("baseline", bk, base), ("candidate", ck, cand)):
        lo, hi = wilson(correct, n)
        console.print(f"  {label:9} {correct}/{n} = {correct / n:6.1%}   95% CI [{lo:.1f}, {hi:.1f}]")

    console.print(
        f"\n  discordant: candidate fixed [green]{n10}[/], broke [red]{n01}[/] "
        f"(agreements carry no information)"
    )
    verdict = "[green]significant[/]" if p < 0.05 else "[yellow]NOT significant[/]"
    console.print(f"  McNemar exact two-sided [bold]p = {p:.3f}[/]  -> {verdict} at 0.05")

    if p >= 0.05:
        needed = required_n(n01, n10, n)
        if needed:
            console.print(
                f"\n  [dim]At this discordance ratio, ~{needed} test examples would make a "
                f"difference this size detectable.[/]"
            )
        else:
            console.print("\n  [dim]The candidate is not ahead on discordant pairs; more data won't help.[/]")

    latency = cand["latency_ms"]["mean"] - base["latency_ms"]["mean"]
    console.print(
        f"\n  latency {base['latency_ms']['mean']:.0f}ms -> {cand['latency_ms']['mean']:.0f}ms "
        f"({latency:+.0f}ms) [dim]— a systematic measurement, no significance test needed[/]\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
