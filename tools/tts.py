# -*- coding: utf-8 -*-
"""script.md の台詞行を VOICEVOX で合成し、話ごとに 1 本の wav に連結する。

台詞行の書式: 話者名｜台詞   (全角縦棒区切り)
見出し ## 第N話 ... で話を区切る。

語りの設定は 2 か所に分かれている。
  script.md   文章とふりがな（ルビ）。人が書くもの
  voice.json  話者・抑揚・速度・アクセントの調整値。ブラウザUI が読み書きするもの
UI でアクセント句をいじった結果はルビ記法に書き戻せないので、原本を分けてある。

出力:
  out/lines/ep{N}_{連番}_{話者}.wav   1 行ずつの素片
  out/ep{N}.wav                        話ごとの連結済み音声
  out/timeline.json                    各行の開始・終了時刻（映像の同期に使う）
"""
import io
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import wave

ENGINE = "http://127.0.0.1:50021"

# 合成ロジックの版。ここを上げると全行を録り直す。
# 台詞も設定も変えていないのに音が変わる直しを入れたときに上げること。
#  2: accent を書き換えたあと /mora_data で pitch と length を計算し直すようにした。
#     それまで accent の変更がまったく音に反映されていなかった。
SYNTH_VERSION = 2

# 企画（配役・間の取り方・BGM）は episode.json が持つ。
# 会話で決めたことの置き場所であり、ブラウザUI の「企画」タブが読み書きする。
def load_plan(ep_dir):
    p = os.path.join(ep_dir, "episode.json")
    if os.path.exists(p):
        return json.load(io.open(p, encoding="utf-8"))
    return {}


def cast_of(plan):
    """話者名 -> 合成の既定値。episode.json の cast から作る。"""
    out = {}
    for who, c in (plan.get("cast") or {}).items():
        out[who] = {k: c[k] for k in
                    ("speaker", "speedScale", "intonationScale", "pitchScale") if k in c}
    return out

# 前後の余白と行間の無音（秒）。episode.json の timing で上書きできる。
# 頭を 0 にすると再生開始直後や AAC のプライミングで最初の一音が欠ける。
LEAD_IN, TAIL = 0.40, 0.90
GAP_SAME, GAP_SWITCH, GAP_CUT = 0.35, 0.55, 1.20

LINE_RE = re.compile(r"^([^｜\[\s]+)｜(.+)$")
EP_RE = re.compile(r"^##\s*(?:第(\d+)話|(アバン)|(エンディング))")
# 「間｜3.0」で任意の秒数の無音を差す。クエスチョンのシンキングタイム用。
# 行そのものは増やさず、次の台詞の gap_before に化けさせる。行を増やすと
# 台詞番号が全部ずれて、shots.py の T(n)/TE(n) がまとめて壊れる。
# シンキングタイムの開始と終わりは TE(問いの行) 〜 T(答えの行) で取れる。
PAUSE_RE = re.compile(r"^間｜([0-9.]+)\s*$")
# アバンは第0話、エンディングは第99話あつかい（番号順に並べると前後に来る）
CUT_RE = re.compile(r"^###\s")

# 読みのその場指定。 碑《ひ》 と書くと、字幕は「碑」・読み上げは「ひ」になる。
# 辞書（tools/readings.json）は語単位で全体に効くので、複合語の読みやアクセントを
# 巻き添えで壊すことがある。1か所だけ直したいときはこちらを使う。
#
# 読みを付ける対象は《》の直前にある漢字・カタカナの連なりだけ。
# ここを `[^《》]+?` のように書くと直前の地の文まで飲み込んでしまい、
# 「この碑《ひ》って」が「ひって」になる（実際に踏んだ）。
#
# 読みのうしろに ^数字 を足すと、その語で始まるアクセント句の核の位置を指定できる。
#   碑《ひ》     読みだけ直す
#   碑《ひ^1》   読みを直し、さらに「ひ＋助詞」の句を頭高にする
# 0 は平板。位置は句の先頭から数えたモーラ数。
# アクセント句の中身は `python tools/readings.py phrases "<台詞>"` で見られる。
RUBY_RE = re.compile(r"([一-鿿゠-ヿ々〆ヶ・ー]+)《([^《》^]+)(?:\^(\d+))?》")


