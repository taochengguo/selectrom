(() => {
  const shell = document.querySelector('.management-shell');
  const toggle = document.querySelector('.sidebar-toggle');
  if (!shell || !toggle) return;
  const key = 'selectrom.management.sidebarCollapsed';
  const apply = (collapsed) => {
    shell.classList.toggle('sidebar-collapsed', collapsed);
    toggle.setAttribute('aria-expanded', String(!collapsed));
    toggle.setAttribute('aria-label', collapsed ? '展开侧边栏' : '折叠侧边栏');
    toggle.title = collapsed ? '展开侧边栏' : '折叠侧边栏';
  };
  try { apply(localStorage.getItem(key) === 'true'); } catch { apply(false); }
  toggle.addEventListener('click', () => {
    const collapsed = !shell.classList.contains('sidebar-collapsed');
    apply(collapsed);
    try { localStorage.setItem(key, String(collapsed)); } catch { /* Storage may be unavailable. */ }
  });
})();
