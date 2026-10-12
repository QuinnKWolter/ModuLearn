(() => {
  'use strict';
  const sidebar = document.getElementById('practice-sidebar');
  if (!sidebar) return;
  const t = (text, values) => window.ModuLearnI18n ? window.ModuLearnI18n.t(text, values) : text;
  const original = document.getElementById('original-activity');
  const workspace = document.getElementById('practice-workspace');
  const list = document.getElementById('practice-items');
  const feedback = document.getElementById('practice-feedback');
  const csrf = document.getElementById('module-frame-csrf').value;
  const frames = new Map(), buttons = new Map(), seen = new Set(), prompted = new Set();
  let items = [], selected = null, feedbackItem = null, busy = false, eventQueue = Promise.resolve();
  const error = message => { document.getElementById('practice-error').textContent = message; };
  function record(item, event_type, value = '') {
    const body=JSON.stringify({event_type,value,event_id:crypto.randomUUID()});
    const send=async()=>{
      for(let attempt=0;attempt<3;attempt++) {
        try {
          const response = await fetch(item.event_url, {method:'POST', keepalive:true,
            headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body});
          if(response.ok)return;
          if(response.status<500)break;
        } catch (_) { /* Retry the same event ID, without duplicate records. */ }
        await new Promise(resolve=>setTimeout(resolve,250*(attempt+1)));
      }
      throw new Error(t('Could not save this action. Please try again.'));
    };
    const pending=eventQueue.then(send,send);eventQueue=pending.catch(()=>{});return pending;
  }
  function showOriginal() {
    if (selected) record(selected, 'return_to_problem').catch(e => error(e.message));
    selected = null;
    original.hidden = false;
    frames.forEach(frame => { frame.hidden = true; });
    buttons.forEach(button => button.removeAttribute('aria-current'));
    document.querySelector('.module-frame-next-row')?.removeAttribute('hidden');
    document.getElementById('content-iframe').focus();
  }
  async function visit(item) {
    error('');
    try { await record(item,'visit'); } catch(e) { error(e.message); return; }
    selected = item;
    original.hidden = true;
    frames.forEach(frame => { frame.hidden = true; });
    buttons.forEach(button => button.removeAttribute('aria-current'));
    buttons.get(item.id).setAttribute('aria-current','true');
    let frame = frames.get(item.id);
    if (!frame) {
      frame = document.createElement('iframe'); frame.className = 'practice-frame';
      frame.title = item.title; frame.src = item.url; frame.allow = 'clipboard-write *';
      workspace.append(frame); frames.set(item.id,frame);
    }
    frame.hidden = false;
    document.querySelector('.module-frame-next-row')?.setAttribute('hidden','');
    frame.focus(); maybeFeedback(item);
  }
  function maybeFeedback(item) {
    if (!item.is_complete || item.feedback || prompted.has(item.id) || feedbackItem) return;
    prompted.add(item.id); feedbackItem = item; feedback.hidden = false;
    document.getElementById('practice-feedback-title').textContent = item.title;
    record(item,'feedback_shown').catch(e => error(e.message));
  }
  feedback.querySelectorAll('button').forEach(button => button.addEventListener('click', async () => {
    if (!feedbackItem) return;
    button.disabled = true;
    try {
      await record(feedbackItem,'feedback',button.dataset.feedback);
      feedbackItem.feedback = button.dataset.feedback;
      feedback.hidden = true; feedbackItem = null;
    } catch(e) { error(e.message); }
    finally { button.disabled = false; }
  }));
  document.getElementById('practice-original').addEventListener('click',showOriginal);
  sidebar.querySelector('details').addEventListener('toggle', () => {
    if (sidebar.hidden) return;
    items.forEach(item => record(item,sidebar.querySelector('details').open?'sidebar_open':'sidebar_close').catch(e=>error(e.message)));
  });
  function render() {
    if (!items.length) { sidebar.hidden = true; document.getElementById('practice-layout').classList.remove('has-practice'); return; }
    sidebar.hidden = false; document.getElementById('practice-layout').classList.add('has-practice');
    const labels = {animatedexamples:t('Animations'), pcex:t('Worked Examples'), quizjet:t('Completion Problems')};
    for (const item of items) {
      let button = buttons.get(item.id);
      if (!button) {
        let group = list.querySelector('[data-provider="'+item.provider+'"]');
        if (!group) {
          group = document.createElement('section');group.dataset.provider=item.provider;
          const heading=document.createElement('h3');heading.textContent=labels[item.provider] || item.provider;
          group.append(heading);list.append(group);
        }
        button=document.createElement('button');button.type='button';button.className='practice-item';
        const title=document.createElement('span'),status=document.createElement('small');
        title.textContent=item.title;button.title=item.title;button.setAttribute('aria-label',item.title);button.append(title,status);group.append(button);buttons.set(item.id,button);
        button.addEventListener('click',()=>visit(items.find(row=>row.id===item.id)));
      }
      const state=item.is_complete?t('Completed'):item.progress>0?t('In progress'):t('Not started');
      const score=item.score===null?'':new Intl.NumberFormat(window.ModuLearnLanguage||'en',{maximumFractionDigits:0}).format(item.score)+'%';
      button.querySelector('small').textContent=[state,score].filter(Boolean).join(' · ');
      if (!seen.has(item.id)) {seen.add(item.id);record(item,'impression').catch(e=>error(e.message));}
      if (selected?.id===item.id) {selected=item;maybeFeedback(item);}
    }
  }
  async function refresh() {
    if (busy || document.hidden) return;
    busy=true;
    try {
      const response=await fetch(sidebar.dataset.queue,{cache:'no-store'});
      if (!response.ok) throw new Error(t('Could not refresh recommendations. Retrying shortly.'));
      const data=await response.json();items=data.items||[];
      if (!data.enabled) {sidebar.hidden=true;document.getElementById('practice-layout').classList.remove('has-practice');if(selected)showOriginal();}
      else render();
    } catch(e) {if(!sidebar.hidden)error(e.message);}
    finally {busy=false;}
  }
  document.addEventListener('moduLearn:module-progress-updated',refresh);
  window.addEventListener('focus',refresh);
  refresh();setInterval(refresh,3000);
})();
