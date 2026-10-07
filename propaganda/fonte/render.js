// Renderiza comp.html quadro a quadro. Uso: node render.js <fps> <saida.mp4|dir> [t1,t2,... para stills]
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const path = require('path');
(async () => {
  const fps = Number(process.argv[2] || 30), out = process.argv[3], stills = process.argv[4];
  const browser = await chromium.launch({args: ['--allow-file-access-from-files']});
  const page = await browser.newPage({viewport: {width: 1080, height: 1920}});
  page.on('console', m => console.log('page:', m.text()));
  page.on('pageerror', e => console.log('ERR', e.message));
  await page.goto('file://' + path.join(__dirname, 'comp.html'));
  await page.evaluate(() => window.ready());
  const D = await page.evaluate(() => window.DURATION);
  if (stills) {
    for (const t of stills.split(',').map(Number)) {
      await page.evaluate(t => renderFrame(t), t);
      await page.screenshot({path: path.join(out, `still_${t.toFixed(2)}.jpg`), type: 'jpeg', quality: 85});
    }
    await browser.close(); return;
  }
  const N = Math.round(D * fps);
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-r', String(fps), out], {stdio: ['pipe', 'inherit', 'inherit']});
  const t0 = Date.now();
  for (let i = 0; i < N; i++) {
    await page.evaluate(t => renderFrame(t), i / fps);
    const buf = await page.screenshot({type: 'jpeg', quality: 95});
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 120 === 0) console.log(`frame ${i}/${N} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
