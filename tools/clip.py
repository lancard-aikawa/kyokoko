# -*- coding: utf-8 -*-
"""地理院タイルの上をカメラが動く映像を作り、字幕を焼いて音声と合わせる。

1カット=1ショットとして別々に描き、最後に連結して音声を乗せる。
字幕の時刻はエピソード全体の絶対時刻で扱う（timeline.json のまま）。
フレームは PIL で作って ffmpeg に生パイプで流す（PNG を大量に書かないため）。
"""
import math
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

import tiles

# 日本語フォント。**環境ごとに場所が違うので探す。**
# もとは C:/Windows/Fonts/BIZ-UDGothic*.ttc を直書きしていたが、それだと
# Windows 以外では import した瞬間に落ち、Windows でも BIZ UD が入っていない
# 機種で落ちた。候補を順に当たり、見つからなければ名指しで案内する。
# 明示したいときは環境変数で: KOKO_FONT（太字・標準の両方）/
# KOKO_FONT_BOLD / KOKO_FONT_REGULAR。
FONT_CANDIDATES = {
    "bold": [
        "C:/Windows/Fonts/BIZ-UDGothicB.ttc",       # Windows 10 1809 以降
        "C:/Windows/Fonts/YuGothB.ttc",             # 游ゴシック Bold
        "C:/Windows/Fonts/meiryob.ttc",             # メイリオ Bold
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",   # macOS
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    ],
    "regular": [
        "C:/Windows/Fonts/BIZ-UDGothicR.ttc",
        "C:/Windows/Fonts/YuGothR.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    ],
}

_FONT_PATH = {}
_FONT_CACHE = {}


def font_path(bold=True):
    """使う日本語フォントのパス。見つからなければ案内して落とす。"""
    kind = "bold" if bold else "regular"
    if kind in _FONT_PATH:
        return _FONT_PATH[kind]
    named = "KOKO_FONT_BOLD" if bold else "KOKO_FONT_REGULAR"
    env = os.environ.get(named) or os.environ.get("KOKO_FONT")
    for cand in ([env] if env else []) + FONT_CANDIDATES[kind]:
        if cand and os.path.exists(cand):
            _FONT_PATH[kind] = cand
            return cand
    NL = chr(10)
    raise RuntimeError(NL.join(
        ["日本語フォントが見つかりません（%s）。" % kind,
         "  探した場所:"]
        + ["    " + c for c in FONT_CANDIDATES[kind]]
        + ["  環境変数で指定できます:",
           "    KOKO_FONT=<太字にも標準にも使うフォントのパス>",
           "    KOKO_FONT_BOLD / KOKO_FONT_REGULAR（別々に指定するとき）"]))


def font(size, bold=True):
    """サイズごとに ImageFont を作って使い回す。"""
    key = (size, bold)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(font_path(bold), size)
    return _FONT_CACHE[key]


ATTRIB = "出典: 国土地理院（地理院タイル）"

# 字幕の色と立ち絵を出す側。episode.json の cast から読む（無ければこの既定）。
# 掛け合いなので左右に分けると、どちらが喋っているか一目でわかる。
COLORS = {"つむぎ": (255, 214, 120), "朱司": (150, 210, 255)}
SIDE = {"つむぎ": "right", "朱司": "left"}


def load_plan(ep_dir):
    """episode.json を読んで、字幕の色と立ち絵の左右を差し替える。"""
    import json
    p = os.path.join(ep_dir, "episode.json") if ep_dir else None
    if not p or not os.path.exists(p):
        return {}
    plan = json.load(open(p, encoding="utf-8"))
    for who, c in (plan.get("cast") or {}).items():
        if c.get("color"):
            COLORS[who] = tuple(c["color"])
        if c.get("side"):
            SIDE[who] = c["side"]
    return plan
ACCENT = (255, 90, 60)


def smoothstep(t):
    return t * t * (3 - 2 * t)


def interp(keys, t):
    if t <= keys[0][0]:
        return list(keys[0][1:])
    if t >= keys[-1][0]:
        return list(keys[-1][1:])
    for a, b in zip(keys, keys[1:]):
        if a[0] <= t <= b[0]:
            u = smoothstep((t - a[0]) / (b[0] - a[0])) if b[0] > a[0] else 0.0
            return [x + (y - x) * u for x, y in zip(a[1:], b[1:])]
    return list(keys[-1][1:])


def ease_in_out(x):
    return smoothstep(max(0.0, min(1.0, x)))


class Master(object):
    """カメラが動く範囲をまとめて 1 枚に焼いた地図。世界ピクセル座標で引く。"""

    def __init__(self, layer, zoom, bounds, w, h, margin=200):
        lat0, lon0, lat1, lon1 = bounds
        lo, hi = tiles.LAYERS[layer][1]
        src_zoom = max(lo, min(zoom, hi))
        self.scale = 2.0 ** (zoom - src_zoom)
        x0, y0 = tiles.deg2num(lat1, lon0, zoom)
        x1, y1 = tiles.deg2num(lat0, lon1, zoom)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        self.W = int((x1 - x0) * 256) + w + margin * 2
        self.H = int((y1 - y0) * 256) + h + margin * 2
        clat, clon = tiles.num2deg(cx, cy, zoom)
        img = tiles.render(layer, clat, clon, src_zoom,
                           int(math.ceil(self.W / self.scale)),
                           int(math.ceil(self.H / self.scale)))
        if abs(self.scale - 1.0) > 1e-6:
            img = img.resize((self.W, self.H), Image.LANCZOS)
        self.img = img.convert("RGB")
        self.zoom = zoom
        self.px0 = cx * 256 - self.W / 2.0
        self.py0 = cy * 256 - self.H / 2.0

    def world(self, lat, lon):
        x, y = tiles.deg2num(lat, lon, self.zoom)
        return x * 256 - self.px0, y * 256 - self.py0

    def view(self, lat, lon, w, h, s):
        """中心(lat,lon)、倍率 s（>1 で引き）で w*h を切り出す。"""
        cw, ch = int(round(w * s)), int(round(h * s))
        cx, cy = self.world(lat, lon)
        left, top = int(round(cx - cw / 2)), int(round(cy - ch / 2))
        img = self.img.crop((left, top, left + cw, top + ch))
        if (cw, ch) != (w, h):
            img = img.resize((w, h), Image.LANCZOS)
        return img, (left, top, s)


def to_screen(m, origin, lat, lon):
    left, top, s = origin
    wx, wy = m.world(lat, lon)
    return (wx - left) / s, (wy - top) / s


def draw_text(d, xy, text, font, fill, anchor="la", hw=3, fade=1.0):
    d.text(xy, text, font=font, fill=fill, anchor=anchor,
           stroke_width=hw, stroke_fill=(0, 0, 0, int(200 * fade)))


# 行頭に置きたくない文字（禁則）
NO_HEAD = "、。，．・）」』】〉》〕｝！？ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ…"


def wrap(d, text, font, max_w):
    """日本語は空白で切れないので文字単位で折る。禁則は 1 文字ぶら下げる。"""
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=font) <= max_w or not cur:
            cur += ch
        elif ch in NO_HEAD:
            cur += ch          # はみ出しても行末にぶら下げる
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def shot_bounds(shot, pad=0.004):
    lats = [k[1] for k in shot["camera"]] + [l["lat"] for l in shot.get("labels", [])]
    lons = [k[2] for k in shot["camera"]] + [l["lon"] for l in shot.get("labels", [])]
    for p in shot.get("paths", []):
        lats += [q[0] for q in p["points"]]
        lons += [q[1] for q in p["points"]]
    s = max([k[3] if len(k) > 3 else 1.0 for k in shot["camera"]])
    pad = pad * s
    return (min(lats) - pad, min(lons) - pad, max(lats) + pad, max(lons) + pad)


