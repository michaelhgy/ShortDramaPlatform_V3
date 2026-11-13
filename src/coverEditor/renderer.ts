import type { TextLayer } from './model';

export interface Paint {
  render_type: 'solid' | 'gradient' | 'texture';
  solid?: { color: number[]; alpha: number };
  gradient?: { color: number[][]; alpha: number[]; percent: number[]; angle: number; mode: string };
  texture?: { source: string; path: string; range: number; alpha: number; angle: number; scale: number; flip?: boolean[]; blend?: 'no' | 'solid' | 'gradient'; stretchMode?: string; wrapMode?: string };
}
export interface Stroke { enable: boolean; width: number; alpha: number; content: Paint }
export interface Shadow { enable: boolean; angle: number; distance: number; feather?: number; diffuse?: number; alpha: number; content: Paint; strokes?: Stroke[] }
export interface FlowerStyle {
  id: string; name: string; icon: string;
  style: { fill: { alpha: number; content: Paint }; strokes: Stroke[]; shadows: Shadow[]; inner_shadows: Shadow[] };
}
interface Glyph { char: string; x: number; y: number; width: number }
export interface LayerBounds { width: number; height: number }
const makeCanvas = (w: number, h: number) => {
  const canvas = document.createElement('canvas'); canvas.width = Math.ceil(w); canvas.height = Math.ceil(h); return canvas;
};
const font = (size: number) => `900 ${size}px "Microsoft YaHei", "Noto Sans SC", sans-serif`;
const rgba = (color: number[], alpha = 1) => `rgba(${color.slice(0, 3).map(c => Math.round(Math.min(1, Math.max(0, c)) * 255)).join(',')},${Math.min(1, Math.max(0, alpha))})`;
const textureImages = new Map<string, HTMLImageElement>();
const textureLoads = new Map<string, Promise<void>>();
const textureTiles = new WeakMap<Paint, Map<number, HTMLCanvasElement>>();
const textureInk = new WeakMap<HTMLCanvasElement, {x:number;y:number;width:number;height:number}>();
function textureInkBounds(tile:HTMLCanvasElement) {
  let bounds=textureInk.get(tile);if(bounds)return bounds;
  const data=tile.getContext('2d')!.getImageData(0,0,tile.width,tile.height).data;
  let left=tile.width,top=tile.height,right=-1,bottom=-1;
  for(let y=0;y<tile.height;y++)for(let x=0;x<tile.width;x++)if(data[(y*tile.width+x)*4+3]>2){left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);}
  bounds=right<left?{x:0,y:0,width:tile.width,height:tile.height}:{x:left,y:top,width:right-left+1,height:bottom-top+1};textureInk.set(tile,bounds);return bounds;
}
export async function prepareFlowerStyles(styles: FlowerStyle[]): Promise<void> {
  const sources = new Set<string>();
  const visit = (value: unknown) => {
    if (!value || typeof value !== 'object') return;
    const object = value as Record<string, unknown>;
    if (object.render_type === 'texture') {
      const source = (object.texture as Paint['texture'])?.source;
      if (!source || !(source.startsWith('data:image/png;base64,') || /^\/api\/v2\/cover-editor\/flowers\/textures\/\d{1,30}\/[a-f0-9]{64}\.png$/.test(source))) throw new Error('纹理图片缺失，请重新导入该款花字。');
      sources.add(source);
    }
    for (const child of Object.values(object)) if (typeof child === 'object') visit(child);
  };
  styles.forEach(s => visit(s.style));
  await Promise.all([...sources].map(source => {
    if (textureImages.has(source)) return;
    if (!textureLoads.has(source)) textureLoads.set(source, loadImage(source).then(img => { textureImages.set(source,img); }).catch(error => { textureLoads.delete(source); throw error; }));
    return textureLoads.get(source);
  }));
}