def to_kata(s):
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def split_ruby(s):
    """(字幕に出す文字列, 読み上げる文字列, アクセント指定のリスト) を返す。"""
    accents = [(to_kata(m.group(2)), int(m.group(3)))
               for m in RUBY_RE.finditer(s) if m.group(3) is not None]
    return RUBY_RE.sub(r"\1", s), RUBY_RE.sub(r"\2", s), accents


def parse(path, speakers=None):
    """script.md を読んで行の一覧を返す。speakers は話者名の集合。"""
    speakers = speakers or set(cast_of(load_plan(os.path.dirname(path))) or
                               {"つむぎ", "朱司"})
    rows = []
    ep, cut = None, 0
    pending_pause = 0.0
    with io.open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = EP_RE.match(line)
            if m:
                ep = int(m.group(1)) if m.group(1) else (0 if m.group(2) else 99)
                cut = 0
                continue
            if CUT_RE.match(line):
                cut += 1
                continue
            m = PAUSE_RE.match(line.strip())
            if m:
                pending_pause = float(m.group(1))
                continue
            m = LINE_RE.match(line.strip())
            if m and ep is not None and m.group(1) in speakers:
                shown, read, accents = split_ruby(m.group(2).strip())
                # ルビの書き方を間違えると読み文だけが短くなる。黙って合成すると
                # 台詞が欠けた音声ができてしまうので、ここで気づけるようにする。
                if len(read) < len(shown) * 0.6:
                    raise ValueError(
                        "読み文が字幕文より極端に短い。ルビの書き方を確認すること。\n"
                        "  字幕: %s\n  読み: %s" % (shown, read))
                rows.append({"episode": ep, "cut": cut, "speaker": m.group(1),
                             "text": shown, "read": read, "ruby_accents": accents,
                             "pause": pending_pause})
                pending_pause = 0.0
    for i, r in enumerate(rows, 1):
        r["index"] = i
    return rows


def load_voice(ep_dir):
    p = os.path.join(ep_dir, "voice.json")
    cfg = json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}
    cfg.setdefault("lines", {})
    # 既定は episode.json の cast。voice.json 側に defaults があればそちらを優先する
    base = cast_of(load_plan(ep_dir))
    for who, v in (cfg.get("defaults") or {}).items():
        base.setdefault(who, {}).update(v)
    cfg["defaults"] = base
    return cfg


def save_voice(ep_dir, cfg):
    p = os.path.join(ep_dir, "voice.json")
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return p


def settings_for(cfg, row):
    """既定 + 行ごとの上書き をまとめた、その行の合成設定を返す。"""
    s = dict(cfg.get("defaults", {}).get(row["speaker"], {}))
    s.update({k: v for k, v in cfg.get("lines", {}).get(str(row["index"]), {}).items()
              if k != "accents"})
    over = cfg.get("lines", {}).get(str(row["index"]), {}).get("accents", [])
    return s, over


def post(path, params, body=None):
    url = ENGINE + path + "?" + urllib.parse.urlencode(params)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(url, data=data, method="POST")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def moras_of(ap):
    return "".join(m["text"] for m in ap["moras"])


def apply_ruby_accents(query, accents):
    """ルビの ^N 指定を当てる。指定した読みで始まる句を、出てきた順に 1 つずつ。"""
    missed, used = [], set()
    for kana, acc in accents:
        hit = False
        for i, ap in enumerate(query["accent_phrases"]):
            if i in used:
                continue
            if moras_of(ap).startswith(kana):
                ap["accent"] = min(acc, len(ap["moras"]))
                used.add(i)
                hit = True
                break
        if not hit:
            missed.append(kana)
    return missed


