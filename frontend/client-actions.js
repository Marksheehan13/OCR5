(() => {
  const API='/api';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const wire=()=>document.querySelectorAll('.client-card').forEach(card=>{
    if(card.querySelector('.client-manage'))return;
    const id=Number(card.dataset.clientId); const footer=card.querySelector('.client-footer'); if(!footer)return;
    const btn=document.createElement('button');btn.type='button';btn.className='client-manage';btn.textContent='Manage';
    btn.style.cssText='border:0;background:transparent;color:#777f8e;font:700 11px inherit;cursor:pointer;padding:4px 0;margin-right:10px';
    btn.onclick=async e=>{e.stopPropagation();
      const client=(window.__ocr5Clients||[]).find(c=>c.id===id);if(!client)return;
      if(!confirm(`Archive ${client.company_name||client.name}? Their invoices will be retained, but the client will no longer appear in the active client list.`))return;
      const r=await fetch(`${API}/clients/${id}`,{method:'DELETE'}); if(!r.ok){alert('Could not archive this client.');return;}
      if(Number(localStorage.getItem('ocr5.activeClientId'))===id)localStorage.removeItem('ocr5.activeClientId');
      window.ocr5ClientUI?.loadClients();
    };
    footer.insertBefore(btn,footer.lastElementChild);
  });
  const observer=new MutationObserver(wire);observer.observe(document.body,{subtree:true,childList:true});wire();
})();
