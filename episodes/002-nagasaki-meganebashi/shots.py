# -*- coding: utf-8 -*-
"""第002回 長崎市 眼鏡橋 のショット定義。

時刻は秒で直書きせず、台詞番号から引く（T=行の頭, TE=行の尻）。
音声の頭には LEAD_IN 0.4 秒、尻には TAIL 0.9 秒の余白がある。各話の最初のショットは
0 秒から始め、最後のショットは TE(最終行, 0.9) で終わらせて音声の全長とそろえる。

2 基の碑は Commons に写真が無い。碑文そのものは台詞が読み上げるので、
画は地図でマーカーを打ち、テロップで碑名と建立年を出すにとどめる。
"""

# --- 地点 -------------------------------------------------------------
MEGANE   = (32.74717, 129.88010)   # 眼鏡橋 / OSM
FUKURO   = (32.74681, 129.87940)   # 袋橋 / OSM
MOMOTANI = (32.75153, 129.88390)   # 桃渓橋 / OSM
KOFUKUJI = (32.74787, 129.88390)   # 興福寺 / OSM
KAZAGASHIRA = (32.74577, 129.88596)  # 風頭山 / OSM
SHIAN    = (32.74262, 129.88060)   # 思案橋 / OSM
UONOMACHI = (32.74866, 129.87993)  # 魚の町 / 地理院
HAMANOMACHI = (32.74429, 129.87776)  # 浜町 / 地理院
NAGAYO   = (32.82330, 129.86970)   # 長与町（1時間187mmを記録）

# 自然災害伝承碑（地理院の全国データから。碑文もこのデータに入っている）
HI_YUKO = (32.747478, 129.880312)  # 水害復興と友好の記念碑（1989年・魚の町）
HI_TOU  = (32.742917, 129.879973)  # 長崎大水害記念塔（1984年・浜町 思案橋跡）

# --- 写真（photos.json のキー） --------------------------------------
P_BASHI  = "Meganebashi_jpg.jpg"                                  # 眼鏡橋 全景（CC0）
P_STONES = "Megane_Bridge_of_Nagasaki_with_Stepping_Stones_jpg.jpg"  # 飛び石ごし（CC0）
P_90S    = "Megane_bridge_90s_jpg.jpg"                            # 1990年代（PD）