def load_chara(ep_dir):
    """立ち絵を読む。chara/<話者>.png が口を閉じた絵、<話者>_open.png が開いた絵。

    開いた絵があれば音の大きさに合わせて口パクする。無ければ閉じた絵だけを使う。
    立ち絵が 1 枚も無ければ何も描かない（いまはこの状態で動く）。
    """
    d = os.path.join(ep_dir, "chara")
    out = {}
    if not os.path.isdir(d):
        return out
    for f in os.listdir(d):
        if not f.lower().endswith(".png") or f.endswith("_open.png"):
            continue
        who = os.path.splitext(f)[0]
        o = os.path.join(d, who + "_open.png")
        out[who] = {"closed": Image.open(os.path.join(d, f)).convert("RGBA"),
                    "open": Image.open(o).convert("RGBA") if os.path.exists(o) else None}
    return out


def voice_envelope(wav_path, fps):
    """1 フレームぶんずつの音の大きさ。口パクに使う。"""
    import array
    import wave as _wave
    if not os.path.exists(wav_path):
        return []
    with _wave.open(wav_path, "rb") as w:
        rate, n = w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    a = array.array("h")
    a.frombytes(raw[:len(raw) // 2 * 2])
    step = int(rate / fps)
    env = []
    for i in range(0, len(a), step):
        seg = a[i:i + step]
        env.append((sum(abs(x) for x in seg) / len(seg) / 32768.0) if seg else 0.0)
    return env


def draw_chara(frame, chara, timeline, t, env, fps, W, H):
    """いま喋っている話者の立ち絵を右下に置く。"""
    if not chara:
        return
    cur = [r for r in timeline if r["start"] - 0.25 <= t <= r["end"] + 0.35]
    if not cur:
        return
    r = cur[-1]
    art = chara.get(r["speaker"])
    if not art:
        return
    fade = min(1.0, (t - (r["start"] - 0.25)) / 0.3, ((r["end"] + 0.35) - t) / 0.3)
    if fade <= 0.02:
        return
    i = int(t * fps)
    loud = env[i] if 0 <= i < len(env) else 0.0
    img = art["open"] if (art["open"] is not None and loud > 0.035) else art["closed"]
    h = int(H * 0.56)
    w = int(img.width * h / img.height)
    img = img.resize((w, h), Image.LANCZOS)
    if fade < 1.0:
        alpha = img.getchannel("A").point(lambda v: int(v * fade))
        img.putalpha(alpha)
    x = 30 if SIDE.get(r["speaker"]) == "left" else W - w - 30
    frame.paste(img, (x, H - h), img)


def title_active(shot, t):
    """タイトルが出ている時間帯か。ラベルと注記を止めるために使う。

    タイトルは画面の中央に出る。地図のラベルもカメラの中心付近に出るので、
    同じ瞬間に両方を描くと番組名の上に町名が重なる。第001〜003回の5枚が
    そうなっていた（「今日はこ眼鏡橋こに」）。ショットを分けて逃げることも
    できるが、ラベルには終了時刻が無いので毎回ショットを割ることになる。
    **タイトルが出ている間はラベルと注記を伏せる**ほうが確実で、
    どの回でも自動的に効く。
    """
    ti = shot.get("title")
    if not ti:
        return False
    a, b = ti["from"], ti["to"]
    # フェードの分だけ内側で切ると、ラベルが消えてからタイトルが出る
    return a - 0.5 <= t <= b + 0.5


def draw_title(frame, d, shot, t, W, H):
    """シーンタイトル。画を暗く落として大きく出す。アバンの番組名にも使う。"""
    ti = shot.get("title")
    if not ti or not (ti["from"] <= t <= ti["to"]):
        return
    a, b = ti["from"], ti["to"]
    fade = min(1.0, (t - a) / 0.7, (b - t) / 0.7)
    if fade <= 0.01:
        return
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, int(ti.get("dim", 130) * fade)))
    f_main = font(ti.get("size", 96))
    f_sub = font(ti.get("subsize", 40))
    cy = int(H * ti.get("y", 0.42))
    draw_text(d, (W // 2, cy), ti["main"], f_main,
              (255, 255, 255, int(255 * fade)), anchor="mm", hw=4, fade=fade)
    if ti.get("sub"):
        # 細い横線を挟んで副題。罫線は主題と副題の広いほうに合わせる
        tw = max(d.textlength(ti["main"], font=f_main),
                 d.textlength(ti["sub"], font=f_sub)) + 40
        y = cy + ti.get("size", 96) // 2 + 26
        d.line([W // 2 - tw / 2, y, W // 2 + tw / 2, y],
               fill=(255, 255, 255, int(200 * fade)), width=2)
        draw_text(d, (W // 2, y + 34), ti["sub"], f_sub,
                  (255, 255, 255, int(255 * fade)), anchor="mm", hw=3, fade=fade)


def draw_question(frame, d, shot, t, W, H):
    """クエスチョンの札。出題からシンキングタイムの終わりまで出したままにする。

    タイトルと違って画を暗く落としすぎない。問いを読みながら現地の絵も
    見ていてほしいので、札を真ん中に置いて背景は軽く沈める程度にとどめる。
    残り時間のバーを下に引く。無音が続く理由が画で分かるようにするため。
    """
    q = shot.get("question")
    if not q or not (q["from"] <= t <= q["to"]):
        return
    a, b = q["from"], q["to"]
    fade = min(1.0, (t - a) / 0.45, (b - t) / 0.45)
    if fade <= 0.01:
        return
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, int(q.get("dim", 96) * fade)))

    lines = q["text"] if isinstance(q["text"], list) else [q["text"]]
    f_q = font(q.get("size", 60))
    f_tag = font(34)
    lh = q.get("size", 60) + 22
    box_h = 150 + lh * len(lines)
    box_w = int(max([d.textlength(x, font=f_q) for x in lines]) + 140)
    box_w = max(box_w, 640)
    x0 = (W - box_w) // 2
    y0 = int(H * q.get("y", 0.30))

    d.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(12, 14, 20, int(228 * fade)))
    d.rectangle([x0, y0, x0 + box_w, y0 + box_h],
                outline=(214, 176, 66, int(255 * fade)), width=3)
    # 見出しの帯
    d.rectangle([x0, y0, x0 + box_w, y0 + 62], fill=(214, 176, 66, int(240 * fade)))
    draw_text(d, (x0 + box_w // 2, y0 + 31), q.get("tag", "クエスチョン"), f_tag,
              (16, 18, 24, int(255 * fade)), anchor="mm", hw=0, fade=fade)
    for i, ln in enumerate(lines):
        draw_text(d, (x0 + box_w // 2, y0 + 96 + lh // 2 + lh * i), ln, f_q,
                  (255, 255, 255, int(255 * fade)), anchor="mm", hw=3, fade=fade)

    # 考える時間のバー。think が無ければ出さない
    th = q.get("think")
    if th and th[0] <= t <= th[1]:
        left = 1.0 - (t - th[0]) / max(0.001, th[1] - th[0])
        bx0, bx1 = x0 + 40, x0 + box_w - 40
        by = y0 + box_h - 36
        d.rectangle([bx0, by, bx1, by + 8], fill=(255, 255, 255, int(46 * fade)))
        d.rectangle([bx0, by, bx0 + (bx1 - bx0) * left, by + 8],
                    fill=(214, 176, 66, int(240 * fade)))


def draw_credits(frame, d, shot, t, W, H):
    """エンディングの出典・クレジット。画を落として左寄せで並べる。"""
    cr = shot.get("credits")
    if not cr or not (cr["from"] <= t <= cr["to"]):
        return
    fade = min(1.0, (t - cr["from"]) / 0.8, (cr["to"] - t) / 0.8)
    if fade <= 0.01:
        return
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, int(cr.get("dim", 165) * fade)))
    f_h = font(30)
    f_b = font(25, bold=False)
    x, y = int(W * 0.17), int(H * 0.17)
    for kind, text in cr["lines"]:
        if kind == "h":
            y += 16
            draw_text(d, (x, y), text, f_h, (255, 255, 255, int(255 * fade)), hw=3, fade=fade)
            y += 42
        elif kind == "gap":
            y += 18
        else:
            draw_text(d, (x + 26, y), text, f_b, (232, 232, 228, int(255 * fade)),
                      hw=2, fade=fade)
            y += 34


