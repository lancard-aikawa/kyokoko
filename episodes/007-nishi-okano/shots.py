# -*- coding: utf-8 -*-
"""第007回 横浜 岡野 のショット定義。

時刻は秒で直書きせず、台詞番号から引く（T=行の頭, TE=行の尻）。
音声の頭には LEAD_IN 0.4 秒、尻には TAIL 0.9 秒の余白がある。各話の最初のショットは
0 秒から始め、最後のショットは TE(最終行, 0.9) で終わらせて音声の全長とそろえる。

テーマは地形。明治期の低湿地（swale）の水色で袖ヶ浦の入江を見せ、1860年の貞秀の
錦絵で「海沿いの土手の道」と「ナベ新田の塩焼屋」を見せる。エンディングは第006回と
同じく、同じ画角で 明治の海 → 1945〜50年 → いま と差し替える。

**swale の上限は z16。**寄るのは camera の scale で。
**関東の swale は位置の誤差が大きい**（地理院の凡例の注）。輪郭に点を重ねて
「ここが縁」と言わない。

錦絵の写真は横 1920px に縮めて取ってある（photos.py）。寄る位置は、絵の中の
比率 (fx, fy) から focus() で kb に直す。

緯度35.5度、画面 1920px で入る横幅:
    z9 240km / z13 30km / z14 15km / z15 7.5km / z16 3.7km / z17 1.9km
"""

# --- 地点（OSM。現地実測ではない） ------------------------------------
ARATAMA  = (35.4642023, 139.6142257)   # 新田間橋
HIRANUMA = (35.4618591, 139.6180379)   # 元平沼橋（1859年の平沼橋の位置）
OKANO    = (35.4617499, 139.6132758)   # 岡野公園（岡野二丁目）
YOKO     = (35.4660109, 139.6226361)   # 横浜駅
KITASAI  = (35.4675485, 139.6170444)   # 北幸
MINASAI  = (35.4650943, 139.6192504)   # 南幸
DAIMACHI = (35.4706230, 139.6235871)   # 神奈川台（台町）
HODOGAYA = (35.4439908, 139.5954260)   # 保土ヶ谷宿本陣跡
KAIKO    = (35.4475178, 139.6438048)   # 横浜開港資料館（開港場のあたり）
FUJI     = (35.3606, 138.7274)         # 富士山頂。新田間橋まで 81.2km
MID      = (35.4640, 139.6170)         # 新田間橋と横浜駅西口の中ほど

# --- 写真（photos.json のキー）と、取ってきたファイルの実寸 ------------
P_NOW    = "AratamaBrdg_jpg.jpg"
P_NABEYA = [k for k in ["NDL1306199_新田間橋ヨリナベヤ新田塩焼屋并神奈川の台かるい沢其海岸を見る此新田間橋ハ東海道大通リ青木町芝生村其.jpg"]][0]
P_HONUMA = "Hon_numaBashi1860_jpg.jpg"
P_DAI    = "Shin_Yokohama_St_1860_jpg.jpg"
SIZE = {P_NOW: (1920, 2560), P_NABEYA: (1920, 1280),
        P_HONUMA: (1920, 1355), P_DAI: (1920, 2821)}


