(() => {
  const panels=[...document.querySelectorAll('[data-recommendations-url]')];
  panels.forEach(panel=>{
    if(panel.dataset.bound)return;panel.dataset.bound='1';
    let loading=false,last='';
    async function refresh(){
      if(loading || document.hidden)return;loading=true;
      try{
        const response=await fetch(panel.dataset.recommendationsUrl,{headers:{Accept:'application/json'},cache:'no-store'});
        if(!response.ok){if(response.status===403){panel.hidden=true;clearInterval(timer);}return;}
        const data=await response.json();panel.hidden=!data.enabled;
        if(!data.enabled)return;
        const encoded=JSON.stringify(data.items);if(last===encoded)return;last=encoded;
        panel.querySelector('[role=status]').textContent=data.items.length?'Suggested from your recent work. Completed activities leave this list automatically.':'No recommendations yet. Continue with your course activities.';
        const links=data.items.map(item=>{const link=document.createElement('a');link.href=item.url;link.textContent=item.title;const reason=document.createElement('small');reason.textContent=item.reason;link.append(reason);return link;});
        panel.querySelector('.rec-student-list').replaceChildren(...links);
      }catch(_){/* Keep the current queue during a transient network failure. */}finally{loading=false;}
    }
    let timer=setInterval(refresh,5000);refresh();
    window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);
    window.addEventListener('pagehide',()=>clearInterval(timer));
    window.addEventListener('pageshow',event=>{if(event.persisted){timer=setInterval(refresh,5000);refresh();}});
  });
})();
