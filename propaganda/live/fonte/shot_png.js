// Salva um PNG (com transparência) de uma página local servida em http://ad.local/
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path');
const ROOT = __dirname;
const [page_, w, h, dpr, out] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({viewport: {width: +w, height: +h}, deviceScaleFactor: +dpr});
  await ctx.route('http://ad.local/**', r => { let f = path.join(ROOT, decodeURIComponent(new URL(r.request().url()).pathname)); try { f = fs.realpathSync(f); } catch (e) { return r.fulfill({status: 404}); }
    r.fulfill({status: 200, contentType: {'.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.woff2': 'font/woff2'}[path.extname(f)] || 'application/octet-stream', body: fs.readFileSync(f)}); });
  const p = await ctx.newPage(); await p.goto('http://ad.local/' + page_);
  await p.waitForFunction(() => window.ready); await p.evaluate(() => window.ready());
  await p.screenshot({path: out, omitBackground: true}); await b.close();
})().catch(e => { console.error(e); process.exit(1); });
