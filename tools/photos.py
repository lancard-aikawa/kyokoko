# -*- coding: utf-8 -*-
"""Wikimedia Commons から写真を取ってきて、出典と一緒に保存する。

  python tools/photos.py find "検索語"        候補を一覧する（ライセンスつき）
  python tools/photos.py free "検索語"        CC0・パブリックドメインだけ一覧する
  python tools/photos.py get "ファイル名" ...   取得して photos/ に保存
  python tools/photos.py list                 保存済みの一覧と出典

取得した画像は episodes/<ep>/photos/ に置き、photos.json に
ライセンス・作者・出典 URL を残す。動画にはこの情報を焼き込む。
CC BY / CC BY-SA は表示義務があるので、記録を欠かさないこと。
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

API = "https://commons.wikimedia.org/w/api.php"
UA = "MachiBura/0.1 (personal video project; local use)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 対象の回。--ep <dir> で切り替える。指定が無ければ episodes/ の最初の回。
def _default_ep():
    d = os.path.join(ROOT, "episodes")
    xs = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))
    return os.path.join(d, xs[0]) if xs else d


EP_DIR = _default_ep()


def use_episode(path):
    global EP_DIR
    EP_DIR = os.path.abspath(path)
    return EP_DIR


def api(params):
    params = dict(params, format="json")
    for _ in range(5):
        try:
            u = API + "?" + urllib.parse.urlencode(params)
            r = urllib.request.urlopen(
                urllib.request.Request(u, headers={"User-Agent": UA}), timeout=45)
            d = json.load(io.TextIOWrapper(r, encoding="utf-8"))
            time.sleep(1.4)          # Commons は連打すると 429 を返す
            return d
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(8)
                continue
            raise
    raise RuntimeError("Commons への問い合わせに失敗しました")


def strip_html(s):
    import re
    s = re.sub(r"<[^>]+>", "", s or "")
    return " ".join(s.split())


def info(titles):
    """ファイル名の一覧 -> ライセンス等のメタ情報"""
    titles = [t if t.startswith("File:") else "File:" + t for t in titles]
    d = api({"action": "query", "titles": "|".join(titles), "prop": "imageinfo",
             "iiprop": "url|extmetadata|size"})
    out = {}
    for pg in (d.get("query", {}).get("pages") or {}).values():
        ii = (pg.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata", {})
        name = pg["title"].replace("File:", "")
        out[name] = {
            "file": name,
            "license": strip_html(em.get("LicenseShortName", {}).get("value")),
            "author": strip_html(em.get("Artist", {}).get("value")),
            "credit": strip_html(em.get("Credit", {}).get("value")),
            "url": ii.get("url"),
            "page": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(
                pg["title"].replace(" ", "_")),
            "width": ii.get("width"), "height": ii.get("height"),
        }
    return out


# 表示義務も法人制限もないライセンス。立ち絵で懲りたので、写真はここを優先する。
FREE = ("cc0", "public domain", "pd")


def is_free(lic):
    l = (lic or "").lower()
    return any(k in l for k in FREE)


def find(query, n=20, only_free=False):
    d = api({"action": "query", "list": "search", "srsearch": query,
             "srnamespace": 6, "srlimit": n})
    titles = [h["title"] for h in d.get("query", {}).get("search", [])]
    if not titles:
        print("見つかりませんでした")
        return []
    out = []
    for m in info(titles).values():
        if only_free and not is_free(m["license"]):
            continue
        out.append(m)
        print("%-54s %-16s %sx%s" % (m["file"][:54], m["license"], m["width"], m["height"]))
        if m["author"]:
            print("    作者: %s" % m["author"][:60])
    if only_free and not out:
        print("（CC0・パブリックドメインのものは見つかりませんでした）")
    return out


def manifest_path():
    return os.path.join(EP_DIR, "photos.json")


def load_manifest():
    p = manifest_path()
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}


def get(names, key_prefix=""):
    d = os.path.join(EP_DIR, "photos")
    os.makedirs(d, exist_ok=True)
    man = load_manifest()
    for name, meta in info(names).items():
        ext = os.path.splitext(name)[1].lower() or ".jpg"
        key = key_prefix + "".join(c if c.isalnum() else "_" for c in name)[:60] + ext
        path = os.path.join(d, key)
        if not os.path.exists(path):
            # 原寸は 1 万px を超えるものもあるので幅 1920 に縮めて取る
            thumb = api({"action": "query", "titles": "File:" + name, "prop": "imageinfo",
                         "iiprop": "url", "iiurlwidth": 1920})
            pg = list((thumb.get("query", {}).get("pages") or {}).values())[0]
            src = (pg.get("imageinfo") or [{}])[0].get("thumburl") or meta["url"]
            r = urllib.request.urlopen(
                urllib.request.Request(src, headers={"User-Agent": UA}), timeout=90)
            with open(path, "wb") as f:
                f.write(r.read())
            time.sleep(0.8)
        meta["path"] = os.path.relpath(path, EP_DIR).replace("\\", "/")
        man[key] = meta
        print("取得: %s  (%s)" % (key, meta["license"]))
    with io.open(manifest_path(), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)


def show():
    man = load_manifest()
    if not man:
        print("まだ 1 枚もありません")
        return
    for k, m in sorted(man.items()):
        print("%-46s %-16s" % (k[:46], m["license"]))
        print("    %s" % m["page"])
        if m["author"]:
            print("    作者: %s" % m["author"][:70])


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--ep" in argv:
        i = argv.index("--ep")
        use_episode(argv[i + 1])
        del argv[i:i + 2]
    sys.argv = [sys.argv[0]] + argv
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"
    if mode == "find":
        find(sys.argv[2])
    elif mode == "free":
        find(sys.argv[2], n=30, only_free=True)
    elif mode == "get":
        get(sys.argv[2:])
    else:
        show()
