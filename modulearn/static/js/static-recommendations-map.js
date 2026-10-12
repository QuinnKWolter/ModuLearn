(() => {
  const t = (message, parameters) => window.ModuLearnI18n.t(message, parameters);
  const source = document.getElementById('rec-visualization');
  if (!source) return;
  const data = JSON.parse(source.textContent);
  const select = document.getElementById('recQuery');
  const binding = document.getElementById('recBindingNode');
  const map = document.getElementById('recMap');
  map.dataset.noUiTranslate = '';
  select.dataset.noUiTranslate = '';
  binding.dataset.noUiTranslate = '';
  const el = (tag, text, css) => { const node=document.createElement(tag); node.textContent=text||''; if(css)node.className=css; return node; };
  const code = (key) => {
    const details=el('details'); details.append(el('summary',t('Activity code')),el('pre',data.code[key]||t('No code supplied.'))); return details;
  };
  const match = key => data.resolved[key] ? t('Matched: {unit} / {title}', {unit:data.resolved[key].unit, title:data.resolved[key].title}) : t('Unmatched — excluded from student delivery');
  const preview = key => {
    const link=el('a',t('Preview activity ↗'),'btn btn-outline-secondary btn-sm mt-2');
    link.href=data.resolved[key].preview_url;link.target='_blank';link.rel='noopener noreferrer';return link;
  };
  const sorted=Object.entries(data.nodes).sort((a,b)=>a[1].title.localeCompare(b[1].title));
  const queries=new Set(data.edges.map(e=>e.source));
  sorted.forEach(([key,node])=>{
    const label=`${node.title} · ${node.provider} · ${node.topic || t('topic unspecified')}${node.code_variant ? ' · '+t('Code variant {id}', {id:node.code_variant}) : ''}`;
    binding.add(new Option(label,key));
    if(queries.has(key))select.add(new Option(label,key));
  });
  function render() {
    const key=select.value, node=data.nodes[key];
    if(!node)return;
    const origin=el('div','', 'rec-source');origin.append(el('h3',node.title));
    if(data.resolved[key])origin.append(preview(key));
    const groups=el('div','', 'rec-groups');
    const edges=data.edges.filter(e=>e.source===key);
    [...new Set(edges.map(e=>e.provider))].forEach(provider=>{
      const group=el('section','', 'rec-group');group.append(el('h3',t(({animatedexamples:'Animations',pcex:'Worked Examples',quizjet:'Completion Problems'})[provider]||provider)));
      edges.filter(e=>e.provider===provider).sort((a,b)=>a.rank-b.rank).forEach(edge=>{
        const target=data.nodes[edge.target], card=el('article','', 'rec-target');
        const heading=el('h4',target.title);heading.title=target.title;card.append(heading);
        if(data.resolved[edge.target])card.append(preview(edge.target));else card.append(el('p',t('Unmatched — excluded from student delivery')));
        group.append(card);
      });groups.append(group);
    });
    map.replaceChildren(origin,el('div',t('↓ Recommended practice by activity type'), 'rec-arrow'),groups);
    binding.value=key; syncBinding();
  }
  function syncBinding(){
    document.querySelector('[name=module]').value=String(data.resolved[binding.value]?.id||0);
    const key=binding.value, node=data.nodes[key];
    const content=[el('strong',node.title),el('p',match(key)),code(key)];
    if(data.resolved[key])content.push(preview(key));
    document.getElementById('recBindingPreview').replaceChildren(...content);
  }
  select.addEventListener('change',render);binding.addEventListener('change',syncBinding);render();
})();
