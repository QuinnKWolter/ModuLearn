/* Activity histories are loaded only when expanded. No charting dependency. */
function initializeActivityTimeline(root, data, endpoint) {
  const t = text => window.ModuLearnI18n?.t(text) || text;
  root.querySelectorAll('[data-timeline-module]').forEach(panel => {
    panel.addEventListener('toggle', async () => {
      if (!panel.open || panel.dataset.loaded || panel.dataset.loading) return;
      const body = panel.querySelector('.engagement-module-body');
      panel.dataset.loading = '1'; body.textContent = t('Loading interactions…');
      try {
        const params = new URLSearchParams({instance_id: data.context.course_instance_id, learner_id: data.learner.id, module_id: panel.dataset.timelineModule});
        const response = await fetch(`${endpoint}?${params}`, {headers: {'Accept':'application/json'}});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || response.status);
        body.innerHTML = result.events.length ? result.events.map(renderEngagementEvent).join('') : escapeHtml(t('No tracked interactions for this module yet.'));
        panel.dataset.loaded = '1';
      } catch (error) {
        body.textContent = `${t('Could not load interactions. Close and expand to retry.')} ${error.message}`;
      } finally { delete panel.dataset.loading; }
    });
  });
  const host = root.querySelector('[data-activity-timeline]');
  const series = data.units.flatMap(unit => unit.modules.map(module => {
    const points = (module.timeline || []).map(p => ({x:Date.parse(p.at), y:Math.max(0,Math.min(1,p.progress))})).filter(p => Number.isFinite(p.x));
    if (module.completed_at) points.push({x:Date.parse(module.completed_at),y:1});
    points.sort((a,b) => a.x-b.x);
    return {...module, points, color:resourceColor(module.activity_type)};
  })).filter(s => s.points.length);
  if (!series.length) { host.textContent = t('No recorded progress signals yet.'); return; }
  const all = series.flatMap(s => s.points);
  const earliest = all.reduce((min,p) => Math.min(min,p.x),Infinity), latest = all.reduce((max,p) => Math.max(max,p.x),-Infinity);
  const fullSpan = Math.max(latest-earliest, 60000);
  let start = earliest-fullSpan*.02, end = latest+fullSpan*.02+ (latest===earliest ? 60000:0);
  const initial = [start,end];
  const completions = series.filter(s => s.completed_at).map(s => Date.parse(s.completed_at));
  const format = value => new Date(value).toLocaleString();
  host.className = 'activity-timeline';
  host.innerHTML = `<div class="activity-timeline-controls"><strong>${escapeHtml(t('Activity progress over time'))}</strong>
    <button type="button" data-zoom="in" aria-label="${escapeHtml(t('Zoom in'))}">+</button><button type="button" data-zoom="out" aria-label="${escapeHtml(t('Zoom out'))}">−</button>
    <button type="button" data-pan="-1" aria-label="${escapeHtml(t('Earlier'))}">←</button><button type="button" data-pan="1" aria-label="${escapeHtml(t('Later'))}">→</button>
    <button type="button" data-reset>${escapeHtml(t('Reset'))}</button></div>
    <p class="text-xs">${escapeHtml(t('Drag to pan; use +/− to zoom. Select an activity to open its interactions.'))}</p>
    ${completions.length ? `<p class="text-xs">${escapeHtml(t('First completion'))}: ${escapeHtml(format(Math.min(...completions)))} · ${escapeHtml(t('Last completion'))}: ${escapeHtml(format(Math.max(...completions)))}</p>` : ''}
    <svg viewBox="0 0 900 230" role="img" aria-label="${escapeHtml(t('Activity progress over time'))}"></svg>
    <div class="activity-timeline-legend"></div><div class="activity-timeline-activities"></div>`;
  const svg = host.querySelector('svg');
  const select = id => {
    const panel = root.querySelector(`[data-timeline-module="${id}"]`);
    if (!panel) return;
    panel.closest('[data-timeline-unit]').open = true;
    panel.open = true;
    panel.querySelector('summary').focus();
    panel.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'nearest'});
  };
  const names = [...new Set(series.map(s => s.activity_type))];
  host.querySelector('.activity-timeline-legend').innerHTML = names.map(name => `<span><span style="color:${resourceColor(name)}">●</span> ${escapeHtml(name)}</span>`).join('');
  host.querySelector('.activity-timeline-activities').innerHTML = series.map(s => `<button type="button" data-activity="${s.id}" style="--type-color:${s.color}">${escapeHtml(s.title)}</button>`).join('');
  host.querySelectorAll('[data-activity]').forEach(button => button.addEventListener('click', () => select(button.dataset.activity)));
  function draw() {
    const x = n => 50+(n-start)/(end-start)*830;
    const y = n => 190-n*160;
    svg.innerHTML = `<defs><clipPath id="activity-plot-clip"><rect x="50" y="25" width="830" height="170"/></clipPath></defs>` +
      [0,.5,1].map(n => `<line x1="50" x2="880" y1="${y(n)}" y2="${y(n)}" stroke="currentColor" opacity=".15"/><text x="5" y="${y(n)+4}">${n*100}%</text>`).join('')+
      `<text x="50" y="218">${escapeHtml(format(start))}</text><text x="880" y="218" text-anchor="end">${escapeHtml(format(end))}</text>`+
      series.map(s => `<g clip-path="url(#activity-plot-clip)" data-series="${s.id}" style="cursor:pointer"><title>${escapeHtml(s.title)}</title><polyline points="${s.points.map(p => `${x(p.x)},${y(p.y)}`).join(' ')}" fill="none" stroke="${s.color}" stroke-width="2" opacity=".75"/>${s.points.filter((p,i) => i % Math.max(1,Math.ceil(s.points.length/100)) === 0 || i === s.points.length-1).map(p => `<circle cx="${x(p.x)}" cy="${y(p.y)}" r="4" fill="${s.color}"><title>${escapeHtml(s.title)} · ${escapeHtml(format(p.x))} · ${Math.round(p.y*100)}%</title></circle>`).join('')}</g>`).join('');
  }
  function constrain() { const span=Math.min(initial[1]-initial[0],Math.max(1000,end-start)); start=Math.max(initial[0],Math.min(start,initial[1]-span));end=start+span;draw(); }
  host.querySelectorAll('[data-zoom]').forEach(b => b.addEventListener('click',()=>{const middle=(start+end)/2;const half=(end-start)*(b.dataset.zoom==='in'?.3:.85);start=middle-half;end=middle+half;constrain();}));
  host.querySelectorAll('[data-pan]').forEach(b => b.addEventListener('click',()=>{const shift=(end-start)*.3*Number(b.dataset.pan);start+=shift;end+=shift;constrain();}));
  host.querySelector('[data-reset]').addEventListener('click',()=>{[start,end]=initial;draw();});
  let drag=null, moved=false;
  svg.addEventListener('pointerdown',e=>{drag={x:e.clientX,start,end};moved=false;svg.setPointerCapture(e.pointerId);});
  svg.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x;if(Math.abs(dx)>4)moved=true;if(!moved)return;const shift=dx/svg.getBoundingClientRect().width*(drag.end-drag.start);start=drag.start-shift;end=drag.end-shift;constrain();});
  svg.addEventListener('pointerup',e=>{drag=null;if(!moved){const target=document.elementFromPoint(e.clientX,e.clientY)?.closest('[data-series]');if(target)select(target.dataset.series);}});
  svg.addEventListener('pointercancel',()=>{drag=null;});
  draw();
}
