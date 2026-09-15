# -*- coding: utf-8 -*-
"""BGM を Wikimedia Commons から取ってきて、出典と一緒に保存する。

  python tools/bgm.py find "検索語"    候補を一覧する（CC0・パブリックドメインのみ）
  python tools/bgm.py get "ファイル名"  取得して bgm/ に保存
  python tools/bgm.py list            保存済みの一覧

方針: **表示義務のないもの（CC0・パブリックドメイン）に限る。**
立ち絵で「音声はOKでも絵はNG」という壁に当たったので、音楽でも同じ轍は踏まない。
表示義務があると、動画のどこかに常時クレジットを出し続ける必要が出てくる。

photos.py と同じ仕組みを音声に向けただけ。ライセンスは photos.py の判定を使う。
"""
import io
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photos as PH  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(ROOT, "episodes", "001-nagasaki-daikokumachi")


def probe(path):
    """尺と音量を測る。BGM として使えるかの目安にする。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,bit_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True).stdout.split()
    dur = float(out[0]) if out else 0.0
    r = subprocess.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    mean = peak = None
    for line in (r.stderr or "").splitlines():
        if "mean_volume" in line:
            mean = line.split(":")[-1].strip()
        if "max_volume" in line:
            peak = line.split(":")[-1].strip()
    return {"duration": round(dur, 1), "mean": mean, "peak": peak}


def find(query, n=20):
    d = PH.api({"action": "query", "list": "search",
                "srsearch": query + " filetype:audio", "srnamespace": 6, "srlimit": n})
    titles = [h["title"] for h in d.get("query", {}).get("search", [])]
    if not titles:
        print("見つかりませんでした")
        return []
    out = []
    for m in PH.info(titles).values():
        if not PH.is_free(m["license"]):
            continue
        out.append(m)
        print("%-52s %-16s %s" % (m["file"][:52], m["license"], (m["author"] or "")[:24]))
    if not out:
        print("（CC0・パブリックドメインのものはありませんでした）")
    return out


def manifest_path():
    return os.path.join(EP_DIR, "bgm.json")


def load():
    p = manifest_path()
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}


def get(names):
    d = os.path.join(EP_DIR, "bgm")
    os.makedirs(d, exist_ok=True)
    man = load()
    for name, meta in PH.info(names).items():
        if not PH.is_free(meta["license"]):
            print("飛ばした（表示義務あり）: %s  %s" % (name[:44], meta["license"]))
            continue
        ext = os.path.splitext(name)[1].lower() or ".ogg"
        key = "".join(c if c.isalnum() else "_" for c in name)[:56] + ext
        path = os.path.join(d, key)
        if not os.path.exists(path):
            # 音声はファイルが大きく、連続で落とすと 429 が返る。待って繰り返す。
            import time
            import urllib.error
            for wait in (0, 8, 20, 45):
                if wait:
                    time.sleep(wait)
                try:
                    r = urllib.request.urlopen(
                        urllib.request.Request(meta["url"], headers={"User-Agent": PH.UA}),
                        timeout=180)
                    with open(path, "wb") as f:
                        f.write(r.read())
                    break
                except urllib.error.HTTPError as e:
                    if e.code != 429:
                        raise
                    print("  429。待ってからやり直します: %s" % name[:40])
            else:
                print("  取得できませんでした: %s" % name[:40])
                continue
            time.sleep(2.0)
        meta["path"] = os.path.relpath(path, EP_DIR).replace("\\", "/")
        meta.update(probe(path))
        man[key] = meta
        print("取得: %-46s %-14s %.0f秒  平均%s" %
              (key[:46], meta["license"], meta["duration"], meta.get("mean")))
    with io.open(manifest_path(), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)


def show():
    man = load()
    if not man:
        print("まだ 1 曲もありません")
        return
    for k, m in sorted(man.items()):
        print("%-46s %-14s %5.0f秒  平均%s" %
              (k[:46], m["license"], m.get("duration", 0), m.get("mean")))
        print("    %s  %s" % (m.get("author") or "不明", m["page"]))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"
    if mode == "find":
        find(sys.argv[2])
    elif mode == "get":
        get(sys.argv[2:])
    else:
        show()
