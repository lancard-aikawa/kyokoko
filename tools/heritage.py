# -*- coding: utf-8 -*-
"""近代化産業遺産（経済産業省）の一覧を、座標つきで取り出す。

  python tools/heritage.py fetch     PDF を取ってくる
  python tools/heritage.py text      PDF を日本語のテキストに落とす（ここまでは動く）
  python tools/heritage.py parse     表を組み立てる（**未完成**。下の「残っている壁」）
  python tools/heritage.py geocode   市区町村名から座標を引く（地理院の住所検索）
  python tools/heritage.py near <町名>   その町の近くのものを出す

出所は経済産業省の2つの PDF。
  平成19年度「近代化産業遺産群 33」        575件
  平成20年度「近代化産業遺産群 続33」      540件

## PDF がそのままでは読めない

3つ重なっている。ここを踏むと1日溶けるので順に書いておく。

1. **METI は bot を弾く。**curl も、ブラウザ内の fetch も、最初は 202 と
   HTML が返る（AWS WAF）。一度ブラウザでそのURLを開くと `aws-waf-token` の
   Cookie が付き、それを渡せば curl でも 200 になる。

2. **poppler は Adobe-Japan1 の対応表を持っていない。**
   `Unknown character collection 'Adobe-Japan1'` が出て、日本語が化ける。
   poppler-data（https://poppler.freedesktop.org/）の `cidToUnicode/Adobe-Japan1`
   を使って、あとから直す。`.cache/poppler-data-*/` に置いてある。

3. **抽出器は CID をそのままコードポイントとして吐く。**
   poppler も pypdf も同じ挙動だった。つまり「地域」が「஍Ҭ」になる。
   上の対応表で 1 文字ずつ引き直せば戻る（`decode_cid`）。

さらに `-layout` を使うと**文字の順番が入れ替わる**（「近代化産業」→「産近業代化」）。
`-raw` なら崩れない。ここまでで、日本語のテキストは正しく取れる。

## 残っている壁 — 表の列が復元できない

本文は取れるが、**575件の表を組み立てるところで止まっている。**

この PDF は121ページの読み物で、中に33個の表が埋まっている。列は
都道府県 / 市区町村 / 遺産（群のテーマ）/ 名称（不動産）/ 内訳（動産）。

- `pdftotext -raw` は**文字順は正しいが、列が失われる**。字下げも付かない
  （見た目の字下げは端末側の整形で、生テキストには無い）
- `pypdf` の `extract_text(visitor_text=...)` なら**座標が取れて列は分かる**
  （x=61 県 / 115 市区町村 / 169 群 / 297 不動産 / 425 動産）。
  ただしテキスト実行の順序が乱れていて、**セル内の文字が入れ替わる**
  （「事業」→「業事」、「市区」→「区市」）。poppler はこれを直しているが、
  pypdf は直さない

つまり「順序は poppler、列は pypdf」で、片方ずつしか取れない。
両方いっぺんに欲しいなら、レイアウトを解釈するライブラリ（pdfplumber か
PyMuPDF）を入れるのが素直。どちらも1行で入るが、**この環境には無い**ので
入れるかどうかは持ち主が決めること。

いまのところ `土木` テーマの候補は選奨土木遺産（約500件・HTML・座標化ずみの手口）
で足りているので、ここは急がない。
"""
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")
OUT = os.path.join(ROOT, "assets", "heritage.json")
UA = "MachiBura/1.0 (https://github.com/lancard-aikawa/machibura-gallery)"

PDFS = {
    "isangun": ("近代化産業遺産群 33", 2007),
    "isangun_zoku": ("近代化産業遺産群 続33", 2008),
}
BASE = ("https://www.meti.go.jp/policy/mono_info_service/mono/creative/"
        "kindaikasangyoisan/pdf/")

PREF = ("北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|"
        "埼玉県|千葉県|東京都|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|"
        "岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|"
        "鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|"
        "佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県")
PREF_RE = re.compile(r"^(%s)" % PREF)
CITY_RE = re.compile(r"^([一-鿿ぁ-ゟァ-ヿヶ]{1,8}?[市区町村郡])")


