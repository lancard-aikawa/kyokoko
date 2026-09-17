# -*- coding: utf-8 -*-
"""clip.py と同じ絵を、画素の処理を ffmpeg に任せて作る版。

**clip.py は消さない。**この版が対応していないショットは clip.py に落ちる
（`supported()` が False を返す）。両方を並べて比べられる状態を保つため。

## なぜ作るか

clip.py は 1 フレームずつ Python で合成している。実測で 1080p30 が 10.7 fps、
つまり実時間の 1/3 の速さしか出ない。内訳は **PIL の合成が 68%、x264 が 32%**。
GPU はほぼ効かない（PIL も x264 も CPU）。ショット単位の並列化も 4 本で
1.94 倍で飽和する（メモリ帯域が天井）。カメラワークは「静止画の上を
パン・ズームする」だけなので、そこは ffmpeg のフィルタの仕事にできる。

## 作り

| 要素 | 担当 |
|---|---|
| カメラ | `zoompan`。smoothstep を式で書く |
| レイヤのアルファ | `sendcmd` + `colorchannelmixer=aa`。**毎フレーム clip.interp の値を流す** |
| 文字 | **PIL で全画面 RGBA を状態ごとに 1 枚**描いて `overlay`。見た目は clip.py と同一 |

文字を PIL に残しているのは、見た目を 1 ピクセルも変えたくないため。文字は
状態が変わるときだけ描き直せばよく（字幕1行につき1枚）、毎フレームの仕事から外れる。

## ffmpeg で踏んだ罠（どれも絵が黙って壊れる）

1. **`crop` の `w`/`h` は設定時に 1 回しか評価されない。**時刻 `t` が未定義の
   まま式の最後の分岐に落ち、scale 0.82 のはずが 0.64 になって 28% ズームイン
   していた。アニメーションには `zoompan` を使う。
2. **`zoompan` は入力のアスペクト比で切る。**マスターが 2126x1466（1.45）だと
   16:9 で切れず縦が詰まる。**マスターを右下パディングして 16:9 にしてから渡す。**
   右下に足すだけなら `Master.world()` の原点は動かない。
3. **`crop` の時刻変数は小文字 `t`、`blend`/`geq` は大文字 `T`。**間違えると
   `Unknown function in ...` で落ちる（これは気づける方）。
4. **`sendcmd=f=` に Windows の絶対パスを渡すとパースが壊れる。**`C:` の
   コロンがフィルタのオプション区切りに食われる。相対パスで渡すこと。
"""
import io
import json
import math
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw

import clip

# この版が扱えるショットの要素。ここに無いものが入っていたら clip.py に落とす。
SUPPORTED_KEYS = {
    "t0", "t1", "zoom", "camera", "layers", "notes", "type", "photo", "kb",
}


def supported(shot):
    """このショットを ffmpeg 版で描けるか。(可否, 理由) を返す。"""
    extra = set(shot.keys()) - SUPPORTED_KEYS
    if extra:
        return False, "未対応の要素: %s" % ", ".join(sorted(extra))
    if shot.get("type") == "photo":
        return False, "写真ショットは未対応"
    for ly in shot.get("layers", []):
        if ly.get("alpha") and len(ly["alpha"]) > 60:
            return False, "アルファのキーが多すぎる"
    return True, ""


def smooth_expr(keys, pick, t0, tv):
    """キーフレームを ffmpeg の式にする。clip.interp と同じ smoothstep。

    clip.interp は区間の外では端の値で止まるので、式も同じ形にする。
    """
    parts = []
    for a, b in zip(keys, keys[1:]):
        ta, tb = a[0] - t0, b[0] - t0
        va, vb = pick(a), pick(b)
        if tb <= ta:
            continue
        u = "((%s-%.6f)/%.6f)" % (tv, ta, tb - ta)
        s = "(%s*%s*(3-2*%s))" % (u, u, u)
        parts.append((tb, "(%.6f+(%.6f)*%s)" % (va, vb - va, s)))
    e = "(%.6f)" % pick(keys[-1])
    for tb, ex in reversed(parts):
        e = "if(lt(%s,%.6f),%s,%s)" % (tv, tb, ex, e)
    return e


