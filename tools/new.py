# -*- coding: utf-8 -*-
"""新しい回の雛形を作る。

  python tools/new.py 006 isahaya-ikiriki "諫早市 多良見町伊木力"
  python tools/new.py 001 mymachi "長崎市大黒町" --center 32.7476,129.8686

作るもの（episodes/<番号>-<slug>/ の下）:

  episode.json   企画。配役・口調・BGM・間の既定値が入る
  script.md      台本の骨。アバン＋第1話＋エンディングで14行
  shots.py       ショットの構図。上の14行に合わせてある
  photos.json    空。写真を足すと tools/photos.py が書き込む
  photos/        写真の置き場

**雛形はそのまま通ります。**VOICEVOX を起動していれば、作った直後に

  python tools/readings.py check episodes/006-isahaya-ikiriki
  python tools/tts.py        episodes/006-isahaya-ikiriki
  python tools/build.py --ep episodes/006-isahaya-ikiriki all

まで走って、40秒ほどの動画ができます。中身を自分の町の話に差し替えるのは
そのあとで。書式は docs/episode-files.md にあります。

町の中心は国土地理院の住所検索から取る。引けなければ --center で渡す。
番号は打った値をそのまま使うので、設定ファイルは要らない。自分の第一話から
始めたい人は、既存の回を消してから 001 を指定する。
"""
import io
import json
import os
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GSI = "https://msearch.gsi.go.jp/address-search/AddressSearch?q="
UA = "kokogallery/0.1 (personal video project; local use)"


def geocode(town):
    """町名から緯度経度を引く。国土地理院の住所検索。見つからなければ None。"""
    url = GSI + urllib.parse.quote(town)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        d = json.load(urllib.request.urlopen(req, timeout=20))
    except Exception as e:
        print("住所検索に失敗しました: %s" % e)
        return None
    if not d:
        return None
    lon, lat = d[0]["geometry"]["coordinates"]
    print("住所検索: %s -> %.6f, %.6f" % (d[0]["properties"]["title"], lat, lon))
    return lat, lon


EPISODE_JSON = {
    "_comment": [
        "この回の企画。Claude との会話で決めたことをここに集める。",
        "ブラウザUI の「企画」タブが読み書きする。",
        "行ごとの細かい調整は voice.json、文章とふりがなは script.md、",
        "ショットの構図は shots.py が持つ。ここはその上流。",
    ],
    "id": "@@ID@@",
    "program": "今日はここに",
    "town": {
        "name": "@@TOWN@@",
        "postal": "",
        "center": [0.0, 0.0],
        "note": "この回で何を芯にするか。調べたことは research.md に書く",
    },
    "title": "（題は未定）",
    # YouTube の概要欄の頭に置く紹介。**1行1文で書く**（改行がそのまま出るので、
    # 文の途中で折ると読み手の側で行が割れて見える）。dist/ に書き出される。
    "summary": [
        "（この回を2〜3行で。台本に実際に出てくる事実だけで書く）",
    ],
    # YouTube に上げたら動画 ID を入れる。ギャラリーと README のリンクに使う
    "youtube": "",
    "mood": "この回の調子。断定しないこと・伏せること・数字の扱いなど、書く前に決めた方針を書く",
    "cast": {
        "つむぎ": {
            "role": "探訪役",
            "speaker": 8,
            "label": "春日部つむぎ / ノーマル",
            "tone": "敬体・明るい・短い。現地で気づき、素朴に驚き、問いを投げる",
            "color": [255, 214, 120],
            "side": "right",
            "speedScale": 0.98,
            "intonationScale": 1.0,
            "pitchScale": 0.0,
            "credit": "VOICEVOX:春日部つむぎ",
        },
        "朱司": {
            "role": "案内人",
            "speaker": 52,
            "label": "雀松朱司 / ノーマル",
            "tone": "敬体・落ち着き・やや講義調。地形と歴史を解きほぐし、答えを出す",
            "color": [150, 210, 255],
            "side": "left",
            "speedScale": 0.98,
            "intonationScale": 1.0,
            "pitchScale": 0.0,
            "credit": "VOICEVOX:雀松朱司(CV:狐狗狸ラク)",
        },
    },
    "chapters": [
        {"n": 0, "key": "アバン", "title": "", "bgm": None},
        {"n": 1, "key": "第1話", "title": "（話の題）", "bgm": None},
        {"n": 99, "key": "エンディング", "title": "", "bgm": None},
    ],
    "timing": {"lead_in": 0.4, "tail": 0.9, "gap_same": 0.35,
               "gap_switch": 0.55, "gap_cut": 1.2},
    "bgm": {
        "policy": "表示義務のないもの（CC0 相当）に限る。法人利用や宣伝利用で詰まらないようにする。",
        "default": "Ambient_music_test__Yamaha_CK61_flac.flac",
        "volume": 0.12,
        "duck": 0.5,
        "credit": "Wilfredor / CC0（Wikimedia Commons）",
    },
    "theme": "（石碑 / 土木 / 地形 / 史跡 のどれか）",
    "style": "（対話 / クエスチョン）",
}