def cid_table():
    d = [x for x in os.listdir(CACHE) if x.startswith("poppler-data")] if os.path.isdir(CACHE) else []
    d = [x for x in d if os.path.isdir(os.path.join(CACHE, x))]
    if not d:
        sys.exit("poppler-data がありません。tools/heritage.py fetch を先に。")
    p = os.path.join(CACHE, sorted(d)[-1], "cidToUnicode", "Adobe-Japan1")
    return [l.strip() for l in io.open(p, encoding="ascii")]


def decode_cid(s, tbl):
    """抽出器が CID をそのまま吐いた文字列を、日本語に戻す。"""
    out = []
    for ch in s:
        c = ord(ch)
        if 0x0080 <= c < len(tbl) and tbl[c] and tbl[c] != "0000":
            u = tbl[c]
            out.append("".join(chr(int(u[i:i + 4], 16)) for i in range(0, len(u), 4)))
        else:
            out.append(ch)
    return "".join(out)


def fetch():
    """PDF と poppler-data を .cache に置く。

    METI は bot を弾くので、Cookie が要る。ブラウザで一度 PDF の URL を開いて
    `aws-waf-token` を取り、環境変数 METI_COOKIE に入れてから実行する。
    """
    os.makedirs(CACHE, exist_ok=True)
    pd = os.path.join(CACHE, "poppler-data-0.4.12")
    if not os.path.isdir(pd):
        tgz = os.path.join(CACHE, "poppler-data.tar.gz")
        urllib.request.urlretrieve(
            "https://poppler.freedesktop.org/poppler-data-0.4.12.tar.gz", tgz)
        subprocess.run(["tar", "xzf", tgz, "-C", CACHE], check=True)
        print("poppler-data を展開しました")
    ck = os.environ.get("METI_COOKIE", "")
    for name in PDFS:
        p = os.path.join(CACHE, name + ".pdf")
        if os.path.exists(p) and os.path.getsize(p) > 100000:
            print("あり: %s" % name); continue
        if not ck:
            print("METI_COOKIE が要ります。ブラウザで次を開いて aws-waf-token を取る:")
            print("  " + BASE + name + ".pdf")
            continue
        r = urllib.request.urlopen(urllib.request.Request(
            BASE + name + ".pdf", headers={"User-Agent": UA, "Cookie": ck,
                                           "Referer": BASE}), timeout=240)
        io.open(p, "wb").write(r.read())
        print("取得: %s (%d bytes)" % (name, os.path.getsize(p)))


def text_of(name):
    """PDF を -raw で抜いて、CID を直して返す。"""
    pdf = os.path.join(CACHE, name + ".pdf")
    txt = os.path.join(CACHE, name + ".raw.txt")
    if not os.path.exists(txt):
        subprocess.run(["pdftotext", "-raw", "-enc", "UTF-8", pdf, txt],
                       capture_output=True)
    s = io.open(txt, encoding="utf-8").read()
    for c in "‪‫‬‭‮‎‏":
        s = s.replace(c, "")
    return decode_cid(s, cid_table())


def dump_text():
    """日本語のテキストを .cache に落とす。ここまでは確実に動く。"""
    for name in PDFS:
        if not os.path.exists(os.path.join(CACHE, name + ".pdf")):
            print("PDFなし: %s" % name); continue
        t = text_of(name)
        p = os.path.join(CACHE, name + ".ja.txt")
        io.open(p, "w", encoding="utf-8").write(t)
        print("%s -> %s (%d文字)" % (name, p, len(t)))


