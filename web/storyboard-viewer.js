import { buildStoryboardModel, viewerTransform, zoomAt } from "./storyboard-model.js";

const STYLE_ID = "soda-storyboard-viewer-style";
const SVG_NS = "http://www.w3.org/2000/svg";
let activeViewer;
let nextViewerId = 0;

// Kept separate from the node widget: a viewer must never inherit the graph's
// CSS transform, clipping, or wheel handlers.
export const viewerCSS = `
.soda-sv-overlay { position:fixed; inset:0; z-index:2147483647; display:grid; place-items:center; background:rgba(0,0,0,.68); color:var(--input-text, #dedee3); font:14px/1.5 var(--comfy-font-family, system-ui, sans-serif); overscroll-behavior:contain; }
.soda-sv-overlay *, .soda-sv-overlay *::before, .soda-sv-overlay *::after { box-sizing:border-box; }
.soda-sv-dialog { width:90vw; height:90vh; height:90dvh; display:flex; flex-direction:column; min-width:0; min-height:0; overflow:hidden; border:1px solid var(--border-color, #62626b); border-radius:12px; background:var(--comfy-menu-bg, #29292e); box-shadow:0 24px 90px rgba(0,0,0,.4); }
.soda-sv-head { flex:none; max-height:30%; overflow:auto; padding:14px 18px 12px; border-bottom:1px solid var(--border-color, #62626b); }
.soda-sv-heading { display:flex; align-items:flex-start; gap:12px; }
.soda-sv-title { flex:1; min-width:0; margin:0; font-size:18px; font-weight:650; line-height:1.45; overflow-wrap:anywhere; }
.soda-sv-actions, .soda-sv-toolbar, .soda-sv-tags { display:flex; align-items:center; flex-wrap:wrap; gap:7px; }
.soda-sv-actions { flex:none; }
.soda-sv-overlay button { min-height:32px; padding:5px 11px; border:1px solid var(--border-color, #62626b); border-radius:6px; color:var(--input-text, #dedee3); background:var(--comfy-input-bg, var(--comfy-menu-secondary-bg, #3a3a42)); font:inherit; line-height:1.4; cursor:pointer; }
.soda-sv-overlay button:hover { filter:brightness(1.13); }
.soda-sv-overlay button:disabled { opacity:.6; cursor:wait; }
.soda-sv-overlay :focus-visible { outline:3px solid var(--p-primary-color, #5b9df7); outline-offset:2px; }
.soda-sv-overlay button[aria-pressed=true] { border-color:var(--p-primary-color, #5b9df7); box-shadow:inset 0 0 0 1px var(--p-primary-color, #5b9df7); }
.soda-sv-close { min-width:34px; font-size:20px !important; line-height:1 !important; }
.soda-sv-tags { margin-top:9px; }
.soda-sv-tag { display:inline-block; padding:2px 8px; font-size:12px; border-radius:5px; border:1px solid var(--border-color, #62626b); background:var(--comfy-input-bg, var(--comfy-menu-secondary-bg, #3a3a42)); }
.soda-sv-warnings { display:grid; gap:5px; margin-top:9px; }
.soda-sv-warning { display:flex; align-items:flex-start; gap:10px; padding:5px 9px; border-left:3px solid #bf8b16; color:var(--input-text, #dedee3); background:rgba(218,164,38,.14); font-size:13px; overflow-wrap:anywhere; }
.soda-sv-warning span { flex:1; min-width:0; }
.soda-sv-warning button { min-height:22px; padding:0 5px; border:0; background:transparent; }
.soda-sv-body { flex:1; display:grid; grid-template-columns:minmax(0, 3fr) minmax(0, 2fr); min-height:0; min-width:0; }
.soda-sv-image-pane { display:flex; flex-direction:column; min-height:0; min-width:0; border-right:1px solid var(--border-color, #62626b); }
.soda-sv-toolbar { flex:none; padding:9px 12px; border-bottom:1px solid var(--border-color, #62626b); }
.soda-sv-zoom { min-width:46px; font-size:12px; font-variant-numeric:tabular-nums; }
.soda-sv-hint { margin-left:auto; color:var(--descrip-text, var(--input-text, #bdbdc7)); font-size:12px; }
.soda-sv-viewport { flex:1; position:relative; min-height:0; min-width:0; overflow:hidden; background:#000; touch-action:none; cursor:grab; user-select:none; isolation:isolate; }
.soda-sv-viewport.soda-sv-dragging { cursor:grabbing; }
.soda-sv-stage { position:absolute; left:0; top:0; transform-origin:0 0; background:white; will-change:transform; }
.soda-sv-stage img { display:block; width:100%; height:100%; pointer-events:none; }
.soda-sv-stage svg { position:absolute; inset:0; width:100%; height:100%; overflow:visible; }
.soda-sv-polygon { fill:transparent; stroke:transparent; stroke-width:3; vector-effect:non-scaling-stroke; cursor:pointer; }
.soda-sv-polygon.soda-sv-active { fill:rgba(36,111,221,.11); stroke:#246fdd; }
.soda-sv-number-bg { fill:#fff; stroke:#246fdd; vector-effect:non-scaling-stroke; }
.soda-sv-number { fill:#164d9d; text-anchor:middle; dominant-baseline:central; font-family:system-ui,sans-serif; font-weight:700; }
.soda-sv-empty-image { position:absolute; inset:0; display:grid; place-items:center; margin:0; padding:20px; color:#ccc; font-size:14px; text-align:center; pointer-events:none; }
.soda-sv-details { display:flex; flex-direction:column; min-height:0; min-width:0; background:var(--comfy-menu-bg, #29292e); }
.soda-sv-tabs { display:flex; gap:3px; flex:none; padding:9px 12px 0; border-bottom:1px solid var(--border-color, #62626b); }
.soda-sv-overlay .soda-sv-tab { border:0; border-bottom:3px solid transparent; border-radius:3px 3px 0 0; padding:7px 14px 9px; background:transparent; }
.soda-sv-overlay .soda-sv-tab[aria-selected=true] { border-bottom-color:var(--p-primary-color, #5b9df7); font-weight:650; }
.soda-sv-panel { flex:1; min-height:0; min-width:0; overflow:auto; overscroll-behavior:contain; }
.soda-sv-panel[hidden], .soda-sv-overlay [hidden] { display:none !important; }
.soda-sv-list { padding:12px; }
.soda-sv-entry { display:block; width:100%; margin:0 0 9px; padding:12px; border:1px solid var(--border-color, #62626b); border-radius:7px; cursor:pointer; overflow-wrap:anywhere; }
.soda-sv-entry:last-child { margin-bottom:0; }
.soda-sv-entry.soda-sv-active { border-color:var(--p-primary-color, #5b9df7); box-shadow:inset 3px 0 0 var(--p-primary-color, #5b9df7); background:var(--comfy-menu-secondary-bg, var(--comfy-input-bg, #34343b)); }
.soda-sv-entry h3 { margin:0 0 5px; font-size:14px; font-weight:650; }
.soda-sv-entry p { margin:4px 0 0; white-space:pre-wrap; }
.soda-sv-entry-characters { font-size:13px; color:var(--descrip-text, var(--input-text, #bdbdc7)); }
.soda-sv-entry-dialogue { padding-top:7px; }
.soda-sv-entry-dialogue p { border-left:2px solid var(--border-color, #62626b); padding-left:9px; }
.soda-sv-list-empty { padding:10px; color:var(--descrip-text, var(--input-text, #bdbdc7)); }
.soda-sv-prompt-pane { display:flex; flex-direction:column; overflow:hidden; }
.soda-sv-prompt-tools { flex:none; display:flex; flex-wrap:wrap; align-items:center; gap:7px; padding:10px 12px; }
.soda-sv-copy-status { font-size:12px; overflow-wrap:anywhere; }
.soda-sv-prompt { display:block; flex:1; width:100%; min-height:0; min-width:0; margin:0; padding:12px 14px; resize:none; border:0; border-top:1px solid var(--border-color, #62626b); border-radius:0; color:var(--input-text, #dedee3); background:var(--comfy-input-bg, #202024); font:13px/1.65 ui-monospace, SFMono-Regular, Consolas, monospace; tab-size:2; white-space:pre; overflow:auto; }
@media (max-width:700px) {
  .soda-sv-dialog { width:96vw; height:94vh; height:94dvh; border-radius:8px; }
  .soda-sv-head { padding:10px 12px; max-height:27%; }
  .soda-sv-heading { flex-wrap:wrap; gap:7px; }
  .soda-sv-title { font-size:16px; }
  .soda-sv-actions { margin-left:auto; }
  .soda-sv-body { grid-template-columns:minmax(0, 3fr) minmax(0, 2fr); }
  .soda-sv-toolbar { padding:7px; gap:5px; }
  .soda-sv-hint { display:none; }
  .soda-sv-list { padding:8px; }
  .soda-sv-entry { padding:9px; }
  .soda-sv-tabs { padding-left:6px; padding-right:6px; }
  .soda-sv-overlay .soda-sv-tab { padding-left:8px; padding-right:8px; }
}
`;

