"""
Train a CRNN (Convolutional Recurrent Neural Network) for Florida plate OCR.

The output is an ONNX model that:
  - Is thread-safe (onnxruntime.InferenceSession)
  - Runs at ~5–20ms on Jetson GPU
  - Can replace PaddleOCR and restore async ThreadPoolExecutor in pilot.py

Usage:
    python scripts/ocr/train_crnn.py --labels data/ocr_training/labels.txt
    python scripts/ocr/train_crnn.py --labels data/ocr_training/labels.txt --epochs 150 --register
"""

import argparse
import random
import re
import sys
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

# ── Character set ──────────────────────────────────────────────────────────────

CHARS     = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
BLANK_IDX = 0
NUM_CLASSES = len(CHARS) + 1  # 37  (0 = CTC blank)

char_to_idx = {c: i + 1 for i, c in enumerate(CHARS)}
idx_to_char = {i + 1: c for i, c in enumerate(CHARS)}

# ── Image dimensions ───────────────────────────────────────────────────────────

IMG_H = 32
IMG_W = 128

# ── Dataset ────────────────────────────────────────────────────────────────────

class PlateDataset(Dataset):
    def __init__(self, samples: List[Tuple[str, str]], augment: bool = False):
        self.samples = samples
        self.augment = augment

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]

        img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            img = np.full((IMG_H, IMG_W), 255, dtype=np.uint8)

        if self.augment:
            img = self._augment(img)

        img = cv2.resize(img, (IMG_W, IMG_H), interpolation=cv2.INTER_CUBIC)
        img = img.astype(np.float32) / 255.0
        img = torch.tensor(img).unsqueeze(0)  # (1, H, W)

        target = torch.tensor([char_to_idx[c] for c in label], dtype=torch.long)
        return img, target, len(label)

    def _augment(self, img: np.ndarray) -> np.ndarray:
        # Random rotation ±5°
        if random.random() < 0.4:
            h, w = img.shape
            angle = random.uniform(-5, 5)
            M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            img = cv2.warpAffine(img, M, (w, h), borderValue=255)

        # Brightness / contrast jitter
        if random.random() < 0.5:
            alpha = random.uniform(0.7, 1.3)
            beta  = random.uniform(-20, 20)
            img = np.clip(alpha * img.astype(np.float32) + beta, 0, 255).astype(np.uint8)

        # Gaussian blur (simulates slight camera defocus)
        if random.random() < 0.3:
            ksize = random.choice([3, 5])
            img = cv2.GaussianBlur(img, (ksize, 1), 0)

        # Additive noise
        if random.random() < 0.2:
            noise = np.random.normal(0, 8, img.shape).astype(np.int16)
            img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        return img


def collate_fn(batch):
    imgs, targets, target_lens = zip(*batch)
    imgs        = torch.stack(imgs)
    target_lens = torch.tensor(target_lens, dtype=torch.long)
    targets_cat = torch.cat(targets)
    return imgs, targets_cat, target_lens


# ── Model ──────────────────────────────────────────────────────────────────────

