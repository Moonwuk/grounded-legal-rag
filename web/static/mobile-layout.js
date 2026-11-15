"use strict";

// Reuse the same panels in native modal dialogs: focus trapping and inert background
// are supplied by the browser, while desktop keeps its original three columns.
(() => {
  const mobile = matchMedia("(max-width: 900px)");
  const get = id => document.getElementById(id);
  const dialog = get("mobile-panel");
  const host = get("mobile-panel-content");
  const input = get("question");
  const desktopPlaceholder = input.placeholder;
  let active = null;
  let placeholder = null;
  let opener = null;
  function restore() {
    if (active && placeholder) placeholder.replaceWith(active);
    active = placeholder = null;
    if (opener?.isConnected && mobile.matches) opener.focus({preventScroll: true});
    opener = null;
  }
  function close(kind) {
    if (typeof kind === "string" && dialog.dataset.panel !== kind) return;
    if (!dialog.open) return;
    dialog.close();
    restore();
  }
  function open(kind) {
    if (!mobile.matches) return;
    const panel = get(kind === "history" ? "history-panel" : "documents-panel");
    if (active === panel) return;
    close();
    opener = document.activeElement;
    input.blur();
    placeholder = document.createComment("mobile panel position");
    panel.before(placeholder);
    active = panel;
    host.append(panel);
    get("mobile-panel-title").textContent = kind === "history" ? "История чатов" : "Документы";
    dialog.dataset.panel = kind;
    dialog.showModal();
    get("close-mobile-panel").focus({preventScroll: true});
  }
  get("open-history").addEventListener("click", () => open("history"));
  get("open-documents").addEventListener("click", () => open("documents"));
  get("close-mobile-panel").addEventListener("click", close);
  dialog.addEventListener("close", () => { if (!dialog.open) restore(); });
  dialog.addEventListener("click", event => { if (event.target === dialog) close(); });
  function resizeInput() {
    input.placeholder = mobile.matches ? "Спросите по документам…" : desktopPlaceholder;
    if (!mobile.matches) { input.style.height = ""; return; }
    input.style.height = "0px";
    input.style.height = Math.min(128, Math.max(44, input.scrollHeight)) + "px";
  }
  function viewport() {
    const visual = window.visualViewport;
    // Keep zoom available; only follow keyboard/browser chrome at normal scale.
    if (visual && visual.scale === 1) {
      document.documentElement.style.setProperty("--mobile-height", visual.height + "px");
      document.documentElement.style.setProperty("--mobile-top", visual.offsetTop + "px");
    }
  }
  input.addEventListener("input", resizeInput);
  window.visualViewport?.addEventListener("resize", viewport);
  window.visualViewport?.addEventListener("scroll", viewport);
  mobile.addEventListener("change", () => { close(); resizeInput(); viewport(); });
  window.addEventListener("resize", viewport);
  viewport();
  resizeInput();
  window.MobileLayout = {open, close, resizeInput, isMobile: () => mobile.matches};
})();
