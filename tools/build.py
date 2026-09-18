# -*- coding: utf-8 -*-
"""エピソードの動画を組み立てる。

  python tools/build.py check        各ショットの真ん中を1枚ずつ静止画で出す（構図確認）
  python tools/build.py 1            第1話だけ作る（2 3 のように複数指定も可）
  python tools/build.py all          全話を作り、通しも1本にまとめる
  python tools/build.py remux        絵はそのままに音声だけ差し替える（速い）
  python tools/build.py compact      公開用に軽くした複製を作る（--hevc でさらに半分）

  --ep <dir> で対象の回を指定する（既定は episodes/ の最初の回）。
  --jobs N   ショットを N 本ずつ同時に描く（auto でコア数から決める）。
  --ff       絵を ffmpeg 側で作る（未対応のショットは PIL 版に落ちる）。

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
import layout
import mix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_ep():
    d = os.path.join(ROOT, "episodes")
    xs = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))
    return os.path.join(d, xs[0]) if xs else d


EP_DIR = _default_ep()
OUT = os.path.join(EP_DIR, "out")


def use_episode(path):
    """対象の回を切り替える。--ep <dir> で指定する。"""
    global EP_DIR, OUT
    EP_DIR = os.path.abspath(path)
    OUT = os.path.join(EP_DIR, "out")
    mix.EP_DIR = EP_DIR
    return EP_DIR


def all_lines():
    p = os.path.join(OUT, "timeline.json")
    if not os.path.exists(p):
        print("out/timeline.json がありません: %s" % p)
        print("先に音声を合成してください:  python tools/tts.py %s" % EP_DIR)
        sys.exit(1)
    return json.load(io.open(p, encoding="utf-8"))


def load_shots():
    p = os.path.join(EP_DIR, "shots.py")
    if not os.path.exists(p):
        print("shots.py がありません: %s" % p)
        print("回の雛形を作るには:  python tools/new.py <番号> <slug> <町名>")
        print("書式は docs/episode-files.md にあります。")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("shots", p)
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
        tasks, mids = [], []
        for i, sh in enumerate(shots):
            mid = (sh["t0"] + sh["t1"]) / 2
            one = dict(sh)
            # 4フレームだけ描いて、その1枚目を取る
            one["t0"], one["t1"] = mid, mid + 4.0 / 30
            tasks.append((i, one, os.path.join(d, "ep%d_shot%d.png" % (ep, i + 1))))
            mids.append(mid)
        for i, png in clip.check_shots(shots, tl, tasks, EP_DIR):
            print("ep%d shot%d  %5.1f秒地点  -> %s"
                  % (ep, i + 1, mids[i], os.path.basename(png)))


def audio_for(ep, shots):
    """その話に使う音声。BGM が割り当てられていればミックスして返す。

    長さは映像に合わせる。語りより映像が長い回（タイトルやクレジットが出る
    アバンとエンディング）で、BGM だけが先に止まるのを防ぐため。
    """
    nar = os.path.join(OUT, "ep%d.wav" % ep)
    src, meta = mix.bgm_for(ep, EP_DIR)
    if not src:
        return nar
    out = os.path.join(OUT, "ep%d_mixed.wav" % ep)
    vol = (mix.plan(EP_DIR).get("bgm") or {}).get("volume", 0.12)
    mix.mix(nar, src, out, volume=vol, limit=shots[-1]["t1"])
    return out


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
        subprocess.run(["ffmpeg", "-y", "-i", mp4, "-i", audio_for(ep, load_shots()[ep]),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", tmp], capture_output=True, check=True)
        os.replace(tmp, mp4)
        print("第%d話: 音声を差し替えました" % ep)
    join(eps)
    return True


def join(eps):
    made = [os.path.join(OUT, "ep%d.mp4" % e) for e in sorted(eps)]
    if len(made) < 2:
        return
    lst = os.path.join(OUT, "_all.txt")
    with io.open(lst, "w", encoding="utf-8") as f:
        for p in made:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    # 通しの名前は回から取る。回ごとに違うので直書きしない。
    layout.dist_dir(EP_DIR, make=True)
    full = layout.full_mp4(EP_DIR)
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", full], capture_output=True, check=True)
    os.remove(lst)
    print("通し -> %s" % full)


def compact(hevc=False, crf=None):
    """公開用に軽くした複製を作る。dist/ の通しは高画質のまま残す。

    絵は地理院タイルと写真なので、H.264 CRF 19 で描くと 7〜12 Mbps になる。
    細かいのは地図の文字だけで、それは CRF を落としても崩れない
    （実測: CRF 23 でも 5px の町名が読める。SSIM 0.989）。

    YouTube に上げるだけなら縮めなくてよい。向こうで再圧縮されるので、
    先に削っておくと二重圧縮になるだけ。ファイルそのものを配るときに使う。
    """
    src = layout.full_mp4(EP_DIR)
    if not os.path.exists(src):
        print("通しがありません。先に build してください: %s" % src)
        return False
    if hevc:
        # H.265。同じ見た目で H.264 の半分だが、再生側が選ぶ。
        v = ["-c:v", "libx265", "-preset", "medium", "-crf", str(crf or 26),
             "-tag:v", "hvc1"]
        suffix = "-hevc"
    else:
        v = ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf or 23)]
        suffix = "-web"
    out = layout.web_mp4(EP_DIR, suffix)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src] + v +
                   ["-pix_fmt", "yuv420p",
                    # 音声はすでにモノラル 24kHz の 98kbps。触っても減らない
                    "-c:a", "copy",
                    "-movflags", "+faststart", out], check=True)
    a, b = os.path.getsize(src), os.path.getsize(out)
    print("%s -> %s" % (os.path.basename(src), os.path.basename(out)))
    print("  %.0fMB -> %.0fMB (%.0f%%減)" % (a / 1048576, b / 1048576, (1 - b / a) * 100))
    return True


USE_CHARA = False


def chapters():
    """その回にある話番号。episode.json の chapters から引く。

    回によって話数が違うので、番号を直書きしない。
    """
    p = os.path.join(EP_DIR, "episode.json")
    if os.path.exists(p):
        d = json.load(io.open(p, encoding="utf-8"))
        ns = [c["n"] for c in d.get("chapters", [])]
        if ns:
            # 台本（合成済みの timeline）にある話が chapters に無いと、その話は
            # 黙って通しから落ちる。雛形の chapters（アバン・第1話・エンディング）の
            # まま話を足して、第007回で第2・3話の抜けた通しを作りかけた。
            tl = os.path.join(OUT, "timeline.json")
            if os.path.exists(tl):
                spoken = {r["episode"] for r in json.load(io.open(tl, encoding="utf-8"))}
                missing = sorted(spoken - set(ns))
                if missing:
                    sys.exit("episode.json の chapters に無い話が台本にあります: %s\n"
                             "  chapters に足してから作り直してください" % missing)
            return sorted(ns)
    return [0, 1, 2, 3, 99]


def build(eps):
    shots = load_shots()
    made = []
    for ep in eps:
        audio = audio_for(ep, shots[ep])
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
    argv = sys.argv[1:]
    if "--ep" in argv:
        i = argv.index("--ep")
        use_episode(argv[i + 1])
        del argv[i:i + 2]
        print("対象: %s" % EP_DIR)
    if "--jobs" in argv:
        i = argv.index("--jobs")
        v = argv[i + 1]
        clip.JOBS = clip.auto_jobs() if v == "auto" else int(v)
        del argv[i:i + 2]
        print("同時に描く数: %d" % clip.JOBS)
    args = [a for a in argv if a not in ("--chara", "--no-chara", "--hevc", "--ff")]
    USE_CHARA = "--chara" in argv
    if "--ff" in argv:
        clip.USE_FF = True
        print("レンダラ: ffmpeg 版を優先（未対応のショットは PIL 版に落ちる）")
    print("立ち絵: %s" % ("あり（--chara）" if USE_CHARA else "なし（既定）"))
    arg = args[0] if args else "all"
    if arg == "check":
        check()
    elif arg == "remux":
        if not remux(chapters()):
            sys.exit(1)
    elif arg == "compact":
        if not compact(hevc="--hevc" in argv):
            sys.exit(1)
    elif arg == "all":
        build(chapters())
    else:
        eps = [int(a) for a in args]
        build(eps)
        if len(eps) < 3:
            join(chapters())   # 一部だけ作り直したときも通しはつなぎ直す
