/* Shared study-site theme. This script only changes presentation and preference. */
(() => {
  'use strict';
  const root = document.documentElement, key = 'snu-homebound-theme-v1';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let saved = null;
  const valid = value => value === 'light' || value === 'dark';
  try { const value = localStorage.getItem(key); if (valid(value)) saved = value; } catch {}
  function apply(theme) {
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#141515' : '#19398a');
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.setAttribute('aria-checked', String(theme === 'dark'));
      button.title = theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환';
      const label = button.querySelector('.theme-label');
      if (label) label.textContent = theme === 'dark' ? '다크 모드' : '라이트 모드';
    });
    document.querySelectorAll('[data-theme-choice]').forEach(input => { input.checked = input.value === (saved || 'system'); });
  }
  function set(preference) {
    saved = valid(preference) ? preference : null;
    let persisted = true;
    try { if (saved) localStorage.setItem(key, saved); else localStorage.removeItem(key); } catch { persisted = false; }
    apply(saved || (system.matches ? 'dark' : 'light'));
    return persisted;
  }
  window.RouteTheme = Object.freeze({ set, preference: () => saved || 'system' });
  apply(saved || (system.matches ? 'dark' : 'light'));
  document.addEventListener('DOMContentLoaded', () => apply(root.dataset.theme));
  document.addEventListener('click', event => {
    if (!event.target.closest?.('[data-theme-toggle]')) return;
    set(root.dataset.theme === 'dark' ? 'light' : 'dark');
  });
  document.addEventListener('change', event => {
    if (!event.target.matches?.('[data-theme-choice]')) return;
    const persisted = set(event.target.value);
    const status = document.getElementById('settings-status');
    if (status) status.textContent = persisted ? '화면 모드를 저장했습니다.' : '기기에 저장할 수 없어 이번 화면에만 적용합니다.';
  });
  system.addEventListener('change', () => { if (!saved) apply(system.matches ? 'dark' : 'light'); });
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    saved = valid(event.newValue) ? event.newValue : null;
    apply(saved || (system.matches ? 'dark' : 'light'));
  });
})();
