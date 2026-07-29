
const API = (p)=>'/api' + p;
const colors = JSON.parse(localStorage.getItem('hc_colors') || '{"Hermes":"#2563eb","GPT":"#10b981","Codex":"#f59e0b","Ollama":"#a78bfa"}');
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function relTime(s){
  if(!s) return '--';
  const ms = Date.now() - new Date(s).getTime();
  const s60 = Math.floor(ms/1000);
  if(s60 < 5) return 'just now';
  if(s60 < 60) return s60 + 's';
  const m = Math.floor(s60/60);
  if(m < 60) return m + 'm';
  const h = Math.floor(m/60);
  if(h < 24) return h + 'h';
  return Math.floor(h/24) + 'd';
}
function el(tag, cls, text){ const e=document.createElement(tag); if(cls) e.className=cls; if(text) e.textContent=text; return e; }
function pill(msg){
  const k = (msg.status||'').toLowerCase() || (msg.type||'chat').toLowerCase();
  const r = el('span','badge'); r.classList.add(esc(k)); r.textContent = k; return r;
}
const cardColors = {assign:'#f59e0b0d','inference':'#a78bfa0d',chat:'#3b82f60d',done:'#10b9810d',yield:'#ef44440d'};
const borderColors = {assign:'#f59e0b33','inference':'#a78bfa33',chat:'#3b82f633',done:'#10b98144',yield:'#ef444444'};
function renderMessage(m){
  const row = el('article','msg'); row._message = m;
  const hue = colors[m.from] || '#6b7280';
  const key = ((m.status||'').toLowerCase()||(m.type||'chat').toLowerCase());
  row.style.background = `linear-gradient(180deg, ${cardColors[key]||'rgba(255,255,255,.025)'}, transparent)`;
  row.style.borderColor = borderColors[key] || 'var(--line)';
  const av = el('span','av'); av.style.background = hue; av.textContent = (m.from||'?')[0].toUpperCase();
  const who = el('span','who'); who.textContent = m.from;
  const to = el('span','to'); to.textContent = 'to: ' + (m.to||'@all');
  const when = el('span','when'); when.textContent = relTime(m.ts); when.title = m.ts;
  const head = el('div','msg-head'); head.appendChild(av); head.appendChild(who); head.appendChild(to); head.appendChild(when); head.appendChild(pill(m));
  row.appendChild(head);
  const txt = el('p','body'); txt.textContent = m.content; row.appendChild(txt);
  return row;
}
let selectedFilter = 'all';
function applyFilter(){
  const feed = document.getElementById('feed');
  if(!feed) return;
  const mine = document.getElementById('f')?.value || '';
  Array.from(feed.children).forEach(node=>{
    const m = node._message; if(!m) return;
    const k = ((m.status||'').toLowerCase()||(m.type||'chat').toLowerCase());
    const show = selectedFilter === 'all' || (selectedFilter === 'mine' && m.from === mine) || (['chat','assign','status','done','yield','inference'].includes(selectedFilter) && k === selectedFilter);
    node.style.display = show ? '' : 'none';
  });
}
function renderSidebar(agents, messages){
  const wrap = document.getElementById('sidebar');
  if(!wrap) return;
  agents = Array.isArray(agents) ? agents : [];
  messages = Array.isArray(messages) ? messages : [];
  wrap.innerHTML = '<div id="sidebar-title">Agents</div><div id="sidebar-online"></div><div id="sidebar-title" style="margin-top:6px">Idle</div><div id="sidebar-offline"></div>';
  const on = document.getElementById('sidebar-online'); const off = document.getElementById('sidebar-offline');
  on.innerHTML = ''; off.innerHTML = '';
  if(!agents.length){ wrap.innerHTML += '<div id="sidebar-empty" class="empty">No agents yet.</div>'; return; }
  const PRESENCE = 60000; const now = Date.now();
  const last = new Map(); messages.slice().reverse().forEach(m=>{ if(!last.has(m.from)) last.set(m.from, m.ts); });
  const online=[]; const offline=[];
  agents.forEach(a=>{
    const ts = last.get(a.name); const t = ts ? new Date(ts).getTime() : 0;
    const on2 = t > 0 && (now-t) < PRESENCE;
    (on2 ? online : offline).push({...a, _on: on2});
  });
  function addRow(a, target){
    const r = document.createElement('button'); r.className = 'agent-row';
    if(!colors[a.name]) colors[a.name] = a.color;
    const av = el('span','av'); av.style.background = colors[a.name]; av.textContent = (a.name||'?')[0].toUpperCase();
    const info = el('span','info'); const n=el('span','name'); n.textContent=a.name; const role=el('span','role'); role.textContent=a.role||''; info.appendChild(n); info.appendChild(role);
    r.appendChild(av); r.appendChild(info);
    r.addEventListener('click', ()=>{ const t=document.getElementById('t'); if(t){ t.value=a.name; load(); }});
    target.appendChild(r);
  }
  online.forEach(a=>addRow(a, on)); offline.forEach(a=>addRow(a, off));
}
async function load(){
  let pin = '';
  try { const el = document.getElementById('pin'); if(el) pin = (el.value||'').trim(); } catch {}
  if(!pin){
    try { pin = localStorage.getItem('hc_pin') || ''; } catch {}
  }
  const h = {'Content-Type':'application/json','X-Channel-PIN': pin};
  let agents=null; let messages=null;
  try {
    [agents, messages] = await Promise.all([
      fetch(API('/agents'), {headers:h, cache:'no-store'}).then(r=>r.json()).catch(()=>null),
      fetch(API('/messages'), {headers:h, cache:'no-store'}).then(r=>r.json()).catch(()=>null)
    ]);
  } catch (e) {
    // handled below
  }
  agents = Array.isArray(agents) ? agents : [];
  messages = Array.isArray(messages) ? messages : [];
  const feed = document.getElementById('feed');
  const emptyEl = document.getElementById('feed-empty');
  const fromSel = document.getElementById('f');
  const tSel = document.getElementById('t');
  fromSel.innerHTML = '';
  agents.forEach(a=>{ const o=el('option'); o.value=a.name; o.textContent=a.name+' ('+a.role+')'; fromSel.appendChild(o); if(!colors[a.name]) colors[a.name]=a.color; });
  tSel.innerHTML = '<option value="all">@all</option>' + agents.map(a=>`<option value="${esc(a.name)}">${esc(a.name)}</option>`).join('');
  try { localStorage.setItem('hc_colors', JSON.stringify(colors)); } catch {}
  renderSidebar(agents, messages);
  if(feed){
    feed.innerHTML='';
    const sorted = messages.sort((a,b)=>String(a.ts).localeCompare(String(b.ts)));
    sorted.forEach(m=> feed.appendChild(renderMessage(m)));
    emptyEl.style.display = 'none';
    selectedFilter = 'all';
    const activeFilterBtn = document.querySelector('#filters button[data-filter="all"]');
    document.querySelectorAll('#filters button').forEach(x=> x.classList.toggle('active', x === activeFilterBtn));
    applyFilter();
    requestAnimationFrame(()=>{ feed.lastElementChild?.scrollIntoView({behavior:'smooth',block:'end'}); });
  }
  const dbg = document.getElementById('debug-count');
  if(dbg) dbg.textContent = 'agents:' + agents.length + ' messages:' + messages.length;
}
document.getElementById('connect-btn').addEventListener('click', async ()=>{
  const pin = (document.getElementById('pin').value||'').trim();
  const msgEl = document.getElementById('login-msg');
  msgEl.textContent = 'Checking...';
  const h = {'Content-Type':'application/json','X-Channel-PIN': pin};
  try {
    const r = await fetch(API('/agents'), {headers:h, mode:'cors', cache:'no-store'});
    if(!r.ok){ msgEl.textContent = 'Server returned ' + r.status; return; }
    try { localStorage.setItem('hc_pin', pin); } catch {}
    enterApp();
  } catch (err){ msgEl.textContent = 'Network: ' + err.message; }
});
document.getElementById('composer').addEventListener('submit', async e=>{
  e.preventDefault();
  const b = document.getElementById('b');
  const content = b.value.trim(); if(!content) return;
  const payload = { from: document.getElementById('f').value, to: document.getElementById('t').value, type: document.getElementById('ty').value, content, status: document.getElementById('ty').value, assigned_to: '' };
  const h = {'Content-Type':'application/json','X-Channel-PIN': (document.getElementById('pin')?.value||'')};
  b.disabled = true;
  try {
    const r = await fetch(API('/messages'), {method:'POST', headers:h, body: JSON.stringify(payload)});
    b.value = ''; if(r.ok) load();
  } finally { b.disabled = false; }
});
document.getElementById('filters').addEventListener('click', e=>{
  const btn = e.target.closest('button[data-filter]'); if(!btn) return;
  selectedFilter = btn.dataset.filter;
  document.querySelectorAll('#filters button').forEach(x=> x.classList.toggle('active', x === btn));
  applyFilter();
});
document.getElementById('clear').addEventListener('click', async ()=>{
  if(!confirm('Archive all messages?')) return;
  const h = {'Content-Type':'application/json','X-Channel-PIN': document.getElementById('pin')?.value || ''};
  const msgs = await (await fetch(API('/messages'), {headers:h})).json();
  await Promise.all(msgs.map(m=> fetch(API('/messages'), {method:'PUT', headers:h, body:JSON.stringify({...m, status:'archived'})})));
  load();
});
function enterApp(){
  document.getElementById('login-wrap').classList.add('hidden');
  const app = document.getElementById('app');
  app.style.display='flex';
  app.style.opacity='0';
  app.offsetHeight; // force synchronous reflow
  app.style.transition='opacity .35s ease';
  app.style.opacity='1';
  load();
}
(function(){
  const qs = new URLSearchParams(location.search);
  const bypass = qs.get('pin');
  const saved = (()=>{ try { return localStorage.getItem('hc_pin'); } catch { return ''; } })();
  if(bypass || saved){
    const pin = bypass || saved;
    const h = {'Content-Type':'application/json','X-Channel-PIN': pin};
    fetch(API('/agents'), {headers: h, cache:'no-store'}).then(r => { if(r.ok){ enterApp(); } else { window._bypassErr = 'bypass status=' + r.status; console.warn(window._bypassErr); } }).catch(err => { window._bypassErr = 'bypass network fail'; console.warn(window._bypassErr, err); });
  }
})();
document.getElementById('pin').addEventListener('keydown', e=>{ if(e.key==='Enter'){ document.getElementById('connect-btn').click(); } });
