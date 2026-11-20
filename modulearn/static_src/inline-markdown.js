import {EditorState, Compartment, Transaction, StateField, StateEffect} from '@codemirror/state';
import {EditorView, Decoration, WidgetType, keymap, placeholder} from '@codemirror/view';
import {defaultKeymap, history, historyKeymap, redo, indentMore, indentLess} from '@codemirror/commands';
import {markdown, insertNewlineContinueMarkupCommand, deleteMarkupBackward} from '@codemirror/lang-markdown';
import {syntaxTree, indentUnit} from '@codemirror/language';
import {GFM} from '@lezer/markdown';
import MarkdownIt from 'markdown-it';

const t = s => window.ModuLearnI18n?.t(s) || s;
const renderer = new MarkdownIt({html:false, breaks:true, linkify:true});
const validateLink = renderer.validateLink;
renderer.validateLink = url => validateLink(url) && !/^data:/i.test(url.trim());
const focusChanged = StateEffect.define();
const focused = StateField.define({create:()=>false, update:(value,tr)=> {
  for (const effect of tr.effects) if (effect.is(focusChanged)) value = effect.value;
  return value;
}});

class Bullet extends WidgetType {
  eq() { return true; }
  toDOM() { const span=document.createElement('span');span.textContent='•';span.className='cm-md-bullet';return span; }
}

class TaskBox extends WidgetType {
  constructor(checked, from) { super(); this.checked = checked; this.from = from; }
  eq(other) { return this.checked === other.checked && this.from === other.from; }
  toDOM(view) {
    // A button, not an input: it must never become part of the host form payload.
    const box = document.createElement('button'); box.type = 'button'; box.className = 'cm-md-task';
    box.setAttribute('role','checkbox'); box.setAttribute('aria-checked',String(this.checked));
    box.setAttribute('aria-label',t('Toggle checklist item')); box.textContent = this.checked ? '☑' : '☐';
    box.addEventListener('mousedown',e=>e.preventDefault());
    box.addEventListener('click', e=> {
      e.preventDefault();
      view.dispatch({changes:{from:this.from,to:this.from+3,insert:this.checked?'[ ]':'[x]'},userEvent:'input'});
    });
    return box;
  }
}

class RenderedBlock extends WidgetType {
  constructor(text, from, kind) { super(); this.text = text; this.from = from; this.kind = kind; }
  eq(other) { return this.text === other.text && this.from === other.from && this.kind === other.kind; }
  toDOM(view) {
    const inline = this.kind==='image' || this.kind==='link';
    const element = document.createElement(inline?'span':'div'); element.className = `cm-md-rendered study-prose cm-md-${this.kind}`;
    element.innerHTML = inline?renderer.renderInline(this.text):renderer.render(this.text); // Raw HTML disabled; unsafe URL schemes rejected.
    element.querySelectorAll('img').forEach(img=>{img.loading='lazy';img.addEventListener('load',()=>view.requestMeasure());});
    element.title = t('Click to edit Markdown');
    element.addEventListener('mousedown', e=>e.preventDefault());
    element.addEventListener('click', e=> {
      e.preventDefault();
      view.dispatch({selection:{anchor:this.from},scrollIntoView:true}); view.focus();
    });
    return element;
  }
}