class CRNN(nn.Module):
    """
    CNN feature extractor + BiLSTM sequence model + CTC output.

    Input : (N, 1, 32, 128)  — grayscale plate crop
    Output: (T, N, num_classes)  — log-softmax over 37 classes (0=blank)
    """

    def __init__(self, num_classes: int = NUM_CLASSES):
        super().__init__()

        # CNN — collapses height to 1, keeps width at 32 time steps
        self.cnn = nn.Sequential(
            # (N, 1, 32, 128) → (N, 32, 16, 64)
            nn.Conv2d(1, 32, 3, padding=1),
            nn.BatchNorm2d(32), nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),

            # → (N, 64, 8, 32)
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64), nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),

            # → (N, 128, 4, 32)
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128), nn.ReLU(inplace=True),
            nn.MaxPool2d((2, 1)),

            # → (N, 256, 2, 32)
            nn.Conv2d(128, 256, 3, padding=1),
            nn.BatchNorm2d(256), nn.ReLU(inplace=True),
            nn.MaxPool2d((2, 1)),

            # → (N, 256, 1, 32)
            nn.Conv2d(256, 256, 3, padding=1),
            nn.BatchNorm2d(256), nn.ReLU(inplace=True),
            nn.MaxPool2d((2, 1)),
        )

        # BiLSTM — 2 layers, hidden=128, bidirectional → output 256
        self.rnn = nn.LSTM(
            256, 128,
            num_layers=2, batch_first=False,
            bidirectional=True, dropout=0.3,
        )
        self.fc = nn.Linear(256, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.cnn(x)           # (N, 256, 1, 32)
        features = features.squeeze(2)   # (N, 256, 32)
        features = features.permute(2, 0, 1)  # (32, N, 256) — (T, N, C) for LSTM

        out, _ = self.rnn(features)      # (32, N, 256)
        out = self.fc(out)               # (32, N, num_classes)
        return torch.log_softmax(out, dim=2)


# ── CTC decode ─────────────────────────────────────────────────────────────────

def ctc_greedy_decode(log_probs: torch.Tensor) -> List[str]:
    """Greedy CTC decode. log_probs: (T, N, C) → list of N strings."""
    preds = log_probs.argmax(dim=2).permute(1, 0)  # (N, T)
    results = []
    for pred in preds:
        chars, prev = [], BLANK_IDX
        for p in pred.tolist():
            if p != prev and p != BLANK_IDX:
                chars.append(idx_to_char.get(p, "?"))
            prev = p
        results.append("".join(chars))
    return results


# ── Metrics ────────────────────────────────────────────────────────────────────

def levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[:], i
        for j in range(1, n + 1):
            dp[j] = prev[j - 1] if a[i - 1] == b[j - 1] else 1 + min(prev[j], dp[j - 1], prev[j - 1])
    return dp[n]


def compute_metrics(preds: List[str], targets: List[str]) -> Tuple[float, float]:
    total_chars = sum(len(t) for t in targets)
    total_edit  = sum(levenshtein(p, t) for p, t in zip(preds, targets))
    exact       = sum(p == t for p, t in zip(preds, targets))
    cer         = total_edit / max(total_chars, 1)
    exact_rate  = exact / len(targets) if targets else 0.0
    return cer, exact_rate


# ── Data loading ───────────────────────────────────────────────────────────────

def load_samples(labels_path: Path) -> List[Tuple[str, str]]:
    samples = []
    missing = 0
    with open(labels_path) as f:
        for line in f:
            line = line.rstrip("\n")
            if "\t" not in line:
                continue
            img_path, text = line.split("\t", 1)
            if text == "__SKIP__":
                continue
            text = re.sub(r"[^A-Z0-9]", "", text.upper())
            if len(text) < 2 or len(text) > 10:
                continue
            if not Path(img_path).exists():
                missing += 1
                continue
            samples.append((img_path, text))
    if missing:
        print(f"  ⚠  {missing} image paths in labels file not found on disk (skipped)")
    return samples


def decode_targets(targets_cat: torch.Tensor, target_lens: torch.Tensor) -> List[str]:
    result, pos = [], 0
    for l in target_lens.tolist():
        result.append("".join(idx_to_char[t] for t in targets_cat[pos:pos + l].tolist()))
        pos += l
    return result


# ── Training ───────────────────────────────────────────────────────────────────

def train(args):
    try:
        import mlflow
        use_mlflow = True
        mlflow.set_tracking_uri(args.mlflow_uri)
        mlflow.set_experiment("alpr-ocr-training")
    except ImportError:
        print("mlflow not available — training without experiment tracking")
        use_mlflow = False

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    samples = load_samples(Path(args.labels))
    if not samples:
        print("No labeled samples found. Run prelabel_with_paddleocr.py and review with label_crops.py first.")
        sys.exit(1)

    print(f"Samples: {len(samples)}")

    random.seed(42)
    random.shuffle(samples)
    split       = int(len(samples) * (1 - args.val_split))
    train_samp  = samples[:split]
    val_samp    = samples[split:]
    print(f"Train: {len(train_samp)}  Val: {len(val_samp)}")

    # num_workers=0: avoid forking CUDA contexts on Jetson (causes NvMapMemAlloc errors)
    train_dl = DataLoader(
        PlateDataset(train_samp, augment=True),
        batch_size=args.batch_size, shuffle=True,
        collate_fn=collate_fn, num_workers=0,
    )
    val_dl = DataLoader(
        PlateDataset(val_samp, augment=False),
        batch_size=args.batch_size, shuffle=False,
        collate_fn=collate_fn, num_workers=0,
    )

    model     = CRNN(NUM_CLASSES).to(device)
    criterion = nn.CTCLoss(blank=BLANK_IDX, reduction="mean", zero_infinity=True)
    optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=8, factor=0.5, verbose=True)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    best_cer      = float("inf")
    best_exact    = 0.0
    patience_ctr  = 0

    run_ctx = mlflow.start_run(run_name="crnn-florida-ocr") if use_mlflow else _nullctx()
    with run_ctx:
        if use_mlflow:
            mlflow.log_params({
                "epochs": args.epochs, "batch_size": args.batch_size,
                "lr": args.lr, "val_split": args.val_split,
                "train_samples": len(train_samp), "val_samples": len(val_samp),
                "img_h": IMG_H, "img_w": IMG_W, "architecture": "CRNN-BiLSTM",
            })

        for epoch in range(1, args.epochs + 1):

            # ── Train ──────────────────────────────────────────────────────────
            model.train()
            train_loss = 0.0
            for imgs, targets, target_lens in train_dl:
                imgs   = imgs.to(device)
                targets = targets.to(device)

                log_probs   = model(imgs)
                T, N        = log_probs.shape[:2]
                input_lens  = torch.full((N,), T, dtype=torch.long)

                loss = criterion(log_probs, targets, input_lens, target_lens)
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_dl)

            # ── Validate ───────────────────────────────────────────────────────
            model.eval()
            val_loss   = 0.0
            all_preds  = []
            all_tgts   = []

            with torch.no_grad():
                for imgs, targets, target_lens in val_dl:
                    imgs    = imgs.to(device)
                    targets = targets.to(device)

                    log_probs  = model(imgs)
                    T, N       = log_probs.shape[:2]
                    input_lens = torch.full((N,), T, dtype=torch.long)

                    val_loss  += criterion(log_probs, targets, input_lens, target_lens).item()
                    all_preds += ctc_greedy_decode(log_probs)
                    all_tgts  += decode_targets(targets.cpu(), target_lens.cpu())

            val_loss /= len(val_dl)
            cer, exact = compute_metrics(all_preds, all_tgts)
            scheduler.step(cer)

            if use_mlflow:
                mlflow.log_metrics({
                    "train_loss": train_loss, "val_loss": val_loss,
                    "val_cer": cer, "val_exact_match": exact,
                }, step=epoch)

            if epoch % 5 == 0 or epoch == 1:
                print(f"Epoch {epoch:3d}/{args.epochs}  "
                      f"loss={train_loss:.4f}  val_loss={val_loss:.4f}  "
                      f"CER={cer:.3f}  exact={exact:.1%}")
                for p, t in zip(all_preds[:3], all_tgts[:3]):
                    mark = "✓" if p == t else "✗"
                    print(f"    {mark}  pred={p!r:12s}  true={t!r}")

            if cer < best_cer:
                best_cer, best_exact = cer, exact
                patience_ctr = 0
                torch.save(model.state_dict(), out_dir / "best.pt")
            else:
                patience_ctr += 1
                if patience_ctr >= args.patience:
                    print(f"\nEarly stopping at epoch {epoch}")
                    break

        print(f"\nBest — CER={best_cer:.3f}  exact={best_exact:.1%}")

        # ── Export to ONNX ─────────────────────────────────────────────────────
        model.load_state_dict(torch.load(out_dir / "best.pt", map_location=device))
        model.eval()

        onnx_path = out_dir / "florida_plate_ocr.onnx"
        dummy = torch.zeros(1, 1, IMG_H, IMG_W, device=device)
        torch.onnx.export(
            model, dummy, str(onnx_path),
            input_names=["input"], output_names=["output"],
            dynamic_axes={"input": {0: "batch"}, "output": {1: "batch"}},
            opset_version=11,
        )
        print(f"Exported → {onnx_path}")

        # Quick ONNX sanity check
        import onnxruntime as ort
        sess = ort.InferenceSession(str(onnx_path),
                                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        test_in = np.zeros((1, 1, IMG_H, IMG_W), dtype=np.float32)
        sess.run(None, {"input": test_in})
        print("ONNX inference check: OK")

        if use_mlflow:
            mlflow.log_metrics({"best_val_cer": best_cer, "best_val_exact": best_exact})
            try:
                mlflow.log_artifact(str(onnx_path))
                mlflow.log_artifact(str(out_dir / "best.pt"))
            except Exception as e:
                print(f"⚠  MLflow artifact upload skipped ({e})")
                print("   (MinIO may not be running — model is saved locally)")

            if args.register:
                run_id = mlflow.active_run().info.run_id
                mv = mlflow.register_model(
                    f"runs:/{run_id}/{onnx_path.name}",
                    "alpr-florida-ocr-crnn",
                )
                print(f"Registered in MLflow: alpr-florida-ocr-crnn v{mv.version}")
                print(f"Promote to champion:")
                print(f"  mlflow models set-model-alias --model-name alpr-florida-ocr-crnn "
                      f"--alias champion --version {mv.version}")

        print(f"\nFiles in {out_dir}/")
        for p in sorted(out_dir.iterdir()):
            print(f"  {p.name}  ({p.stat().st_size // 1024} KB)")


# ── Null context manager for when mlflow is disabled ──────────────────────────

class _nullctx:
    def __enter__(self): return self
    def __exit__(self, *a): pass


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Train CRNN OCR model for Florida license plates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--labels",     default="data/ocr_training/labels.txt",
                        help="labels.txt from label_crops.py")
    parser.add_argument("--output-dir", default="models/crnn_florida",
                        help="Where to save best.pt and .onnx (default: models/crnn_florida)")
    parser.add_argument("--epochs",     type=int,   default=100)
    parser.add_argument("--batch-size", type=int,   default=32)
    parser.add_argument("--lr",         type=float, default=1e-3)
    parser.add_argument("--val-split",  type=float, default=0.15,
                        help="Fraction of data used for validation (default: 0.15)")
    parser.add_argument("--patience",   type=int,   default=20,
                        help="Early-stopping patience in epochs (default: 20)")
    parser.add_argument("--mlflow-uri", default="http://localhost:5000")
    parser.add_argument("--register",   action="store_true",
                        help="Register ONNX model in MLflow Model Registry after training")
    args = parser.parse_args()

    train(args)


if __name__ == "__main__":
    main()
