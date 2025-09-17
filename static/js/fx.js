(function(){
  const cvs = document.createElement('canvas');
  cvs.id = 'fx-canvas';
  Object.assign(cvs.style,{position:'fixed',inset:0,pointerEvents:'none',zIndex:9999,display:'none'});
  document.addEventListener('DOMContentLoaded',()=>document.body.appendChild(cvs));
  const ctx = cvs.getContext('2d');
  function resize(){ cvs.width = innerWidth; cvs.height = innerHeight; }
  addEventListener('resize', resize); resize();

  let raf, parts=[];
  function beep(){
    try{
      const AC = window.AudioContext||window.webkitAudioContext;
      const ac = (beep._ac ||= new AC());
      const o = ac.createOscillator();
      const g = ac.createGain();
      o.type='triangle'; o.frequency.value=880;
      g.gain.setValueAtTime(0.12, ac.currentTime);
      g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime+0.15);
      o.connect(g).connect(ac.destination); o.start(); o.stop(ac.currentTime+0.16);
    }catch{}
  }
  function haptic(){ try{ navigator.vibrate && navigator.vibrate(40) }catch{} }
  function col(){ const H=[200,330,45,150,260]; const h=H[(Math.random()*H.length)|0]; return `hsl(${h} 90% ${60+Math.random()*20}%)`; }

  function emit(n=160){
    parts.length=0;
    for(let i=0;i<n;i++){
      parts.push({
        x: innerWidth/2 + (Math.random()-0.5)*120,
        y: innerHeight/2,
        vx:(Math.random()-0.5)*7,
        vy:(Math.random()-0.5)*6-6,
        g:0.18+Math.random()*0.05,
        w:4+Math.random()*6,
        h:10+Math.random()*10,
        a:Math.random()*Math.PI,
        va:(Math.random()-0.5)*0.3,
        c:col()
      });
    }
  }
  function loop(){
    ctx.clearRect(0,0,cvs.width,cvs.height);
    for(const p of parts){
      p.vy+=p.g; p.x+=p.vx; p.y+=p.vy; p.a+=p.va;
      ctx.save(); ctx.translate(p.x,p.y); ctx.rotate(p.a);
      ctx.fillStyle=p.c; ctx.fillRect(-p.w/2,-p.h/2,p.w,p.h); ctx.restore();
    }
    if(parts.every(p=>p.y>cvs.height+40)){ cvs.style.display='none'; cancelAnimationFrame(raf); return; }
    raf = requestAnimationFrame(loop);
  }
  window.celebrate = function(){
    beep(); haptic(); cvs.style.display='block'; emit(); loop();
  };
})();
