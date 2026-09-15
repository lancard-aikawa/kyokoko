# -*- coding: utf-8 -*-
"""語りの微調整用のブラウザUI。

  python tools/editor.py [ep_dir]     http://127.0.0.1:8765 を開く

できること:
  - 行ごとに 話者・抑揚・速度・高さ を変える
  - アクセント句の核をクリックで動かす
  - その場で合成して聴く（VOICEVOX エンジンに直接投げる）
  - voice.json に保存する
  - 変更した行だけ録り直す

script.md は触らない。文章とふりがなは人が書くもので、ここで直すのは語り方だけ。
"""
import io
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(ROOT, "episodes", "001-nagasaki-daikokumachi")
PORT = 8765

HTML = r"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MachiBura 語り調整</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--line:#e2e2dd;--ink:#1c1c1a;--dim:#77776f;
      --tsumugi:#c98a12;--akashi:#2f7fbf;--accent:#d94f30}
*{box-sizing:border-box}
body{margin:0;font:14px/1.6 "BIZ UDPGothic","Yu Gothic UI",system-ui,sans-serif;
     background:var(--bg);color:var(--ink);height:100vh;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--panel);
       border-bottom:1px solid var(--line);flex:0 0 auto}
header h1{font-size:15px;margin:0;font-weight:700}
header .sp{flex:1}
button{font:inherit;padding:6px 14px;border:1px solid var(--line);background:#fff;
       border-radius:6px;cursor:pointer}