def draw_subtitle(d, timeline, t, W, H, fonts):
    f_sub, f_name = fonts
    cur = [r for r in timeline if r["start"] - 0.15 <= t <= r["end"] + 0.25]
    if not cur:
        return 0
    r = cur[-1]
    lines = wrap(d, r["text"], f_sub, W - 140)
    band = 62 + len(lines) * 54
    d.rectangle([0, H - band, W, H], fill=(0, 0, 0, 150))
    col = COLORS.get(r["speaker"], (255, 255, 255))
    draw_text(d, (70, H - band + 14), r["speaker"], f_name, col + (255,), hw=2)
    for k, ln in enumerate(lines):
        draw_text(d, (70, H - band + 50 + k * 54), ln, f_sub, (255, 255, 255, 255))
    return band


def render_photo_shot(shot, timeline, photos, out_path, size=(1920, 1080), fps=30,
                      quiet=True, chara=None, env=()):
    """写真を 1 枚映すショット。ゆっくり寄る／引くだけの素直な動き。"""
    W, H = size
    t0, t1 = shot["t0"], shot["t1"]
    meta = photos[shot["photo"]]
    src = Image.open(os.path.join(photos["_dir"], os.path.basename(meta["path"]))).convert("RGB")

    f_sub = font(42)
    f_name = font(26)
    f_note = font(38)
    f_small = font(20, bold=False)

    # 画面いっぱいに使えるよう、足りない側に合わせて拡大しておく。
    # 余裕はショットがいちばん寄るところから決める。ここを定数にしておくと、
    # それを超える kb を書いたとき crop が画像からはみ出し、PIL が黒で埋める。
    # エラーにならないので、書き出した動画を見るまで気づけない。
    zmax = max([float(r[1]) for r in shot.get("kb", []) if len(r) > 1] or [1.25])
    k = max(W / src.width, H / src.height) * max(zmax, 1.05)
    base = src.resize((int(src.width * k), int(src.height * k)), Image.LANCZOS)

    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (W, H), "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL if quiet else None,
                         stderr=subprocess.DEVNULL if quiet else None)

    kb = shot.get("kb", [[t0, 1.10, 0.5, 0.5], [t1, 1.0, 0.5, 0.5]])
    cred = "写真: %s ／ %s（Wikimedia Commons）" % (meta.get("author") or "不明",
                                                 meta.get("license") or "?")
    for i in range(int(round((t1 - t0) * fps))):
        t = t0 + i / float(fps)
        s, cx, cy = interp(kb, t)
        cw, ch = int(W * s), int(H * s)
        left = int((base.width - cw) * cx)
        top = int((base.height - ch) * cy)
        left = max(0, min(left, base.width - cw))
        top = max(0, min(top, base.height - ch))
        frame = base.crop((left, top, left + cw, top + ch))
        if (cw, ch) != (W, H):
            frame = frame.resize((W, H), Image.LANCZOS)
        d = ImageDraw.Draw(frame, "RGBA")

        hide = title_active(shot, t)
        for nt in shot.get("notes", []):
            if hide or not (nt["from"] <= t <= nt["to"]):
                continue
            fade = min(1.0, (t - nt["from"]) / 0.4, (nt["to"] - t) / 0.4)
            tw = d.textlength(nt["text"], font=f_note)
            d.rectangle([60, 80, 60 + tw + 56, 80 + 68], fill=(0, 0, 0, int(165 * fade)))
            draw_text(d, (88, 96), nt["text"], f_note,
                      (255, 255, 255, int(255 * fade)), hw=2, fade=fade)

        draw_chara(frame, chara, timeline, t, env, fps, W, H)
        d = ImageDraw.Draw(frame, "RGBA")
        band = draw_subtitle(d, timeline, t, W, H, (f_sub, f_name))
        # 出典は字幕帯の上に。CC BY / CC BY-SA は表示が義務。
        draw_text(d, (W - 24, H - band - 30), cred, f_small,
                  (255, 255, 255, 235), anchor="ra")
        draw_question(frame, d, shot, t, W, H)
        draw_title(frame, d, shot, t, W, H)
        draw_credits(frame, d, shot, t, W, H)
        p.stdin.write(frame.tobytes())
    p.stdin.close()
    p.wait()
    return out_path


