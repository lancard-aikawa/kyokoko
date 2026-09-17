# -*- coding: utf-8 -*-
"""今日はここにの調整用ブラウザUI。

  python tools/editor.py [ep_dir]     http://127.0.0.1:8765 を開く

タブは 3 つ。

  企画        会話で決めたことを直す。町・回の題・全体の調子・配役（話者と口調）・
              各話の題と BGM・間の取り方。episode.json に保存する。
  語り        行ごとの話者・抑揚・速度・アクセントを直し、その場で聴く。
              voice.json に保存する。
  シーンと素材 ショットの中身を確認する。構図のプレビュー、使っている地図レイヤ、
              写真とライセンス、テロップ、その間の台詞。表示義務のある素材には印が付く。

script.md（文章とふりがな）と shots.py（構図）はここでは触らない。確認だけ。
"""
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip  # noqa: E402
import tiles  # noqa: E402
import tts  # noqa: E402


def load_shots(ep_dir, timeline):
    """その回の shots.py を読み込んで、話番号 -> ショット一覧 を返す。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("shots", os.path.join(ep_dir, "shots.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.build(timeline)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(ROOT, "episodes", "001-nagasaki-daikokumachi")
PORT = 8765

HTML = r"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日はここに 調整</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--line:#e2e2dd;--ink:#1c1c1a;--dim:#77776f;--accent:#d94f30}
*{box-sizing:border-box}
body{margin:0;font:14px/1.6 "BIZ UDPGothic","Yu Gothic UI",system-ui,sans-serif;
     background:var(--bg);color:var(--ink);height:100vh;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:6px;padding:8px 16px;background:var(--panel);
       border-bottom:1px solid var(--line);flex:0 0 auto}
header h1{font-size:15px;margin:0 14px 0 0;font-weight:700}
.tab{padding:7px 18px;border:1px solid var(--line);border-radius:7px;background:#fff;
     cursor:pointer;font:inherit}
.tab.on{background:var(--ink);color:#fff;border-color:var(--ink)}
header .sp{flex:1}
button{font:inherit;padding:6px 14px;border:1px solid var(--line);background:#fff;
       border-radius:6px;cursor:pointer}
button:hover{background:#f0f0ec}
button.primary{background:var(--ink);color:#fff;border-color:var(--ink)}
button.primary:hover{background:#000}
#msg{color:var(--dim);font-size:13px}
main{flex:1;min-height:0;overflow:auto}
.pane{display:none;height:100%}
.pane.on{display:block}
#plan{padding:22px 28px;max-width:1080px}
h2{font-size:13px;color:var(--dim);margin:26px 0 10px;font-weight:700;letter-spacing:.04em}
h2:first-child{margin-top:0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:16px 18px;
      margin-bottom:12px}
.grid{display:grid;grid-template-columns:96px 1fr;gap:9px 14px;align-items:center}
.grid.w{grid-template-columns:96px 1fr 96px 1fr}
label{color:var(--dim);font-size:13px}
input[type=text],input[type=number],textarea,select{font:inherit;padding:6px 9px;
  border:1px solid var(--line);border-radius:6px;background:#fff;width:100%}
textarea{resize:vertical;min-height:62px;line-height:1.7}
.cast{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.role{font-weight:700;font-size:15px;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.swatch{width:15px;height:15px;border-radius:4px;border:1px solid #0002}
.sliders{display:grid;grid-template-columns:62px 1fr 54px;gap:8px 10px;align-items:center;
         margin-top:10px}
.val{font-variant-numeric:tabular-nums;text-align:right;font-size:13px}
input[type=range]{width:100%}
table.ch{width:100%;border-collapse:collapse}
table.ch td,table.ch th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
table.ch th{font-size:12px;color:var(--dim);font-weight:700}
table.ch td.n{width:80px;color:var(--dim)}
.hint{color:var(--dim);font-size:12px;margin-top:8px;line-height:1.7}
/* シーンと素材タブ / 語りタブ */
#scene{display:flex;height:100%}
#scenelist{width:40%;overflow:auto;border-right:1px solid var(--line)}
#scenedetail{flex:1;overflow:auto;padding:18px 22px}
img.prev{width:100%;max-width:820px;border:1px solid var(--line);border-radius:8px;
         background:#eee;display:block}
#talk{display:flex;height:100%}
#list{width:46%;overflow:auto;border-right:1px solid var(--line)}
#detail{flex:1;overflow:auto;padding:18px 22px}
table.ln{width:100%;border-collapse:collapse}
tr.ep td{background:#edece7;font-weight:700;font-size:12px;color:var(--dim);
         padding:5px 12px;position:sticky;top:0}
tbody tr.row{cursor:pointer;border-bottom:1px solid var(--line)}
tbody tr.row:hover{background:#efeeea}
tbody tr.row.sel{background:#e4eef6}
table.ln td{padding:6px 10px;vertical-align:top}
td.n2{width:42px;color:var(--dim);text-align:right;font-variant-numeric:tabular-nums}
td.who{width:74px;font-weight:700;white-space:nowrap}
td.dur{width:52px;color:var(--dim);text-align:right;font-variant-numeric:tabular-nums}
td.txt{font-size:13px;max-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tag{display:inline-block;margin-left:6px;padding:0 6px;border-radius:99px;
     background:var(--accent);color:#fff;font-size:11px;vertical-align:1px}
.sub{font-size:17px;line-height:1.7;background:var(--panel);border:1px solid var(--line);
     border-radius:8px;padding:12px 14px}
.sub .rd{display:block;margin-top:6px;font-size:13px;color:var(--dim)}
.phr{display:flex;flex-wrap:wrap;gap:10px}
.ph{border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:6px 8px}
.ph .ms{display:flex;gap:2px}
.mora{min-width:26px;text-align:center;padding:3px 4px;border-radius:5px;cursor:pointer;
      font-size:15px}
.mora:hover{background:#eee}
.mora.hi{background:var(--accent);color:#fff}
.ph .cap{font-size:11px;color:var(--dim);text-align:center;margin-top:3px}
.row2{display:flex;gap:8px;align-items:center;margin-top:10px}
</style></head><body>
<header>
  <h1>今日はここに</h1>
  <button class="tab on" data-p="plan">企画</button>
  <button class="tab" data-p="talk">語り</button>
  <button class="tab" data-p="scene">シーンと素材</button>
  <span id="msg"></span><span class="sp"></span>
  <button id="save" class="primary">保存</button>
</header>
<main>
  <div class="pane on" id="plan"></div>
  <div class="pane" id="scene"><div id="scenelist"></div><div id="scenedetail"></div></div>
  <div class="pane" id="talk">
    <div id="list"></div>
    <div id="detail"><p class="hint">左の一覧から行を選んでください。</p></div>
  </div>
</main>
<script>
let S=null, P=null, cur=null, audio=new Audio(), tab='plan';
const api=(p,o)=>fetch(p,o).then(r=>r.ok?r.json():r.text().then(t=>{throw new Error(t)}));
const msg=t=>document.getElementById('msg').textContent=t;
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const hex=c=>'#'+(c||[0,0,0]).map(v=>v.toString(16).padStart(2,'0')).join('');

document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{
  tab=b.dataset.p;
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));
  document.querySelectorAll('.pane').forEach(x=>x.classList.toggle('on',x.id===tab));
  if(tab==='scene') renderScenes();
});

/* ===================== 企画 ===================== */
function renderPlan(){
  const t=P.town||{}, tm=P.timing||{}, bg=P.bgm||{};
  const opts=w=>S.speakers.map(s=>
    `<option value="${s.id}"${s.id===P.cast[w].speaker?' selected':''}>${esc(s.label)}</option>`).join('');
  const sl=(w,k,lb,mn,mx,st)=>{
    const v=P.cast[w][k];
    return `<label>${lb}</label>
      <input type="range" data-c="${w}" data-k="${k}" min="${mn}" max="${mx}" step="${st}" value="${v}">
      <span class="val" id="v_${w}_${k}">${(+v).toFixed(2)}</span>`;
  };
  const cast=Object.entries(P.cast).map(([w,c])=>`
    <div class="card">
      <div class="role"><span class="swatch" style="background:${hex(c.color)}"></span>
        ${esc(c.role)}　<span style="color:var(--dim);font-weight:400">${esc(w)}</span></div>
      <div class="grid">
        <label>話者</label><select data-c="${w}" data-k="speaker">${opts(w)}</select>
        <label>口調</label><textarea data-c="${w}" data-k="tone">${esc(c.tone)}</textarea>
        <label>立ち絵の側</label>
        <select data-c="${w}" data-k="side">
          <option value="left"${c.side==='left'?' selected':''}>左</option>
          <option value="right"${c.side==='right'?' selected':''}>右</option>
        </select>
      </div>
      <div class="sliders">
        ${sl(w,'intonationScale','抑揚',0,2,0.05)}
        ${sl(w,'speedScale','速度',0.5,1.6,0.01)}
        ${sl(w,'pitchScale','高さ',-0.15,0.15,0.01)}
      </div>
    </div>`).join('');

  const ch=P.chapters.map((c,i)=>`<tr>
      <td class="n">${esc(c.key)}</td>
      <td><input type="text" data-ch="${i}" data-k="title" value="${esc(c.title)}"></td>
      <td style="width:34%"><input type="text" data-ch="${i}" data-k="bgm"
          value="${esc(c.bgm)}" placeholder="（未設定）"></td>
    </tr>`).join('');

  document.getElementById('plan').innerHTML=`
    <h2>どの町を</h2>
    <div class="card"><div class="grid w">
      <label>町名</label><input type="text" data-t="name" value="${esc(t.name)}">
      <label>〒</label><input type="text" data-t="postal" value="${esc(t.postal)}">
      <label>中心 緯度</label><input type="number" step="0.00001" data-t="lat" value="${(t.center||[])[0]}">
      <label>経度</label><input type="number" step="0.00001" data-t="lon" value="${(t.center||[])[1]}">
      <label>メモ</label><input type="text" data-t="note" value="${esc(t.note)}">
      <label>回の題</label><input type="text" data-p2="title" value="${esc(P.title)}">
    </div></div>

    <h2>全体の調子</h2>
    <div class="card"><textarea data-p2="mood" style="min-height:82px">${esc(P.mood)}</textarea>
      <div class="hint">シナリオを書くときの指針。ここを変えても既存の台詞は変わらないが、
        次に書き足すときの拠りどころになる。</div></div>

    <h2>誰が</h2>
    <div class="cast">${cast}</div>

    <h2>各話の題と BGM</h2>
    <div class="card"><table class="ch">
      <tr><th>章</th><th>題</th><th>BGM</th></tr>${ch}</table>
      <div class="hint">${esc(bg.policy||'')}</div></div>

    <h2>間の取り方（秒）</h2>
    <div class="card"><div class="grid w">
      <label>頭の余白</label><input type="number" step="0.05" data-tm="lead_in" value="${tm.lead_in}">
      <label>尻の余白</label><input type="number" step="0.05" data-tm="tail" value="${tm.tail}">
      <label>同じ話者</label><input type="number" step="0.05" data-tm="gap_same" value="${tm.gap_same}">
      <label>話者交代</label><input type="number" step="0.05" data-tm="gap_switch" value="${tm.gap_switch}">
      <label>カット跨ぎ</label><input type="number" step="0.05" data-tm="gap_cut" value="${tm.gap_cut}">
      <label>BGM 音量</label><input type="number" step="0.01" data-bg="volume" value="${bg.volume}">
    </div>
    <div class="hint">間を変えると全体の尺が変わる。保存したあと
      <code>python tools/tts.py</code> で組み直すと反映される。</div></div>`;

  document.querySelectorAll('#plan [data-c]').forEach(el=>{
    const h=e=>{
      const w=el.dataset.c, k=el.dataset.k;
      let v=el.value; if(el.type==='range'||k==='speaker') v=+v;
      P.cast[w][k]=v;
      const o=document.getElementById('v_'+w+'_'+k); if(o) o.textContent=(+v).toFixed(2);
      dirty();
    };
    el.oninput=h; el.onchange=h;
  });
  document.querySelectorAll('#plan [data-t]').forEach(el=>el.oninput=()=>{
    const k=el.dataset.t;
    if(k==='lat') P.town.center[0]=+el.value;
    else if(k==='lon') P.town.center[1]=+el.value;
    else P.town[k]=el.value;
    dirty();
  });
  document.querySelectorAll('#plan [data-p2]').forEach(el=>el.oninput=()=>{
    P[el.dataset.p2]=el.value; dirty(); });
  document.querySelectorAll('#plan [data-ch]').forEach(el=>el.oninput=()=>{
    const c=P.chapters[+el.dataset.ch]; const k=el.dataset.k;
    c[k]= (k==='bgm' && !el.value) ? null : el.value; dirty(); });
  document.querySelectorAll('#plan [data-tm]').forEach(el=>el.oninput=()=>{
    P.timing[el.dataset.tm]=+el.value; dirty(); });
  document.querySelectorAll('#plan [data-bg]').forEach(el=>el.oninput=()=>{
    P.bgm[el.dataset.bg]=+el.value; dirty(); });
}
let touched=false;
function dirty(){ touched=true; msg('未保存の変更があります'); }

/* ================== シーンと素材 ================== */
let SC=null, scur=null;
const isFree=l=>/CC0|Public domain/i.test(l||'');
async function renderScenes(){
  if(!SC) SC=await api('/api/scenes');
  const nm={0:'アバン',99:'エンディング'};
  let ep=null,h='<table class="ln"><tbody>';
  SC.shots.forEach((s,i)=>{
    if(s.ep!==ep){ep=s.ep;h+='<tr class="ep"><td colspan="4">'+(nm[ep]||('第'+ep+'話'))+'</td></tr>';}
    const bad=s.photo && !isFree(s.photo.license);
    h+='<tr class="row" data-s="'+i+'"><td class="n2">'+(s.i+1)+'</td>'
      +'<td class="who" style="color:'+(s.kind==='写真'?'#b06a1a':'#2f7fbf')+'">'+s.kind+'</td>'
      +'<td class="txt">'+esc((s.lines[0]||{}).text||'（台詞なし）')
      +(s.title?'<span class="tag">題</span>':'')
      +(s.credits?'<span class="tag">出典</span>':'')
      +(bad?'<span class="tag" style="background:#8a6d1f">表示義務</span>':'')+'</td>'
      +'<td class="dur">'+(s.t1-s.t0).toFixed(1)+'</td></tr>';
  });
  document.getElementById('scenelist').innerHTML=h+'</tbody></table>';
  document.querySelectorAll('#scenelist tr.row').forEach(tr=>
    tr.onclick=()=>selectScene(+tr.dataset.s));
  selectScene(scur==null?0:scur);
}
function selectScene(i){
  scur=i; const s=SC.shots[i];
  document.querySelectorAll('#scenelist tr.row').forEach(tr=>
    tr.classList.toggle('sel',+tr.dataset.s===i));
  const nm={0:'アバン',99:'エンディング'};
  let mat='';
  if(s.photo){
    const free=isFree(s.photo.license);
    mat='<h2>素材</h2><div class="card"><div class="grid">'
      +'<label>写真</label><div>'+esc(s.photo.key)+'</div>'
      +'<label>作者</label><div>'+esc(s.photo.author||'不明')+'</div>'
      +'<label>ライセンス</label><div><b style="color:'+(free?'#2a7a35':'#8a6d1f')+'">'
      +esc(s.photo.license)+'</b> '+(free?'（表示義務なし）':'（画面に表示が必要）')+'</div>'
      +'<label>出典</label><div><a href="'+esc(s.photo.page)+'" target="_blank">Commons</a></div>'
      +'</div></div>';
  }else{
    mat='<h2>地図</h2><div class="card"><div class="grid">'
      +'<label>ズーム</label><div>z'+s.zoom+'</div>'
      +'<label>レイヤ</label><div>'+s.layers.map(l=>esc(l.name)
        +' <span style="color:var(--dim)">('+esc(l.id)+' 濃度 '+l.alpha.join('→')+')</span>'
        ).join('<br>')+'</div>'
      +(s.labels.length?'<label>ラベル</label><div>'+s.labels.map(esc).join(' / ')+'</div>':'')
      +(s.paths?'<label>経路</label><div>'+s.paths+'本</div>':'')
      +'</div></div>';
  }
  const head=(nm[s.ep]||('第'+s.ep+'話'))+' ショット'+(s.i+1)+' — '
    +s.t0.toFixed(1)+'〜'+s.t1.toFixed(1)+'秒（'+(s.t1-s.t0).toFixed(1)+'秒）';
  document.getElementById('scenedetail').innerHTML='<h2>'+head+'</h2>'
    +'<img class="prev" src="/api/shot.png?ep='+s.ep+'&i='+s.i+'" alt="描画中…">'
    +mat
    +(s.notes.length?'<h2>テロップ</h2><div class="card">'+s.notes.map(esc).join('<br>')+'</div>':'')
    +'<h2>この間の台詞</h2><div class="card">'
    +(s.lines.length?s.lines.map(l=>'<div><b style="color:'
        +hex((P.cast[l.speaker]||{}).color)+'">'+esc(l.speaker)+'</b>　'+esc(l.text)+'</div>').join('')
      :'<span class="hint">なし</span>')+'</div>';
}

/* ===================== 語り ===================== */
function lineCfg(i){ return (S.voice.lines[String(i)] ||= {}); }
function hasOv(i){ const c=S.voice.lines[String(i)]; return c && Object.keys(c).length>0; }
function setting(i,k){
  const L=S.lines.find(x=>x.index===i);
  const d=S.voice.defaults[L.speaker]||{}, c=S.voice.lines[String(i)]||{};
  return c[k]!==undefined?c[k]:d[k];
}
function renderList(){
  let h='<table class="ln"><tbody>', ep=null;
  const nm={0:'アバン',99:'エンディング'};
  for(const L of S.lines){
    if(L.episode!==ep){ ep=L.episode;
      h+=`<tr class="ep"><td colspan="4">${nm[ep]||('第'+ep+'話')}</td></tr>`; }
    h+=`<tr class="row" data-i="${L.index}"><td class="n2">${L.index}</td>`+
       `<td class="who" style="color:${hex((P.cast[L.speaker]||{}).color)}">${esc(L.speaker)}</td>`+
       `<td class="txt" title="${esc(L.text)}">${esc(L.text)}${hasOv(L.index)?'<span class="tag">調整</span>':''}</td>`+
       `<td class="dur">${L.duration.toFixed(1)}</td></tr>`;
  }
  document.getElementById('list').innerHTML=h+'</tbody></table>';
  document.querySelectorAll('tr.row').forEach(tr=>tr.onclick=()=>select(+tr.dataset.i));
  if(cur) document.querySelectorAll('tr.row').forEach(tr=>
    tr.classList.toggle('sel',+tr.dataset.i===cur));
}
async function select(i){
  cur=i; renderList();
  const L=S.lines.find(x=>x.index===i);
  const opts=S.speakers.map(s=>
    `<option value="${s.id}"${s.id===setting(i,'speaker')?' selected':''}>${esc(s.label)}</option>`).join('');
  const sl=(k,lb,mn,mx,st)=>{const v=setting(i,k);
    return `<label>${lb}</label><input type="range" id="r_${k}" min="${mn}" max="${mx}" step="${st}" value="${v}">
            <span class="val" id="v_${k}">${(+v).toFixed(2)}</span>`;};
  document.getElementById('detail').innerHTML=`
    <h2>台詞</h2>
    <div class="sub">${esc(L.text)}<span class="rd">読み: ${esc(L.read)}</span></div>
    <h2>話者</h2><select id="spk">${opts}</select>
    <h2>声のつまみ</h2>
    <div class="sliders">${sl('intonationScale','抑揚',0,2,0.05)}
      ${sl('speedScale','速度',0.5,1.6,0.01)}${sl('pitchScale','高さ',-0.15,0.15,0.01)}</div>
    <h2>アクセント句 — モーラを押すと核がそこに移る。核をもう一度押すと平板</h2>
    <div class="phr" id="phr">読み込み中…</div>
    <div class="row2"><button id="play" class="primary">▶ 試聴</button>
      <button id="reset">この行を既定に戻す</button>
      <span class="hint" id="pstat"></span></div>`;
  document.getElementById('spk').onchange=e=>{lineCfg(i).speaker=+e.target.value;dirty();renderList();loadPhrases();};
  ['intonationScale','speedScale','pitchScale'].forEach(k=>{
    document.getElementById('r_'+k).oninput=e=>{
      document.getElementById('v_'+k).textContent=(+e.target.value).toFixed(2);
      lineCfg(i)[k]=+e.target.value; dirty(); renderList(); };
  });
  document.getElementById('play').onclick=preview;
  document.getElementById('reset').onclick=()=>{
    delete S.voice.lines[String(i)]; dirty(); select(i); };
  loadPhrases();
}
async function loadPhrases(){
  const i=cur;
  const r=await api('/api/phrases?index='+i+'&cfg='+encodeURIComponent(JSON.stringify(S.voice.lines[String(i)]||{})));
  if(cur!==i) return;
  const box=document.getElementById('phr');
  box.innerHTML=r.phrases.map((p,pi)=>`<div class="ph"><div class="ms">`+
    p.moras.map((m,mi)=>`<span class="mora${p.accent===mi+1?' hi':''}" data-p="${pi}" data-m="${mi}">${m}</span>`).join('')+
    `</div><div class="cap">核 ${p.accent}</div></div>`).join('');
  box.querySelectorAll('.mora').forEach(el=>el.onclick=()=>{
    const pi=+el.dataset.p, mi=+el.dataset.m, p=r.phrases[pi];
    const c=lineCfg(i); c.accents=(c.accents||[]).filter(a=>a.i!==pi);
    c.accents.push({i:pi, moras:p.moras.join(''), accent:p.accent===mi+1?0:mi+1});
    dirty(); renderList(); loadPhrases();
  });
}
async function preview(){
  const i=cur, st=document.getElementById('pstat'); st.textContent='合成中…';
  const res=await fetch('/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({index:i, cfg:S.voice.lines[String(i)]||{}})});
  if(!res.ok){ st.textContent='失敗: '+await res.text(); return; }
  audio.src=URL.createObjectURL(await res.blob()); audio.play(); st.textContent='';
}

document.getElementById('save').onclick=async()=>{
  await api('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(P)});
  await api('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(S.voice)});
  touched=false; msg('episode.json と voice.json に保存しました');
};
window.onbeforeunload=()=>touched?'未保存の変更があります':null;

Promise.all([api('/api/state'), api('/api/plan')]).then(([s,p])=>{
  S=s; P=p; renderPlan(); renderList();
});
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

    def _lines(self):
        dur = {r["index"]: r["duration"] for r in self._timeline()}
        return [{"index": r["index"], "episode": r["episode"], "cut": r["cut"],
                 "speaker": r["speaker"], "text": r["text"], "read": r["read"],
                 "duration": dur.get(r["index"], 0.0)} for r in self._rows()]

    def _engine(self, path):
        with urllib.request.urlopen(tts.ENGINE + path, timeout=30) as r:
            return r.read().decode("utf-8")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/":
                return self._send(200, HTML, "text/html; charset=utf-8")
            if u.path == "/favicon.ico":
                return self._send(200, b"", "image/x-icon")
            if u.path == "/api/plan":
                return self._json(tts.load_plan(self.ep_dir))
            if u.path == "/api/state":
                spk = json.loads(self._engine("/speakers"))
                flat = [{"id": st["id"], "label": "%s / %s" % (s["name"], st["name"])}
                        for s in spk for st in s["styles"]]
                return self._json({"lines": self._lines(),
                                   "voice": tts.load_voice(self.ep_dir), "speakers": flat})
            if u.path == "/api/scenes":
                return self._json(self._scenes())
            if u.path == "/api/shot.png":
                return self._shot_png(int(q["ep"][0]), int(q["i"][0]))
            if u.path == "/api/phrases":
                i = int(q["index"][0])
                row = [r for r in self._rows() if r["index"] == i][0]
                cfg = tts.load_voice(self.ep_dir)
                cfg.setdefault("lines", {})[str(i)] = json.loads(q.get("cfg", ["{}"])[0] or "{}")
                st, over = tts.settings_for(cfg, row)
                query, _, _ = tts.build_query(row["read"], st, row["ruby_accents"], over)
                return self._json({"phrases": [
                    {"moras": [m["text"] for m in ap["moras"]], "accent": ap["accent"]}
                    for ap in query["accent_phrases"]]})
        except Exception as e:
            return self._send(500, str(e), "text/plain; charset=utf-8")
        self._send(404, "not found", "text/plain; charset=utf-8")

    def _photos(self):
        p = os.path.join(self.ep_dir, "photos.json")
        return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}

    def _scenes(self):
        tl = self._timeline()
        shots = load_shots(self.ep_dir, tl)
        man = self._photos()
        out = []
        for ep in sorted(shots):
            rows = [r for r in tl if r["episode"] == ep]
            for i, sh in enumerate(shots[ep]):
                t0, t1 = sh["t0"], sh["t1"]
                lines = [{"speaker": r["speaker"], "text": r["text"]}
                         for r in rows if r["start"] < t1 and r["end"] > t0]
                item = {"ep": ep, "i": i, "t0": t0, "t1": t1,
                        "kind": "写真" if sh.get("type") == "photo" else "地図",
                        "lines": lines,
                        "notes": [x["text"] for x in sh.get("notes", [])],
                        "labels": [x["text"] for x in sh.get("labels", [])],
                        "title": (sh.get("title") or {}).get("main"),
                        "credits": bool(sh.get("credits")),
                        "paths": len(sh.get("paths", []))}
                if sh.get("type") == "photo":
                    m = man.get(sh["photo"], {})
                    item["photo"] = {"key": sh["photo"], "license": m.get("license"),
                                     "author": m.get("author"), "page": m.get("page")}
                else:
                    item["zoom"] = sh.get("zoom")
                    item["layers"] = [
                        {"id": l["id"],
                         "name": (tiles.LAYERS.get(l["id"]) or ("", (), l["id"]))[2],
                         "alpha": [round(a[1], 2) for a in (l.get("alpha") or [[0, 1.0]])]}
                        for l in sh.get("layers", [])]
                out.append(item)
        return {"shots": out, "photos": man}

    def _shot_png(self, ep, i):
        """そのショットの真ん中を 1 枚だけ描く。重いので描いたものは残す。"""
        import subprocess
        d = os.path.join(self.ep_dir, "out", "shotcheck")
        os.makedirs(d, exist_ok=True)
        png = os.path.join(d, "scene_ep%d_%d.png" % (ep, i))
        if not os.path.exists(png):
            tl = self._timeline()
            sh = load_shots(self.ep_dir, tl)[ep][i]
            mid = (sh["t0"] + sh["t1"]) / 2
            one = dict(sh)
            one["t0"], one["t1"] = mid, mid + 4.0 / 30
            rows = [r for r in tl if r["episode"] == ep]
            mp4 = png.replace(".png", ".mp4")
            clip.load_plan(self.ep_dir)
            if one.get("type") == "photo":
                clip.render_photo_shot(one, rows, clip.load_photos(self.ep_dir), mp4,
                                       size=(960, 540))
            else:
                clip.render_shot(one, rows, mp4, size=(960, 540))
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", mp4, "-frames:v", "1", png],
                           check=True)
            os.remove(mp4)
        with open(png, "rb") as f:
            return self._send(200, f.read(), "image/png")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        try:
            if u.path == "/api/plan":
                p = os.path.join(self.ep_dir, "episode.json")
                with io.open(p, "w", encoding="utf-8") as f:
                    json.dump(body, f, ensure_ascii=False, indent=2)
                return self._json({"saved": p})
            if u.path == "/api/save":
                # 既定は episode.json 側が持つので、voice.json には行ごとの上書きだけ書く
                return self._json({"saved": tts.save_voice(
                    self.ep_dir, {"lines": body.get("lines", {})})})
            if u.path == "/api/preview":
                i = body["index"]
                row = [r for r in self._rows() if r["index"] == i][0]
                cfg = tts.load_voice(self.ep_dir)
                cfg.setdefault("lines", {})[str(i)] = body.get("cfg", {})
                st, over = tts.settings_for(cfg, row)
                query, _, _ = tts.build_query(row["read"], st, row["ruby_accents"], over)
                wav = tts.post("/synthesis", {"speaker": st["speaker"]}, query)
                return self._send(200, wav, "audio/wav")
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
