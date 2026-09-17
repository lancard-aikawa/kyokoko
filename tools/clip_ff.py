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
5. **`overlay` にフレーム番号の変数 `on` は無い。**`zoompan` にはある。
   同じ式を使い回そうとして `Undefined constant` で落ちた。`overlay` の
   位置は時刻 `t` で書く。
6. **`drawbox` の式の `t` は「時刻」ではなく「線の太さ」。**カウントダウンの
   バーの幅に時刻を書いたら、幅がでたらめになって画面の右端まで伸びた。
   黙って壊れるのではなく派手に壊れる分ましだが、名前が同じなので気づき
   にくい。幅は `sendcmd` で毎フレーム流す（レイヤのアルファと同じ手）。

## 重ねる絵は中身のある矩形に切る

全画面の PNG をそのまま重ねると、50秒のショットに字幕が20枚あるとき
`overlay` が 1920x1080 を20本ぶん毎フレーム舐めることになる。字幕は下の帯、
注記は左上の箱、出典は右上にしか無いので、`crop_to_ink()` で切ってから
位置を指定する。クレジットのショットで 76.4秒 -> 58.6秒。
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
    "t0", "t1", "zoom", "camera", "layers", "notes", "labels", "type", "photo", "kb",
    "title", "question", "credits",
}


def supported(shot):
    """このショットを ffmpeg 版で描けるか。(可否, 理由) を返す。"""
    extra = set(shot.keys()) - SUPPORTED_KEYS
    if extra:
        return False, "未対応の要素: %s" % ", ".join(sorted(extra))
    q = shot.get("question")
    if q and q.get("think"):
        # 札のフェード（0.45秒）の外に考える時間があるなら、バーの色を
        # フェードと掛け合わせる必要がある。drawbox の色は式を取れないので、
        # その組み合わせだけ PIL に落とす。いまの回はすべて内側に収まっている。
        a, b = q["from"], q["to"]
        th = q["think"]
        if not (a + 0.45 <= th[0] and th[1] <= b - 0.45):
            return False, "考える時間が札のフェードに掛かっている"
    if shot.get("type") == "photo":
        return True, ""
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


