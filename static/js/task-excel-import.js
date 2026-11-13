(() => {
  const dialog = document.getElementById('excel-import-dialog');
  const content = document.getElementById('excel-dialog-content');
  if (!dialog || !content) return;
  const opener = document.getElementById('open-excel-dialog');
  let busy = false;
  const decorate = () => {
    dialog.classList.toggle('excel-dialog--preview', !!content.querySelector('[data-stage="preview"]'));
    initPreview();
    content.querySelector('#excel-dialog-title')?.focus({preventScroll:true});
  };
  const request = async (url, options = {}) => {
    const response = await fetch(url, {...options, headers: {'X-Requested-With': 'XMLHttpRequest'}});
    if (!response.ok) throw new Error('加载失败，请检查网络后重试。');
    if (new URL(response.url).pathname.includes('/login/')) {
      window.location.assign(response.url);
      return;
    }
    if (response.headers.get('content-type')?.includes('application/json')) {
      window.location.assign((await response.json()).redirect);
      return;
    }
    content.innerHTML = await response.text();
    decorate();
  };
  opener?.addEventListener('click', async () => {
    dialog.showModal();
    if (content.querySelector('.excel-import')) return;
    content.innerHTML = '<div class="excel-loading" role="status">正在加载导入窗口…</div>';
    try { await request(opener.dataset.url); }
    catch (error) { content.innerHTML = '<div class="excel-loading" role="alert">加载失败，请关闭后重新打开。<button type="button" class="button button--secondary" data-excel-close>关闭</button></div>'; }
  });
  dialog.addEventListener('close', () => {
    if (dialog.dataset.closeUrl) window.location.assign(dialog.dataset.closeUrl);
  });
  dialog.addEventListener('click', event => {
    if (event.target.closest('[data-excel-close]')) dialog.close();
  });
  content.addEventListener('change', event => {
    if (event.target.type === 'file') {
      content.querySelector('[data-selected-file]').textContent = event.target.files[0]?.name || '尚未选择文件';
    }
  });
  content.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const form = event.target;
    const data = new FormData(form);
    if (event.submitter?.name) data.set(event.submitter.name, event.submitter.value);
    const button = event.submitter;
    const label = button?.innerHTML;
    busy = true;
    if (button) { button.disabled = true; button.textContent = '正在处理…'; }
    content.querySelector('[data-request-error]')?.remove();
    try { await request(form.getAttribute('action'), {method:'POST', body:data}); }
    catch (error) {
      const message = document.createElement('p');
      message.className = 'excel-error';
      message.dataset.requestError = 'true';
      message.setAttribute('role', 'alert');
      message.textContent = '请求未完成，请重试；系统会重新校验并跳过重复记录。';
      form.prepend(message);
    } finally {
      busy = false;
      if (button?.isConnected) { button.disabled = false; button.innerHTML = label; }
    }
  });
  function initPreview() {
  const form = document.getElementById('excel-preview-form');
  if (!form) return;
  const rows = [...form.querySelectorAll('[data-excel-row]')];
  const confirm = document.getElementById('excel-confirm');
  form.addEventListener('input', event => {
    if (event.target.matches('[data-delete]')) {
      const row = event.target.closest('[data-excel-row]');
      const deleted = event.target.checked;
      row.classList.toggle('is-deleted', deleted);
      row.querySelectorAll('details input, details textarea, details select').forEach(field => { field.disabled = deleted; });
    }
    const remaining = rows.filter(row => !row.querySelector('[data-delete]').checked).length;
    document.getElementById('excel-row-count').textContent = remaining;
    document.getElementById('excel-change-note').textContent = '预览已修改，校验统计需要更新。可重新校验，或确认导入时由系统校验当前内容。';
    confirm.disabled = !remaining;
  });
  // Open invalid collapsed fields before the browser focuses them.
  form.addEventListener('invalid', event => {
    const details = event.target.closest('details');
    if (details) details.open = true;
  }, true);
  }
  decorate();
  if (dialog.hasAttribute('data-auto-open')) dialog.showModal();
})();
