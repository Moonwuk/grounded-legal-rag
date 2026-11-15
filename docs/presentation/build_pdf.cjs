// Renders presentation.html into the submission PDF (16:9, one slide per page).
// Usage from the repository root: node docs/presentation/build_pdf.cjs
const path = require('node:path');
const {chromium} = require('playwright');
(async () => {
  const dir = __dirname;
  const browser = await chromium.launch();
  const page = await browser.newPage({viewport: {width: 1280, height: 720}});
  await page.goto('file://' + path.join(dir, 'presentation.html'), {waitUntil: 'networkidle'});
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({path: path.join(dir, 'grounded-legal-rag-presentation.pdf'), width: '1280px', height: '720px', printBackground: true, preferCSSPageSize: true});
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