def apply_overrides(query, overrides):
    """voice.json のアクセント上書きを当てる。

    句の位置だけで指すと台詞を直したときに黙ってずれるので、
    記録しておいたモーラ列と一致するかを毎回確かめる。
    """
    stale = []
    for o in overrides:
        i = o.get("i")
        aps = query["accent_phrases"]
        if i is None or i >= len(aps) or moras_of(aps[i]) != o.get("moras"):
            stale.append(o.get("moras"))
            continue
        aps[i]["accent"] = min(o["accent"], len(aps[i]["moras"]))
    return stale


def build_query(text, st, ruby_accents=(), overrides=()):
    q = json.loads(post("/audio_query", {"text": text, "speaker": st["speaker"]}))
    q["speedScale"] = st.get("speedScale", 0.98)
    q["intonationScale"] = st.get("intonationScale", 1.0)
    q["pitchScale"] = st.get("pitchScale", 0.0)
    q["volumeScale"] = st.get("volumeScale", 1.0)
    q["prePhonemeLength"] = 0.05
    q["postPhonemeLength"] = 0.10
    missed = apply_ruby_accents(q, ruby_accents)
    stale = apply_overrides(q, overrides)

    # accent はただの印で、合成が実際に見るのはモーラごとの pitch と length。
    # accent を書き換えただけでは音がまったく変わらないので、必ず計算し直す。
    if ruby_accents or overrides:
        q["accent_phrases"] = json.loads(
            post("/mora_data", {"speaker": st["speaker"]}, q["accent_phrases"]))
    return q, missed, stale


def synth(text, st, out_path, ruby_accents=(), overrides=()):
    q, missed, stale = build_query(text, st, ruby_accents, overrides)
    if missed:
        sys.stderr.write("  ルビのアクセント指定が当たらなかった: %s  (%s)\n"
                         % (" / ".join(missed), text[:28]))
    if stale:
        sys.stderr.write("  voice.json のアクセント上書きが台詞と噛み合わない: %s  (%s)\n"
                         % (" / ".join(str(s) for s in stale), text[:28]))
    with open(out_path, "wb") as f:
        f.write(post("/synthesis", {"speaker": st["speaker"]}, q))
    return q


def concat_wav(items, ep_dir, out_path):
    """素片と無音をサンプル単位でつないで 1 本の wav にし、各行の時刻を書き込む。

    ffmpeg の concat + outpoint で無音を切ると、`-c copy` ではパケット境界でしか
    切れず 1 箇所あたり 0.05〜0.08 秒ずつ長くなる。無音が 28 箇所あると 1.4 秒ずれ、
    映像より音声が長くなって末尾が切れていた。自分で並べればサンプル単位で合う。
    """
    chunks, t = [], 0.0
    rate = width = ch = None

    def silence(sec):
        return b"\x00" * (int(round(sec * rate)) * width * ch)

    first = wave.open(os.path.join(ep_dir, items[0]["file"]), "rb")
    rate, width, ch = first.getframerate(), first.getsampwidth(), first.getnchannels()
    first.close()

    chunks.append(silence(LEAD_IN))
    t += LEAD_IN
    for it in items:
        if it["gap_before"] > 0:
            chunks.append(silence(it["gap_before"]))
            t += it["gap_before"]
        with wave.open(os.path.join(ep_dir, it["file"]), "rb") as w:
            if (w.getframerate(), w.getsampwidth(), w.getnchannels()) != (rate, width, ch):
                raise ValueError("素片の形式がそろっていません: " + it["file"])
            data = w.readframes(w.getnframes())
        it["start"] = round(t, 3)
        t += w.getnframes() / float(rate)
        it["end"] = round(t, 3)
        chunks.append(data)
    chunks.append(silence(TAIL))
    t += TAIL

    with wave.open(out_path, "wb") as o:
        o.setnchannels(ch)
        o.setsampwidth(width)
        o.setframerate(rate)
        o.writeframes(b"".join(chunks))
    return t