def parse():
    """**未完成。**構成遺産リストの行から 都道府県・市区町村・名称 を拾う。

    -raw のテキストは列が失われているので、いまは本文まで拾ってしまい
    件数が桁で合わない（575件のところ 9,446行になった）。
    列を正しく取るにはレイアウトを解釈するライブラリが要る。
    モジュール先頭の「残っている壁」を参照。
    """
    print("※ parse は未完成です。tools/heritage.py の先頭を読んでください。")
    rows = []
    for name, (label, year) in PDFS.items():
        if not os.path.exists(os.path.join(CACHE, name + ".pdf")):
            print("飛ばした（PDFなし）: %s" % name); continue
        pref = city = None
        for raw in text_of(name).splitlines():
            line = raw.strip()
            if not line or line in ("−", "-", "―"):
                continue
            m = PREF_RE.match(line)
            if m:
                pref = m.group(1); line = line[len(pref):].strip(); city = None
            m = CITY_RE.match(line)
            if m and pref:
                city = m.group(1); line = line[len(city):].strip()
            if not pref or not line:
                continue
            # 表題・注記・ページ番号は落とす
            if re.match(r"^[0-9０-９\s]+$", line) or "構成遺産リスト" in line:
                continue
            if line.startswith(("（", "※", "◆", "内訳", "地域", "名称", "遺産")):
                continue
            rows.append({"pref": pref, "city": city or "", "name": line,
                         "group": label, "year": year})
    # 行の折り返しでちぎれた短い断片は前の行にくっつける
    merged = []
    for r in rows:
        if merged and len(r["name"]) <= 3 and merged[-1]["pref"] == r["pref"]:
            merged[-1]["name"] += r["name"]
        else:
            merged.append(r)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump({"_source": "経済産業省 近代化産業遺産",
                   "_note": "PDF から機械で抜いたもの。表記ゆれと取りこぼしがある",
                   "items": merged}, f, ensure_ascii=False, indent=1)
    print("%d件を書きました -> %s" % (len(merged), OUT))
    by = {}
    for r in merged:
        by[r["pref"]] = by.get(r["pref"], 0) + 1
    print("都道府県 %d、うち長崎県 %d件" % (len(by), by.get("長崎県", 0)))
    return merged


def geocode(limit=None):
    """市区町村名から座標を引く。地理院の住所検索。同じ市は1回しか引かない。"""
    d = json.load(io.open(OUT, encoding="utf-8"))
    cache = {}
    n = 0
    for r in d["items"]:
        if not r.get("city") or r.get("lat"):
            continue
        q = r["pref"] + r["city"]
        if q not in cache:
            u = ("https://msearch.gsi.go.jp/address-search/AddressSearch?q="
                 + urllib.parse.quote(q))
            try:
                j = json.load(urllib.request.urlopen(
                    urllib.request.Request(u, headers={"User-Agent": UA}), timeout=20))
                cache[q] = j[0]["geometry"]["coordinates"] if j else None
            except Exception:
                cache[q] = None
            time.sleep(0.3)
            n += 1
            if limit and n >= limit:
                break
        if cache[q]:
            r["lon"], r["lat"] = cache[q]
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    got = sum(1 for r in d["items"] if r.get("lat"))
    print("座標つき %d / %d件（市区町村 %d種を照会）" % (got, len(d["items"]), n))


def near(town, km=15.0):
    import math
    u = ("https://msearch.gsi.go.jp/address-search/AddressSearch?q="
         + urllib.parse.quote(town))
    j = json.load(urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": UA}), timeout=20))
    if not j:
        sys.exit("町が見つかりません: %s" % town)
    lon0, lat0 = j[0]["geometry"]["coordinates"]
    print("%s  %.5f, %.5f" % (town, lat0, lon0))
    d = json.load(io.open(OUT, encoding="utf-8"))
    out = []
    for r in d["items"]:
        if not r.get("lat"):
            continue
        dx = (r["lon"] - lon0) * 111.32 * math.cos(math.radians(lat0))
        dy = (r["lat"] - lat0) * 111.32
        km_ = math.hypot(dx, dy)
        if km_ <= km:
            out.append((km_, r))
    for km_, r in sorted(out)[:30]:
        print("  %5.1fkm  %s%s  %s" % (km_, r["pref"], r["city"], r["name"][:44]))
    print("%d件" % len(out))


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "parse"
    if a == "fetch":
        fetch()
    elif a == "text":
        dump_text()
    elif a == "parse":
        parse()
    elif a == "geocode":
        geocode()
    elif a == "near":
        near(sys.argv[2] if len(sys.argv) > 2 else "長崎市大黒町")
    else:
        print(__doc__)
