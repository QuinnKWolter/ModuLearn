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
  const returnButton = document.getElementById('practice-original');
  const layout = document.getElementById('practice-layout');
  const home = document.createComment('practice-sidebar-home');
  sidebar.before(home);
  // Once per page visit: revisiting an activated problem introduces practice again.
  let presented = false;
  let items = [], selected = null, feedbackItem = null, busy = false, visiting = false, eventQueue = Promise.resolve();
  let config = {animate:true}, panelOpen = false, closing = false, presentation = 'sidebar';
  const canAnimate = () => config.animate && !matchMedia('(prefers-reduced-motion: reduce)').matches;
  function updateContext() {
    returnButton.hidden = !selected;
    returnButton.textContent = '← ' + t('Return');
  }
  function logPanel(type, reason) {
    items.forEach(item => record(item, type, reason).catch(e => error(e.message)));
  }
  function impressions() {
    if (!panelOpen) return;
    items.forEach(item => {
      if (item.tier !== 'recommended' && !document.getElementById('practice-similar').open) return;
      if (!seen.has(item.id)) { seen.add(item.id); record(item,'impression').catch(e=>error(e.message)); }
    });
  }
  document.getElementById('practice-similar').addEventListener('toggle', impressions);
  function openPanel(reason = 'launcher', mode = 'sidebar') {
    if (!items.length || closing || panelOpen) return;
    presented = true; presentation = mode; panelOpen = true; sidebar.hidden = false;
    if (presentation === 'modal') { dialog.append(sidebar); dialog.showModal(); }
    else { home.after(sidebar); layout.classList.add('has-practice'); }
    launcher.setAttribute('aria-expanded','true'); launcher.hidden = true;
    if (canAnimate()) sidebar.animate([{opacity:0,transform:'translateY(-6px)'},{opacity:1,transform:'none'}],{duration:180,easing:'ease-out'});
    logPanel(presentation === 'modal' ? 'modal_open' : 'sidebar_open', reason);
    if (reason === 'launcher') logPanel('launcher_open',reason);
    impressions();
    if (reason === 'launcher') document.getElementById('practice-minimize').focus();
  }
  function hidePanel() {
    if (dialog.open) dialog.close();
    sidebar.hidden = true; home.after(sidebar); layout.classList.remove('has-practice');
    panelOpen = false; launcher.setAttribute('aria-expanded','false'); launcher.hidden = !items.length;
  }
  async function closePanel(reason = 'minimize') {
    if (!panelOpen || closing) return;
    closing = true; launcher.disabled = true;
    const wasModal = dialog.open;
    logPanel(presentation === 'modal' ? 'modal_close' : 'sidebar_close',reason);
    const surface = dialog.open ? dialog : sidebar;
    if (canAnimate()) {
      launcher.hidden = false;
      const from = surface.getBoundingClientRect(), to = launcher.getBoundingClientRect();
      const animation = surface.animate([
        {transform:'translate(0,0) scale(1)',opacity:1},
        {transform:`translate(${to.left-from.left}px,${to.top-from.top}px) scale(${to.width/Math.max(from.width,1)},${to.height/Math.max(from.height,1)})`,opacity:.15}
      ],{duration:320,easing:'cubic-bezier(.4,0,.2,1)'});
      surface.style.transformOrigin='top left';
      try { await animation.finished; } catch (_) {}
      surface.style.transformOrigin='';
    }
    hidePanel(); closing = false; launcher.disabled = false;
    if (wasModal && items.length && !launcher.hidden) openPanel('modal_to_sidebar');
    else if (selected) showOriginal();
    if (!launcher.hidden && canAnimate()) launcher.animate([{transform:'scale(1)'},{transform:'scale(1.15)'},{transform:'scale(1)'}],{duration:240});
    if (reason === 'engage') frames.get(selected?.id)?.focus();
    else if (wasModal && panelOpen) document.getElementById('practice-minimize').focus();
    else if (!launcher.hidden) launcher.focus();
  }
  launcher.addEventListener('click', () => { if (!panelOpen) openPanel(); else document.getElementById('practice-minimize').focus(); });
  document.getElementById('practice-minimize').addEventListener('click', () => closePanel());
  dialog.addEventListener('cancel', event => { event.preventDefault(); closePanel('escape'); });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const r=dialog.getBoundingClientRect();
    if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom) closePanel('backdrop');
  });
  const error = message => {
    document.getElementById('practice-panel-error').textContent = message;
  };
  function record(item, event_type, value = '') {
    if (item.preview) return Promise.resolve();
    const body=JSON.stringify({event_type,value,presentation,event_id:crypto.randomUUID()});
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
    if(presentation === 'modal') await closePanel('engage');
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
    launcher.hidden = panelOpen;
    document.getElementById('module-frame-container').classList.add('practice-available');
    const ids = new Set(items.map(item=>item.id));
    buttons.forEach((button,id)=>{if(!ids.has(id)){button.remove();buttons.delete(id);frames.get(id)?.remove();frames.delete(id);}});
    list.querySelectorAll('[data-kind]').forEach(group=>{if(!group.querySelector('button'))group.remove();});
    if(selected && !ids.has(selected.id)) showOriginal();
    const labels = {animation:t('Animations'), worked_example:t('Worked Examples'), completion:t('Completion Problems'), tracing:t('Tracing Problems'), coding:t('Coding Problems'), other:t('Other Activities')};
    for (const item of items) {
      let button = buttons.get(item.id);
      const tier = item.tier === 'recommended' ? 'recommended' : 'similar';
      const container = document.getElementById('practice-' + tier + '-items');
      const kind = Object.hasOwn(labels, item.activity_kind) ? item.activity_kind : 'other';
      let group = container.querySelector('[data-kind="'+kind+'"]');
      if (!group) {
        group = document.createElement('section'); group.dataset.kind=kind;
        const heading=document.createElement('h4'); heading.textContent=labels[kind];
        group.append(heading); container.append(group);
      }
      if (button && button.parentElement !== group) group.append(button);
      if (!button) {
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
    list.querySelectorAll('[data-kind]').forEach(group=>{if(!group.querySelector('button'))group.remove();});
    for (const tier of ['recommended','similar']) document.getElementById('practice-'+tier).hidden = !document.getElementById('practice-'+tier+'-items').querySelector('button');
    updateContext();
    if (!presented) openPanel('automatic', 'modal');
    impressions();
  }
  function deactivate() {
    if(selected) showOriginal();
    hidePanel(); launcher.hidden=true;feedback.hidden=true;feedbackItem=null;
    document.getElementById('module-frame-container').classList.remove('practice-available');
    buttons.forEach(button=>button.remove());buttons.clear();
    list.querySelectorAll('[data-kind]').forEach(group=>group.remove());
    document.getElementById('practice-recommended').hidden=true;
    document.getElementById('practice-similar').hidden=true;
    document.getElementById('practice-similar').open=false;
    frames.forEach(frame=>frame.remove());frames.clear();
  }
  async function refresh() {
    if (busy || document.hidden) return;
    busy=true;
    try {
      const response=await fetch(sidebar.dataset.queue,{cache:'no-store'});
      if (!response.ok) throw new Error(t('Could not refresh recommendations. Retrying shortly.'));
      const data=await response.json();items=data.items||[];
      config={animate:data.presentation?.animate!==false};
      if (!data.enabled) deactivate();
      else render();
    } catch(e) {if(!launcher.hidden)error(e.message);}
    finally {busy=false;}
  }
  document.addEventListener('moduLearn:module-progress-updated',refresh);
  window.addEventListener('focus',refresh);
  refresh();setInterval(refresh,3000);
})();
