import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, '..');
const projectRoot = resolve(webRoot, '..');
const temporaryOutput = mkdtempSync(join(tmpdir(), 'ipr-ui-build-'));
const angularExecutable = join(
  webRoot,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'ng.cmd' : 'ng',
);
const destination = join(projectRoot, 'src', 'pr_reviewer', 'web', 'static');

function collectReferencedAssets(browserOutput) {
  const assets = new Set(['index.html']);
  const queue = ['index.html'];
  const htmlAssetPattern = /(?:src|href)=["']([^"'?#]+)["']/g;
  const modulePattern = /["']\.\/([^"'?#]+\.js)["']/g;

  while (queue.length) {
    const relativePath = queue.shift();
    const sourcePath = join(browserOutput, relativePath);
    if (!existsSync(sourcePath)) {
      throw new Error(`Angular output references a missing asset: ${relativePath}`);
    }
    if (!relativePath.endsWith('.html') && !relativePath.endsWith('.js')) continue;

    const content = readFileSync(sourcePath, 'utf8');
    const patterns = relativePath.endsWith('.html')
      ? [htmlAssetPattern, modulePattern]
      : [modulePattern];
    for (const pattern of patterns) {
      pattern.lastIndex = 0;
      for (const match of content.matchAll(pattern)) {
        const referenced = match[1].replace(/^\.\//, '');
        if (referenced.startsWith('http:') || referenced.startsWith('https:')) continue;
        if (!/\.(?:css|ico|js|json|png|svg|webp|woff2?)$/i.test(referenced)) continue;
        if (!assets.has(referenced)) {
          assets.add(referenced);
          queue.push(referenced);
        }
      }
    }
  }
  return [...assets];
}

try {
  const build = spawnSync(
    angularExecutable,
    ['build', `--output-path=${temporaryOutput}`],
    { cwd: webRoot, stdio: 'inherit' },
  );
  if (build.status !== 0) process.exit(build.status ?? 1);

  const browserOutput = join(temporaryOutput, 'browser');
  if (!existsSync(join(browserOutput, 'index.html'))) {
    throw new Error('Angular build completed without browser/index.html');
  }

  const assets = collectReferencedAssets(browserOutput);
  rmSync(destination, { recursive: true, force: true });
  mkdirSync(destination, { recursive: true });
  for (const relativePath of assets) {
    const target = join(destination, relativePath);
    mkdirSync(dirname(target), { recursive: true });
    cpSync(join(browserOutput, relativePath), target);
  }
  console.log(`Embedded ${assets.length} UI assets in ${destination}`);
} finally {
  rmSync(temporaryOutput, { recursive: true, force: true });
}