function layout(ctx: CanvasRenderingContext2D, layer: TextLayer): { glyphs: Glyph[]; bounds: LayerBounds; size: number; ascent: number } {
  const measure = (size: number) => {
    ctx.font = font(size); ctx.textBaseline = 'alphabetic';
    const lines: string[] = [];
    for (const paragraph of layer.text.split('\n')) {
      let current = '';
      for (const char of paragraph) {
        if (current && ctx.measureText(current + char).width > layer.width) { lines.push(current); current = ''; }
        current += char;
      }
      lines.push(current);
    }
    const metrics = lines.filter(Boolean).map(line => ctx.measureText(line));
    if (!metrics.length) metrics.push(ctx.measureText('国Ag'));
    const ascent = Math.max(...metrics.map(m => m.actualBoundingBoxAscent));
    const descent = Math.max(...metrics.map(m => m.actualBoundingBoxDescent));
    return { lines, ascent, contentHeight: (lines.length - 1) * size * 1.24 + ascent + descent,
      widestGlyph: Math.max(0, ...Array.from(layer.text).map(c => ctx.measureText(c).width)) };
  };
  let size = layer.fontSize, measured = measure(size);
  // A smaller box fits the text rather than clipping it; extra space uses vertical alignment.
  if (layer.height !== undefined && (measured.contentHeight > layer.height || measured.widestGlyph > layer.width)) {
    let low = 1, high = size;
    for (let i = 0; i < 12; i++) {
      const mid = (low + high) / 2, trial = measure(mid);
      if (trial.contentHeight <= layer.height && trial.widestGlyph <= layer.width) low = mid; else high = mid;
    }
    size = low; measured = measure(size);
  }
  const { lines, ascent, contentHeight } = measured;
  const height = layer.height ?? Math.max(layer.fontSize * 1.24, contentHeight);
  const free = Math.max(0, height - contentHeight);
  const offsetY = layer.verticalAlign === 'top' ? 0 : layer.verticalAlign === 'bottom' ? free : free / 2;
  const glyphs: Glyph[] = [];
  lines.forEach((line, row) => {
    const total = ctx.measureText(line).width;
    let x = layer.align === 'left' ? 0 : layer.align === 'right' ? layer.width - total : (layer.width - total) / 2;
    for (const char of line) {
      const width = ctx.measureText(char).width;
      glyphs.push({ char, x, y: offsetY + ascent + row * size * 1.24, width }); x += width;
    }
  });
  return { glyphs, bounds: { width: layer.width, height }, size, ascent };
}
export function layerBounds(layer: TextLayer): LayerBounds {
  return layout(makeCanvas(1, 1).getContext('2d')!, layer).bounds;
}

function paint(ctx: CanvasRenderingContext2D, content: Paint, x: number, y: number, w: number, h: number, glyphIndex = 0): string | CanvasGradient | CanvasPattern {
  if (content.render_type === 'solid' && content.solid) return rgba(content.solid.color, content.solid.alpha);
  if (content.render_type === 'texture' && content.texture) {
    const t = content.texture, image = textureImages.get(t.source);
    if (!image) throw new Error('纹理图片尚未加载，请稍候再试。');
    // TextStyle range is a horizontal texture atlas: choose one band per glyph.
    const count=t.range||1,index=glyphIndex%count;
    let tiles=textureTiles.get(content);if(!tiles){tiles=new Map();textureTiles.set(content,tiles);}
    let tile = tiles.get(index);
    if (!tile) {
      tile = makeCanvas(image.naturalWidth/count,image.naturalHeight); const c = tile.getContext('2d')!;
      c.drawImage(image,index*image.naturalWidth/count,0,image.naturalWidth/count,image.naturalHeight,0,0,tile.width,tile.height);
      const pixels = c.getImageData(0,0,tile.width,tile.height), blend = t.blend || 'no';
      let tint: ImageData | null = null;
      if (blend !== 'no') {
        const colors = makeCanvas(tile.width,tile.height), cc = colors.getContext('2d')!;
        cc.fillStyle = paint(cc,{...content,render_type:blend},0,0,tile.width,tile.height);cc.fillRect(0,0,tile.width,tile.height);
        tint = cc.getImageData(0,0,tile.width,tile.height);
      }
      for (let i=0;i<pixels.data.length;i+=4) {
        if (tint) for (let channel=0;channel<3;channel++) pixels.data[i+channel] *= tint.data[i+channel]/255;
        pixels.data[i+3] *= (t.alpha ?? 1) * (tint ? tint.data[i+3]/255 : 1);
      }
      c.putImageData(pixels,0,0); tiles.set(index,tile);
    }
    const pattern = ctx.createPattern(tile,t.wrapMode === 'clamp' ? 'no-repeat' : 'repeat')!;
    let sx=w/tile.width,sy=h/tile.height;
    if (t.stretchMode === 'fit') sx=sy=Math.min(sx,sy);
    const scale=t.scale ?? 1;
    pattern.setTransform(new DOMMatrix().translate(x+w/2,y+h/2).rotate(t.angle || 0)
      .scale(sx*scale*(t.flip?.[0]?-1:1),sy*scale*(t.flip?.[1]?-1:1)).translate(-tile.width/2,-tile.height/2));
    return pattern;
  }
  if (content.render_type !== 'gradient' || !content.gradient) throw new Error('当前花字包含尚未支持的材质，请选择简单花字。');
  const g = content.gradient, angle = g.angle * Math.PI / 180;
  // Jianying's 90 degree gradient runs down the text rectangle.
  const dx = Math.cos(angle), dy = Math.sin(angle), span = Math.abs(dx) * w + Math.abs(dy) * h;
  const result = ctx.createLinearGradient(x + w / 2 - dx * span / 2, y + h / 2 - dy * span / 2, x + w / 2 + dx * span / 2, y + h / 2 + dy * span / 2);
  g.color.forEach((c, i) => result.addColorStop(Math.min(1, Math.max(0, g.percent[i] ?? i / Math.max(1, g.color.length - 1))), rgba(c, g.alpha[i] ?? 1)));
  return result;
}

