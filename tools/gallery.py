# -*- coding: utf-8 -*-
"""ギャラリー用の軽い素材を書き出す。

  python tools/gallery.py build              全部の回のポスターとプレビューを作る
  python tools/gallery.py build --ep <dir>   1回だけ
  python tools/gallery.py index              gallery/README.md を書く
  python tools/gallery.py release            本編を GitHub Releases に上げる
  python tools/gallery.py release --ep <dir> 1回だけ
  python tools/gallery.py youtube --ep <dir> YouTube 用の材料（概要欄・チャプター・字幕）
  python tools/gallery.py srt     --ep <dir> 字幕ファイルだけ書く

動画そのものは git に入れない。GitHub は 1 ファイル 100MB で push が弾かれる
うえに、git は全バージョンを永久に持つ。動画は差分圧縮が効かないので、
録り直すたびにリポジトリが本編1本分ずつ太る。本編は Releases に添付する
（1アセット 2GB まで、しかも履歴に入らない）。

ここで作るのはリポジトリに置いても困らないものだけ:

  poster.jpg   タイトル画面の1枚（数百KB）
  preview.mp4  アバンをそのまま 720p に落としたもの（数MB）

アバンは「掴み＋番組タイトル」で出来ているので、切り出しをせずに
そのままプレビューとして成立する。
"""
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import build as B  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GALLERY = os.path.join(ROOT, "gallery")

# プレビューはギャラリーで並べて見るもの。本編の代わりではないので割り切って落とす。
PREVIEW_SCALE = "1280:-2"
PREVIEW_CRF = "28"


def episodes():
    d = os.path.join(ROOT, "episodes")
    return [os.path.join(d, x) for x in sorted(os.listdir(d))
            if os.path.isdir(os.path.join(d, x))]


def plan(ep_dir):
    p = os.path.join(ep_dir, "episode.json")
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}


# youtube() の中で plan を変数名に使うので、関数には別名でも触れるようにする
plan_of = plan


def title_moment(ep_dir):
    """番組タイトルがいちばんはっきり出ている時刻を、アバンの中から探す。

    shots.py の title の from/to をそのまま使う。秒を直書きすると、
    台詞を録り直して尺が動いた瞬間にずれる。
    """
    B.use_episode(ep_dir)
    shots = B.load_shots()
    av = shots.get(0) or shots[sorted(shots)[0]]
    for sh in av:
        t = sh.get("title")
        if t and "from" in t and "to" in t:
            # 出きったところ。フェードの途中を掴まない
            return sh, min(t["to"] - 0.4, (t["from"] + t["to"]) / 2 + 0.6)
    last = av[-1]
    return last, (last["t0"] + last["t1"]) / 2


def poster(ep_dir, out_dir):
    name = os.path.basename(ep_dir)
    src = os.path.join(ep_dir, "out", "ep0.mp4")
    if not os.path.exists(src):
        print("  アバンがありません: %s" % src)
        print("  先に本編を作ってください:  python tools/build.py --ep %s all" % ep_dir)
        return None
    sh, t = title_moment(ep_dir)
    # ep0.mp4 は話の先頭が 0 秒。ショットの t0/t1 も話の中の秒なので、そのまま使う
    # （ショット相対に直すと、タイトルではなく途中の絵を掴む）
    at = t
    out = os.path.join(out_dir, "poster.jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "%.3f" % at, "-i", src,
                    "-frames:v", "1", "-vf", "scale=%s:flags=lanczos" % PREVIEW_SCALE,
                    "-q:v", "3", out], check=True)
    print("  poster.jpg   %5.0fKB  (%.1f秒地点)" % (os.path.getsize(out) / 1024, at))
    return out


