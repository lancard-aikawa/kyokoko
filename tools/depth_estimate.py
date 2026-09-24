# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["torch", "torchvision", "transformers", "pillow", "numpy"]
#
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
#
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# torchvision = { index = "pytorch-cpu" }
# ///
# -*- coding: utf-8 -*-
"""写真 1 枚から深度（相対的な視差）を推定し、Godot が読む形で書き出す。

  uv run tools/depth_estimate.py <写真> <出力フォルダ>

**依存はこのファイルの先頭に書いてあり、uv が使い捨ての環境を作る。**
torch は重い（CPU 版でも数百MB）ので、番組の本体（Pillow だけで動く）の
要件には入れない。tools/depth.py が必要なときだけこれを呼ぶ。

出力:
  photo.jpg     長辺 2048 に縮めた写真（テクスチャ用）
  depth.f32     float32 リトルエンディアン, 0=遠い 1=近い
  depth.json    {"w":..., "h":..., "model":...}
  depth_vis.png 目で確かめる用のグレースケール

モデルは Depth Anything V2 **Small**（Apache-2.0）。Base 以上は CC BY-NC で
非商用に限られるので使わない。
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision.transforms.functional import gaussian_blur
from transformers import pipeline

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"
DEPTH_W = 1024  # 深度マップの幅。Godot 側の格子（512）より細かければ足りる


def main(src, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    im = Image.open(src).convert("RGB")
    im.thumbnail((2048, 2048), Image.LANCZOS)
    im.save(out / "photo.jpg", quality=92)

    pipe = pipeline("depth-estimation", model=MODEL, device="cpu")
    pred = pipe(im)["predicted_depth"]  # モデル解像度の相対視差（大きいほど近い）
    if pred.dim() == 2:
        pred = pred[None]

    dw = DEPTH_W
    dh = round(DEPTH_W * im.height / im.width)
    d = torch.nn.functional.interpolate(
        pred[None].float(), size=(dh, dw), mode="bicubic", align_corners=False)
    # 境界の段差をわずかにならす。格子より細かい段差はギザギザの伸びとして出る
    d = gaussian_blur(d, kernel_size=[7, 7], sigma=[1.5, 1.5])[0, 0].numpy()

    # 外れ値に引っ張られないよう 1〜99 パーセンタイルで 0..1 に正規化
    lo, hi = np.percentile(d, [1, 99])
    d = np.clip((d - lo) / (hi - lo), 0.0, 1.0).astype("<f4")

    d.tofile(out / "depth.f32")
    (out / "depth.json").write_text(json.dumps({"w": dw, "h": dh, "model": MODEL}))
    Image.fromarray((d * 255).astype(np.uint8)).save(out / "depth_vis.png")
    print("photo %s  depth %dx%d  -> %s" % (im.size, dw, dh, out))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
