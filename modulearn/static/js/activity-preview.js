/* Interactive authoring preview. Native responses stay local; external launches use preview identities. */
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
  const note=document.createElement('p'); note.id='activity-preview-note'; note.className='activity-preview-note'; note.textContent=t('Preview only. ModuLearn does not save responses or progress.');
  const status=document.createElement('p'); status.className='activity-preview-status'; status.setAttribute('role','status');
  const body=document.createElement('div'); body.className='activity-preview-body'; body.dataset.noUiTranslate='';
  header.append(heading,close); dialog.append(header,note,status,body); document.body.append(dialog);
  let revision=0, opener, fileUrl;
  close.addEventListener('click',()=>dialog.close());
  function clear() { body.replaceChildren(); if(fileUrl){URL.revokeObjectURL(fileUrl);fileUrl=null;} }
  dialog.addEventListener('close',()=>{revision++;clear();if(opener?.isConnected)opener.focus();});
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
      moduleId:root.dataset.moduleId || null,
      activityType:builder?read(root,'[name="module_type"]'):root.dataset.activityType,
      contentUrl:read(root,builder?'[name="content_url"]':'[name$="_content_url"]'),
      providerId:read(root,builder?'[name="provider_id"]':'[name$="_provider_id"]'),
      protocols:read(root,builder?'[name="supported_protocols"]':'[name$="_supported_protocols"]'),
      title:read(root,builder?'[name="title"]':'[name$="_title"]'),
      description:read(root,builder?'[name="description"]':'[name$="_description"]'),
      instructions:read(root,builder?'[name="form_instructions"]':'[name$="_form_instructions"]'),
      continuation:read(root,builder?'[name="submit_button_label"]':'[name$="_form_submit_button_label"]') || t('Submit'),
      isForm:builder?read(root,'[name="module_type"]')==='form':!!root.querySelector('.cfg-form-content-panel'),questions,
    };
  }
  function wireForm() {
    const stack=body.querySelector('[data-preview-form]');
    if(!stack)return;
    const form=document.createElement('form');
    stack.replaceWith(form);form.append(stack);
    stack.querySelector('button').type='submit';
    form.querySelectorAll('[data-preview-require-choice]').forEach(group=>{
      const choices=[...group.querySelectorAll('input[type=checkbox]')];
      const validate=()=>{if(choices[0])choices[0].required=!choices.some(choice=>choice.checked);};
      group.addEventListener('change',validate);form.addEventListener('reset',()=>setTimeout(validate,0));validate();
    });
    form.addEventListener('submit',event=>{
      event.preventDefault();
      if(!form.reportValidity())return;
      form.hidden=true;
      const done=document.createElement('div');done.setAttribute('role','status');
      const message=document.createElement('p');message.textContent=t('Preview completed. No responses were saved.');
      const again=document.createElement('button');again.type='button';again.className='btn btn-outline-secondary';again.textContent=t('Restart Preview');
      again.addEventListener('click',()=>{form.reset();form.hidden=false;done.remove();form.querySelector('input,textarea,button')?.focus();});
      done.append(message,again);form.after(done);again.focus();
    });
  }
  async function preview(root,button) {
    opener=button;const current=++revision;
    clear();body.hidden=true;status.hidden=false;status.textContent=t('Loading…');
    if(!dialog.open)dialog.showModal();
    dialog.scrollTop=0;
    try {
      const html=await markdown.renderActivity(collect(root));
      if(current!==revision)return;
      body.innerHTML=html;body.hidden=false;status.hidden=true;wireForm();
      const file=root.querySelector('input[type="file"]')?.files?.[0];
      if(file && (file.type==='application/pdf' || file.type.startsWith('image/'))) {
        body.querySelector('[data-preview-missing]')?.remove();
        body.querySelectorAll('iframe').forEach(frame=>frame.remove());
        body.querySelector('[data-preview-file-link]')?.remove();
        fileUrl=URL.createObjectURL(file);
        const frame=document.createElement('iframe');frame.className='activity-preview-frame';frame.title=file.name;frame.src=fileUrl;
        const link=document.createElement('a');link.href=fileUrl;link.target='_blank';link.rel='noopener';link.textContent=t('Open In A New Window');
        body.append(frame,link);
      }
      dialog.classList.toggle('activity-preview--embedded',!!body.querySelector('iframe'));
    } catch (_) {if(current===revision)status.textContent=t('Unable to load preview. Please try again.');}
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-preview-activity]');
    if(!button)return;
    const root=button.closest('[data-module-block],#customModuleForm');
    if(root){event.preventDefault();preview(root,button);}
  });
})();
