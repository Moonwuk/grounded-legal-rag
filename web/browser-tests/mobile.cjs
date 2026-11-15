// Optional browser regression: NODE_PATH=<playwright installation>/node_modules
// BASE_URL=http://127.0.0.1:8002 CHROMIUM_PATH=<binary> node web/browser-tests/mobile.cjs
// All chat/collection writes are fixtures; corpus reads use the running app.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {}), args: ['--no-sandbox']});
  const base = process.env.BASE_URL || 'http://127.0.0.1:8002';
  const credentials = process.env.TEST_CREDENTIALS ? JSON.parse(fs.readFileSync(process.env.TEST_CREDENTIALS)) : null;
  const context = await browser.newContext({viewport: {width: 390, height: 844},
    ...(credentials ? {httpCredentials: {username: credentials.username, password: credentials.password}} : {})});
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  let tabs = [], savedIds = [];
  await page.route("**/api/chat-folders", route => route.fulfill({json: []}));
  await page.route('**/api/document-tabs**', async route => {
    const method = route.request().method();
    if (method === 'GET') return route.fulfill({json: tabs});
    const input = route.request().postDataJSON();
    savedIds = input.document_ids;
    const tab = {...input, id: 'fixture-tab', revision: 1};
    tabs = [tab];
    return route.fulfill({status: method === 'POST' ? 201 : 200, json: tab});
  });
  const chat = {id: 'fixture-chat', title: 'Сохранённый вопрос', updated: 1700000000,
    turns: [{question: 'Сохранённый вопрос', answer: {status: 'clarify', text: 'Уточните дату договора.', sources: []}}]};
  let queuedAnswer;
  await page.route('**/api/chats**', route => {
    const url = route.request().url();
    if (url.endsWith('/jobs')) {
      if (route.request().method() === 'POST') {
        const data = route.request().postDataJSON();
        chat.turns.push({question: data.question, answer: queuedAnswer});
        return route.fulfill({status: 202, json: {id: data.id, status: 'done'}});
      }
      return route.fulfill({json: {jobs: [], paused: false, turns: chat.turns, title: chat.title}});
    }
    return route.fulfill({json: url.includes('?trash=true') ? [] : url.endsWith('/api/chats') ? [chat] : chat});
  });
  await page.goto(base);
  await page.waitForFunction(() => !document.querySelector('#send').disabled);
  await page.locator('#open-history').click();
  await page.locator('#reset').click();
  await page.locator('#question').blur();
  const fits = async () => {
    await page.waitForFunction(() => document.querySelector("#chat-form").getBoundingClientRect().bottom <= innerHeight + 1);
    const box = await page.locator('#chat-form').boundingBox();
    const viewport = page.viewportSize();
    assert.ok(box.y >= 0 && box.y + box.height <= viewport.height + 1, JSON.stringify({box, viewport}));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await page.evaluate(() => document.body.scrollHeight <= innerHeight + 1), true);
  };
  await fits();
  assert.equal(await page.locator('#history-panel').isVisible(), false);
  assert.equal(await page.locator('#documents-panel').isVisible(), false);
  await page.screenshot({path: '/tmp/legal-rag-mobile-chat.png'});
  await page.locator('#open-history').click();
  await page.locator('#history-panel .chat-select').click();
  await page.waitForFunction(() => !document.querySelector('#mobile-panel').open);
  assert.match(await page.locator('#conversation').innerText(), /Уточните дату/);
  await page.locator('#open-history').click();
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('#mobile-panel').open);
  assert.equal(await page.locator('#open-history').evaluate(e => document.activeElement === e), true);
  await page.locator('#open-documents').click();
  await page.waitForFunction(() => !document.querySelector('#create-doc-tab').disabled);
  assert.equal(await page.getByRole('tab', {name: 'Все · 21'}).getAttribute('aria-selected'), 'true');
  assert.equal(await page.locator('#doc-list li').count(), 21);
  await page.getByRole('tab', {name: 'Законы · 13'}).click();
  assert.equal(await page.locator('#doc-list li').count(), 13);
  await page.locator('#create-doc-tab').click();
  await page.locator('#tab-name').fill('Договор и закон');
  await page.locator('#tab-doc-type').selectOption('contracts');
  assert.equal(await page.locator('#tab-choices label:visible').count(), 3);
  await page.locator('#tab-choices label:visible input').first().check();
  await page.locator('#tab-doc-type').selectOption('laws');
  await page.locator('#tab-doc-query').fill('НК');
  assert.equal(await page.locator('#tab-choices label:visible').count(), 6);
  await page.locator('#tab-choices label:visible input').first().check();
  await page.locator('#tab-doc-status').selectOption('expired');
  assert.equal(await page.locator('#tab-choices label:visible').count(), 0);
  assert.match(await page.locator('#tab-selection-status').innerText(), /Выбрано: 2/);
  await page.locator('#reset-tab-filters').click();
  await page.locator('#tab-doc-selected').check();
  assert.equal(await page.locator('#tab-choices label:visible').count(), 2);
  await page.screenshot({path: '/tmp/legal-rag-mobile-filters.png'});
  await page.locator('#save-doc-tab').click();
  await page.waitForFunction(() => !document.querySelector('#tab-dialog').open);
  assert.equal(savedIds.length, 2);
  assert.equal(await page.locator('#doc-list li').count(), 2);
  await page.screenshot({path: '/tmp/legal-rag-mobile-documents.png'});
  await page.locator('#doc-list button').first().click();
  await page.locator('#doc-text').waitFor({state: 'visible'});
  await page.locator('#all-docs').click();
  assert.equal(await page.locator('#doc-list li').count(), 2);
  await page.locator('#close-mobile-panel').click();
  // A sourced answer must stay in the chat; only tapping a citation opens the document.
  const documents = await (await context.request.get(base + '/api/documents')).json();
  const document = await (await context.request.get(base + '/api/documents/' + documents[0].id)).json();
  const source = {...documents[0], n: 1, document_id: documents[0].id, start: 0, end: 20,
    quote: Array.from(document.text).slice(0, 20).join('')};
  queuedAnswer = {status: 'answer', text: 'Ответ по документу [1]', sources: [source]};
  await page.locator('#question').fill('Тестовый вопрос');
  await page.locator('#send').click();
  await page.locator('.inline-citation').waitFor();
  assert.equal(await page.locator('#mobile-panel').evaluate(e => e.open), false);
  await page.locator('.inline-citation').click();
  await page.locator('#doc-text mark').waitFor({state: 'visible'});
  await page.locator('#close-mobile-panel').click();
  // Compact height models the space remaining when a software keyboard is open.
  for (const [width, height] of [[320, 568], [390, 420], [844, 390], [768, 1024]]) {
    await page.setViewportSize({width, height});
    await fits();
  }
  // Resizing with a panel open must restore its original desktop placement.
  await page.locator('#open-documents').click();
  await page.setViewportSize({width: 1440, height: 1000});
  await page.waitForFunction(() => !document.querySelector('#mobile-panel').open);
  assert.equal(await page.locator('.workspace > #documents-panel').isVisible(), true);
  assert.equal(await page.locator('.workspace > #history-panel').isVisible(), true);
  assert.equal(await page.locator('#open-documents').isVisible(), false);
  await page.screenshot({path: '/tmp/legal-rag-desktop-preserved.png'});
  assert.deepEqual(errors, []);
  await browser.close();
  console.log('PASS: mobile chat, history, dialogs, source navigation, all documents, combined filters, preserved selection, keyboard-sized viewport, desktop restoration.');
})().catch(error => {console.error(error); process.exit(1);});
