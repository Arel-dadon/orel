(function(){
  const root = document.documentElement;
  const key = 'pref-theme';
  const saved = localStorage.getItem(key);
  if(saved){ root.setAttribute('data-theme', saved); }

  const btn = document.getElementById('themeToggle');
  if(btn){
    btn.addEventListener('click', () => {
      const cur = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', cur);
      localStorage.setItem(key, cur);
    });
  }
})();
