const pages=[...document.querySelectorAll('.page')];
const nav=[...document.querySelectorAll('[data-page]')];
const crumb=document.getElementById('crumb');

function show(name){
  pages.forEach(page=>page.classList.toggle('hidden',page.id!==name));
  document.querySelectorAll('.nav[data-page]').forEach(item=>item.classList.toggle('active',item.dataset.page===name));
  if(crumb) crumb.textContent=name[0].toUpperCase()+name.slice(1);
  window.scrollTo({top:0,behavior:'smooth'});
}

document.querySelectorAll('[data-page]').forEach(item=>{
  item.addEventListener('click',event=>{
    event.preventDefault();
    show(item.dataset.page);
  });
});

const modal=document.getElementById('modal');
const drop=modal?.querySelector('.drop');
const processing=modal?.querySelector('.processing');
const openModal=()=>modal?.classList.remove('hidden');
const closeModal=()=>modal?.classList.add('hidden');

document.getElementById('upload')?.addEventListener('click',openModal);
document.getElementById('upload2')?.addEventListener('click',openModal);
document.getElementById('close')?.addEventListener('click',closeModal);
modal?.querySelector('.backdrop')?.addEventListener('click',closeModal);

drop?.addEventListener('click',()=>{
  drop.classList.add('hidden');
  processing?.classList.remove('hidden');
  setTimeout(()=>{
    if(!processing)return;
    const title=processing.querySelector('b');
    const detail=processing.querySelector('small');
    if(title)title.textContent='Invoices ready for review';
    if(detail)detail.textContent='3 documents processed successfully. Open Invoices to review them.';
  },1300);
});

const drawer=document.getElementById('drawer');
const openDrawer=()=>drawer?.classList.remove('hidden');
const closeDrawer=()=>drawer?.classList.add('hidden');

document.querySelectorAll('[data-review="true"]').forEach(row=>row.addEventListener('click',openDrawer));
document.getElementById('drawer-close')?.addEventListener('click',closeDrawer);
drawer?.querySelector('.backdrop')?.addEventListener('click',closeDrawer);

document.getElementById('approve')?.addEventListener('click',()=>{
  const score=document.querySelector('.score');
  const note=document.querySelector('.ai-note');
  if(score)score.textContent='✓ Approved';
  if(note){note.style.background='#edf8f2';note.style.color='#4d9973';}
  const noteTitle=note?.querySelector('b');
  const noteText=note?.querySelector('small');
  if(noteTitle)noteTitle.textContent='Invoice approved';
  if(noteText)noteText.textContent='Ready to be saved to your bookkeeping records.';
});

document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){
    closeModal();
    closeDrawer();
  }
});

// Demo search interaction — presentation only until the live data service is connected.
const search=document.querySelector('.search input');
search?.addEventListener('input',()=>{
  const query=search.value.trim().toLowerCase();
  document.querySelectorAll('#invoices .invoice-row.clickable').forEach(row=>{
    row.style.display=!query||row.textContent.toLowerCase().includes(query)?'':'none';
  });
});

show('overview');