# -*- coding: utf-8 -*-
"""回のフォルダの中で、どれが作業場でどれが成果物かを決める1か所。

  out/    作業場。話ごとの wav と mp4、タイムライン、構図確認の静止画。
          作り直せるし、20個以上たまる。
  dist/   最終成果物。**ここだけ見れば公開できる**ようにする。
          通し・配布用・字幕・YouTube のタイトルと概要欄・サムネイル候補。

分けたのは、out/ の中に中間物と成果物が混ざっていて「結局どれを上げるのか」が
毎回分からなくなったため。dist/ の中身も作り直せるので、追跡はしない。
"""
import os


def out_dir(ep_dir, make=False):
    """作業場。"""
    d = os.path.join(ep_dir, "out")
    if make:
        os.makedirs(d, exist_ok=True)
    return d


def dist_dir(ep_dir, make=False):
    """最終成果物の置き場。"""
    d = os.path.join(ep_dir, "dist")
    if make:
        os.makedirs(d, exist_ok=True)
    return d


def full_mp4(ep_dir):
    """通し。YouTube に上げるのはこれ。"""
    return os.path.join(dist_dir(ep_dir), "%s.mp4" % os.path.basename(ep_dir))


def web_mp4(ep_dir, suffix="-web"):
    """軽くした複製。ファイルとして直接配るのはこれ（Releases）。"""
    return os.path.join(dist_dir(ep_dir),
                        "%s%s.mp4" % (os.path.basename(ep_dir), suffix))


def srt_path(ep_dir):
    return os.path.join(dist_dir(ep_dir), "%s.srt" % os.path.basename(ep_dir))


def youtube_paths(ep_dir):
    """YouTube にそのまま貼る2つ。タイトルと概要欄。"""
    d = dist_dir(ep_dir)
    return (os.path.join(d, "youtube-title.txt"),
            os.path.join(d, "youtube-description.txt"))
