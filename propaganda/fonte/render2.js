// Uso: node render2.js <comp.html> <w> <h> <fps> <saída: .mp4 | pasta de frames | pasta de stills> [stills t1,t2,...]
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const fs = require('fs');
const path = require('path');
(async () => {
  const [comp, w, h, fps, out, stills] = process.argv.slice(2);
  const W = Number(w), H = Number(h), F = Number(fps);
  const browser = await chromium.launch({args: ['--allow-file-access-from-files']});
  const page = await browser.newPage({viewport: {width: W, height: H}});
  page.on('pageerror', e => console.log('ERR', e.message));
  await page.goto('file://' + path.join(__dirname, comp) + `?w=${W}&h=${H}` + (process.env.CUT ? `&cut=${process.env.CUT}` : '') + (process.env.Z ? `&z=${process.env.Z}` : ''));
  const info = await page.evaluate(() => window.ready());
  fs.writeFileSync(out.endsWith('.mp4') ? out.replace(/\.mp4$/, '.sfx.json') : path.join(__dirname, 'sfx.json'), JSON.stringify(await page.evaluate(() => window.SFX || [])));
  const D = info.D || info;
  if (stills) {
    fs.mkdirSync(out, {recursive: true});
    for (const t of stills.split(',').map(Number)) {
      await page.evaluate(t => renderFrame(t), t);
      await page.screenshot({path: path.join(out, `s_${t.toFixed(2)}.jpg`), type: 'jpeg', quality: 88});
    }
    await browser.close(); return;
  }
  const N = Math.round(D * F);
  const toDir = !out.endsWith('.mp4');
  let ff;
  if (toDir) fs.mkdirSync(out, {recursive: true});
  else ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(F), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '15', '-pix_fmt', 'yuv420p', '-r', String(F), out], {stdio: ['pipe', 'inherit', 'inherit']});
  const t0 = Date.now();
  for (let i = 0; i < N; i++) {
    await page.evaluate(t => renderFrame(t), i / F);
    const buf = await page.screenshot({type: 'jpeg', quality: 95});
    if (toDir) fs.writeFileSync(path.join(out, `f${String(i).padStart(5, '0')}.jpg`), buf);
    else if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 150 === 0) console.log(`frame ${i}/${N} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  if (ff) { ff.stdin.end(); await new Promise(r => ff.on('close', r)); }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