/** Render actual local TextStyle parameters. No Jianying process or network calls. */
export function renderText(layer: TextLayer, flower: FlowerStyle): { canvas: HTMLCanvasElement; padding: number; bounds: LayerBounds } {
  const scratch = makeCanvas(1, 1).getContext('2d')!, { glyphs, bounds, size, ascent } = layout(scratch, layer), style = flower.style;
  const strokes = style.strokes.filter(s => s.enable && s.width > 0);
  const shadows = style.shadows.filter(s => s.enable);
  const padding = Math.ceil(Math.max(size * .4,
    ...strokes.map(s => s.width * size * 2),
    ...shadows.map(s => s.distance * size / 100 + (s.feather ?? s.diffuse ?? 0) * size * 4 + Math.max(0, ...(s.strokes || []).filter(v => v.enable).map(v => v.width * size)) )) + 12);
  const width = Math.ceil(bounds.width + padding * 2), height = Math.ceil(bounds.height + padding * 2);
  if (width > 8192 || height > 8192 || width * height > 24_000_000) throw new Error('文字区域过大，请缩小字号或减少文字。');
  const result = makeCanvas(width, height), ctx = result.getContext('2d')!;
  const draw = (target: CanvasRenderingContext2D, content: Paint, strokeWidth = 0) => {
    target.font = font(size); target.textBaseline = 'alphabetic'; target.lineJoin = 'round'; target.miterLimit = 2;
    for (const [index,g] of glyphs.entries()) {
      const characterGradient = content.render_type === 'gradient' && content.gradient?.mode === 'character' || content.render_type === 'texture';
      const color = paint(target, content, characterGradient ? g.x + padding : padding, characterGradient ? g.y - ascent + padding : padding,
        characterGradient ? g.width : bounds.width, characterGradient ? size : bounds.height,index);
      // Wide textured strokes in TextStyle carry decorative sprites (paper, flames).
      // Preserve their silhouette behind the glyph instead of repeating or clipping
      // the sprite to a thick glyph outline. Narrow strokes still follow the glyph.
      if(content.render_type==='texture'&&strokeWidth>=size*.3){
        const t=content.texture!,tile=textureTiles.get(content)!.get(index%(t.range||1))!,ink=textureInkBounds(tile);
        const w=(g.width+strokeWidth)*(t.scale??1),h=(size+strokeWidth)*(t.scale??1);
        target.save();target.translate(g.x+padding+g.width/2,g.y-ascent+padding+size/2);target.rotate((t.angle||0)*Math.PI/180);
        target.scale(t.flip?.[0]?-1:1,t.flip?.[1]?-1:1);target.drawImage(tile,ink.x,ink.y,ink.width,ink.height,-w/2,-h/2,w,h);target.restore();continue;
      }
      if (strokeWidth) { target.strokeStyle = color; target.lineWidth = strokeWidth * 2; target.strokeText(g.char, g.x + padding, g.y + padding); }
      else { target.fillStyle = color; target.fillText(g.char, g.x + padding, g.y + padding); }
    }
  };
  // Frontmost effects occur first in TextStyle arrays, so composite back to front.
  for (const shadow of [...shadows].reverse()) {
    const buffer = makeCanvas(width, height), b = buffer.getContext('2d')!;
    for (const stroke of [...(shadow.strokes || [])].reverse()) if (stroke.enable && stroke.width > 0) {
      b.globalAlpha = stroke.alpha ?? 1; draw(b, stroke.content, stroke.width * size);
    }
    b.globalAlpha = 1; draw(b, shadow.content);
    const rad = shadow.angle * Math.PI / 180, distance = shadow.distance * size / 100;
    ctx.save(); ctx.globalAlpha = shadow.alpha;
    ctx.filter = `blur(${Math.max(0, (shadow.feather ?? shadow.diffuse ?? 0) * size / 2)}px)`;
    ctx.drawImage(buffer, Math.cos(rad) * distance, -Math.sin(rad) * distance); ctx.restore();
  }
  for (const stroke of [...strokes].reverse()) {
    ctx.globalAlpha = stroke.alpha; draw(ctx, stroke.content, stroke.width * size);
  }
  ctx.globalAlpha = style.fill.alpha; draw(ctx, style.fill.content); ctx.globalAlpha = 1;
  const mask = makeCanvas(width, height), m = mask.getContext('2d')!;
  draw(m, { render_type: 'solid', solid: { color: [1, 1, 1], alpha: 1 } });
  for (const shadow of [...style.inner_shadows].reverse()) if (shadow.enable) {
    // TextStyle inner_shadows are inset colored glyph layers. Clip the shifted
    // glyph to the original, retaining its colored rim (not a CSS cutout shadow).
    const cutout = makeCanvas(width, height), c = cutout.getContext('2d')!;
    const rad = shadow.angle * Math.PI / 180, distance = shadow.distance * size / 100;
    c.filter = `blur(${Math.max(0, (shadow.feather ?? shadow.diffuse ?? 0) * size / 2)}px)`;
    c.drawImage(mask, Math.cos(rad) * distance, -Math.sin(rad) * distance);
    c.filter = 'none'; c.globalCompositeOperation = 'destination-in'; c.drawImage(mask, 0, 0);
    const colored = makeCanvas(width, height), cc = colored.getContext('2d')!;
    draw(cc, shadow.content); cc.globalCompositeOperation = 'destination-in'; cc.drawImage(cutout, 0, 0);
    ctx.save(); ctx.globalAlpha = shadow.alpha; ctx.drawImage(colored, 0, 0); ctx.restore();
  }
  return { canvas: result, padding, bounds };
}

