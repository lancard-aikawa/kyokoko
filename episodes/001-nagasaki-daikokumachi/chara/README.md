# このフォルダの中身は配布しないこと

立ち絵の元データ（Live2D モデル・PSD）はどれも**二次配布禁止**。
ここに書き出した PNG も派生物なので、リポジトリやアーカイブに含めて人に渡すと
二次配布にあたる。**使う人が自分で用意する部品**として扱う。

## 置き方

    つむぎ.png        口を閉じた絵
    つむぎ_open.png   口を開けた絵（任意。あれば音に合わせて口パクする）
    朱司.png
    朱司_open.png

## 作り方

Live2D モデルから（例: 春日部つむぎ）

    python tools/live2d.py serve download/<モデルのフォルダ> download/out
    # ブラウザで http://127.0.0.1:8770/ を開き window.shoot() を呼ぶ

PSD から（例: 雀松朱司 / PSDTool 形式）

    python tools/psd.py tree download/VriVoxProject-PSDs/akashi.psd
    python tools/psd.py shot download/VriVoxProject-PSDs/akashi.psd 朱司

## 規約で気をつけること

**音声と立ち絵は規約が別物で、立ち絵のほうが厳しい。**

| | 音声 | 立ち絵 |
|---|---|---|
| 雀松朱司（VirVox） | 法人可・申請不要 | 「個人が」の範囲。宣伝手段としての利用は要許諾 |
| ずんだもん等（東北ずん子PJ） | 商用可・無償 | 東北6県の企業以外は個別契約（有償） |
| 春日部つむぎ | 商用可 | 法人の記述なし。加筆・加工は禁止 |

とくに **「このプログラムでこういう動画が作れます」と見せる用途**は、
他のコンテンツの宣伝手段としての利用にあたり、たいていのキャラで許諾が要る。
**既定では立ち絵は出ない。**入れたいときだけ `--chara` を付ける。

    python tools/build.py all            立ち絵なし（既定）
    python tools/build.py all --chara    立ち絵あり
