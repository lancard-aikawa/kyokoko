# -*- coding: utf-8 -*-
"""ナレーションに BGM を混ぜる。

  python tools/mix.py sample <bgm.json のキー> [秒]   アバンで試聴用のミックスを作る
  python tools/mix.py ep <話番号>                     その話のミックスを作る

BGM は語りの下に潜らせる。ただ音量を下げるだけだと、語っている間も
一定の音量で鳴り続けて言葉が聞き取りにくい。ナレーションを横入力にした
コンプレッサ（sidechaincompress）で、喋っている間だけ自動で引っ込める。
"""
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(ROOT, "episodes", "001-nagasaki-daikokumachi")


def plan(ep_dir=EP_DIR):
    p = os.path.join(ep_dir, "episode.json")
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}


# BGM は回をまたいで共有する。リポジトリ直下の assets/ に置く。
BGM_DIR = os.path.join(ROOT, "assets")


def catalog(ep_dir=None):
    p = os.path.join(BGM_DIR, "bgm.json")
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}


def duration(path):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True).stdout.strip())


def mix(narration, bgm_path, out_path, volume=0.12, fade_in=2.0, fade_out=3.5,
        limit=None):
    """ナレーションの下に BGM を敷く。長さはナレーションに合わせる。"""
    dur = limit if limit else duration(narration)
    out_st = max(0.0, dur - fade_out)
    fc = (
        # 足りなければ繰り返し、ナレーションの長さで切る
        "[1:a]aformat=sample_rates=24000:channel_layouts=mono,"
        "atrim=0:{dur:.3f},asetpts=N/SR/TB,volume={vol},"
        "afade=t=in:st=0:d={fin},afade=t=out:st={ost:.3f}:d={fout}[bg];"
        # 語りを横入力にして、喋っている間だけ BGM を引っ込める
        # 語りが映像より短いときは無音で伸ばす。そうしないと amix が短いほうで
        # 切ってしまい、エンディングのクレジットの間だけ BGM が消える。
        "[0:a]aformat=sample_rates=24000:channel_layouts=mono,"
        "apad,atrim=0:{dur:.3f},asetpts=N/SR/TB,asplit=2[nar][sc];"
        "[bg][sc]sidechaincompress=threshold=0.02:ratio=12:attack=20:release=450[duck];"
        "[nar][duck]amix=inputs=2:duration=first:normalize=0[out]"
    ).format(dur=dur, vol=volume, fin=fade_in, ost=out_st, fout=fade_out)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", narration,
           "-stream_loop", "-1", "-i", bgm_path,
           "-filter_complex", fc, "-map", "[out]", out_path]
    subprocess.run(cmd, check=True)
    return out_path


def resolve(key, ep_dir=None):
    m = catalog().get(key)
    if not m:
        sys.exit("assets/bgm.json に %s がありません。python tools/bgm.py list で確認を。" % key)
    return os.path.join(BGM_DIR, m["path"].replace("/", os.sep)), m


def bgm_for(ep, ep_dir=EP_DIR):
    """その話に割り当てられた BGM のパス。無ければ None。"""
    p = plan(ep_dir)
    key = None
    for c in p.get("chapters", []):
        if c.get("n") == ep:
            key = c.get("bgm")
    key = key or (p.get("bgm") or {}).get("default")
    if not key:
        return None, None
    return resolve(key, ep_dir)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"
    if mode == "sample":
        key = sys.argv[2]
        sec = float(sys.argv[3]) if len(sys.argv) > 3 else None
        src, m = resolve(key)
        out = os.path.join(EP_DIR, "out", "bgm_sample_%s.wav" % os.path.splitext(key)[0][:28])
        vol = (plan().get("bgm") or {}).get("volume", 0.12)
        mix(os.path.join(EP_DIR, "out", "ep0.wav"), src, out, volume=vol, limit=sec)
        print("%s  （%s / %s）" % (out, m["license"], m.get("author") or "不明"))
    elif mode == "ep":
        ep = int(sys.argv[2])
        src, m = bgm_for(ep)
        nar = os.path.join(EP_DIR, "out", "ep%d.wav" % ep)
        if not src:
            print("第%d話に BGM は割り当てられていません" % ep)
        else:
            out = os.path.join(EP_DIR, "out", "ep%d_mixed.wav" % ep)
            vol = (plan().get("bgm") or {}).get("volume", 0.12)
            mix(nar, src, out, volume=vol)
            print("%s  （%s）" % (out, m["license"]))
    else:
        for k, m in sorted(catalog().items()):
            print("%-46s %-14s %5.0f秒" % (k[:46], m["license"], m.get("duration", 0)))
