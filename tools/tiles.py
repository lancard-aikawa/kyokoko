# -*- coding: utf-8 -*-
"""地理院タイルを取得してつなぎ、指定サイズの画像として返す。

出典表示が必要（動画に焼き込むこと）:
  出典: 国土地理院（地理院タイル） https://maps.gsi.go.jp/development/ichiran.html
"""
import io
import math
import os
import time
import urllib.request

from PIL import Image

BASE = "https://cyberjapandata.gsi.go.jp/xyz/{layer}/{z}/{x}/{y}.{ext}"
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "tiles")
UA = "kokogallery/0.1 (personal video production; contact via local use)"

# レイヤ定義: id -> (拡張子, 使えるズーム範囲, 表示名)
LAYERS = {
    "pale":          ("png", (5, 16), "淡色地図"),
    "std":           ("png", (5, 18), "標準地図"),
    "blank":         ("png", (5, 14), "白地図"),
    "hillshademap":  ("png", (2, 16), "陰影起伏図"),
    "relief":        ("png", (5, 15), "色別標高図"),
    "slopemap":      ("png", (3, 15), "傾斜量図"),
    # ズーム範囲はただのメモではない。clip.Master がこの下限まで切り上げて
    # 取りに行くので、狭く書くと広い画角のとき欠測だらけの絵になる。
    # シームレス写真は z5 でも欠けない（実測 0%）。14 と書いていたせいで
    # z12 の俯瞰が z14 に繰り上がり、第004回で真っ黒になった。
    "seamlessphoto": ("jpg", (5, 18), "全国最新写真（シームレス）"),
    "ort":           ("jpg", (14, 18), "電子国土基本図（オルソ画像）2007年〜"),
    # 歴史的空中写真。長崎は ort_USA10 の範囲外（404）なので ort_old10 が最古。
    "ort_USA10":     ("png", (10, 17), "空中写真 1945〜50年"),
    "ort_old10":     ("png", (10, 17), "空中写真 1961〜69年"),
    "gazo1":         ("jpg", (10, 17), "国土画像情報 1974〜78年"),
    "gazo2":         ("jpg", (10, 17), "国土画像情報 1979〜83年"),
    "gazo3":         ("jpg", (10, 17), "国土画像情報 1984〜86年"),
    "gazo4":         ("jpg", (10, 17), "国土画像情報 1987〜90年"),
    # さらに古い層。整備範囲が極端に狭い（2026-09-16 実測）。
    #   ort_1928    大阪のみ。東京も名古屋も 404
    #   ort_riku10  東京と大阪のみ
    # 長崎県はどちらも ort_USA10 も含めて全滅で、1961年が最古になる。
    "ort_1928":      ("png", (13, 18), "空中写真 1928年頃"),
    "ort_riku10":    ("png", (13, 18), "空中写真 1936〜42年（旧陸軍撮影）"),

    # --- 地形・土地の成り立ち --------------------------------------
    # 「いま町になっている場所が、かつて何だったか」を語るための層。
    # swale は長崎でも出る。第001回の「入り江の上に駅が立った」が絵になる。
    "swale":         ("png", (10, 16), "明治期の低湿地"),
    "lcm25k_2012":   ("png", (10, 16), "土地条件図（数値地図25000）"),
    # 治水地形分類図は主要河川の流域だけ。長崎県内では諫早湾しか出なかった。
    "lcmfc2":        ("png", (11, 16), "治水地形分類図"),
    "ccm1":          ("png", (14, 16), "沿岸海域土地条件図（平成元年以降）"),
    "ccm2":          ("png", (14, 16), "沿岸海域土地条件図（昭和63年以前）"),

    # --- 火山 ------------------------------------------------------
    # 火山限定の整備。市街地では 404 になるので、最初に街で叩いて
    # 「無い」と早合点しないこと。富士・雲仙・桜島・阿蘇で確認済み。
    "sekishoku":     ("png", (2, 16), "赤色立体地図"),
    "vlcd":          ("png", (10, 16), "火山土地条件図"),
    "vbm":           ("png", (11, 17), "火山基本図"),
    "afm":           ("png", (11, 16), "活断層図（都市圏）"),
}


def deg2num(lat, lon, z):
    """緯度経度 -> タイル座標（小数）"""
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y


def num2deg(x, y, z):
    """タイル座標（小数） -> 緯度経度"""
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def fetch_tile(layer, z, x, y):
    ext = LAYERS[layer][0]
    path = os.path.join(CACHE, layer, str(z), str(x), "%d.%s" % (y, ext))
    if os.path.exists(path):
        return Image.open(path).convert("RGBA")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = BASE.format(layer=layer, z=z, x=x, y=y, ext=ext)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:  # そのズーム・範囲にタイルが無い
            return Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        raise
    with open(path, "wb") as f:
        f.write(data)
    time.sleep(0.05)  # 相手のサーバに気を遣う
    return Image.open(io.BytesIO(data)).convert("RGBA")


def render(layer, lat, lon, z, w, h):
    """中心(lat,lon)・ズームz で w×h ピクセルの画像を作る。"""
    cx, cy = deg2num(lat, lon, z)
    px, py = cx * 256.0, cy * 256.0          # 世界ピクセル座標
    left, top = px - w / 2.0, py - h / 2.0
    tx0, ty0 = int(math.floor(left / 256)), int(math.floor(top / 256))
    tx1, ty1 = int(math.floor((left + w) / 256)), int(math.floor((top + h) / 256))
    canvas = Image.new("RGBA", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            canvas.paste(fetch_tile(layer, z, tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    ox, oy = int(left - tx0 * 256), int(top - ty0 * 256)
    return canvas.crop((ox, oy, ox + w, oy + h))


if __name__ == "__main__":
    import sys
    layer = sys.argv[1] if len(sys.argv) > 1 else "pale"
    img = render(layer, 32.7555, 129.8703, 16, 800, 600)
    out = os.path.join(CACHE, "_test_%s.png" % layer)
    img.convert("RGB").save(out)
    print(out, img.size)