def draw_label_sprite(lb):
    """ラベル（点＋文字）を1枚の小さな絵にする。

    返すのは (画像, 点の位置からの左上オフセット)。カメラで動くので、
    毎フレーム描き直す代わりに overlay の x/y を式で動かす。
    フェードは ffmpeg 側で掛けるので、ここでは開ききった状態で描く。
    """
    f = clip.font(34)
    r = lb.get("r", 9)
    dx, dy = lb.get("offset", (18, -20))
    anchor = lb.get("anchor", "la")
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tb = probe.textbbox((dx, dy), lb["text"], font=f, anchor=anchor, stroke_width=3)
    x0 = min(-r - 3, tb[0]) - 2
    y0 = min(-r - 3, tb[1]) - 2
    x1 = max(r + 3, tb[2]) + 2
    y1 = max(r + 3, tb[3]) + 2
    img = Image.new("RGBA", (int(x1 - x0), int(y1 - y0)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    ox, oy = -x0, -y0
    d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=clip.ACCENT + (235,),
              outline=(255, 255, 255, 235), width=3)
    clip.draw_text(d, (ox + dx, oy + dy), lb["text"], f, (255, 255, 255, 255),
                   anchor=anchor)
    return img, (x0, y0)


def photo_credit(meta):
    return "写真: %s ／ %s（Wikimedia Commons）" % (meta.get("author") or "不明",
                                                 meta.get("license") or "?")


def draw_subtitle_layer(row, size, cred=None):
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
    if cred:
        # 写真ショットの出典は字幕帯の上。帯の高さが行数で変わるので、
        # 字幕と同じ絵に描いてしまう（別レイヤにすると位置を追えない）。
        clip.draw_text(d, (W - 24, H - band - 30), cred, clip.font(20, bold=False),
                       (255, 255, 255, 235), anchor="ra")
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


def draw_title_layer(ti, size):
    """タイトル。フェードは ffmpeg 側で掛けるので、ここは開ききった状態。"""
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, ti.get("dim", 130)))
    f_main = clip.font(ti.get("size", 96))
    f_sub = clip.font(ti.get("subsize", 40))
    cy = int(H * ti.get("y", 0.42))
    clip.draw_text(d, (W // 2, cy), ti["main"], f_main, (255, 255, 255, 255),
                   anchor="mm", hw=4)
    if ti.get("sub"):
        tw = max(d.textlength(ti["main"], font=f_main),
                 d.textlength(ti["sub"], font=f_sub)) + 40
        y = cy + ti.get("size", 96) // 2 + 26
        d.line([W // 2 - tw / 2, y, W // 2 + tw / 2, y], fill=(255, 255, 255, 200), width=2)
        clip.draw_text(d, (W // 2, y + 34), ti["sub"], f_sub, (255, 255, 255, 255),
                       anchor="mm", hw=3)
    return img


def draw_credits_layer(cr, size):
    """エンディングのクレジット。"""
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, cr.get("dim", 165)))
    f_h, f_b = clip.font(30), clip.font(25, bold=False)
    x, y = int(W * 0.17), int(H * 0.17)
    for kind, text in cr["lines"]:
        if kind == "h":
            y += 16
            clip.draw_text(d, (x, y), text, f_h, (255, 255, 255, 255), hw=3)
            y += 42
        elif kind == "gap":
            y += 18
        else:
            clip.draw_text(d, (x + 26, y), text, f_b, (232, 232, 228, 255), hw=2)
            y += 34
    return img


def question_box(q, size):
    """クエスチョンの札の位置。clip.draw_question と同じ計算。"""
    W, H = size
    lines = q["text"] if isinstance(q["text"], list) else [q["text"]]
    f_q = clip.font(q.get("size", 60))
    lh = q.get("size", 60) + 22
    box_h = 150 + lh * len(lines)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    box_w = int(max([probe.textlength(x, font=f_q) for x in lines]) + 140)
    box_w = max(box_w, 640)
    x0 = (W - box_w) // 2
    y0 = int(H * q.get("y", 0.30))
    return lines, f_q, lh, box_w, box_h, x0, y0


def draw_question_layer(q, size, with_bar_bg):
    """クエスチョンの札。バーの「残り」は drawbox で描くので、ここには入れない。

    バーの下地（薄い白）は考える時間のあいだだけ出るので、別の絵にする。
    """
    W, H = size
    lines, f_q, lh, box_w, box_h, x0, y0 = question_box(q, size)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    if with_bar_bg:
        bx0, bx1 = x0 + 40, x0 + box_w - 40
        by = y0 + box_h - 36
        d.rectangle([bx0, by, bx1, by + 8], fill=(255, 255, 255, 46))
        return img
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, q.get("dim", 96)))
    d.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(12, 14, 20, 228))
    d.rectangle([x0, y0, x0 + box_w, y0 + box_h], outline=(214, 176, 66, 255), width=3)
    d.rectangle([x0, y0, x0 + box_w, y0 + 62], fill=(214, 176, 66, 240))
    clip.draw_text(d, (x0 + box_w // 2, y0 + 31), q.get("tag", "クエスチョン"),
                   clip.font(34), (16, 18, 24, 255), anchor="mm", hw=0)
    for i, ln in enumerate(lines):
        clip.draw_text(d, (x0 + box_w // 2, y0 + 96 + lh // 2 + lh * i), ln, f_q,
                       (255, 255, 255, 255), anchor="mm", hw=3)
    return img


def crop_to_ink(img):
    """透明でない範囲だけに切り詰めて、(切った絵, 左上の位置) を返す。

    重ねる絵を全画面のまま渡すと、overlay がフレームごとに 1920x1080 を
    何枚も舐めることになる。字幕は下の帯だけ、注記は左上の箱だけなので、
    そこだけ渡せば重ね合わせの量が桁で減る。
    """
    bb = img.getbbox()
    if not bb:
        return None, (0, 0)
    return img.crop(bb), (bb[0], bb[1])


def _fmt(x):
    return ("%.6f" % x).rstrip("0").rstrip(".") or "0"


def render_shot(shot, timeline, out_path, size=(1920, 1080), fps=30, quiet=True,
                photos=None):
    """1ショットを書き出す。clip.render_shot / render_photo_shot と同じ出力。"""
    W, H = size
    t0, t1 = shot["t0"], shot["t1"]
    dur = t1 - t0
    n = int(round(dur * fps))
    is_photo = shot.get("type") == "photo"

    tmp = tempfile.mkdtemp(prefix="kokogallery_ff_", dir=".cache")

    def rel(q):
        return os.path.relpath(q, os.getcwd()).replace(chr(92), "/")

    inputs, chains = [], []
    state = {"idx": 0}

    def add_input(path):
        """入力を1本足して、その番号を返す。"""
        inputs.extend(["-loop", "1", "-framerate", str(fps), "-t", _fmt(dur), "-i", path])
        state["idx"] += 1
        return state["idx"] - 1

    ti = shot.get("title")
    # clip.title_active と同じ。タイトルが出ている間はラベルと注記を伏せる。
    hide = ("" if not ti else
            "*not(between(t,%s,%s))" % (_fmt(ti["from"] - t0 - 0.5),
                                        _fmt(ti["to"] - t0 + 0.5)))
    cred = None
    if is_photo:
        last = _bg_photo(shot, photos, size, fps, tmp, add_input, chains)
        cred = photo_credit(photos[shot["photo"]])
    else:
        last, screen = _bg_map(shot, size, fps, tmp, add_input, chains, rel, n, t0)

        # --- ラベル。カメラで動くので、スプライトを式で運ぶ ----------------
        for j, lb in enumerate(shot.get("labels", [])):
            img, off = draw_label_sprite(lb)
            q = os.path.join(tmp, "lb%d.png" % j)
            img.save(q)
            i = add_input(q)
            a = max(lb["from"], t0)
            sx, sy = screen(lb["lat"], lb["lon"])
            chains.append("[%d:v]format=rgba,fade=t=in:st=%s:d=0.6:alpha=1[B%d]"
                          % (i, _fmt(a - t0), j))
            chains.append("[%s][B%d]overlay=x='(%s)+(%.1f)':y='(%s)+(%.1f)':"
                          "format=auto:eval=frame:enable='gte(t,%s)%s'[b%d]"
                          % (last, j, sx, off[0], sy, off[1], _fmt(a - t0), hide, j))
            last = "b%d" % j

    # --- 注記 -------------------------------------------------------------
    for j, nt in enumerate(shot.get("notes", [])):
        a, b = max(nt["from"], t0), min(nt["to"], t1)
        if b - a <= 1.0 / 60:
            continue
        img, at = crop_to_ink(draw_note_layer(nt["text"], size))
        if img is None:
            continue
        q = os.path.join(tmp, "note%d.png" % j)
        img.save(q)
        i = add_input(q)
        fd = min(0.4, (b - a) / 2.0)
        chains.append("[%d:v]format=rgba,fade=t=in:st=%s:d=%s:alpha=1,"
                      "fade=t=out:st=%s:d=%s:alpha=1[N%d]"
                      % (i, _fmt(a - t0), _fmt(fd), _fmt(b - t0 - fd), _fmt(fd), j))
        chains.append("[%s][N%d]overlay=x=%d:y=%d:format=auto:"
                      "enable='between(t,%s,%s)%s'[n%d]"
                      % (last, j, at[0], at[1], _fmt(a - t0), _fmt(b - t0), hide, j))
        last = "n%d" % j

    # --- 字幕（写真ショットでは出典を同じ絵に入れる）------------------------
    spans = subtitle_spans(timeline, t0, t1)
    for j, sp in enumerate(spans):
        a, b, row = sp
        img, at = crop_to_ink(draw_subtitle_layer(row, size, cred))
        if img is None:
            continue
        q = os.path.join(tmp, "sub%d.png" % j)
        img.save(q)
        i = add_input(q)
        chains.append("[%s][%d:v]overlay=x=%d:y=%d:format=auto:"
                      "enable='between(t,%s,%s)'[s%d]"
                      % (last, i, at[0], at[1], _fmt(a - t0), _fmt(b - t0), j))
        last = "s%d" % j

    if is_photo:
        # 字幕が出ていない間の写真クレジット（帯が無いので画面の下端寄り）
        gaps, prev = [], t0
        for a, b, _row in spans:
            if a - prev > 1.0 / 60:
                gaps.append((prev, a))
            prev = b
        if t1 - prev > 1.0 / 60:
            gaps.append((prev, t1))
        if gaps:
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(img, "RGBA")
            clip.draw_text(d, (W - 24, H - 30), cred, clip.font(20, bold=False),
                           (255, 255, 255, 235), anchor="ra")
            q = os.path.join(tmp, "cred.png")
            img.save(q)
            i = add_input(q)
            en = "+".join("between(t,%s,%s)" % (_fmt(a - t0), _fmt(b - t0))
                          for a, b in gaps)
            chains.append("[%s][%d:v]overlay=format=auto:enable='%s'[out]"
                          % (last, i, en))
            last = "out"
    else:
        # 地図は右上に地理院の出典。写真ショットには出さない（clip.py と同じ）
        img, at = crop_to_ink(draw_attrib_layer(size))
        q = os.path.join(tmp, "attrib.png")
        img.save(q)
        i = add_input(q)
        chains.append("[%s][%d:v]overlay=x=%d:y=%d:format=auto[A]"
                      % (last, i, at[0], at[1]))
        last = "A"

    # --- クエスチョンの札 ---------------------------------------------
    q = shot.get("question")
    if q:
        a, b = max(q["from"], t0), min(q["to"], t1)
        card = os.path.join(tmp, "q.png")
        draw_question_layer(q, size, False).save(card)
        i = add_input(card)
        chains.append("[%d:v]format=rgba,fade=t=in:st=%s:d=0.45:alpha=1,"
                      "fade=t=out:st=%s:d=0.45:alpha=1[Q]"
                      % (i, _fmt(a - t0), _fmt(b - t0 - 0.45)))
        chains.append("[%s][Q]overlay=format=auto:enable='between(t,%s,%s)'[q]"
                      % (last, _fmt(a - t0), _fmt(b - t0)))
        last = "q"
        th = q.get("think")
        if th:
            ta, tb = th[0] - t0, th[1] - t0
            bg = os.path.join(tmp, "qbar.png")
            draw_question_layer(q, size, True).save(bg)
            i = add_input(bg)
            chains.append("[%s][%d:v]overlay=format=auto:enable='between(t,%s,%s)'[qb]"
                          % (last, i, _fmt(ta), _fmt(tb)))
            last = "qb"
            _l, _f, _lh, box_w, box_h, x0, y0 = question_box(q, size)
            bx0, bx1 = x0 + 40, x0 + box_w - 40
            by = y0 + box_h - 36
            # **drawbox の式の t は時刻ではなく線の太さ。**ここに時刻を書くと
            # 幅がでたらめになり、バーが画面外まで伸びる（実際に踏んだ）。
            # 幅は sendcmd で毎フレーム流す。
            cmds, prev = [], None
            for f in range(n):
                tt = f / float(fps)
                if tt < ta or tt > tb:
                    continue
                wpx = int(round((bx1 - bx0) * (1.0 - (tt - ta) / max(0.001, tb - ta))))
                if prev is None or wpx != prev:
                    cmds.append("%s drawbox w %d;" % (_fmt(tt), wpx))
                    prev = wpx
            cf = os.path.join(tmp, "qbar.txt")
            io.open(cf, "w", encoding="utf-8").write(chr(10).join(cmds) + chr(10))
            chains.append("[%s]sendcmd=f=%s,drawbox=x=%d:y=%d:w=%d:h=8:"
                          "color=0xD6B042@0.941:t=fill:enable='between(t,%s,%s)'[qf]"
                          % (last, rel(cf), bx0, by, bx1 - bx0, _fmt(ta), _fmt(tb)))
            last = "qf"

    # --- タイトル -------------------------------------------------------
    if ti:
        a, b = ti["from"] - t0, ti["to"] - t0
        p2 = os.path.join(tmp, "title.png")
        draw_title_layer(ti, size).save(p2)
        i = add_input(p2)
        chains.append("[%d:v]format=rgba,fade=t=in:st=%s:d=0.7:alpha=1,"
                      "fade=t=out:st=%s:d=0.7:alpha=1[T]"
                      % (i, _fmt(a), _fmt(b - 0.7)))
        chains.append("[%s][T]overlay=format=auto:enable='between(t,%s,%s)'[ti]"
                      % (last, _fmt(a), _fmt(b)))
        last = "ti"

    # --- クレジット ------------------------------------------------------
    cr = shot.get("credits")
    if cr:
        a, b = cr["from"] - t0, cr["to"] - t0
        p2 = os.path.join(tmp, "credits.png")
        draw_credits_layer(cr, size).save(p2)
        i = add_input(p2)
        chains.append("[%d:v]format=rgba,fade=t=in:st=%s:d=0.8:alpha=1,"
                      "fade=t=out:st=%s:d=0.8:alpha=1[C]"
                      % (i, _fmt(a), _fmt(b - 0.8)))
        chains.append("[%s][C]overlay=format=auto:enable='between(t,%s,%s)'[cr]"
                      % (last, _fmt(a), _fmt(b)))
        last = "cr"

    if last != "out":
        chains.append("[%s]null[out]" % last)

    # zoompan の内部スケーリングは swscale。PIL は LANCZOS なので合わせる。
    cmd = ["ffmpeg", "-v", "error", "-y", "-sws_flags", "lanczos"] + inputs + [
        "-filter_complex", ";".join(chains), "-map", "[out]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-frames:v", str(n), out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("ffmpeg が失敗しました:" + chr(10) + r.stderr[-2000:])
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    return out_path


def _bg_map(shot, size, fps, tmp, add_input, chains, rel, n, t0):
    """地図ショットの下地。返すのは (最後の名札, 画面座標の式を返す関数)。"""
    W, H = size
    bounds = clip.shot_bounds(shot)
    smax = max([k[3] if len(k) > 3 else 1.0 for k in shot["camera"]])
    masters = []
    for k, ly in enumerate(shot["layers"]):
        m = clip.Master(ly["id"], shot["zoom"], bounds, int(W * smax), int(H * smax))
        img = pad_16x9(m.img)
        q = os.path.join(tmp, "m%d.png" % k)
        img.save(q)
        masters.append((ly, m, q, img.width))

    base = masters[0][1]
    # zoompan の時刻変数。on/fps でも動くが、長いショットで実測 0.1 秒ほど
    # ずれた（31秒のズームの終盤で倍率が食い違う）。time は入力フレームの
    # PTS そのものなので、こちらのほうが PIL の t と素直に一致する。
    TV = "time"
    s_e = smooth_expr(shot["camera"], lambda kk: (kk[3] if len(kk) > 3 else 1.0), t0, TV)
    cx_e = smooth_expr(shot["camera"], lambda kk: base.world(kk[1], kk[2])[0], t0, TV)
    cy_e = smooth_expr(shot["camera"], lambda kk: base.world(kk[1], kk[2])[1], t0, TV)

    # PIL の Master.view は int(round(...)) で切る。zoompan は切り捨てなので
    # 式の側を floor(x+0.5) に揃える。揃えないと 1〜2px ずれ、等高線の地図では
    # それが画素差として大きく出る（実測で平均 6〜8 → 2〜3 に落ちた）。
    cwr = "floor(%d*(%s)+0.5)" % (W, s_e)
    chr_ = "floor(%d*(%s)+0.5)" % (H, s_e)
    xl = "floor((%s)-(%s)/2+0.5)" % (cx_e, cwr)
    yt = "floor((%s)-(%s)/2+0.5)" % (cy_e, chr_)

    def cam(iw):
        return ("zoompan=z='(%d/(%s))':x='%s':y='%s':d=1:s=%dx%d:fps=%d,setsar=1"
                % (iw, cwr, xl, yt, W, H, fps))

    last = None
    for k, item in enumerate(masters):
        ly, m, q, iw = item
        i = add_input(q)
        if k == 0:
            chains.append("[%d:v]%s[bg]" % (i, cam(iw)))
            last = "bg"
            continue
        # アルファは毎フレーム clip.interp の値を sendcmd で流す。PIL と完全一致。
        keys = ly.get("alpha") or [[t0, 1.0]]
        cmds, prev = [], None
        for f in range(n):
            a = clip.interp(keys, t0 + f / float(fps))[0]
            if prev is None or abs(a - prev) > 0.002:
                cmds.append("%s colorchannelmixer aa %s;" % (_fmt(f / float(fps)), _fmt(a)))
                prev = a
        cf = os.path.join(tmp, "a%d.txt" % k)
        io.open(cf, "w", encoding="utf-8").write(chr(10).join(cmds) + chr(10))
        chains.append("[%d:v]%s,format=rgba,sendcmd=f=%s,colorchannelmixer=aa=%s[L%d]"
                      % (i, cam(iw), rel(cf), _fmt(clip.interp(keys, t0)[0]), k))
        chains.append("[%s][L%d]overlay=format=auto[c%d]" % (last, k, k))
        last = "c%d" % k

    def screen(lat, lon):
        """clip.to_screen と同じ。((world - left)/s, (world - top)/s)。

        **overlay には on が無い**（変数は n と t）。zoompan 用に組んだ式を
        そのまま渡すと "Error when evaluating the expression" で落ちるので、
        ここでは時刻変数 t で組み直す。t = n/fps なので値は同じ。
        """
        tv = "t"
        se = smooth_expr(shot["camera"], lambda kk: (kk[3] if len(kk) > 3 else 1.0), t0, tv)
        cxe = smooth_expr(shot["camera"], lambda kk: base.world(kk[1], kk[2])[0], t0, tv)
        cye = smooth_expr(shot["camera"], lambda kk: base.world(kk[1], kk[2])[1], t0, tv)
        cw = "floor(%d*(%s)+0.5)" % (W, se)
        ch = "floor(%d*(%s)+0.5)" % (H, se)
        lft = "floor((%s)-(%s)/2+0.5)" % (cxe, cw)
        top = "floor((%s)-(%s)/2+0.5)" % (cye, ch)
        wx, wy = base.world(lat, lon)
        return ("((%.3f-(%s))/(%s))" % (wx, lft, se),
                "((%.3f-(%s))/(%s))" % (wy, top, se))

    return last, screen


def _bg_photo(shot, photos, size, fps, tmp, add_input, chains):
    """写真ショットの下地。clip.render_photo_shot と同じ寄り引き。"""
    W, H = size
    t0, t1 = shot["t0"], shot["t1"]
    meta = photos[shot["photo"]]
    src = Image.open(os.path.join(photos["_dir"],
                                  os.path.basename(meta["path"]))).convert("RGB")
    kb = shot.get("kb", [[t0, 1.10, 0.5, 0.5], [t1, 1.0, 0.5, 0.5]])
    zmax = max([float(r[1]) for r in kb if len(r) > 1] or [1.25])
    k = max(W / float(src.width), H / float(src.height)) * max(zmax, 1.05)
    base = src.resize((int(src.width * k), int(src.height * k)), Image.LANCZOS)
    bw, bh = base.width, base.height
    img = pad_16x9(base, bg=(0, 0, 0))
    q = os.path.join(tmp, "photo.png")
    img.save(q)
    i = add_input(q)

    TV = "time"
    s_e = smooth_expr(kb, lambda r: r[1], t0, TV)
    cx_e = smooth_expr(kb, lambda r: r[2], t0, TV)
    cy_e = smooth_expr(kb, lambda r: r[3], t0, TV)
    # PIL 側は int() の切り捨て。round ではないので floor で揃える。
    cw = "floor(%d*(%s))" % (W, s_e)
    ch = "floor(%d*(%s))" % (H, s_e)
    x = "max(0,min(floor((%d-(%s))*(%s)),%d-(%s)))" % (bw, cw, cx_e, bw, cw)
    y = "max(0,min(floor((%d-(%s))*(%s)),%d-(%s)))" % (bh, ch, cy_e, bh, ch)
    chains.append("[%d:v]zoompan=z='(%d/(%s))':x='%s':y='%s':d=1:s=%dx%d:fps=%d,"
                  "setsar=1[bg]" % (i, img.width, cw, x, y, W, H, fps))
    return "bg"
