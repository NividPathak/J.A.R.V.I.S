#!/usr/bin/env python3
"""Routing eval harness.

Establishes the baseline the Phase 4 fine-tune is measured against, and doubles
as the regression test for every routing change after that.

    python evals/run_routing.py                      # full set
    python evals/run_routing.py --tag multi          # one slice
    python evals/run_routing.py --save baseline.json # record a run
    python evals/run_routing.py --compare baseline.json

Exact set match is the headline number: a route is correct only if it predicts
*precisely* the right label set. Partial credit would flatter multi-intent
performance, which is exactly the slice that decides whether a 3B model is
usable here.
"""
import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from core.router.base import CONFIDENCE_FLOOR, Intent  # noqa: E402
from core.router.llm_router import LLMRouter  # noqa: E402

console = Console()
DATASET = Path(__file__).parent / "routing" / "test.jsonl"


def load(path: Path = DATASET, tag: str | None = None, limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if tag:
        rows = [r for r in rows if r.get("tag") == tag]
    return rows[:limit] if limit else rows


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def evaluate(router, rows: list[dict]) -> dict:
    results, latencies = [], []
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    for row in rows:
        expected = frozenset(Intent(i) for i in row["intents"])
        started = time.perf_counter()
        route = router.route(row["utterance"])
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)

        for intent in Intent:
            in_pred, in_gold = intent in route.intents, intent in expected
            if in_pred and in_gold:
                counts[intent.value]["tp"] += 1
            elif in_pred:
                counts[intent.value]["fp"] += 1
            elif in_gold:
                counts[intent.value]["fn"] += 1

        results.append({
            "utterance": row["utterance"],
            "tag": row.get("tag", "core"),
            "expected": sorted(str(i) for i in expected),
            "predicted": sorted(str(i) for i in route.intents),
            "correct": route.intents == expected,
            "confidence": route.confidence,
            "latency_ms": elapsed,
        })

    correct = [r for r in results if r["correct"]]
    per_intent = {name: prf(c["tp"], c["fp"], c["fn"]) for name, c in counts.items()}
    scored = [f for _, _, f in per_intent.values()]

    by_tag: dict[str, dict] = {}
    for tag in sorted({r["tag"] for r in results}):
        subset = [r for r in results if r["tag"] == tag]
        by_tag[tag] = {
            "n": len(subset),
            "accuracy": sum(r["correct"] for r in subset) / len(subset),
        }

    confident = [r for r in results if r["confidence"] >= CONFIDENCE_FLOOR]
    unsure = [r for r in results if r["confidence"] < CONFIDENCE_FLOOR]

    return {
        "router": router.name,
        "n": len(results),
        "exact_match": len(correct) / len(results) if results else 0.0,
        "macro_f1": statistics.fmean(scored) if scored else 0.0,
        "per_intent": per_intent,
        "by_tag": by_tag,
        "latency_ms": {
            "mean": statistics.fmean(latencies),
            "p95": sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0.0,
        },
        "calibration": {
            "confident_n": len(confident),
            "confident_accuracy": (
                sum(r["correct"] for r in confident) / len(confident) if confident else 0.0
            ),
            "unsure_n": len(unsure),
            "unsure_accuracy": (
                sum(r["correct"] for r in unsure) / len(unsure) if unsure else 0.0
            ),
        },
        "results": results,
    }


