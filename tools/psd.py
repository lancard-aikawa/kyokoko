# -*- coding: utf-8 -*-
"""PSDTool 形式の立ち絵 PSD から、口を閉じた絵と開けた絵を書き出す。

  python tools/psd.py tree <file.psd>              レイヤー構成を見る
  python tools/psd.py shot <file.psd> <話者名> [出力先]  立ち絵2枚を書き出す

PSDTool の約束ごと:
  !名前   常に表示するレイヤー
  *名前   同じグループ内で 1 つだけ表示するラジオ選択

口パク用に、口グループの「通常」（閉じ）と「あ」（開き）を選んで 2 枚作る。
レイヤーの表示を切り替えて合成するだけで、絵そのものには手を加えない。
"""
import os
import sys

from PIL import Image
from psd_tools import PSDImage

sys.stdout.reconfigure(encoding="utf-8")

# 立ち絵の縦の割合。全身だと画面の隅で顔が小さすぎるので、頭から膝上で使う。
FRAME_KEEP = 0.62


def clean(name):
    return name.lstrip("!*").strip()


def walk(node, depth=0, limit=3):
    for l in node:
        print("%s%s %s" % ("  " * depth, "o" if l.visible else ".", l.name))
        if l.is_group() and depth < limit:
            walk(l, depth + 1, limit)


def find_group(node, name):
    for l in node:
        if l.is_group() and clean(l.name) == name:
            return l
        if l.is_group():
            g = find_group(l, name)
            if g:
                return g
    return None


def pick(group, want):
    """ラジオ選択のグループで、指定した名前だけを表示にする。"""
    hit = False
    for l in group:
        if l.name.startswith("*"):
            on = clean(l.name) == want
            l.visible = on
            hit = hit or on
    return hit


def shot(path, who, out_dir):
    psd = PSDImage.open(path)
    mouth = find_group(psd, "口")
    if mouth is None:
        sys.exit("口のグループが見つかりません。tree で構成を確認してください。")

    # 目・眉は通常、装飾は消す
    for gname, want in (("目", "通常"), ("眉", "通常")):
        g = find_group(psd, gname)
        if g:
            pick(g, want)
    etc = find_group(psd, "その他")
    if etc:
        for l in etc:
            l.visible = False

    os.makedirs(out_dir, exist_ok=True)
    made = {}
    for suffix, want in (("", "通常"), ("_open", "あ")):
        if not pick(mouth, want):
            sys.exit("口のレイヤー「%s」が見つかりません" % want)
        img = psd.composite(force=True).convert("RGBA")
        made[suffix] = img

    # 透明な余白を詰めてから、頭〜膝上だけを使う（絵は加工しない。見せ方の話）
    box = made[""].getchannel("A").getbbox()
    h = int((box[3] - box[1]) * FRAME_KEEP)
    box = (box[0], box[1], box[2], box[1] + h)
    for suffix, img in made.items():
        p = os.path.join(out_dir, "%s%s.png" % (who, suffix))
        img.crop(box).save(p)
        print("書き出し: %s  %s" % (p, img.crop(box).size))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "tree"
    if mode == "tree":
        walk(PSDImage.open(sys.argv[2]))
    elif mode == "shot":
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out = sys.argv[4] if len(sys.argv) > 4 else os.path.join(
            root, "episodes", "001-nagasaki-daikokumachi", "chara")
        shot(sys.argv[2], sys.argv[3], out)
    else:
        sys.exit(__doc__)
