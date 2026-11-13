import stylesData from '../../src/coverEditor/simpleFlowerStyles.json';
import { activeImage, addTemplate, applyTemplate, createProject, deleteVersion, replaceOriginal, resizeTextBox, saveVersion, selectVersion, type CoverKind, type CoverProject, type CoverTemplate, type TextLayer } from '../../src/coverEditor/model';
import { drawLayer, layerBounds, loadImage, prepareFlowerStyles, renderCover, renderText, type FlowerStyle } from '../../src/coverEditor/renderer';
import { FlowerLibraryUI, type Library, type ManagedFlowerStyle } from '../../src/coverEditor/flowerLibraryUI';
import { confirmAction, confirmationOpen } from '../../src/coverEditor/dialog';
declare const __DEMO_COVER__: string;
let styles = stylesData as unknown as ManagedFlowerStyle[];
let flowerLibrary: FlowerLibraryUI;
const query = new URLSearchParams(location.search), remoteId = query.get('dramaId') || '';
const remote = /^[a-f0-9]+$/.test(remoteId), remoteRoot = `/api/v2/cover-editor/dramas/${remoteId}`;
let projectRevision = 0, templateRevision = 0, lastProject = '', lastTemplates = '';
if (remote) document.body.classList.add('embedded');
async function request<T>(url: string, body?: unknown): Promise<T> {
  if (url.startsWith('/api/v2/cover-editor/flowers')) url += '?compact=1';
  const response = await fetch(url, { method: body === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json' }, cache: 'no-store', ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const value = await response.json(); if (!response.ok) throw new Error(value.error || '封面保存失败'); return value;
}
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const input = (id: string) => $<HTMLInputElement>(id);
const copy = $<HTMLTextAreaElement>('copy'), canvas = $<HTMLCanvasElement>('cover');
let project: CoverProject = createProject(__DEMO_COVER__), kind: CoverKind = 'drama', editingId = 'original';
if (remote && query.get('kind') === 'sheep') kind = 'sheep';
let source = '', image: HTMLImageElement | null = null, layers: TextLayer[] = [], selectedId = '', dirty = false;
let loadToken = 0, persistenceFailed = false, selectionVisible = true, saving = false;
let sceneReady = false;
let styleLoading = false;
let templates: CoverTemplate[] = [];
const chosen = () => layers.find(l => l.id === selectedId);
const uuid = () => crypto.randomUUID();
const label = () => kind === 'drama' ? '剧集封面' : '羊头封面';
function notify(message: string) { $('toast').textContent = message; $('toast').classList.add('visible'); clearTimeout((notify as any).timer); (notify as any).timer = setTimeout(() => $('toast').classList.remove('visible'), 4300); }
function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => { const r = indexedDB.open('v3-cover-flower-preview', 1); r.onupgradeneeded = () => r.result.createObjectStore('projects'); r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });
}
async function persist() {
  const projectSnapshot = structuredClone(project), templateSnapshot = structuredClone(templates);
  try {
    if (remote) {
      if (JSON.stringify(projectSnapshot) !== lastProject) {
        const saved = await request<{project: CoverProject; revision: number}>(remoteRoot, { project: projectSnapshot, revision: projectRevision });
        project = saved.project; projectRevision = saved.revision; lastProject = JSON.stringify(project);
        window.parent.postMessage({ type: 'v3-cover-saved', dramaId: remoteId }, location.origin);
        void flowerLibrary?.refresh().catch(() => {});
      }
      if (JSON.stringify(templateSnapshot) !== lastTemplates) {
        const saved = await request<{templates: CoverTemplate[]; revision: number}>('/api/v2/cover-editor/templates', { templates: templateSnapshot, revision: templateRevision });
        templates = saved.templates; templateRevision = saved.revision; lastTemplates = JSON.stringify(templates);
      }
      $('save-state').textContent = '已保存到软件'; persistenceFailed = false; return true;
    }
    const db = await database();
    await new Promise<void>((resolve, reject) => { const tx = db.transaction('projects', 'readwrite'); tx.objectStore('projects').put(projectSnapshot, 'demo'); tx.objectStore('projects').put(templateSnapshot, 'templates'); tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error); });
    db.close(); persistenceFailed = false; $('save-state').textContent = '已存到本浏览器';
    return true;
  } catch (error) { persistenceFailed = true; $('save-state').textContent = '保存失败，请保留编辑'; notify(remote ? (error as Error).message : '浏览器本地保存失败；当前内容仍在，可先导出图片。'); return false; }
}
function newLayer(): TextLayer {
  const w = image?.naturalWidth || 540, h = image?.naturalHeight || 720;
  return { id: uuid(), text: '主页看全集', styleId: styles.find(s => s.enabled !== false && s.name === '复古淡黄花字')?.id || styles.find(s => s.enabled !== false)?.id || styles[0].id,
    x: w * .08, y: h * .70, width: w * .84, height: h * .21, fontSize: w * .085, rotation: 0, align: 'center', verticalAlign: 'middle', background: '#111827', backgroundAlpha: 0 };
}
function controls() {
  const layer = chosen(); copy.value = layer?.text || ''; copy.disabled = !layer;
  input('font-size').value = String(Math.round(layer?.fontSize || 40)); input('rotation').value = String(layer?.rotation || 0);
  $<HTMLSelectElement>('align').value = layer?.align || 'center'; input('background').value = layer?.background || '#111827';
  $<HTMLSelectElement>('vertical-align').value = layer?.verticalAlign || 'middle';
  input('background-alpha').value = String(Math.round((layer?.backgroundAlpha || 0) * 100)); $('alpha-label').textContent = layer?.backgroundAlpha ? `${Math.round(layer.backgroundAlpha * 100)}%` : '透明';
  const select = $<HTMLSelectElement>('layer-select'); select.replaceChildren();
  layers.forEach((l, i) => { const option = new Option(`${i + 1}. ${l.text.slice(0, 8) || '空白文字'}`, l.id); option.selected = l.id === selectedId; select.add(option); });
  document.querySelectorAll<HTMLButtonElement>('.style-card').forEach(b => b.classList.toggle('selected', b.dataset.id === layer?.styleId));
  $('selection').hidden = !layer || !selectionVisible;
  $('toggle-selection').textContent = selectionVisible ? '隐藏选框' : '显示选框';
}
function updateButtons() {
  const original = editingId === 'original',busy=saving||styleLoading;
  for (const id of ['text-editor', 'flower-section', 'template-actions', 'preview-hint', 'center-x', 'center-y', 'delete-version']) $(id).hidden = original;
  $('upload').hidden = !original;
  $('copy-original').hidden = !original || kind !== 'sheep';
  $<HTMLButtonElement>('delete-version').disabled = original || saving;
  for (const id of ['save', 'save-use', 'export', 'upload', 'copy-original']) $<HTMLButtonElement>(id).disabled = !image || busy;
  // Upload remains the only useful action when there is no source image yet.
  $<HTMLButtonElement>('upload').disabled = saving;
  $<HTMLButtonElement>('copy-original').disabled = saving || !project.drama.original;
  $('export').hidden = !image;
  $('save-use').hidden = !image || original && project[kind].activeId === 'original';
  $('save').hidden = !image || original && project[kind].versions.length >= 3;
  $('save-use').textContent = original ? '设为使用' : '保存使用';
  $<HTMLButtonElement>('save-template').disabled = !image || !layers.length || busy;
  $<HTMLButtonElement>('apply-template').disabled = !image || busy || !$<HTMLSelectElement>('template-select').value;
  $<HTMLButtonElement>('delete-template').disabled = saving || !$<HTMLSelectElement>('template-select').value;
  $('editing-label').textContent = `${label()} · ${editingId === 'original' ? '原图' : '修改版'}${dirty ? ' · 有未保存编辑' : ''}`;
}
function draw() {
  if (!sceneReady) return;
  try {
    const output = renderCover(image, layers, styles);
    canvas.width = output.width; canvas.height = output.height; canvas.getContext('2d')!.drawImage(output, 0, 0);
    const layer = chosen();
    $('selection').hidden = !layer || !selectionVisible;
    $('toggle-selection').textContent = selectionVisible ? '隐藏选框' : '显示选框';
    if (layer) {
      const bounds = layerBounds(layer), ratio = canvas.getBoundingClientRect().width / canvas.width;
      Object.assign($('selection').style, { left: `${layer.x * ratio}px`, top: `${layer.y * ratio}px`, width: `${bounds.width * ratio}px`, height: `${bounds.height * ratio}px`, transform: `rotate(${layer.rotation}deg)` });
    }
    updateButtons();
  } catch (error) { notify((error as Error).message); }
}
function versions() {
  const set = project[kind], container = $('versions'); container.replaceChildren();
  const entries = [{ id: 'original', image: set.original, name: '原始封面' }, ...set.versions.map((v, i) => ({ ...v, name: `修改版 ${i + 1}` }))];
  for (const item of entries) {
    const button = document.createElement('button'); button.className = `version${editingId === item.id ? ' selected' : ''}`; button.dataset.version = item.id;
    if (item.image) { const img = new Image(); img.src = item.image; img.alt = item.name; button.append(img); }
    const text = document.createElement('div'), title = document.createElement('span'); title.textContent = item.name; text.append(title);
    if (set.activeId === item.id) { const tag = document.createElement('small'); tag.textContent = '✓ 使用中'; text.append(tag); }
    button.append(text); button.onclick = async () => { if (await allowDiscard()) void openVersion(item.id); }; container.append(button);
  }
  for (let i = set.versions.length; i < 3; i++) { const placeholder = document.createElement('div'); placeholder.className = 'empty-version'; placeholder.textContent = `修改版 ${i + 1}`; container.append(placeholder); }
  $('active-covers').replaceChildren();
  for (const type of ['drama', 'sheep'] as CoverKind[]) {
    const button = document.createElement('button'); button.className = 'cover-card'; button.dataset.kind = type;
    const currentImage = activeImage(project[type]);
    const img = new Image(); img.alt = type === 'drama' ? '剧集当前使用封面' : '羊头当前使用封面';
    if (currentImage) { img.src = currentImage; button.append(img); }
    const title = document.createElement('b'); title.textContent = type === 'drama' ? '剧集封面' : '羊头封面';
    const desc = document.createElement('small'); desc.textContent = !currentImage ? '未设置封面，请上传' : project[type].activeId === 'original' ? '正在使用原图' : '正在使用修改版';
    button.append(title, desc); button.onclick = () => switchKind(type); $('active-covers').append(button);
  }
}
async function allowDiscard(): Promise<boolean> { if (saving) { notify('正在保存，请稍候再切换或关闭。'); return false; } return !dirty || await confirmAction('当前文字编辑还没有保存，确定放弃吗？','放弃未保存的修改','放弃修改'); }
async function openVersion(id: string, createFirst = false) {
  flowerLibrary?.cancelPendingStyle();
  const token = ++loadToken, version = project[kind].versions.find(v => v.id === id);
  const nextSource = version?.sourceImage || project[kind].original;
  try {
    const usedStyles=new Set((version?.layers||[]).map(l=>l.styleId));
    const [nextImage] = await Promise.all([nextSource ? loadImage(nextSource) : null,prepareFlowerStyles(styles.filter(s=>usedStyles.has(s.id)))]);
    if (token !== loadToken) return;
    if (nextImage && (nextImage.naturalWidth * nextImage.naturalHeight > 24_000_000 || nextImage.naturalWidth > 8192 || nextImage.naturalHeight > 8192)) throw new Error('封面图片过大，请选择较小图片。');
    source = nextSource; image = nextImage; editingId = id; layers = structuredClone(version?.layers || []); dirty = false; sceneReady = true;
    selectedId = layers[0]?.id || ''; selectionVisible = !!layers.length; controls(); versions(); draw();
    if (createFirst && id === 'original' && image && !project[kind].versions.length) await save(false);
  } catch (error) { notify((error as Error).message); }
}
async function switchKind(next: CoverKind) {
  if (next === kind || !await allowDiscard()) return;
  kind = next; $('tab-drama').classList.toggle('active', kind === 'drama'); $('tab-sheep').classList.toggle('active', kind === 'sheep');
  const set = project[kind];
  void openVersion(set.activeId === 'original' && set.versions.length ? set.versions[0].id : set.activeId, true);
}
function change(callback: (layer: TextLayer) => void) { const layer = chosen(); if (!layer || editingId === 'original') return; callback(layer); dirty = true; draw(); }
async function save(use: boolean) {
  if (saving) return;
  const previous = project;
  try {
    if (!image) throw new Error('请先上传原始封面。');
    saving = true; updateButtons();
    if (use && !dirty) {
      project = selectVersion(project, kind, editingId);
      if (!await persist()) { project = previous; return; }
      versions(); notify('已设为本套使用封面'); return;
    }
    const overwrite = use && editingId !== 'original';
    const id = overwrite ? editingId : uuid();
    const savedLayers = editingId === 'original' ? [newLayer()] : layers;
    const usedStyles = new Set(savedLayers.map(l=>l.styleId));
    await prepareFlowerStyles(styles.filter(s=>usedStyles.has(s.id)));
    project = saveVersion(project, kind, { id, image: renderCover(image, savedLayers, styles).toDataURL('image/png'), sourceImage: source, layers: savedLayers, createdAt: new Date().toISOString() }, use, overwrite ? editingId : undefined);
    if (!await persist()) { project = previous; return; }
    editingId = id; layers = savedLayers; selectedId = layers[0]?.id || ''; selectionVisible = !!layers.length; dirty = false; controls(); versions(); draw();
    notify(use ? '已保存当前修改并使用' : '已另存新版，当前使用的封面不变');
  } catch (error) { project = previous; notify((error as Error).message); }
  finally { saving = false; updateButtons(); }
}

