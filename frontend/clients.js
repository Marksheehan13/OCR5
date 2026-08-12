(() => {
  const API = '/api';
  const CLIENT_KEY = 'ocr5.activeClientId';
  const originalFetch = window.fetch.bind(window);

  function activeClientId() {
    const value = Number(localStorage.getItem(CLIENT_KEY));
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  // Every API request automatically carries the active client context. This
  // keeps the existing invoice UI working without duplicating client logic.
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (!url.includes('/api/') || url.includes('/api/clients')) return originalFetch(input, init);
    const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined));
    const id = activeClientId();
    if (id) headers.set('X-OCR5-Client-ID', String(id));
    return originalFetch(input, { ...init, headers });
  };

  const css = `
    .ocr5-client-nav{position:relative}
    .ocr5-client-nav .client-dot{width:8px;height:8px;border-radius:50%;background:#7c5cff;box-shadow:0 0 12px #7c5cff;display:inline-block;margin-left:auto}
    #clients.ocr5-clients-page{padding-bottom:60px}
    .client-hero{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;margin-bottom:28px}
    .client-hero h1{margin:5px 0 8px;font-size:44px;letter-spacing:-1.8px}
    .client-hero p{margin:0;color:#7f8797;font-size:15px}
    .client-actions{display:flex;gap:10px}
    .client-search{height:46px;min-width:280px;border:1px solid #e5e7ee;border-radius:13px;background:#fff;padding:0 15px;outline:none;font:inherit}
    .client-search:focus{border-color:#8c79ff;box-shadow:0 0 0 4px rgba(124,92,255,.08)}
    .clients-toolbar{display:flex;justify-content:space-between;align-items:center;margin:0 0 16px}
    .clients-toolbar small{color:#8a91a0}
    .clients-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
    .client-card{background:#fff;border:1px solid #e7e9ef;border-radius:18px;padding:20px;box-shadow:0 8px 30px rgba(18,22,33,.045);transition:.2s transform,.2s box-shadow,.2s border-color;cursor:pointer}
    .client-card:hover{transform:translateY(-2px);border-color:#d7d0ff;box-shadow:0 14px 38px rgba(18,22,33,.08)}
    .client-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
    .client-avatar{width:46px;height:46px;border-radius:14px;display:grid;place-items:center;background:linear-gradient(135deg,#171925,#5143a5);color:#fff;font-weight:800;font-size:16px}
    .client-card h3{margin:0;font-size:16px;color:#171925}.client-card .company{display:block;margin-top:4px;color:#8a91a0;font-size:12px}
    .client-card .chevron{color:#9aa0ad;font-size:18px}
    .client-meta{display:flex;gap:8px;margin-top:22px}.client-stat{flex:1;background:#f7f7fa;border-radius:11px;padding:10px}.client-stat b{display:block;font-size:16px;color:#191b24}.client-stat span{font-size:10px;color:#8a91a0;text-transform:uppercase;letter-spacing:.6px}
    .client-footer{display:flex;justify-content:space-between;align-items:center;margin-top:16px;padding-top:14px;border-top:1px solid #eef0f4}.client-status{font-size:11px;color:#5f6675}.client-status i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#2fbe78;margin-right:6px}.client-open{color:#6b58ef;font-weight:700;font-size:12px}
    .client-empty{grid-column:1/-1;border:1px dashed #dfe2e9;border-radius:18px;padding:70px 20px;text-align:center;background:#fbfbfc}.client-empty h3{margin:12px 0 6px}.client-empty p{margin:0;color:#8a91a0}
    .client-modal-backdrop{position:fixed;inset:0;background:rgba(10,12,20,.45);backdrop-filter:blur(8px);z-index:1000;display:grid;place-items:center;padding:20px}
    .client-modal{width:min(560px,100%);background:#fff;border-radius:22px;box-shadow:0 30px 90px rgba(0,0,0,.22);padding:26px}.client-modal h2{margin:0 0 5px;font-size:23px}.client-modal>p{margin:0 0 22px;color:#7f8797;font-size:13px}.client-form{display:grid;gap:13px}.client-form label{display:grid;gap:6px;font-size:11px;font-weight:700;color:#555c6c}.client-form input,.client-form textarea{width:100%;box-sizing:border-box;border:1px solid #e1e4eb;border-radius:11px;padding:11px 12px;font:inherit;outline:none}.client-form textarea{min-height:75px;resize:vertical}.client-form input:focus,.client-form textarea:focus{border-color:#7c5cff;box-shadow:0 0 0 4px rgba(124,92,255,.08)}.client-form-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:8px}.client-secondary{height:42px;padding:0 15px;border:1px solid #e1e4eb;background:#fff;border-radius:11px;font-weight:700}.client-danger{height:42px;padding:0 15px;border:0;background:#171925;color:#fff;border-radius:11px;font-weight:700}.client-error{color:#b33b3b;font-size:12px;min-height:16px}
    .client-context{display:inline-flex;align-items:center;gap:8px;border:1px solid #e5e7ee;border-radius:10px;background:#fff;padding:7px 10px;font-size:11px;color:#555c6c}.client-context i{width:7px;height:7px;border-radius:50%;background:#7c5cff}
    @media(max-width:1050px){.clients-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.clients-grid{grid-template-columns:1fr}.client-hero{align-items:flex-start;flex-direction:column}.client-search{min-width:0;width:100%}}
  `;
  const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
  const initials = name => name.split(/\s+/).filter(Boolean).slice(0,2).map(x => x[0]).join('').toUpperCase() || 'C';

  function addNav() {
    const nav = document.querySelector('.sidebar nav');
    if (!nav || document.querySelector('[data-page="clients"]')) return;
    const insights = nav.querySelector('.nav-label.second');
    const button = document.createElement('button');
    button.className = 'nav ocr5-client-nav'; button.dataset.page = 'clients';
    button.innerHTML = '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3"/><path d="M3.8 20c.7-3.2 2.4-5 5.2-5s4.5 1.8 5.2 5M16 11a3 3 0 1 0 0-6M16.2 15c2.4.1 4 1.7 4.7 5"/></svg><span>Clients</span><span class="client-dot"></span>';
    nav.insertBefore(button, insights || null);
    button.addEventListener('click', () => showClients());
  }

  function addPage() {
    if (document.getElementById('clients')) return;
    const main = document.querySelector('main'); if (!main) return;
    const section = document.createElement('section'); section.className='page hidden ocr5-clients-page'; section.id='clients';
    section.innerHTML = `
      <div class="client-hero"><div><div class="eyebrow">CLIENT MANAGEMENT</div><h1>Clients<span>.</span></h1><p>Keep every client's books separate, organised and ready to work on.</p></div><div class="client-actions"><input id="client-search" class="client-search" placeholder="Search clients…"><button class="primary" id="add-client"><span>＋</span> Add client</button></div></div>
      <div class="clients-toolbar"><small id="client-count">Loading clients…</small><span class="client-context" id="client-context"><i></i><span>No client selected</span></span></div>
      <div class="clients-grid" id="clients-grid"></div>`;
    main.appendChild(section);
    document.getElementById('add-client').addEventListener('click', () => openModal());
    document.getElementById('client-search').addEventListener('input', e => renderClients(window.__ocr5Clients || [], e.target.value));
  }

  function showClients() {
    addNav(); addPage();
    document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
    document.getElementById('clients').classList.remove('hidden');
    document.querySelectorAll('.nav[data-page]').forEach(n => n.classList.toggle('active', n.dataset.page === 'clients'));
    const crumb = document.getElementById('crumb'); if (crumb) crumb.textContent='Clients';
    loadClients();
  }

  function setActiveClient(client, reload=true) {
    localStorage.setItem(CLIENT_KEY, String(client.id));
    window.__ocr5ActiveClient = client;
    const context = document.getElementById('client-context'); if (context) context.innerHTML = `<i></i><span>${esc(client.company_name || client.name)}</span>`;
    const workspace = document.querySelector('.workspace');
    if (workspace) workspace.innerHTML = `<span class="avatar-dot">${esc(initials(client.name))}</span><span><b>${esc(client.company_name || client.name)}</b><small>Active client</small></span><svg viewBox="0 0 16 16"><path d="m4 6 4 4 4-4"/></svg>`;
    if (reload) window.dispatchEvent(new CustomEvent('ocr5:client-changed', {detail:client}));
    showClients();
  }

  async function loadClients() {
    try {
      const res = await originalFetch(`${API}/clients`); if (!res.ok) throw new Error(await res.text());
      const data = await res.json(); window.__ocr5Clients = data.clients || [];
      let current = window.__ocr5Clients.find(c => c.id === activeClientId());
      if (!current) current = window.__ocr5Clients[0];
      if (current) { localStorage.setItem(CLIENT_KEY, String(current.id)); window.__ocr5ActiveClient=current; }
      renderClients(window.__ocr5Clients);
      if (current) { const context=document.getElementById('client-context'); if(context) context.innerHTML=`<i></i><span>${esc(current.company_name || current.name)}</span>`; }
    } catch (err) { renderClientError(err.message); }
  }

  function renderClients(clients, filter='') {
    const grid=document.getElementById('clients-grid'); if(!grid)return;
    const q=filter.trim().toLowerCase(); const rows=clients.filter(c => !q || [c.name,c.company_name,c.email].some(v=>String(v||'').toLowerCase().includes(q)));
    const count=document.getElementById('client-count'); if(count) count.textContent=`${clients.length} active client${clients.length===1?'':'s'}`;
    if(!rows.length){grid.innerHTML=`<div class="client-empty"><div class="client-avatar" style="margin:auto">＋</div><h3>${clients.length?'No clients match your search':'Add your first client'}</h3><p>${clients.length?'Try a different search term.':'Create a client and their bookkeeping data will be isolated from everyone else.'}</p></div>`;return;}
    grid.innerHTML=rows.map(c=>`<article class="client-card" data-client-id="${c.id}"><div class="client-card-top"><div class="client-avatar">${esc(initials(c.company_name || c.name))}</div><div style="flex:1"><h3>${esc(c.company_name || c.name)}</h3><span class="company">${esc(c.company_name && c.name !== c.company_name ? c.name : (c.email || 'Bookkeeping client'))}</span></div><span class="chevron">→</span></div><div class="client-meta"><div class="client-stat"><b data-invoice-count="${c.id}">—</b><span>Invoices</span></div><div class="client-stat"><b data-client-total="${c.id}">—</b><span>Total tracked</span></div></div><div class="client-footer"><span class="client-status"><i></i>Active</span><span class="client-open">Open workspace →</span></div></article>`).join('');
    rows.forEach(c=>{const card=grid.querySelector(`[data-client-id="${c.id}"]`);card.addEventListener('click',()=>setActiveClient(c));loadClientStats(c.id);});
  }

  async function loadClientStats(id){
    try{const r=await originalFetch(`${API}/clients/${id}`);if(!r.ok)return;const d=await r.json();const a=d.analytics||{};const n=document.querySelector(`[data-invoice-count="${id}"]`);const t=document.querySelector(`[data-client-total="${id}"]`);if(n)n.textContent=a.invoice_count??0;if(t)t.textContent=`€${Number(a.total_spend||0).toLocaleString('en-IE',{maximumFractionDigits:0})}`;}catch(_e){}
  }

  function renderClientError(message){const grid=document.getElementById('clients-grid');if(grid)grid.innerHTML=`<div class="client-empty"><h3>Could not load clients</h3><p>${esc(message)}</p></div>`;}

  function openModal(){
    closeModal(); const back=document.createElement('div');back.className='client-modal-backdrop';back.id='client-modal';
    back.innerHTML=`<div class="client-modal"><h2>Add a client</h2><p>Create a private bookkeeping workspace. Invoices saved while this client is active will belong only to them.</p><form class="client-form" id="client-form"><label>Client / contact name<input name="name" required placeholder="John Murphy"></label><label>Company name<input name="company_name" placeholder="John Murphy Ltd"></label><label>Email<input name="email" type="email" placeholder="john@example.com"></label><label>Phone<input name="phone" placeholder="+353…"></label><label>Address<textarea name="address" placeholder="Business address"></textarea></label><div class="client-error" id="client-error"></div><div class="client-form-actions"><button type="button" class="client-secondary" id="client-cancel">Cancel</button><button type="submit" class="client-danger">Create client</button></div></form></div>`;
    document.body.appendChild(back);back.addEventListener('click',e=>{if(e.target===back)closeModal()});document.getElementById('client-cancel').onclick=closeModal;
    document.getElementById('client-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;const payload=Object.fromEntries(new FormData(form).entries());const error=document.getElementById('client-error');try{const r=await originalFetch(`${API}/clients`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not create client');closeModal();await loadClients();setActiveClient(d.client);}catch(err){error.textContent=err.message;}};
  }
  function closeModal(){document.getElementById('client-modal')?.remove();}

  // Bootstrap after the existing application markup has loaded.
  const boot=()=>{addNav();addPage();loadClients();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
  window.ocr5ClientUI={showClients,loadClients,activeClientId};
})();
