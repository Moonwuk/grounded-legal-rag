/* Run in the head so saved preferences apply before the stylesheets paint. */
"use strict";

(() => {
  const key = "psb-appearance-v1";
  const root = document.documentElement;
  const themes = ["system", "light", "dark"];
  const accents = ["psb", "violet", "emerald", "orange", "pink", "graphite"];
  const fonts = ["Georgia", "Arial", "Inter", "Roboto", "Times New Roman"];
  const defaults = {version: 1, theme: "system", accent: "psb", font: "Arial", size: 16, animations: true};
  const scheme = matchMedia("(prefers-color-scheme: dark)");
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  let settings = {...defaults};

  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (saved?.version === defaults.version) {
      if (themes.includes(saved.theme)) settings.theme = saved.theme;
      if (accents.includes(saved.accent)) settings.accent = saved.accent;
      if (fonts.includes(saved.font)) settings.font = saved.font;
      if (Number.isInteger(saved.size) && saved.size >= 12 && saved.size <= 22) settings.size = saved.size;
      settings.animations = typeof saved.animations === "boolean" ? saved.animations : saved.reduced !== true;
    }
  } catch { /* Storage may be disabled. */ }

  function apply() {
    root.dataset.theme = settings.theme === "system" ? (scheme.matches ? "dark" : "light") : settings.theme;
    root.dataset.accent = settings.accent;
    const fallback = ["Georgia", "Times New Roman"].includes(settings.font) ? "serif" : "sans-serif";
    root.style.setProperty("--interface-font", `"${settings.font}", ${fallback}`);
    root.style.setProperty("--interface-size", `${settings.size}px`);
    const reduced = !settings.animations || motion.matches;
    if (root.dataset.motion !== (reduced ? "reduced" : "")) {
      root.dataset.motion = reduced ? "reduced" : "";
      if (reduced) {
        for (const frame of document.querySelectorAll(".archive-scene__frame")) {
          for (const animation of frame.getAnimations()) animation.cancel();
        }
      } else if (typeof ArchiveScene !== "undefined") {
        for (const scene of document.querySelectorAll('.archive-scene[data-state="searching"]')) {
          ArchiveScene.setState(scene, "searching");
        }
      }
    }
  }

  apply();
  scheme.addEventListener("change", apply);
  motion.addEventListener("change", apply);

  document.addEventListener("DOMContentLoaded", () => {
    const dialog = document.getElementById("appearance-dialog");
    const opener = document.getElementById("open-appearance");
    const form = document.getElementById("appearance-controls");
    const controls = form.elements;
    const status = document.getElementById("appearance-status");
    function reflect() {
      for (const name of ["theme", "accent", "font", "size"]) controls[name].value = settings[name];
      controls.animations.value = settings.animations ? "on" : "off";
      document.getElementById("appearance-size-value").value = `${settings.size} px`;
      document.querySelectorAll("[data-font-size]").forEach(button => {
        button.setAttribute("aria-pressed", String(Number(button.dataset.fontSize) === settings.size));
      });
    }
    function save(message = "") {
      apply();
      reflect();
      try {
        localStorage.setItem(key, JSON.stringify(settings));
        status.textContent = message;
      } catch {
        status.textContent = "Изменения действуют до закрытия страницы: браузер не сохраняет настройки.";
      }
    }
    opener.addEventListener("click", () => {
      reflect();
      dialog.showModal();
    });
    dialog.addEventListener("close", () => opener.focus());
    form.addEventListener("input", ({target}) => {
      if (target.name === "animations") settings.animations = target.value === "on";
      else if (target.name === "size") settings.size = Number(target.value);
      else if (["theme", "accent", "font"].includes(target.name)) settings[target.name] = target.value;
      else return;
      save();
    });
    form.querySelectorAll("[data-font-size]").forEach(button => {
      button.addEventListener("click", () => {
        settings.size = Number(button.dataset.fontSize);
        save();
      });
    });
    document.getElementById("reset-appearance").addEventListener("click", () => {
      settings = {...defaults};
      save("Стандартные настройки восстановлены.");
    });
    const previewButton = document.getElementById("appearance-preview-button");
    previewButton.addEventListener("click", () => {
      const source = document.getElementById("appearance-preview-source");
      source.hidden = !source.hidden;
      previewButton.setAttribute("aria-expanded", String(!source.hidden));
    });
    document.getElementById("close-appearance").addEventListener("click", () => dialog.close());
  });
})();
