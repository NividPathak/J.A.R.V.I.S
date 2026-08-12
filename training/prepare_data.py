#!/usr/bin/env python3
"""Build the MLX fine-tuning corpus from the labelled JSONL.

    python training/prepare_data.py

Reads training/data/train_*.jsonl, verifies none of it collides with the
held-out test set, splits train/valid, and writes the chat-format files
mlx_lm.lora expects.

The assistant target is a bare label list — no confidence figure. Self-reported
confidence was the LLM baseline's weakest point (93 of 94 predictions cleared
the floor, so abstention never fired), and training a model to imitate a number
it cannot introspect would reproduce exactly that. The tuned router derives
confidence from token logprobs instead, which is the whole reason to expect
better calibration.

Short targets also keep generation to a handful of tokens, which is most of
where the latency win comes from.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.router.base import TUNED_SYSTEM as SYSTEM, Intent  # noqa: E402

DATA = Path(__file__).parent / "data"
TEST_SET = ROOT / "evals" / "routing" / "test.jsonl"
VALID_FRACTION = 0.12
SEED = 20260812


def normalise(text: str) -> str:
    return " ".join(text.lower().split()).strip(" .,?!")


def target(intents: list[str]) -> str:
    return ",".join(sorted(intents)) if intents else "none"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    rows: list[dict] = []
    for path in sorted(DATA.glob("train_*.jsonl")):
        loaded = load(path)
        rows.extend(loaded)
        print(f"  {path.name}: {len(loaded)}")

    valid_labels = {i.value for i in Intent}
    for row in rows:
        unknown = set(row["intents"]) - valid_labels
        if unknown:
            print(f"ERROR: unknown label {unknown} in {row['utterance']!r}")
            return 1

    # Leakage check. Training on the eval set makes every downstream number
    # meaningless, and it is silent — so it fails the build rather than warning.
    test = load(TEST_SET)
    test_keys = {normalise(r["utterance"]) for r in test}
    leaked = [r for r in rows if normalise(r["utterance"]) in test_keys]
    if leaked:
        print(f"\nERROR: {len(leaked)} training examples collide with the test set:")
        for row in leaked[:10]:
            print(f"  {row['utterance']!r}")
        return 1

    # Internal duplicates dilute the corpus without adding signal.
    seen, deduped = set(), []
    for row in rows:
        key = normalise(row["utterance"])
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    if len(deduped) < len(rows):
        print(f"  dropped {len(rows) - len(deduped)} internal duplicates")

    random.Random(SEED).shuffle(deduped)
    split = int(len(deduped) * (1 - VALID_FRACTION))
    parts = {"train": deduped[:split], "valid": deduped[split:]}

    for name, subset in parts.items():
        out = DATA / f"{name}.jsonl"
        with out.open("w") as f:
            for row in subset:
                f.write(json.dumps({"messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": row["utterance"]},
                    {"role": "assistant", "content": target(row["intents"])},
                ]}) + "\n")
        print(f"  wrote {out.name}: {len(subset)}")

    print(f"\nno leakage against {len(test)} held-out test examples")
    counts: dict[str, int] = {}
    for row in deduped:
        counts[row["tag"]] = counts.get(row["tag"], 0) + 1
    print("slices:", counts)
    label_counts: dict[str, int] = {}
    for row in deduped:
        for label in row["intents"] or ["none"]:
            label_counts[label] = label_counts.get(label, 0) + 1
    print("labels:", dict(sorted(label_counts.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