SCRIPT_MD = """# 第@@NO@@回 @@TOWN@@ —「（題は未定）」

- 話者: 探訪役＝春日部つむぎ（ノーマル）／案内人＝雀松朱司（ノーマル）
- アバン＋第1話＋エンディング（**雛形**。話を足すときは episode.json の chapters も足す）
- テーマ: （石碑 / 土木 / 地形 / 史跡 のどれか）
- 形式: （対話 / クエスチョン）
- トーン: 断定しないこと・伏せること・数字の扱いを、書く前に決めて書いておく

台詞行の書式: `話者名｜台詞`（全角縦棒区切り。TTS はこの行だけを拾う）
話者名は つむぎ / 朱司。ふりがなは `碑《ひ》`、考える時間は `間｜3.2`。
くわしくは docs/episode-files.md。

---

## アバン

### カット0-1 つかみ

地図: 淡色地図 z15 / 町の中心

つむぎ｜ここが、@@TOWN@@ なんですね。
朱司｜そうです。今日はここに来ています。
つむぎ｜なにか、引っかかるものがありますか。
朱司｜あります。それを順に見ていきましょう。

---

## 第1話 （話の題）

### カット1-1 現地の違和感

地図: 淡色地図 z15 / 町の中心

つむぎ｜この道、ゆるく曲がってますね。
朱司｜曲がっている理由は、地面の側にあります。
つむぎ｜地面。
朱司｜ここは昔、いまとは違うものでした。
つむぎ｜……何だったんですか。
朱司｜それを、この地図で見てみましょう。

---

## エンディング

### カット9-1 締め

地図: 淡色地図 z15 / 町の中心

朱司｜上から見てみましょう。
つむぎ｜形が、残ってますね。
朱司｜町は、何度も書き換えられています。
つむぎ｜でも、残るものは残るんですね。

---

## クレジット（動画概要欄）

```
音声: VOICEVOX:春日部つむぎ / VOICEVOX:雀松朱司(CV:狐狗狸ラク)
音楽: Wilfredor / CC0（Wikimedia Commons）
地図: 出典 国土地理院（地理院タイル）
　　　https://maps.gsi.go.jp/development/ichiran.html
```

## 収録前チェック

- [ ] `python tools/readings.py check <ep_dir>` を通す（誤読があれば落ちる）
- [ ] `python tools/readings.py scan <ep_dir>` を目で追い、**声にも出す**
- [ ] 固有名詞の読み（地名・人名・熟語）
- [ ] 断定していないこと
"""

