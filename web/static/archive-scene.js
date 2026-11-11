/* Filing-cabinet scenes use API status, never the mere presence of citations. */
"use strict";

const ArchiveScene = (() => {
  const refusals = new Set(["insufficient", "out_of_scope", "disallowed", "unverified"]);

  function stateFor(answer) {
    if (answer.status === "technical_error") return "error";
    if (refusals.has(answer.status)) return "refused";
    if (answer.status === "partial") return "partial";
    if (answer.status === "clarify") return "clarify";
    return answer.status === "answer" && Array.isArray(answer.sources) && answer.sources.length
      ? "found" : "neutral";
  }

  function create(state = "searching") {
    const scene = document.createElement("div");
    scene.className = "archive-scene";
    scene.dataset.state = state;
    scene.setAttribute("aria-hidden", "true");
    const frame = document.createElement("span");
    frame.className = "archive-scene__frame";
    scene.append(frame);
    return scene;
  }

  return {create, stateFor};
})();
