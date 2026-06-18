// Animated counters on the homepage
document.addEventListener('DOMContentLoaded', function () {
  const nums = document.querySelectorAll('[data-count]');
  const animate = el => {
    const target = +el.getAttribute('data-count');
    const dur = 900, start = performance.now();
    const tick = now => {
      const p = Math.min((now - start) / dur, 1);
      el.textContent = Math.floor(p * target).toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) { animate(e.target); io.unobserve(e.target); } });
    }, { threshold: 0.4 });
    nums.forEach(n => io.observe(n));
  } else { nums.forEach(animate); }

  // Confirm dialogs
  document.querySelectorAll('[data-confirm]').forEach(f => {
    f.addEventListener('submit', e => { if (!confirm(f.getAttribute('data-confirm'))) e.preventDefault(); });
  });
});

// Mobile nav toggle
document.addEventListener('DOMContentLoaded', function () {
  var t = document.getElementById('navToggle'), m = document.getElementById('navMenu');
  if (t && m) {
    t.addEventListener('click', function () {
      var open = m.classList.toggle('open');
      t.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    // close menu when a link is tapped
    m.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        m.classList.remove('open');
        t.setAttribute('aria-expanded', 'false');
      });
    });
  }
});

// ---- Gallery: instant filter + search ----
document.addEventListener('DOMContentLoaded', function () {
  var grid = document.getElementById('galleryGrid');
  if (!grid) return;
  var items = Array.prototype.slice.call(grid.querySelectorAll('.gal-item'));
  var filters = document.getElementById('galleryFilters');
  var searchBox = document.getElementById('gallerySearch');
  var empty = document.getElementById('galleryEmpty');
  var activeFilter = 'all';

  function apply() {
    var q = (searchBox && searchBox.value || '').trim().toLowerCase();
    var shown = 0;
    items.forEach(function (el) {
      var okType = activeFilter === 'all' || el.getAttribute('data-type') === activeFilter;
      var okSearch = !q || (el.getAttribute('data-search') || '').indexOf(q) !== -1;
      var show = okType && okSearch;
      el.style.display = show ? '' : 'none';
      if (show) shown++;
    });
    if (empty) empty.style.display = shown ? 'none' : 'block';
  }

  if (filters) {
    filters.addEventListener('click', function (e) {
      var btn = e.target.closest('.gal-fbtn');
      if (!btn) return;
      filters.querySelectorAll('.gal-fbtn').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      activeFilter = btn.getAttribute('data-filter');
      apply();
    });
  }
  if (searchBox) searchBox.addEventListener('input', apply);
});

// ---- Lightbox for activity photos ----
document.addEventListener('DOMContentLoaded', function () {
  var pg = document.getElementById('photoGrid');
  var lb = document.getElementById('lightbox');
  if (!pg || !lb) return;
  var img = document.getElementById('lbImg');
  var cells = Array.prototype.slice.call(pg.querySelectorAll('.photo-cell'));
  var urls = cells.map(function (c) { return c.getAttribute('data-full'); });
  var idx = 0;

  function open(i) { idx = i; img.src = urls[idx]; lb.classList.add('open'); }
  function close() { lb.classList.remove('open'); img.src = ''; }
  function go(d) { idx = (idx + d + urls.length) % urls.length; img.src = urls[idx]; }

  cells.forEach(function (c, i) { c.addEventListener('click', function () { open(i); }); });
  document.getElementById('lbClose').addEventListener('click', close);
  document.getElementById('lbPrev').addEventListener('click', function (e) { e.stopPropagation(); go(-1); });
  document.getElementById('lbNext').addEventListener('click', function (e) { e.stopPropagation(); go(1); });
  lb.addEventListener('click', function (e) { if (e.target === lb) close(); });
  document.addEventListener('keydown', function (e) {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft') go(-1);
    else if (e.key === 'ArrowRight') go(1);
  });
});
