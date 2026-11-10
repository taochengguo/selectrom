(() => {
  const feedback = document.getElementById('user-feedback');
  const notify = (message, error = false) => {
    feedback.textContent = message;
    feedback.hidden = false;
    feedback.classList.toggle('is-error', error);
  };
  const errorsText = data => Object.values(data.errors || {}).flat().join('；');
  async function submit(form) {
    const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'Accept': 'application/json'}});
    if (response.redirected) throw new Error('登录已过期，请刷新页面后重试');
    const data = await response.json();
    if (!response.ok) throw new Error(errorsText(data) || '保存失败，请稍后重试');
    return data;
  }
  document.querySelectorAll('.user-role-form').forEach(form => {
    const select = form.elements.role;
    select.addEventListener('change', async () => {
      const pending = submit(form);
      select.disabled = true;
      try {
        const data = await pending;
        select.dataset.savedRole = data.role;
        notify(data.message);
      } catch (error) {
        select.value = select.dataset.savedRole;
        notify(error.message, true);
      } finally { select.disabled = false; }
    });
  });
  const drawer = document.getElementById('password-drawer');
  const form = document.getElementById('password-drawer-form');
  const errors = document.getElementById('password-drawer-errors');
  let trigger;
  document.querySelectorAll('[data-password-url]').forEach(button => {
    button.addEventListener('click', () => {
      trigger = button;
      form.reset();
      errors.hidden = true;
      form.action = button.dataset.passwordUrl;
      document.getElementById('password-user-name').textContent = button.dataset.fullName;
      document.getElementById('password-user-account').textContent = '修改该用户的登录密码';
      drawer.showModal();
      document.getElementById('drawer-password1').focus();
    });
  });
  const close = () => drawer.close();
  drawer.querySelectorAll('[data-close-password]').forEach(button => button.addEventListener('click', close));
  drawer.addEventListener('close', () => { form.reset(); if (trigger) trigger.focus(); });
  drawer.addEventListener('click', event => {
    if (event.target === drawer && event.clientX < drawer.getBoundingClientRect().left) close();
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const save = form.querySelector('[type=submit]');
    save.disabled = true;
    save.textContent = '保存中…';
    errors.hidden = true;
    try { const data = await submit(form); close(); notify(data.message); }
    catch (error) { errors.textContent = error.message; errors.hidden = false; }
    finally { save.disabled = false; save.textContent = '保存密码'; }
  });
})();

(() => {
  const drawer = document.getElementById('profile-drawer');
  const form = document.getElementById('profile-drawer-form');
  const errors = document.getElementById('profile-drawer-errors');
  let trigger;
  document.querySelectorAll('[data-profile-url]').forEach(button => {
    button.addEventListener('click', () => {
      trigger = button;
      errors.hidden = true;
      form.action = button.dataset.profileUrl;
      form.elements.username.value = button.dataset.username;
      form.elements.first_name.value = button.dataset.fullName;
      drawer.showModal();
      form.elements.username.focus();
    });
  });
  drawer.querySelectorAll('[data-close-profile]').forEach(button => button.addEventListener('click', () => drawer.close()));
  drawer.addEventListener('close', () => { form.reset(); if (trigger) trigger.focus(); });
  drawer.addEventListener('click', event => {
    if (event.target === drawer && event.clientX < drawer.getBoundingClientRect().left) drawer.close();
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const save = form.querySelector('[type=submit]');
    save.disabled = true;
    save.textContent = '保存中…';
    errors.hidden = true;
    try {
      const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'Accept': 'application/json'}});
      if (response.redirected) throw new Error('登录已过期，请刷新页面后重试');
      const data = await response.json();
      if (!response.ok) throw new Error(Object.values(data.errors || {}).flat().join('；') || '保存失败，请稍后重试');
      window.location.reload();
    } catch (error) {
      errors.textContent = error.message;
      errors.hidden = false;
      save.disabled = false;
      save.textContent = '保存信息';
    }
  });
})();
