/** Build a single offline HTML. Does not run or rebuild the business application. */
const fs = require('node:fs'), path = require('node:path'), esbuild = require('esbuild');
const root = path.resolve(__dirname, '../..');
const production = process.argv.includes('--production');
const out = path.resolve(root, production ? 'public' : process.argv[2] || 'local-test-output/cover-editor-preview-20261026');
const cover = production ? '' : process.argv[3];
const coverData = cover ? 'data:image/jpeg;base64,' + fs.readFileSync(cover).toString('base64') : '';
const built = esbuild.buildSync({ entryPoints: [path.join(__dirname, 'main.ts')], bundle: true, write: false, format: 'iife', target: 'es2022', define: { __DEMO_COVER__: JSON.stringify(coverData) } });
let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
html = html.replace('</head>', '<style>' + fs.readFileSync(path.join(__dirname, 'style.css'), 'utf8') + '</style></head>');
html = html.replace('</body>', '<script>' + built.outputFiles[0].text.replace(/<\/script/gi, '<\\/script') + '</script></body>');
const filename = production ? 'cover-editor.html' : 'index.html';
fs.mkdirSync(out, { recursive: true }); fs.writeFileSync(path.join(out, filename), html);
if(production) fs.copyFileSync(path.join(root,'src/coverEditor/simpleFlowerStyles.json'),path.join(out,'cover-flower-styles.json'));
console.log(JSON.stringify({ preview: path.join(out, filename), bytes: Buffer.byteLength(html) }));
