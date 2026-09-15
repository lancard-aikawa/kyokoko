# -*- coding: utf-8 -*-
"""VOICEVOX の読みを補正する。

  python tools/readings.py apply           readings.json をエンジンに流し込む（全入れ替え）
  python tools/readings.py diff [ep_dir]   補正の前後で読みがどう変わるかを見る
  python tools/readings.py scan [ep_dir]     台詞1行ずつの読みを全部出す
  python tools/readings.py suspects [ep_dir] 台詞中の漢字語を全部さらって読みを並べる
  python tools/readings.py phrases "<台詞>" アクセント句と核の位置を見る

**diff を必ず見ること。**ある語を直すと別の語が巻き添えで壊れる。
実例: 「碑」を イシブミ→ヒ に直したら「石碑」が セキヒ→イシヒ になった。
diff は台詞と guard 語の読みを補正前後で比べ、変わったものを全部並べる。
狙った変化か巻き添えかは人間が判断する。
"""
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

E = "http://127.0.0.1:50021"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JSON_PATH = os.path.join(HERE, "readings.json")
DEFAULT_EP = os.path.join(ROOT, "episodes", "001-nagasaki-daikokumachi")

LINE_RE = re.compile(r"^([^｜\[\s]+)｜(.+)$")


def req(path, params=None, method="GET", data=b""):
    url = E + path + ("?" + urllib.parse.urlencode(params) if params else "")
    r = urllib.request.Request(url, data=data if method == "POST" else None, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        body = resp.read()
    return body


def kana(text, speaker=52):
    return json.loads(req("/audio_query", {"text": text, "speaker": speaker},
                          "POST"))["kana"]


def load():
    return json.load(io.open(JSON_PATH, encoding="utf-8"))


def current_dict():
    return json.loads(req("/user_dict"))


def clear():
    for uid in list(current_dict().keys()):
        req("/user_dict_word/" + uid, method="DELETE")


def apply_words(verbose=True):
    """辞書を空にしてから readings.json を入れ直す。重複が増えないようにするため。"""
    cfg = load()
    clear()
    for w in cfg["words"]:
        req("/user_dict_word", {"surface": w["surface"], "pronunciation": w["kana"],
                                "accent_type": w["accent"], "word_type": "PROPER_NOUN",
                                "priority": 10}, "POST")
    if verbose:
        print("%d 語を登録しました" % len(cfg["words"]))
    return cfg


RUBY_RE = re.compile(r"([一-鿿゠-ヿ々〆ヶ・ー]+)《([^《》]+)》")


def script_lines(ep_dir):
    """実際に読み上げる文字列（碑《ひ》 は ひ に展開したもの）を返す。"""
    p = os.path.join(ep_dir, "script.md")
    out = []
    for raw in io.open(p, encoding="utf-8"):
        m = LINE_RE.match(raw.strip())
        if m and m.group(1) in ("つむぎ", "朱司"):
            out.append(RUBY_RE.sub(r"\2", m.group(2).strip()))
    return out


def diff(ep_dir):
    cfg = load()
    targets = cfg["guard"] + script_lines(ep_dir)

    clear()
    before = [kana(t) for t in targets]
    apply_words(verbose=False)
    after = [kana(t) for t in targets]

    changed = {t: (b, a) for t, b, a in zip(targets, before, after) if b != a}
    print("補正した語 %d / 照合 %d / 読みが変わった %d"
          % (len(cfg["words"]), len(targets), len(changed)))

    print()
    print("--- guard 語（巻き添えの検出用）---")
    bad = []
    for t in cfg["guard"]:
        if t in changed:
            b, a = changed[t]
            bad.append(t)
            print("  [変] %-16s %s  ->  %s" % (t, b, a))
        else:
            print("  [同] %s" % t)
    print()
    if bad:
        print("!! guard 語の読みが変わった: " + " / ".join(bad))
        print("   狙った変化か巻き添えか判断し、巻き添えなら readings.json に補正を足す。")
    else:
        print("guard 語はすべて据え置き。巻き添えなし。")

    lines = [t for t in changed if t not in cfg["guard"]]
    print()
    print("--- 台詞で読みが変わった行: %d 行 ---" % len(lines))
    for t in lines:
        print("  ", t[:60])


def phrases(text):
    """台詞のアクセント句を並べて見せる。^数字 で指定する核の位置を決めるのに使う。"""
    apply_words(verbose=False)
    q = json.loads(req("/audio_query", {"text": text, "speaker": 52}, "POST"))
    for i, ap in enumerate(q["accent_phrases"]):
        moras = "".join(m["text"] for m in ap["moras"])
        marks = "".join("^" if j + 1 == ap["accent"] else " " for j in range(len(ap["moras"])))
        print("  [%d] %s   核=%d  (0 は平板)" % (i, moras, ap["accent"]))
        print("      %s" % marks)


def suspects(ep_dir):
    """台詞に出てくる漢字語を全部さらって、読みを並べる。

    「碑」も「側」も、指摘されるまで気づかなかった。気づいた語だけ直していては
    取りこぼす。台詞から漢字の連なりを機械的に抜き出し、読みを付けて並べる。
    人が目で見て変なものを拾う。辞書に入れた語には印を付けて、未確認の語を
    見分けられるようにする。
    """
    import collections
    apply_words(verbose=False)
    known = {w["surface"] for w in load()["words"]}
    terms = collections.Counter()
    for line in script_lines(ep_dir):
        for t in re.findall(r"[一-鿿々〆ヶ]{1,12}", line):
            terms[t] += 1
    print("漢字語 %d 種。辞書に入っていないものを中心に見ること。" % len(terms))
    print()
    for t, c in sorted(terms.items(), key=lambda x: (-len(x[0]), -x[1])):
        mark = "済" if t in known else "  "
        print("  %s %-14s x%-2d %s" % (mark, t, c, kana(t)))


def scan(ep_dir):
    apply_words(verbose=False)
    for t in script_lines(ep_dir):
        print(t)
        print("   ", kana(t))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "apply"
    ep = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_EP
    if mode == "apply":
        apply_words()
    elif mode == "diff":
        diff(ep)
    elif mode == "scan":
        scan(ep)
    elif mode == "suspects":
        suspects(ep)
    elif mode == "phrases":
        phrases(sys.argv[2])
    else:
        sys.exit(__doc__)
