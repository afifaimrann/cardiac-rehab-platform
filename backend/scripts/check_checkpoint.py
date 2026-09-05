"""Inspect the reranker checkpoint on disk.

Three independent loaders returned identical wrong scores, which rules out the
loader and points at the file they all read. This checks the file itself: is the
classification head present, and do its weights look trained rather than
freshly initialised?

    python -m scripts.check_checkpoint
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

EXPECTED_MIN_BYTES = 2_000_000_000  # bge-reranker-v2-m3 is ~2.24 GB


def main() -> int:
    from huggingface_hub import try_to_load_from_cache
    from safetensors import safe_open

    path = try_to_load_from_cache(settings.RERANKER_MODEL, "model.safetensors")
    if not path or not Path(path).exists():
        print("model.safetensors not found in the cache.")
        return 1

    path = Path(path)
    size = path.stat().st_size
    print(f"file:  {path}")
    print(f"size:  {size / 1_073_741_824:.2f} GB ({size:,} bytes)")
    if size < EXPECTED_MIN_BYTES:
        print(f"  TRUNCATED: expected at least {EXPECTED_MIN_BYTES / 1_073_741_824:.1f} GB.")
        print("  The download did not finish. Delete the cache folder and refetch.")
        return 1
    print("  size looks complete")

    with safe_open(str(path), framework="pt") as f:
        keys = list(f.keys())
        head = [k for k in keys if "classifier" in k or "score" in k]

        print(f"\ntensors: {len(keys)}")
        print(f"classification head tensors: {head or 'NONE FOUND'}")
        if not head:
            print("\n  The scoring head is absent from this checkpoint.")
            print("  Any loader will attach a fresh, untrained head -- which is")
            print("  exactly the behaviour observed.")
            return 1

        print("\nhead weight statistics:")
        # Imported for the side effect of failing here, with a clear
        # traceback, rather than deep inside the tensor loop below.
        import torch  # noqa: F401

        for key in head:
            tensor = f.get_tensor(key).float()
            mean = tensor.mean().item()
            # std is undefined for a single element (out_proj.bias is scalar).
            std = tensor.std().item() if tensor.numel() > 1 else float("nan")
            largest = tensor.abs().max().item()
            shown = f"{std:.5f}" if std == std else "   n/a"
            print(f"  {key:34} mean={mean:+.5f}  std={shown}  max|w|={largest:.4f}")
            # A freshly initialised head is tightly centred on zero
            # (initializer_range=0.02); a trained one is not. Weight matrices
            # only -- biases are near zero even in a trained model.


        print("\n--- notes ---")
        print("  Weight statistics CANNOT tell a trained head from an untrained one.")
        print("  A head fine-tuned at a small learning rate stays close to its")
        print("  initialisation distribution, so std ~= initializer_range is normal")
        print("  for a working model. This script was written believing otherwise and")
        print("  produced a confident false diagnosis; the numbers above are context,")
        print("  not a verdict.")
        print("\n  What this script CAN establish: the file is present, complete, and")
        print("  contains the classification tensors at all. Everything else needs a")
        print("  behavioural test -- see scripts/rerank_sanity.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