def pad_16x9(img, bg=(24, 24, 24)):
    """zoompan は入力のアスペクト比で切るので、16:9 にしておく。

    右下に足すだけにする。左上に足すと Master.world() の原点がずれる。
    """
    w0, h0 = img.width, img.height
    w = max(w0, int(round(h0 * 16.0 / 9.0)))
    h = max(h0, int(round(w * 9.0 / 16.0)))
    if (w, h) == (w0, h0):
        return img
    out = Image.new("RGB", (w, h), bg)
    out.paste(img, (0, 0))
    return out


def subtitle_spans(timeline, t0, t1):
    """字幕を (開始, 終了, 行) の重ならない区間にする。

    clip.draw_subtitle は該当する行のうち **最後のもの**を描く。前の行の
    尻（end+0.25）と次の行の頭（start-0.15）は重なるので、そこは次が勝つ。
    静止画にする都合で、重なりを先にほどいておく。
    """
    rows = sorted(timeline, key=lambda r: r["start"])
    spans = []
    for i, r in enumerate(rows):
        a = r["start"] - 0.15
        b = r["end"] + 0.25
        if i + 1 < len(rows):
            b = min(b, rows[i + 1]["start"] - 0.15)
        a, b = max(a, t0), min(b, t1)
        if b - a > 1.0 / 60:
            spans.append((a, b, r))
    return spans


def draw_subtitle_layer(row, size):
    """字幕1行ぶんの透明な全画面。clip.draw_subtitle と同じ描き方。"""
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    f_sub, f_name = clip.font(42), clip.font(26)
    lines = clip.wrap(d, row["text"], f_sub, W - 140)
    band = 62 + len(lines) * 54
    d.rectangle([0, H - band, W, H], fill=(0, 0, 0, 150))
    col = clip.COLORS.get(row["speaker"], (255, 255, 255))
    clip.draw_text(d, (70, H - band + 14), row["speaker"], f_name, col + (255,), hw=2)
    for k, ln in enumerate(lines):
        clip.draw_text(d, (70, H - band + 50 + k * 54), ln, f_sub, (255, 255, 255, 255))
    return img


def draw_attrib_layer(size):
    """右上の出典。常時。"""
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    clip.draw_text(d, (W - 24, 22), clip.ATTRIB, clip.font(20, bold=False),
                   (255, 255, 255, 230), anchor="ra")
    return img


def draw_note_layer(text, size):
    """左上の札。フェードは ffmpeg 側で掛けるので、ここでは不透明で描く。"""
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    f = clip.font(38)
    tw = d.textlength(text, font=f)
    d.rectangle([60, 80, 60 + tw + 56, 80 + 68], fill=(0, 0, 0, 165))
    clip.draw_text(d, (88, 96), text, f, (255, 255, 255, 255), hw=2)
    return img


def _fmt(x):
    return ("%.6f" % x).rstrip("0").rstrip(".") or "0"