function decorations(state) {
  const ranges = [], doc = state.doc;
  const selection = state.selection.main;
  const activeFrom = state.field(focused) ? doc.lineAt(selection.from).from : -1;
  const activeTo = state.field(focused) ? doc.lineAt(selection.to).to : -1;
  const editing = (from,to) => activeFrom >= 0 && from <= activeTo && to >= activeFrom;
  const mark = (from,to,className) => { if(to>from) ranges.push(Decoration.mark({class:className}).range(from,to)); };
  const syntax = (from,to) => { if(to>from) ranges.push((editing(from,to) ? Decoration.mark({class:'cm-md-syntax'}) : Decoration.replace({})).range(from,to)); };
  function lines(node, className) {
    for(let n=doc.lineAt(node.from).number; n<=doc.lineAt(node.to).number; n++) ranges.push(Decoration.line({class:className}).range(doc.line(n).from));
  }
  syntaxTree(state).iterate({enter(node) {
    const {name,from,to} = node;
    if (name === 'Table' || name === 'HorizontalRule') {
      if (!editing(from,to)) {
        ranges.push(Decoration.replace({widget:new RenderedBlock(doc.sliceString(from,to),from,name==='Table'?'table':'rule'),block:true}).range(from,to));
      } else lines(node, name==='Table'?'cm-md-table-source':'cm-md-syntax');
      return false;
    }
    if (name === 'Image' && !editing(from,to)) {
      ranges.push(Decoration.replace({widget:new RenderedBlock(doc.sliceString(from,to),from,'image')}).range(from,to));
      return false;
    }
    if (name === 'Link' && node.node.getChild('URL') && !editing(from,to)) {
      ranges.push(Decoration.replace({widget:new RenderedBlock(doc.sliceString(from,to),from,'link')}).range(from,to));
      return false;
    }
    if (/^(ATX|Setext)Heading/.test(name)) lines(node,`cm-md-heading cm-md-h${name.slice(-1)}`);
    if (name === 'StrongEmphasis') mark(from,to,'cm-md-bold');
    if (name === 'Emphasis') mark(from,to,'cm-md-italic');
    if (name === 'Strikethrough') mark(from,to,'cm-md-strike');
    if (name === 'InlineCode') mark(from,to,'cm-md-code');
    if (name === 'FencedCode' || name === 'CodeBlock') lines(node,'cm-md-codeblock');
    if (name === 'Blockquote') lines(node,'cm-md-quote');
    if (name === 'Link' || name === 'Autolink') mark(from,to,'cm-md-link');
    if (name === 'Image') mark(from,to,'cm-md-image');
    if (name === 'TaskMarker' && !editing(from,to)) {
      ranges.push(Decoration.replace({widget:new TaskBox(/x/i.test(doc.sliceString(from,to)),from)}).range(from,to));
      return false;
    }
    if (['EmphasisMark','StrikethroughMark','HeaderMark','CodeMark'].includes(name)) syntax(from,to);
    if (name === 'ListMark' && /^[-+*]$/.test(doc.sliceString(from,to)) && !editing(from,to)) {
      ranges.push(Decoration.replace(node.node.parent?.getChild('Task')?{}:{widget:new Bullet()}).range(from,to));
    } else if (name==='QuoteMark') syntax(from,to);
    else if (['ListMark','LinkMark'].includes(name)) mark(from,to,'cm-md-marker');
    if (name === 'CodeInfo') syntax(from,to);
  }});
  return Decoration.set(ranges,true);
}
// Block replacements must be provided by a StateField, not a viewport plugin.
const formatted = StateField.define({create:decorations, update:(_value,tr)=>decorations(tr.state), provide:field=>EditorView.decorations.from(field)});