def render_shot(shot, timeline, out_path, size=(1920, 1080), fps=30, quiet=True,
                chara=None, env=()):
    W, H = size
    t0, t1 = shot["t0"], shot["t1"]
    zoom = shot["zoom"]
    bounds = shot_bounds(shot)
    # 引き（scale>1）の分までマスターに含めないと切り出しが画面外に出て黒く抜ける
    smax = max([k[3] if len(k) > 3 else 1.0 for k in shot["camera"]])
    masters = [(ly, Master(ly["id"], zoom, bounds, int(W * smax), int(H * smax)))
               for ly in shot["layers"]]

    f_sub = font(42)
    f_name = font(26)
    f_label = font(34)
    f_note = font(38)
    f_small = font(20, bold=False)

    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (W, H), "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL if quiet else None,
                         stderr=subprocess.DEVNULL if quiet else None)

    n = int(round((t1 - t0) * fps))
    for i in range(n):
        t = t0 + i / float(fps)
        cam = interp(shot["camera"], t)
        lat, lon = cam[0], cam[1]
        s = cam[2] if len(cam) > 2 else 1.0

        # 先頭レイヤは必ず下地（alpha は無視）。2枚目以降を重ねる。
        frame, origin, m = None, None, None
        for j, (ly, mm) in enumerate(masters):
            a = 1.0 if j == 0 else interp(ly.get("alpha", [[t0, 1.0]]), t)[0]
            if a <= 0.002:
                continue
            img, org = mm.view(lat, lon, W, H, s)
            frame = img if frame is None else Image.blend(frame, img, a)
            origin, m = org, mm
        if frame is None:
            frame = Image.new("RGB", (W, H), (24, 24, 24))
        d = ImageDraw.Draw(frame, "RGBA")

        for pa in shot.get("paths", []):
            prog = ease_in_out((t - pa["from"]) / max(0.01, pa["to"] - pa["from"]))
            if prog <= 0:
                continue
            pts = [to_screen(m, origin, q[0], q[1]) for q in pa["points"]]
            k = prog * (len(pts) - 1)
            ki = int(k)
            shown = pts[:ki + 1]
            if ki < len(pts) - 1:
                a_, b_ = pts[ki], pts[ki + 1]
                u = k - ki
                shown.append((a_[0] + (b_[0] - a_[0]) * u, a_[1] + (b_[1] - a_[1]) * u))
            if len(shown) >= 2:
                d.line(shown, fill=ACCENT + (235,), width=6, joint="curve")

        hide = title_active(shot, t)
        for lb in shot.get("labels", []):
            if hide or t < lb["from"]:
                continue
            fade = min(1.0, (t - lb["from"]) / 0.6)
            x, y = to_screen(m, origin, lb["lat"], lb["lon"])
            if not (-150 < x < W + 150 and -150 < y < H + 150):
                continue
            r = lb.get("r", 9)
            d.ellipse([x - r, y - r, x + r, y + r], fill=ACCENT + (int(235 * fade),),
                      outline=(255, 255, 255, int(235 * fade)), width=3)
            dx, dy = lb.get("offset", (18, -20))
            draw_text(d, (x + dx, y + dy), lb["text"], f_label,
                      (255, 255, 255, int(255 * fade)),
                      anchor=lb.get("anchor", "la"), fade=fade)

        for nt in shot.get("notes", []):
            if hide or not (nt["from"] <= t <= nt["to"]):
                continue
            fade = min(1.0, (t - nt["from"]) / 0.4, (nt["to"] - t) / 0.4)
            tw = d.textlength(nt["text"], font=f_note)
            d.rectangle([60, 80, 60 + tw + 56, 80 + 68], fill=(0, 0, 0, int(165 * fade)))
            draw_text(d, (88, 96), nt["text"], f_note,
                      (255, 255, 255, int(255 * fade)), hw=2, fade=fade)

        draw_chara(frame, chara, timeline, t, env, fps, W, H)
        d = ImageDraw.Draw(frame, "RGBA")
        draw_subtitle(d, timeline, t, W, H, (f_sub, f_name))
        draw_text(d, (W - 24, 22), ATTRIB, f_small, (255, 255, 255, 230), anchor="ra")
        draw_question(frame, d, shot, t, W, H)
        draw_title(frame, d, shot, t, W, H)
        draw_credits(frame, d, shot, t, W, H)
        p.stdin.write(frame.tobytes())

    p.stdin.close()
    p.wait()
    return out_path


