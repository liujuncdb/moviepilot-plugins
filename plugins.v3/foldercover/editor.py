# -*- coding: utf-8 -*-
"""插件详情页的预览 / 批量制作界面。

设计上分成两块：
- 左栏：扫描范围内的目录树，可多选、可搜索；点目录名切换右侧预览对象；
- 右栏：一次性把当前画幅的所有风格都渲染出来做对比，点图即选，再写入。

所有路由都是匿名可访问的，页面里不需要任何 token。
"""
import base64
import io
from collections import OrderedDict
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Response
from starlette.responses import HTMLResponse

PAGE_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>文件夹封面工作室</title>
<style>
:root{
  --bg:#0b0e14;--panel:#12161f;--panel2:#161b26;--line:#232a38;--ink:#e8edf7;--dim:#8b96ab;
  --accent:#7aa2ff;--ok:#48d18a;--warn:#e6b45a;--bad:#f06a6a;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:radial-gradient(1200px 700px at 10% -10%,#17233c 0%,transparent 55%),var(--bg);color:var(--ink);
     font:14px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden;
     display:flex;flex-direction:column;height:100%}
header{display:flex;flex-wrap:wrap;align-items:center;gap:14px;padding:12px 16px;border-bottom:1px solid var(--line);
        background:rgba(12,16,24,.72);backdrop-filter:blur(10px);position:sticky;top:0;z-index:5}
h1{font-size:15px;font-weight:650;margin:0;letter-spacing:.3px}
.sub{color:var(--dim);font-size:12px}
.grow{flex:1}
button{font:inherit;color:var(--ink);background:#1b2230;border:1px solid var(--line);border-radius:10px;
       padding:7px 12px;cursor:pointer;transition:.15s}
