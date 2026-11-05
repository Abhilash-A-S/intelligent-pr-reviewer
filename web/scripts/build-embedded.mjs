import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDirectory, '..');
const projectRoot = resolve(webRoot, '..');
const temporaryOutput = mkdtempSync(join(tmpdir(), 'ipr-ui-build-'));
const angularCli = join(webRoot, 'node_modules', '@angular', 'cli', 'bin', 'ng.js');
const destination = join(projectRoot, 'src', 'pr_reviewer', 'web', 'static');

function collectReferencedAssets(browserOutput) {
  const assets = new Set(['index.html']);
  const queue = ['index.html'];
  const htmlAssetPattern = /(?:src|href)=["']([^"'?#]+)["']/g;
  const cssAssetPattern = /url\(\s*[\"']?([^\"')?#]+)[\"']?\s*\)/g;
  const modulePattern = /["']\.\/([^"'?#]+\.js)["']/g;

  while (queue.length) {
    const relativePath = queue.shift();
    const sourcePath = join(browserOutput, relativePath);
    if (!existsSync(sourcePath)) {
      throw new Error(`Angular output references a missing asset: ${relativePath}`);
    }
    if (!/\.(html|js|css)$/.test(relativePath)) continue;

    const content = readFileSync(sourcePath, 'utf8');
    const patterns = relativePath.endsWith('.html')
      ? [htmlAssetPattern, modulePattern]
      : relativePath.endsWith('.css') ? [cssAssetPattern] : [modulePattern];
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

function collectFiles(directory) {
  return readdirSync(directory, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(directory, join(entry.parentPath, entry.name)).replaceAll('\\', '/'))
    .sort();
}

try {
  if (!existsSync(angularCli)) {
    throw new Error(
      `Angular CLI was not found at ${angularCli}. Run npm install in the web directory first.`,
    );
  }
  const build = spawnSync(
    process.execPath,
    [angularCli, 'build', `--output-path=${temporaryOutput}`],
    { cwd: webRoot, stdio: 'inherit' },
  );
  if (build.error) {
    throw new Error(`Angular build could not be started: ${build.error.message}`, {
      cause: build.error,
    });
  }
  if (build.status !== 0) {
    throw new Error(`Angular build failed with exit code ${build.status ?? 'unknown'}.`);
  }

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
  const expectedAssets = [...assets].sort();
  const embeddedAssets = collectFiles(destination);
  if (JSON.stringify(embeddedAssets) !== JSON.stringify(expectedAssets)) {
    const unexpected = embeddedAssets.filter((asset) => !expectedAssets.includes(asset));
    const missing = expectedAssets.filter((asset) => !embeddedAssets.includes(asset));
    throw new Error(
      `Embedded asset verification failed. Unexpected: ${unexpected.join(', ') || 'none'}; missing: ${missing.join(', ') || 'none'}`,
    );
  }
  console.log(`Embedded and verified ${assets.length} UI assets in ${destination}`);
} finally {
  rmSync(temporaryOutput, { recursive: true, force: true });
}
