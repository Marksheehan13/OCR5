const pages=[...document.querySelectorAll('.page')];
const nav=[...document.querySelectorAll('[data-page]')];
const crumb=document.getElementById('crumb');
const API_BASE=window.OCR5_API_BASE||'';

function show(name){
  pages.forEach(page=>page.classList.toggle('hidden',page.id!==name));
  document.querySelectorAll('.nav[data-page]').forEach(item=>item.classList.toggle('active',item.dataset.page===name));
  if(crumb) crumb.textContent=name[0].toUpperCase()+name.slice(1);
  window.scrollTo({top:0,behavior:'smooth'});
  if(name==='invoices') loadLiveInvoices();
  if(name==='analytics') loadLiveAnalytics();
}

document.querySelectorAll('[data-page]').forEach(item=>{
  item.addEventListener('click',event=>{event.preventDefault();show(item.dataset.page);});
});

const state={invoice:null,apiKey:localStorage.getItem('ocr5_api_key')||'',provider:localStorage.getItem('ocr5_provider')||'Google Gemini (free tier)'};

function esc(value){return String(value??'').replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[m]));}
function money(value,currency='EUR'){const n=Number(value);return Number.isFinite(n)?new Intl.NumberFormat('en-IE',{style:'currency',currency}).format(n):'—';}
function api(path,options={}){return fetch(`${API_BASE}${path}`,options).then(async r=>{const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.detail||`Request failed (${r.status})`);return data;});}

function ensureOverlay(){
  if(document.getElementById('live-overlay'))return document.getElementById('live-overlay');
  const el=document.createElement('div');el.id='live-overlay';el.className='live-overlay hidden';
  el.innerHTML=`<div class="live-backdrop"></div><div class="live-modal" role="dialog" aria-modal="true"></div>`;
  document.body.appendChild(el);el.querySelector('.live-backdrop').onclick=()=>el.classList.add('hidden');return el;
}
function openOverlay(html){const el=ensureOverlay();el.querySelector('.live-modal').innerHTML=html;el.classList.remove('hidden');return el;}
function closeOverlay(){document.getElementById('live-overlay')?.classList.add('hidden');}

async function openUploader(){
  const overlay=openOverlay(`<div class="live-modal-head"><div><span class="live-kicker">OCR5 AI</span><h2>Bring your invoices in.</h2><p>Drop documents here. OCR5 will extract, validate and prepare them for review.</p></div><button class="live-close" data-close>×</button></div>
  <div class="upload-dropzone" id="live-drop"><div class="upload-orb">✦</div><b>Drop invoices here</b><span>or choose files from your computer</span><small>JPG · PNG · WEBP · TIFF · HEIC</small><button class="primary" id="choose-files">Choose invoices</button><input id="live-files" type="file" multiple accept=".jpg,.jpeg,.png,.heic,.heif,.bmp,.tiff,.webp" hidden></div>
  <div class="provider-row"><label>AI provider<select id="live-provider"></select></label><label>API key<input id="live-key" type="password" placeholder="Stored only in this browser session"></label></div>`);
  overlay.querySelector('[data-close]').onclick=closeOverlay;
  const provider=overlay.querySelector('#live-provider');const key=overlay.querySelector('#live-key');
  try{const p=await api('/api/providers');provider.innerHTML=p.providers.map(x=>`<option>${esc(x.name)}</option>`).join('');provider.value=state.provider;}catch{provider.innerHTML=`<option>${esc(state.provider)}</option>`;}
  key.value=state.apiKey;
  const input=overlay.querySelector('#live-files');overlay.querySelector('#choose-files').onclick=()=>input.click();
  const drop=overlay.querySelector('#live-drop');['dragenter','dragover'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('dragging');}));['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('dragging');}));
  drop.addEventListener('drop',e=>processFiles([...e.dataTransfer.files],provider.value,key.value));input.addEventListener('change',()=>processFiles([...input.files],provider.value,key.value));
}

