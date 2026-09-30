/* ============================================================
   LearnOrbit — main.js
   Global utilities: loader, toast, theme toggle, sidebar
   ============================================================ */

// ── Page loader ───────────────────────────────────────────
window.addEventListener('load', () => {
  const loader = document.getElementById('page-loader');
  if (loader) {
    setTimeout(() => loader.classList.add('hidden'), 850);
  }
});

// ── Toast notifications ───────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { success: 'circle-check', error: 'circle-x', warning: 'triangle-alert', info: 'info' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icon = document.createElement('i');
  icon.dataset.lucide = icons[type] || 'message-circle';
  icon.setAttribute('aria-hidden', 'true');
  const text = document.createElement('span');
  text.textContent = message;
  toast.append(icon, text);
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
    document.dispatchEvent(new CustomEvent('learnorbit:themechange', {detail: {theme}}));
    ['#theme-icon', '#theme-icon-top'].forEach(sel => {
      const el = document.querySelector(sel);
      if (el) window.setLucideIcon?.(el, theme === 'dark' ? 'sun' : 'moon');
    });
    window.refreshIcons?.();
    // Persist via API if authenticated
    try {
      const response = await fetch('/api/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRF() },
        body: JSON.stringify({ theme })
      });
      if (!response.ok) throw new Error(`Theme update failed (${response.status}).`);
    } catch (error) {
      console.warn('Could not synchronize theme with the account:', error);
    }
  }

  document.querySelectorAll('#theme-toggle, #theme-toggle-top').forEach(btn => {
    btn?.addEventListener('click', () => {
      const current = html.getAttribute('data-theme') || 'light';
      setTheme(current === 'dark' ? 'light' : 'dark');
    });
  });
}

window.addEventListener('storage', event => {
  const html = document.documentElement;
  if (event.key === 'learnorbit-theme' && ['dark', 'light'].includes(event.newValue)) {
    html.dataset.theme = event.newValue;
    document.dispatchEvent(new CustomEvent('learnorbit:themechange', {detail: {theme: event.newValue}}));
    ['#theme-icon', '#theme-icon-top'].forEach(selector => {
      const icon = document.querySelector(selector);
      if (icon) window.setLucideIcon?.(icon, event.newValue === 'dark' ? 'sun' : 'moon');
    });
    window.refreshIcons?.();
  }
  if (event.key === 'learnorbit-accent' && event.newValue) html.dataset.accent = event.newValue;
});

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

