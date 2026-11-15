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
  showModal() { this.open = true; }
  close(value = "") { this.returnValue = value; this.open = false; this.events.close?.(); }
  animate() { return {cancel() {}}; }
  closest() { return this; }
  querySelector(selector) {
    if (selector === ".message") return this.children.find(c => c.classes?.has("message")) || null;
    return new Element();
  }
}
function harness(saved = null, documents = [], tabs = [], folders = [], historyFailure = null) {
  const requests = [];
  const trash = [];
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
    confirm: () => { throw new Error("Native confirmation must not be used"); },
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
        if (historyFailure) return {ok: false, status: historyFailure, json: async () => ({detail: "Unavailable"})};
        if (!saved) return {ok: false, status: 503, json: async () => ({detail: "История на сервере не настроена."})};
        if (url.includes("?trash=true")) return ok(trash);
        const id = url.split("/")[3];
        if (options.method === "POST" && url.endsWith("/restore")) {
          const chat = trash.splice(trash.findIndex(c => c.id === id), 1)[0];
          delete chat.deleted_at;
          saved.push(chat);
          return {ok: true, status: 204};
        }
        if (options.method === "POST") {
          const chat = {id: "chat-" + (saved.length + 1), title: "Новый диалог", updated: Date.now() / 1000, turns: []};
          saved.unshift(chat); return ok(chat);
        }
        if (options.method === "DELETE") {
          if (url.endsWith("/permanent")) trash.splice(trash.findIndex(c => c.id === id), 1);
          else trash.push({...saved.splice(saved.findIndex(c => c.id === id), 1)[0], deleted_at: Date.now() / 1000});
          return {ok: true, status: 204};
        }
        return ok(id ? saved.find(c => c.id === id) : saved);
      }
      if (url === "/api/chat-folders") return ok(folders);
      if (url === "/api/documents") return ok(documents);
      if (url === "/api/document-tabs") return ok(tabs);
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
test("document tabs partition the corpus, include addenda, and scope search to a custom collection", async () => {
  const docs = [
    {id: "law", title: "НК ст1", category: "законы"},
    {id: "contract", title: "Договор поставки", category: "документы компании"},
    {id: "addendum", title: "Доп соглашение 1", category: "документы компании"},
    {id: "policy", title: "Регламент", category: "документы компании"},
    {id: "letter", title: "Письмо", category: "документы компании"}
  ];
  const h = harness(null, docs, [{id: "mine", title: "Моя сделка", document_ids: ["contract", "letter"]}]);
  await h.ready;
  const titles = () => h.get("doc-list").children.map(row => row.children[0].children[0].textContent);
  assert.deepEqual(titles(), docs.map(doc => doc.title));
  assert.equal(h.get("doc-tabs").children.length, 5);
  h.get("doc-tabs").children[1].events.click();
  assert.deepEqual(titles(), ["НК ст1"]);
  h.get("doc-tabs").children[2].events.click();
  assert.deepEqual(titles(), ["Договор поставки", "Доп соглашение 1"]);
  h.get("custom-doc-tabs").value = "mine";
  h.get("custom-doc-tabs").events.change();
  assert.deepEqual(titles(), ["Договор поставки", "Письмо"]);
  assert.equal(h.get("edit-doc-tab").hidden, false);
  h.get("doc-query").value = "НК";
  h.get("doc-query").events.input();
  assert.deepEqual(titles(), []);
  assert.equal(h.get("doc-status").textContent, "В этой вкладке ничего не найдено.");
  h.get("doc-tabs").children[3].events.click();
  assert.deepEqual(titles(), ["Регламент"]);
  assert.equal(h.get("doc-query").value, "");
});
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


test("server history restores citations and never falls back to synchronous sending without the queue", async () => {
  const saved = [{id: "first", title: "Аренда", updated: 1000, turns: [
    {question: "Вопрос", answer: {status: "answer", text: "Ответ [1]", sources: [source]}}
  ]}];
  const h = harness(saved); await h.ready;
  const answer = h.get("conversation").children.find(n => n.dataset.status === "answer");
  assert.ok(answer);
  const body = answer.children.find(n => n.className === "message-body");
  assert.ok(body.children.find(n => n.className === "source"));
  h.get("question").value = "Уточнение";
  await assert.rejects(h.send(), /queue_unavailable/);
  assert.equal(h.requests.length, 0);
  assert.equal(h.get("question").value, "Уточнение");
  assert.equal(saved[0].turns.length, 1);
});