button:hover{border-color:#3a4a68;background:#212a3b}
button.primary{background:linear-gradient(180deg,#3f6fe8,#2f57c0);border-color:#4a7cf0}
button.primary:hover{filter:brightness(1.08)}
button.ghost{background:transparent}
button:disabled{opacity:.45;cursor:not-allowed}
main{display:grid;grid-template-columns:320px 1fr;flex:1;min-height:0;height:auto}
aside{border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0;background:var(--panel)}
.pane-head{padding:10px 12px;display:flex;gap:8px;align-items:center;border-bottom:1px solid var(--line)}
input[type=text],input[type=search],textarea,select{width:100%;background:#0f141d;color:var(--ink);
  border:1px solid var(--line);border-radius:8px;padding:7px 9px;font:inherit;outline:none}
input:focus,textarea:focus{border-color:#3f5c8f}
.tree{overflow:auto;flex:1;padding:6px 4px 40px}
.node{display:flex;align-items:center;gap:6px;padding:4px 6px;border-radius:8px;cursor:pointer;user-select:none}
.node:hover{background:#182031}
.node.active{background:#1d2942;box-shadow:inset 0 0 0 1px #35507f}
.node .caret{width:16px;text-align:center;color:var(--dim);font-size:11px}
.node .caret.empty{opacity:0}
.node input[type=checkbox]{accent-color:#5b8bff;width:14px;height:14px;margin:0}
.node .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{font-size:10px;color:var(--dim);background:#0e131c;border:1px solid var(--line);
  border-radius:999px;padding:0 6px;line-height:16px}
.badge.ok{color:#9fe8c4;border-color:#245c42}
.badge.img{color:#a9c1ff;border-color:#2c3f66}
.right{display:flex;flex-direction:column;min-height:0;min-width:0}
.bar{display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--line);background:var(--panel2)}
.bar .path{color:var(--dim);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:52vw}
.seg{display:inline-flex;background:#0f141d;border:1px solid var(--line);border-radius:10px;padding:2px}
.seg button{border:0;background:transparent;padding:5px 12px;border-radius:8px;color:var(--dim)}
.seg button.on{background:#26324a;color:#fff}
.content{overflow:auto;padding:16px 18px 40px;flex:1}
.status{color:var(--dim);font-size:12px}
.group{margin-bottom:22px}
.group h3{margin:0 0 4px;font-size:12px;letter-spacing:1.4px;color:#9fb0cc;font-weight:600;text-transform:uppercase}
.group .hint{color:var(--dim);font-size:11px;margin-bottom:10px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));align-items:start}
.card{position:relative;border-radius:12px;overflow:hidden;border:1px solid var(--line);background:#0f141d;
  cursor:pointer;transition:.15s}
.card:hover{transform:translateY(-1px);border-color:#3c527d}
.card.sel{border-color:#6f9bff;box-shadow:0 0 0 2px rgba(111,155,255,.25)}
.card img{display:block;width:100%;height:auto;background:#0a0d13;object-fit:contain}
.card .cap{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:7px 9px}
.card .cap b{font-size:12px;font-weight:600}
.card .tag{font-size:10px;color:var(--dim)}
.card .rec{position:absolute;top:8px;right:8px;font-size:10px;padding:1px 7px;border-radius:999px;
  background:rgba(72,209,138,.16);color:#9fe8c4;border:1px solid #2c6b4f}
.skel{width:100%;aspect-ratio:2/3;background:linear-gradient(110deg,#0f141d 8%,#1a2130 18%,#0f141d 33%);
  background-size:200% 100%;animation:sh 1.2s linear infinite}
@keyframes sh{to{background-position-x:-200%}}
.tools{border-top:1px solid var(--line);background:var(--panel2);padding:10px 16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.field{display:flex;flex-direction:column;gap:4px;min-width:160px;flex:1}
.field label{font-size:11px;color:var(--dim)}
.toolsbox{background:var(--panel2);border-top:1px solid var(--line)}
.toolsbox summary{display:none}
.toolsbox .tools{border-top:0}
.check{display:flex;align-items:center;gap:8px;font-size:12px;color:#c9d6ea;padding:2px 2px}
.check input{width:15px;height:15px;accent-color:#7aa2ff}
body,main,.right,.content,.bar,.tools,.toolsbox{max-width:100%;overflow-x:hidden}
details.adv{border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:14px 0 0;background:#0f141d}
details.adv summary{cursor:pointer;color:#a9b8d4;font-size:12px}
.adv .rows{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-top:10px}
.toast{position:fixed;right:18px;bottom:18px;background:#1b2230;border:1px solid #2f3b52;border-radius:10px;
  padding:9px 13px;font-size:12px;color:var(--ink);box-shadow:0 8px 30px rgba(0,0,0,.35);opacity:0;transform:translateY(8px);
  transition:.2s;pointer-events:none;z-index:50}
.toast.show{opacity:1;transform:none}
.modal{position:fixed;inset:0;background:rgba(5,8,13,.72);display:none;align-items:center;justify-content:center;z-index:40}
.modal.show{display:flex}
.modal .box{width:min(720px,92vw);max-height:86vh;overflow:auto;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:18px}
.modal h2{margin:0 0 6px;font-size:15px}
.modal .row{display:flex;gap:10px;align-items:center}
ul.report{margin:10px 0 0;padding-left:18px;color:#c8d3e6;font-size:12px;max-height:40vh;overflow:auto}
ul.report li{margin:3px 0}
#btnTree{display:none}
#scrim{position:fixed;inset:0;background:rgba(4,7,12,.6);z-index:30;display:none}
#scrim.show{display:block}
@media (max-width:760px){
  header{gap:8px;padding:8px 10px}
  h1{font-size:14px}
  .sub{display:none}
  header #stat{font-size:11px;margin-left:auto}
  header button{padding:6px 10px;font-size:12px}
  main{display:flex;flex-direction:column}
  aside{position:fixed;top:0;bottom:0;left:0;width:86vw;max-width:360px;z-index:31;padding-top:env(safe-area-inset-top);
        transform:translateX(-103%);transition:transform .22s ease;box-shadow:18px 0 40px rgba(0,0,0,.45)}
  aside.open{transform:none}
  aside .pane-head{padding-top:12px}
  #btnTree{display:inline-flex}
  .right{flex:1;min-height:0}
  .bar{flex-wrap:wrap;gap:8px;padding:8px 10px;padding-bottom:calc(8px + env(safe-area-inset-bottom))}
  .bar .path{display:none}
  #curName{font-size:12px;max-width:56vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .seg{order:-1;width:100%}
  .seg button{flex:1;padding:7px 0}
  #btnApply,#btnBatch{flex:1;padding:9px 8px;font-size:12px}
  .content{padding:10px 10px 24px}
  .group{margin-bottom:16px}
  .group h3{font-size:11px;letter-spacing:1px}
  .grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .card{border-radius:10px}
  .card .cap{padding:6px 7px;gap:4px}
  .card .cap b{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .card .tag{display:none}
  .card .rec{top:6px;right:6px;font-size:9px;padding:0 6px}
  .tools{flex-direction:column;gap:8px;padding:8px 10px 12px}
  .field{min-width:0;width:100%}
  .tools button{width:100%;padding:9px}
  .adv .rows{grid-template-columns:1fr}
  .modal .box{width:94vw;padding:14px}
  .toast{left:12px;right:12px;bottom:12px}
  body,main,.right,.content,.bar,.toolsbox{width:100%;max-width:100vw}
  header{width:100%}
  h1{flex:1 1 100%;margin-bottom:2px}
  .toolsbox summary{display:block;padding:9px 12px;font-size:12px;color:#a9b8d4;cursor:pointer}
  .toolsbox[open] summary{border-bottom:1px solid var(--line)}
  .toolsbox .tools{max-height:38vh;overflow:auto}
}
@media (max-width:760px) and (max-height:620px){
  .content{padding-bottom:12px}
}
</style>
</head>
<body>
<header>
  <h1>文件夹封面工作室</h1>
  <span class="sub">预览 · 选择 · 写入 Emby 文件夹封面</span>
  <span class="grow"></span>
  <span id="stat" class="status">就绪</span>
  <button id="btnRefresh" class="ghost">刷新目录</button>
  <button id="btnAll" class="primary">一键全量制作</button>
</header>

<main>
  <aside id="side">
    <div class="pane-head">
      <input id="q" type="search" placeholder="搜索目录…"/>
      <button id="btnClear" class="ghost" title="清空勾选">清空</button>
    </div>
    <div class="pane-head" style="padding-top:0">
      <label class="status" style="display:flex;gap:6px;align-items:center">
        <input id="ckAll" type="checkbox"/> 全选可见
      </label>
      <span class="grow"></span>
      <span id="ckCount" class="status">已选 0</span>
    </div>
    <div id="tree" class="tree"><div class="status" style="padding:10px">加载目录中…</div></div>
  </aside>

  <section class="right">
    <div class="bar">
      <button id="btnTree" class="ghost" type="button">目录</button>
      <div class="seg">
        <button data-o="portrait" class="on">竖版 2:3</button>
        <button data-o="landscape">横版 16:9</button>
      </div>
      <span id="curName" style="font-weight:600">未选择目录</span>
      <span id="curPath" class="path"></span>
      <span class="grow"></span>
      <button id="btnApply" class="primary" disabled>写入当前目录</button>
      <button id="btnBatch" disabled>制作选中 (0)</button>
    </div>
    <div id="selHint" class="hint" style="padding:2px 0 8px"></div>

    <div id="content" class="content">
      <div class="status" style="padding:30px 0">先在左边选一个目录，这里会同时显示所有风格的效果。</div>
    </div>

    <details id="toolsBox" class="toolsbox" open>
      <summary>文字与标签（默认取文件夹名）</summary>
      <div class="tools">
        <label class="check"><input id="tShow" type="checkbox" checked/> 显示标题</label>
        <div class="field"><label>标题</label><input id="tTitle" type="text" placeholder="默认取文件夹名"/></div>
        <div class="field"><label>副标题</label><input id="tSub" type="text" placeholder="可留空"/></div>
        <div class="field"><label>小标签（年份/地区）</label><input id="tKicker" type="text" placeholder="如 2023 华语"/></div>
        <button id="btnRerender" class="ghost">应用文字并重绘</button>
      </div>
    </details>
  </section>
</main>

<div id="scrim"></div>
<div id="toast" class="toast"></div>
<div id="modal" class="modal">
  <div class="box">
    <h2 id="mTitle">批量制作结果</h2>
    <div id="mBody" class="status"></div>
    <ul id="mList" class="report"></ul>
    <div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">关闭</button></div>
  </div>
</div>

<script>
const QS = new URLSearchParams(location.search);
const MOBILE = ()=>window.matchMedia('(max-width:760px)').matches;
const O = {tree:null, q:'', open:new Set(), checked:new Set(), cur:null, orientation:(QS.get('orientation')==='landscape'?'landscape':'portrait'),
           meta:{}, text:{}, chosen:{portrait_single:null,portrait_multi:null,landscape_single:null,landscape_multi:null}, config:{portrait:{},landscape:{}},
           schema:{}, autoMode:'', running:false, timer:null};

const $ = (id)=>document.getElementById(id);
function toast(msg, ms){const t=$('toast');t.textContent=msg;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'), ms||2600);}
function closeModal(){$('modal').classList.remove('show')}
function openModal(title, body, list){$('mTitle').textContent=title;$('mBody').textContent=body||'';
  const ul=$('mList');ul.innerHTML='';(list||[]).forEach(x=>{const li=document.createElement('li');li.textContent=x;ul.appendChild(li);});
  $('modal').classList.add('show');}

async function api(url, opt){
  const r = await fetch(url, opt||{});
  const ct = r.headers.get('content-type')||'';
  if(ct.includes('application/json')) return await r.json();
  return await r.text();
}
function post(url, body){return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});}

/* ---------------- 目录树 ---------------- */
async function loadTree(){
  $('tree').innerHTML = '<div class="status" style="padding:10px">加载目录中…</div>';
  try{
    const data = await api('/api/v1/plugin/FolderCover/editor_tree');
    O.tree = data.roots || [];
    renderTree();
    if(!O.cur && QS.get('path')){ O.cur=QS.get('path'); renderTree(); loadGallery(); }
    else if(!O.cur){
      const pick = (function walk(list){ for(const n of (list||[])){ if(n.images){ return n; } const hit=walk(n.children); if(hit) return hit; } return null; })(O.tree);
      if(pick){ O.cur=pick.path; renderTree(); loadGallery(); }
    }
  }catch(e){ $('tree').innerHTML = '<div class="status" style="padding:10px">目录加载失败：'+e+'</div>'; }
}
function matchNode(n){
  if(!O.q) return true;
  const q=O.q.toLowerCase();
  if((n.name||'').toLowerCase().includes(q) || (n.path||'').toLowerCase().includes(q)) return true;
  return (n.children||[]).some(matchNode);
}
function renderTree(){
  const host = $('tree'); host.innerHTML='';
  if(!O.tree || !O.tree.length){host.innerHTML='<div class="status" style="padding:10px">没有可扫描的目录，请先在插件设置里填扫描目录。</div>';return}
  const frag = document.createDocumentFragment();
  O.tree.forEach(n=>{ if(matchNode(n)) frag.appendChild(nodeEl(n,0)); });
  host.appendChild(frag);
  updateCounts();
}
function nodeEl(n, depth){
  const wrap=document.createElement('div');
  const row=document.createElement('div');
  row.className='node'+(O.cur===n.path?' active':'');
  row.style.paddingLeft=(6+depth*14)+'px';
  const kids=(n.children||[]).filter(matchNode);
  const caret=document.createElement('span');
  caret.className='caret'+(kids.length?'':' empty');
  caret.textContent = kids.length ? (O.open.has(n.path)?'▾':'▸') : '';
  if(kids.length){ caret.onclick=(e)=>{e.stopPropagation(); O.open.has(n.path)?O.open.delete(n.path):O.open.add(n.path); renderTree(); }; }
  const ck=document.createElement('input'); ck.type='checkbox'; ck.checked=O.checked.has(n.path);
  ck.onclick=(e)=>{e.stopPropagation(); ck.checked?O.checked.add(n.path):O.checked.delete(n.path); updateCounts(); markAll();};
  const nm=document.createElement('span'); nm.className='nm'; nm.textContent=n.name || n.path; nm.title=n.path;
  row.append(caret, ck, nm);
  if(n.has_folder){ const b=document.createElement('span'); b.className='badge ok'; b.textContent='封面'; row.appendChild(b); }
  if(n.images){ const b=document.createElement('span'); b.className='badge img'; b.textContent=n.images+'图'; row.appendChild(b); }
  row.onclick=()=>{ O.cur=n.path; O.chosen={portrait:null,landscape:null}; renderTree(); loadGallery();
    if(window.matchMedia('(max-width:760px)').matches) toggleDrawer(false); };
  wrap.appendChild(row);
  if(kids.length && O.open.has(n.path)){
    const box=document.createElement('div');
    kids.forEach(k=>box.appendChild(nodeEl(k, depth+1)));
    wrap.appendChild(box);
  }
  return wrap;
}
function markAll(){ document.querySelectorAll('.node').forEach(()=>{}); }
function updateCounts(){
  $('ckCount').textContent = '已选 '+O.checked.size;
  const n=O.checked.size;
  $('btnBatch').textContent = '制作选中 ('+n+')';
  $('btnBatch').disabled = n===0 || O.running;
}
function flatVisible(){
  const out=[];
  (function walk(list){ (list||[]).forEach(n=>{ if(matchNode(n)) out.push(n); walk(n.children); }); })(O.tree);
  return out;
}
$('ckAll').onchange=(e)=>{
  if(e.target.checked){ flatVisible().forEach(n=>O.checked.add(n.path)); }
  else { O.checked.clear(); }
  renderTree();
};

/* ---------------- 画廊 ---------------- */
async function loadGallery(){
  if(!O.cur) return;
  const content=$('content');
  $('curName').textContent = O.cur.split('/').filter(Boolean).slice(-1)[0]||O.cur;
  $('curPath').textContent = O.cur;
  content.innerHTML='<div class="status" style="padding:10px 0">正在排布风格…</div>';
  O.text = readText();
  try{
    const meta = await post('/api/v1/plugin/FolderCover/editor_choices',
      {path:O.cur, orientation:O.orientation, text:O.text, configs:O.config});
    if(meta.error){ content.innerHTML='<div class="status" style="padding:24px 0">'+meta.error+'</div>'; return; }
    O.meta[O.orientation]=meta;
    const sel=meta.selected||{};
    ['portrait_single','portrait_multi','landscape_single','landscape_multi'].forEach(k=>{ if(!O.chosen[k] && sel[k]) O.chosen[k]=sel[k]; });
    renderGallery(); refreshSels();
    const token = (O.token = (O.token||0)+1);
    setStat('渲染中 0/'+meta.items.length);
    let done=0;
    await Promise.all(meta.items.map(async (it)=>{
      try{
        const one = await post('/api/v1/plugin/FolderCover/editor_gallery',
          {path:O.cur, orientation:O.orientation, layout:it.value, text:O.text||{}, configs:O.config});
        if(token!==O.token) return;
        done++; setStat('渲染中 '+done+'/'+meta.items.length);
        const card=$('card-'+it.value);
        if(one && one.img && card){
          const img=card.querySelector('img');
          if(img){ img.src=one.img; }
          card.querySelector('.skel')?.remove();
        }
      }catch(e){ done++; setStat('渲染中 '+done+'/'+meta.items.length); }
    }));
    if(token===O.token) setStat('已渲染 '+meta.items.length+' 个风格');
  }catch(e){ content.innerHTML='<div class="status" style="padding:24px 0">渲染失败：'+e+'</div>'; }
}
function setStat(t){ $('stat').textContent=t; }
function slotOf(it){ return O.orientation + (String(it.group||'').indexOf('多图')>=0 ? '_multi' : '_single'); }
function slotName(slot){ return slot.replace('_single',' · 单图').replace('_multi',' · 多图').replace('portrait','竖版').replace('landscape','横版'); }
function refreshSels(){
  const meta=O.meta[O.orientation]; if(!meta) return;
  (meta.items||[]).forEach(it=>{
    const c=$('card-'+it.value); if(!c) return;
    const slot=slotOf(it);
    c.classList.toggle('sel', O.chosen[slot]===it.value);
  });
  const chosenNow = O.chosen[O.orientation+'_single']||O.chosen[O.orientation+'_multi'];
  O.chosen[O.orientation]=chosenNow||null;
  updateApply(); renderSelHint();
}
function renderSelHint(){
  const meta=O.meta[O.orientation]||{};
  const sel=meta.selected||{};
  const pick=(k)=>O.chosen[k]||sel[k]||'默认';
  $('selHint').textContent='一键全量将使用 → 竖版单图：'+pick('portrait_single')
    +' ｜ 竖版多图：'+pick('portrait_multi')
    +' ｜ 横版单图：'+pick('landscape_single')
    +' ｜ 横版多图：'+pick('landscape_multi');
}

function renderGallery(){
  const meta=O.meta[O.orientation]; if(!meta) return;
  const content=$('content'); content.innerHTML='';
  const groups={};
  (meta.items||[]).forEach(it=>{ (groups[it.group]=groups[it.group]||[]).push(it); });
  Object.keys(groups).forEach(g=>{
    const sec=document.createElement('div'); sec.className='group';
    const h=document.createElement('h3'); h.textContent=g; sec.appendChild(h);
    const hint=document.createElement('div'); hint.className='hint';
    const isMulti=g.indexOf('多图')>=0;
    hint.textContent=(isMulti?'多张素材的版式':'单张素材的版式')+((meta.mode===(isMulti?'multi':'single'))?' · 自动判定会选这一组':'');
    sec.appendChild(hint);
    const grid=document.createElement('div'); grid.className='grid';
    (groups[g]||[]).forEach(it=>{
      const card=document.createElement('div');
      card.id='card-'+it.value;
      const _slot=O.orientation+(g.indexOf('多图')>=0?'_multi':'_single');
      card.className='card'+(O.chosen[_slot]===it.value?' sel':'');
      if(it.recommend){const r=document.createElement('span');r.className='rec';r.textContent='推荐';card.appendChild(r);}
      const img=document.createElement('img'); img.alt=it.title; img.style.visibility='hidden';
      img.style.aspectRatio=(O.orientation==='portrait'?'2/3':'16/9');
      img.onload=()=>{img.style.visibility='visible'};
      card.appendChild(img);
      const sk=document.createElement('div'); sk.className='skel'; sk.style.aspectRatio=(O.orientation==='portrait'?'2/3':'16/9'); card.appendChild(sk);
      const cap=document.createElement('div');cap.className='cap';
      const b=document.createElement('b');b.textContent=it.title;cap.appendChild(b);
      const tag=document.createElement('span');tag.className='tag';tag.textContent=it.tag||'';cap.appendChild(tag);
      card.appendChild(cap);
      card.onclick=()=>{ O.chosen[_slot]=it.value; refreshSels(); loadSchema(it.value); };
      grid.appendChild(card);
    });
    sec.appendChild(grid); content.appendChild(sec);
  });
  const adv=document.createElement('details'); adv.className='adv';
  adv.innerHTML='<summary>当前风格的可调参数（高级）</summary><div class="rows" id="advRows"><span class="status">选择风格后加载…</span></div>';
  content.appendChild(adv);
  adv.addEventListener('toggle', ()=>{ if(adv.open) loadSchema(O.chosen[O.orientation]); });
  updateApply();
}
function updateApply(){
  const has = O.chosen[O.orientation+'_single'] || O.chosen[O.orientation+'_multi'];
  $('btnApply').disabled = !O.cur || !has || O.running;
}
let _oneTimer=null, _textTimer=null;
async function refreshOne(layout){
  layout = layout || O.chosen[O.orientation] || (O.meta[O.orientation] && O.meta[O.orientation].auto_layout);
  if(!O.cur || !layout) return;
  try{
    const one=await post('/api/v1/plugin/FolderCover/editor_gallery',
      {path:O.cur, orientation:O.orientation, layout, text:O.text||{}, configs:O.config});
    const card=$('card-'+layout); if(!card) return;
    const img=card.querySelector('img');
    if(one && one.img && img){ img.src=one.img; img.style.visibility='visible'; }
  }catch(e){}
}
function scheduleOne(layout){ clearTimeout(_oneTimer); _oneTimer=setTimeout(()=>refreshOne(layout), 320); }
function scheduleAll(){ clearTimeout(_textTimer); _textTimer=setTimeout(()=>{ if(O.cur) loadGallery(); }, 700); }
async function loadSchema(layout){
  layout = layout || O.chosen[O.orientation] || (O.meta[O.orientation] && O.meta[O.orientation].auto_layout);
  if(!layout) return;
  const rows=$('advRows'); if(!rows) return;
  try{
    const data = await api('/api/v1/plugin/FolderCover/editor_schema?orientation='+O.orientation+'&layout='+encodeURIComponent(layout));
    const schema=data.schema||[];
    if(!schema.length){ rows.innerHTML='<span class="status">这个风格没有额外参数。</span>'; return; }
    rows.innerHTML='';
    schema.forEach(f=>{
      const wrap=document.createElement('div'); wrap.className='field';
      const lb=document.createElement('label'); lb.textContent=(f.group?f.group+' · ':'')+(f.label||f.key); wrap.appendChild(lb);
      let el;
      if(f.type==='range'){
        el=document.createElement('input'); el.type='range';
        el.min=f.min!==undefined?f.min:0; el.max=f.max!==undefined?f.max:100;
      } else { el=document.createElement('input'); el.type='text'; if(f.type==='color') el.placeholder='#RRGGBB 或留空'; }
      const cur=(O.config[O.orientation]||{})[f.key];
      el.value = cur===undefined||cur==='' ? (f.default===undefined?'':String(f.default)) : String(cur);
      el.oninput=()=>{ (O.config[O.orientation]=O.config[O.orientation]||{})[f.key]=el.value;
        scheduleOne(layout); };
      wrap.appendChild(el); rows.appendChild(wrap);
    });
  }catch(e){ rows.innerHTML='<span class="status">参数加载失败</span>'; }
}

/* ---------------- 写入 ---------------- */
function readText(){ return {title:$('tTitle').value.trim(), subtitle:$('tSub').value.trim(), kicker:$('tKicker').value.trim(), show_title:$('tShow').checked}; }
async function applyCurrent(){
  if(!O.cur) return;
  if(!O.chosen.portrait && !O.chosen.landscape){ toast('先点一张封面选中风格'); return; }
  $('stat').textContent='写入中…';
  const payload={path:O.cur, text:readText(), portrait_config:O.config.portrait||{}, landscape_config:O.config.landscape||{}};
  if(O.chosen.portrait_single) payload.portrait_layout=O.chosen.portrait_single;
  if(O.chosen.portrait_multi) payload.portrait_multi_layout=O.chosen.portrait_multi;
  if(O.chosen.landscape_single) payload.landscape_layout=O.chosen.landscape_single;
  if(O.chosen.landscape_multi) payload.landscape_multi_layout=O.chosen.landscape_multi;
  try{
    const data=await post('/api/v1/plugin/FolderCover/editor_apply', payload);
    if(data.error){ toast(data.error); return; }
    toast('已写入：'+(data.written||[]).join('、'));
    loadGallery(); loadTree();
  }catch(e){ toast('写入失败：'+e); }
}
async function batchApply(){
  const paths=Array.from(O.checked);
  if(!paths.length) return;
  if(!O.chosen.portrait && !O.chosen.landscape){ toast('先点一张封面选中风格'); return; }
  $('stat').textContent='批量写入 '+paths.length+' 个目录…';
  $('btnBatch').disabled=true;
  try{
    const data=await post('/api/v1/plugin/FolderCover/editor_batch', {
      paths, text:readText(), portrait_layout:O.chosen.portrait||null, landscape_layout:O.chosen.landscape||null,
      portrait_config:O.config.portrait||{}, landscape_config:O.config.landscape||{}
    });
    const lines=(data.results||[]).map(r=>r.path+'  →  '+(r.ok?('成功 '+(r.written||[]).join(',') ):'失败 '+(r.error||'')));
    openModal('批量制作完成', '成功 '+(data.ok||0)+' 个，失败 '+(data.fail||0)+' 个', lines);
    $('stat').textContent='批量完成';
    loadTree();
  }catch(e){ toast('批量失败：'+e); }
  finally{ updateCounts(); }
}

/* ---------------- 全量 + 状态 ---------------- */
async function runAll(){
  if(!confirm('对扫描目录内的全部文件夹执行一次封面生成？')) return;
  try{
    const data=await post('/api/v1/plugin/FolderCover/editor_run_all', {portrait_layout:O.chosen.portrait_single||null, portrait_multi_layout:O.chosen.portrait_multi||null, landscape_layout:O.chosen.landscape_single||null, landscape_multi_layout:O.chosen.landscape_multi||null});
    if(!data.started){ toast(data.message||'已在运行中'); return; }
    O.running=true; updateCounts(); $('stat').textContent='全量制作进行中…';
    pollStatus();
  }catch(e){ toast('启动失败：'+e); }
}
async function pollStatus(){
  clearTimeout(O.timer);
  try{
    const s=await api('/api/v1/plugin/FolderCover/editor_status');
    $('stat').textContent = s.running ? ('进行中：处理 '+s.total+'，成功 '+s.ok+'，跳过 '+s.skip+'，失败 '+s.fail)
      : (s.ts? ('上次：处理 '+s.total+'，成功 '+s.ok+'，跳过 '+s.skip+'，失败 '+s.fail+' · '+s.ts) : '就绪');
    if(s.running){ O.timer=setTimeout(pollStatus, 1500); }
    else if(O.running){ O.running=false; updateCounts(); loadTree(); toast('全量制作完成'); }
  }catch(e){ O.timer=setTimeout(pollStatus, 2500); }
}

/* ---------------- 移动端目录抽屉 ---------------- */
if(MOBILE()){ const tb=$('toolsBox'); if(tb) tb.open=false; }
function toggleDrawer(open){
  const side=$('side'), scrim=$('scrim');
  if(!side) return;
  side.classList.toggle('open', !!open);
  scrim.classList.toggle('show', !!open);
}
$('btnTree').onclick=()=>toggleDrawer(true);
$('scrim').onclick=()=>toggleDrawer(false);
window.addEventListener('keydown', e=>{ if(e.key==='Escape') toggleDrawer(false); });

/* ---------------- 事件 ---------------- */
document.querySelectorAll('.seg button').forEach(b=>{
  b.onclick=()=>{ document.querySelectorAll('.seg button').forEach(x=>x.classList.remove('on')); b.classList.add('on');
    O.orientation=b.dataset.o; if(O.cur) loadGallery(); };
});
$('q').oninput=(e)=>{ O.q=e.target.value.trim(); renderTree(); };
$('btnClear').onclick=()=>{O.checked.clear();renderTree();};
$('btnRefresh').onclick=loadTree;
$('btnApply').onclick=applyCurrent;
$('btnBatch').onclick=batchApply;
$('btnAll').onclick=runAll;
$('btnRerender').onclick=()=>{ if(O.cur) loadGallery(); };
['tTitle','tSub','tKicker'].forEach(id=>{ $(id).oninput=scheduleAll; });
$('tShow').onchange=()=>{ if(O.cur) loadGallery(); };

loadTree();
pollStatus();
</script>
</body>
</html>
"""


def _page() -> HTMLResponse:
    return HTMLResponse(PAGE_HTML)


def _plugin_dir(plugin) -> Path:
    return Path(plugin.__file__).parent


_ENGINE_LOCK = __import__("threading").RLock()


def _engine(plugin):
    """复用主插件的引擎实例；没有就现建一个（插件停用也能预览）。"""
    engine = getattr(plugin, "_engine", None)
    if engine is None:
        from .engine import FolderCoverEngine

        with _ENGINE_LOCK:
            engine = getattr(plugin, "_engine", None)
            if engine is None:
                engine = FolderCoverEngine(plugin, _plugin_dir(plugin) / "layouts")
                plugin._engine = engine
    return engine


def _choices(plugin, orientation: str) -> List[Dict[str, Any]]:
    if orientation == "portrait":
        single = list(plugin.PORTRAIT_SINGLE_CHOICES)
        multi = list(plugin.PORTRAIT_MULTI_CHOICES)
    else:
        single = list(plugin.LANDSCAPE_SINGLE_CHOICES)
        multi = list(plugin.LANDSCAPE_MULTI_CHOICES)
    items: List[Dict[str, Any]] = []
    for row in single:
        items.append({"value": row["value"], "title": row["title"], "group": "单图版式"})
    for row in multi:
        items.append({"value": row["value"], "title": row["title"], "group": "多图版式"})
    return items


def _roots(plugin) -> List[Path]:
    """插件里的 _scan_paths 在运行态是换行字符串，这里统一成路径列表。"""
    raw = getattr(plugin, "_scan_paths", "")
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split("\n") if p.strip()]
    else:
        parts = [str(p).strip() for p in (raw or [])]
    return [Path(p) for p in parts]


def _safe_path(plugin, raw: str) -> Optional[Path]:
    """只允许配置里扫描范围内的目录，避免页面被用来读写任意路径。"""
    path = Path(str(raw or "").strip())
    if not path.is_dir():
        return None
    roots = _roots(plugin)
    for root in roots:
        try:
            path.resolve().relative_to(root.resolve())
            return path
        except Exception:
            continue
    return False  # 明确不在范围内


def _special_dirs():
    try:
        from . import SPECIAL_DIRS as special_dirs

        return set(special_dirs)
    except Exception:
        return set()


def _count_images(path: Path) -> int:
    try:
        return len([p for p in path.iterdir() if p.is_file()
                    and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")])
    except Exception:
        return 0


def _tree(plugin, keyword: str = "", limit: int = 6000, depth_limit: int = 8) -> List[Dict[str, Any]]:
    """把扫描根目录展开成树，供前端多选；顺带标出已有封面与图片数。"""
    specials = _special_dirs()
    roots = [r for r in _roots(plugin) if r.is_dir()]
    counter = {"n": 0}

    def walk(path: Path, depth: int) -> Dict[str, Any]:
        counter["n"] += 1
        node = {
            "path": str(path),
            "name": path.name,
            "images": _count_images(path),
            "has_folder": (path / "folder.jpg").is_file(),
            "has_backdrop": (path / "backdrop.jpg").is_file(),
            "children": [],
        }
        if depth >= depth_limit or counter["n"] >= limit:
            return node
        try:
            subs = sorted([d for d in path.iterdir() if d.is_dir() and not d.is_symlink()])
        except Exception:
            return node
        for sub in subs:
            if sub.name.startswith(".") or sub.name.lower() in specials:
                continue
            node["children"].append(walk(sub, depth + 1))
            if counter["n"] >= limit:
                break
        return node

    return [walk(root, 0) for root in roots]


def _schema(plugin, orientation: str, layout: str) -> List[Dict[str, Any]]:
    modules = _engine(plugin).layout_modules("portrait" if orientation == "portrait" else "landscape")
    module = modules.get(layout)
    if module is None:
        return []
    try:
        raw = module.get_schema() or []
    except Exception:
        return []
    flat: List[Dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict) and "items" in entry:
            for item in entry.get("items") or []:
                row = dict(item)
                row["group"] = entry.get("group") or ""
                row["label"] = row.get("label") or row.get("title") or row.get("key")
                flat.append(row)
        elif isinstance(entry, dict):
            flat.append(entry)
    return flat


def _merge_text(config: Dict[str, Any], text: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(config or {})
    for key in ("title", "subtitle", "kicker", "meta"):
        value = (text or {}).get(key)
        if value:
            merged[key] = value
    return merged


def _render_frame(plugin, assets: Dict[str, Any], directory: Path, orientation: str,
                  layout: str, config: Dict[str, Any], text: Dict[str, Any], size):
    from . import BACKDROP_SIZE, FOLDER_SIZE

    cfg = _merge_text(config, text)
    show = text.get("show_title")
    if show is None:
        show = getattr(plugin, "_title_enabled", True)
    cfg["show_title"] = bool(show)
    if not show:
        cfg["title"] = ""
    elif not cfg.get("title"):
        cfg["title"] = directory.name
    target_size = size or (FOLDER_SIZE if orientation == "portrait" else BACKDROP_SIZE)
    # 预览画布比成品小：把绝对像素参数（字号等）按比例缩放，保证"预览即成品"
    full_h = FOLDER_SIZE[1] if orientation == "portrait" else BACKDROP_SIZE[1]
    scale = target_size[1] / float(full_h)
    if abs(scale - 1.0) > 0.01:
        try:
            for f in _schema(plugin, orientation, layout):
                if str(f.get("key", "")).endswith("_size") and "default" in f:
                    cfg.setdefault(f["key"], f["default"])
        except Exception:
            pass
        for k, v in list(cfg.items()):
            if k.endswith("_size") or k in ("title_size", "subtitle_size", "line_gap"):
                try:
                    cfg[k] = max(8, int(float(v) * scale))
                except (TypeError, ValueError):
                    continue
    return _engine(plugin).render(layout, cfg, assets, target_size, orientation)


def _b64(frame) -> str:
    buffer = io.BytesIO()
    frame.convert("RGB").save(buffer, format="JPEG", quality=86, subsampling=0)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")



_ASSET_CACHE: Dict[str, Any] = {}


def _assets(plugin, target: Path) -> Dict[str, Any]:
    """同一目录短时间内多次预览/应用只扫一次素材，避免重复算哈希。"""
    import time

    key = str(target)
    try:
        stamp = int(target.stat().st_mtime)
    except Exception:
        stamp = 0
    hit = _ASSET_CACHE.get(key)
    now = time.time()
    if hit and hit[0] == stamp and now - hit[1] < 300:
        return hit[2]
    data = plugin._collect_assets(target)
    _ASSET_CACHE[key] = (stamp, now, data)
    if len(_ASSET_CACHE) > 200:
        _ASSET_CACHE.clear()
    return data


_CACHE: "OrderedDict[str, str]" = OrderedDict()
_CACHE_LIMIT = 90


def _cache_key(target: Path, orientation: str, layout: str, text, cfg) -> str:
    import hashlib
    import json

    try:
        stamp = int(target.stat().st_mtime)
    except Exception:
        stamp = 0
    raw = json.dumps([str(target), stamp, orientation, layout, text or {}, cfg or {}],
                     ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    value = _CACHE.get(key)
    if value:
        _CACHE.move_to_end(key)
    return value


def _cache_put(key: str, value: str) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_LIMIT:
        _CACHE.popitem(last=False)


def _choices_meta(plugin, payload: Dict[str, Any]) -> Dict[str, Any]:
    """先返回风格清单（不含图），前端据此先把卡片骨架摆出来。"""
    target = _safe_path(plugin, payload.get("path"))
    if not target:
        return {"error": "目录不在扫描范围内"}
    orientation = "landscape" if payload.get("orientation") == "landscape" else "portrait"
    assets = _assets(plugin, target)
    mode = plugin._mode_for(assets)
    items = []
    for choice in _choices(plugin, orientation):
        title = choice["title"]
        name, tag = title, ""
        if "（" in title:
            name = title.split("（")[0]
            tag = title.split("（")[-1].rstrip("）")
        items.append({
            "value": choice["value"], "title": name, "tag": tag, "group": choice["group"],
            "recommend": (choice["group"].startswith("多图") and mode == "multi")
                         or (choice["group"].startswith("单图") and mode == "single"),
        })
    selected = {
        "portrait_single": getattr(plugin, "_portrait_layout", ""),
        "portrait_multi": getattr(plugin, "_portrait_multi_layout", ""),
        "landscape_single": getattr(plugin, "_landscape_layout", ""),
        "landscape_multi": getattr(plugin, "_landscape_multi_layout", ""),
    }
    return {"path": str(target), "orientation": orientation, "mode": mode,
            "auto_layout": plugin._pick_layout(orientation, assets),
            "selected": selected, "items": items}


def _gallery_one(plugin, payload: Dict[str, Any]) -> Dict[str, Any]:
    """渲染单个风格；带内存缓存，来回切换时直接命中。"""
    target = _safe_path(plugin, payload.get("path"))
    if not target:
        return {"error": "目录不在扫描范围内"}
    orientation = "landscape" if payload.get("orientation") == "landscape" else "portrait"
    layout = str(payload.get("layout") or "").strip()
    if not layout:
        return {"error": "缺少 layout 参数"}
    if layout not in [c["value"] for c in _choices(plugin, orientation)]:
        return {"error": "未知风格：" + layout}

    text = payload.get("text") or {}
    configs = payload.get("configs") or {}
    cfg = configs.get(orientation) or {}
    key = _cache_key(target, orientation, layout, text, cfg)
    cached = _cache_get(key)
    if cached:
        return {"value": layout, "img": cached, "cached": True}

    assets = _assets(plugin, target)
    size = (380, 570) if orientation == "portrait" else (560, 315)
    frame = _render_frame(plugin, assets, target, orientation, layout, cfg, text, size)
    if frame is None:
        return {"error": "渲染失败：" + layout}
    image = _b64(frame)
    _cache_put(key, image)
    return {"value": layout, "img": image}


def _apply_one(plugin, target: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    text = payload.get("text") or {}
    want_portrait = bool(payload.get("portrait_layout") or payload.get("portrait_multi_layout"))
    want_landscape = bool(payload.get("landscape_layout") or payload.get("landscape_multi_layout"))
    if not want_portrait and not want_landscape:
        want_portrait = want_landscape = True
    assets = _assets(plugin, target)
    mode = plugin._mode_for(assets)
    portrait_layout = ((payload.get("portrait_multi_layout") if mode == "multi" else None)
                       or payload.get("portrait_layout")
                       or (plugin._portrait_multi_layout if mode == "multi" else plugin._portrait_layout))
    landscape_layout = ((payload.get("landscape_multi_layout") if mode == "multi" else None)
                        or payload.get("landscape_layout")
                        or (plugin._landscape_multi_layout if mode == "multi" else plugin._landscape_layout))
    portrait_config = dict(payload.get("portrait_config") or {})
    landscape_config = dict(payload.get("landscape_config") or {})
    from . import BACKDROP_SIZE, FOLDER_SIZE

    written: List[str] = []
    for orientation, layout, cfg, size, name, wanted in (
        ("portrait", portrait_layout, portrait_config, FOLDER_SIZE, "folder.jpg", want_portrait),
        ("landscape", landscape_layout, landscape_config, BACKDROP_SIZE, "backdrop.jpg", want_landscape),
    ):
        if not wanted:
            continue
        frame = _render_frame(plugin, assets, target, orientation, layout, cfg, text, size)
        if frame is None:
            continue
        frame.convert("RGB").save(target / name, format="JPEG", quality=90, subsampling=0, optimize=False)
        written.append(name)

    style = {
        "portrait_layout": portrait_layout if want_portrait else (plugin._read_style(target).get("portrait_layout") or plugin._portrait_layout),
        "landscape_layout": landscape_layout if want_landscape else (plugin._read_style(target).get("landscape_layout") or plugin._landscape_layout),
        "portrait_multi_layout": payload.get("portrait_multi_layout") or "",
        "landscape_multi_layout": payload.get("landscape_multi_layout") or "",
        "portrait_config": portrait_config,
        "landscape_config": landscape_config,
        "title": text.get("title") or "",
        "subtitle": text.get("subtitle") or "",
        "kicker": text.get("kicker") or "",
        "meta": text.get("meta") or "",
        "show_title": bool(text.get("show_title", True)),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if written:
        plugin._write_manifest(target, written, style=style)
    return {"ok": bool(written), "written": written, "style": style}


def _apply(plugin, payload: Dict[str, Any]) -> Dict[str, Any]:
    target = _safe_path(plugin, payload.get("path"))
    if not target:
        return {"error": "目录不在扫描范围内"}
    return _apply_one(plugin, target, payload)


def _batch(plugin, payload: Dict[str, Any]) -> Dict[str, Any]:
    paths = payload.get("paths") or []
    results: List[Dict[str, Any]] = []
    ok = fail = 0
    for raw in paths[:200]:
        target = _safe_path(plugin, raw)
        if not target:
            results.append({"path": str(raw), "ok": False, "error": "不在扫描范围内"})
            fail += 1
            continue
        try:
            res = _apply_one(plugin, target, payload)
            results.append({"path": str(target), "ok": res.get("ok", False),
                            "written": res.get("written"), "error": res.get("error")})
            ok += 1 if res.get("ok") else 0
            fail += 0 if res.get("ok") else 1
        except Exception as err:  # noqa: BLE001
            results.append({"path": str(target), "ok": False, "error": str(err)})
            fail += 1
    return {"ok": ok, "fail": fail, "results": results}


def _run_all(plugin, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stats = getattr(plugin, "_last_stats", None) or {}
    if stats.get("running"):
        return {"started": False, "message": "全量任务已经在运行"}
    runner = getattr(plugin, "scan_once", None)
    if not callable(runner):
        return {"started": False, "message": "插件未提供扫描入口"}

    payload = payload or {}
    overrides = {}
    for key in ("portrait", "portrait_multi", "landscape", "landscape_multi"):
        val = payload.get(key + "_layout")
        if val:
            overrides[key] = val

    def _job():
        try:
            runner(overrides)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_job, name="foldercover-scan", daemon=True).start()
    return {"started": True}


def _status(plugin) -> Dict[str, Any]:
    stats = getattr(plugin, "_last_stats", None) or {}
    return {
        "running": bool(stats.get("running")),
        "total": stats.get("total", 0),
        "ok": stats.get("ok", 0),
        "skip": stats.get("skip", 0),
        "fail": stats.get("fail", 0),
        "ts": stats.get("ts", ""),
    }


def _thumb(plugin, raw_path: str, kind: str = "folder") -> Response:
    target = _safe_path(plugin, raw_path)
    if not target:
        return Response(status_code=404)
    name = "folder.jpg" if kind != "backdrop" else "backdrop.jpg"
    image_path = target / name
    if not image_path.is_file():
        return Response(status_code=404)
    with open(image_path, "rb") as handle:
        return Response(content=handle.read(), media_type="image/jpeg")


def build_routes(plugin) -> List[Dict[str, Any]]:
    """把页面和接口注册进 MoviePilot 的插件路由表。"""

    def page() -> HTMLResponse:
        return _page()

    def tree(keyword: str = "") -> Dict[str, Any]:
        return {"roots": _tree(plugin, keyword=keyword)}

    def choices(payload: Dict[str, Any]) -> Dict[str, Any]:
        return _choices_meta(plugin, payload)

    def gallery(payload: Dict[str, Any]) -> Dict[str, Any]:
        return _gallery_one(plugin, payload)

    def schema(orientation: str, layout: str) -> Dict[str, Any]:
        return {"schema": _schema(plugin, orientation, layout)}

    def apply(payload: Dict[str, Any]) -> Dict[str, Any]:
        return _apply(plugin, payload)

    def batch(payload: Dict[str, Any]) -> Dict[str, Any]:
        return _batch(plugin, payload)

    def run_all(payload: Dict[str, Any]) -> Dict[str, Any]:
        return _run_all(plugin, payload)

    def status() -> Dict[str, Any]:
        return _status(plugin)

    def thumb(path: str, kind: str = "folder") -> Response:
        return _thumb(plugin, path, kind)

    return [
        {"path": "/editor", "endpoint": page, "methods": ["GET"],
         "allow_anonymous": True, "summary": "文件夹封面工作室"},
        {"path": "/editor_tree", "endpoint": tree, "methods": ["GET"], "allow_anonymous": True,
         "summary": "扫描目录树"},
        {"path": "/editor_choices", "endpoint": choices, "methods": ["POST"], "allow_anonymous": True,
         "summary": "风格清单"},
        {"path": "/editor_gallery", "endpoint": gallery, "methods": ["POST"], "allow_anonymous": True,
         "summary": "渲染单个风格"},
        {"path": "/editor_schema", "endpoint": schema, "methods": ["GET"], "allow_anonymous": True,
         "summary": "布局参数定义"},
        {"path": "/editor_apply", "endpoint": apply, "methods": ["POST"], "allow_anonymous": True,
         "summary": "写入当前目录封面"},
        {"path": "/editor_batch", "endpoint": batch, "methods": ["POST"], "allow_anonymous": True,
         "summary": "批量写入选中目录"},
        {"path": "/editor_run_all", "endpoint": run_all, "methods": ["POST"], "allow_anonymous": True,
         "summary": "一键全量制作"},
        {"path": "/editor_status", "endpoint": status, "methods": ["GET"], "allow_anonymous": True,
         "summary": "全量任务状态"},
        {"path": "/editor_thumb", "endpoint": thumb, "methods": ["GET"], "allow_anonymous": True,
         "summary": "读取现有封面"},
    ]
