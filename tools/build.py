# -*- coding: utf-8 -*-
"""エピソードの動画を組み立てる。

  python tools/build.py check        各ショットの真ん中を1枚ずつ静止画で出す（構図確認）
  python tools/build.py 1            第1話だけ作る（2 3 のように複数指定も可）
  python tools/build.py all          全話を作り、通しも1本にまとめる
  python tools/build.py remux        絵はそのままに音声だけ差し替える（速い）

  既定では立ち絵を出さない。--chara を付けたときだけ入る。

  立ち絵はキャラごとの規約が厳しい。調べた 5 権利者のうち 4 つが法人利用を
  制限しており、「このプログラムでこういう動画が作れます」と見せる用途
  （＝他のコンテンツの宣伝手段）はたいてい許諾が要る。だから既定は外し、
  個人の作品として出すときだけ --chara で足す。詳細は docs/character-art-license.md。
"""
import importlib.util
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(ROOT, "episodes", "001-nagasaki-daikokumachi")
OUT = os.path.join(EP_DIR, "out")


def all_lines():
    return json.load(io.open(os.path.join(OUT, "timeline.json"), encoding="utf-8"))


def load_shots():
    spec = importlib.util.spec_from_file_location("shots", os.path.join(EP_DIR, "shots.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    # 時刻は台詞番号から引くので、録り直すたびに自動で追従する
    return m.build(all_lines())


def timeline(ep):
    return [r for r in all_lines() if r["episode"] == ep]


def check():
    d = os.path.join(OUT, "shotcheck")
    os.makedirs(d, exist_ok=True)
    for ep, shots in sorted(load_shots().items()):
        tl = timeline(ep)
        for i, sh in enumerate(shots):
            mid = (sh["t0"] + sh["t1"]) / 2
            one = dict(sh)
            one["t0"], one["t1"] = mid, mid + 4.0 / 30
            mp4 = os.path.join(d, "ep%d_shot%d.mp4" % (ep, i + 1))
            if one.get("type") == "photo":
                clip.render_photo_shot(one, tl, clip.load_photos(EP_DIR), mp4)
            else:
                clip.render_shot(one, tl, mp4)
            png = mp4.replace(".mp4", ".png")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", mp4, "-frames:v", "1", png],
                           check=True)
            os.remove(mp4)
            print("ep%d shot%d  %5.1f秒地点  -> %s" % (ep, i + 1, mid, os.path.basename(png)))


def timing_key(ep):
    """映像づくりに効く値だけを並べた指紋。これが同じなら絵は描き直さなくていい。"""
    return json.dumps([[r["index"], r["start"], r["end"], r["text"], r["speaker"]]
                       for r in timeline(ep)], ensure_ascii=False)


def stamp_path(ep):
    return os.path.join(OUT, "ep%d.timing.json" % ep)


def remux(eps):
    """絵はそのままに音声だけ差し替える。読みやアクセントだけ直したときに使う。"""
    for ep in eps:
        mp4 = os.path.join(OUT, "ep%d.mp4" % ep)
        st = stamp_path(ep)
        if not os.path.exists(mp4) or not os.path.exists(st):
            print("第%d話: 映像が無いので作り直しが要ります" % ep)
            return False
        if io.open(st, encoding="utf-8").read() != timing_key(ep):
            print("第%d話: 台詞の時刻が変わっています。絵から作り直してください" % ep)
            return False
    for ep in eps:
        mp4 = os.path.join(OUT, "ep%d.mp4" % ep)
        tmp = mp4 + ".tmp.mp4"
        subprocess.run(["ffmpeg", "-y", "-i", mp4, "-i", os.path.join(OUT, "ep%d.wav" % ep),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", tmp], capture_output=True, check=True)
        os.replace(tmp, mp4)
        print("第%d話: 音声を差し替えました" % ep)
    join(eps)
    return True


def join(eps):
    made = [os.path.join(OUT, "ep%d.mp4" % e) for e in eps]
    if len(made) < 2:
        return
    lst = os.path.join(OUT, "_all.txt")
    with io.open(lst, "w", encoding="utf-8") as f:
        for p in made:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    full = os.path.join(OUT, "nagasaki-daikokumachi.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", full], capture_output=True, check=True)
    os.remove(lst)
    print("通し -> %s" % full)


USE_CHARA = False


def build(eps):
    shots = load_shots()
    made = []
    for ep in eps:
        audio = os.path.join(OUT, "ep%d.wav" % ep)
        out = os.path.join(OUT, "ep%d.mp4" % ep)
        print("第%d話 を作ります" % ep)
        clip.build_episode(shots[ep], timeline(ep), audio, out, ep_dir=EP_DIR,
                           use_chara=USE_CHARA)
        # 次に音声だけ直したとき、絵を描き直さずに済むよう時刻の指紋を残す
        io.open(stamp_path(ep), "w", encoding="utf-8").write(timing_key(ep))
        made.append(out)
        print("  -> %s" % out)
    join(eps)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a not in ("--chara", "--no-chara")]
    USE_CHARA = "--chara" in sys.argv
    print("立ち絵: %s" % ("あり（--chara）" if USE_CHARA else "なし（既定）"))
    arg = args[0] if args else "all"
    if arg == "check":
        check()
    elif arg == "remux":
        if not remux([0, 1, 2, 3]):
            sys.exit(1)
    elif arg == "all":
        build([0, 1, 2, 3])
    else:
        eps = [int(a) for a in args]
        build(eps)
        if len(eps) < 3:
            join([0, 1, 2, 3])   # 一部だけ作り直したときも通しはつなぎ直す
