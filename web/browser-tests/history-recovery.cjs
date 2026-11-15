// Browser regression with API fixtures only; no model calls or stored user data.
// Run like mobile.cjs against the selected application version.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {}), args: ['--no-sandbox']});
  try {
    for (const failure of ['network', 401, 500, 503, 'unconfigured', 'none']) {
      const page = await browser.newPage();
      const errors = []; page.on('pageerror', e => errors.push(e.message));
      let broken = failure !== 'none', posts = [], lost = false, jobs = new Map();
      const chat = {id: 'saved', title: 'Старый диалог', turns: [], updated: 1};
      const chats = [chat];
      await page.route('**/api/**', async route => {
        const req = route.request(), url = new URL(req.url()), path = url.pathname;
        if (req.method() === 'POST') posts.push({path, body: req.postDataJSON()});
        if (path === '/api/documents' || path === '/api/chat-folders') return route.fulfill({json: []});
        if (path === '/api/document-tabs') return route.fulfill({status: 503, json: {detail: 'Не настроено'}});
        if (path === '/api/chats') {
          if (broken) {
            if (failure === 'network') return route.abort('failed');
            return route.fulfill({status: failure === 'unconfigured' ? 503 : failure,
              json: {detail: failure === 'unconfigured' ? 'История на сервере не настроена.' : 'Сервис недоступен'}});
          }
          if (req.method() === 'POST') {
            const created = {id: 'new', title: 'Новый диалог', turns: [], updated: 2};
            chats.unshift(created); return route.fulfill({status: 201, json: created});
          }
          return route.fulfill({json: url.search ? [] : chats});
        }
        if (path.endsWith('/jobs')) {
          if (req.method() === 'POST') {
            const body = req.postDataJSON(); jobs.set(body.id, body);
            if (!lost) { lost = true; return route.abort('failed'); }
            return route.fulfill({status: 202, json: {}});
          }
          return route.fulfill({json: {title: 'Диалог', turns: [], jobs: [], paused: false}});
        }
        if (path.startsWith('/api/chats/')) return route.fulfill({json: chats.find(c => path.endsWith(c.id))});
        if (path === '/api/chat') return route.fulfill({json: {status: 'answer', text: 'Временный ответ', sources: []}});
        throw new Error('Unexpected API: ' + path);
      });
      await page.goto(process.env.BASE_URL || 'http://127.0.0.1:8003');
      await page.waitForFunction(() => !navigating);
      await page.locator('#question').fill('Мой вопрос');
      if (failure !== 'none') {
        await page.locator('#question').press('Enter');
        await page.waitForFunction(() => sendController.state.phase !== 'pending');
        assert.equal(posts.length, failure === 'unconfigured' ? 1 : 0, 'Failed initialization must block Enter');
        if (failure !== 'unconfigured') {
          assert.equal(await page.locator('#question').inputValue(), 'Мой вопрос');
          assert.match(await page.locator('#input-error').textContent(), /истории/);
        }
      }
      if (failure === 'unconfigured') { await page.close(); continue; }
      broken = false;
      await page.locator('#refresh-history').click();
      await page.waitForFunction(() => historyReady && !navigating);
      // Refreshing an existing conversation must preserve its draft too.
      await page.locator('#question').fill('Черновик старого');
      await page.locator('#refresh-history').click();
      await page.waitForFunction(() => !navigating);
      assert.equal(await page.locator('#question').inputValue(), 'Черновик старого');
      await page.locator('#reset').click();
      await page.locator('#question').fill('Отдельный вопрос');
      await page.locator('#refresh-history').click();
      await page.waitForFunction(() => !navigating);
      assert.equal(await page.evaluate(() => currentChat), null);
      assert.equal(await page.locator('#question').inputValue(), 'Отдельный вопрос');
      // First queue POST is accepted but its response is lost. Retry uses its ID.
      await page.locator('#question').press('Enter');
      await page.waitForFunction(() => sendController.state.phase === 'error');
      await page.locator('#question').press('Enter');
      await page.waitForFunction(() => sendController.state.phase === 'complete');
      assert.equal(posts.filter(p => p.path === '/api/chats').length, 1);
      const attempts = posts.filter(p => p.path.endsWith('/jobs'));
      assert.equal(attempts.length, 2); assert.equal(attempts[0].body.id, attempts[1].body.id);
      assert.equal(jobs.size, 1); assert.equal(posts.filter(p => p.path === '/api/chat').length, 0);
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('PASS: initialization errors, explicit temporary mode, draft preservation, new dialogue, lost queue response');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