export function drawLayer(ctx: CanvasRenderingContext2D, layer: TextLayer, flower: FlowerStyle): void {
  const rendered = renderText(layer, flower), { bounds, padding } = rendered;
  ctx.save(); ctx.translate(layer.x + bounds.width / 2, layer.y + bounds.height / 2); ctx.rotate(layer.rotation * Math.PI / 180);
  if (layer.backgroundAlpha > 0) {
    ctx.save(); ctx.globalAlpha = layer.backgroundAlpha; ctx.fillStyle = layer.background;
    ctx.beginPath(); ctx.roundRect(-bounds.width / 2 - 10, -bounds.height / 2 - 5, bounds.width + 20, bounds.height + 10, 12); ctx.fill(); ctx.restore();
  }
  ctx.drawImage(rendered.canvas, -bounds.width / 2 - padding, -bounds.height / 2 - padding); ctx.restore();
}
export function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => reject(new Error('图片无法读取，请重新选择图片。')); img.src = url; });
}
export function renderCover(image: HTMLImageElement | null, layers: TextLayer[], styles: FlowerStyle[], transparent = false): HTMLCanvasElement {
  const w = image?.naturalWidth || 1080, h = image?.naturalHeight || 1440;
  if (w * h > 24_000_000 || w > 8192 || h > 8192) throw new Error('图片过大，请使用不超过 2400 万像素且边长不超过 8192 的封面。');
  const canvas = makeCanvas(w, h), ctx = canvas.getContext('2d')!;
  if (!transparent && image) ctx.drawImage(image, 0, 0);
  for (const layer of layers) {
    const style = styles.find(s => s.id === layer.styleId);
    if (!style) throw new Error('花字样式不存在。');
    drawLayer(ctx, layer, style);
  }
  return canvas;
}
