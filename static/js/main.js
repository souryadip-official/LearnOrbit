/* ============================================================
   LearnOrbit — main.js
   Global utilities: loader, toast, theme toggle, sidebar
   ============================================================ */

// ── Page loader ───────────────────────────────────────────
window.addEventListener('load', () => {
  const loader = document.getElementById('page-loader');
  if (loader) {
    setTimeout(() => loader.classList.add('hidden'), 400);
  }
});

// ── Toast notifications ───────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { success: 'circle-check', error: 'circle-x', warning: 'triangle-alert', info: 'info' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<i data-lucide="${icons[type] || 'message-circle'}" aria-hidden="true"></i><span>${message}</span>`;
  container.appendChild(toast);
  window.refreshIcons?.();

  setTimeout(() => {
    toast.style.animation = 'slideInRight .3s ease reverse';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
window.showToast = showToast;

// ── Sidebar toggle (mobile) ───────────────────────────────
function initSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const toggleBtn = document.getElementById('sidebar-toggle');
  const closeBtn = document.getElementById('sidebar-close');
  if (!sidebar) return;

  function openSidebar() {
    sidebar.classList.add('open');
    overlay.classList.add('show');
    document.body.style.overflow = 'hidden';
  }
  function closeSidebar() {
    sidebar.classList.remove('open');
    overlay.classList.remove('show');
    document.body.style.overflow = '';
  }

  toggleBtn?.addEventListener('click', openSidebar);
  closeBtn?.addEventListener('click', closeSidebar);
  overlay?.addEventListener('click', closeSidebar);
}

// ── Theme toggle ──────────────────────────────────────────
function initTheme() {
  const html = document.documentElement;

  async function setTheme(theme) {
    html.setAttribute('data-theme', theme);
    localStorage.setItem('learnorbit-theme', theme);
    ['#theme-icon', '#theme-icon-top'].forEach(sel => {
      const el = document.querySelector(sel);
      if (el) window.setLucideIcon?.(el, theme === 'dark' ? 'sun' : 'moon');
    });
    window.refreshIcons?.();
    // Persist via API if authenticated
    try {
      await fetch('/api/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRF() },
        body: JSON.stringify({ theme })
      });
    } catch (_) {}
  }

  document.querySelectorAll('#theme-toggle, #theme-toggle-top').forEach(btn => {
    btn?.addEventListener('click', () => {
      const current = html.getAttribute('data-theme') || 'light';
      setTheme(current === 'dark' ? 'light' : 'dark');
    });
  });
}

// ── CSRF helper ───────────────────────────────────────────
function getCSRF() {
  // Flask-WTF sets a cookie named csrf_token or csrftoken
  const match = document.cookie.split('; ').find(r =>
    r.startsWith('csrf_token=') || r.startsWith('csrftoken=')
  );
  if (match) return match.split('=')[1];
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta?.getAttribute('content') || '';
}
window.getCSRF = getCSRF;

window.saveGameScore = (gameId, score) => fetch('/games/score', {
  method: 'POST', keepalive: true,
  headers: {'Content-Type':'application/json','X-CSRFToken':getCSRF()},
  body: JSON.stringify({game_id:gameId, score})
}).catch(() => {});

// ── Auto-resize textareas ─────────────────────────────────
function initAutoResize() {
  document.querySelectorAll('textarea[data-autoresize]').forEach(ta => {
    ta.addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });
  });
}

// ── Keyboard shortcuts ────────────────────────────────────
function initShortcuts() {
  document.addEventListener('keydown', e => {
    // Escape closes modals
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(m => m.classList.add('hidden'));
      const splitModal = document.getElementById('split-screen-modal');
      if (splitModal && !splitModal.classList.contains('hidden')) {
        splitModal.classList.add('hidden');
      }
    }
  });
}

// ── Smooth scroll for anchor links ───────────────────────
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
      const target = document.querySelector(a.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
}

function initFloatingNav() {
  const nav = document.querySelector('.topbar');
  if (!nav) return;
  const update = () => nav.classList.toggle('scrolled', window.scrollY > 24);
  window.addEventListener('scroll', update, {passive:true});
  update();
}

// ── Active nav highlight (MathJax cleanup helper) ─────────
function renderMathInElement(el) {
  if (window.MathJax && el) {
    MathJax.typesetPromise([el]).catch(() => {});
  }
}
window.renderMathInElement = renderMathInElement;

// ── Init all ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initSidebar();
  initTheme();
  initAutoResize();
  initShortcuts();
  initSmoothScroll();
  initFloatingNav();
  const clock = document.getElementById('live-clock');
  const paintClock = () => { if (clock) clock.textContent = new Intl.DateTimeFormat([], {hour:'2-digit', minute:'2-digit'}).format(new Date()); };
  paintClock(); setInterval(paintClock, 15000);
  const musicIsland = document.getElementById('music-island');
  const player = document.getElementById('global-focus-audio');
  if (musicIsland && player) {
    const state = () => {
      musicIsland.classList.toggle('hidden', !player.src);
      const label = musicIsland.querySelector('span');
      if (label) label.textContent = player.paused ? 'Resume focus music' : 'Music playing';
      localStorage.setItem('learnorbit-music-active', String(!player.paused && !!player.src));
    };
    const restore = async () => {
      try {
        const open = indexedDB.open('learnorbit-focus-audio', 1);
        open.onupgradeneeded = () => open.result.createObjectStore('tracks');
        open.onsuccess = () => {
          const db = open.result, req = db.transaction('tracks').objectStore('tracks').get('current');
          req.onsuccess = () => {
            const file = req.result;
            if (!file) return;
            player.src = URL.createObjectURL(file);
            player.addEventListener('loadedmetadata', () => {
              const shouldResume = localStorage.getItem('learnorbit-music-active') === 'true';
              player.currentTime = Math.min(Number(localStorage.getItem('learnorbit-music-position') || 0), player.duration || 0);
              state();
              if (shouldResume) player.play().catch(state);
            }, {once:true});
          };
        };
      } catch (_) {}
    };
    player.addEventListener('play', state); player.addEventListener('pause', state);
    player.addEventListener('timeupdate', () => localStorage.setItem('learnorbit-music-position', String(player.currentTime || 0)));
    musicIsland.addEventListener('click', () => player.paused ? player.play().catch(state) : player.pause());
    restore();
  }
  if (location.pathname.startsWith('/games/') && location.pathname !== '/games/') {
    window.addEventListener('pagehide', () => fetch('/games/usage/close', {method:'POST', keepalive:true}));
  }
});