SHOTS_PY = '''# -*- coding: utf-8 -*-
"""第@@NO@@回 @@TOWN@@ のショット定義。

時刻は秒で直書きせず、台詞番号から引く（T=行の頭, TE=行の尻）。
音声の頭には LEAD_IN 0.4 秒、尻には TAIL 0.9 秒の余白がある。各話の最初の
ショットは 0 秒から始め、最後のショットは TE(最終行, 0.9) で終わらせて
音声の全長とそろえる。

**ズームは地上の広さから決める。**緯度33度あたり、画面 1920px で入る横幅:

    z12 62km / z13 31km / z14 15km / z15 7.7km / z16 3.8km / z17 1.9km

camera の scale はここに掛かる（大きいほど広い）。主役の大きさを決めてから選ぶ。
レイヤごとに使えるズーム範囲が違う（tiles.LAYERS）。範囲外を頼むと、下限は
切り上げて欠測が黒く出て、上限は切り下げて拡大されるのでぼやける。

書式は docs/episode-files.md にある。
"""

# --- 地点 -------------------------------------------------------------
CENTER = (@@LAT@@, @@LON@@)      # 町の中心。国土地理院の住所検索から入れた
TOWN = "@@TOWN@@"


def credit_lines(ep_dir=None):
    """出典の一覧。photos.json と episode.json から組み立てる。"""
    import json
    import os
    base = ep_dir or os.path.dirname(os.path.abspath(__file__))
    out = [("h", "音声"),
           ("b", "VOICEVOX:春日部つむぎ"),
           ("b", "VOICEVOX:雀松朱司（CV:狐狗狸ラク）"),
           ("gap", ""),
           ("h", "地図・空中写真"),
           ("b", "出典 国土地理院（地理院タイル）")]
    plan = os.path.join(base, "episode.json")
    if os.path.exists(plan):
        b = (json.load(open(plan, encoding="utf-8")).get("bgm") or {})
        if b.get("default") and b.get("credit"):
            out += [("gap", ""), ("h", "音楽"), ("b", b["credit"])]
    p = os.path.join(base, "photos.json")
    if os.path.exists(p):
        metas = json.load(open(p, encoding="utf-8"))
        seen = []
        for m in metas.values():
            a = (m.get("author") or "不明").strip()
            h = len(a) // 2
            if h and a[:h] == a[h:]:
                a = a[:h]
            line = "%s / %s" % (a, m.get("license") or "?")
            if line not in seen:
                seen.append(line)
        # 写真を1枚も使っていない回では見出しを出さない
        if seen:
            out += [("gap", ""), ("h", "写真 — Wikimedia Commons")]
            out += [("b", x) for x in seen]
    return out


def build(timeline):
    S = {r["index"]: r["start"] for r in timeline}
    E = {r["index"]: r["end"] for r in timeline}
    T = lambda i, d=0.0: S[i] + d      # noqa: E731
    TE = lambda i, d=0.0: E[i] + d     # noqa: E731

    def lb(text, pt, t, **kw):
        d = {"text": text, "lat": pt[0], "lon": pt[1], "from": t}
        d.update(kw)
        return d

    def note(text, a, b):
        return {"text": text, "from": a, "to": b}

    def photo(key, a, b, kb=None, notes=None):
        d = {"type": "photo", "t0": a, "t1": b, "photo": key,
             "kb": kb or [[a, 1.20, 0.5, 0.5], [b, 1.04, 0.5, 0.5]]}
        if notes:
            d["notes"] = notes
        return d

    def question(lines, q, ans, tag="クエスチョン"):
        """札は問いを読み始めたところから、答えが出るまで。
        考える時間は TE(問いの行) 〜 T(その次の行)。"""
        return {"text": lines, "from": T(q, 0.3), "to": T(ans, 0.2),
                "think": [TE(q), T(q + 1)], "tag": tag}

    pale = {"id": "pale"}
    hill = lambda k: {"id": "hillshademap", "alpha": k}       # noqa: E731
    relief = lambda k: {"id": "relief", "alpha": k}           # noqa: E731
    now = lambda k=None: ({"id": "seamlessphoto"} if k is None  # noqa: E731
                          else {"id": "seamlessphoto", "alpha": k})

    # --- アバン --------------------------------------------------------
    # 台詞は 1〜4 行目。最後にタイトルを出してから第1話へ渡す。
    ep0 = [
        {"t0": 0.0, "t1": TE(4, 5.4), "zoom": 15,
         "camera": [[0.0, CENTER[0], CENTER[1], 1.25],
                    [TE(4), CENTER[0], CENTER[1], 0.95],
                    [TE(4, 5.4), CENTER[0], CENTER[1], 0.90]],
         "layers": [pale, hill([[0.0, 0.30]])],
         "labels": [lb(TOWN, CENTER, 1.0)]},
    ]
    ep0[0]["title"] = {"main": "今日はここに",
                       "sub": "第@@NO@@回　@@TOWN@@ —「（題は未定）」",
                       "from": TE(4, 0.8), "to": TE(4, 4.8),
                       "size": 108, "subsize": 34, "dim": 150, "y": 0.44}

    # --- 第1話 --------------------------------------------------------
    # 台詞は 5〜10 行目。レイヤを差し替えて「ここが何だったか」を見せる。
    ep1 = [
        {"t0": 0.0, "t1": T(8), "zoom": 15,
         "camera": [[0.0, CENTER[0], CENTER[1], 1.10],
                    [T(8), CENTER[0], CENTER[1], 0.92]],
         "layers": [pale, hill([[0.0, 0.30]])],
         "labels": [lb(TOWN, CENTER, 0.8)],
         "title": {"main": "第一話", "sub": "（話の題）",
                   "from": 0.3, "to": 4.6, "size": 76, "subsize": 38, "dim": 110},
         "notes": [note("ここに年や数字の札を置く", T(6, 0.8), TE(6))]},

        {"t0": T(8), "t1": TE(10, 0.9), "zoom": 15,
         "camera": [[T(8), CENTER[0], CENTER[1], 0.92],
                    [TE(10, 0.9), CENTER[0], CENTER[1], 1.05]],
         "layers": [pale, relief([[T(8), 0.0], [T(8, 1.2), 0.70]])],
         "notes": [note("色別標高図に切り替えた", T(9, 0.6), TE(9))]},
    ]

    # --- エンディング --------------------------------------------------
    # 台詞は 11〜14 行目。最後にクレジットを流す。
    end = [
        {"t0": 0.0, "t1": TE(14, 9.4), "zoom": 15,
         "camera": [[0.0, CENTER[0], CENTER[1], 1.00],
                    [TE(14), CENTER[0], CENTER[1], 1.20],
                    [TE(14, 9.4), CENTER[0], CENTER[1], 1.22]],
         "layers": [now()],
         "credits": {"lines": credit_lines(), "from": TE(14, 4.6),
                     "to": TE(14, 8.6), "dim": 165}},
    ]

    return {0: ep0, 1: ep1, 99: end}
'''