def focus(key, t, s, fx, fy, zmax):
    """絵の中の (fx, fy)（0〜1）を画面の中央に置く kb の1点を返す。

    clip.render_photo_shot の切り出し方をそのまま逆算する。zmax はそのショットの
    kb の最大 s（clip はそれで下地の拡大率を決める）。
    """
    w, h = SIZE[key]
    k = max(1920.0 / w, 1080.0 / h) * max(zmax, 1.05)
    bw, bh = w * k, h * k
    cw, ch = 1920.0 * s, 1080.0 * s
    cx = (fx * bw - cw / 2) / (bw - cw) if bw > cw else 0.5
    cy = (fy * bh - ch / 2) / (bh - ch) if bh > ch else 0.5
    return [t, s, max(0.0, min(1.0, cx)), max(0.0, min(1.0, cy))]


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
        out += [("gap", ""), ("h", "写真・絵 — Wikimedia Commons")]
        seen = set()
        for m in json.load(open(p, encoding="utf-8")).values():
            a = (m.get("author") or "不明").strip()
            if a in ("貞秀", "五雲亭貞秀（歌川貞秀）"):
                a = "歌川貞秀"
            line = "%s / %s" % (a, m.get("license") or "?")
            if line not in seen:
                seen.add(line)
                out.append(("b", line))
        out.append(("b", "（錦絵の原本 国立国会図書館）"))
    out += [("gap", ""), ("h", "参考"),
            ("b", "『保土ケ谷区郷土史』（1938）　石野瑛『横浜近郊文化史』（1927）"),
            ("b", "『今昔横浜案内』（1929）"),
            ("b", "横浜市「YOKOHAMA RIVER のはなし」第十稿（2022）"),
            ("b", "横浜市西区「西区の町名とそのあゆみ」")]
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

    def photo(key, a, b, kb, notes=None):
        d = {"type": "photo", "t0": a, "t1": b, "photo": key, "kb": kb}
        if notes:
            d["notes"] = notes
        return d

    def question(lines, q, ans, tag="クエスチョン"):
        return {"text": lines, "from": T(q, 0.3), "to": T(ans, 0.2),
                "think": [TE(q), T(q + 1)], "tag": tag}

    std = {"id": "std"}
    pale = {"id": "pale"}
    swale = lambda k: {"id": "swale", "alpha": k}             # noqa: E731
    usa = lambda k=None: ({"id": "ort_USA10"} if k is None    # noqa: E731
                          else {"id": "ort_USA10", "alpha": k})
    now = lambda k=None: ({"id": "seamlessphoto"} if k is None  # noqa: E731
                          else {"id": "seamlessphoto", "alpha": k})

    # --- アバン --------------------------------------------------------
    ep0 = [
        # 0-1 いまの新田間橋の上から。縦長の写真を横に切り出し、道の先へ寄る
        photo(P_NOW, 0.0, T(5),
              kb=[focus(P_NOW, 0.0, 1.00, 0.50, 0.55, 1.00),
                  focus(P_NOW, T(5), 0.80, 0.50, 0.50, 1.00)],
              notes=[note("横浜市西区　新田間橋（あらたまばし）", T(2, 0.6), TE(2))]),

        # 0-2 1860年の同じ橋。絵全体から、ナベ新田の札へ
        photo(P_NABEYA, T(5), TE(9, 0.6),
              kb=[focus(P_NABEYA, T(5), 0.66, 0.49, 0.44, 0.66),
                  focus(P_NABEYA, T(8), 0.60, 0.52, 0.44, 0.66),
                  focus(P_NABEYA, TE(9, 0.6), 0.40, 0.70, 0.45, 0.66)],
              notes=[note("貞秀「新田間橋ヨリナベヤ新田塩焼屋…を見る」万延元年（1860）",
                          T(5, 1.0), TE(6))]),

        # 0-3 タイトル。いまの空中写真で新田間橋から西口を上から
        {"t0": TE(9, 0.6), "t1": TE(9, 5.4), "zoom": 16,
         "camera": [[TE(9, 0.6), MID[0], MID[1], 0.80],
                    [TE(9, 5.4), MID[0], MID[1], 0.74]],
         "layers": [now()]},
    ]
    ep0[2]["title"] = {"main": "今日はここに",
                       "sub": "第007回　横浜 岡野",
                       "from": TE(9, 0.8), "to": TE(9, 4.8),
                       "size": 108, "subsize": 34, "dim": 150, "y": 0.44}

    # --- 第1話 浅くなった入江 ---------------------------------------------
    ep1 = [
        # 1-1 明治の海。水色が入江（袖ヶ浦）
        {"t0": 0.0, "t1": T(15), "zoom": 15,
         "camera": [[0.0, MID[0], MID[1], 0.95],
                    [T(15), MID[0], MID[1], 0.80]],
         "layers": [std, swale([[0.0, 0.0], [T(10, 2.0), 0.0], [T(10, 4.0), 0.85]])],
         "labels": [lb("横浜駅", YOKO, T(11, 0.4)),
                    lb("新田間橋", ARATAMA, T(12, 1.0)),
                    lb("神奈川台", DAIMACHI, T(14, 0.6))],
         "title": {"main": "第一話", "sub": "浅くなった入江",
                   "from": 0.3, "to": 4.6, "size": 76, "subsize": 38, "dim": 110},
         "notes": [note("水色 = 明治期の河川・海面（地理院「明治期の低湿地」）", T(10, 4.2), TE(11)),
                   note("帷子川の河口の入江「袖ヶ浦」", T(12, 1.6), TE(12))]},

        # 1-2 クエスチョン。帷子川の流域
        dict({"t0": T(15), "t1": T(19), "zoom": 13,
              "camera": [[T(15), 35.4600, 139.5900, 1.00],
                         [T(19), 35.4600, 139.5950, 0.94]],
              # swale は外す。z13 だと整備範囲の四角い境目が出た
              "layers": [pale],
              "labels": [lb("新田間橋", ARATAMA, T(15, 0.6))]},
             question=question(["入江が浅くなった", "大きなきっかけは"], 16, 18)),

        # 1-3 答え。富士山から横浜まで引く
        {"t0": T(19), "t1": T(24), "zoom": 9,
         "camera": [[T(19), 35.4100, 139.1700, 0.95],
                    [T(24), 35.4300, 139.3500, 0.80]],
         "layers": [pale, {"id": "hillshademap", "alpha": [[T(19), 0.45]]}],
         "labels": [lb("富士山", FUJI, T(19, 0.4)),
                    lb("新田間橋", ARATAMA, T(19, 1.2))],
         "notes": [note("宝永4年（1707）富士山の噴火", T(19, 0.4), TE(19)),
                   note("富士山頂から新田間橋まで 約81km", T(20, 1.0), TE(20)),
                   note("降灰で帷子川の河口が浅くなった（横浜市 河川資料）", T(21, 1.0), TE(21))]},

        # 1-4 新田が並ぶ
        {"t0": T(24), "t1": TE(26, 0.9), "zoom": 15,
         "camera": [[T(24), MID[0], MID[1], 0.85],
                    [TE(26, 0.9), 35.4600, 139.6100, 0.95]],
         "layers": [std, swale([[T(24), 0.85]])],
         "notes": [note("尾張屋新田　宝暦新田（1754）　安永新田（1780 検地）　藤江新田（1786）",
                        T(24, 1.0), TE(24))]},
    ]

    # --- 第2話 鍋屋の新田 -------------------------------------------------
    ep2 = [
        # 2-1 保土ケ谷宿の年寄
        {"t0": 0.0, "t1": T(32), "zoom": 14,
         "camera": [[0.0, 35.4540, 139.6050, 1.00],
                    [T(32), 35.4560, 139.6080, 0.92]],
         "layers": [pale],
         "labels": [lb("保土ヶ谷宿（本陣跡）", HODOGAYA, 5.0),
                    lb("岡野", OKANO, T(29, 1.5))],
         "title": {"main": "第二話", "sub": "鍋屋の新田",
                   "from": 0.3, "to": 4.6, "size": 76, "subsize": 38, "dim": 110},
         "notes": [note("岡野家は保土ケ谷宿の年寄（本陣・名主は苅部家）", T(27, 1.5), TE(28)),
                   note("天保4年（1833）埋め立てに着手", T(31, 0.6), TE(31))]},

        # 2-2 七つの跡継ぎ
        {"t0": T(32), "t1": T(37), "zoom": 16,
         "camera": [[T(32), OKANO[0], OKANO[1], 0.95],
                    [T(37), OKANO[0], OKANO[1], 0.80]],
         "layers": [std, swale([[T(32), 0.85]])],
         "labels": [lb("岡野（いまの岡野一・二丁目）", OKANO, T(32, 0.8))],
         "notes": [note("天保7年（1836）良親 没（数え41）　子の良哉 数え7つ", T(32, 1.0), TE(34)),
                   note("岡野新田開拓碑（明治44年）「設隄防通溝渠以拓田畝」", T(36, 1.0), TE(36))]},

        # 2-3 クエスチョン。錦絵の塩焼屋のあたり
        dict(photo(P_NABEYA, T(37), T(41),
                   kb=[focus(P_NABEYA, T(37), 0.50, 0.55, 0.44, 0.50),
                       focus(P_NABEYA, T(41), 0.44, 0.58, 0.44, 0.50)]),
             question=question(["この新田で", "つくっていたものは"], 38, 40)),

        # 2-4 答え。塩焼屋の札に寄る
        photo(P_NABEYA, T(41), TE(46, 0.9),
              kb=[focus(P_NABEYA, T(41), 0.44, 0.58, 0.44, 0.44),
                  focus(P_NABEYA, T(44), 0.30, 0.64, 0.43, 0.44),
                  focus(P_NABEYA, TE(46, 0.9), 0.28, 0.65, 0.43, 0.44)],
              notes=[note("「塩田による製塩が大部分」（横浜市 河川資料）", T(43, 2.4), TE(43)),
                     note("碑「嘉永三年には早くも數戶の民家を見るに至り專ら製鹽の業を起した」",
                          T(45, 2.2), TE(45))]),
    ]

    # --- 第3話 開港の道 ---------------------------------------------------
    ep3 = [
        # 3-1 開港。神奈川宿・新田間橋・開港場を一枚に
        {"t0": 0.0, "t1": T(52), "zoom": 14,
         "camera": [[0.0, 35.4580, 139.6280, 1.00],
                    [T(52), 35.4600, 139.6250, 0.92]],
         "layers": [pale],
         "labels": [lb("新田間橋", ARATAMA, 5.0),
                    lb("開港場（いまの関内）", KAIKO, T(49, 1.0)),
                    lb("神奈川台", DAIMACHI, T(49, 2.0))],
         "title": {"main": "第三話", "sub": "開港の道",
                   "from": 0.3, "to": 4.6, "size": 76, "subsize": 38, "dim": 110},
         "notes": [note("安政6年（1859）3月　幕府の命で横浜道の普請", T(51, 1.0), TE(51))]},

        # 3-2 新田の縁。新田間橋と平沼橋の間
        {"t0": T(52), "t1": T(56), "zoom": 16,
         "camera": [[T(52), 35.4630, 139.6160, 0.80],
                    [T(56), 35.4630, 139.6160, 0.70]],
         "layers": [std, swale([[T(52), 0.85]])],
         "labels": [lb("新田間橋", ARATAMA, T(52, 0.6)),
                    lb("平沼橋（いまの元平沼橋）", HIRANUMA, T(52, 1.4))],
         "notes": [note("岡野新田の中の区間　延長197間（約358m）", T(54, 1.0), TE(54)),
                   note("請負の賃金もめ → 保土ケ谷宿名主 苅部清兵衛が完成（『今昔横浜案内』）",
                        T(55, 2.0), TE(55))]},

        # 3-3 クエスチョン。新田間橋の札に寄る
        dict(photo(P_NABEYA, T(56), T(60),
                   kb=[focus(P_NABEYA, T(56), 0.56, 0.49, 0.44, 0.56),
                       focus(P_NABEYA, T(60), 0.44, 0.47, 0.42, 0.56)]),
             question=question(["新田間橋に", "つけられかけた名前は"], 57, 59)),

        # 3-4 答え
        photo(P_NABEYA, T(60), T(66),
              kb=[focus(P_NABEYA, T(60), 0.44, 0.47, 0.42, 0.62),
                  focus(P_NABEYA, T(66), 0.62, 0.49, 0.44, 0.62)],
              notes=[note("「岡野橋」— 修繕費を嫌って断った（『今昔横浜案内』1929）",
                          T(62, 1.0), TE(62)),
                     note("どの新田のあいだか：芝生新田／安永・弘化新田 と資料で割れる",
                          T(64, 2.4), TE(64))]),

        # 3-5 平沼橋から神奈川台を見る。縦長の絵の上半分（海と台）から橋の上へ
        photo(P_DAI, T(66), TE(69, 0.9),
              kb=[focus(P_DAI, T(66), 0.55, 0.50, 0.62, 0.62),
                  focus(P_DAI, T(67, 2.0), 0.50, 0.55, 0.72, 0.62),
                  focus(P_DAI, TE(69, 0.9), 0.62, 0.50, 0.30, 0.62)],
              notes=[note("貞秀「横浜平沼橋ヨリ東海道神奈川台…ヲ見ル」万延元年（1860）",
                          T(66, 1.0), TE(66))]),
    ]

    # --- エンディング -----------------------------------------------------
    end = [
        # 9-1 最後の海。北幸・南幸
        {"t0": 0.0, "t1": T(75), "zoom": 16,
         "camera": [[0.0, 35.4650, 139.6180, 0.85],
                    [T(75), 35.4650, 139.6180, 0.75]],
         "layers": [std, swale([[0.0, 0.85]])],
         "labels": [lb("北幸", KITASAI, T(73, 2.4)),
                    lb("南幸", MINASAI, T(73, 3.0)),
                    lb("横浜駅", YOKO, T(74, 0.4))],
         "notes": [note("大正2年（1913）内海の埋め立て5万坪が完成（『横浜の町名』）",
                        T(72, 2.0), TE(72))]},

        # 9-2 変遷。同じ画角で 明治 → 1945〜50年 → いま
        {"t0": T(75), "t1": T(81), "zoom": 16,
         "camera": [[T(75), MID[0], MID[1], 0.80],
                    [T(81), MID[0], MID[1], 0.72]],
         "layers": [std,
                    usa([[T(75), 0.0], [T(77), 0.0], [T(77, 1.2), 1.0]]),
                    now([[T(75), 0.0], [T(79), 0.0], [T(79, 1.2), 1.0]]),
                    swale([[T(75), 0.85], [T(77), 0.85], [T(77, 1.2), 0.0]])],
         "notes": [note("明治期の海", T(75, 0.6), T(77, 0.2)),
                   note("1945〜50年", T(77, 0.6), T(79, 0.2)),
                   note("現在", T(79, 0.6), TE(80))]},

        # 9-3 道。いまの新田間橋から
        photo(P_NOW, T(81), TE(85, 0.9),
              kb=[focus(P_NOW, T(81), 0.80, 0.50, 0.50, 1.00),
                  focus(P_NOW, TE(85, 0.9), 1.00, 0.50, 0.58, 1.00)],
              notes=[note("「僅か一町ばかり其の面影を殘すに止まつて」（『今昔横浜案内』1929）",
                          T(81, 2.0), TE(81)),
                     note("いまの新田間橋は震災復興橋（昭和2年＝1927 竣工）", T(83, 0.8), TE(83))]),

        # 9-4 クレジット
        {"t0": TE(85, 0.9), "t1": TE(85, 9.4), "zoom": 16,
         "camera": [[TE(85, 0.9), MID[0], MID[1], 0.80],
                    [TE(85, 9.4), MID[0], MID[1], 0.88]],
         "layers": [now()],
         "credits": {"lines": credit_lines(), "from": TE(85, 1.4),
                     "to": TE(85, 8.6), "dim": 165}},
    ]

    return {0: ep0, 1: ep1, 2: ep2, 3: ep3, 99: end}