async function processFiles(files,provider,key){
  if(!files.length)return;
  if(!key){alert('Add your AI API key to process invoices.');return;}
  state.apiKey=key;state.provider=provider;localStorage.setItem('ocr5_api_key',key);localStorage.setItem('ocr5_provider',provider);
  const overlay=ensureOverlay();overlay.classList.remove('hidden');overlay.querySelector('.live-modal').innerHTML=`<div class="processing-screen"><div class="processing-orb">✦</div><span class="live-kicker">OCR5 INTELLIGENCE</span><h2>Understanding your invoices.</h2><p id="process-detail">Preparing ${files.length} document${files.length>1?'s':''}…</p><div class="process-list" id="process-list"></div></div>`;
  const list=overlay.querySelector('#process-list');let first=null;
  for(const file of files){
    const row=document.createElement('div');row.className='process-row';row.innerHTML=`<span class="process-dot"></span><span>${esc(file.name)}</span><small>Processing…</small>`;list.appendChild(row);
    const form=new FormData();form.append('file',file);
    try{const data=await api('/api/extract',{method:'POST',headers:{'X-OCR5-API-Key':key,'X-OCR5-Provider':provider},body:form});row.querySelector('small').textContent=`${data.invoice.overall_confidence}% confidence`;row.querySelector('.process-dot').textContent='✓';if(!first)first=data.invoice;}catch(err){row.querySelector('small').textContent=err.message;row.classList.add('failed');}
  }
  if(first){state.invoice=first;setTimeout(()=>openReview(first),450);}else{overlay.querySelector('#process-detail').textContent='No invoices could be processed. Check your provider and API key.';}
}

function confidenceClass(n){return n>=90?'high':n>=70?'medium':'review';}
function fieldEditor(label,key,field){const value=field?.value??'';const confidence=field?.confidence??0;return `<label class="review-field"><span>${label}<em class="confidence ${confidenceClass(confidence)}">${confidence}%</em></span><input data-field="${key}" value="${esc(value)}"><small>${confidence>=90?'High confidence':confidence>=70?'Worth a quick check':'Needs review'}</small></label>`;}

function openReview(invoice){
  const overlay=openOverlay(`<div class="review-shell"><div class="review-head"><div><span class="live-kicker">INVOICE INTELLIGENCE</span><h2>${esc(invoice.source_file)}</h2><p>OCR5 extracted this document and checked it for consistency.</p></div><button class="live-close" data-close>×</button></div><div class="review-body"><div class="document-panel"><div class="document-placeholder"><div class="doc-icon">▤</div><b>Source document</b><span>${esc(invoice.source_file)}</span><small>Document preview becomes available when source storage is connected.</small></div></div><div class="review-panel"><div class="review-summary"><div><span>Overall confidence</span><strong>${invoice.overall_confidence}%</strong></div><div class="review-ring" style="--score:${invoice.overall_confidence}"><span>${invoice.overall_confidence}</span></div></div><div class="review-fields">${fieldEditor('Supplier','supplier',invoice.supplier)}${fieldEditor('Invoice number','invoice_number',invoice.invoice_number)}${fieldEditor('Date','date',invoice.date)}${fieldEditor('Subtotal','subtotal',invoice.subtotal)}${fieldEditor('VAT amount','vat_amount',invoice.vat_amount)}${fieldEditor('VAT rate','vat_rate',invoice.vat_rate)}${fieldEditor('Total','amount',invoice.amount)}</div>${invoice.warnings?.length?`<div class="review-warning"><b>⚠ Review required</b><span>${esc(invoice.warnings.join(' · '))}</span></div>`:''}<div class="line-items-review"><div class="section-title"><b>Line items</b><span>${invoice.line_items?.length||0} detected</span></div>${(invoice.line_items||[]).map((x,i)=>`<div class="line-review"><span>${i+1}</span><b>${esc(x.description)}</b><span>${esc(x.quantity||'')}</span><span>${esc(x.line_total||'')}</span><em>${x.confidence}%</em></div>`).join('')}</div><div class="review-actions"><button class="secondary" data-close>Back</button><button class="primary" id="save-review">Approve & save</button></div></div></div></div>`);
  overlay.querySelectorAll('[data-close]').forEach(b=>b.onclick=closeOverlay);
  overlay.querySelector('#save-review').onclick=()=>saveReviewedInvoice(overlay,invoice);
}