function initCalendarReminders() {
  const userId = document.body.dataset.userId;
  if (!userId || !document.getElementById('sidebar')) return;
  const cursorKey = `learnorbit-calendar-reminder-cursor-${userId}`;
  const firedKey = `learnorbit-calendar-reminders-fired-${userId}`;
  async function check() {
    if (document.visibilityState === 'hidden') return;
    let since = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    let fired = [];
    try {
      since = localStorage.getItem(cursorKey) || since;
      fired = JSON.parse(localStorage.getItem(firedKey) || '[]');
      if (!Array.isArray(fired)) fired = [];
    } catch (error) {
      console.warn('Calendar reminder storage is unavailable:', error);
    }
    try {
      const query = new URLSearchParams({since});
      const response = await fetch(`/features/calendar/reminders?${query}`, {
        headers: {'X-CSRFToken': getCSRF()}
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not check calendar reminders.');
      const known = new Set(fired.map(String));
      for (const event of data.events || []) {
        if (known.has(String(event.id))) continue;
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification('LearnOrbit reminder', {body: event.title});
        } else {
          showToast(`Reminder: ${event.title}`, 'info');
        }
        known.add(String(event.id));
      }
      localStorage.setItem(firedKey, JSON.stringify(Array.from(known).slice(-100)));
      if (data.checked_at) localStorage.setItem(cursorKey, data.checked_at);
    } catch (error) {
      console.warn('Calendar reminder check failed:', error);
    }
  }
  check();
  const timer = setInterval(check, 30000);
  document.addEventListener('visibilitychange', check);
  window.addEventListener('pagehide', () => {
    clearInterval(timer);
    document.removeEventListener('visibilitychange', check);
  }, {once: true});
}

function initRecallReminders() {
  const userId = document.body.dataset.userId;
  if (!userId) return;
  const storageKey = `learnorbit-recall-reminders-seen-${userId}`;
  let checking = false;
  async function check() {
    if (checking || document.visibilityState === 'hidden') return;
    checking = true;
    try {
      const response = await fetch('/dashboard/api/recall-due', {
        headers: {'X-CSRFToken': getCSRF()}
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not check session recall tests.');
      let seen = [];
      try {
        const stored = JSON.parse(localStorage.getItem(storageKey) || '[]');
        if (Array.isArray(stored)) seen = stored.map(String);
      } catch (error) {
        console.warn('Recall reminder storage is unavailable:', error);
      }
      const seenSet = new Set(seen);
      const unseen = (data.checks || []).filter(check => {
        const key = `${check.session_id}-${check.cycle_number}`;
        if (seenSet.has(key)) return false;
        seenSet.add(key);
        return true;
      });
      if (unseen.length) {
        const names = unseen.slice(0, 2).map(check => check.topic).join(', ');
        const extra = unseen.length > 2 ? ` and ${unseen.length - 2} more` : '';
        showToast(`${unseen.length} session recall test${unseen.length === 1 ? ' is' : 's are'} due: ${names}${extra}. Open the dashboard to take them.`, 'info', 8000);
        localStorage.setItem(storageKey, JSON.stringify(Array.from(seenSet).slice(-1000)));
      }
    } catch (error) {
      console.warn('Session recall reminder check failed:', error);
    } finally {
      checking = false;
    }
  }
  check();
  const timer = setInterval(check, 60000);
  document.addEventListener('visibilitychange', check);
  window.addEventListener('pagehide', () => {
    clearInterval(timer);
    document.removeEventListener('visibilitychange', check);
  }, {once:true});
}

// ── Active nav highlight (MathJax cleanup helper) ─────────
function renderMathInElement(el) {
  if (window.MathJax && el) {
    MathJax.typesetPromise([el]).catch(() => {});
  }
}
window.renderMathInElement = renderMathInElement;

// ── Persistent-audio navigation (pjax) ────────────────────
// Swaps only the main content region for sidebar destinations so the
// global focus-music <audio> element is never torn down by a full
// page reload, letting music keep playing while the user moves
// between tabs.
function initPjaxNav() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  async function go(url, push) {
    const loader = document.getElementById('page-loader');
    const startedAt = Date.now();
    loader?.classList.remove('hidden');
    if (window.matchMedia('(max-width: 768px)').matches) {
      sidebar.classList.remove('open');
      document.getElementById('sidebar-overlay')?.classList.remove('show');
      document.body.style.overflow = '';
    }
    try {
      const res = await fetch(url, { headers: { 'X-Pjax': '1' } });
      const contentType = res.headers.get('content-type') || '';
      if (!res.ok || !contentType.includes('text/html')) { window.location.href = url; return; }
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const newMain = doc.querySelector('.main-content');
      const curMain = document.querySelector('.main-content');
      if (!newMain || !curMain) { window.location.href = url; return; }

      document.dispatchEvent(new CustomEvent('learnorbit:beforepagechange'));
      document.querySelectorAll('link[data-pjax-head]').forEach(link => link.remove());
      const pageStyles = Array.from(doc.head.querySelectorAll('link[data-pjax-head]'));
      await Promise.all(pageStyles.map(source => new Promise((resolve, reject) => {
        const link = document.createElement('link');
        Array.from(source.attributes).forEach(attribute => link.setAttribute(attribute.name, attribute.value));
        link.addEventListener('load', resolve, {once:true});
        link.addEventListener('error', () => reject(new Error(`Could not load page stylesheet ${link.href}`)), {once:true});
        document.head.appendChild(link);
        if (link.sheet) resolve();
      })));
      window.Chart?.getChart?.(document.getElementById('learning-chart'))?.destroy();
      window.Chart?.getChart?.(document.getElementById('retention-chart'))?.destroy();
      document.title = doc.title;
      curMain.replaceWith(newMain);

      const newTitle = doc.querySelector('.topbar-center');
      const curTitle = document.querySelector('.topbar-center');
      if (newTitle && curTitle) curTitle.replaceWith(newTitle);

      const newActions = doc.getElementById('topbar-actions');
      const curActions = document.getElementById('topbar-actions');
      if (newActions && curActions) curActions.replaceWith(newActions);

      const newScripts = doc.getElementById('page-scripts');
      const curScripts = document.getElementById('page-scripts');
      if (newScripts && curScripts) curScripts.replaceWith(newScripts);

      let targetPath;
      try { targetPath = new URL(url, location.href).pathname; } catch (_) { targetPath = url; }
      document.querySelectorAll('#sidebar .nav-item').forEach(a => {
        try { a.classList.toggle('active', new URL(a.href, location.href).pathname === targetPath); } catch (_) {}
      });

      if (push) history.pushState({ pjax: true }, '', url);

      // Recreate scripts in document order; page code is isolated so revisiting
      // a route cannot fail on duplicate top-level lexical declarations. Keep
      // neighboring inline scripts together so they share their page scope.
      const scripts = Array.from(document.getElementById('page-scripts')?.querySelectorAll('script') || []);
      let inlineGroup = [];
      const runInlineGroup = () => {
        if (!inlineGroup.length) return;
        const [first, ...rest] = inlineGroup;
        const runner = document.createElement('script');
        runner.textContent = `(()=>{\n${inlineGroup.map(script => script.textContent).join('\n;\n')}\n})();`;
        first.replaceWith(runner);
        rest.forEach(script => script.remove());
        inlineGroup = [];
      };
      for (const old of scripts) {
        if (!old.src) {
          inlineGroup.push(old);
          continue;
        }
        runInlineGroup();
        const fresh = document.createElement('script');
        Array.from(old.attributes).forEach(attr => fresh.setAttribute(attr.name, attr.value));
        old.replaceWith(fresh);
        if (fresh.src) {
          fresh.async = false;
          await new Promise((resolve, reject) => {
            fresh.addEventListener('load', resolve, {once: true});
            fresh.addEventListener('error', () => reject(new Error(`Could not load ${fresh.src}`)), {once: true});
          });
        }
      }
      runInlineGroup();

      window.refreshIcons?.();
      initAutoResize();
      window.scrollTo(0, 0);
      document.dispatchEvent(new CustomEvent('learnorbit:pagechange', {detail: {url}}));
    } catch (_) {
      window.location.href = url;
    } finally {
      const minimumDuration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 650;
      const remaining = minimumDuration - (Date.now() - startedAt);
      if (remaining > 0) await new Promise(resolve => setTimeout(resolve, remaining));
      loader?.classList.add('hidden');
    }
  }

  window.navigateLearnOrbit = url => go(url, true);

  sidebar.querySelectorAll('a.nav-item').forEach(a => {
    a.addEventListener('click', e => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.target === '_blank') return;
      let url;
      try { url = new URL(a.href, location.href); } catch (_) { return; }
      if (url.origin !== location.origin) return;
      if (url.pathname === location.pathname) { e.preventDefault(); return; }
      e.preventDefault();
      go(a.href, true);
    });
  });

  window.addEventListener('popstate', () => go(location.href, false));
}