function mount(parent, {value, label, hint, maxLength, onChange}) {
  const mode = new Compartment();
  let syncing = false;
  function format(view, kind) {
    const {from,to} = view.state.selection.main, doc = view.state.doc;
    const selected = doc.sliceString(from,to);
    const token = {bold:'**',italic:'*',strike:'~~',code:'`'}[kind];
    if (token) {
      const wrapped = selected.startsWith(token) && selected.endsWith(token) && selected.length >= token.length*2;
      const around = doc.sliceString(Math.max(0,from-token.length),from)===token && doc.sliceString(to,to+token.length)===token;
      if (around) view.dispatch({changes:[{from:from-token.length,to:from,insert:''},{from:to,to:to+token.length,insert:''}],selection:{anchor:from-token.length,head:to-token.length},userEvent:'input'});
      else view.dispatch({changes:{from,to,insert:wrapped?selected.slice(token.length,-token.length):token+selected+token},selection:{anchor:from+(wrapped?0:token.length),head:to+(wrapped?-2*token.length:token.length)},userEvent:'input'});
    } else if (['heading','bullet','ordered','task','quote'].includes(kind)) {
      const first = doc.lineAt(from), last = doc.lineAt(to>from && doc.lineAt(to).from===to ? to-1 : to);
      const changes = [];
      for(let n=first.number; n<=last.number;n++) {
        const line=doc.line(n), indent=/^\s*/.exec(line.text)[0];
        const body=line.text.slice(indent.length);
        const prefix={heading:'# ',bullet:'- ',ordered:`${n-first.number+1}. `,task:'- [ ] ',quote:'> '}[kind];
        const existing=/^(?:#{1,6}\s+|(?:[-+*]|\d+[.)])\s+(?:\[[ xX]\]\s+)?|>\s?)/.exec(body)?.[0] || '';
        const same = kind==='ordered' ? /^\d+[.)] $/.test(existing) : existing===prefix;
        changes.push({from:line.from+indent.length,to:line.from+indent.length+existing.length,insert:same?'':prefix});
      }
      const changeSet = view.state.changes(changes);
      const selection = from===to
        // An insertion at the caret otherwise maps to *before* the new marker.
        // Also move past a replacement marker when switching list types.
        ? {anchor:Math.max(changeSet.mapPos(from,1), changeSet.mapPos(changes[0].from,-1)+changes[0].insert.length)}
        : view.state.selection.map(changeSet);
      view.dispatch({changes:changeSet,selection,scrollIntoView:true,userEvent:'input'});
    } else if (kind==='indent' || kind==='outdent') {
      (kind==='indent'?indentMore:indentLess)(view);
    } else {
      const inserts = {
        table:`| ${t('Column')} 1 | ${t('Column')} 2 |\n| --- | --- |\n| ${selected || t('Text')} |  |`,
        link:`[${selected || t('Link text')}](https://)`,image:`![${selected || t('Image description')}](https://)`,
        codeblock:'```\n'+selected+'\n```',rule:'---',
      };
      if (!(kind in inserts)) return false;
      const block=['table','codeblock','rule'].includes(kind);
      const before=block && from>0?'\n\n':'', after=block?'\n\n':'';
      const insert=before+inserts[kind]+after;
      const start=from+before.length;
      let anchor, head;
      if (kind==='table') {
        // Replace the first header, not the whole table, when typing next.
        anchor=start+2; head=anchor+`${t('Column')} 1`.length;
      } else if (kind==='codeblock') {
        anchor=start+4; head=anchor+selected.length;
      } else if (kind==='rule') {
        anchor=head=from+insert.length;
      } else {
        const label=selected || t(kind==='image'?'Image description':'Link text');
        const labelStart=start+(kind==='image'?2:1);
        // Selected text already supplies the label; the destination is next.
        anchor=selected?labelStart+label.length+2:labelStart;
        head=anchor+(selected?'https://'.length:label.length);
      }
      view.dispatch({changes:{from,to,insert},selection:{anchor,head},scrollIntoView:true,userEvent:'input'});
    }
    view.focus(); return true;
  }
  const continueList=insertNewlineContinueMarkupCommand({nonTightLists:false});
  const view = new EditorView({parent,state:EditorState.create({doc:value,extensions:[
    history(), EditorView.lineWrapping, placeholder(hint || ''),
    markdown({extensions:GFM,addKeymap:false,completeHTMLTags:false}), indentUnit.of('    '),
    focused, mode.of(formatted),
    EditorView.domEventHandlers({focus:(_e,v)=>{v.dispatch({effects:focusChanged.of(true)});},blur:(_e,v)=>{v.dispatch({effects:focusChanged.of(false)});}}),
    EditorView.contentAttributes.of({'aria-label':label,'aria-multiline':'true',spellcheck:'true'}),
    keymap.of([
      {key:'Enter',run:continueList},{key:'Backspace',run:deleteMarkupBackward},
      // Tab retains normal focus navigation. Indentation also has visible toolbar controls.
      {key:'Mod-]',run:indentMore},{key:'Mod-[',run:indentLess},
      {key:'Mod-b',run:v=>format(v,'bold')},{key:'Mod-i',run:v=>format(v,'italic')},
      {key:'Mod-Shift-z',run:redo,preventDefault:true},...defaultKeymap,...historyKeymap,
    ]),
    EditorState.transactionFilter.of(tr=>!syncing && tr.docChanged && maxLength>0 && tr.newDoc.length>maxLength && tr.newDoc.length>tr.startState.doc.length?[]:tr),
    EditorView.updateListener.of(update=>{if(update.docChanged&&!syncing)onChange(update.state.doc.toString());}),
  ]})});
  return {
    focus:()=>view.focus(),format:kind=>format(view,kind),
    source(enabled) {view.dispatch({effects:mode.reconfigure(enabled?[]:formatted)});parent.classList.toggle('is-markdown-source',enabled);},
    sync(value) {
      if(view.state.doc.toString()===value)return;
      syncing=true;
      view.dispatch({changes:{from:0,to:view.state.doc.length,insert:value},annotations:Transaction.addToHistory.of(false)});
      syncing=false;
    },
    invalid(message) {view.contentDOM.setAttribute('aria-invalid',String(Boolean(message)));},
    destroy:()=>view.destroy(),
  };
}
window.ModuLearnInlineMarkdown = {mount};
