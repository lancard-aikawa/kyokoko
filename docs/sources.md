# 素材ソースと出典表記

## 使う（権利が明快）

### 地理院タイル — 本命
出典明示のみ、申請不要。https://maps.gsi.go.jp/development/ichiran.html

表記: `出典: 国土地理院（地理院タイル）` ＋ 上記一覧ページへのリンク

| レイヤ | 用途 |
|---|---|
| 陰影起伏図・傾斜量図・色別標高図 | 高低差ネタ |
| 治水地形分類図 | 旧河道・自然堤防・後背湿地＝集落立地の理由 |
| 空中写真 1961〜69年（`ort_old10`） | 同一画角の時代重ね |
| 国土画像情報 1974〜78年（`gazo1`） | 同上 |
| 全国最新写真（`seamlessphoto`） | 現在の姿 |

**注意: `ort_USA10`（1945〜50年・米軍撮影）は全国をカバーしていない。**
長崎（z16 の該当タイル）は 404 で、最古は `ort_old10`（1961〜69年）だった。
町を決めたら、シナリオに年代を書く前に必ずタイルの存在を確認すること。

レイヤのズーム範囲: `relief` は 5〜15、`hillshademap` は 2〜16、
空中写真系は 10〜17、`seamlessphoto` / `ort` は 14〜18。
範囲外を指定すると拡大ぼけ、または透明（＝黒）になる。

### 自然災害伝承碑 — 碑のネタ元の芯
https://www.gsi.go.jp/bousaichiri/denshouhi.html
全国672市区町村2,403基（2025-12-25 時点）。位置・写真・碑文要約つき。CSV ダウンロード可。

### OpenStreetMap
ODbL。表記: `© OpenStreetMap contributors`
碑そのものは `historic=memorial` / `historic=monument` タグで拾える。

### PLATEAU
CC BY 4.0 等。商用可。3D都市モデル。https://www.mlit.go.jp/plateau/

### 基盤地図情報 数値標高モデル（DEM）
QGIS/Blender で地形3D化。

### Wikimedia Commons
CC / PD。碑・史跡の実写。ライセンスと著作者表記を画像ごとに記録すること。

### 国立国会図書館デジタルコレクション
PD の古写真・絵葉書・地誌（新編武蔵風土記稿など）。

### 文化遺産オンライン / 国指定文化財等データベース
検索用 API あり。https://bunkaedit.nii.ac.jp/system_03.html

## 条件つき・避ける

### Google Maps / Earth / Street View — 既定では使わない
教育・娯楽目的のオンライン動画なら収益化していても許諾不要だが、
**帰属表示を画面に出し続ける必要があり**（エンドクレジットへの移動は不可）、
自動での大量取得は規約違反になりやすい。地理院タイルで代替可能。

### 今昔マップ on the web — 動画への切り出しは不可
http://ktgis.net/kjmapw/note.html に「画像ファイル自体を複製して PC やサーバに
保存する方法での使用はしないでください」。
旧版地形図が要るときは、国土地理院の旧版地形図謄本、または
農研機構「歴史的農業環境閲覧システム」の迅速測図へ。

## 音声

VOICEVOX。クレジット表記で商用可。**キャラごとに規約が異なる**ため採用キャラは個別確認。
表記例: `VOICEVOX:春日部つむぎ` / `VOICEVOX:雀松朱司(CV:狐狗狸ラク)`

**キャラごとの企業利用の可否は docs/voicevox-characters.md に全43キャラ分をまとめた。**

### ⚠ 青山龍星（VirVox Project）— 企業・個人事業主は事前申請が必要

個人が「VOICEVOX:青山龍星」とクレジットして使うぶんには商用・非商用問わず可、
YouTube の収益化も可。ただし次の場合は**収益の有無にかかわらず**、
ななはぴ（https://v.seventhh.com/contact/）への事前申請・許可が必須。

1. 企業・個人事業主である場合
2. 企業と契約を結んだ個人である場合
3. 企業スポンサー契約を結んでスポンサー関係動画に使用する場合

また青山龍星はクレジット除去に対応していない（表記必須）。
規約: https://www.virvoxproject.com/voicevoxの利用規約

### 春日部つむぎ（KASUKABEproject）

クレジット表記で商用利用可。規約: https://tsumugi-official.studio.site/rule