def report(m: dict, show_failures: int = 12) -> None:
    console.print(
        f"\n[bold]{m['router']}[/]  ·  n={m['n']}  ·  "
        f"[bold cyan]exact match {m['exact_match']:.1%}[/]  ·  macro-F1 {m['macro_f1']:.3f}  ·  "
        f"{m['latency_ms']['mean']:.0f}ms mean / {m['latency_ms']['p95']:.0f}ms p95\n"
    )

    slices = Table(title="By slice", header_style="bold cyan")
    slices.add_column("Slice")
    slices.add_column("n", justify="right")
    slices.add_column("Exact match", justify="right")
    for tag, stats in sorted(m["by_tag"].items(), key=lambda kv: -kv[1]["accuracy"]):
        colour = "green" if stats["accuracy"] >= 0.9 else "yellow" if stats["accuracy"] >= 0.7 else "red"
        slices.add_row(tag, str(stats["n"]), f"[{colour}]{stats['accuracy']:.1%}[/]")
    console.print(slices)

    per = Table(title="Per intent", header_style="bold cyan")
    per.add_column("Intent")
    for col in ("Precision", "Recall", "F1"):
        per.add_column(col, justify="right")
    for name, (p, r, f) in sorted(m["per_intent"].items(), key=lambda kv: -kv[1][2]):
        colour = "green" if f >= 0.9 else "yellow" if f >= 0.7 else "red"
        per.add_row(name, f"{p:.2f}", f"{r:.2f}", f"[{colour}]{f:.2f}[/]")
    console.print(per)

    cal = m["calibration"]
    console.print(
        f"\n[bold]Calibration[/]  confident (>={CONFIDENCE_FLOOR}): "
        f"{cal['confident_accuracy']:.1%} over {cal['confident_n']}  ·  "
        f"unsure: {cal['unsure_accuracy']:.1%} over {cal['unsure_n']}"
    )
    console.print("[dim]Confident accuracy should exceed unsure accuracy — that gap is what "
                  "makes abstention worth acting on.[/]")

    failures = [r for r in m["results"] if not r["correct"]]
    if failures:
        console.print(f"\n[bold red]{len(failures)} failures[/] (showing {min(show_failures, len(failures))}):")
        for r in failures[:show_failures]:
            console.print(
                f"  [dim]{r['tag']:9}[/] {r['utterance'][:52]:54} "
                f"want [green]{','.join(r['expected']) or 'none':28}[/] "
                f"got [red]{','.join(r['predicted']) or 'none':28}[/] @{r['confidence']:.2f}"
            )


def compare(current: dict, path: Path) -> None:
    old = json.loads(path.read_text())
    d_match = current["exact_match"] - old["exact_match"]
    d_f1 = current["macro_f1"] - old["macro_f1"]
    d_latency = current["latency_ms"]["mean"] - old["latency_ms"]["mean"]

    def arrow(d: float, higher_is_better: bool = True) -> str:
        good = d > 0 if higher_is_better else d < 0
        if abs(d) < 1e-9:
            return "[dim]=[/]"
        return f"[{'green' if good else 'red'}]{d:+.1%}[/]"

    console.print(f"\n[bold]vs {old['router']}[/] ({path.name})")
    console.print(f"  exact match  {old['exact_match']:.1%} -> {current['exact_match']:.1%}  {arrow(d_match)}")
    console.print(f"  macro-F1     {old['macro_f1']:.3f} -> {current['macro_f1']:.3f}  {arrow(d_f1)}")
    console.print(
        f"  latency      {old['latency_ms']['mean']:.0f}ms -> {current['latency_ms']['mean']:.0f}ms  "
        f"[{'green' if d_latency < 0 else 'red'}]{d_latency:+.0f}ms[/]"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Routing eval")
    ap.add_argument("--router", default="llm", choices=("llm", "tuned"),
                    help="which router implementation to evaluate")
    ap.add_argument("--adapter", help="LoRA adapter path (tuned router only)")
    ap.add_argument("--provider", help="ollama | anthropic (default: from settings)")
    ap.add_argument("--model", help="override model id")
    ap.add_argument("--tag", help="evaluate a single slice")
    ap.add_argument("--limit", type=int, help="first N examples only")
    ap.add_argument("--save", type=Path, help="write metrics to JSON")
    ap.add_argument("--compare", type=Path, help="diff against a saved run")
    args = ap.parse_args()

    rows = load(tag=args.tag, limit=args.limit)
    if not rows:
        console.print("[red]No examples matched.[/]")
        return 1

    if args.router == "tuned":
        from core.router.tuned_router import DEFAULT_ADAPTER, DEFAULT_MODEL, TunedRouter

        router = TunedRouter(
            model=args.model or DEFAULT_MODEL,
            adapter_path=args.adapter or DEFAULT_ADAPTER,
        )
    else:
        from core.llm import get_llm

        router = LLMRouter(get_llm(provider=args.provider, model=args.model))
    console.print(f"[dim]Evaluating {router.name} over {len(rows)} examples...[/]")

    metrics = evaluate(router, rows)
    report(metrics)

    if args.compare:
        compare(metrics, args.compare)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(metrics, indent=2))
        console.print(f"\n[dim]Saved to {args.save}[/]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
