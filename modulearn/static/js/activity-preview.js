/* One isolated preview of the current, unsaved activity. Never launches or submits it. */
(() => {
  const markdown = window.ModuLearnMarkdown;
  if (!markdown) return;
  const t = s => window.ModuLearnI18n?.t(s) || s;
  const dialog=document.createElement('dialog'); dialog.className='activity-preview';
  dialog.setAttribute('aria-labelledby','activity-preview-title');
  dialog.setAttribute('aria-describedby','activity-preview-note');
  const header=document.createElement('header'); header.className='activity-preview-header';
  const heading=document.createElement('h2'); heading.id='activity-preview-title'; heading.textContent=t('Activity Preview');
  const close=document.createElement('button'); close.type='button'; close.className='btn btn-outline-secondary btn-sm'; close.textContent=t('Close Preview');
  const note=document.createElement('p'); note.id='activity-preview-note'; note.className='activity-preview-note'; note.textContent=t('Preview only. Responses are not saved.');
  const status=document.createElement('p'); status.className='activity-preview-status'; status.setAttribute('role','status');
  const body=document.createElement('div'); body.className='activity-preview-body'; body.dataset.noUiTranslate='';
  header.append(heading,close); dialog.append(header,note,status,body); document.body.append(dialog);
  let revision=0, opener;
  close.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{revision++;body.replaceChildren();if(opener?.isConnected)opener.focus();});
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  const read=(root,selector)=>root.querySelector(selector)?.value || '';
  function collect(root) {
    const builder=root.id==='customModuleForm';
    const questions=[...root.querySelectorAll('details[data-config-question],[data-builder-question],.cfg-inline-question [data-config-question]')]
      .filter(q=>!q.querySelector('[name$="_delete"]')?.checked).map(q=>{
        const fresh=q.hasAttribute('data-builder-question');
        const field=suffix=>q.querySelector(fresh?`[data-question-${suffix}]`:`[name$="_${suffix==='type'?'question_type':suffix}"]`);
        return {
          prompt:field('prompt')?.value || '',help:read(q,fresh?'[data-question-help]':'[name$="_help_text"]'),
          type:field('type')?.value || 'short_answer',required:!!field('required')?.checked,
          options:(field('options')?.value || '').split('\n').map(s=>s.trim()).filter(Boolean),
          low:read(q,fresh?'[data-likert-min]':'[name$="_likert_min_label"]'),
          high:read(q,fresh?'[data-likert-max]':'[name$="_likert_max_label"]'),
          order:Number(q.querySelector('[name$="_order"]')?.value ?? Number.MAX_SAFE_INTEGER),
        };
      }).filter(q=>q.prompt.trim()).sort((a,b)=>a.order-b.order);
    return {
      title:read(root,builder?'[name="title"]':'[name$="_title"]'),
      description:read(root,builder?'[name="description"]':'[name$="_description"]'),
      instructions:read(root,builder?'[name="form_instructions"]':'[name$="_form_instructions"]'),
      continuation:read(root,builder?'[name="submit_button_label"]':'[name$="_form_submit_button_label"]') || t('Submit'),
      isForm:builder?read(root,'[name="module_type"]')==='form':!!root.querySelector('.cfg-form-content-panel'),questions,
    };
  }
  async function preview(root,button) {
    opener=button;const current=++revision;
    body.replaceChildren();body.hidden=true;status.hidden=false;status.textContent=t('Loading…');
    if(!dialog.open)dialog.showModal();
    dialog.scrollTop=0;
    try {
      const html=await markdown.renderActivity(collect(root));
      if(current!==revision)return;
      body.innerHTML=html;body.hidden=false;status.hidden=true;
    } catch (_) {if(current===revision)status.textContent=t('Unable to load preview. Please try again.');}
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-preview-activity]');
    if(!button)return;
    const root=button.closest('[data-module-block],#customModuleForm');
    if(root){event.preventDefault();preview(root,button);}
  });
})();