async function saveReviewedInvoice(overlay,invoice){
  const edited=structuredClone(invoice);overlay.querySelectorAll('[data-field]').forEach(input=>{const key=input.dataset.field;if(edited[key])edited[key].value=input.value;});
  const button=overlay.querySelector('#save-review');button.disabled=true;button.textContent='Checking & saving…';
  try{
    let duplicates=[];try{duplicates=(await api('/api/invoices/check-duplicates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(edited)})).matches||[];}catch(err){if(err.message.includes('Supabase'))duplicates=[];else throw err;}
    if(duplicates.length){button.disabled=false;button.textContent='Approve & save';const first=duplicates[0];if(!confirm(`OCR5 found a possible duplicate: ${first.supplier} · ${money(first.amount,first.currency)}.\n\nSave anyway?`))return;button.disabled=true;button.textContent='Saving…';}
    const saved=await api('/api/invoices/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(edited)});
    closeOverlay();show('invoices');notify(`Invoice saved · ${saved.supplier||edited.supplier.value||'Invoice'}`);
  }catch(err){button.disabled=false;button.textContent='Approve & save';notify(err.message,true);}
}

function notify(message,error=false){let n=document.getElementById('ocr5-toast');if(!n){n=document.createElement('div');n.id='ocr5-toast';document.body.appendChild(n);}n.className=`ocr5-toast ${error?'error':''}`;n.textContent=message;n.classList.add('show');setTimeout(()=>n.classList.remove('show'),3500);}

async function loadLiveInvoices(){
  try{const data=await api('/api/invoices');const rows=data.invoices||[];const container=document.querySelector('#invoices .invoice-table');if(!container||!rows.length)return;const heading=container.querySelector('.heading')?.outerHTML||'';container.innerHTML=heading+rows.map(r=>`<div class="invoice-row clickable live-invoice-row"><span class="supplier"><i class="supplier-logo">${esc((r.supplier||'?')[0].toUpperCase())}</i><b>${esc(r.supplier||'Unknown')}</b></span><span>${esc(r.invoice_number||'—')}</span><span>${esc(r.date||'—')}</span><b>${money(r.amount,r.currency||'EUR')}</b><strong class="confidence">${r.confidence??0}%</strong><span class="status good"><i></i>Saved</span></div>`).join('');}catch{/* demo data remains visible when database is not configured */}
}

async function loadLiveAnalytics(){try{const data=await api('/api/analytics');document.querySelectorAll('[data-live-total-spend]').forEach(el=>el.textContent=money(data.total_spend));document.querySelectorAll('[data-live-invoice-count]').forEach(el=>el.textContent=data.invoice_count);}catch{/* demo analytics remain visible */}}

// Replace the old presentation-only upload interactions with the live OCR workflow.
document.getElementById('upload')?.addEventListener('click',openUploader);
document.getElementById('upload2')?.addEventListener('click',openUploader);

document.addEventListener('click',event=>{
  const row=event.target.closest('.live-invoice-row');if(row){notify('Open an invoice from the review queue to inspect it.');}
});

document.addEventListener('keydown',event=>{if(event.key==='Escape')closeOverlay();});

const search=document.querySelector('.search input');
search?.addEventListener('input',()=>{const q=search.value.trim().toLowerCase();document.querySelectorAll('#invoices .invoice-row.clickable').forEach(row=>row.style.display=!q||row.textContent.toLowerCase().includes(q)?'':'none');});

show('overview');