def write(path, text):
    if os.path.exists(path):
        print("  すでにあります（上書きしません）: %s" % path)
        return False
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)
    print("  書きました: %s" % os.path.relpath(path, ROOT))
    return True


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip())
        return 1
    no, slug, town = argv[0], argv[1], argv[2]
    if not no.isdigit():
        print("番号は数字で: 例 006")
        return 1
    no = "%03d" % int(no)

    center = None
    if "--center" in argv:
        raw = argv[argv.index("--center") + 1]
        lat, lon = [float(x) for x in raw.replace(" ", "").split(",")]
        center = (lat, lon)
    if center is None:
        center = geocode(town)
    if center is None:
        print("町の中心が引けませんでした。--center 緯度,経度 で渡してください:")
        print('  python tools/new.py %s %s "%s" --center 32.7476,129.8686'
              % (no, slug, town))
        return 1

    ep_id = "%s-%s" % (no, slug)
    d = os.path.join(ROOT, "episodes", ep_id)
    if os.path.isdir(d) and os.listdir(d):
        print("すでに中身があります: %s" % d)
        return 1
    os.makedirs(os.path.join(d, "photos"), exist_ok=True)
    print("回を作ります: episodes/%s  中心 %.6f, %.6f" % (ep_id, center[0], center[1]))

    plan = json.loads(json.dumps(EPISODE_JSON))   # 深いコピー
    plan["id"] = ep_id
    plan["town"]["name"] = town
    plan["town"]["center"] = [round(center[0], 6), round(center[1], 6)]
    write(os.path.join(d, "episode.json"),
          json.dumps(plan, ensure_ascii=False, indent=2) + "\n")

    def fill(t):
        return (t.replace("@@NO@@", no).replace("@@TOWN@@", town)
                 .replace("@@ID@@", ep_id)
                 .replace("@@LAT@@", "%.6f" % center[0])
                 .replace("@@LON@@", "%.6f" % center[1]))

    write(os.path.join(d, "script.md"), fill(SCRIPT_MD))
    write(os.path.join(d, "shots.py"), fill(SHOTS_PY))
    write(os.path.join(d, "photos.json"), "{}\n")

    print("")
    print("次の手順（VOICEVOX を起動してから）:")
    print("  python tools/readings.py check episodes/%s" % ep_id)
    print("  python tools/tts.py        episodes/%s" % ep_id)
    print("  python tools/build.py --ep episodes/%s all" % ep_id)
    print("")
    print("調査メモは research.md に自分で書く（雛形は作らない）。")
    print("書式は docs/episode-files.md。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
