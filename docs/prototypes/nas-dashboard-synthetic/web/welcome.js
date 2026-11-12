// Decorative welcome only. Never waits for data or changes navigation.
export function startWelcome(cover, schedule = globalThis.setTimeout, skip, main) {
  if (!cover) return;
  const finish = () => {
    if (cover.hidden) return;
    cover.hidden = true;
    if (skip && skip.ownerDocument.activeElement === skip) main?.focus({preventScroll:true});
  };
  skip?.addEventListener('click', finish);
  schedule(finish, 1000);
}
if (typeof document !== 'undefined') {
  const start = () => startWelcome(document.getElementById('welcome-cover'), globalThis.setTimeout, document.getElementById('welcome-skip'), document.getElementById('main'));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
}
