"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.style = {};
    this.events = {}; this.value = ""; this.hidden = false; this.textContent = "";
    this.classes = new Set();
    this.classList = {add: n => this.classes.add(n), remove: n => this.classes.delete(n)};
  }
  set className(value) { this.classes = new Set(value.split(" ")); }
  get className() { return [...this.classes].join(" "); }
  append(...children) {
    for (const value of children) {
      const child = typeof value === "string" ? Object.assign(new Element("#text"), {textContent: value}) : value;
      child.remove?.(); child.parent = this; this.children.push(child);
    }
  }
  before(child) {
    child.remove?.(); child.parent = this.parent;
    this.parent.children.splice(this.parent.children.indexOf(this), 0, child);
  }
  remove() {
    if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1);
    this.parent = null;
  }
  replaceChildren(...children) { for (const c of [...this.children]) c.remove?.(); this.children = []; this.append(...children); }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, fn) { this.events[name] = fn; }
  dispatchEvent() {}
  focus() {}
  animate() { return {cancel() {}}; }
  closest() { return this; }
  querySelector(selector) {
    if (selector === ".message") return this.children.find(c => c.classes?.has("message")) || null;
    return new Element();
  }
}
function harness(saved = null) {
  const requests = [];
  const storage = new Map();
  const ids = new Map();
  const get = id => { if (!ids.has(id)) ids.set(id, new Element()); return ids.get(id); };
  get("conversation").append(get("welcome"));
  const intervals = new Set();
  let onSend, reply, reject, startCalls = 0;
  const context = vm.createContext({
    document: {getElementById: get, createElement: tag => new Element(tag), querySelectorAll: () => []},
    MatteCopy: {mount: () => ({reset() {}})},
    SLComponent: {mount: (_, options) => {
      onSend = options.onSend;
      return {start() { startCalls++; }, reset() {}};
    }},
    localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
    confirm: () => true,
    fetch: async (url, options = {}) => {
      const ok = data => ({ok: true, json: async () => JSON.parse(JSON.stringify(data))});
      if (url === "/api/chat") {
        const body = JSON.parse(options.body); requests.push(body);
        return new Promise((resolve, fail) => {
          reply = answer => {
            if (saved && body.chat_id) saved.find(c => c.id === body.chat_id).turns.push({question: body.messages[0].text, answer});
            resolve(ok(answer));
          };
          reject = fail;
        });
      }
      if (url.startsWith("/api/chats")) {
        if (!saved) return {ok: false, status: 503, json: async () => ({detail: "disabled"})};
        const id = url.split("/")[3];
        if (options.method === "POST") {
          const chat = {id: "chat-" + (saved.length + 1), title: "Новый диалог", updated: Date.now() / 1000, turns: []};
          saved.unshift(chat); return ok(chat);
        }
        if (options.method === "DELETE") {
          saved.splice(saved.findIndex(c => c.id === id), 1);
          return {ok: true, status: 204};
        }
        return ok(id ? saved.find(c => c.id === id) : saved);
      }
      return ok([]);
    },
    AbortController, AbortSignal, performance, Intl, matchMedia: () => ({matches: false}), CustomEvent,
    setInterval: fn => { intervals.add(fn); return fn; },
    clearInterval: fn => intervals.delete(fn),
    setTimeout, clearTimeout
  });
  const staticDir = path.join(__dirname, "../static");
  vm.runInContext(fs.readFileSync(path.join(staticDir, "archive-scene.js"), "utf8"), context);
  vm.runInContext(fs.readFileSync(path.join(staticDir, "app.js"), "utf8"), context);
  return {
    get, intervals, requests,
    ready: new Promise(resolve => setImmediate(resolve)),
    scene: () => get("conversation").children.flatMap(n => n.children || []).find(n => n.className === "archive-scene"),
    stateFor: answer => { context.testAnswer = answer; return vm.runInContext("ArchiveScene.stateFor(testAnswer)", context); },
    send: (signal = new AbortController().signal) => onSend({signal}),
    reply: answer => reply(answer), fail: error => reject(error),
    startCalls: () => startCalls
  };
}
const source = {n: 1, title: "Документ", document_id: "fixture", quote: "Текст", start: 0, end: 5};
test("only a complete sourced answer celebrates; refusal and error never do, even with sources", () => {
  const h = harness();
  assert.equal(h.stateFor({status: "answer", sources: [source]}), "success");
  assert.equal(h.stateFor({status: "answer", sources: []}), "idle");
  assert.equal(h.stateFor({status: "partial", sources: [source]}), "partial");
  assert.equal(h.stateFor({status: "clarify", sources: [source]}), "clarify");
  assert.equal(h.stateFor({status: "insufficient"}), "search_error");
  assert.equal(h.stateFor({status: "out_of_scope"}), "out_of_scope");
  assert.equal(h.stateFor({status: "disallowed"}), "unsafe_legal_request");
  assert.equal(h.stateFor({status: "unverified"}), "unverified");
  assert.equal(h.stateFor({status: "out_of_scope", ui_state: "role_protection"}), "role_protection");
  assert.equal(h.stateFor({status: "answer", ui_state: "role_protection", sources: [source]}), "success");
  assert.equal(h.stateFor({status: "technical_error", sources: [source]}), "system_error");
  assert.equal(h.stateFor({status: "future_status", sources: [source]}), "idle");
});
test("pending request searches, then freezes on the sourced result without delaying the answer", async () => {
  const h = harness(); await h.ready; h.get("question").value = "Вопрос";
  const request = h.send();
  const scene = h.scene();
  assert.equal(scene.dataset.state, "searching");
  assert.equal(scene.attributes["aria-hidden"], "true");
  assert.equal(h.intervals.size, 1);
  h.reply({status: "answer", text: "Ответ", sources: [source]});
  await request;
  assert.equal(h.scene(), scene);
  assert.equal(scene.dataset.state, "success");
  assert.equal(h.intervals.size, 0);
  assert.equal(h.get("reset").disabled, false);
});
test("network failure uses its own scene; retry starts a new search without duplicating the user", async () => {
  const h = harness(); await h.ready; h.get("question").value = "Вопрос";
  const request = h.send();
  h.fail(new TypeError("offline"));
  await assert.rejects(request, /chat_request_failed/);
  assert.equal(h.scene().dataset.state, "system_error");
  assert.equal(h.intervals.size, 0);
  const assistant = h.get("conversation").children.at(-1);
  const body = assistant.children.find(n => n.className === "message-body");
  const retry = body.children.find(n => n.textContent === "Повторить");
  retry.events.click();
  assert.equal(h.startCalls(), 1);
  const second = h.send();
  assert.equal(h.scene().dataset.state, "searching");
  h.reply({status: "answer", text: "Ответ", sources: [source]});
  await second;
  assert.equal(h.get("conversation").children.filter(n => n.classes?.has("user")).length, 1);
});
test("refusal displays refusal frames and keeps its reason in the answer", async () => {
  const h = harness(); await h.ready; h.get("question").value = "Вопрос";
  const request = h.send();
  h.reply({status: "insufficient", text: "Недостаточно оснований", sources: []});
  await request;
  assert.equal(h.scene().dataset.state, "search_error");
  assert.equal(h.intervals.size, 0);
});
test("clarification uses its own whole image and survives opening saved history", async () => {
  const h = harness(); await h.ready;
  h.get("question").value = "Какой срок по договору?";
  const request = h.send();
  h.reply({status: "clarify", text: "Уточните договор.", sources: []});
  await request;
  assert.equal(h.scene().dataset.state, "clarify");
  assert.equal(h.scene().children[0].style.backgroundImage, 'url("/static/media/archive-clarify.webp")');
  assert.equal(h.scene().children[0].style.backgroundSize, "contain");
  assert.equal(h.intervals.size, 0);
  const restored = harness([{id: "clarify-test", title: "Договор", updated: 1000, turns: [
    {question: "Какой срок по договору?", answer: {status: "clarify", text: "Уточните договор.", sources: []}}
  ]}]);
  await restored.ready;
  assert.equal(restored.scene().dataset.state, "clarify");
  assert.equal(restored.scene().children[0].style.backgroundSize, "contain");
});
test("cancel removes the scene and timer, restores the question and welcome", async () => {
  const h = harness(); await h.ready; h.get("question").value = "Вопрос";
  const controller = new AbortController();
  const request = h.send(controller.signal);
  controller.abort();
  h.fail(new DOMException("Cancelled", "AbortError"));
  await assert.rejects(request, {name: "AbortError"});
  assert.equal(h.scene(), undefined);
  assert.equal(h.intervals.size, 0);
  assert.equal(h.get("question").value, "Вопрос");
  assert.equal(h.get("welcome").hidden, false);
});
test("new dialogue clears terminal scenes", async () => {
  const h = harness(); await h.ready; h.get("question").value = "Вопрос";
  const request = h.send(); h.reply({status: "disallowed", text: "Отказ", sources: []});
  await request;
  h.get("reset").events.click();
  assert.equal(h.scene(), undefined);
  assert.equal(h.get("welcome").hidden, false);
});