def credit_lines(ep_dir=None):
    """出典の一覧。photos.json と episode.json から組み立てる。"""
    import json
    import os
    base = ep_dir or os.path.dirname(os.path.abspath(__file__))
    out = [("h", "音声"),
           ("b", "VOICEVOX:春日部つむぎ"),
           ("b", "VOICEVOX:雀松朱司（CV:狐狗狸ラク）"),
           ("gap", ""),
           ("h", "地図・碑文"),
           ("b", "出典 国土地理院（地理院タイル）"),
           ("b", "出典 国土地理院（自然災害伝承碑）")]
    plan = os.path.join(base, "episode.json")
    if os.path.exists(plan):
        b = (json.load(open(plan, encoding="utf-8")).get("bgm") or {})
        if b.get("default") and b.get("credit"):
            out += [("gap", ""), ("h", "音楽"), ("b", b["credit"])]
    p = os.path.join(base, "photos.json")
    if os.path.exists(p):
        out += [("gap", ""), ("h", "写真 — Wikimedia Commons")]
        seen = set()
        for m in json.load(open(p, encoding="utf-8")).values():
            a = (m.get("author") or "不明").strip()
            h = len(a) // 2
            if h and a[:h] == a[h:]:
                a = a[:h]
            line = "%s / %s" % (a, m.get("license") or "?")
            if line not in seen:
                seen.add(line)
                out.append(("b", line))
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
             "kb": kb or [[a, 1.22, 0.5, 0.5], [b, 1.04, 0.5, 0.5]]}
        if notes:
            d["notes"] = notes
        return d

    pale = {"id": "pale"}
    hill = lambda keys: {"id": "hillshademap", "alpha": keys}   # noqa: E731
    relief = lambda keys: {"id": "relief", "alpha": keys}       # noqa: E731

    # --- アバン --------------------------------------------------------
    ep0 = [
        photo(P_BASHI, 0.0, T(4),
              kb=[[0.0, 1.24, 0.5, 0.5], [T(4), 1.05, 0.46, 0.55]],
              notes=[note("眼鏡橋（1634年）", T(2, 0.6), TE(2))]),

        # 「流されています」で川筋を俯瞰し、そのままタイトルへ
        {"t0": T(4), "t1": TE(6, 5.0), "zoom": 16,
         "camera": [[T(4), MEGANE[0], MEGANE[1], 0.9],
                    [TE(6), 32.7460, 129.8790, 1.35],
                    [TE(6, 5.0), 32.7455, 129.8785, 1.4]],
         "layers": [pale, hill([[T(4), 0.4]])],
         "labels": [lb("眼鏡橋", MEGANE, T(4, 0.4))],
         "title": {"main": "今日はここに", "sub": "第002回　長崎市 眼鏡橋 —「流されないための橋」",
                   "from": TE(6, 0.8), "to": TE(6, 4.6), "size": 108, "subsize": 38,
                   "dim": 150, "y": 0.44}},
    ]

    # --- 第1話 ---------------------------------------------------------
    ep1 = [
        # 1-1 中島川と、そこに架かる橋の数
        {"t0": 0.0, "t1": T(13), "zoom": 17,
         "camera": [[0.0, MEGANE[0], MEGANE[1], 1.0], [T(9), 32.7480, 129.8810, 1.4],
                    [T(13), 32.7495, 129.8825, 1.7]],
         "layers": [pale, hill([[0.0, 0.35]])],
         "labels": [lb("眼鏡橋", MEGANE, 0.6), lb("袋橋", FUKURO, T(9, 0.5)),
                    lb("桃渓橋", MOMOTANI, T(10, 1.0))],
         "title": {"main": "第一話", "sub": "流されないために、石で架けた",
                   "from": 0.3, "to": 4.6, "size": 76, "subsize": 38, "dim": 110},
         "notes": [note("江戸時代には17〜18基あった", T(10, 1.5), TE(11))]},

        # 1-2 なぜ石だったのか。谷が川へ集まる地形を見せる
        {"t0": T(13), "t1": T(21), "zoom": 16,
         "camera": [[T(13), 32.7490, 129.8820, 1.2], [T(18), 32.7478, 129.8835, 1.5],
                    [T(21), 32.7475, 129.8830, 1.45]],
         "layers": [pale, hill([[T(13), 0.35], [T(14, 2.0), 0.75]])],
         "labels": [lb("興福寺", KOFUKUJI, T(18, 1.2)), lb("眼鏡橋", MEGANE, T(18, 4.0))],
         "notes": [note("1634年 黙子如定が石の橋を架ける", T(18, 3.5), TE(18)),
                   note("石工は中国から呼び寄せた", T(20, 2.5), TE(20))]},

        # 1-3 橋そのもの
        photo(P_BASHI, T(21), T(26),
              kb=[[T(21), 1.20, 0.5, 0.52], [T(26), 1.00, 0.42, 0.62]],
              notes=[note("日本最古の石造アーチ橋 — 長さ22.35m", T(23, 0.5), TE(23))]),

        # 1-4 十三年後に崩れる
        {"t0": T(26), "t1": TE(30, 0.9), "zoom": 17,
         "camera": [[T(26), 32.7478, 129.8808, 1.3], [T(28, 2.0), MEGANE[0], MEGANE[1], 0.85],
                    [TE(30, 0.9), MEGANE[0], MEGANE[1], 0.8]],
         "layers": [pale, hill([[T(26), 0.4]])],
         "labels": [lb("眼鏡橋", MEGANE, T(26, 0.4))],
         "notes": [note("1647年 洪水で崩流。架けて13年", T(28, 2.5), TE(29))]},
    ]

    # --- 第2話 ---------------------------------------------------------
    ep2 = [
        # 2-1 1982年7月23日。長与町の187mm
        {"t0": 0.0, "t1": T(38), "zoom": 13,
         "camera": [[0.0, 32.7600, 129.8790, 1.0], [T(35, 3.0), 32.7930, 129.8760, 1.35],
                    [T(38), 32.7950, 129.8760, 1.35]],
         "layers": [pale, hill([[0.0, 0.3]])],
         "labels": [lb("眼鏡橋", MEGANE, 0.6), lb("長与町", NAGAYO, T(35, 3.5))],
         "title": {"main": "第二話", "sub": "その橋が、流された",
                   "from": 0.3, "to": 4.6, "size": 76, "subsize": 38, "dim": 110},
         "notes": [note("1982年7月23日 長崎大水害", T(33, 1.0), TE(33)),
                   note("長与町で1時間187mm — 当時の国内最高", T(35, 4.0), TE(36))]},

        # 2-2 すり鉢の底。色別標高図で谷が一点に集まるのを見せる
        {"t0": T(38), "t1": T(44), "zoom": 15,
         "camera": [[T(38), 32.7500, 129.8810, 1.1], [T(41), 32.7490, 129.8820, 1.35],
                    [T(44), 32.7485, 129.8815, 1.3]],
         "layers": [pale, relief([[T(38), 0.0], [T(39, 2.0), 0.6]]),
                    hill([[T(38), 0.35], [T(41), 0.45]])],
         "labels": [lb("中島川", MEGANE, T(39, 1.0))],
         "notes": [note("すり鉢の底に街がある", T(39, 1.5), TE(40)),
                   note("14橋のうち6橋が流失・3橋が大破", T(41, 3.5), TE(42)),
                   note("眼鏡橋は831個の石材のうち15%が流出", T(43, 3.0), TE(43, 0.5))]},

        # 2-3 思案橋跡の碑へ
        {"t0": T(44), "t1": T(51), "zoom": 16,
         "camera": [[T(44), 32.7470, 129.8800, 1.0], [T(46), HI_TOU[0], HI_TOU[1], 0.75],
                    [T(51), HI_TOU[0], HI_TOU[1], 0.7]],
         "layers": [pale, hill([[T(44), 0.4]])],
         "labels": [lb("眼鏡橋", MEGANE, T(44, 0.3)),
                    lb("長崎大水害記念塔", HI_TOU, T(45, 2.5)),
                    lb("浜町", HAMANOMACHI, T(45, 0.6), offset=(-18, -20), anchor="ra")],
         "notes": [note("長崎大水害記念塔（1984年・思案橋跡）", T(46, 0.5), TE(47)),
                   note("水位 1.57m", T(48, 6.0), TE(49))]},

        # 2-4 塔の上の御朱印船
        {"t0": T(51), "t1": TE(56, 0.9), "zoom": 17,
         "camera": [[T(51), HI_TOU[0], HI_TOU[1], 1.1], [T(54), HI_TOU[0], HI_TOU[1], 0.75],
                    [TE(56, 0.9), HI_TOU[0], HI_TOU[1], 0.9]],
         "layers": [pale, hill([[T(51), 0.4]])],
         "labels": [lb("長崎大水害記念塔", HI_TOU, T(51, 0.3))],
         "notes": [note("塔飾りは、海に向かう御朱印船", T(54, 3.0), TE(55))]},
    ]

    # --- 第3話 ---------------------------------------------------------
    ep3 = [
        # 3-1 県の撤去案
        {"t0": 0.0, "t1": T(63), "zoom": 16,
         "camera": [[0.0, 32.7480, 129.8800, 1.0], [T(59), 32.7490, 129.8815, 1.35],
                    [T(63), 32.7488, 129.8812, 1.3]],
         "layers": [pale, hill([[0.0, 0.4]])],
         "labels": [lb("眼鏡橋", MEGANE, 0.6), lb("袋橋", FUKURO, T(59, 2.0)),
                    lb("桃渓橋", MOMOTANI, T(59, 3.0))],
         "title": {"main": "第三話", "sub": "石を拾い集めて、また架けた",
                   "from": 0.3, "to": 4.6, "size": 76, "subsize": 38, "dim": 110},
         "notes": [note("県の案 — 川幅を広げ、石橋は撤去", T(59, 1.5), TE(60))]},

        # 3-2 住民が水位を数えた
        {"t0": T(63), "t1": T(70), "zoom": 14,
         "camera": [[T(63), 32.7500, 129.8810, 1.0], [T(67), 32.7550, 129.8830, 1.4],
                    [T(70), 32.7545, 129.8825, 1.35]],
         "layers": [pale, hill([[T(63), 0.45]]), relief([[T(65), 0.0], [T(67), 0.35]])],
         "labels": [lb("中島川", MEGANE, T(63, 0.5))],
         "notes": [note("住民と専門家が街じゅうの水位を集めた", T(65, 1.0), TE(66)),
                   note("川幅は変えず、両岸の地下にバイパス水路", T(69, 2.0), TE(69, 0.5))]},

        # 3-3a 拾い集めた石
        photo(P_STONES, T(70), T(73),
              kb=[[T(70), 1.18, 0.5, 0.55], [T(73), 1.02, 0.45, 0.62]]),

        # 3-3b 風頭山の石
        {"t0": T(73), "t1": T(76), "zoom": 16,
         "camera": [[T(73), 32.7470, 129.8830, 1.0], [T(76), KAZAGASHIRA[0], KAZAGASHIRA[1], 0.9]],
         "layers": [pale, hill([[T(73), 0.55]])],
         "labels": [lb("風頭山", KAZAGASHIRA, T(73, 1.0)), lb("眼鏡橋", MEGANE, T(73, 0.3))],
         "notes": [note("角閃石安山岩 — 同じ風頭山の石で補った", T(73, 5.0), TE(74)),
                   note("1983年10月 復元が完成", T(75, 4.0), TE(75, 0.5))]},

        # 3-4 橋のたもとの碑
        {"t0": T(76), "t1": T(81), "zoom": 18,
         "camera": [[T(76), MEGANE[0], MEGANE[1], 1.2], [T(79), HI_YUKO[0], HI_YUKO[1], 0.8],
                    [T(81), HI_YUKO[0], HI_YUKO[1], 0.75]],
         "layers": [pale],
         "labels": [lb("眼鏡橋", MEGANE, T(76, 0.3)),
                    lb("水害復興と友好の記念碑", HI_YUKO, T(76, 1.8))],
         "notes": [note("水害復興と友好の記念碑（1989年）", T(77, 1.0), TE(78))]},

        # 3-5 三百四十八年
        photo(P_90S, T(81), TE(89, 0.9),
              kb=[[T(81), 1.06, 0.5, 0.5], [TE(89, 0.9), 1.24, 0.5, 0.48]],
              notes=[note("碑は中国に依頼して作られた", T(83, 2.0), TE(84)),
                     note("1634年に石工を呼んだ相手に、348年後", T(85, 2.0), TE(86)),
                     note("「中島川に石橋を架けるなど、ゆかりの深い中国に依頼し」",
                          T(87, 1.0), TE(88))]),
    ]

    # --- エンディング ---------------------------------------------------
    ep99 = [
        {"t0": 0.0, "t1": TE(93, 9.0), "zoom": 15,
         "camera": [[0.0, MEGANE[0], MEGANE[1], 0.7], [TE(93, 2.0), 32.7440, 129.8760, 1.2],
                    [TE(93, 9.0), 32.7420, 129.8740, 1.3]],
         "layers": [pale, hill([[0.0, 0.35]])],
         "labels": [lb("眼鏡橋", MEGANE, 0.6)],
         "title": {"main": "今日はここに", "sub": "第002回　長崎市 眼鏡橋 —「流されないための橋」",
                   "from": TE(93, 0.6), "to": TE(93, 4.2), "size": 96, "subsize": 34,
                   "dim": 140, "y": 0.40},
         "credits": {"lines": credit_lines(), "from": TE(93, 4.6), "to": TE(93, 8.6),
                     "dim": 180}},
    ]

    return {0: ep0, 1: ep1, 2: ep2, 3: ep3, 99: ep99}
