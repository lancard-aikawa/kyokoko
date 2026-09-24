# -*- coding: utf-8 -*-
"""写真ショットに奥行きを付けて動かす（shots.py の写真ショットの `depth` キー）。

  深度の推定   tools/depth_estimate.py を uv で呼ぶ（torch はそちらの使い捨て環境に入る）
  絵を描く     tools/godot_depth/ を Godot の Movie Maker で書き出す
  重ね描き     字幕・札・出典はいままでどおり clip.render_photo_shot が PIL で焼く

どちらも episodes/<回>/out/depth/ にキャッシュする。深度は写真ごと、絵は
ショットの動きごと。絵は 1 ショット 140MB 前後あり、動きを詰めるたびに増えるので、
要らなくなったら out/depth/ ごと消してよい（次の build で作り直される）。

**写っている面しか使わない**ので、動かしすぎると物の境目が引き伸ばされる
（見えていない裏側を作らないため。作ると番組が断定していないものを絵が
断定してしまう）。既定値はめがね橋の飛び石の写真（第002回 3-3a）で、境目の
崩れが目立たないところまで詰めたもの。前進 0.7・横 0.3 までは試して、
手前の石の縁が波打った。

要るもの（どちらも depth を使う回だけ）:
  uv      https://docs.astral.sh/uv/
  Godot   4.x。PATH の godot か、環境変数 KOKO_GODOT に実行ファイルのパス
"""
import hashlib
import json
import os
import shutil
import subprocess
import uuid

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(HERE, "godot_depth")
ESTIMATE = os.path.join(HERE, "depth_estimate.py")

# カメラの動き。始点は常に撮影したカメラそのもので、終点までを smoothstep で動く。
DEFAULTS = {
    "dolly": 0.45,   # 前進量。前進は隠れた面をほとんど見せないので主役にする
    "shift": -0.15,  # 横移動（負で左）。境目の伸びと写真の外の露出に直結する
    "rise": 0.0,     # 上昇量
    "look": 0.0,     # 視線の上下（tan）。16:9 に切ると上下が落ちるので、残したい側へ振る
    "pivot": 10.0,   # 見つめる点までの距離。視差 0.12 前後（中景）がこのくらいになる
    "hfov": 60.0,    # 写真の水平画角（度）。Commons の写真は EXIF が無いことが多いので仮定値
    "view": 55.0,    # 出力の水平画角（度）。写真より狭くして、動いても端を見せない
    "near": 2.0,     # 最も近いものの距離
    "far": 33.0,     # 最も遠いもの（空・山）の距離
}


def godot_exe():
    p = (os.environ.get("KOKO_GODOT") or shutil.which("godot")
         or shutil.which("godot4"))
    if not p:
        raise SystemExit(
            "Godot が見つかりません。depth を使うショットには Godot 4 が要ります。\n"
            "  https://godotengine.org/download/ から入れて PATH に置くか、\n"
            "  環境変数 KOKO_GODOT に実行ファイルのパスを入れてください")
    return p


def _newer(a, b):
    """a が b より新しい（b が無い場合も含む）。"""
    return not os.path.exists(b) or os.path.getmtime(a) > os.path.getmtime(b)


def _publish_dir(tmp, final):
    """作り終えたフォルダを置く。並列のワーカが同じ写真を先に置いていたら捨てる。"""
    if os.path.exists(final):
        shutil.rmtree(final)
    try:
        os.rename(tmp, final)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)


def prepare(photo_path, ep_dir, key):
    """写真の深度を用意して、そのフォルダを返す。写真が変わっていなければ作り直さない。"""
    d = os.path.join(ep_dir, "out", "depth", os.path.splitext(key)[0])
    if not _newer(photo_path, os.path.join(d, "depth.f32")):
        return d
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv が見つかりません。深度の推定は uv で環境を作って動かします。\n"
                         "  https://docs.astral.sh/uv/getting-started/installation/")
    print("   深度を推定します: %s（初回はモデルと torch を取るので数分かかる）" % key)
    tmp = d + ".tmp-" + uuid.uuid4().hex[:8]
    subprocess.run([uv, "run", "--quiet", ESTIMATE, photo_path, tmp], check=True)
    _publish_dir(tmp, d)
    return d


def render(depth_dir, params, frames, u0, u1, size, fps):
    """Godot で背景だけを書き出し、AVI のパスを返す。同じ動きなら作り直さない。"""
    p = dict(DEFAULTS, **params)
    p.update(data_dir=depth_dir.replace("\\", "/"), frames=frames, u0=u0, u1=u1)
    # 深度を作り直したら絵も作り直す
    stamp = os.path.getmtime(os.path.join(depth_dir, "depth.f32"))
    h = hashlib.sha1(json.dumps([p, size, fps, stamp], sort_keys=True).encode()).hexdigest()[:12]
    avi = os.path.join(depth_dir, "shot_%s.avi" % h)
    if os.path.exists(avi):
        return avi

    tmp = os.path.join(depth_dir, "shot_%s.tmp-%s" % (h, uuid.uuid4().hex[:8]))
    pj = tmp + ".json"
    with open(pj, "w", encoding="utf-8") as f:
        json.dump(p, f)
    # Movie Maker は固定の刻みで 1 コマずつ描く。GPU が遅くてもコマは落ちない。
    # --quit-after は少し多めにし、読む側で frames 枚だけ使う
    r = subprocess.run([godot_exe(), "--path", PROJECT,
                        "--write-movie", tmp + ".avi", "--fixed-fps", str(fps),
                        "--resolution", "%dx%d" % size, "--quit-after", str(frames + 2),
                        "--", pj], capture_output=True, text=True, errors="replace")
    os.remove(pj)
    if r.returncode != 0 or not os.path.exists(tmp + ".avi"):
        raise RuntimeError("Godot の書き出しに失敗しました:\n%s" % (r.stdout + r.stderr)[-2000:])
    os.replace(tmp + ".avi", avi)
    return avi


def frames(avi, n, size):
    """AVI からちょうど n 枚のコマを取り出す。足りなければ最後のコマで埋める。"""
    W, H = size
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", avi, "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-s", "%dx%d" % size, "-"],
                         stdout=subprocess.PIPE)
    last = None
    got = 0
    try:
        while got < n:
            buf = p.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            last = Image.frombytes("RGB", size, buf)
            got += 1
            yield last.copy()
    finally:
        p.stdout.close()
        p.kill()
        p.wait()
    if last is None:
        raise RuntimeError("Godot の書き出しが空です: %s" % avi)
    for _ in range(n - got):
        yield last.copy()


def background(shot, photo_path, ep_dir, key, size, fps):
    """写真ショットの背景のコマを、ショットの頭から順に返す。"""
    t0, t1 = shot["t0"], shot["t1"]
    n = int(round((t1 - t0) * fps))
    # 動きはショット全体（span）で決める。構図確認は真ん中の数コマだけを描くので、
    # そのとき t0/t1 は一部分を指している
    a, b = shot["depth"].get("span") or (t0, t1)
    u0 = (t0 - a) / (b - a)
    u1 = (t0 + (n - 1) / float(fps) - a) / (b - a)
    params = {k: v for k, v in shot["depth"].items() if k != "span"}
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise SystemExit("depth に知らないキーがあります: %s（使えるのは %s）"
                         % (sorted(unknown), sorted(DEFAULTS)))
    d = prepare(photo_path, ep_dir, key)
    return frames(render(d, params, n, u0, u1, size, fps), n, size)
