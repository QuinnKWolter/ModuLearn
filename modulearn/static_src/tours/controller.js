import {driver} from 'driver.js';
import 'driver.js/dist/driver.css';
import './tour.css';
import {definitions} from './definitions';

const t = (message, params) => window.ModuLearnI18n.t(message, params);
const registry = definitions(t);
let active = null;
const escape = text => { const node = document.createElement('span'); node.textContent = text; return node.innerHTML; };
const key = (panel, tour) => `modulearn.guide.${panel.dataset.guideUser}.${panel.dataset.guide}.${tour.version}`;
function stored(panel, tour) { try { return JSON.parse(localStorage.getItem(key(panel, tour)) || 'null'); } catch { return null; } }
function save(panel, tour, value) { try { localStorage.setItem(key(panel, tour), JSON.stringify(value)); } catch { /* Private browsing still permits tours. */ } }
const visible = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
const frame = () => new Promise(resolve => requestAnimationFrame(resolve));

async function start(panel, {reset = false, opener} = {}) {
  const tour = registry[panel.dataset.guide];
  if (!tour || document.body.classList.contains('study-shell')) return;
  active?.destroy();
  const steps = tour.steps.filter(step => document.querySelector(step.target) || !step.optional);
  let index = 0, cancelled = false, completed = false, moving = false;
  let modal = null, openedDetails = [];
  const initialScroll = {left: scrollX, top: scrollY};
  const previous = stored(panel, tour);
  if (!reset && previous?.status === 'paused') {
    const found = steps.findIndex(step => step.id === previous.step);
    if (found >= 0) index = found;
  }
  function cleanStep() {
    if (modal) { window.bootstrap.Modal.getOrCreateInstance(modal).hide(); modal = null; }
    openedDetails.reverse().forEach(element => { if (element.isConnected) element.open = false; });
    openedDetails = [];
  }
  function cleanup() {
    if (cancelled) return;
    cancelled = true; cleanStep(); active = null;
    save(panel, tour, {status: completed ? 'completed' : 'paused', step: steps[index]?.id});
    document.removeEventListener('keydown', keyboard, true);
    document.removeEventListener('click', blockWrite, true);
    document.removeEventListener('submit', blockWrite, true);
    document.removeEventListener('focusin', keepFocus, true);
    window.scrollTo({...initialScroll, behavior: 'instant'});
    opener?.focus({preventScroll: true});
  }
  function close() { controller.destroy(); cleanup(); }
  const controller = driver({
    animate: !matchMedia('(prefers-reduced-motion: reduce)').matches,
    smoothScroll: false, allowClose: true, allowKeyboardControl: false,
    disableActiveInteraction: true, overlayClickBehavior: 'none',
    popoverClass: 'modulearn-tour', showProgress: true,
    nextBtnText: t('Next'), prevBtnText: t('Back'), doneBtnText: t('Done'), closeBtnLabel: t('Close guide'),
    // Driver replaces its own tokens after our locale lookup; no user data is HTML.
    progressText: t('{current} of {total}', {current: '{{current}}', total: '{{total}}'}),
    steps: steps.map(step => ({element: step.target, popover: {title: escape(step.title), description: escape(step.description)}})),
    onNextClick: () => {
      if (moving) return;
      if (index === steps.length - 1) { completed = true; close(); }
      else go(index + 1);
    },
    onPrevClick: () => { if (!moving && index > 0) go(index - 1); },
    onCloseClick: close,
    onPopoverRender: popover => {
      popover.wrapper.setAttribute('data-no-ui-translate', '');
      popover.wrapper.setAttribute('aria-modal', 'true');
    },
    onDestroyed: cleanup,
  });
  function blockWrite(event) {
    if (!event.target.closest('.driver-popover')) { event.preventDefault(); event.stopImmediatePropagation(); }
  }
  function keepFocus(event) {
    if (!moving && active && !event.target.closest('.driver-popover')) document.querySelector('.driver-popover-next-btn')?.focus();
  }
  function keyboard(event) {
    if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); close(); }
    else if (!event.target.closest('.driver-popover') && event.key !== 'Tab') { event.preventDefault(); event.stopImmediatePropagation(); }
  }
  async function go(next) {
    moving = true; cleanStep(); index = next;
    const step = steps[index];
    if (step.modal) {
      const element = document.getElementById(step.modal);
      if (element && !visible(element)) { modal = element; window.bootstrap.Modal.getOrCreateInstance(element).show(); }
    }
    let element = document.querySelector(step.target);
    if (step.details && element) {
      for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        if (parent.tagName === 'DETAILS' && !parent.open) { openedDetails.push(parent); parent.open = true; }
      }
    }
    await frame(); await frame();
    if (cancelled) return;
    element = document.querySelector(step.target);
    // A missing/hidden target gets a centered explanation, never a broken pointer.
    controller.setConfig({...controller.getConfig(), steps: steps.map((item, i) => ({element: i === index ? (visible(element) ? element : undefined) : item.target,
      popover: {title: escape(item.title), description: escape(item.description)}}))});
    controller.drive(index); moving = false;
    save(panel, tour, {status: 'paused', step: step.id});
  }
  active = controller;
  document.addEventListener('keydown', keyboard, true);
  document.addEventListener('click', blockWrite, true);
  document.addEventListener('submit', blockWrite, true);
  document.addEventListener('focusin', keepFocus, true);
  try { await go(index); } catch (error) { close(); throw error; }
}
window.ModuLearnTours = {
  start,
  hasProgress(panel) { const tour = registry[panel.dataset.guide]; return tour && stored(panel, tour)?.status === 'paused'; },
};
