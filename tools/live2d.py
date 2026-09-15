# -*- coding: utf-8 -*-
"""Live2D モデルをブラウザで描画して、立ち絵の PNG を書き出す。

  python tools/live2d.py serve <モデルのフォルダ>

を起動してから http://127.0.0.1:8770/ を開き、ページの window.shoot(name, params)
を呼ぶと PNG がサーバに送られて out/ に落ちる。Playwright から叩く前提。

なぜランタイムで描くのか:
  Live2D は .moc3 と 3 枚のテクスチャアトラスでできていて、テクスチャをそのまま
  開いてもパーツがバラバラに並んでいるだけで立ち絵にはならない。組み立てて描く
  にはランタイムが要る。テクスチャ画像そのものには一切手を加えない。
"""
import io
import json
import os
import re
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = 8770

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Live2D 書き出し</title>
<style>html,body{margin:0;background:transparent}canvas{display:block}</style>
<!-- ローカルでだけ開く書き出し用のページ。配布物ではないので CDN 直参照にしている。
     版は固定してあるが、外に出すなら integrity を付けること。 -->
<script src="https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/pixi.js@6.5.10/dist/browser/pixi.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js"></script>
</head><body>
<script>
const W = 1000, H = 1500;
let app, model, ready = false, err = null;

async function boot(){
  try{
    app = new PIXI.Application({width:W, height:H, backgroundAlpha:0,
                                antialias:true, preserveDrawingBuffer:true});
    document.body.appendChild(app.view);
    const res = await fetch('/model.json');
    const {path} = await res.json();
    model = await PIXI.live2d.Live2DModel.from(path, {autoInteract:false});
    app.stage.addChild(model);
    // 画面いっぱいに収める
    const s = Math.min(W / model.width, H / model.height) * 0.98;
    model.scale.set(s);
    model.anchor.set(0.5, 0.5);
    model.position.set(W/2, H/2);
    // 絵が毎回変わると口パクで体がブレるので、動くものを全部止める。
    // これを止めないと、口だけ差し替えたつもりが髪揺れや呼吸まで変わり、
    // 差分が 600x770px にもなった（口だけなら 36x30px で済む）。
    app.ticker.stop();
    model.autoUpdate = false;
    if (model.internalModel.motionManager) model.internalModel.motionManager.stopAllMotions();
    if (model.internalModel.eyeBlink) model.internalModel.eyeBlink = null;
    if (model.internalModel.breath) model.internalModel.breath = null;
    if (model.internalModel.physics) model.internalModel.physics = null;
    ready = true;
  }catch(e){ err = String(e && e.stack || e); }
}
boot();

window.status_ = () => ({ready, err, w: model && model.width, h: model && model.height});

window.params = () => {
  const c = model.internalModel.coreModel;
  const n = c.getParameterCount();
  const out = [];
  for (let i=0;i<n;i++) out.push(c.getParameterId(i));
  return out;
};

// params は {パラメータID: 値} 。設定してから 1 フレーム描いて PNG を送る。
window.shoot = async (name, params) => {
  const c = model.internalModel.coreModel;
  for (const [k,v] of Object.entries(params||{})) {
    try { c.setParameterValueById(k, v); } catch(e) {}
  }
  model.internalModel.coreModel.update();
  model.internalModel.update(0, 0);
  app.renderer.render(app.stage);
  const url = app.view.toDataURL('image/png');
  const r = await fetch('/save?name=' + encodeURIComponent(name), {
    method:'POST', headers:{'Content-Type':'text/plain'}, body:url});
  return await r.text();
};
</script></body></html>
"""


class H(SimpleHTTPRequestHandler):
    model_dir = "."
    out_dir = "."

    def log_message(self, *a):
        pass

    def translate_path(self, path):
        p = urllib.parse.unquote(urllib.parse.urlparse(path).path).lstrip("/")
        return os.path.join(self.model_dir, p)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path).path
        if u == "/":
            b = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if u == "/model.json":
            name = [f for f in os.listdir(self.model_dir) if f.endswith(".model3.json")][0]
            b = json.dumps({"path": "/" + urllib.parse.quote(name)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path != "/save":
            self.send_error(404)
            return
        q = urllib.parse.parse_qs(u.query)
        name = re.sub(r"[^\w\-.ぁ-んァ-ヶ一-龠]", "_", q.get("name", ["out"])[0])
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n).decode("ascii", "ignore")
        import base64
        raw = base64.b64decode(data.split(",", 1)[1])
        os.makedirs(self.out_dir, exist_ok=True)
        p = os.path.join(self.out_dir, name + ".png")
        with open(p, "wb") as f:
            f.write(raw)
        b = ("%s (%d bytes)" % (p, len(raw))).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def main():
    H.model_dir = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else "."
    H.out_dir = os.path.abspath(sys.argv[3]) if len(sys.argv) > 3 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "download", "out")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("http://127.0.0.1:%d/  モデル: %s" % (PORT, H.model_dir))
    print("書き出し先: %s" % H.out_dir)
    srv.serve_forever()


if __name__ == "__main__":
    main()
