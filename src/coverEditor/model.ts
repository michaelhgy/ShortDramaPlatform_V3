/** Independent cover state. Integration adapters own disk/API persistence. */
export type CoverKind = 'drama' | 'sheep';
export interface TextLayer {
  id: string; text: string; styleId: string; x: number; y: number;
  width: number; height?: number; fontSize: number; rotation: number;
  align: 'left' | 'center' | 'right'; verticalAlign?: 'top' | 'middle' | 'bottom';
  background: string; backgroundAlpha: number;
}
export interface CoverVersion {
  id: string; image: string; sourceImage: string; layers: TextLayer[]; createdAt: string;
}
export interface CoverSet { original: string; versions: CoverVersion[]; activeId: string }
export interface CoverProject { schema: 1; drama: CoverSet; sheep: CoverSet; sheepCustomOriginal?: boolean }
export const MAX_VERSIONS = 3;
export const MAX_TEMPLATES = 5;
export interface CoverTemplate {
  id: string; name: string; width: number; height: number; layers: TextLayer[]; createdAt: string;
}
const clone = <T>(v: T): T => structuredClone(v);
const emptySet = (): CoverSet => ({ original: '', versions: [], activeId: 'original' });
export function createProject(original = ''): CoverProject {
  return { schema: 1, drama: { ...emptySet(), original }, sheep: { ...emptySet(), original } };
}
export function activeImage(set: CoverSet): string {
  return set.versions.find(v => v.id === set.activeId)?.image || set.original;
}
export function replaceOriginal(project: CoverProject, kind: CoverKind, image: string): CoverProject {
  if (!image) throw new Error('请先选择有效的图片。');
  const next = clone(project);
  next[kind].original = image; next[kind].activeId = 'original';
  if (kind === 'sheep') next.sheepCustomOriginal = true;
  // Seed once; replacing a drama original must not overwrite an independent sheep cover.
  if (kind === 'drama' && !next.sheep.original && !next.sheep.versions.length) next.sheep.original = image;
  return next;
}
export function saveVersion(project: CoverProject, kind: CoverKind, version: CoverVersion, use = false, overwriteId?: string): CoverProject {
  if (!version.image || !version.sourceImage) throw new Error('请先上传原图并完成预览。');
  const next = clone(project), set = next[kind];
  const index = overwriteId ? set.versions.findIndex(v => v.id === overwriteId) : -1;
  if (overwriteId && index < 0) throw new Error('要覆盖的版本不存在。');
  if (index < 0 && set.versions.length >= MAX_VERSIONS) throw new Error('已保存 3 个修改版。请删除一个后再另存，或选中已有修改版后点击“保存使用”。');
  const saved = clone(version);
  if (index >= 0) { saved.id = overwriteId!; set.versions[index] = saved; }
  else {
    if (saved.id === 'original' || set.versions.some(v => v.id === saved.id)) throw new Error('版本编号重复。');
    set.versions.push(saved);
  }
  if (use) set.activeId = saved.id;
  return next;
}
export function selectVersion(project: CoverProject, kind: CoverKind, id: string): CoverProject {
  const next = clone(project), set = next[kind];
  if (id !== 'original' && !set.versions.some(v => v.id === id)) throw new Error('封面版本不存在。');
  if (id === 'original' && !set.original) throw new Error('这部剧还没有原始封面，请先上传图片。');
  set.activeId = id; return next;
}
export function deleteVersion(project: CoverProject, kind: CoverKind, id: string): CoverProject {
  if (id === 'original') throw new Error('原始封面可替换，不能作为修改版删除。');
  const next = clone(project), set = next[kind];
  set.versions = set.versions.filter(v => v.id !== id);
  if (set.activeId === id) set.activeId = 'original';
  return next;
}

export function addTemplate(templates: CoverTemplate[], template: CoverTemplate): CoverTemplate[] {
  if (templates.length >= MAX_TEMPLATES) throw new Error('已保存 5 个模板，请先删除不需要的模板。');
  if (!template.name.trim()) throw new Error('请填写模板名称。');
  if (!template.layers.length) throw new Error('请先添加文字，再保存模板。');
  if (template.width <= 0 || template.height <= 0) throw new Error('请先选择封面图片。');
  if (templates.some(t => t.id === template.id)) throw new Error('模板编号重复。');
  return [...clone(templates), { ...clone(template), name: template.name.trim() }];
}
export function applyTemplate(template: CoverTemplate, width: number, height: number): TextLayer[] {
  if (width <= 0 || height <= 0 || template.width <= 0 || template.height <= 0) throw new Error('模板或封面尺寸无效。');
  const sx = width / template.width, sy = height / template.height;
  return template.layers.map(layer => ({ ...clone(layer), x: layer.x * sx, y: layer.y * sy,
    width: layer.width * sx, height: layer.height === undefined ? undefined : layer.height * sy,
    fontSize: layer.fontSize * Math.min(sx, sy) }));
}

/** Resize in local axes; the opposite edge/corner stays anchored even when rotated. */
export function resizeTextBox(layer: TextLayer, height: number, handle: string, dx: number, dy: number): TextLayer {
  const angle = layer.rotation * Math.PI / 180, cos = Math.cos(angle), sin = Math.sin(angle);
  const lx = dx * cos + dy * sin, ly = -dx * sin + dy * cos;
  let left = -layer.width / 2, right = layer.width / 2, top = -height / 2, bottom = height / 2;
  if (handle.includes('w')) left = Math.min(right - 60, left + lx);
  if (handle.includes('e')) right = Math.max(left + 60, right + lx);
  if (handle.includes('n')) top = Math.min(bottom - 24, top + ly);
  if (handle.includes('s')) bottom = Math.max(top + 24, bottom + ly);
  const shiftX = (left + right) / 2, shiftY = (top + bottom) / 2;
  const w = right - left, h = bottom - top;
  return { ...layer, width: w, height: h,
    x: layer.x + layer.width / 2 + shiftX * cos - shiftY * sin - w / 2,
    y: layer.y + height / 2 + shiftX * sin + shiftY * cos - h / 2 };
}