def preview(ep_dir, out_dir):
    src = os.path.join(ep_dir, "out", "ep0.mp4")
    if not os.path.exists(src):
        return None
    out = os.path.join(out_dir, "preview.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src,
                    "-vf", "scale=%s:flags=lanczos" % PREVIEW_SCALE,
                    "-c:v", "libx264", "-preset", "slow", "-crf", PREVIEW_CRF,
                    "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-movflags", "+faststart", out], check=True)
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration", "-of", "default=nw=1:nk=1", out],
                             capture_output=True, text=True).stdout.strip())
    print("  preview.mp4  %5.1fMB  (%.0f秒)" % (os.path.getsize(out) / 1048576, d))
    return out


def meta(ep_dir):
    """ギャラリーの1行に要る値を集める。"""
    name = os.path.basename(ep_dir)
    p = plan(ep_dir)
    full = os.path.join(ep_dir, "out", "%s.mp4" % name)
    dur = 0.0
    if os.path.exists(full):
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                    "format=duration", "-of", "default=nw=1:nk=1", full],
                                   capture_output=True, text=True).stdout.strip())
    town = (p.get("town") or {}).get("name", "")
    no = name.split("-")[0]
    return {"dir": name, "no": no, "town": town,
            "title": p.get("title") or name,
            # 「第002回 長崎市 眼鏡橋（中島川）—「流されないための橋」」
            "heading": "第%s回 %s —「%s」" % (no, town, p.get("title") or name),
            "duration": dur,
            "chapters": [c.get("title", "") for c in p.get("chapters", [])
                         if c.get("n") not in (0, 99)]}


