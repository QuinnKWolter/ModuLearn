import {build} from 'esbuild';
import {readFile, writeFile} from 'node:fs/promises';
await build({entryPoints:['static_src/tours/controller.js'], bundle:true, minify:true, format:'iife', target:'es2020', outfile:'static/js/tours.generated.js',
  banner:{js:'/* Driver.js license: tours.generated.js.LICENSE.txt */'}});
const license = await readFile('node_modules/driver.js/license', 'utf8').catch(() => readFile('node_modules/driver.js/LICENSE', 'utf8'));
await writeFile('static/js/tours.generated.js.LICENSE.txt', license);
