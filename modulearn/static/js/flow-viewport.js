/* Canvas navigation only: moving the viewport never changes activity order or rules. */
(() => {
  function mount({modal, shell, map, redraw}) {
    const abort=new AbortController(), on=(el,type,fn,options={})=>el?.addEventListener(type,fn,{...options,signal:abort.signal});
    const saved=modal.__flowView || {scale:1,left:0,top:0};
    let scale=saved.scale, dragging=null, space=false, frame=0;
    const stage=document.createElement('div');stage.className='cfg-flow-stage';
    map.before(stage);stage.append(map);
    const output=modal.querySelector('[data-flow-zoom-level]');
    const remember=()=>{modal.__flowView={scale,left:shell.scrollLeft,top:shell.scrollTop};};
    function size() {
      if(!shell.clientWidth)return;
      stage.style.width=`${map.offsetWidth*scale}px`;stage.style.height=`${map.offsetHeight*scale}px`;
      map.style.transform=`scale(${scale})`;
      output.textContent=`${Math.round(scale*100)}%`;
      shell.dataset.zoom=String(scale);
    }
    function zoom(value, x=shell.clientWidth/2, y=shell.clientHeight/2) {
      const old=scale, worldX=(shell.scrollLeft+x)/old, worldY=(shell.scrollTop+y)/old;
      scale=Math.min(2,Math.max(.15,value));size();
      shell.scrollLeft=worldX*scale-x;shell.scrollTop=worldY*scale-y;remember();redraw();
    }
    function fit() {
      if(!shell.clientWidth)return;
      zoom(Math.min(1,(shell.clientWidth-24)/map.offsetWidth,(shell.clientHeight-24)/map.offsetHeight));
      shell.scrollLeft=0;shell.scrollTop=0;remember();
    }
    function focus(nodes) {
      if(!nodes.length)return;
      const rect=map.getBoundingClientRect(), boxes=nodes.map(n=>n.getBoundingClientRect());
      const left=Math.min(...boxes.map(b=>(b.left-rect.left)/scale)), right=Math.max(...boxes.map(b=>(b.right-rect.left)/scale));
      const top=Math.min(...boxes.map(b=>(b.top-rect.top)/scale)), bottom=Math.max(...boxes.map(b=>(b.bottom-rect.top)/scale));
      zoom(Math.min(1.2,Math.max(.3,Math.min((shell.clientWidth-64)/(right-left),(shell.clientHeight-64)/(bottom-top)))));
      shell.scrollLeft=(left+right)*scale/2-shell.clientWidth/2;shell.scrollTop=(top+bottom)*scale/2-shell.clientHeight/2;remember();
    }
    on(modal.querySelector('[data-flow-zoom-in]'),'click',()=>zoom(scale*1.2));
    on(modal.querySelector('[data-flow-zoom-out]'),'click',()=>zoom(scale/1.2));
    on(modal.querySelector('[data-flow-fit]'),'click',fit);
    on(modal.querySelector('[data-flow-reset]'),'click',()=>zoom(1));
    on(modal.querySelector('[data-flow-focus-view]'),'click',()=>focus([...map.querySelectorAll('.is-source,.is-target,.is-related')]));
    on(shell,'wheel',event=>{
      if(!event.ctrlKey&&!event.metaKey)return;
      event.preventDefault();const r=shell.getBoundingClientRect();
      zoom(scale*Math.exp(-event.deltaY*.008),event.clientX-r.left,event.clientY-r.top);
    },{passive:false});
    on(shell,'pointerdown',event=>{
      if(event.button!==0&&event.button!==1)return;
      if(!space&&event.button!==1&&event.target.closest('button,input,select,a,[data-flow-line]'))return;
      if(event.pointerType==='touch')return; // Native touch scrolling retains its inertia.
      event.preventDefault();shell.focus({preventScroll:true});shell.setPointerCapture(event.pointerId);
      dragging={id:event.pointerId,x:event.clientX,y:event.clientY,left:shell.scrollLeft,top:shell.scrollTop};
      shell.classList.add('is-panning');
    });
    on(shell,'pointermove',event=>{
      if(!dragging)return;
      shell.scrollLeft=dragging.left+dragging.x-event.clientX;shell.scrollTop=dragging.top+dragging.y-event.clientY;
    });
    const stop=()=>{dragging=null;shell.classList.remove('is-panning');remember();};
    on(shell,'pointerup',stop);on(shell,'pointercancel',stop);on(shell,'lostpointercapture',stop);
    on(shell,'scroll',remember,{passive:true});
    on(shell,'keydown',event=>{
      if(event.target.closest('input,select,textarea'))return;
      if(event.code==='Space'){space=true;if(event.target===shell)event.preventDefault();}
      if(event.target!==shell)return;
      if(['+','=','-','0','f','F'].includes(event.key)){
        event.preventDefault();if(event.key==='0')zoom(1);else if(event.key.toLowerCase()==='f')fit();else zoom(scale*(event.key==='-'?1/1.2:1.2));
      }
    });
    on(shell,'keyup',event=>{if(event.code==='Space')space=false;});on(shell,'blur',()=>{space=false;});
    const resize=new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{size();redraw();});});
    resize.observe(shell);resize.observe(map);
    const show=()=>{const current=modal.__flowView || saved;scale=current.scale;size();shell.scrollLeft=current.left;shell.scrollTop=current.top;redraw();};
    on(modal,'shown.bs.modal',show);show();
    let previousFocus;
    on(modal,'show.bs.modal',()=>{previousFocus=document.activeElement;});
    on(modal,'shown.bs.modal',()=>modal.querySelector('[data-flow-search]')?.focus({preventScroll:true}));
    on(modal,'hidden.bs.modal',()=>{space=false;previousFocus?.focus?.({preventScroll:true});});
    on(modal,'keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();window.bootstrap?.Modal.getOrCreateInstance(modal).hide();}
      if(event.key!=='Tab')return;
      const items=[...modal.querySelectorAll('button,input,select,summary,a[href],[tabindex="0"]')].filter(e=>!e.disabled&&e.getClientRects().length);
      const first=items[0],last=items.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    });
    return {get scale(){return scale;},fit,focus,destroy(){if(shell.isConnected)remember();abort.abort();resize.disconnect();cancelAnimationFrame(frame);stage.before(map);stage.remove();map.style.transform='';}};
  }
  window.ModuLearnFlowViewport={mount};
})();
