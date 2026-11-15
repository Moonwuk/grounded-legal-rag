// UI regression with fixture dialogue writes; document reads use the real corpus.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  const base = process.env.BASE_URL || 'http://127.0.0.1:8003';
  const output = process.env.AUDIT_OUTPUT || '/tmp/legal-usability'; fs.mkdirSync(output, {recursive: true});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce', permissions: ['clipboard-read', 'clipboard-write']});
  const page = await context.newPage(), errors = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    const docs = await (await context.request.get(base + '/api/documents')).json();
    const doc = await (await context.request.get(base + '/api/documents/' + docs[0].id)).json();
    const characters = Array.from(doc.text);
    const source = {n: 1, document_id: docs[0].id, title: doc.title, status: doc.status, heading: 'Положение документа', start: 0, end: 350, quote: characters.slice(0, 350).join('')};
    const second = {...source, n: 2, start: 350, end: 650, quote: characters.slice(350, 650).join(''), heading: 'Следующее положение'};
    const chat = {id: 'review', title: 'Проверка договора', updated: 1, pinned: false, turns: [
      {question: 'Какие условия содержит договор?', answer: {status: 'answer', text: 'Найденные положения договора [1] [2].', sources: [source, second]}},
      {question: 'А на дату сделки?', answer: {status: 'clarify', text: 'Уточните дату события и договор.', sources: [], clarification_fields: [{code: 'event_date', label: 'Дата события'}, {code: 'contract', label: 'Номер договора'}]}}
    ]};
    let submitted;
    await page.route('**/api/chat-folders', r => r.fulfill({json: []}));
    await page.route('**/api/document-tabs', r => r.fulfill({json: []}));
    await page.route('**/api/chats**', r => {
      const url = new URL(r.request().url());
      if (url.pathname.endsWith('/jobs')) {
        if (r.request().method() === 'POST') { submitted = r.request().postDataJSON(); return r.fulfill({status: 202, json: {}}); }
        return r.fulfill({json: {turns: chat.turns, title: chat.title, jobs: [], paused: false}});
      }
      if (url.pathname.endsWith('/pin')) { chat.pinned = url.searchParams.get('pinned') === 'true'; return r.fulfill({json: {id: chat.id, pinned: chat.pinned}}); }
      if (url.pathname === '/api/chats') return r.fulfill({json: url.searchParams.has('trash') ? [] : [chat]});
      return r.fulfill({json: chat});
    });
    await page.goto(base); await page.waitForFunction(() => !document.querySelector('#send').disabled);
    assert.equal(await page.locator('.source-group').count(), 1);
    assert.equal(await page.locator('.source-group .source').count(), 2);
    assert.equal(await page.locator('.quote-preview').first().textContent(), source.quote);
    // Share only the chosen answer and its exact sources, never the whole dialogue.
    await page.evaluate(() => Object.defineProperty(navigator, 'share', {configurable: true, value: async payload => { window.sharedAnswer = payload; }}));
    await page.locator('.share-answer').first().click();
    const shared = await page.evaluate(() => window.sharedAnswer);
    assert.ok(shared.text.includes(second.quote));
    assert.equal(shared.text.includes('А на дату сделки?'), false);
    await page.evaluate(() => Object.defineProperty(navigator, 'share', {configurable: true, value: async () => { throw new DOMException('Cancelled', 'AbortError'); }}));
    await page.locator('.share-answer').first().click();
    assert.equal(await page.locator('#copy-dialog').isVisible(), false);
    for (const mode of ['missing', 'denied']) {
      await page.evaluate(mode => Object.defineProperty(navigator, 'share', {configurable: true, value: mode === 'missing' ? undefined : async () => { throw new DOMException('Denied', 'NotAllowedError'); }}), mode);
      await page.locator('.share-answer').first().click();
      await page.locator('#copy-dialog').waitFor({state:'visible'});
      assert.equal(await page.locator('#copy-text').inputValue(), shared.text);
      await page.locator('#copy-dialog-button').click();
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), shared.text);
      await page.locator('#close-copy').click();
    }
    await page.setViewportSize({width:390,height:420});
    await page.locator('.share-answer').first().click();
    const shareControls = await page.locator('#copy-dialog-button').boundingBox();
    assert.ok(shareControls.y >= 0 && shareControls.y + shareControls.height <= 420);
    await page.screenshot({path:output + '/share-mobile.png'});
    await page.locator('#close-copy').click();
    await page.setViewportSize({width:1440,height:1000});
    // Native Ctrl+P / browser menu must prepare the current transcript too.
    await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
    assert.ok((await page.locator('#print-view').textContent()).includes(second.quote));
    await page.locator('.copy-answer').first().click();
    assert.ok((await page.evaluate(() => navigator.clipboard.readText())).includes(second.quote));
    await page.evaluate(() => { window.print = () => { window.printCalled = true; }; });
    await page.locator('#print-dialogue').click();
    assert.equal(await page.evaluate(() => window.printCalled), true);
    assert.ok((await page.locator('#print-view').textContent()).includes(second.quote));
    assert.ok((await page.locator('#print-view').textContent()).includes('А на дату сделки?'));
    await page.emulateMedia({media: 'print'}); await page.pdf({path: output + '/dialogue.pdf', format: 'A4'}); await page.emulateMedia({media: 'screen'});
    await page.locator('#conversation').evaluate(e => e.scrollTop = 0);
    await page.screenshot({path: output + '/desktop.png'});
    await page.locator('#toggle-documents').click(); assert.equal(await page.locator('#documents-panel').isVisible(), false);
    await page.locator('.source').first().click(); assert.equal(await page.locator('#documents-panel').isVisible(), true);
    await page.locator('#document-search').waitFor({state: 'visible'});
    assert.equal(await page.locator('.source-highlight').textContent(), source.quote);
    await page.locator('#document-query').fill('договор');
    assert.ok(await page.locator('.document-hit').count() > 1);
    const before = await page.locator('#document-search-status').textContent();
    await page.locator('#document-next').click(); assert.notEqual(await page.locator('#document-search-status').textContent(), before);
    await page.locator('#document-prev').click(); assert.equal(await page.locator('#document-search-status').textContent(), before);
    assert.equal(await page.locator('#doc-text').textContent(), doc.text);
    await page.locator('#document-citation').click();
    await page.locator('#document-query').fill('[.*'); assert.equal(await page.locator('#document-search-status').textContent(), 'Не найдено');
    await page.locator('#document-query').fill('');
    assert.equal(await page.locator('.source-highlight').textContent(), source.quote);
    // Printing a searched/cited document must retain its entire unchanged text.
    await page.locator('#print-document').click();
    await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
    assert.equal(await page.locator('#print-view .printed-document').textContent(), doc.text);
    assert.equal(await page.locator('#print-view h1').textContent(), doc.title);
    await page.emulateMedia({media:'print'});
    await page.pdf({path: output + '/document.pdf', format:'A4'});
    await page.emulateMedia({media:'screen'});
    await page.evaluate(() => { window.dispatchEvent(new Event('afterprint')); window.dispatchEvent(new Event('beforeprint')); });
    assert.equal(await page.locator('#print-view .printed-document').count(), 0);
    assert.ok((await page.locator('#print-view').textContent()).includes('А на дату сделки?'));
    await page.screenshot({path: output + '/document.png'});
    await page.locator('#history-query').fill('условия');
    await page.waitForFunction(() => document.querySelector('#history-search-status').textContent.startsWith('Найдено:'));
    await page.locator('.chat-actions summary').click(); await page.getByRole('button', {name: 'Закрепить', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('.chat-select-title').textContent.startsWith('★'));
    await page.locator('.clarification-form input').nth(0).fill('15.08.2024');
    await page.locator('.clarification-form input').nth(1).fill('А-08-2024');
    await page.locator('.clarification-form button').click();
    await page.waitForFunction(() => document.querySelector('#send').closest('.sl-component').dataset.phase !== 'pending');
    assert.match(submitted.question, /Дата события: 15.08.2024\nНомер договора: А-08-2024/);
    for (const [width, height] of [[390, 844], [320, 568], [390, 420]]) {
      await page.setViewportSize({width, height}); await page.locator('#all-docs').evaluate(e => e.click());
      await page.locator('#open-documents').click();
      assert.equal(await page.locator('.collection-picker').isVisible(), false);
      const first = await page.locator('#doc-list button').first().boundingBox(); assert.ok(first.y < 370, JSON.stringify({width, height, first}));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({path: output + '/catalog-' + width + '-' + height + '.png'});
      await page.locator('#create-doc-tab').click();
      const footer = await page.locator('.tab-dialog-actions').boundingBox(); assert.ok(footer.y >= 0 && footer.y + footer.height <= height, JSON.stringify(footer));
      await page.locator('#tab-name').fill('Проверка');
      await page.locator('#tab-choices input').last().check();
      const save = await page.locator('#save-doc-tab').boundingBox(); assert.ok(save.y + save.height <= height);
      await page.screenshot({path: output + '/collection-' + width + '-' + height + '.png'});
      await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
      await page.locator('#open-history').click();
      const row = await page.locator('#chat-list li').first().boundingBox(); assert.ok(row.y < 370, JSON.stringify(row));
      await page.screenshot({path: output + '/history-' + width + '-' + height + '.png'});
      await page.keyboard.press('Escape');
    }
    const unicode = '😀 Начало. Договор😀 и договор. Конец';
    const chars = Array.from(unicode), from = 10, to = 20;
    await page.route('**/api/documents/unicode-fixture', r => r.fulfill({json: {title: 'Unicode', text: unicode, status: ''}}));
    await page.evaluate(({from, to, quote}) => openDocument('unicode-fixture', {start: from, end: to, quote}), {from, to, quote: chars.slice(from, to).join('')});
    assert.equal(await page.locator('.source-highlight').textContent(), chars.slice(from, to).join(''));
    await page.locator('#document-query').fill('😀');
    assert.equal(await page.locator('#doc-text').textContent(), unicode);
    assert.equal(await page.locator('#document-search-status').textContent(), '1 / 2');
    await page.locator('#document-citation').click();
    // Short mobile document navigation keeps controls visible and scrolls the hit.
    const longText = 'Искомый фрагмент\nНачало\n' + 'Строка документа\n'.repeat(350) + 'Искомый фрагмент\nКонец';
    await page.route('**/api/documents/long-fixture', r => r.fulfill({json: {title: 'Длинный документ', text: longText, status: ''}}));
    for (const viewport of [{width:320,height:568},{width:390,height:420}]) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => openDocument('long-fixture'));
      await page.locator('#document-query').fill('Искомый фрагмент');
      assert.equal(await page.locator('#mobile-panel-content > aside').count(), 1);
      await page.locator('#document-next').click();
      const hit = await page.locator('.current-hit').boundingBox();
      assert.ok(hit.y >= 0 && hit.y + hit.height <= viewport.height, JSON.stringify({hit,viewport}));
      await page.locator('#print-document').click();
      assert.equal(await page.locator('#print-view .printed-document').textContent(), longText);
      const printButton = await page.locator('#print-document').boundingBox();
      assert.ok(printButton.y >= 0 && printButton.y + printButton.height <= viewport.height);
      await page.screenshot({path: output + '/document-print-' + viewport.width + '.png'});
      if (viewport.width === 390) { await page.emulateMedia({media:'print'}); await page.pdf({path: output + '/mobile-document.pdf', format:'A4'}); await page.emulateMedia({media:'screen'}); }
      await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
      const controls = await page.locator('#document-next').boundingBox();
      assert.ok(controls.y >= 0 && controls.y + controls.height <= viewport.height);
    }
    await page.keyboard.press('Escape');
    await page.locator('#new-dialogue').click();
    await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
    assert.equal((await page.locator('#print-view').textContent()).includes(second.quote), false);
    assert.ok((await page.locator('#print-view').textContent()).includes('пока нет сообщений'));
    assert.deepEqual(errors, []);
    console.log('PASS: answer sharing/cancellation/fallback, full document and dialogue PDF, exact quotes, clarification, search, pinning and mobile layouts.');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
