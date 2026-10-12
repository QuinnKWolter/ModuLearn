(() => {
  const t = (message, parameters) => window.ModuLearnI18n.t(message, parameters);
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
        panel.querySelector('[role=status]').textContent=t(data.items.length?'Open the original problem to revisit its recommended practice. Practice does not count toward course completion.':'No recommendations yet. Continue with your course activities.');
        const links=data.items.map(item=>{const link=document.createElement('a');link.dataset.noUiTranslate='';link.href=item.source_url;link.textContent=item.title;const reason=document.createElement('small');reason.textContent=item.source_title?t(item.trigger==='completed'?'After completing {title}':'Practice related to {title}',{title:item.source_title}):item.reason;link.append(reason);return link;});
        panel.querySelector('.rec-student-list').replaceChildren(...links);
      }catch(_){/* Keep the current queue during a transient network failure. */}finally{loading=false;}
    }
    let timer=setInterval(refresh,5000);refresh();
    window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);
    window.addEventListener('pagehide',()=>clearInterval(timer));
    window.addEventListener('pageshow',event=>{if(event.persisted){timer=setInterval(refresh,5000);refresh();}});
  });
})();