def wav_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def readings_fingerprint():
    """読み辞書の中身の指紋。辞書を直したら録り直しが要るので判定に混ぜる。

    台詞も設定も変えずに辞書だけ直したとき、これが無いと古い音声が残る。
    実際に「側」を ソク -> ガワ に直したのに録り直されず、気づかず進みかけた。
    """
    import hashlib
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "readings.json")
    if not os.path.exists(p):
        return ""
    return hashlib.sha1(io.open(p, encoding="utf-8").read().encode("utf-8")).hexdigest()[:12]


def run(ep_dir, quiet=False):
    global LEAD_IN, TAIL, GAP_SAME, GAP_SWITCH, GAP_CUT
    tm = (load_plan(ep_dir).get("timing") or {})
    LEAD_IN = tm.get("lead_in", LEAD_IN)
    TAIL = tm.get("tail", TAIL)
    GAP_SAME = tm.get("gap_same", GAP_SAME)
    GAP_SWITCH = tm.get("gap_switch", GAP_SWITCH)
    GAP_CUT = tm.get("gap_cut", GAP_CUT)

    script = os.path.join(ep_dir, "script.md")
    out = os.path.join(ep_dir, "out")
    lines_dir = os.path.join(out, "lines")
    os.makedirs(lines_dir, exist_ok=True)

    # 読みの補正を必ず当ててから合成する。当て忘れると読みが化ける。
    try:
        import readings
        readings.apply_words(verbose=False)
    except Exception as e:
        sys.stderr.write("読み辞書の適用に失敗: %s\n" % e)

    rows = parse(script)
    if not rows:
        sys.exit("台詞行が見つかりません: " + script)
    cfg = load_voice(ep_dir)
    dict_fp = readings_fingerprint()

    timeline, by_ep, prev = [], {}, {}
    for r in rows:
        i, ep, who = r["index"], r["episode"], r["speaker"]
        st, over = settings_for(cfg, r)
        path = os.path.join(lines_dir, "ep%d_%03d_%s.wav" % (ep, i, who))
        stamp = path[:-4] + ".read"
        want = json.dumps([SYNTH_VERSION, dict_fp, r["read"], r["ruby_accents"], st, over],
                          ensure_ascii=False, sort_keys=True)
        old = io.open(stamp, encoding="utf-8").read() if os.path.exists(stamp) else None
        if not os.path.exists(path) or old != want:
            synth(r["read"], st, path, r["ruby_accents"], over)
            io.open(stamp, "w", encoding="utf-8").write(want)
            if not quiet:
                sys.stderr.write("[%d/%d] %s %s\n" % (i, len(rows), who, r["read"][:24]))
        dur = wav_duration(path)

        p = prev.get(ep)
        gap = 0.0 if p is None else (GAP_CUT if p[0] != r["cut"]
                                     else GAP_SWITCH if p[1] != who else GAP_SAME)
        # 台本で指定した間があればそちらを使う（話の頭では入れない）
        if p is not None and r.get("pause"):
            gap = r["pause"]
        prev[ep] = (r["cut"], who)

        item = {"index": i, "episode": ep, "cut": r["cut"], "speaker": who,
                "text": r["text"], "read": r["read"],
                "file": os.path.relpath(path, ep_dir).replace("\\", "/"),
                "gap_before": gap, "duration": round(dur, 3)}
        by_ep.setdefault(ep, []).append(item)
        timeline.append(item)

    for ep, items in sorted(by_ep.items()):
        t = concat_wav(items, ep_dir, os.path.join(out, "ep%d.wav" % ep))
        if not quiet:
            print("第%d話: %d行 / %.1f秒 (%d分%02d秒)"
                  % (ep, len(items), t, int(t) // 60, int(t) % 60))

    with io.open(os.path.join(out, "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)
    total = sum(v[-1]["end"] for v in by_ep.values())
    if not quiet:
        print("合計 %.1f秒 (%d分%02d秒)" % (total, int(total) // 60, int(total) % 60))
    return timeline


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        root, "episodes", "001-nagasaki-daikokumachi")
    run(d)
