# MachiBura

〒や町名を指定すると、その町の遺構・歴史建造物・地名の由来にまつわる「碑」の話を集め、
読み上げシナリオを作り、VOICEVOX と地図で動画にする。参考番組: ブラタモリ。

第001回は長崎市大黒町。アバン＋3話で 9分31秒。

## つくり

```
docs/
  format.md                  番組フォーマット（話者・口調・話数・映像方針・表記規約）
  sources.md                 素材ソースと出典表記・権利の可否
  voicevox-characters.md     全43キャラの「音声」の企業利用可否
  character-art-license.md   「立ち絵」の企業利用可否（音声とは別物。こちらは厳しい）

tools/
  tiles.py      地理院タイルの取得（キャッシュつき）
  photos.py     Wikimedia Commons から写真を取得。ライセンスごと記録する
  readings.py   読みの補正・巻き添えの検出・アクセント句の確認
  readings.json 読みの補正辞書
  tts.py        VOICEVOX で合成し、話ごとに 1 本の wav に組み立てる
  editor.py     語りの微調整用のブラウザUI（localhost:8765）
  live2d.py     Live2D モデルから立ち絵の PNG を書き出す
  psd.py        PSDTool 形式の PSD から立ち絵の PNG を書き出す
  clip.py       地図のカメラワーク・写真・字幕・タイトル・立ち絵を描く
  build.py      ショットを連結して音声を乗せる

episodes/001-nagasaki-daikokumachi/
  research.md   調査メモ（年表・碑・座標・出典）
  script.md     読み上げシナリオ（カット指示・ふりがな・クレジット）
  shots.py      ショットの構図定義
  photos.json   写真の作者・ライセンス・出典 URL
  photos/       写真そのもの
  chara/        立ち絵を置く場所（中身は配らない。README.md 参照）
  out/          音声・動画・タイムライン（生成物。git には入れない）
```

## 作る手順

1. **VOICEVOX エンジンを起動**

   ```
   "%LOCALAPPDATA%\Programs\VOICEVOX\vv-engine\run.exe" --host 127.0.0.1 --port 50021
   ```

2. **調べて `research.md` と `script.md` を書く**（Claude との会話で）

3. **読みを確かめる**

   ```
   python tools/readings.py diff      補正の前後で何が変わるかを見る
   python tools/readings.py phrases "<台詞>"   アクセント句と核の位置
   ```

4. **合成**

   ```
   python tools/tts.py
   ```

5. **構図を確かめる**

   ```
   python tools/build.py check        各ショットの真ん中を静止画で
   ```

6. **動画にする**

   ```
   python tools/build.py all          全話 + 通し（立ち絵なし）
   python tools/build.py 2 3          一部だけ作り直す
   python tools/build.py remux        音声だけ差し替える（絵が変わっていないとき）
   python tools/build.py all --chara  立ち絵を入れる
   ```

## つまずきどころ

この番組を作る過程で実際に踏んだもの。同じ穴を掘らないための覚え書き。

**アクセントは `accent` を書き換えただけでは音に出ない。**
合成が見ているのはモーラごとの `pitch` で、`accent` はただの印。書き換えたあと
`/mora_data` で計算し直さないと、画面上は核が動いて見えるのに音は一切変わらない。
`tts.SYNTH_VERSION` を上げると全行を録り直せる。

**ffmpeg の concat + outpoint は無音を正確に切れない。**
`-c copy` ではパケット境界でしか切れず、1 箇所あたり 0.05〜0.08 秒ずつ伸びる。
無音が 28 箇所あると 1.4 秒ずれて、字幕が後半ほど音声から遅れる。
いまはサンプル単位で自分で組み立てている（`tts.concat_wav`）。

**読み辞書を直したら録り直しが要る。**
台詞も設定も変えていないので、判定に辞書の指紋を混ぜないと古い音声が残る。

**語単位の辞書は複合語を巻き添えにする。**
「碑」を ヒ に直したら「石碑」が イシヒ になった。`readings.py diff` が
`guard` 語の読みを補正前後で比べて教えてくれる。1 か所だけ直したいときは
script.md に `碑《ひ》` と書く（ルビ）。

**ルビの範囲は漢字・カタカナの連なりだけに限る。**
`[^《》]+?` のように書くと直前の地の文まで飲み込み、「この碑《ひ》って」が
「ひって」になる。読み文が字幕文より極端に短くなったら止まるようにしてある。

**地理院タイルはレイヤごとに範囲が違う。**
`ort_USA10`（1945〜50年の米軍撮影）は全国をカバーしておらず、長崎は 404 だった。
シナリオに年代を書く前にタイルの存在を確かめること。

**画像はファイル名を信じない。**
`Nagasaki-Dejima-1770.jpg` は 1770 年の絵図ではなく、現代の復元建物の写真だった
（数字はカメラの連番）。必ず開いて中身を見る。

**VOICEVOX は音声と立ち絵で規約が別物。**
音声が法人フリーでも、立ち絵は法人要許諾のキャラが多い。とくに
「このプログラムでこんな動画が作れます」と見せる用途は宣伝手段にあたり、
ほぼ確実に許諾が要る。だから立ち絵は既定では出さない。
詳しくは `docs/character-art-license.md`。

## 出典表示

動画には焼き込み済み。概要欄に貼る分は `script.md` の末尾にある。

- 地図: 出典 国土地理院（地理院タイル）
- 音声: VOICEVOX:春日部つむぎ / VOICEVOX:雀松朱司(CV:狐狗狸ラク)
- 写真: Wikimedia Commons（作者とライセンスは `photos.json`）