def load_photos(ep_dir):
    p = os.path.join(ep_dir, "photos.json")
    if not os.path.exists(p):
        return {"_dir": os.path.join(ep_dir, "photos")}
    import json
    d = json.load(open(p, encoding="utf-8"))
    d["_dir"] = os.path.join(ep_dir, "photos")
    return d


# ffmpeg 版のレンダラ（tools/clip_ff.py）を使うか。build.py が --ff で立てる。
# 立ち絵を出すときは使わない（口パクが毎フレームの仕事なので ffmpeg に寄せられない）。
USE_FF = False
JOBS = 1        # 同時に描くショットの数。build.py の --jobs で決める。

_W = {}         # ワーカが1回だけ仕込む重たいもの（立ち絵・写真・時刻表）


def _worker_init(ep_dir, use_chara, use_ff, timeline, env, size, fps):
    """ワーカを1回だけ仕込む。**重いものはタスクではなくここで渡す。**

    ショットごとに渡すと、ショットの数だけ立ち絵と写真と時刻表を pickle で
    運ぶことになる。ワーカは数個しか作らないので、ここで一度だけ作る。
    """
    global USE_FF, _W
    USE_FF = use_ff
    load_plan(ep_dir)
    chara = load_chara(ep_dir) if (ep_dir and use_chara) else {}
    ff = None
    if use_ff and not chara:
        import clip_ff
        ff = clip_ff
    _W = {"ff": ff, "timeline": timeline, "chara": chara, "env": env,
          "photos": load_photos(ep_dir) if ep_dir else None, "size": size, "fps": fps}