function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
}

function svgElement(tag, attributes = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    return node;
}

function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = element("style");
    style.id = STYLE_ID;
    style.textContent = viewerCSS;
    document.head.append(style);
}

/** Open a read-only viewer using the same normalized metadata as the node. */
export function openStoryboardViewer(options = {}) {
    activeViewer?.close(false);
    ensureStyle();
    let settings = { ...options };
    let model;
    let disposed = false;
    let frame = 0;
    let drag;
    let selected = null;
    let hovered = null;
    let formatted = true;
    let currentTab = "panels";
    let backgroundPointer = false;
    let view = { mode: "fit", zoom: 1, panX: 0, panY: 0 };
    const previousFocus = options.triggerElement || document.activeElement;
    const controller = new AbortController();
    let contentController = new AbortController();
    const entries = new Map();
    const shapes = new Map();
    const labels = new Map();
    const id = `soda-storyboard-viewer-${++nextViewerId}`;
    const overlay = element("div", "soda-sv-overlay");
    const dialog = element("section", "soda-sv-dialog");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", `${id}-title`);
    dialog.tabIndex = -1;
    const head = element("header", "soda-sv-head");
    const heading = element("div", "soda-sv-heading");
    const title = element("h2", "soda-sv-title");
    title.id = `${id}-title`;
    const actions = element("div", "soda-sv-actions");
    const edit = element("button", "", "在编辑器中打开");
    const closeButton = element("button", "soda-sv-close", "×");
    closeButton.setAttribute("aria-label", "关闭分镜查看器");
    closeButton.title = "关闭（Esc）";
    actions.append(edit, closeButton);
    heading.append(title, actions);
    const tags = element("div", "soda-sv-tags");
    tags.setAttribute("aria-label", "分镜信息");
    const warnings = element("div", "soda-sv-warnings");
    head.append(heading, tags, warnings);
    const body = element("div", "soda-sv-body");
    const imagePane = element("section", "soda-sv-image-pane");
    imagePane.setAttribute("aria-label", "分镜图");
    const toolbar = element("div", "soda-sv-toolbar");
    const fit = element("button", "", "适应");
    fit.title = "适应窗口（0）";
    const actual = element("button", "", "100%");
    actual.title = "原始尺寸（1）";
    const zoomLabel = element("span", "soda-sv-zoom", "100%");
    zoomLabel.setAttribute("aria-label", "当前缩放比例");
    const hint = element("span", "soda-sv-hint", "滚轮缩放 · 拖动平移");
    toolbar.append(fit, actual, zoomLabel, hint);
    const viewport = element("div", "soda-sv-viewport");
    viewport.tabIndex = 0;
    viewport.setAttribute("role", "region");
    viewport.setAttribute("aria-label", "分镜图。滚轮或加减键缩放，方向键平移，0 适应，1 原始尺寸。");
    const stage = element("div", "soda-sv-stage");
    const image = element("img");
    image.draggable = false;
    const svg = svgElement("svg", { "aria-label": "分格及阅读顺序" });
    const emptyImage = element("p", "soda-sv-empty-image", "暂无分镜图");
    emptyImage.setAttribute("role", "status");
    stage.append(image, svg);
    viewport.append(stage, emptyImage);
    imagePane.append(toolbar, viewport);
    const details = element("section", "soda-sv-details");
    details.setAttribute("aria-label", "分镜内容");
    const tabs = element("div", "soda-sv-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "查看内容");
    const panelsTab = element("button", "soda-sv-tab", "逐格");
    const promptTab = element("button", "soda-sv-tab", "提示词");
    const list = element("div", "soda-sv-panel soda-sv-list");
    const promptPane = element("div", "soda-sv-panel soda-sv-prompt-pane");
    for (const [tab, panel, name] of [[panelsTab, list, "panels"], [promptTab, promptPane, "prompt"]]) {
        tab.type = "button";
        tab.id = `${id}-${name}-tab`;
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-controls", `${id}-${name}`);
        panel.id = `${id}-${name}`;
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", tab.id);
        panel.tabIndex = 0;
    }
    const promptTools = element("div", "soda-sv-prompt-tools");
    const copy = element("button", "", "复制");
    const format = element("button", "", "压缩");
    const copyStatus = element("span", "soda-sv-copy-status");
    copyStatus.setAttribute("role", "status");
    copyStatus.setAttribute("aria-live", "polite");
    const prompt = element("textarea", "soda-sv-prompt");
    prompt.readOnly = true;
    prompt.spellcheck = false;
    prompt.wrap = "off";
    prompt.setAttribute("aria-label", "完整 MOSS JSON 提示词（只读）");
    prompt.placeholder = "暂无提示词";
    promptTools.append(copy, format, copyStatus);
    promptPane.append(promptTools, prompt);
    tabs.append(panelsTab, promptTab);
    details.append(tabs, list, promptPane);
    body.append(imagePane, details);
    dialog.append(head, body);
    overlay.append(dialog);

    const listen = (target, type, action, extra = {}) => target.addEventListener(type, action, { ...extra, signal: controller.signal });
    const listenContent = (target, type, action) => target.addEventListener(type, action, { signal: contentController.signal });
    const report = error => {
        copyStatus.textContent = String(error?.message || error);
        settings.onError?.(error);
    };
    const dimensions = () => ({
        width: Math.max(1, Number(model?.width) || image.naturalWidth || 1),
        height: Math.max(1, Number(model?.height) || image.naturalHeight || 1),
        viewportWidth: Math.max(1, viewport.clientWidth),
        viewportHeight: Math.max(1, viewport.clientHeight),
        ...view,
    });
    const transform = () => {
        if (disposed) return;
        const source = dimensions();
        const t = viewerTransform(source);
        stage.style.width = `${source.width}px`;
        stage.style.height = `${source.height}px`;
        stage.style.transform = `translate(${t.x}px, ${t.y}px) scale(${t.scale})`;
        zoomLabel.textContent = `${Math.round(t.scale * 100)}%`;
        fit.setAttribute("aria-pressed", String(view.mode === "fit" && view.zoom === 1 && !view.panX && !view.panY));
        actual.setAttribute("aria-pressed", String(view.mode === "actual" && view.zoom === 1));
        // Counter-scale labels so small panels remain readable at any zoom.
        const labelScale = 1 / Math.max(.001, t.scale);
        for (const { group, x, y } of labels.values()) {
            group.setAttribute("transform", `translate(${x} ${y}) scale(${labelScale})`);
        }
    };
    const scheduleTransform = () => {
        if (frame || disposed) return;
        frame = requestAnimationFrame(() => { frame = 0; transform(); });
    };
    const highlight = () => {
        const active = hovered ?? selected;
        for (const [key, card] of entries) {
            card.classList.toggle("soda-sv-active", key === active);
            card.setAttribute("aria-pressed", String(key === selected));
        }
        for (const [key, polygon] of shapes) polygon.classList.toggle("soda-sv-active", key === active);
    };
    const select = (key, reveal = false) => {
        selected = key;
        highlight();
        if (reveal) {
            setTab("panels");
            const card = entries.get(key);
            card?.scrollIntoView?.({ block: "nearest" });
            card?.focus({ preventScroll: true });
        }
    };
    function setTab(name, focus = false) {
        currentTab = name;
        for (const [tab, panel, key] of [[panelsTab, list, "panels"], [promptTab, promptPane, "prompt"]]) {
            const active = key === name;
            tab.setAttribute("aria-selected", String(active));
            tab.tabIndex = active ? 0 : -1;
            panel.hidden = !active;
            if (active && focus) tab.focus();
        }
    }
    const changeZoom = (nextZoom, point) => {
        const next = zoomAt(dimensions(), nextZoom, point || [viewport.clientWidth / 2, viewport.clientHeight / 2]);
        view = { mode: next.mode, zoom: next.zoom, panX: next.panX, panY: next.panY };
        transform();
    };
    const renderPrompt = () => {
        const raw = String(model?.prompt || "");
        try { prompt.value = raw ? JSON.stringify(JSON.parse(raw), null, formatted ? 2 : 0) : ""; }
        catch { prompt.value = raw; }
        format.textContent = formatted ? "压缩" : "格式化";
        copy.disabled = !raw;
        format.disabled = !raw;
    };
    const renderEntries = () => {
        entries.clear(); shapes.clear(); labels.clear();
        list.replaceChildren(); svg.replaceChildren();
        svg.setAttribute("viewBox", `0 0 ${Math.max(1, model.width || 1)} ${Math.max(1, model.height || 1)}`);
        const rows = model.entries || [];
        if (!rows.length) list.append(element("p", "soda-sv-list-empty", "暂无逐格内容。"));
        for (const [index, entry] of rows.entries()) {
            const key = `${index}:${entry.id || index}`;
            const card = element("article", "soda-sv-entry");
            card.tabIndex = 0;
            card.setAttribute("role", "button");
            card.setAttribute("aria-pressed", "false");
            const number = entry.number || index + 1;
            const label = entry.kind === "panel" ? `第 ${number} 格` : entry.kind === "text" ? "页上文字" : `第 ${number} 条`;
            card.append(element("h3", "", [label, entry.shot].filter(Boolean).join(" · ")));
            const characters = (entry.characters || []).map(character => character.name || character.id).filter(Boolean);
            if (characters.length) card.append(element("p", "soda-sv-entry-characters", `出场角色：${characters.join("、")}`));
            if (entry.description) card.append(element("p", "", entry.description));
            const dialogue = element("div", "soda-sv-entry-dialogue");
            for (const text of entry.texts || []) {
                if (!text.text) continue;
                const speaker = text.speaker || text.speakerId;
                const prefix = speaker || ({ narration: "旁白", dialogue: "台词", thought: "心声", sfx: "音效" }[text.kind] || text.kind || "文字");
                dialogue.append(element("p", "", `${prefix}：${text.text}`));
            }
            if (dialogue.childElementCount) card.append(dialogue);
            const onEnter = () => { if (!drag?.moved) { hovered = key; highlight(); } };
            const onLeave = () => { if (hovered === key) { hovered = null; highlight(); } };
            listenContent(card, "pointerenter", onEnter);
            listenContent(card, "pointerleave", onLeave);
            listenContent(card, "focus", onEnter);
            listenContent(card, "blur", onLeave);
            listenContent(card, "click", () => select(key));
            listenContent(card, "keydown", event => {
                if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(key); }
                const offset = { ArrowDown: 1, ArrowUp: -1, Home: -index, End: rows.length - index - 1 }[event.key];
                if (offset !== undefined) {
                    event.preventDefault();
                    [...entries.values()][Math.max(0, Math.min(rows.length - 1, index + offset))]?.focus();
                }
            });
            entries.set(key, card);
            list.append(card);
            const points = entry.polygon;
            if (!Array.isArray(points) || points.length < 3) continue;
            const polygon = svgElement("polygon", { points: points.map(point => point.join(",")).join(" "), "data-soda-panel": key, "aria-label": label });
            polygon.classList.add("soda-sv-polygon");
            listenContent(polygon, "pointerenter", onEnter);
            listenContent(polygon, "pointerleave", onLeave);
            svg.append(polygon);
            shapes.set(key, polygon);
            // Place each marker inside the upper right corner, matching manga
            // reading direction without changing the authored reading order.
            const top = Math.min(...points.map(point => point[1]));
            const right = Math.max(...points.filter(point => point[1] <= top + 1).map(point => point[0]));
            const group = svgElement("g", { "pointer-events": "none", "aria-hidden": "true" });
            group.append(svgElement("rect", { x: -29, y: 5, width: 25, height: 24, rx: 4, class: "soda-sv-number-bg" }));
            const labelText = svgElement("text", { x: -16.5, y: 17, "font-size": 13, class: "soda-sv-number" });
            labelText.textContent = String(number);
            group.append(labelText); svg.append(group);
            labels.set(key, { group, x: Number.isFinite(right) ? right : points[0][0], y: top });
        }
    };
    function update(patch = {}) {
        if (disposed) return;
        settings = { ...settings, ...patch };
        if (Object.hasOwn(patch, "metadata") && !Object.hasOwn(patch, "model")) settings.model = undefined;
        contentController.abort();
        contentController = new AbortController();
        model = settings.model || buildStoryboardModel(settings.metadata || {}, settings.filename || "");
        title.textContent = settings.title || model.title || "分镜查看器";
        image.alt = `${title.textContent} · 分镜图`;
        tags.replaceChildren(...(model.tags || []).map(tag => element("span", "soda-sv-tag", typeof tag === "string" ? tag : tag.label)));
        warnings.replaceChildren();
        for (const warning of settings.warnings || model.warnings || []) {
            const line = element("div", "soda-sv-warning");
            const dismiss = element("button", "", "×");
            dismiss.setAttribute("aria-label", "关闭此提示");
            listenContent(dismiss, "click", () => line.remove());
            line.append(element("span", "", warning), dismiss);
            warnings.append(line);
        }
        warnings.hidden = !warnings.childElementCount;
        edit.hidden = typeof settings.onEdit !== "function";
        copyStatus.textContent = "";
        formatted = true;
        selected = null; hovered = null; drag = undefined;
        view = { mode: "fit", zoom: 1, panX: 0, panY: 0 };
        const source = String(model.image || "");
        image.hidden = !source;
        stage.hidden = !source;
        emptyImage.hidden = Boolean(source);
        emptyImage.textContent = "暂无分镜图";
        if (source) image.src = source; else image.removeAttribute("src");
        renderPrompt(); renderEntries(); setTab(currentTab); scheduleTransform();
    }
    function close(restoreFocus = true) {
        if (disposed) return;
        disposed = true;
        controller.abort();
        contentController.abort();
        observer?.disconnect();
        if (frame) cancelAnimationFrame(frame);
        overlay.remove();
        if (activeViewer === handle) activeViewer = undefined;
        if (restoreFocus && previousFocus?.isConnected) previousFocus.focus?.({ preventScroll: true });
        settings.onClose?.();
    }

    for (const item of [edit, closeButton, fit, actual, copy, format]) item.type = "button";
    listen(closeButton, "click", () => close());
    listen(overlay, "pointerdown", event => { backgroundPointer = event.target === overlay; });
    listen(overlay, "click", event => { if (event.target === overlay && backgroundPointer) close(); });
    for (const type of ["pointerdown", "pointerup", "click", "dblclick", "keydown", "wheel", "contextmenu"]) listen(overlay, type, event => event.stopPropagation());
    listen(edit, "click", async () => {
        edit.disabled = true;
        try { await settings.onEdit?.(); if (!disposed) close(); }
        catch (error) { if (!disposed) report(error); }
        finally { edit.disabled = false; }
    });
    listen(fit, "click", () => { view = { mode: "fit", zoom: 1, panX: 0, panY: 0 }; transform(); });
    listen(actual, "click", () => { view = { mode: "actual", zoom: 1, panX: 0, panY: 0 }; transform(); });
    listen(viewport, "wheel", event => {
        event.preventDefault();
        const rect = viewport.getBoundingClientRect();
        const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1);
        changeZoom(view.zoom * Math.exp(-delta * .0015), [event.clientX - rect.left, event.clientY - rect.top]);
    }, { passive: false });
    listen(viewport, "pointerdown", event => {
        if (event.button !== 0 || !model.image) return;
        event.preventDefault();
        viewport.focus({ preventScroll: true });
        drag = { id: event.pointerId, x: event.clientX, y: event.clientY, panX: view.panX, panY: view.panY, moved: false,
            key: event.target.closest?.("[data-soda-panel]")?.getAttribute("data-soda-panel") };
    });
    listen(window, "pointermove", event => {
        if (!drag || drag.id !== event.pointerId) return;
        const dx = event.clientX - drag.x;
        const dy = event.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) < 3) return;
        drag.moved = true;
        hovered = null; highlight();
        viewport.classList.add("soda-sv-dragging");
        view.panX = drag.panX + dx; view.panY = drag.panY + dy;
        scheduleTransform();
    });
    const endDrag = event => {
        if (!drag || drag.id !== event.pointerId) return;
        if (!drag.moved && drag.key && event.type !== "pointercancel") select(drag.key, true);
        drag = undefined;
        viewport.classList.remove("soda-sv-dragging");
    };
    listen(window, "pointerup", endDrag, { capture: true });
    listen(window, "pointercancel", endDrag, { capture: true });
    listen(window, "blur", () => { drag = undefined; viewport.classList.remove("soda-sv-dragging"); });
    listen(viewport, "keydown", event => {
        if (event.target !== viewport) return;
        const pan = { ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] }[event.key];
        if (pan) { event.preventDefault(); view.panX += pan[0]; view.panY += pan[1]; transform(); }
        if (["+", "=", "-", "_"].includes(event.key)) { event.preventDefault(); changeZoom(view.zoom * (["-", "_"].includes(event.key) ? .8 : 1.25)); }
        if (event.key === "0") { event.preventDefault(); fit.click(); }
        if (event.key === "1") { event.preventDefault(); actual.click(); }
    });
    listen(image, "load", scheduleTransform);
    listen(image, "error", () => {
        if (disposed) return;
        stage.hidden = true; emptyImage.hidden = false;
        emptyImage.textContent = "分镜图无法加载，请重新载入文件。";
    });
    listen(panelsTab, "click", () => setTab("panels"));
    listen(promptTab, "click", () => setTab("prompt"));
    listen(tabs, "keydown", event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        setTab(event.key === "Home" ? "panels" : event.key === "End" ? "prompt" : currentTab === "panels" ? "prompt" : "panels", true);
    });
    listen(format, "click", () => {
        try { JSON.parse(String(model.prompt || "")); }
        catch { report(new Error("提示词不是有效 JSON，无法格式化。")); return; }
        formatted = !formatted; renderPrompt(); copyStatus.textContent = "";
    });
    listen(copy, "click", async () => {
        copy.disabled = true;
        try {
            if (globalThis.navigator?.clipboard?.writeText) await navigator.clipboard.writeText(prompt.value);
            else {
                const focus = document.activeElement;
                prompt.focus(); prompt.select();
                const copied = document.execCommand("copy");
                focus?.focus?.({ preventScroll: true });
                if (!copied) throw new Error("复制失败，请选中提示词后手动复制。");
            }
            if (!disposed) copyStatus.textContent = "已复制提示词";
        } catch (error) { if (!disposed) report(error); }
        finally { if (!disposed) copy.disabled = !prompt.value; }
    });
    listen(document, "keydown", event => {
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); return; }
        if (event.key !== "Tab") return;
        const focusable = [...dialog.querySelectorAll('button:not(:disabled), textarea, [tabindex="0"]')]
            .filter(node => !node.hidden && !node.closest("[hidden]") && node.getClientRects().length);
        const first = focusable[0]; const last = focusable.at(-1);
        if (!first) { event.preventDefault(); dialog.focus(); return; }
        const focused = document.activeElement;
        if (event.shiftKey && (focused === first || !dialog.contains(focused))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (focused === last || !dialog.contains(focused))) { event.preventDefault(); first.focus(); }
    }, { capture: true });
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(scheduleTransform) : null;
    observer?.observe(viewport);
    listen(window, "resize", scheduleTransform);
    const handle = { close, destroy: close, dispose: close, update, element: overlay };
    activeViewer = handle;
    document.body.append(overlay);
    update();
    closeButton.focus({ preventScroll: true });
    return handle;
}

export const mountViewer = openStoryboardViewer;
