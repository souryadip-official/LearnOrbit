/* Settings page actions. Kept separate from Jinja so one template-rendering
   issue cannot prevent all of the page's click handlers from registering. */
document.addEventListener('DOMContentLoaded', () => {
  const page = document.getElementById('settings-page');
  if (!page) return;

  const providerButtons = [...document.querySelectorAll('.provider-btn')];
  const modelSelect = document.getElementById('model-select');
  const saveButton = document.getElementById('save-ai-btn');
  const keyInput = document.getElementById('api-key-input');
  const keyBadge = document.getElementById('key-status');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  let selectedProvider = page.dataset.currentProvider || 'openai';
  let modelLoadVersion = 0;
  const keyValues = new Map([[selectedProvider, keyInput.value]]);
  const dirtyKeys = new Set();

  keyInput.addEventListener('input', () => {
    keyValues.set(selectedProvider, keyInput.value);
    dirtyKeys.add(selectedProvider);
    keyBadge.textContent = keyInput.value ? 'Unsaved' : 'Not set';
  });

  async function refreshKeyStatus(provider) {
    if (dirtyKeys.has(provider)) {
      keyBadge.textContent = keyValues.get(provider) ? 'Unsaved' : 'Not set';
      return;
    }
    keyBadge.textContent = 'Checking...';
    try {
      const status = await requestJson(`/api/provider-key-status/${encodeURIComponent(provider)}`);
      if (provider === selectedProvider && !dirtyKeys.has(provider)) {
        keyBadge.textContent = status.has_key ? 'Saved' : 'Not set';
      }
    } catch {
      if (provider === selectedProvider) keyBadge.textContent = 'Key status unavailable';
    }
  }

  function modelsFor(button) {
    try { return JSON.parse(button.dataset.models || '[]'); }
    catch { return []; }
  }

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    let body;
    try { body = await response.json(); }
    catch { throw new Error(`Server returned an unreadable response (${response.status}).`); }
    if (!response.ok) throw new Error(body.message || body.error || `Request failed (${response.status}).`);
    return body;
  }

  async function loadModels(provider, fallbackModels, preferredModel = '') {
    const version = ++modelLoadVersion;
    modelSelect.disabled = true;
    saveButton.disabled = true;
    modelSelect.innerHTML = '<option value="">Loading models...</option>';

    let models = fallbackModels;
    try {
      if (provider === 'huggingface') {
        const result = await requestJson('/api/huggingface-models');
        if (Array.isArray(result.models) && result.models.length) models = result.models;
      } else {
        const catalog = await requestJson('/api/providers');
        const providerModels = catalog[provider]?.models;
        if (Array.isArray(providerModels) && providerModels.length) models = providerModels;
      }
    } catch (error) {
      console.warn(`Could not load models for ${provider}:`, error);
    }

    if (version !== modelLoadVersion) return;
    modelSelect.replaceChildren(...models.map(model => {
      const option = document.createElement('option');
      option.value = model;
      option.textContent = model;
      return option;
    }));
    if (models.includes(preferredModel)) modelSelect.value = preferredModel;
    modelSelect.disabled = models.length === 0;
    saveButton.disabled = modelSelect.disabled;
    if (!models.length) {
      modelSelect.innerHTML = '<option value="">No models are configured for this provider.</option>';
      showToast(`No models are configured for ${provider}.`, 'error');
    }
  }

  providerButtons.forEach(button => {
    button.addEventListener('click', () => {
      keyValues.set(selectedProvider, keyInput.value);
      providerButtons.forEach(item => item.classList.remove('active'));
      button.classList.add('active');
      selectedProvider = button.dataset.provider;
      keyInput.value = keyValues.get(selectedProvider) || '';
      refreshKeyStatus(selectedProvider);
      loadModels(selectedProvider, modelsFor(button));
    });
  });

  if (selectedProvider === 'huggingface') {
    const active = providerButtons.find(button => button.dataset.provider === selectedProvider);
    loadModels(selectedProvider, active ? modelsFor(active) : [], page.dataset.savedModel || '');
  }

  document.getElementById('validate-key-btn').addEventListener('click', async event => {
    const button = event.currentTarget;
    const result = document.getElementById('validate-result');
    const model = modelSelect.value;
    if (!model) {
      result.textContent = 'Choose a model after the list finishes loading.';
      result.style.color = '#ef4444';
      return;
    }
    button.disabled = true;
    result.textContent = 'Validating...';
    try {
      const data = await requestJson('/api/validate-key', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({
          provider: selectedProvider,
          model,
          api_key: keyInput.value.trim(),
        }),
      });
      result.textContent = data.message || 'Validation completed.';
      result.style.color = data.valid ? '#10b981' : '#ef4444';
    } catch (error) {
      result.textContent = `Could not validate key: ${error.message}`;
      result.style.color = '#ef4444';
    } finally {
      button.disabled = false;
    }
  });

  saveButton.addEventListener('click', async () => {
    const model = modelSelect.value;
    if (!model) {
      showToast('Wait for the model list to load, then choose a model.', 'warning');
      return;
    }
    saveButton.disabled = true;
    try {
      const data = await requestJson('/auth/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
        body: JSON.stringify({
          ai_provider: selectedProvider,
          ai_model: model,
          api_key: keyInput.value.trim(),
        }),
      });
      showToast(data.message || 'AI settings saved.', 'success');
      keyValues.set(selectedProvider, keyInput.value);
      dirtyKeys.delete(selectedProvider);
      if (keyInput.value.trim()) keyBadge.textContent = 'Saved';
      else refreshKeyStatus(selectedProvider);
      page.dataset.currentProvider = selectedProvider;
      page.dataset.savedModel = model;
    } catch (error) {
      showToast(`Could not save settings: ${error.message}`, 'error');
    } finally {
      saveButton.disabled = false;
    }
  });

  document.querySelectorAll('.theme-option').forEach(button => {
    button.addEventListener('click', async () => {
      const theme = button.dataset.theme;
      button.disabled = true;
      try {
        const data = await requestJson('/api/theme', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
          body: JSON.stringify({theme}),
        });
        document.querySelectorAll('.theme-option').forEach(item =>
          item.classList.toggle('active', item.dataset.theme === data.theme));
        document.documentElement.setAttribute('data-theme', data.theme);
        document.querySelectorAll('#theme-icon,#theme-icon-top').forEach(icon => {
          window.setLucideIcon?.(icon, data.theme === 'dark' ? 'sun' : 'moon');
        });
        window.refreshIcons?.();
        showToast(`${data.theme === 'dark' ? 'Dark' : 'Light'} mode activated.`, 'success');
      } catch (error) {
        showToast(`Could not save theme: ${error.message}`, 'error');
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelector('.input-eye')?.addEventListener('click', event => {
    const button = event.currentTarget;
    const input = document.getElementById(button.dataset.target);
    input.type = input.type === 'password' ? 'text' : 'password';
    button.setAttribute('aria-label', input.type === 'password' ? 'Show API key' : 'Hide API key');
    button.innerHTML = `<i data-lucide="${input.type === 'password' ? 'eye' : 'eye-off'}" aria-hidden="true"></i><span>${input.type === 'password' ? 'Show' : 'Hide'}</span>`;
    window.refreshIcons?.();
  });
});
