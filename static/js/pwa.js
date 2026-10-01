(() => {
  if (!('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch(error => {
      console.warn('LearnOrbit offline support could not be enabled.', error);
    });
  }, {once: true});

  const buttons = [...document.querySelectorAll('[data-pwa-install]')];
  if (!buttons.length) return;
  let installPrompt = null;

  const setInstallVisible = visible => buttons.forEach(button => {
    button.classList.toggle('hidden', !visible);
  });

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    setInstallVisible(true);
  });

  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    setInstallVisible(false);
  });

  buttons.forEach(button => button.addEventListener('click', async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    const {outcome} = await installPrompt.userChoice;
    if (outcome === 'accepted') setInstallVisible(false);
    installPrompt = null;
  }));
})();
