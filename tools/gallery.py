# -*- coding: utf-8 -*-
"""ギャラリー用の軽い素材を書き出す。

  python tools/gallery.py build              全部の回のポスターとプレビューを作る
  python tools/gallery.py build --ep <dir>   1回だけ
  python tools/gallery.py index              gallery/README.md を書く
  python tools/gallery.py release            本編を GitHub Releases に上げる
  python tools/gallery.py release --ep <dir> 1回だけ

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


def index(ms):
    """gallery/README.md。GitHub の Releases に置いた本編へ誘導する。"""
    L = ["# まちぶら",
         "",
         "〒や町名を指定すると、その町の遺構・歴史建造物・地名の由来にまつわる",
         "「碑」の話を集め、読み上げシナリオを作り、VOICEVOX と地図で動画にする。",
         "",
         "本編は **[Releases](../../releases)** に置いています。",
         "ここに入っているのはポスターと、アバン（掴み）のプレビューだけです。",
         "動画そのものを git に入れると、録り直すたびにリポジトリが本編1本分",
         "太っていくためです。",
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


REPO = "lancard-aikawa/machibura-gallery"

# 配るのは H.264。H.265 は同じ見た目で半分になるが、Windows は標準で
# デコーダを持っておらず（有料の拡張が要る）、入っている機種と無い機種が
# 混在する。落として見る人の環境を選ばないほうを既定にする。
DIST_SUFFIX = "-web"

NL = chr(10)


def release(ep_dir, repo=REPO):
    """本編を Releases に添付する。タグは回のフォルダ名。

    gallery/README.md の「本編をダウンロード」がこのタグを指している。
    """
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
    else:
        ms = [build_one(e) for e in eps]
        index(ms if len(eps) > 1 else [meta(e) for e in episodes()])