def render_shot(shot, timeline, out_path, size=(1920, 1080), fps=30, quiet=True):
    """1ショットを書き出す。clip.render_shot と同じ引数・同じ出力。"""
    W, H = size
    t0, t1 = shot["t0"], shot["t1"]
    dur = t1 - t0
    n = int(round(dur * fps))
    bounds = clip.shot_bounds(shot)
    smax = max([k[3] if len(k) > 3 else 1.0 for k in shot["camera"]])

    tmp = tempfile.mkdtemp(prefix="kokogallery_ff_", dir=".cache")
    rel = lambda p: os.path.relpath(p, os.getcwd()).replace("\\", "/")  # noqa: E731

    # --- レイヤのマスターを PNG に出す --------------------------------
    inputs, chains, alpha_cmds = [], [], []
    masters = []
    for k, ly in enumerate(shot["layers"]):
        m = clip.Master(ly["id"], shot["zoom"], bounds, int(W * smax), int(H * smax))
        p = os.path.join(tmp, "m%d.png" % k)
        pad_16x9(m.img).save(p)
        masters.append((ly, m, p, pad_16x9(m.img).width))

    base = masters[0][1]
    TV = "(on/%d)" % fps
    s_e = smooth_expr(shot["camera"], lambda kk: (kk[3] if len(kk) > 3 else 1.0), t0, TV)
    cx_e = smooth_expr(shot["camera"], lambda kk: base.world(kk[1], kk[2])[0], t0, TV)
    cy_e = smooth_expr(shot["camera"], lambda kk: base.world(kk[1], kk[2])[1], t0, TV)

    # PIL の Master.view は int(round(...)) で切る。zoompan は切り捨てなので、
    # 式の側を floor(x+0.5) に揃える。揃えないと 1〜2px ずれ、等高線の地図では
    # それが画素差として大きく出る（実測で平均 6〜8 → 2〜3 に落ちた）。
    cwr = "floor(%d*(%s)+0.5)" % (W, s_e)
    chr_ = "floor(%d*(%s)+0.5)" % (H, s_e)

    def cam_chain(iw):
        return ("zoompan=z='(%d/(%s))':x='floor((%s)-(%s)/2+0.5)':"
                "y='floor((%s)-(%s)/2+0.5)':d=1:s=%dx%d:fps=%d,setsar=1"
                % (iw, cwr, cx_e, cwr, cy_e, chr_, W, H, fps))

    for k, (ly, m, p, iw) in enumerate(masters):
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", _fmt(dur), "-i", p]
        if k == 0:
            chains.append("[0:v]%s[bg]" % cam_chain(iw))
            last = "bg"
            continue
        # アルファは毎フレーム clip.interp の値を sendcmd で流す。PIL と完全一致。
        keys = ly.get("alpha") or [[t0, 1.0]]
        cmd = []
        prev = None
        for i in range(n):
            t = t0 + i / float(fps)
            a = clip.interp(keys, t)[0]
            if prev is None or abs(a - prev) > 0.002:
                cmd.append("%s colorchannelmixer aa %s;" % (_fmt(i / float(fps)), _fmt(a)))
                prev = a
        cf = os.path.join(tmp, "a%d.txt" % k)
        io.open(cf, "w", encoding="utf-8").write("\n".join(cmd) + "\n")
        a0 = clip.interp(keys, t0)[0]
        chains.append("[%d:v]%s,format=rgba,sendcmd=f=%s,colorchannelmixer=aa=%s[L%d]"
                      % (k, cam_chain(iw), rel(cf), _fmt(a0), k))
        chains.append("[%s][L%d]overlay=format=auto[c%d]" % (last, k, k))
        last = "c%d" % k

    idx = len(masters)

    # --- 注記（タイトル中は伏せる。この版はタイトル未対応なので常に出す）---
    for j, nt in enumerate(shot.get("notes", [])):
        a, b = max(nt["from"], t0), min(nt["to"], t1)
        if b - a <= 1.0 / 60:
            continue
        p = os.path.join(tmp, "note%d.png" % j)
        draw_note_layer(nt["text"], size).save(p)
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", _fmt(dur), "-i", p]
        fd = min(0.4, (b - a) / 2.0)
        chains.append("[%d:v]format=rgba,fade=t=in:st=%s:d=%s:alpha=1,"
                      "fade=t=out:st=%s:d=%s:alpha=1[N%d]"
                      % (idx, _fmt(a - t0), _fmt(fd), _fmt(b - t0 - fd), _fmt(fd), j))
        chains.append("[%s][N%d]overlay=format=auto:enable='between(t,%s,%s)'[n%d]"
                      % (last, j, _fmt(a - t0), _fmt(b - t0), j))
        last = "n%d" % j
        idx += 1

    # --- 字幕 -----------------------------------------------------------
    for j, (a, b, row) in enumerate(subtitle_spans(timeline, t0, t1)):
        p = os.path.join(tmp, "sub%d.png" % j)
        draw_subtitle_layer(row, size).save(p)
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", _fmt(dur), "-i", p]
        chains.append("[%s][%d:v]overlay=format=auto:enable='between(t,%s,%s)'[s%d]"
                      % (last, idx, _fmt(a - t0), _fmt(b - t0), j))
        last = "s%d" % j
        idx += 1

    # --- 右上の出典 ------------------------------------------------------
    p = os.path.join(tmp, "attrib.png")
    draw_attrib_layer(size).save(p)
    inputs += ["-loop", "1", "-framerate", str(fps), "-t", _fmt(dur), "-i", p]
    chains.append("[%s][%d:v]overlay=format=auto[out]" % (last, idx))

    # zoompan の内部スケーリングは swscale。PIL は LANCZOS なので合わせる。
    # -sws_flags はグローバルに効く（zoompan にフィルタ固有の指定が無いため）。
    cmd = ["ffmpeg", "-v", "error", "-y", "-sws_flags", "lanczos"] + inputs + [
        "-filter_complex", ";".join(chains), "-map", "[out]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-frames:v", str(n), out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("ffmpeg が失敗しました:\n%s" % r.stderr[-2000:])
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    return out_path