test("only registered citation numbers become links and the answer text stays intact", async () => {
  const h = harness(); await h.ready;
  h.get("question").value = "Вопрос";
  const request = h.send();
  const text = "Основание [1], неизвестный номер [9], повтор [1].";
  h.reply({status: "answer", text, sources: [source]});
  await request;
  const answer = h.get("conversation").children.find(node => node.dataset.status === "answer");
  const body = answer.children.find(node => node.className === "message-body");
  const paragraph = body.children.find(node => node.tagName === "p");
  const links = paragraph.children.filter(node => node.tagName === "a");
  assert.deepEqual(links.map(link => link.textContent), ["[1]", "[1]"]);
  assert.equal(links[0].href, "#doc-title");
  assert.equal(paragraph.children.map(node => node.textContent).join(""), text);
});


test("server history restores citations after a new browser and sends only the current question", async () => {
  const saved = [{id: "first", title: "Аренда", updated: 1000, turns: [
    {question: "Вопрос", answer: {status: "answer", text: "Ответ [1]", sources: [source]}}
  ]}];
  const h = harness(saved); await h.ready;
  const answer = h.get("conversation").children.find(n => n.dataset.status === "answer");
  assert.ok(answer);
  const body = answer.children.find(n => n.className === "message-body");
  assert.ok(body.children.find(n => n.className === "source"));
  h.get("question").value = "Уточнение";
  const request = h.send(); await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(h.requests[0], {chat_id: "first", messages: [{role: "user", text: "Уточнение"}]});
  h.reply({status: "clarify", text: "Уточните дату", sources: []}); await request;
  const second = harness(saved); await second.ready;
  assert.equal(second.get("conversation").children.filter(n => n.classes.has("message")).length, 4);
  second.get("reset").events.click();
  assert.equal(saved.length, 1);
  second.get("question").value = "Другой договор";
  const newRequest = second.send(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(saved.length, 2);
  assert.notEqual(second.requests[0].chat_id, "first");
  second.reply({status: "answer", text: "Другой ответ", sources: []}); await newRequest;
  const row = second.get("chat-list").children[0];
  row.children[1].events.click(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(saved.length, 1);
  assert.equal(second.get("welcome").hidden, false);
});