button:hover{background:#f0f0ec}
button.primary{background:var(--ink);color:#fff;border-color:var(--ink)}
button.primary:hover{background:#000}
button:disabled{opacity:.45;cursor:default}
#msg{color:var(--dim);font-size:13px}
main{flex:1;display:flex;min-height:0}
#list{width:46%;overflow:auto;border-right:1px solid var(--line)}
#detail{flex:1;overflow:auto;padding:18px 22px}
table{width:100%;border-collapse:collapse}
tr.ep td{background:#edece7;font-weight:700;font-size:12px;color:var(--dim);
         padding:5px 12px;position:sticky;top:0}
tbody tr.row{cursor:pointer;border-bottom:1px solid var(--line)}
tbody tr.row:hover{background:#efeeea}
tbody tr.row.sel{background:#e4eef6}
td{padding:6px 10px;vertical-align:top}
td.n{width:42px;color:var(--dim);font-variant-numeric:tabular-nums;text-align:right}
td.who{width:74px;font-weight:700;white-space:nowrap}
td.who.t{color:var(--tsumugi)} td.who.a{color:var(--akashi)}
td.dur{width:52px;color:var(--dim);text-align:right;font-variant-numeric:tabular-nums}
td.txt{font-size:13px;max-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tag{display:inline-block;margin-left:6px;padding:0 6px;border-radius:99px;
     background:var(--accent);color:#fff;font-size:11px;vertical-align:1px}
h2{font-size:13px;color:var(--dim);margin:22px 0 8px;font-weight:700;
   letter-spacing:.04em}
h2:first-child{margin-top:0}
.sub{font-size:17px;line-height:1.7;background:var(--panel);border:1px solid var(--line);
     border-radius:8px;padding:12px 14px}
.sub .rd{display:block;margin-top:6px;font-size:13px;color:var(--dim)}
.grid{display:grid;grid-template-columns:70px 1fr 62px;gap:10px 12px;align-items:center}
.grid label{color:var(--dim);font-size:13px}
input[type=range]{width:100%}
.val{font-variant-numeric:tabular-nums;text-align:right;font-size:13px}
select{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;
       background:#fff;width:100%}
.phr{display:flex;flex-wrap:wrap;gap:10px}
.ph{border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:6px 8px}
.ph .ms{display:flex;gap:2px}
.mora{min-width:26px;text-align:center;padding:3px 4px;border-radius:5px;cursor:pointer;
      border:1px solid transparent;font-size:15px}
.mora:hover{background:#eee}
.mora.hi{background:var(--accent);color:#fff}
.ph .cap{font-size:11px;color:var(--dim);text-align:center;margin-top:3px}
.hint{color:var(--dim);font-size:12px;margin-top:6px}
.row2{display:flex;gap:8px;align-items:center;margin-top:10px}
</style></head><body>
<header>
  <h1>MachiBura 語り調整</h1>
  <span id="msg"></span><span class="sp"></span>
  <button id="reset">この行を既定に戻す</button>
  <button id="resynth">変更した行を録り直す</button>
  <button id="save" class="primary">voice.json に保存</button>
</header>
<main>
  <div id="list"></div>
  <div id="detail"><p class="hint">左の一覧から行を選んでください。</p></div>
</main>
<script>
let S=null, cur=null, dirty=new Set(), audio=new Audio();

const api=(p,o)=>fetch(p,o).then(r=>r.ok?r.json():r.text().then(t=>{throw new Error(t)}));
const msg=t=>{document.getElementById('msg').textContent=t;};

function lineCfg(i){ return (S.voice.lines[String(i)] ||= {}); }
function hasOverride(i){ const c=S.voice.lines[String(i)]; return c && Object.keys(c).length>0; }
function setting(i,k){
  const L=S.lines.find(x=>x.index===i);
  const d=S.voice.defaults[L.speaker]||{};
  const c=S.voice.lines[String(i)]||{};
  return c[k]!==undefined?c[k]:d[k];
}

function renderList(){
  let h='<table><tbody>', ep=null;
  for(const L of S.lines){
    if(L.episode!==ep){ ep=L.episode; h+=`<tr class="ep"><td colspan="4">第${ep}話</td></tr>`; }
    const cls=L.speaker==='つむぎ'?'t':'a';
    h+=`<tr class="row" data-i="${L.index}"><td class="n">${L.index}</td>`+
       `<td class="who ${cls}">${L.speaker}</td>`+
       `<td class="txt" title="${esc(L.text)}">${esc(L.text)}${hasOverride(L.index)?'<span class="tag">調整</span>':''}</td>`+
       `<td class="dur">${L.duration.toFixed(1)}</td></tr>`;
  }
  document.getElementById('list').innerHTML=h+'</tbody></table>';
  document.querySelectorAll('tr.row').forEach(tr=>tr.onclick=()=>select(+tr.dataset.i));
  if(cur) markSel();
}
function markSel(){
  document.querySelectorAll('tr.row').forEach(tr=>
    tr.classList.toggle('sel', +tr.dataset.i===cur));
}
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function select(i){
  cur=i; markSel();
  const L=S.lines.find(x=>x.index===i);
  const d=document.getElementById('detail');
  const opts=S.speakers.map(s=>
    `<option value="${s.id}"${s.id===setting(i,'speaker')?' selected':''}>${s.label}</option>`).join('');
  d.innerHTML=`
    <h2>台詞</h2>
    <div class="sub">${esc(L.text)}<span class="rd">読み: ${esc(L.read)}</span></div>
    <h2>話者</h2><select id="spk">${opts}</select>
    <h2>声のつまみ</h2>
    <div class="grid">
      ${slider('intonationScale','抑揚',0,2,0.05,i)}
      ${slider('speedScale','速度',0.5,1.6,0.01,i)}
      ${slider('pitchScale','高さ',-0.15,0.15,0.01,i)}
    </div>
    <h2>アクセント句 — モーラをクリックすると核がそこに移る。核をもう一度押すと平板</h2>
    <div class="phr" id="phr">読み込み中…</div>
    <div class="hint">赤いモーラの直後で音が下がる。核なし（平板）は下の数字が 0。</div>
    <div class="row2"><button id="play" class="primary">▶ 試聴</button>
      <span class="hint" id="pstat"></span></div>`;
  document.getElementById('spk').onchange=e=>{ lineCfg(i).speaker=+e.target.value; touch(i); loadPhrases(); };
  ['intonationScale','speedScale','pitchScale'].forEach(k=>{
    const el=document.getElementById('r_'+k);
    el.oninput=e=>{ document.getElementById('v_'+k).textContent=(+e.target.value).toFixed(2);
                    lineCfg(i)[k]=+e.target.value; touch(i); };
  });
  document.getElementById('play').onclick=preview;
  loadPhrases();
}
function slider(k,label,min,max,step,i){
  const v=setting(i,k);
  return `<label>${label}</label>
    <input type="range" id="r_${k}" min="${min}" max="${max}" step="${step}" value="${v}">
    <span class="val" id="v_${k}">${(+v).toFixed(2)}</span>`;
}
function touch(i){ dirty.add(i); renderList(); msg(dirty.size+' 行を変更中'); }

async function loadPhrases(){
  const i=cur;
  const r=await api('/api/phrases?index='+i+'&cfg='+encodeURIComponent(JSON.stringify(S.voice.lines[String(i)]||{})));
  if(cur!==i) return;
  const box=document.getElementById('phr');
  box.innerHTML=r.phrases.map((p,pi)=>
    `<div class="ph"><div class="ms">`+
    p.moras.map((m,mi)=>`<span class="mora${p.accent===mi+1?' hi':''}" data-p="${pi}" data-m="${mi}">${m}</span>`).join('')+
    `</div><div class="cap">核 ${p.accent}</div></div>`).join('');
  box.querySelectorAll('.mora').forEach(el=>el.onclick=()=>{
    const pi=+el.dataset.p, mi=+el.dataset.m, p=r.phrases[pi];
    const next = p.accent===mi+1 ? 0 : mi+1;
    const c=lineCfg(i); c.accents=(c.accents||[]).filter(a=>a.i!==pi);
    c.accents.push({i:pi, moras:p.moras.join(''), accent:next});
    touch(i); loadPhrases();
  });
}

async function preview(){
  const i=cur, st=document.getElementById('pstat');
  st.textContent='合成中…';
  const res=await fetch('/api/preview',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({index:i, cfg:S.voice.lines[String(i)]||{}})});
  if(!res.ok){ st.textContent='失敗: '+await res.text(); return; }
  audio.src=URL.createObjectURL(await res.blob()); audio.play();
  st.textContent='';
}

document.getElementById('reset').onclick=()=>{
  if(!cur) return; delete S.voice.lines[String(cur)]; dirty.add(cur); renderList(); select(cur);
};
document.getElementById('save').onclick=async()=>{
  await api('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},
                         body:JSON.stringify(S.voice)});
  msg('voice.json に保存しました');
};
document.getElementById('resynth').onclick=async()=>{
  msg('録り直しています…');
  const r=await api('/api/resynth',{method:'POST'});
  S.lines=r.lines; dirty.clear(); renderList(); msg('録り直しました（合計 '+r.total+'）');
};

api('/api/state').then(s=>{ S=s; renderList(); });
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    ep_dir = EP_DIR

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False))

    def _rows(self):
        return tts.parse(os.path.join(self.ep_dir, "script.md"))

    def _timeline(self):
        p = os.path.join(self.ep_dir, "out", "timeline.json")
        return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else []

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/":
                return self._send(200, HTML, "text/html; charset=utf-8")
            if u.path == "/favicon.ico":
                return self._send(200, b"", "image/x-icon")
            if u.path == "/api/state":
                cfg = tts.load_voice(self.ep_dir)
                dur = {r["index"]: r["duration"] for r in self._timeline()}
                lines = [{"index": r["index"], "episode": r["episode"], "cut": r["cut"],
                          "speaker": r["speaker"], "text": r["text"], "read": r["read"],
                          "duration": dur.get(r["index"], 0.0)} for r in self._rows()]
                spk = json.loads(self._get_engine("/speakers"))
                flat = [{"id": st["id"], "label": "%s / %s" % (s["name"], st["name"])}
                        for s in spk for st in s["styles"]]
                return self._json({"lines": lines, "voice": cfg, "speakers": flat})
            if u.path == "/api/phrases":
                i = int(q["index"][0])
                over_cfg = json.loads(q.get("cfg", ["{}"])[0] or "{}")
                row = [r for r in self._rows() if r["index"] == i][0]
                cfg = tts.load_voice(self.ep_dir)
                cfg.setdefault("lines", {})[str(i)] = over_cfg
                st, over = tts.settings_for(cfg, row)
                query, _, _ = tts.build_query(row["read"], st, row["ruby_accents"], over)
                return self._json({"phrases": [
                    {"moras": [m["text"] for m in ap["moras"]], "accent": ap["accent"]}
                    for ap in query["accent_phrases"]]})
        except Exception as e:
            return self._send(500, str(e), "text/plain; charset=utf-8")
        self._send(404, "not found", "text/plain; charset=utf-8")

    def _get_engine(self, path):
        import urllib.request
        with urllib.request.urlopen(tts.ENGINE + path, timeout=30) as r:
            return r.read().decode("utf-8")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        try:
            if u.path == "/api/save":
                p = tts.save_voice(self.ep_dir, body)
                return self._json({"saved": p})
            if u.path == "/api/preview":
                i = body["index"]
                row = [r for r in self._rows() if r["index"] == i][0]
                cfg = tts.load_voice(self.ep_dir)
                cfg.setdefault("lines", {})[str(i)] = body.get("cfg", {})
                st, over = tts.settings_for(cfg, row)
                query, _, _ = tts.build_query(row["read"], st, row["ruby_accents"], over)
                wav = tts.post("/synthesis", {"speaker": st["speaker"]}, query)
                return self._send(200, wav, "audio/wav")
            if u.path == "/api/resynth":
                tl = tts.run(self.ep_dir, quiet=True)
                total = sum(v["end"] for v in
                            [max([r for r in tl if r["episode"] == e], key=lambda r: r["end"])
                             for e in sorted({r["episode"] for r in tl})])
                dur = {r["index"]: r["duration"] for r in tl}
                lines = [{"index": r["index"], "episode": r["episode"], "cut": r["cut"],
                          "speaker": r["speaker"], "text": r["text"], "read": r["read"],
                          "duration": dur.get(r["index"], 0.0)} for r in self._rows()]
                return self._json({"lines": lines,
                                   "total": "%d分%02d秒" % (int(total) // 60, int(total) % 60)})
        except Exception as e:
            return self._send(500, str(e), "text/plain; charset=utf-8")
        self._send(404, "not found", "text/plain; charset=utf-8")


def main():
    Handler.ep_dir = sys.argv[1] if len(sys.argv) > 1 else EP_DIR
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("http://127.0.0.1:%d  (Ctrl+C で終了)" % PORT)
    print("対象: %s" % Handler.ep_dir)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