def _render_one(task):
    """ワーカ側。1ショットを描いて (番号, どちらで描いたか, 理由) を返す。"""
    i, sh, seg = task
    g = _W
    ok, why = (g["ff"].supported(sh) if g["ff"] else (False, ""))
    if ok:
        g["ff"].render_shot(sh, g["timeline"], seg, g["size"], g["fps"], photos=g["photos"])
        return i, True, ""
    if sh.get("type") == "photo":
        render_photo_shot(sh, g["timeline"], g["photos"], seg, g["size"], g["fps"],
                          chara=g["chara"], env=g["env"])
    else:
        render_shot(sh, g["timeline"], seg, g["size"], g["fps"],
                    chara=g["chara"], env=g["env"])
    return i, False, why


def auto_jobs():
    """同時に描く数の既定。

    頭打ちは実測で2倍あたり。絵を作っているのは PIL（Python 側）なので
    コアを増やせば増えるはずだが、実際には帯域で止まる。コアの半分、
    最大4までにして、余りは x264 に残す。
    """
    try:
        n = len(os.sched_getaffinity(0))
    except AttributeError:
        n = os.cpu_count() or 1
    return max(1, min(4, n // 2))




def build_episode(shots, timeline, audio, out_path, size=(1920, 1080), fps=30, ep_dir=None,
                  use_chara=True):
    load_plan(ep_dir)
    photos = load_photos(ep_dir) if ep_dir else None
    chara = load_chara(ep_dir) if (ep_dir and use_chara) else {}
    env = voice_envelope(audio, fps) if chara else ()
    ff = None
    if USE_FF and not chara:
        import clip_ff
        ff = clip_ff
    tmp = tempfile.mkdtemp(prefix="kokogallery_")
    segs = [os.path.join(tmp, "seg%02d.mp4" % i) for i in range(len(shots))]
    tasks = [(i, sh, segs[i]) for i, sh in enumerate(shots)]

    def report(i, ok, why):
        sh = shots[i]
        tail = "" if not USE_FF else ("  [ffmpeg]" if ok else "  [PIL: %s]" % why)
        print("   ショット%d/%d (%.1f-%.1f秒)%s"
              % (i + 1, len(shots), sh["t0"], sh["t1"], tail))

    jobs = max(1, min(JOBS, len(shots)))
    if jobs > 1:
        # ショットは互いに関係がないので、そのまま別のプロセスに渡せる。
        # 順に受けるので、出てくる行はいままでと同じ並びになる。
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(
                max_workers=jobs, initializer=_worker_init,
                initargs=(ep_dir, use_chara, USE_FF, timeline, env, size, fps)) as ex:
            for i, ok, why in ex.map(_render_one, tasks):
                report(i, ok, why)
    else:
        for i, sh, seg in tasks:
            ok, why = (ff.supported(sh) if ff else (False, ""))
            if ok:
                ff.render_shot(sh, timeline, seg, size, fps, photos=photos)
            elif sh.get("type") == "photo":
                render_photo_shot(sh, timeline, photos, seg, size, fps, chara=chara, env=env)
            else:
                render_shot(sh, timeline, seg, size, fps, chara=chara, env=env)
            report(i, ok, why)
    lst = os.path.join(tmp, "concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s in segs:
            f.write("file '%s'\n" % s.replace("\\", "/"))
    # apad は保険。音声が映像より短いときに無音で埋め、末尾が切れるのを防ぐ。
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-i", audio, "-c:v", "copy", "-af", "apad", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", out_path], capture_output=True, check=True)
    for s in segs:
        os.remove(s)
    os.remove(lst)
    os.rmdir(tmp)
    return out_path
