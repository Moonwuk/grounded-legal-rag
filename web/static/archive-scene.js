/* Sprite sheets and separate images share one stepped timeline. */
"use strict";

const SpriteAnimation = (() => {
  const running = new WeakMap();

  function stop(frame) {
    running.get(frame)?.cancel();
    running.delete(frame);
  }

  function play(frame, {src, images, columns = 1, rows = 1, frames, fps = 30, loop = false}) {
    stop(frame);
    const count = images ? images.length : columns * rows;
    const sequence = frames ?? Array.from({length: count}, (_, index) => index);
    const position = (index, size) => size > 1 ? 100 * index / (size - 1) : 0;
    const cssUrl = url => `url("${url}")`;
    const pose = index => images
      ? {backgroundImage: cssUrl(images[index]), backgroundPosition: "center"}
      : {backgroundPosition: `${position(index % columns, columns)}% ${position(Math.floor(index / columns), rows)}%`};
    if (!sequence.length || !Number.isFinite(fps) || fps <= 0 ||
        sequence.some(index => !Number.isInteger(index) || index < 0 || index >= count)) {
      throw new RangeError("Invalid sprite sequence");
    }
    const finalPose = pose(loop ? sequence[0] : sequence.at(-1));
    frame.style.backgroundSize = images ? "contain" : `${columns * 100}% ${rows * 100}%`;
    if (!images) frame.style.backgroundImage = cssUrl(src);
    Object.assign(frame.style, finalPose);
    const finish = () => frame.dispatchEvent(new CustomEvent("spriteend", {bubbles: true}));
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || sequence.length === 1) {
      if (!loop) finish();
      return;
    }
    const poses = sequence.map(pose);
    const motion = frame.animate([...poses, finalPose], {
      duration: 1000 * sequence.length / fps,
      easing: `steps(${sequence.length}, end)`,
      iterations: loop ? Infinity : 1,
      fill: "none"
    });
    running.set(frame, motion);
    if (!loop) motion.onfinish = () => {
      if (running.get(frame) !== motion) return;
      running.delete(frame);
      finish();
    };
  }

  return {play, stop};
})();

const ArchiveScene = (() => {
  const blue = "/static/media/archive-blue.webp";
  const found = "/static/media/archive-found.webp";
  const outcomes = "/static/media/archive-outcomes.webp";
  const range = (start, end) => Array.from({length: end - start + 1}, (_, i) => start + i);
  const scenes = {
    idle: {src: blue, frames: [0]},
    searching: {src: blue, frames: [...range(0, 24), ...range(1, 23).reverse()], loop: true},
    success: {src: found, frames: range(15, 24)},
    partial: {src: found, frames: [20]},
    clarify: {images: ["/static/media/archive-clarify.webp"]},
    search_error: {src: outcomes, frames: range(18, 29)},
    role_protection: {src: blue, frames: [7, 8, 9, 7]},
    out_of_scope: {src: outcomes, frames: [18, 19, 20]},
    unsafe_legal_request: {src: blue, frames: range(20, 29)},
    system_error: {src: outcomes, frames: [20, 21, 22]},
    unverified: {src: outcomes, frames: [20, 21]}
  };
  const symbols = {role_protection: "!", out_of_scope: "?", unsafe_legal_request: "⊘", system_error: "!"};

  function stateFor(answer) {
    if (answer.status === "technical_error") return "system_error";
    if (answer.ui_state === "role_protection" && ["disallowed", "out_of_scope"].includes(answer.status))
      return "role_protection";
    switch (answer.status) {
      case "insufficient": return "search_error";
      case "out_of_scope": return "out_of_scope";
      case "disallowed": return "unsafe_legal_request";
      case "unverified": return "unverified";
      case "partial": return "partial";
      case "clarify": return "clarify";
      case "answer": return answer.sources?.length ? "success" : "idle";
      default: return "idle";
    }
  }

  function setState(scene, state) {
    scene.dataset.state = state;
    const [frame, badge] = scene.children;
    badge.textContent = symbols[state] || "";
    SpriteAnimation.play(frame, {columns: 6, rows: 5, ...scenes[state]});
  }

  function create(state = "searching") {
    const scene = document.createElement("div");
    scene.className = "archive-scene";
    scene.setAttribute("aria-hidden", "true");
    const frame = document.createElement("span");
    frame.className = "archive-scene__frame";
    const badge = document.createElement("span");
    badge.className = "archive-scene__badge";
    scene.append(frame, badge);
    setState(scene, state);
    return scene;
  }

  return {create, setState, stateFor, stop: scene => SpriteAnimation.stop(scene.children[0])};
})();