test("history errors block sending even when invoked directly instead of the disabled button", async () => {
  for (const status of [401, 500, 503]) {
    const h = harness(null, [], [], [], status); await h.ready;
    h.get("question").value = "Сохраните вопрос";
    await assert.rejects(h.send(), /history_unavailable/);
    assert.equal(h.requests.length, 0);
    assert.equal(h.get("question").value, "Сохраните вопрос");
  }
});

test("refresh preserves a new dialogue and its draft instead of opening the first saved chat", async () => {
  const h = harness([{id: "old", title: "Старый диалог", updated: 1, turns: [
    {question: "Старый вопрос", answer: {status: "answer", text: "Ответ", sources: []}}
  ]}]); await h.ready;
  h.get("reset").events.click();
  h.get("question").value = "Новый вопрос";
  h.get("refresh-history").events.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.get("question").value, "Новый вопрос");
  assert.equal(h.get("welcome").hidden, false);
  assert.equal(h.get("conversation").children.length, 1);
});

test("chat folders filter existing history without removing chats or losing the all/unfiled views", async () => {
  const saved = [
    {id: "a", title: "Первый", updated: 1, turns: [], folder_id: "folder-a"},
    {id: "b", title: "Второй", updated: 2, turns: [], folder_id: null},
    {id: "c", title: "Третий", updated: 3, turns: [], folder_id: "folder-b"}
  ];
  const h = harness(saved, [], [], [{id: "folder-a", title: "Сделки"}, {id: "folder-b", title: "Регламенты"}]);
  await h.ready;
  const visible = () => h.get("chat-list").children.map(row => row.dataset.chatId);
  assert.deepEqual(visible(), ["a", "b", "c"]);
  h.get("folder-list").children[2].events.click();
  assert.deepEqual(visible(), ["a"]);
  assert.equal(h.get("edit-chat-folder").hidden, false);
  h.get("folder-list").children[1].events.click();
  assert.deepEqual(visible(), ["b"]);
  assert.equal(h.get("edit-chat-folder").hidden, true);
  h.get("folder-list").children[0].events.click();
  assert.deepEqual(visible(), ["a", "b", "c"]);
  assert.equal(saved.length, 3);
});

test("trash keeps deleted chats out of active folders, restores sources, and exposes permanent deletion separately", async () => {
  const saved = [{id: "saved", title: "Аренда", updated: 1000, turns: [
    {question: "Вопрос", answer: {status: "answer", text: "Ответ [1]", sources: [source]}}
  ]}];
  const h = harness(saved); await h.ready;
  const settle = () => new Promise(resolve => setImmediate(resolve));
  h.get("chat-list").children[0].children.find(n => n.className === "chat-delete").events.click(); h.get("confirm-accept").events.click(); await settle();
  assert.equal(saved.length, 0);
  h.get("folder-list").children.at(-1).events.click();
  let row = h.get("chat-list").children[0];
  assert.equal(row.children[0].disabled, true);
  assert.equal(row.children[1].textContent, "Восстановить");
  assert.equal(row.children[2].textContent, "Удалить навсегда");
  row.children[1].events.click(); await settle();
  assert.equal(saved.length, 1);
  assert.ok(h.get("conversation").children.find(n => n.dataset.status === "answer"));
  h.get("chat-list").children[0].children.find(n => n.className === "chat-delete").events.click(); h.get("confirm-accept").events.click(); await settle();
  h.get("folder-list").children.at(-1).events.click();
  row = h.get("chat-list").children[0];
  row.children[2].events.click(); h.get("confirm-accept").events.click(); await settle();
  assert.equal(h.get("chat-list").children.length, 0);
  assert.equal(h.get("folder-empty").textContent, "Корзина пуста.");
});


test("site confirmation waits for explicit acceptance and cancellation preserves the dialogue", async () => {
  const saved = [{id: "kept", title: "Мой договор", updated: 1, turns: []}];
  const h = harness(saved); await h.ready;
  const remove = () => h.get("chat-list").children[0].children.find(n => n.className === "chat-delete").events.click();
  const pending = remove();
  assert.equal(h.get("confirm-dialog").open, true);
  assert.equal(saved.length, 1);
  assert.match(h.get("confirm-message").textContent, /Мой договор/);
  h.get("confirm-cancel").events.click(); await pending;
  assert.equal(saved.length, 1);
  remove();
  assert.equal(h.get("confirm-accept").textContent, "В корзину");
  h.get("confirm-accept").events.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(saved.length, 0);
});