function templateControls(selected = $<HTMLSelectElement>('template-select').value) {
  const select = $<HTMLSelectElement>('template-select'); select.replaceChildren(new Option('选择模板', ''));
  templates.forEach(t => select.add(new Option(t.name, t.id))); select.value = selected;
  $('template-count').textContent = `${templates.length} / 5`; updateButtons();
}
async function saveTemplate() {
  if (saving) return;
  if (!image || !layers.length) return notify('请先添加文字，再保存模板。');
  const previous = templates;
  try {
    saving = true; updateButtons();
    const id = uuid(), name = input('template-name').value.trim() || `模板 ${templates.length + 1}`;
    // Store text/style/geometry only, never the source or rendered cover image.
    const readyLayers = layers.map(layer => ({ ...layer, height: layerBounds(layer).height }));
    templates = addTemplate(templates, { id, name, width: image.naturalWidth, height: image.naturalHeight, layers: readyLayers, createdAt: new Date().toISOString() });
    if (!await persist()) { templates = previous; return; }
    input('template-name').value = ''; templateControls(id); notify('模板已保存，可套用到其他封面后微调');
  } catch (error) { templates = previous; notify((error as Error).message); }
  finally { saving = false; updateButtons(); }
}
async function download() {
  try {
    const output = renderCover(image, layers, styles), filename = `${label()}-${editingId === 'original' ? '原始封面' : '修改版'}.png`;
    const dataUrl = output.toDataURL('image/png');
    const requestId = crypto.randomUUID();
    const result = await new Promise<{ saved?: boolean; canceled?: boolean; native?: boolean; error?: string }>((resolve, reject) => {
      const timer = setTimeout(() => { window.removeEventListener('message', onResult); reject(new Error('系统保存对话框没有响应，请重试。')); }, 120000);
      const onResult = (event: MessageEvent) => {
        if (event.origin !== location.origin || event.source !== window.parent || event.data?.type !== 'v3-cover-save-result' || event.data.requestId !== requestId) return;
        clearTimeout(timer); window.removeEventListener('message', onResult); resolve(event.data);
      };
      window.addEventListener('message', onResult);
      window.parent.postMessage({ type: 'v3-cover-save-request', requestId, dataUrl, filename }, location.origin);
    });
    if (result.native) {
      if (result.canceled) { notify('已取消保存封面。'); return; }
      if (result.error) throw new Error(result.error);
      if (!result.saved) throw new Error('封面未保存，请重试。');
    } else {
      const blob = await (await fetch(dataUrl)).blob(), url = URL.createObjectURL(blob), a = document.createElement('a');
      a.download = filename; a.href = url; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    void flowerLibrary.recordExport(layers.map(l => l.styleId)); notify('封面已保存。');
  } catch (error) { notify((error as Error).message); }
}
async function init() {
  const closeEditor=async()=>{if(!confirmationOpen()&&await allowDiscard())window.parent.postMessage({ type: 'v3-cover-close-allowed' }, location.origin);};
  window.addEventListener('message', e => { if (remote && e.origin === location.origin && e.source === window.parent && e.data?.type === 'v3-cover-close-request')void closeEditor(); });
  window.addEventListener('keydown', e => { if (remote && e.key === 'Escape' && $('flower-manager').hidden && !confirmationOpen()){e.preventDefault();void closeEditor();} });
  const startupError=(message:string)=>{$('startup-message').textContent=message;$('startup-retry').hidden=false;};
  $('startup-retry').onclick=()=>location.reload();
  let initialLibrary:Library|undefined;
  try {
    if (remote) {
      const [saved, common, library] = await Promise.all([request<{project: CoverProject; revision: number}>(remoteRoot), request<{templates: CoverTemplate[]; revision: number}>('/api/v2/cover-editor/templates'),request<Library>('/api/v2/cover-editor/flowers')]);
      initialLibrary=library;
      project = saved.project; projectRevision = saved.revision; templates = common.templates; templateRevision = common.revision;
      lastProject = JSON.stringify(project); lastTemplates = JSON.stringify(templates); $('save-state').textContent = '保存到软件';
      document.querySelector('.section-title span')!.textContent = '本剧共用';
    } else {
      const db = await database(); const read = <T>(key: string, fallback: T): Promise<T> => new Promise((resolve, reject) => { const r = db.transaction('projects').objectStore('projects').get(key); r.onsuccess = () => resolve(r.result || fallback); r.onerror = () => reject(r.error); }); [project, templates] = await Promise.all([read('demo', project), read('templates', [])]); db.close();
    }
  } catch (error) { notify(remote ? (error as Error).message : '浏览器本地存储不可用，仍可预览并导出图片。'); if (remote){startupError((error as Error).message);return;} }
  $('style-count').textContent = `${styles.length} 款`; $(`tab-${kind}`).classList.add('active');
  flowerLibrary = new FlowerLibraryUI(styles,remote,request,id => {
    if (editingId === 'original') return;
    if (!image) return notify('请先上传封面图片，再添加花字。');
    if (!chosen()) { layers.push(newLayer()); selectedId = layers.at(-1)!.id; }
    selectionVisible = true; change(l => l.styleId = id); controls();
  },notify,updated => { styles = updated; },() => chosen()?.styleId || '',loading=>{styleLoading=loading;updateButtons();});
  try { await flowerLibrary.init(initialLibrary); } catch (error) { startupError(`花字库读取失败：${(error as Error).message}`); return; }
  $('tab-drama').onclick = () => switchKind('drama'); $('tab-sheep').onclick = () => switchKind('sheep');
  copy.oninput = () => change(l => l.text = copy.value);
  input('font-size').oninput = () => change(l => l.fontSize = Math.max(12, Math.min(220, Number(input('font-size').value) || 12)));
  input('rotation').oninput = () => change(l => l.rotation = Math.max(-180, Math.min(180, Number(input('rotation').value) || 0)));
  $<HTMLSelectElement>('align').onchange = () => change(l => l.align = $<HTMLSelectElement>('align').value as TextLayer['align']);
  $<HTMLSelectElement>('vertical-align').onchange = () => change(l => l.verticalAlign = $<HTMLSelectElement>('vertical-align').value as TextLayer['verticalAlign']);
  input('background').oninput = () => change(l => l.background = input('background').value);
  input('background-alpha').oninput = () => { change(l => l.backgroundAlpha = Number(input('background-alpha').value) / 100); $('alpha-label').textContent = input('background-alpha').value === '0' ? '透明' : `${input('background-alpha').value}%`; };
  $<HTMLSelectElement>('layer-select').onchange = () => { selectedId = $<HTMLSelectElement>('layer-select').value; selectionVisible = true; controls(); draw(); };
  $('add-text').onclick = () => { if (editingId === 'original') return; if (!image) return notify('请先上传封面图片。'); if (layers.length >= 6) return notify('每张封面最多添加 6 段文字。'); layers.push(newLayer()); selectedId = layers.at(-1)!.id; selectionVisible = true; dirty = true; controls(); draw(); };
  $('remove-text').onclick = () => { layers = layers.filter(l => l.id !== selectedId); selectedId = layers[0]?.id || ''; dirty = true; controls(); draw(); };
  $('save').onclick = () => void save(false); $('save-use').onclick = () => void save(true);
  $('toggle-selection').onclick = () => { selectionVisible = !selectionVisible; draw(); };
  $('center-x').onclick = () => change(l => l.x = (canvas.width - l.width) / 2);
  $('center-y').onclick = () => change(l => l.y = (canvas.height - layerBounds(l).height) / 2);
  $('save-template').onclick = () => void saveTemplate();
  $<HTMLSelectElement>('template-select').onchange = () => updateButtons();
  $('apply-template').onclick = async () => {
    const template = templates.find(t => t.id === $<HTMLSelectElement>('template-select').value);
    if (!template || !image || editingId === 'original') return;
    if (layers.length && !await confirmAction('套用模板将替换当前文字排版，封面底图保持当前图片。','套用通用模板','套用')) return;
    const next=applyTemplate(template, image.naturalWidth, image.naturalHeight).map(l => ({ ...l, id: uuid() }));
    try{await prepareFlowerStyles(styles.filter(s=>next.some(l=>l.styleId===s.id)));}catch(error){notify((error as Error).message);return;}
    layers = next;
    selectedId = layers[0]?.id || ''; selectionVisible = true; dirty = true; controls(); draw(); notify('已套用模板，可继续修改文字和位置');
  };
  $('delete-template').onclick = async () => {
    const id = $<HTMLSelectElement>('template-select').value; if (!id || !await confirmAction('已生成的封面不受影响。','删除通用模板','删除')) return;
    const previous = templates; templates = templates.filter(t => t.id !== id);
    if (!await persist()) templates = previous;
    templateControls();
  };
  $('delete-version').onclick = async () => { if (!await confirmAction(project[kind].activeId === editingId ? '删除正在使用的修改版后，将改用本套原图。' : '删除后，此修改版将从版本列表中移除。','删除修改版','删除')) return; project = deleteVersion(project, kind, editingId); await openVersion(project[kind].activeId); await persist(); };
  $('upload').onclick = async () => { if (await allowDiscard()) input('file').click(); };
  input('file').onchange = async () => {
    const file = input('file').files?.[0]; if (!file) return;
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error('请选择小于 20 MB 的封面图片。');
      const data = await new Promise<string>((resolve, reject) => { const r = new FileReader(); r.onload = () => resolve(String(r.result)); r.onerror = reject; r.readAsDataURL(file); });
      const checked = await loadImage(data); if (checked.naturalWidth * checked.naturalHeight > 24_000_000 || checked.naturalWidth > 8192 || checked.naturalHeight > 8192) throw new Error('图片过大，请使用不超过 2400 万像素且边长不超过 8192 的图片。');
      project = replaceOriginal(project, kind, data); await openVersion('original', true); await persist();
    } catch (e) { notify((e as Error).message); } finally { input('file').value = ''; }
  };
  $('copy-original').onclick = async () => { if (!project.drama.original) return notify('请先设置剧集原图。'); if (!await allowDiscard() || !await confirmAction('用剧集原图替换羊头原图，已保存的羊头修改版会保留。','复制剧集原图','复制')) return; project = replaceOriginal(project, 'sheep', project.drama.original); await openVersion('original', true); await persist(); };
  $('export').onclick = () => download();
  let drag: { x: number; y: number; layer: TextLayer; mode: string; height: number } | null = null;
  $('selection').onpointerdown = e => { const l = chosen(); if (!l) return; e.preventDefault(); drag = { x: e.clientX, y: e.clientY, layer: structuredClone(l), height: layerBounds(l).height, mode: (e.target as HTMLElement).dataset.handle || 'move' }; $('selection').setPointerCapture(e.pointerId); };
  $('selection').onpointermove = e => {
    if (!drag) return;
    const ratio = canvas.width / canvas.getBoundingClientRect().width, dx = (e.clientX - drag.x) * ratio, dy = (e.clientY - drag.y) * ratio, start = drag.layer;
    change(l => {
      if (drag!.mode !== 'move') {
        const resized = resizeTextBox(start, drag!.height, drag!.mode, dx, dy);
        if (resized.width <= canvas.width * 2 && resized.height! <= canvas.height * 2) Object.assign(l, resized);
      }
      else { l.x = Math.max(-start.width + 30, Math.min(canvas.width - 30, start.x + dx)); l.y = Math.max(0, Math.min(canvas.height - 30, start.y + dy)); }
    });
    input('font-size').value = String(Math.round(chosen()!.fontSize));
  };
  $('selection').onpointerup = $('selection').onpointercancel = () => { drag = null; };
  canvas.onpointerdown = e => { const r = canvas.getBoundingClientRect(), x = (e.clientX - r.left) * canvas.width / r.width, y = (e.clientY - r.top) * canvas.height / r.height;
    for (const l of [...layers].reverse()) { const b = layerBounds(l), angle = -l.rotation * Math.PI / 180, dx = x - l.x - b.width / 2, dy = y - l.y - b.height / 2, lx = dx * Math.cos(angle) - dy * Math.sin(angle), ly = dx * Math.sin(angle) + dy * Math.cos(angle); if (Math.abs(lx) <= b.width / 2 && Math.abs(ly) <= b.height / 2) { selectedId = l.id; selectionVisible = true; controls(); draw(); return; } }
    selectionVisible = false; draw();
  };
  document.querySelector('.preview-area')!.addEventListener('pointerdown', e => { if (e.target === e.currentTarget) { selectionVisible = false; draw(); } });
  new ResizeObserver(() => draw()).observe($('stage'));
  window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
  templateControls();
  const firstVersion = project[kind].versions[0];
  await openVersion(project[kind].activeId === 'original' && firstVersion ? firstVersion.id : project[kind].activeId, true);
  if(!sceneReady){startupError('封面无法读取，请关闭后重新选择封面，或重试。');return;}
  $('editor-workspace').hidden=false;$('startup').hidden=true;draw();
  Object.assign(window, { coverPreview: { styles, getStyles: () => styles, prepareFlowerStyles, renderText, renderCover, drawLayer, getProject: () => structuredClone(project), getLayers: () => structuredClone(layers), getTemplates: () => structuredClone(templates), getSource: () => image, ready: true } });
}
void init();
