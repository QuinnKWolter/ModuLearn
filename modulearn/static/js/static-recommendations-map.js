(() => {
  const source = document.getElementById('rec-visualization');
  if (!source) return;
  const data = JSON.parse(source.textContent);
  const select = document.getElementById('recQuery');
  const binding = document.getElementById('recBindingNode');
  const map = document.getElementById('recMap');
  const el = (tag, text, css) => { const node=document.createElement(tag); node.textContent=text||''; if(css)node.className=css; return node; };
  const code = (key) => {
    const details=el('details'); details.append(el('summary','Activity code'),el('pre',data.code[key]||'No code supplied.')); return details;
  };
  const match = key => data.resolved[key] ? `Matched: ${data.resolved[key].unit} / ${data.resolved[key].title}` : 'Unmatched — excluded from student delivery';
  const preview = key => {
    const link=el('a','Preview activity ↗','btn btn-outline-secondary btn-sm mt-2');
    link.href=data.resolved[key].preview_url;link.target='_blank';link.rel='noopener noreferrer';return link;
  };
  const sorted=Object.entries(data.nodes).sort((a,b)=>a[1].title.localeCompare(b[1].title));
  const queries=new Set(data.edges.map(e=>e.source));
  sorted.forEach(([key,node])=>{
    const label=`${node.title} · ${node.provider} · ${node.topic || 'topic unspecified'}`;
    binding.add(new Option(label,key));
    if(queries.has(key))select.add(new Option(label,key));
  });
  function render() {
    const key=select.value, node=data.nodes[key];
    if(!node)return;
    const origin=el('div','', 'rec-source');origin.append(el('h3',node.title),el('p',match(key)),code(key));
    if(data.resolved[key])origin.append(preview(key));
    const groups=el('div','', 'rec-groups');
    const edges=data.edges.filter(e=>e.source===key);
    [...new Set(edges.map(e=>e.provider))].forEach(provider=>{
      const group=el('section','', 'rec-group');group.append(el('h3',provider));
      edges.filter(e=>e.provider===provider).sort((a,b)=>a.rank-b.rank).forEach(edge=>{
        const target=data.nodes[edge.target], card=el('article','', 'rec-target');
        card.append(el('h4',`#${edge.rank} ${target.title}`),el('p',`Cosine similarity: ${edge.similarity.toFixed(4)}`));
        const meter=el('meter','', 'rec-score');meter.min=-1;meter.max=1;meter.value=edge.similarity;meter.setAttribute('aria-label','Cosine similarity');card.append(meter,el('p',match(edge.target)));
        const shared=node.clusters.filter(k=>target.clusters.includes(k));
        const details=el('details');details.append(el('summary',`Shared clusters (${shared.length})`));
        shared.forEach(k=>{const medoid=data.medoids[k]||{};details.append(el('p',`KC ${k}: ${medoid.normalized_pattern||'Pattern not supplied'}`),el('pre',medoid.subtree_code||medoid.raw_pattern||''));});
        card.append(details,code(edge.target));if(data.resolved[edge.target])card.append(preview(edge.target));group.append(card);
      });groups.append(group);
    });
    map.replaceChildren(origin,el('div','↓ Recommended practice by activity type', 'rec-arrow'),groups);
    binding.value=key; syncBinding();
  }
  function syncBinding(){document.querySelector('[name=module]').value=String(data.resolved[binding.value]?.id||0);}
  select.addEventListener('change',render);binding.addEventListener('change',syncBinding);render();
})();
