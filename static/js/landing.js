/* ============================================================
   LearnOrbit — landing.js
   Starfield canvas, scroll behavior, mobile nav
   ============================================================ */

// ── Starfield ─────────────────────────────────────────────
(function initStarfield() {
  const canvas = document.getElementById('starfield');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let stars = [], W, H;

  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function makeStars(n) {
    stars = [];
    for (let i = 0; i < n; i++) {
      stars.push({
        x: Math.random() * W,
        y: Math.random() * H,
        r: Math.random() * 1.5 + 0.3,
        speed: Math.random() * 0.3 + 0.05,
        opacity: Math.random() * 0.6 + 0.1,
        twinkle: Math.random() * Math.PI * 2,
      });
    }
  }

  function draw(ts) {
    ctx.clearRect(0, 0, W, H);
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    stars.forEach(s => {
      s.twinkle += 0.015;
      const op = s.opacity * (0.6 + 0.4 * Math.sin(s.twinkle));
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fillStyle = isDark
        ? `rgba(165,180,252,${op})`
        : `rgba(99,102,241,${op * 0.6})`;
      ctx.fill();
      s.y -= s.speed;
      if (s.y < 0) { s.y = H; s.x = Math.random() * W; }
    });
    requestAnimationFrame(draw);
  }

  resize();
  makeStars(150);
  window.addEventListener('resize', () => { resize(); makeStars(150); });
  requestAnimationFrame(draw);
})();

// ── Nav scroll effect ──────────────────────────────────────
(function initNavScroll() {
  const nav = document.getElementById('landing-nav');
  if (!nav) return;
  function onScroll() {
    if (window.scrollY > 40) nav.classList.add('scrolled');
    else nav.classList.remove('scrolled');
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

// ── Mobile nav ────────────────────────────────────────────
(function initMobileNav() {
  const btn = document.getElementById('nav-mobile-toggle');
  const nav = document.getElementById('mobile-nav');
  if (!btn || !nav) return;
  btn.addEventListener('click', () => {
    nav.classList.toggle('open');
    btn.textContent = nav.classList.contains('open') ? '✕' : '☰';
  });
  nav.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => {
      nav.classList.remove('open');
      btn.textContent = '☰';
    });
  });
})();

// ── Theme toggle on landing ───────────────────────────────
(function initLandingTheme() {
  const btn = document.getElementById('theme-btn');
  if (!btn) return;
  const html = document.documentElement;
  // Init from localStorage
  const saved = localStorage.getItem('lo-theme') || 'light';
  html.setAttribute('data-theme', saved);
  btn.textContent = saved === 'dark' ? '☀️' : '🌙';

  btn.addEventListener('click', () => {
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    btn.textContent = next === 'dark' ? '☀️' : '🌙';
    localStorage.setItem('lo-theme', next);
  });
})();

// ── Intersection observer for feature cards ───────────────
(function initReveal() {
  if (!('IntersectionObserver' in window)) return;
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.style.opacity = '1';
        e.target.style.transform = 'translateY(0)';
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.feature-card, .step-item, .pricing-card, .game-preview-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(24px)';
    el.style.transition = 'opacity .5s ease, transform .5s ease';
    obs.observe(el);
  });
})();
