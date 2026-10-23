(() => {
  const t = text => window.ModuLearnI18n?.t(text) || text;
  const $ = id => document.getElementById(id);
  const initial = JSON.parse($('initialGradePolicy').textContent);
  const inputs = {mode: $('gradeMode'), points: $('gradePoints'), target: $('gradeTarget'), missing_deduction: $('gradeMissing')};
  Object.entries(inputs).forEach(([key, input]) => { input.value = initial[key] ?? ''; });
  document.querySelectorAll('[data-grade-unit]').forEach(row => {
    const settings = initial.units[row.dataset.gradeUnit];
    if (settings) row.querySelectorAll('[data-field]').forEach(input => { input.value = settings[input.dataset.field] ?? ''; });
  });
  let rows = [], timer, revision = 0, saving = false;
  const status = $('gradeStatus');
  function addGroup(group={unit_ids:[],deduction:0}) {
    const row=document.createElement('div'); row.className='grade-group';
    const label=document.createElement('label'); label.textContent=t('Units (select one or more)');
    const select=document.createElement('select'); select.multiple=true; select.required=true; select.size=3;
    document.querySelectorAll('[data-grade-unit]').forEach(unit=>{
      const option=document.createElement('option');option.value=unit.dataset.gradeUnit;
      option.textContent=unit.querySelector('th').childNodes[0].textContent;
      option.selected=group.unit_ids.includes(option.value);select.append(option);
    });
    label.append(select);
    const amountLabel=document.createElement('label');amountLabel.textContent=t('Deduct once');
    const input=document.createElement('input');input.type='number';input.min=0;input.step='any';input.required=true;input.value=group.deduction;amountLabel.append(input);
    const remove=document.createElement('button');remove.type='button';remove.className='btn btn-sm btn-outline-secondary';remove.textContent=t('Remove requirement');
    remove.addEventListener('click',()=>{row.remove();$('gradeControls').dispatchEvent(new Event('input'));});
    row.append(label,amountLabel,remove);$('gradeGroups').append(row);
  }
  (initial.groups || []).forEach(addGroup);
  $('addGradeGroup').addEventListener('click',()=>{ addGroup(); status.textContent=t('Preview · unsaved changes'); $('gradeGroups').lastElementChild.querySelector('select').focus(); });
  function syncMode() {
    const disabled = inputs.mode.value !== 'units';
    inputs.target.disabled = disabled;
    document.querySelectorAll('[data-field=weight],[data-field=target]').forEach(input => { input.disabled = disabled; });
  }
  syncMode();
  const policy = () => {
    const result = Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.value]));
    result.missing_deduction = result.missing_deduction || 0;
    result.target = result.target || 100;
    result.units = {};
    result.groups = [...document.querySelectorAll('.grade-group')].map(row=>({
      unit_ids:[...row.querySelector('select').selectedOptions].map(option=>option.value),
      deduction:row.querySelector('input').value,
    }));
    document.querySelectorAll('[data-grade-unit]').forEach(row => {
      result.units[row.dataset.gradeUnit] = Object.fromEntries([...row.querySelectorAll('[data-field]')].map(input => [input.dataset.field, input.value || (input.dataset.field === 'target' ? null : 0)]));
    });
    return result;
  };
  const number = value => Number(value).toLocaleString(undefined, {maximumFractionDigits:2});
  function render() {
    const body = $('gradeRows'); body.replaceChildren();
    const term = $('gradeSearch').value.toLocaleLowerCase();
    for (const row of rows.filter(row => `${row.name} ${row.username}`.toLocaleLowerCase().includes(term))) {
      const tr = document.createElement('tr');
      const cell = (text, className='') => { const td=document.createElement('td'); td.textContent=text; td.className=className; tr.append(td); return td; };
      const name=cell(row.name), username=document.createElement('small'); username.textContent=row.username; name.append(username);
      const progress=cell(`${row.completed}/${row.total} · ${number(row.progress)}%`);
      const meter=document.createElement('progress'); meter.max=100; meter.value=row.progress; meter.setAttribute('aria-label', t('Graded completion')); progress.prepend(meter);
      cell(`${number(row.base)}%`);
      cell(number(row.deduction));
      cell(inputs.points.value ? `${number(row.earned)} / ${number(row.maximum)} (${number(row.grade)}%)` : `${number(row.grade)}%`, 'grade-value');
      body.append(tr);
    }
    if (!body.children.length) { const tr=document.createElement('tr'), td=document.createElement('td'); td.colSpan=5; td.textContent=t('No students match.'); tr.append(td); body.append(tr); }
  }
  async function update(save=false, initialLoad=false) {
    if (!$('gradeControls').reportValidity()) { status.textContent=t('Enter valid grading settings to update the preview.'); return; }
    const current=++revision;
    if(save) { saving=true; $('saveGrades').disabled=true; $('gradeControls').inert=true; }
    status.textContent=t(save?'Saving…':'Updating preview…');
    try {
      const response=await fetch(location.href,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({policy:policy(),save})});
      const data=await response.json(); if(!response.ok) throw new Error(data.error || t('Could not update grades.'));
      if(current!==revision) return;
      rows=data.rows; render(); status.textContent=t(save?'Saved.':initialLoad?'Saved rules':'Preview · unsaved changes');
    } catch(error) { if(current===revision) status.textContent=error.message; }
    finally { if(save) { saving=false; $('saveGrades').disabled=false; $('gradeControls').inert=false; } }
  }
  $('gradeControls').addEventListener('submit',event=>event.preventDefault());
  $('gradeControls').addEventListener('input',()=>{ if(saving) return; syncMode(); ++revision; clearTimeout(timer); timer=setTimeout(()=>update(),300); });
  $('saveGrades').addEventListener('click',()=>{ clearTimeout(timer); update(true); });
  $('gradeSearch').addEventListener('input',render);
  update(false,true);
})();
