const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function contrast(rgb, other) {
  const linear = channel => {
    const value = Number(channel) / 255;
    return value <= .04045 ? value / 12.92 : Math.pow((value + .055) / 1.055, 2.4);
  };
  const luminance = color => color.match(/\d+/g).slice(0, 3).map(linear)
    .reduce((total, value, i) => total + value * [.2126, .7152, .0722][i], 0);
  const a = luminance(rgb), b = luminance(other);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  const output = process.env.AUDIT_OUTPUT;
  const base = process.env.BASE_URL || 'http://127.0.0.1:8003';
  const page = await browser.newPage({viewport: {width: 1440, height: 1050}, colorScheme: 'light'});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(base);
    const theme = () => page.locator('html').getAttribute('data-theme');
    const open = page.getByRole('button', {name: 'Настройки', exact: true});
    await open.focus();
    await page.keyboard.press('Enter');
    const dialog = page.locator('#appearance-dialog');
    assert.equal(await dialog.getAttribute('open'), '');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'close-appearance');
    await page.emulateMedia({colorScheme: 'dark'});
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    const mode = page.locator('#appearance-theme');
    await mode.selectOption('light');
    assert.equal(await theme(), 'light');
    if (output) {
      fs.mkdirSync(output, {recursive: true});
      await page.screenshot({path: path.join(output, 'appearance-light.png')});
    }
    for (const modeName of ['light', 'dark']) {
      await mode.selectOption(modeName);
      const backgrounds = new Set();
      for (const value of ['psb', 'violet', 'emerald', 'orange', 'pink', 'graphite']) {
        await page.locator('#appearance-accent').selectOption(value);
        const colors = await page.evaluate(() => {
          const button = getComputedStyle(document.getElementById('appearance-preview-button'));
          const preview = getComputedStyle(document.querySelector('.appearance-preview'));
          const link = getComputedStyle(document.querySelector('.appearance-preview a'));
          return [button.color, button.backgroundColor, preview.color, preview.backgroundColor, link.color];
        });
        backgrounds.add(colors[1]);
        assert.ok(contrast(colors[0], colors[1]) >= 4.5, [modeName, value, ...colors]);
        assert.ok(contrast(colors[2], colors[3]) >= 4.5, [modeName, value, ...colors]);
        assert.ok(contrast(colors[4], colors[3]) >= 4.5, [modeName, value, ...colors]);
      }
      assert.equal(backgrounds.size, 6);
    }
    await page.locator('#appearance-accent').selectOption('emerald');
    for (const font of ['Georgia', 'Arial', 'Inter', 'Roboto', 'Times New Roman']) {
      await page.locator('#appearance-font').selectOption(font);
      const css = await page.locator('.appearance-preview').evaluate(el => getComputedStyle(el).fontFamily);
      assert.ok(css.includes(font));
      if (['Inter', 'Roboto'].includes(font)) {
        assert.ok(await page.evaluate(async name => (await document.fonts.load('16px ' + name, 'Юридический')).length > 0, font));
      }
    }
    await page.locator('#appearance-font').selectOption('Inter');
    await page.getByRole('button', {name: 'Крупный'}).click();
    assert.equal(await page.locator('#appearance-size').inputValue(), '20');
    await page.locator('#appearance-size').focus();
    await page.keyboard.press('End');
    assert.equal(await page.locator('#appearance-size').inputValue(), '22');
    await page.getByRole('button', {name: 'Основание', exact: true}).click();
    assert.equal(await page.locator('#appearance-preview-source').isVisible(), true);
    await page.getByRole('checkbox', {name: 'Уменьшить анимацию'}).check();
    assert.equal(await page.locator('html').getAttribute('data-motion'), 'reduced');
    if (output) await page.screenshot({path: path.join(output, 'appearance-dark.png')});
    await page.keyboard.press('Escape');
    assert.equal(await dialog.getAttribute('open'), null);
    await page.waitForFunction(() => document.activeElement.id === 'open-appearance');

    await page.reload();
    assert.equal(await theme(), 'dark');
    assert.equal(await page.locator('html').evaluate(el => getComputedStyle(el).fontSize), '22px');
    for (const width of [1440, 1024, 390, 320]) {
      await page.setViewportSize({width, height: 844});
      if (width <= 900) await page.locator('#open-documents').click();
      if (await page.locator('#all-docs').isVisible()) await page.locator('#all-docs').click();
      const item = page.locator('#doc-list button').filter({hasText: 'НК ст284'}).first();
      await item.click();
      await page.locator('#doc-text').waitFor({state: 'visible'});
      assert.ok((await page.locator('#doc-text').textContent()).length > 30000);
      assert.ok(await page.locator('#doc-text').evaluate(el => el.scrollHeight > el.clientHeight && el.scrollWidth <= el.clientWidth + 1));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      if (width <= 900) await page.locator('#close-mobile-panel').click();
      await open.click();
      assert.ok(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1));
      await page.getByRole('button', {name: 'Закрыть настройки'}).click();
      console.log('PASS width', width);
    }
    await open.click();
    await page.getByRole('button', {name: 'Сбросить настройки'}).click();
    assert.equal(await mode.inputValue(), 'system');
    assert.equal(await page.locator('#appearance-size').inputValue(), '16');
    assert.equal(await page.locator('#appearance-accent').inputValue(), 'psb');
    assert.equal(await page.locator('#appearance-font').inputValue(), 'Arial');
    assert.equal(await theme(), 'dark');
    await page.emulateMedia({colorScheme: 'light', reducedMotion: 'reduce'});
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
    assert.equal(await page.locator('html').getAttribute('data-motion'), 'reduced');
    assert.deepEqual(errors, []);
    console.log('PASS appearance, contrast, storage, keyboard, responsive document view and reduced motion');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
