// Browser layout regression: collections/history are fixtures, corpus reads are real.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {}), args: ['--no-sandbox']});
  const base = process.env.BASE_URL || 'http://127.0.0.1:8002';
  const creds = process.env.TEST_CREDENTIALS ? JSON.parse(fs.readFileSync(process.env.TEST_CREDENTIALS)) : null;
  const context = await browser.newContext(creds ? {httpCredentials: {username: creds.username, password: creds.password}} : {});
  const page = await context.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  try {
    const docs = await (await context.request.get(base + '/api/documents')).json();
    const tabs = Array.from({length: 30}, (_, i) => ({id: 'layout-' + i, title: 'Документы по аренде и сопровождению договоров — подборка ' + i,
      document_ids: [docs[0].id], revision: 1}));
    await page.route('**/api/chats**', route => route.fulfill({json: []}));
    await page.route('**/api/chat-folders', route => route.fulfill({json: []}));
    await page.route('**/api/document-tabs', route => route.fulfill({json: tabs}));
    for (const [width, height] of [[1440, 1000], [1024, 768], [390, 844], [320, 568], [844, 390]]) {
      await page.setViewportSize({width, height}); await page.goto(base);
      await page.waitForFunction(() => !document.querySelector('#create-doc-tab').disabled);
      if (width <= 900) await page.locator('#open-documents').click();
      const result = await page.locator('#documents-panel').evaluate(panel => {
        const grid = panel.querySelector('#doc-tabs'), rect = panel.getBoundingClientRect();
        return {fits: grid.scrollWidth <= grid.clientWidth + 1, panelFits: panel.scrollWidth <= panel.clientWidth + 1,
          tabsFit: [...grid.children].every(el => {const b = el.getBoundingClientRect(); return b.left >= rect.left && b.right <= rect.right && el.scrollWidth <= el.clientWidth + 1;}),
          count: grid.children.length};
      });
      assert.deepEqual(result, {fits: true, panelFits: true, tabsFit: true, count: 5}, `${width}×${height}`);
      assert.equal(await page.locator('#custom-doc-tabs option').count(), 31);
      await page.locator('#custom-doc-tabs').selectOption('layout-29');
      assert.equal(await page.locator('#doc-list li').count(), 1);
      assert.equal(await page.locator('#edit-doc-tab').isVisible(), true);
      await page.getByRole('tab', {name: /^Все ·/}).click();
      assert.equal(await page.locator('#doc-list li').count(), docs.length);
      assert.equal(await page.locator('#custom-doc-tabs').inputValue(), '');
      await page.getByRole('tab', {name: /^Все ·/}).focus();
      await page.keyboard.press('ArrowRight');
      assert.equal(await page.getByRole('tab', {name: /^Законы ·/}).getAttribute('aria-selected'), 'true');
      await page.getByRole('tab', {name: /^Все ·/}).click();
      await page.locator('#doc-list button').first().scrollIntoViewIfNeeded();
      const box = await page.locator('#doc-list button').first().boundingBox();
      assert.ok(box.y >= 0 && box.y + box.height <= height + 1, `${width}×${height}: document reachable`);
      if (width === 390 || width === 1440) await page.screenshot({path: '/tmp/legal-rag-document-layout-' + width + '.png'});
    }
    assert.deepEqual(errors, []);
    console.log('PASS: all categories fit without horizontal scroll, 30 long custom names, selection/filtering, keyboard and document access at five viewport sizes.');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