// ── Init all ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initSidebar();
  initTheme();
  initAutoResize();
  initShortcuts();
  initSmoothScroll();
  initFloatingNav();
  initPjaxNav();
  initCalendarReminders();
  initRecallReminders();
  const clock = document.getElementById('live-clock');
  const paintClock = () => { if (clock) clock.textContent = new Intl.DateTimeFormat([], {hour:'2-digit', minute:'2-digit'}).format(new Date()); };
  paintClock(); setInterval(paintClock, 15000);
  const musicIsland = document.getElementById('music-island');
  const player = document.getElementById('global-focus-audio');
  if (musicIsland && player) {
    const state = (persist = true) => {
      musicIsland.classList.toggle('hidden', !player.src);
      const label = musicIsland.querySelector('span');
      if (label) label.textContent = player.paused ? 'Resume focus music' : 'Music playing';
      musicIsland.setAttribute('aria-label', player.paused ? 'Resume focus music' : 'Pause focus music');
      musicIsland.setAttribute('aria-pressed', String(!player.paused && !!player.src));
      if (persist && player.src) {
        localStorage.setItem('learnorbit-music-active', String(!player.paused));
      }
    };
    const restore = async () => {
      player.volume = Math.max(0, Math.min(1, Number(localStorage.getItem('learnorbit-music-volume') || .65)));
      try {
        const open = indexedDB.open('learnorbit-focus-audio', 1);
        open.onupgradeneeded = () => open.result.createObjectStore('tracks');
        open.onsuccess = () => {
          const db = open.result;
          const store = db.transaction('tracks').objectStore('tracks');
          const keysRequest = store.getAllKeys();
          keysRequest.onsuccess = () => {
            const activeId = localStorage.getItem('learnorbit-active-track');
            const trackId = activeId && keysRequest.result.includes(activeId)
              ? activeId
              : keysRequest.result.includes('current')
                ? 'current'
                : keysRequest.result[keysRequest.result.length - 1];
            if (trackId === undefined) { db.close(); return; }
            const trackRequest = store.get(trackId);
            trackRequest.onsuccess = () => {
              const storedTrack = trackRequest.result;
              const file = storedTrack && typeof storedTrack === 'object' && 'blob' in storedTrack
                ? storedTrack.blob
                : storedTrack;
              if (!(file instanceof Blob)) { db.close(); return; }
              const resolvedTrackId = typeof storedTrack === 'object' && storedTrack && 'id' in storedTrack
                ? String(storedTrack.id)
                : String(trackId);
              const shouldResume = localStorage.getItem('learnorbit-music-active') === 'true';
              localStorage.setItem('learnorbit-active-track', resolvedTrackId);
              const restorePosition = () => {
                player.currentTime = Math.min(Number(localStorage.getItem('learnorbit-music-position') || 0), player.duration || 0);
                state(false);
                if (shouldResume) {
                  localStorage.setItem('learnorbit-music-active', 'true');
                  player.play().catch(error => {
                    state(false);
                    localStorage.setItem('learnorbit-music-active', 'true');
                    console.info('Focus music is ready; playback needs a user gesture in this browser.', error);
                  });
                }
              };
              if (player.dataset.trackId !== resolvedTrackId) {
                player.dataset.trackId = resolvedTrackId;
                player.addEventListener('loadedmetadata', restorePosition, {once:true});
                player.src = URL.createObjectURL(file);
              } else if (player.readyState >= 1) {
                restorePosition();
              } else {
                player.addEventListener('loadedmetadata', restorePosition, {once:true});
              }
              db.close();
            };
            trackRequest.onerror = () => { console.warn('Could not restore the saved focus track.', trackRequest.error); db.close(); };
          };
          keysRequest.onerror = () => { console.warn('Could not list saved focus tracks.', keysRequest.error); db.close(); };
        };
        open.onerror = () => console.warn('Could not open saved focus tracks.', open.error);
      } catch (error) {
        console.warn('Could not restore focus music.', error);
      }
    };
    player.addEventListener('play', state); player.addEventListener('pause', state);
    player.addEventListener('timeupdate', () => localStorage.setItem('learnorbit-music-position', String(player.currentTime || 0)));
    window.addEventListener('pagehide', () => {
      if (!player.src) return;
      localStorage.setItem('learnorbit-music-position', String(player.currentTime || 0));
      localStorage.setItem('learnorbit-music-active', String(!player.paused));
    });
    musicIsland.addEventListener('click', () => player.paused ? player.play().catch(state) : player.pause());
    restore();
  }
  if (location.pathname.startsWith('/games/') && location.pathname !== '/games/') {
    window.addEventListener('pagehide', () => fetch('/games/usage/close', {method:'POST', keepalive:true}));
  }
});
