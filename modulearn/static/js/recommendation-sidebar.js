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
  const launcher = document.getElementById('practice-launcher');
  const dialog = document.getElementById('practice-dialog');
  const toolbar = document.getElementById('practice-toolbar');
  const returnButton = document.getElementById('practice-original');
  const layout = document.getElementById('practice-layout');
  const home = document.createComment('practice-sidebar-home');
  sidebar.before(home); workspace.prepend(toolbar);
  const storageKey = 'modulearn-practice:' + sidebar.dataset.viewer + ':' + sidebar.dataset.queue;
  let presented = false;
  try { presented = sessionStorage.getItem(storageKey) === 'seen'; } catch (_) { /* Private storage may be unavailable. */ }
  let items = [], selected = null, feedbackItem = null, busy = false, visiting = false, eventQueue = Promise.resolve();
  let config = {mode:'sidebar', auto_open:true, animate:true}, panelOpen = false, closing = false;
  const canAnimate = () => config.animate && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const markPresented = () => { presented = true; try { sessionStorage.setItem(storageKey,'seen'); } catch (_) {} };
  function updateContext() {
    returnButton.disabled = !selected;
    returnButton.textContent = selected ? '← ' + t('Return') : t('Original problem');
    document.getElementById('practice-context').textContent = selected ? selected.title : t('Try optional practice when you are ready.');
    document.getElementById('practice-context').title = selected?.title || '';
  }
  function logPanel(type, reason) {
    items.forEach(item => record(item, type, reason).catch(e => error(e.message)));
  }
  function impressions() {
    if (!panelOpen) return;
    items.forEach(item => {
      if (!seen.has(item.id)) { seen.add(item.id); record(item,'impression').catch(e=>error(e.message)); }
    });
  }
  function openPanel(reason = 'launcher') {
    if (!items.length || closing || panelOpen) return;
    markPresented(); panelOpen = true; sidebar.hidden = false;
    if (config.mode === 'modal') { dialog.append(sidebar); dialog.showModal(); }
    else { home.after(sidebar); layout.classList.add('has-practice'); }
    launcher.setAttribute('aria-expanded','true');
    if (canAnimate()) sidebar.animate([{opacity:0,transform:'translateY(-6px)'},{opacity:1,transform:'none'}],{duration:180,easing:'ease-out'});
    logPanel(config.mode === 'modal' ? 'modal_open' : 'sidebar_open', reason);
    if (reason === 'launcher') logPanel('launcher_open',reason);
    impressions();
    if (reason === 'launcher') document.getElementById('practice-minimize').focus();
  }
  function hidePanel() {
    if (dialog.open) dialog.close();
    sidebar.hidden = true; home.after(sidebar); layout.classList.remove('has-practice');
    panelOpen = false; launcher.setAttribute('aria-expanded','false');
  }
  async function closePanel(reason = 'minimize') {
    if (!panelOpen || closing) return;
    closing = true; markPresented();
    logPanel(config.mode === 'modal' ? 'modal_close' : 'sidebar_close',reason);
    const surface = dialog.open ? dialog : sidebar;
    if (canAnimate()) {
      const from = surface.getBoundingClientRect(), to = launcher.getBoundingClientRect();
      const animation = surface.animate([
        {transform:'translate(0,0) scale(1)',opacity:1},
        {transform:`translate(${to.left-from.left}px,${to.top-from.top}px) scale(${to.width/Math.max(from.width,1)},${to.height/Math.max(from.height,1)})`,opacity:.15}
      ],{duration:320,easing:'cubic-bezier(.4,0,.2,1)'});
      surface.style.transformOrigin='top left';
      try { await animation.finished; } catch (_) {}
      surface.style.transformOrigin='';
    }
    hidePanel(); closing = false;
    if (!launcher.hidden && canAnimate()) launcher.animate([{transform:'scale(1)'},{transform:'scale(1.15)'},{transform:'scale(1)'}],{duration:240});
    if (reason === 'engage') frames.get(selected?.id)?.focus();
    else if (!launcher.hidden) launcher.focus();
  }
  launcher.addEventListener('click', () => panelOpen ? closePanel() : openPanel());
  document.getElementById('practice-minimize').addEventListener('click', () => closePanel());
  dialog.addEventListener('cancel', event => { event.preventDefault(); closePanel('escape'); });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const r=dialog.getBoundingClientRect();
    if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom) closePanel('backdrop');
  });
  const error = message => {
    document.getElementById('practice-error').textContent = message;
    document.getElementById('practice-panel-error').textContent = message;
  };
  function record(item, event_type, value = '') {
    if (item.preview) return Promise.resolve();
    const body=JSON.stringify({event_type,value,presentation:config.mode,event_id:crypto.randomUUID()});
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
    updateContext();
    document.getElementById('content-iframe').focus();
  }
  async function visit(item) {
    if (!item || visiting || closing) return;
    visiting = true; error('');
    try { await record(item,'visit'); } catch(e) { error(e.message); visiting = false; return; }
    if (!items.some(row => row.id === item.id)) { visiting = false; return; }
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
    updateContext();
    if(config.mode === 'modal') await closePanel('engage');
    frame.focus(); maybeFeedback(item); visiting = false;
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
  function render() {
    if (!items.length) { deactivate(); return; }
    launcher.hidden = false; toolbar.hidden = false;
    document.getElementById('module-frame-container').classList.add('practice-available');
    const ids = new Set(items.map(item=>item.id));
    buttons.forEach((button,id)=>{if(!ids.has(id)){button.remove();buttons.delete(id);frames.get(id)?.remove();frames.delete(id);}});
    list.querySelectorAll('section').forEach(group=>{if(!group.querySelector('button'))group.remove();});
    if(selected && !ids.has(selected.id)) showOriginal();
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
        const title=document.createElement('span'),status=document.createElement('span'),icon=document.createElement('span');
        title.className='practice-title';status.className='practice-score';icon.className='practice-status-icon';icon.setAttribute('aria-hidden','true');
        title.textContent=item.title;button.title=item.title;button.setAttribute('aria-label',item.title);button.append(icon,title,status);group.append(button);buttons.set(item.id,button);
        button.addEventListener('click',()=>visit(items.find(row=>row.id===item.id)));
      }
      const started = item.progress>0 || item.attempts>0;
      const state=item.preview?t('Preview'):item.is_complete?t('Completed'):started?t('In progress'):t('Not started');
      const score=item.score==null?'':new Intl.NumberFormat(window.ModuLearnLanguage||'en',{maximumFractionDigits:0}).format(item.score)+'%';
      button.dataset.state=item.is_complete?'complete':started?'started':'new';
      button.querySelector('.practice-status-icon').textContent=item.is_complete?'✓':started?'◐':'○';
      button.querySelector('.practice-score').textContent=score;
      button.querySelector('.practice-title').textContent=item.title;
      button.title=[item.title,state,score].filter(Boolean).join(' · ');
      button.setAttribute('aria-label',button.title);
      if (selected?.id===item.id) {selected=item;maybeFeedback(item);}
    }
    updateContext();
    if (!presented && config.auto_open) openPanel('automatic');
    impressions();
  }
  function deactivate() {
    if(selected) showOriginal();
    hidePanel(); launcher.hidden=true;toolbar.hidden=true;feedback.hidden=true;feedbackItem=null;
    document.getElementById('module-frame-container').classList.remove('practice-available');
    buttons.forEach(button=>button.remove());buttons.clear();list.replaceChildren();
    frames.forEach(frame=>frame.remove());frames.clear();
  }
  async function refresh() {
    if (busy || document.hidden) return;
    busy=true;
    try {
      const response=await fetch(sidebar.dataset.queue,{cache:'no-store'});
      if (!response.ok) throw new Error(t('Could not refresh recommendations. Retrying shortly.'));
      const data=await response.json();items=data.items||[];
      const next={mode:data.presentation?.mode==='modal'?'modal':'sidebar', auto_open:data.presentation?.auto_open!==false, animate:data.presentation?.animate!==false};
      if(next.mode!==config.mode && panelOpen) hidePanel();
      config=next;
      if (!data.enabled) deactivate();
      else render();
    } catch(e) {if(!launcher.hidden)error(e.message);}
    finally {busy=false;}
  }
  document.addEventListener('moduLearn:module-progress-updated',refresh);
  window.addEventListener('focus',refresh);
  refresh();setInterval(refresh,3000);
})();
