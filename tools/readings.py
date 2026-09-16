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
        # 品詞は既定で固有名詞。ただし「日本人」のように組み込み辞書の語と
        # 品詞がぶつかると、priority 10 でも負ける。そのときだけ type で切り替える。
        req("/user_dict_word", {"surface": w["surface"], "pronunciation": w["kana"],
                                "accent_type": w["accent"],
                                "word_type": w.get("type", "PROPER_NOUN"),
                                "priority": 10}, "POST")
    if verbose:
        print("%d 語を登録しました" % len(cfg["words"]))
    return cfg


# tts.py と同じ形にしておく。アクセント指定 《ひ^1》 の ^1 を落とさないと、
# 読みが「ヒ、イチ」になって、碑の出てくる行が全部おかしく見える。
RUBY_RE = re.compile(r"([一-鿿゠-ヿ々〆ヶ・ー]+)《([^《》^]+)(?:\^(\d+))?》")


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
    print("漢字語 %d 種。" % len(terms))
    print()
    for t, c in sorted(terms.items(), key=lambda x: (-len(x[0]), -x[1])):
        mark = "済" if t in known else "  "
        print("  %s %-14s x%-2d %s" % (mark, t, c, kana(t)))
    print()
    print("※ 語を単独で読ませているので、文脈で決まる読みはここでは出ない。")
    print("   「同じ人」は単独なら正しいのに「同じ人たち」で ドオジジンタチ になり、")
    print("   「雨が降りました」は オリマシタ になった。どちらも語単位では見えない。")
    print("   合成の前に scan も通して、行ごとの読みを目で追うこと。")


def scan(ep_dir):
    """台詞を 1 行ずつ、文章と読みを並べて出す。

    語単位の suspects では文脈で決まる読みを拾えない。フラグメントを切り出して
    単独で読ませても、切った時点で文脈が消えるので意味がない。結局、行をそのまま
    読ませて人が目で追うのがいちばん確実。行数はたかだか百程度なので追える。
    """
    apply_words(verbose=False)
    lines = script_lines(ep_dir)
    print("%d 行。文章と読みを見比べて、合わないものを拾う。" % len(lines))
    print()
    for i, t in enumerate(lines, 1):
        print("%3d %s" % (i, t))
        print("    %s" % kana(t))


def _unused_scan(ep_dir):

    apply_words(verbose=False)
    for t in script_lines(ep_dir):
        print(t)
        print("   ", kana(t))


# 一度直したのに、次の回でまた素の漢字に戻して同じ誤読を出した語。
# 辞書では直せない（どちらの読みも正しい／活用形だけ壊れる）ので、
# 台本を書く側が気をつけるしかない。気をつけるのは無理なので、ここで止める。
# 正規表現は「行全体」に当てる。前後の語で正誤が決まるものは、
# 手がかりの語が同じ行にあるときだけ拾う（電車を降りる／手間・隙間 は正しい）。
TRAPS = [
    (r"[^ぁ-ん]の方[がをにはでのへ、。]", None,
     "「〜の方」は のほう/のかた が割れる。かな で開く", "のかた または のほう"),
    (r"降り(まし|ましょ|ます)", r"雨|雪|豪雨|降水|土砂降",
     "「雨が降りました」は オリマシタ になる（「降ると」は正しい）", "降《ふ》りました"),
    (r"[^ぁ-ん]他[がをにはのへ、。]", None,
     "「他」は ほか/た が割れる。かな で開く", "ほか"),
    (r"(の間|この間|その間|合間)[がをにはのへ、。]", None,
     "「〜の間」は あいだ/ま/かん が割れる。かな で開く", "あいだ"),
]


def check(ep_dir):
    """合成の前に、台本を機械で見る。

    2つ見る。
    1. **踏み直しやすい語**。「〜の方」や「降りました」は、一度直しても
       次の回で素の漢字に戻すと同じ誤読が出る。人の注意力に頼らない。
    2. **オウム返し**。直前の台詞から語をそのまま借りて体言止めで置く返しが
       何回あるか。1回なら驚き、5回並ぶと相槌マシンに見える。

    誤読の疑いが1つでもあれば終了コード1で落とす。合成の前に気づくため。
    """
    import re as _re
    p = os.path.join(ep_dir, "script.md")
    rows = []
    for raw in io.open(p, encoding="utf-8"):
        m = _re.match(r"^(\S+)｜(.+)$", raw.strip())
        if m:
            rows.append((m.group(1), RUBY_RE.sub(r"", m.group(2)), m.group(2)))

    bad = 0
    print("■ 踏み直しやすい語")
    for i, (who, shown, raw) in enumerate(rows, 1):
        for pat, need, why, how in TRAPS:
            if _re.search(pat, raw) and (need is None or _re.search(need, raw)):
                bad += 1
                print("  %3d %s" % (i, shown[:54]))
                print("      %s  →  %s" % (why, how))
    if not bad:
        print("  なし")

    print()
    print("■ オウム返し（直前の台詞から語を借りて体言止め）")
    def core(x):
        return _re.sub(r"[。、！？…「」　 ]", "", x)
    echo = []
    for i in range(1, len(rows)):
        who, cur, _ = rows[i]
        pw, prev, _ = rows[i - 1]
        if who == pw:
            continue
        c, pv = core(cur), core(prev)
        if not c or len(c) > 14:
            continue
        best = ""
        for a in range(len(c)):
            for b in range(a + 2, len(c) + 1):
                if c[a:b] in pv and (b - a) > len(best):
                    best = c[a:b]
        # 感嘆符・疑問符が付くものは「反応」なので数えない。
        # 借りた語を疑問や言い換えに変えているものも、型が違うので外す。
        if _re.search(r"[！？]", cur):
            continue
        if _re.search(r"(というと|ってこと|んですね|んですか|ですか)", cur):
            continue
        if best and len(best) >= max(2, len(c) * 0.45):
            echo.append((i + 1, who, cur, best))
    for n, who, cur, b in echo:
        print("  %3d %s｜%s   ← 借りた語「%s」" % (n, who, cur, b))
    print("  %d 件。1話あたり1回までが目安。多いときは返しの型を散らす"
          % len(echo))
    print("  ※ 引用の反芻や、意図した繰り返しはここに出る。人が見て選ぶこと")
    print("  （借りて評価を足す／自分の言葉に言い換える／疑問にする／黙る）")

    if bad:
        print()
        sys.exit("誤読の疑いが %d 件。直してから合成すること。" % bad)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "apply"
    ep = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_EP
    if mode == "apply":
        apply_words()
    elif mode == "diff":
        diff(ep)
    elif mode == "check":
        check(ep)
    elif mode == "scan":
        scan(ep)
    elif mode == "suspects":
        suspects(ep)
    elif mode == "phrases":
        phrases(sys.argv[2])
    else:
        sys.exit(__doc__)
