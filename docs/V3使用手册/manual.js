'use strict';
(() => {
  const chapters=[...document.querySelectorAll('.chapter')],toc=document.querySelector('#toc'),search=document.querySelector('#search'),results=document.querySelector('#search-results');
  const escape=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  chapters.forEach(section=>{const a=document.createElement('a');a.href='#'+section.id;a.textContent=section.dataset.title;toc.append(a);});
  document.querySelectorAll('table').forEach(t=>{const wrap=document.createElement('div');wrap.className='table-wrap';wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',(t.closest('section')?.querySelector('h2')?.textContent||'')+'对照表，可横向滚动');t.before(wrap);wrap.append(t);});
  const blocks=[];
  chapters.forEach(section=>{
    let current={title:section.querySelector('h2').textContent,id:section.id,chapter:section.dataset.title,text:''};blocks.push(current);
    [...section.children].forEach(el=>{
      if(el.matches('h3')){current={title:el.textContent,id:el.id,chapter:section.dataset.title,text:''};blocks.push(current);}
      else current.text+=' '+el.textContent;
    });
  });
  const sidebar=document.querySelector('.sidebar'),menu=document.querySelector('#menu');
  const closeMenu=()=>{sidebar.classList.remove('open');menu.setAttribute('aria-expanded','false');};
  menu.addEventListener('click',()=>{const open=sidebar.classList.toggle('open');menu.setAttribute('aria-expanded',String(open));if(open)search.focus();});
  const normal=s=>s.toLowerCase().replace(/\s+/g,' ').trim();
  function runSearch(){
    const query=normal(search.value),words=query.split(' ').filter(Boolean);
    results.hidden=!query;toc.hidden=!!query;
    if(!query){results.replaceChildren();return;}
    const matches=blocks.map(b=>({...b,score:words.every(w=>normal(b.title+' '+b.text).includes(w))?words.reduce((s,w)=>s+(normal(b.title).includes(w)?3:1),0):0})).filter(b=>b.score).sort((a,b)=>b.score-a.score);
    results.innerHTML='<div class="result-count">找到 '+matches.length+' 处'+(matches.length>25?'，先显示前 25 处，请缩小关键词':'')+'</div>';
    if(!matches.length)results.insertAdjacentHTML('beforeend','<p>没有匹配内容。试试更短的词，如“缓存”“删除”“原片”。</p>');
    matches.slice(0,25).forEach(b=>{
      const t=b.text.replace(/\s+/g,' ').trim(),pos=Math.max(0,normal(t).indexOf(words[0])-22),snippet=t.slice(pos,pos+105);
      const a=document.createElement('a');a.href='#'+b.id;a.innerHTML='<strong>'+escape(b.title)+'</strong><span>'+escape(b.chapter)+' · '+escape(snippet)+'…</span>';results.append(a);
    });
  }
  search.addEventListener('input',runSearch);
  document.querySelector('#clear-search').addEventListener('click',()=>{search.value='';runSearch();search.focus();});
  function revealHash(){const id=decodeURIComponent(location.hash.slice(1)),el=document.getElementById(id);if(!el)return;let p=el.closest('details');if(p)p.open=true;el.classList.remove('jump-highlight');requestAnimationFrame(()=>el.classList.add('jump-highlight'));}
  document.addEventListener('click',e=>{const a=e.target.closest('a[href^="#"]');if(!a)return;closeMenu();setTimeout(revealHash,20);});
  addEventListener('hashchange',revealHash);revealHash();
  const observer=new IntersectionObserver(entries=>{const visible=entries.filter(e=>e.isIntersecting);if(!visible.length)return;const id=visible[0].target.id;toc.querySelectorAll('a').forEach(a=>{const active=a.hash==='#'+id;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});},{rootMargin:'-5% 0px -68% 0px',threshold:0});chapters.forEach(s=>observer.observe(s));
  const dialog=document.querySelector('#image-dialog'),large=dialog.querySelector('img'),caption=dialog.querySelector('p');let imageTrigger=null;
  const closeImage=()=>dialog.close();
  document.querySelectorAll('figure img').forEach(img=>{img.tabIndex=0;img.setAttribute('role','button');img.setAttribute('aria-label','放大截图：'+img.alt);function open(){imageTrigger=img;large.src=img.src;large.alt=img.alt;caption.textContent=img.closest('figure').querySelector('figcaption').textContent;dialog.showModal();}img.addEventListener('click',open);img.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});});
  document.querySelector('#close-image').addEventListener('click',closeImage);dialog.addEventListener('click',e=>{if(e.target===dialog)closeImage();});dialog.addEventListener('close',()=>imageTrigger?.focus());
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu();if(e.key==='/'&&!/INPUT|TEXTAREA/.test(document.activeElement.tagName)&&!dialog.open){e.preventDefault();if(innerWidth<=820){sidebar.classList.add('open');menu.setAttribute('aria-expanded','true');}search.focus();}});
  let beforePrint=[];addEventListener('beforeprint',()=>{beforePrint=[...document.querySelectorAll('details')].map(d=>[d,d.open]);beforePrint.forEach(([d])=>d.open=true);});addEventListener('afterprint',()=>beforePrint.forEach(([d,o])=>d.open=o));document.querySelector('#print').addEventListener('click',()=>window.print());
})();
