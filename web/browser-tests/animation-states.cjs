// Read-only application probe: all chat responses below are browser fixtures.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}, reducedMotion: 'no-preference'});
  const source = {n: 1, document_id: 'fixture', title: 'Тестовый источник', quote: 'Фикстура', start: 0, end: 8};
  const cases = [
    ['answer', 'success'], ['partial', 'partial'], ['clarify', 'clarify'], ['insufficient', 'search_error'],
    ['out_of_scope', 'out_of_scope'], ['disallowed', 'unsafe_legal_request'], ['unverified', 'unverified'],
    ['technical_error', 'system_error'], ['cancelled', 'stopped']
  ];
  const turns = cases.map(([status]) => ({question: 'Состояние ' + status, answer: {status, text: 'Тестовое состояние', sources: [source]}}));
  turns.push({question: 'Тест маркера роли', answer: {status: 'out_of_scope', ui_state: 'role_protection', text: 'Тестовый отказ', sources: []}});
  const chat = {id: 'animation-fixture', title: 'Состояния', updated: 1, turns};
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/chat-folders', route => route.fulfill({json: []}));
  await page.route('**/api/workspace/**', route => route.fulfill({json: {matter: {}, draft: '', draft_revision: 0, answers: []}}));
  await page.route('**/api/chats**', route => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({json: path.endsWith('/jobs') ? {jobs: [], paused: false, turns: chat.turns, title: chat.title} :
      route.request().url().includes('trash=true') ? [] : path === '/api/chats' ? [chat] : chat});
  });
  try {
    await page.goto(process.env.BASE_URL || 'http://127.0.0.1:8003');
    await page.waitForFunction(() => !document.querySelector('#send').disabled);
    const scenes = page.locator('#conversation .archive-scene');
    assert.deepEqual(await scenes.evaluateAll(nodes => nodes.map(node => node.dataset.state)), [...cases.map(item => item[1]), 'role_protection']);
    assert.ok((await scenes.evaluateAll(nodes => nodes.map(node => node.firstElementChild.getAnimations().length))).every(count => count === 0));
    chat.turns.push({question: 'Новый завершённый вопрос', answer: {status: 'answer', text: 'Готовый ответ [1]', sources: [source]}});
    await page.waitForFunction(() => document.querySelectorAll('#conversation .archive-scene').length === 11 &&
      document.querySelector('#conversation .message:last-child .archive-scene__frame').getAnimations().length === 1);
    assert.equal(await scenes.last().getAttribute('data-state'), 'success');
    assert.equal(await scenes.last().evaluate(node => node.firstElementChild.getAnimations()[0].effect.getTiming().duration), 1000);
    await page.locator('#open-appearance').click();
    await page.locator('#appearance-animations').selectOption('off');
    assert.equal(await scenes.first().isVisible(), false);
    await page.locator('#appearance-animations').selectOption('on');
    await page.emulateMedia({reducedMotion: 'reduce'});
    assert.equal(await scenes.first().isVisible(), true);
    assert.ok((await scenes.evaluateAll(nodes => nodes.map(node => node.firstElementChild.getAnimations().length))).every(count => count === 0));
    await page.locator('#close-appearance').click();
    for (const selector of ['.copy-answer', '.share-answer', '#print-dialogue', '#print-document']) {
      const node = page.locator(selector).first();
      assert.ok(await node.getAttribute('aria-label'));
      assert.ok(await node.getAttribute('title'));
      assert.equal(await node.locator('svg[aria-hidden=true]').count(), 1);
    }
    const icon = await page.locator('link[rel=icon]').getAttribute('href');
    const response = await page.request.get(new URL(icon, page.url()).href);
    assert.equal(response.status(), 200); assert.match(response.headers()['content-type'], /image\/svg\+xml/);
    assert.deepEqual(errors, []);
    console.log('PASS restored outcome poses, one-shot queue animation, reduced motion, animation setting, labelled icons and favicon.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
