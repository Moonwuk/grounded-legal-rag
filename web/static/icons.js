"use strict";
// Small inline vectors, with the action name retained for assistive technology.
(() => {
  const paths = {
    copy: 'M9 8h10v13H9zM15 8V3H4v13h5',
    check: 'm5 12 4 4L19 6',
    share: 'M12 15V3m-4 4 4-4 4 4M5 12v8h14v-8',
    print: 'M7 8V3h10v5M7 17H4V9h16v8h-3M7 14h10v7H7zM17 11h.01',
    edit: 'm4 16 11-11 4 4L8 20H4zm10-10 4 4',
    trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
    pin: 'm9 3 6 0-1 6 4 4v2H6v-2l4-4zM12 15v6',
    star: 'm12 3 2.8 5.7 6.3.9-4.6 4.5 1.1 6.3-5.6-3-5.6 3 1.1-6.3L3 9.6l6.2-.9z',
    close: 'm6 6 12 12M6 18 18 6',
    refresh: 'M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6',
    folder: 'M3 6h7l2 3h9v11H3z',
    branch: 'M7 4v16M7 14c7 0 10-4 10-10m-3 3 3-3 3 3',
    note: 'M5 3h14v18H5zM8 8h8M8 12h8M8 16h5',
    template: 'M4 4h16v5H4zM4 13h7v7H4zM15 13h5M15 17h5M15 21h3',
    restore: 'M4 4v6h6M4 10a8 8 0 1 1 0 5',
    up: 'm6 14 6-6 6 6',
    down: 'm6 10 6 6 6-6'
  };
  function set(node, name, label, compact = true) {
    if (!node || !paths[name]) return;
    const text = label || node.textContent.trim();
    const accessible = label || node.getAttribute('aria-label') || text;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path'); path.setAttribute('d', paths[name]); svg.append(path);
    const caption = document.createElement('span'); caption.className = 'icon-label'; caption.textContent = text;
    node.replaceChildren(svg, caption); node.classList.add('with-icon');
    node.classList.toggle('icon-only', compact); node.dataset.icon = name;
    node.setAttribute('aria-label', accessible); node.title = accessible;
  }
  function staticButtons() {
    const actions = {'print-dialogue': 'print', 'print-document': 'print', 'refresh-doc-tabs': 'refresh',
      'document-prev': 'up', 'document-next': 'down', 'close-appearance': 'close', 'close-copy': 'close'};
    for (const [id, icon] of Object.entries(actions)) set(document.getElementById(id), icon);
    for (const node of document.querySelectorAll('[data-close]')) set(node, 'close');
  }
  window.WebIcons = {set};
  document.addEventListener('DOMContentLoaded', staticButtons);
})();
