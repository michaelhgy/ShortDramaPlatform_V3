import { prepareFlowerStyles, type FlowerStyle } from './renderer';

export interface ManagedFlowerStyle extends FlowerStyle { favorite?: boolean; enabled?: boolean; usageCount?: number; lastUsed?: string; builtin?: boolean }
export interface Library { styles: ManagedFlowerStyle[]; custom_directory?: string }
interface Candidate { id: string; name: string; icon: string; status: string; reason: string; imported: boolean; source_folder: string }
type Request = <T>(url: string, body?: unknown) => Promise<T>;
const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const input = (id: string) => $<HTMLInputElement>(id);

export class FlowerLibraryUI {
  styles: ManagedFlowerStyle[];
  private candidates: Candidate[] = [];
  private selected = new Set<string>();
  private page = 0;
  private mode: 'cache' | 'library' = 'cache';
  private busy = false;
  private oldFocus: HTMLElement | null = null;
  private styleRequest = 0;
  private libraryPage = 0;
  private readonly libraryPageSize = 12;
  constructor(styles: ManagedFlowerStyle[], private remote: boolean, private request: Request,
    private apply: (id: string) => void, private notify: (message: string) => void,
    private updated: (styles: ManagedFlowerStyle[]) => void, private current: () => string = () => '', private loading: (value:boolean)=>void = ()=>{}) {
    this.styles = styles;
  }
  async init(initial?: Library) {
    if (this.remote) await this.accept(initial || await this.request<Library>('/api/v2/cover-editor/flowers'));
    else {
      try { const prefs = JSON.parse(localStorage.getItem('cover-flower-preferences') || '{}'); this.styles.forEach(s => Object.assign(s, prefs[s.id] || {})); } catch { /* Existing offline preview has no preferences. */ }
      this.updated(this.styles);
    }
    input('flower-query').oninput = () => { this.libraryPage=0;this.render(); };
    $<HTMLSelectElement>('flower-filter').onchange = () => { this.libraryPage=0;this.render(); };
    $('library-page-prev').onclick=()=>{this.libraryPage=Math.max(0,this.libraryPage-1);this.render();};
    $('library-page-next').onclick=()=>{this.libraryPage++;this.render();};
    $('manage-flowers').onclick = () => void this.open();
    $('close-flowers').onclick = () => this.close();
    $('flower-manager').addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); this.close(); } });
    $('scan-flowers').onclick = () => void this.scan(true);
    $('auto-find-flowers').onclick = () => { input('cache-directory').value = ''; void this.scan(true); };
    $('choose-flower-folder').onclick = async () => {
      if (!this.remote) return this.notify('请在V3正式编辑器中选择剪映缓存目录。');
      try { const result = await this.request<{path: string; cancelled: string}>('/api/v2/select-path', {kind: 'directory', title: '选择剪映用户目录或花字缓存目录'}); if (result.path) { input('cache-directory').value = result.path; await this.scan(true); } }
      catch (error) { this.notify((error as Error).message); }
    };
    input('cache-query').oninput = () => { this.page = 0; this.renderManager(); };
    $<HTMLSelectElement>('cache-filter').onchange = () => { this.page = 0; this.renderManager(); };
    $('flower-cache-tab').onclick = () => { this.mode = 'cache'; this.page = 0; this.renderManager(); };
    $('flower-library-tab').onclick = () => { this.mode = 'library'; this.page = 0; this.renderManager(); };
    $('flower-page-prev').onclick = () => { this.page = Math.max(0, this.page - 1); this.renderManager(); };
    $('flower-page-next').onclick = () => { this.page++; this.renderManager(); };
    $('import-flowers').onclick = () => void this.importSelected();
    $('select-all-flowers').onclick = () => this.selectAvailable(false);
    $('select-page-flowers').onclick = () => this.selectAvailable(true);
    $('clear-flower-selection').onclick = () => { this.selected.clear(); this.renderManager(); };
    this.render();
  }
  private async accept(data: Library) {
    this.styles = data.styles; this.updated(this.styles);
    if (data.custom_directory !== undefined && !input('cache-directory').value) input('cache-directory').value = data.custom_directory;
    this.render();
  }
  async refresh() { if (this.remote) await this.accept(await this.request<Library>('/api/v2/cover-editor/flowers')); }
  cancelPendingStyle(){this.styleRequest++;this.loading(false);}
  private async preference(id: string, update: {favorite?: boolean; enabled?: boolean}) {
    try {
      if (this.remote) await this.accept(await this.request<Library>('/api/v2/cover-editor/flowers/preference', {id, ...update}));
      else {
        Object.assign(this.styles.find(s => s.id === id)!, update);
        localStorage.setItem('cover-flower-preferences', JSON.stringify(Object.fromEntries(this.styles.map(s => [s.id, {favorite: !!s.favorite, enabled: s.enabled !== false, usageCount: s.usageCount || 0, lastUsed: s.lastUsed || ''}]))));
        this.updated(this.styles); this.render();
      }
      if (!$('flower-manager').hidden) this.renderManager();
    } catch (error) { this.notify((error as Error).message); }
  }
  render() {
    const query = input('flower-query').value.trim().toLocaleLowerCase(), filter = $<HTMLSelectElement>('flower-filter').value;
    let rows = this.styles.filter(s => s.enabled !== false && (!query || `${s.name} ${s.id}`.toLocaleLowerCase().includes(query)));
    if (filter === 'favorite') rows = rows.filter(s => s.favorite);
    if (filter === 'recent') rows = rows.filter(s => s.lastUsed).sort((a,b) => (b.lastUsed || '').localeCompare(a.lastUsed || ''));
    else rows.sort((a,b) => (filter === 'all' ? Number(!!b.favorite) - Number(!!a.favorite) : 0) || (b.usageCount || 0) - (a.usageCount || 0));
    $('style-count').textContent = `${this.styles.filter(s => s.enabled !== false).length} 款`;
    const pages=Math.max(1,Math.ceil(rows.length/this.libraryPageSize));this.libraryPage=Math.min(this.libraryPage,pages-1);
    $('library-page-label').textContent=`${this.libraryPage+1} / ${pages} · ${rows.length} 款`;
    $<HTMLButtonElement>('library-page-prev').disabled=this.libraryPage===0;
    $<HTMLButtonElement>('library-page-next').disabled=this.libraryPage>=pages-1;
    const list = $('styles'); list.replaceChildren();
    for (const style of rows.slice(this.libraryPage*this.libraryPageSize,(this.libraryPage+1)*this.libraryPageSize)) {
      const tile = document.createElement('div'); tile.className = 'style-tile';
      const b = document.createElement('button'); b.className = `style-card${this.current() === style.id ? ' selected' : ''}`; b.dataset.id = style.id; b.title = style.name;
      if (style.icon) { const img = new Image(); img.loading = 'lazy'; img.decoding = 'async'; img.src = style.icon; img.alt = style.name; b.append(img); }
      const title = document.createElement('span'); title.textContent = style.name;
      const uses = document.createElement('small'); uses.textContent = `使用 ${style.usageCount || 0} 次`; b.append(title, uses);
      b.onclick = async () => {
        const token=++this.styleRequest;b.disabled=true;this.loading(true);
        try { await prepareFlowerStyles([style]);if(token===this.styleRequest)this.apply(style.id); }
        catch(error){this.notify((error as Error).message);}
        finally{b.disabled=false;if(token===this.styleRequest)this.loading(false);}
      };
      const star = document.createElement('button'); star.className = `flower-star${style.favorite ? ' starred' : ''}`; star.textContent = style.favorite ? '★' : '☆'; star.title = style.favorite ? '取消收藏' : '收藏'; star.setAttribute('aria-label', `${style.favorite ? '取消收藏' : '收藏'}${style.name}`);
      star.onclick = () => { star.disabled = true; void this.preference(style.id, {favorite: !style.favorite}).finally(() => { star.disabled = false; }); }; tile.append(b,star); list.append(tile);
    }
    if (!rows.length) { const empty = document.createElement('p'); empty.className = 'flower-empty'; empty.textContent = filter === 'favorite' ? '还没有收藏，点击花字右上角的☆收藏。' : '没有符合条件的花字'; list.append(empty); }
  }
  async recordExport(ids: string[]) {
    if (this.remote) {
      try { await this.accept(await this.request<Library>('/api/v2/cover-editor/flowers/usage', {ids: [...new Set(ids)], eventId: crypto.randomUUID()})); }
      catch { this.notify('图片已生成，花字使用次数暂未更新。'); }
    }
  }
  private async open() {
    this.oldFocus = document.activeElement as HTMLElement; $('flower-manager').hidden = false; $('close-flowers').focus();
    await this.scan(false);
  }
  private close() {
    $('flower-manager').hidden = true; this.oldFocus?.focus();
  }
  private async scan(remember: boolean) {
    if (this.busy) return;
    if (!this.remote) { $('cache-summary').textContent = '离线预览无法扫描电脑文件。请在V3正式编辑器中打开“管理花字”。'; this.renderManager(); return; }
    this.busy = true; this.renderManager(); $('cache-summary').textContent = '正在读取本机剪映缓存，请稍候…';
    try {
      const result = await this.request<{items: Candidate[]; roots: string[]; ready_count: number; message: string}>('/api/v2/cover-editor/flowers/scan', {directory: input('cache-directory').value.trim(), remember});
      this.candidates = result.items; this.selected.clear(); this.page = 0;
      $('cache-summary').textContent = result.message || `找到 ${result.items.length} 款已缓存花字，其中 ${result.ready_count} 款当前可加入。`;
      $('cache-roots').textContent = result.roots.join('；');
    } catch (error) { $('cache-summary').textContent = (error as Error).message; }
    finally { this.busy = false; this.renderManager(); }
  }
  private renderManager() {
    $('flower-cache-tab').classList.toggle('active', this.mode === 'cache'); $('flower-library-tab').classList.toggle('active', this.mode === 'library');
    const query = input('cache-query').value.trim().toLocaleLowerCase(), filter = $<HTMLSelectElement>('cache-filter').value;
    const known = new Map(this.styles.map(s => [s.id,s]));
    const rows: Candidate[] = this.mode === 'cache' ? this.candidates.map(c => ({...c, imported: known.get(c.id)?.enabled !== false && known.has(c.id)})) : this.styles.map(s => ({id:s.id,name:s.name,icon:s.icon,status:'ready',reason:'',imported:s.enabled !== false,source_folder:''}));
    const filtered = rows.filter(c => (!query || `${c.name} ${c.id}`.toLocaleLowerCase().includes(query)) && (filter === 'all' || filter === 'ready' && c.status === 'ready' && !c.imported || filter === 'unsupported' && c.status !== 'ready' || filter === 'imported' && c.imported));
    const pages = Math.max(1,Math.ceil(filtered.length/48)); this.page = Math.min(this.page,pages-1);
    const list = $('cache-results'); list.replaceChildren();
    for (const item of filtered.slice(this.page*48,this.page*48+48)) {
      const card = document.createElement('div'); card.className = `cache-card${item.status !== 'ready' ? ' unsupported' : ''}`; card.dataset.id = item.id; card.title = `${item.name}\n${item.id}\n${item.reason || item.source_folder}`;
      if (item.icon) { const img = new Image(); img.src = item.icon; img.alt = item.name; img.loading = 'lazy'; card.append(img); } else { const icon = document.createElement('div'); icon.className = 'cache-no-icon'; icon.textContent = 'Aa'; card.append(icon); }
      const name = document.createElement('strong'); name.textContent = item.name; card.append(name);
      const note = document.createElement('small'); note.textContent = item.imported ? '已加入' : item.status === 'ready' ? '可加入' : item.reason; card.append(note);
      if (this.mode === 'cache') {
        const check = document.createElement('input'); check.type = 'checkbox'; check.checked = this.selected.has(item.id); check.disabled = this.busy || item.imported || item.status !== 'ready'; check.setAttribute('aria-label', `选择${item.name}`);
        check.onchange = () => { check.checked ? this.selected.add(item.id) : this.selected.delete(item.id); this.updateCount(); }; card.prepend(check);
      } else {
        const remove = document.createElement('button'); remove.textContent = item.imported ? '移出列表' : '重新加入'; remove.onclick = () => void this.preference(item.id,{enabled:!item.imported}); card.append(remove);
      }
      list.append(card);
    }
    if (!filtered.length) { const empty = document.createElement('p'); empty.className = 'flower-empty'; empty.textContent = this.busy ? '正在扫描…' : '没有符合条件的花字'; list.append(empty); }
    $('flower-page-label').textContent = `${this.page+1} / ${pages} · ${filtered.length} 款`;
    $<HTMLButtonElement>('flower-page-prev').disabled = this.page===0 || this.busy;
    $<HTMLButtonElement>('flower-page-next').disabled = this.page>=pages-1 || this.busy;
    for (const id of ['scan-flowers','auto-find-flowers','choose-flower-folder']) $<HTMLButtonElement>(id).disabled = this.busy;
    this.updateCount();
  }
  private selectAvailable(pageOnly: boolean) {
    if (this.busy || this.mode !== 'cache') return;
    const known=new Set(this.styles.filter(s=>s.enabled!==false).map(s=>s.id));
    const query=input('cache-query').value.trim().toLocaleLowerCase(),filter=$<HTMLSelectElement>('cache-filter').value;
    const filtered=this.candidates.filter(c=>(!query||`${c.name} ${c.id}`.toLocaleLowerCase().includes(query)) && (filter==='all'||filter==='ready'&&c.status==='ready'&&!known.has(c.id)||filter==='imported'&&known.has(c.id)||filter==='unsupported'&&c.status!=='ready'));
    const rows=pageOnly?filtered.slice(this.page*48,this.page*48+48):filtered;
    for(const c of rows)if(c.status==='ready'&&!known.has(c.id))this.selected.add(c.id);
    this.renderManager();
  }
  private updateCount() {
    $('import-flowers').textContent = this.busy ? '请稍候…' : `添加选中（${this.selected.size}）`;
    $<HTMLButtonElement>('import-flowers').disabled = this.busy || !this.selected.size || this.mode !== 'cache';
    for(const id of ['select-all-flowers','select-page-flowers','clear-flower-selection'])$<HTMLButtonElement>(id).disabled=this.busy||this.mode!=='cache';
  }
  private async importSelected() {
    if (this.busy || !this.selected.size) return;
    this.busy = true; this.renderManager();
    try {
      const identifiers=[...this.selected],count=identifiers.length;
      for(let i=0;i<identifiers.length;i+=100){
        const batch=identifiers.slice(i,i+100);
        await this.accept(await this.request<Library>('/api/v2/cover-editor/flowers/import', {ids:batch, directory:input('cache-directory').value.trim()}));
        batch.forEach(id=>this.selected.delete(id));
        $('import-flowers').textContent=`已添加 ${Math.min(i+100,count)} / ${count}`;
      }
      this.notify(`已添加 ${count} 款花字到V3，剪映清理缓存后仍可使用。`);
    } catch (error) { this.notify((error as Error).message); }
    finally { this.busy = false; this.renderManager(); }
  }
}
