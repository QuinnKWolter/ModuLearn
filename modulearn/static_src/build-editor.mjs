import {build} from 'esbuild';
import {readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';

const output = 'static/js/inline-markdown.generated.js';
await build({entryPoints:['static_src/inline-markdown.js'], bundle:true, minify:true, format:'iife', target:'es2020', outfile:output,
  banner:{js:'/* Third-party licenses: inline-markdown.generated.js.LICENSE.txt */'}});

const seen = new Set(), notices = [];
async function license(name) {
  if (seen.has(name)) return;
  seen.add(name);
  const directory = path.join('node_modules', name);
  const pkg = JSON.parse(await readFile(path.join(directory, 'package.json'), 'utf8'));
  let text;
  for (const filename of ['LICENSE', 'LICENSE.txt', 'LICENSE.md', 'LICENSE-MIT.txt']) {
    try { text = await readFile(path.join(directory, filename), 'utf8'); break; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  if (!text) throw new Error(`Missing license for ${name}`);
  notices.push(`${name} ${pkg.version}\n${text.trim()}`);
  for (const dependency of Object.keys(pkg.dependencies || {})) await license(dependency);
}
for (const name of ['@codemirror/state','@codemirror/view','@codemirror/commands','@codemirror/lang-markdown','@codemirror/language','@lezer/markdown','markdown-it']) await license(name);
await writeFile(output + '.LICENSE.txt', notices.join('\n\n---\n\n') + '\n');