def build_one(ep_dir):
    name = os.path.basename(ep_dir)
    out_dir = os.path.join(GALLERY, name)
    os.makedirs(out_dir, exist_ok=True)
    print("%s" % name)
    poster(ep_dir, out_dir)
    preview(ep_dir, out_dir)
    m = meta(ep_dir)
    with io.open(os.path.join(out_dir, "episode.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return m


PAGE_HEAD = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日はここに</title>
<meta name="description" content="町の碑をめぐる読み上げ動画。地理院タイルと VOICEVOX で作っています。">
<link rel="icon" href="favicon.svg">
<style>
:root{
  --bg:#12141a; --card:#1b1e26; --line:#2b3040;
  --fg:#e8e6e1; --dim:#9aa0ad; --accent:#c9a227;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font-family:"Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,system-ui,sans-serif;
  line-height:1.8; -webkit-text-size-adjust:100%;
}
.wrap{max-width:900px; margin:0 auto; padding:0 20px 80px}
header{padding:72px 0 40px; border-bottom:1px solid var(--line)}
h1{
  margin:0; font-size:clamp(38px,9vw,64px); letter-spacing:.22em;
  font-weight:600; text-indent:.22em;
}
.lead{margin:20px 0 0; color:var(--dim); font-size:15px; max-width:34em}
article{padding:52px 0; border-bottom:1px solid var(--line); scroll-margin-top:24px}
.anchor{color:inherit; text-decoration:none}
.anchor:hover{text-decoration:underline}
h2{margin:0 0 4px; font-size:clamp(19px,4vw,25px); font-weight:600; line-height:1.5}
.meta{margin:0 0 22px; color:var(--dim); font-size:13px; letter-spacing:.06em}
video{
  width:100%; display:block; background:#000; border-radius:6px;
  border:1px solid var(--line);
}
.cap{margin:10px 0 0; color:var(--dim); font-size:12.5px}
ol{margin:24px 0 0; padding-left:1.4em; color:var(--fg)}
ol li{margin:.35em 0; font-size:15px}
ol li::marker{color:var(--accent); font-variant-numeric:tabular-nums}
.dl{
  display:inline-block; margin-top:26px; padding:11px 22px;
  border:1px solid var(--accent); border-radius:4px;
  color:var(--accent); text-decoration:none; font-size:14px;
}
.dl:hover{background:var(--accent); color:var(--bg)}
.dl small{display:block; font-size:11px; opacity:.75; letter-spacing:.04em}
footer{padding:44px 0 0; color:var(--dim); font-size:12.5px}
footer h3{margin:0 0 12px; font-size:13px; color:var(--fg); font-weight:600;
  letter-spacing:.1em}
footer ul{margin:0; padding-left:1.2em}
footer li{margin:.3em 0}
footer a{color:var(--dim)}
@media (prefers-color-scheme: light){
  :root{--bg:#faf8f4; --card:#fff; --line:#e0dcd4; --fg:#20222a;
        --dim:#6b6f7a; --accent:#8a6d1f;}
}
</style>
<div class="wrap">
<header>
<h1>今日はここに</h1>
<p class="lead">〒や町名を指定すると、その町の遺構・歴史建造物・地名の由来にまつわる
「碑」の話を集め、読み上げシナリオを作り、地図と VOICEVOX で動画にしています。</p>
</header>
"""

PAGE_FOOT = """<footer>
<h3>出典</h3>
<ul>
<li>地図 — 出典 国土地理院（<a href="https://maps.gsi.go.jp/development/ichiran.html">地理院タイル</a>）</li>
<li>碑文 — 出典 国土地理院（自然災害伝承碑）</li>
<li>音声 — VOICEVOX:春日部つむぎ / VOICEVOX:雀松朱司(CV:狐狗狸ラク)</li>
<li>写真 — Wikimedia Commons（作者とライセンスは各回の photos.json）</li>
</ul>
<h3>制作環境</h3>
<ul>
<li>調査メモ・台本・構図・ツールは <a href="https://github.com/@@SRC@@">@@SRC@@</a>（MIT）</li>
</ul>
</footer>
</div>
"""


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="10" fill="#12141a"/>
<text x="32" y="45" font-size="42" text-anchor="middle" fill="#c9a227"
 font-family="serif">碑</text>
</svg>
"""


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def html(ms, repo=None):
    """gallery/index.html。GitHub Pages で見る用。

    README.md からプレビューに張ったリンクは blob 画面に飛んでしまうので、
    その場で再生できる面を別に用意する。preload="none" にしてあるので、
    開いただけでは動画を取りに行かない（Pages の帯域を使わない）。
    本編は Releases 側なので、そもそも Pages の帯域には乗らない。
    """
    rel = "../../releases/tag/%s"
    if repo:
        rel = "https://github.com/" + repo + "/releases/tag/%s"
    out = [PAGE_HEAD]
    foot = PAGE_FOOT.replace("@@SRC@@", SOURCE_REPO)
    for m in ms:
        mm, ss = int(m["duration"] // 60), int(m["duration"] % 60)
        d = m["dir"]
        # 回ごとに id を振る。これが無いと「この回だけを見せる URL」が作れない。
        # 元リポジトリの README からギャラリーの各回へ深いリンクを張るのに使う。
        # 見出し自体をその id へのリンクにしておくと、人が URL を拾える。
        out.append(
            '<article id="%s">\n'
            '<h2><a class="anchor" href="#%s">%s</a></h2>\n'
            '<p class="meta">%s　%d分%02d秒</p>\n'
            '<video controls preload="none" playsinline poster="%s/poster.jpg">\n'
            '  <source src="%s/preview.mp4" type="video/mp4">\n'
            '</video>\n'
            '<p class="cap">アバン（冒頭）だけの抜粋です。</p>\n'
            % (d, d, esc(m["heading"]), esc(m["town"]), mm, ss, d, d))
        out.append("<ol>\n%s\n</ol>\n" %
                   "\n".join("<li>%s</li>" % esc(c) for c in m["chapters"]))
        out.append('<a class="dl" href="%s">本編をダウンロード'
                   '<small>1920x1080 / H.264 / MP4</small></a>\n</article>\n'
                   % (rel % d))
    out.append(foot)
    pth = os.path.join(GALLERY, "index.html")
    io.open(pth, "w", encoding="utf-8").write("".join(out))
    # Jekyll に触らせない。index.html をそのまま出したいだけなので
    io.open(os.path.join(GALLERY, ".nojekyll"), "w", encoding="utf-8").write("")
    io.open(os.path.join(GALLERY, "favicon.svg"), "w", encoding="utf-8").write(FAVICON)
    print("page  -> %s" % pth)


def index(ms):
    """gallery/README.md。GitHub の Releases に置いた本編へ誘導する。"""
    L = ["# 今日はここに",
         "",
         "〒や町名を指定すると、その町の遺構・歴史建造物・地名の由来にまつわる",
         "「碑」の話を集め、読み上げシナリオを作り、VOICEVOX と地図で動画にする。",
         "",
         "本編は **[Releases](../../releases)** に置いています。",
         "ここに入っているのはポスターと、アバン（掴み）のプレビューだけです。",
         "動画そのものを git に入れると、録り直すたびにリポジトリが本編1本分",
         "太っていくためです。",
         "",
         "調査メモ・台本・構図・ツールは **[%s](https://github.com/%s)**（MIT）にあります。"
         % (SOURCE_REPO, SOURCE_REPO),
         ""]
    for m in ms:
        mm, ss = int(m["duration"] // 60), int(m["duration"] % 60)
        L += ["---", "",
              "## %s" % m["heading"],
              "",
              "[![%s](%s/poster.jpg)](%s/preview.mp4)" % (m["heading"], m["dir"], m["dir"]),
              "",
              "%d分%02d秒" % (mm, ss), ""]
        for i, c in enumerate(m["chapters"], 1):
            L.append("%d. %s" % (i, c))
        L += ["",
              "[本編をダウンロード](../../releases/tag/%s)　/　"
              "[プレビュー（%s）](%s/preview.mp4)" % (m["dir"], "アバン", m["dir"]),
              ""]
    L += ["---", "",
          "## 出典", "",
          "- 地図: 出典 国土地理院（地理院タイル）",
          "- 碑文: 出典 国土地理院（自然災害伝承碑）",
          "- 音声: VOICEVOX:春日部つむぎ / VOICEVOX:雀松朱司(CV:狐狗狸ラク)",
          "- 写真: Wikimedia Commons（作者とライセンスは各回の photos.json）",
          ""]
    os.makedirs(GALLERY, exist_ok=True)
    p = os.path.join(GALLERY, "README.md")
    io.open(p, "w", encoding="utf-8").write("\n".join(L))
    print("index -> %s" % p)
    html(ms, REPO)


# 公開先。fork した人は自分のリポジトリを指す必要があるので、環境変数で上書きできる。
#   KOKO_REPO=you/your-gallery python tools/gallery.py release
REPO = os.environ.get("KOKO_REPO", "lancard-aikawa/kokogallery")

# 制作環境（このリポジトリ）。ギャラリーから戻るリンクに使う。
# ギャラリーだけ見た人がソースへ辿れないので、両方向に張る。
SOURCE_REPO = os.environ.get("KOKO_SOURCE_REPO", "lancard-aikawa/kyokoko")

# 配るのは H.264。H.265 は同じ見た目で半分になるが、Windows は標準で
# デコーダを持っておらず（有料の拡張が要る）、入っている機種と無い機種が
# 混在する。落として見る人の環境を選ばないほうを既定にする。
DIST_SUFFIX = "-web"

NL = chr(10)


def release(ep_dir, repo=None):
    """本編を Releases に添付する。タグは回のフォルダ名。

    gallery/README.md の「本編をダウンロード」がこのタグを指している。

    公開先が自分のものか先に確かめる。既定値のまま fork した人が実行すると、
    300MB を投げ終わってから 403 で落ちることになるため。
    """
    repo = repo or REPO
    me = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                        capture_output=True, text=True).stdout.strip()
    owner = repo.split("/")[0]
    if me and me != owner:
        print("公開先 %s は %s のものです（いまの認証は %s）。" % (repo, owner, me))
        print("自分のリポジトリを指してください:")
        print("  KOKO_REPO=%s/<repo名> python tools/gallery.py release" % me)
        return False
    print("公開先: %s" % repo)
    name = os.path.basename(ep_dir)
    asset = os.path.join(ep_dir, "out", "%s%s.mp4" % (name, DIST_SUFFIX))
    if not os.path.exists(asset):
        print("%s: 配布用がありません。先に compact してください" % name)
        print("  python tools/build.py --ep %s compact" % ep_dir)
        return False
    m = meta(ep_dir)
    mm, ss = int(m["duration"] // 60), int(m["duration"] % 60)
    notes = ["%s" % m["heading"], "", "%d分%02d秒　1920x1080 / H.264" % (mm, ss), ""]
    for i, c in enumerate(m["chapters"], 1):
        notes.append("%d. %s" % (i, c))
    notes += ["", "出典 国土地理院（地理院タイル・自然災害伝承碑）",
              "音声 VOICEVOX:春日部つむぎ / VOICEVOX:雀松朱司(CV:狐狗狸ラク)",
              "写真 Wikimedia Commons"]
    r = subprocess.run(["gh", "release", "view", name, "--repo", repo],
                       capture_output=True)
    if r.returncode == 0:
        subprocess.run(["gh", "release", "upload", name, asset,
                        "--repo", repo, "--clobber"], check=True)
        print("%s: 差し替えました (%.0fMB)" % (name, os.path.getsize(asset) / 1048576))
    else:
        subprocess.run(["gh", "release", "create", name, asset, "--repo", repo,
                        "--title", m["heading"], "--notes", NL.join(notes)],
                       check=True)
        print("%s: 作りました (%.0fMB)" % (name, os.path.getsize(asset) / 1048576))
    return True


def probe(path, key):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=" + key,
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def chapter_offsets(ep_dir):
    """話ごとの開始秒（通しの中での絶対秒）を返す。

    通しは ep0.mp4, ep1.mp4, ... を順に連結したものなので、先行する話の
    **映像の長さ**を足せば開始秒になる。音声の長さではない（アバンは
    タイトルの分、エンディングはクレジットの分だけ映像が長い）。
    """
    plan = plan_of(ep_dir)
    out = []
    t = 0.0
    for c in sorted(plan.get("chapters") or [], key=lambda x: x["n"]):
        f = os.path.join(ep_dir, "out", "ep%d.mp4" % c["n"])
        if not os.path.exists(f):
            continue
        out.append((t, c.get("title") or c.get("key") or "第%d話" % c["n"], c["n"]))
        t += probe(f, "duration")
    return out, t


def mmss(t):
    return "%d:%02d" % (t // 60, t % 60)


def script_credits(ep_dir):
    """script.md の「## クレジット（動画概要欄）」の中身。人が書いたもの。"""
    import re
    p = os.path.join(ep_dir, "script.md")
    if not os.path.exists(p):
        return ""
    t = io.open(p, encoding="utf-8").read()
    m = re.search(r"## クレジット[^" + NL + r"]*" + NL + r"+```" + NL + r"(.*?)" + NL + r"```",
                  t, re.S)
    return m.group(1).strip() if m else ""


def srt(ep_dir):
    """通しに合わせた字幕ファイルを書く。out/<回>.srt

    字幕は絵に焼き込んであるので、映像としては要らない。要るのは
    **YouTube の中で検索に乗ること**と、自動翻訳が効くこと。焼き込みの
    文字は画像なので、いまは1文字も検索に引っかからない。

    注意: 視聴者が字幕を ON にすると、焼き込みと二重に出る。
    """
    tl = os.path.join(ep_dir, "out", "timeline.json")
    if not os.path.exists(tl):
        print("  timeline.json がありません。先に合成してください")
        return None
    rows = json.load(io.open(tl, encoding="utf-8"))
    offs, _ = chapter_offsets(ep_dir)
    base = {n: t for t, _, n in offs}

    def stamp(t):
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return "%02d:%02d:%02d,%03d" % (h, m, int(s), round((s - int(s)) * 1000))

    lines = []
    k = 0
    for r in sorted(rows, key=lambda x: (x["episode"], x["start"])):
        if r["episode"] not in base:
            continue
        o = base[r["episode"]]
        k += 1
        lines += ["%d" % k,
                  "%s --> %s" % (stamp(o + r["start"]), stamp(o + r["end"])),
                  "%s：%s" % (r["speaker"], r["text"]),
                  ""]
    p = os.path.join(ep_dir, "out", "%s.srt" % os.path.basename(ep_dir))
    io.open(p, "w", encoding="utf-8", newline=NL).write(NL.join(lines))
    print("  字幕   %s  (%d行)" % (os.path.relpath(p, ROOT), k))
    return p


def youtube(ep_dir):
    """YouTube に上げるための材料を出す。概要欄はそのまま貼れる形にする。"""
    name = os.path.basename(ep_dir)
    m = meta(ep_dir)
    plan = plan_of(ep_dir)
    full = os.path.join(ep_dir, "out", "%s.mp4" % name)
    web = os.path.join(ep_dir, "out", "%s%s.mp4" % (name, DIST_SUFFIX))
    poster_p = os.path.join(GALLERY, name, "poster.jpg")

    if not os.path.exists(full):
        print("通しがありません: %s" % full)
        print("  python tools/build.py --ep %s all" % ep_dir)
        return 1

    offs, total = chapter_offsets(ep_dir)
    print("=" * 66)
    print("タイトル")
    print("=" * 66)
    print("%s %s" % (plan.get("program", ""), m["heading"]))
    print("")
    print("=" * 66)
    print("概要欄（ここから下をそのまま貼る）")
    print("=" * 66)
    body = ["（ここに2〜3行の紹介を書く。研究メモの「なぜここか」から起こすとよい）",
            "", "チャプター"]
    for t, label, _ in offs:
        body.append("%s %s" % (mmss(t), label))
    cr = script_credits(ep_dir)
    if cr:
        body += ["", cr]
    body += ["",
             "制作環境: https://github.com/%s" % SOURCE_REPO,
             "ギャラリー: https://lancard-aikawa.github.io/kokogallery/#%s" % name]
    print(NL.join(body))
    print("")
    print("=" * 66)
    print("上げるもの")
    print("=" * 66)
    br = probe(full, "bit_rate") / 1e6
    print("  動画   %s" % full)
    print("         %d:%02d / %.0fMB / %.1f Mbps / 1920x1080"
          % (total // 60, total % 60, os.path.getsize(full) / 1048576, br))
    if br > 12:
        print("         ※ 12 Mbps を超えている。YouTube の 1080p30 推奨は 8 Mbps")
    if os.path.exists(web):
        print("  ※ %s%s.mp4 は**上げない**。YouTube 側で再圧縮されるので二重圧縮になる"
              % (name, DIST_SUFFIX))
        print("     あれは Releases で直接配るためのもの")
    if os.path.exists(poster_p):
        try:
            from PIL import Image
            wh = Image.open(poster_p).size
        except Exception:
            wh = ("?", "?")
        print("  サムネ %s  (%sx%s)" % (poster_p, wh[0], wh[1]))
    else:
        print("  サムネ なし。python tools/gallery.py build --ep %s" % ep_dir)
    srt(ep_dir)
    print("         ※ 字幕は焼き込み済み。SRT は検索と自動翻訳のため。")
    print("           視聴者が字幕を ON にすると二重に出るので、上げるかは選ぶ")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    eps = episodes()
    if "--ep" in argv:
        i = argv.index("--ep")
        eps = [os.path.abspath(argv[i + 1])]
        del argv[i:i + 2]
    mode = argv[0] if argv else "build"
    if mode == "release":
        for e in eps:
            release(e)
    elif mode == "index":
        index([meta(e) for e in eps])
    elif mode == "youtube":
        rc = 0
        for e in eps:
            rc |= youtube(e) or 0
        sys.exit(rc)
    elif mode == "srt":
        for e in eps:
            print(os.path.basename(e))
            srt(e)
    else:
        ms = [build_one(e) for e in eps]
        index(ms if len(eps) > 1 else [meta(e) for e in episodes()])
