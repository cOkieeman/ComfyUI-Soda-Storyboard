import { buildStoryboardModel, displayFilename, widgetVisibility } from "./storyboard-model.js";
import { openStoryboardViewer } from "./storyboard-viewer.js";

export const previewCSS = `
.soda-preview { --soda-bg:var(--comfy-menu-bg,#202020); --soda-text:var(--input-text,#ddd); --soda-border:var(--border-color,#666); --soda-input:var(--comfy-input-bg,#333); display:flex; flex-direction:column; box-sizing:border-box; gap:8px; width:100%; height:100%; min-width:0; min-height:0; padding:8px; overflow:auto; container-type:inline-size; background:var(--soda-bg); color:var(--soda-text); font:14px/1.45 var(--comfy-font,Arial,sans-serif); border:1px solid var(--soda-border); border-radius:6px; }
.soda-preview *, .soda-preview *::before, .soda-preview *::after { box-sizing:border-box; }
.soda-preview [hidden] { display:none !important; }
.soda-preview button,.soda-preview select { min-height:30px; min-width:0; border:1px solid var(--soda-border); border-radius:4px; background:var(--soda-input); color:var(--soda-text); font:inherit; font-size:12px; padding:4px 8px; cursor:pointer; }
.soda-preview button:focus-visible,.soda-preview select:focus-visible,.soda-preview textarea:focus-visible,.soda-preview img:focus-visible { outline:2px solid var(--primary-color,#58a6ff); outline-offset:1px; }
.soda-preview button:disabled { opacity:.5; cursor:default; }
.soda-file-row { display:flex; flex-wrap:wrap; gap:5px; flex:none; align-items:center; }
.soda-file-row select { flex:1 1 110px; width:0; text-overflow:ellipsis; }
.soda-file-row button { flex:0 0 auto; }
.soda-file-row .soda-more { flex:0 0 auto; }
.soda-more { position:relative; }
.soda-more summary { padding:4px 10px; min-height:30px; cursor:pointer; border:1px solid var(--soda-border); border-radius:4px; list-style:none; }
.soda-more[open] { flex-basis:100%; }
.soda-more[open] summary { display:inline-block; }
.soda-more button { display:block; width:100%; margin-top:4px; text-align:left; }
.soda-tags { display:flex; flex-wrap:wrap; gap:5px; flex:none; }
.soda-tag { border:1px solid var(--soda-border); padding:2px 7px; border-radius:6px; font-size:12px; overflow-wrap:anywhere; }
.soda-warnings { display:flex; flex-direction:column; gap:4px; max-height:100px; overflow:auto; flex:none; }
.soda-warning { display:flex; align-items:start; gap:6px; padding:5px 7px; border:1px solid var(--warning-color,#b18832); border-radius:4px; background:color-mix(in srgb,var(--warning-color,#d7a130) 15%,var(--soda-bg)); color:var(--soda-text); font-size:12px; overflow-wrap:anywhere; }
.soda-warning span { flex:1; }
.soda-warning button { border:0; padding:0 4px; min-height:20px; background:transparent; }
.soda-preview [role=status] { flex:none; font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; }
.soda-preview [data-error=true] { color:var(--error-text,#e25c67); }
.soda-tabs { display:flex; flex:none; border-bottom:1px solid var(--soda-border); gap:5px; }
.soda-tabs button { border:0; border-radius:4px 4px 0 0; flex:1; background:transparent; }
.soda-tabs button[aria-selected=true] { background:var(--soda-input); box-shadow:inset 0 -2px var(--primary-color,#58a6ff); font-weight:600; }
.soda-tab-body { display:flex; flex-direction:column; flex:1 1 0; min-height:0; min-width:0; overflow:hidden; }
.soda-image-pane { display:flex; flex-direction:column; flex:1; min-height:0; width:100%; overflow:hidden; background:#000; border-radius:3px; }
.soda-image-frame { display:flex; align-items:center; justify-content:center; width:100%; flex:1; min-height:0; overflow:hidden; }
.soda-image-legend { display:flex; flex-wrap:wrap; gap:12px; flex:none; width:100%; padding:4px 6px; background:var(--soda-bg); color:var(--soda-text); font-size:12px; }
.soda-image-legend span { border-left:3px solid; padding-left:5px; }
.soda-image-pane img { display:block; width:100%; height:100%; min-height:0; min-width:0; object-fit:contain; cursor:zoom-in; }
.soda-image-empty { padding:12px; color:#ccc; font-size:12px; text-align:center; }
.soda-prompt-pane { display:flex; flex-direction:column; flex:1; min-height:0; gap:5px; }
.soda-prompt-tools { display:flex; justify-content:flex-end; gap:5px; flex:none; }
.soda-preview textarea { display:block; flex:1; width:100%; min-height:0; resize:none; border:1px solid var(--soda-border); border-radius:3px; background:var(--soda-input); color:var(--soda-text); padding:8px; overflow:auto; font:13px/1.55 Consolas,monospace; }
.soda-panel-list { flex:1; min-height:0; overflow:auto; padding:0; margin:0; list-style:none; }
.soda-panel-entry { padding:10px 4px; border-bottom:1px solid var(--soda-border); overflow-wrap:anywhere; }
.soda-panel-entry strong { font-size:14px; }
.soda-panel-entry p { margin:4px 0 0; font-size:13px; white-space:pre-wrap; }
.soda-entry-group { padding:8px 4px 3px; font-size:13px; font-weight:600; }
.soda-size-hint { flex:none; font-size:12px; }
.soda-advanced { flex:none; text-align:left; }
.soda-preview[data-compact=true] .soda-tabs,.soda-preview[data-compact=true] .soda-tab-body,.soda-preview[data-compact=true] .soda-warnings,.soda-preview[data-compact=true] .soda-advanced { display:none; }
@container (max-width:340px) { .soda-file-row select { flex-basis:100%; width:100%; } .soda-file-row button { flex:1 0 auto; } }
`;

const field = (node, name) => node.widgets?.find(item => item.name === name);

// Keep the widget and its value in the original serialization order. Both the
// current frontend and legacy LiteGraph recognize hidden widgets differently.
export function setWidgetVisible(item, visible) {
    if (!item) return;
    if (!item._sodaOriginal) item._sodaOriginal = {
        type: item.type, computeSize: item.computeSize, computeLayoutSize: item.computeLayoutSize,
        hidden: item.hidden, advanced: item.advanced,
    };
    const original = item._sodaOriginal;
    item.hidden = !visible;
    item.advanced = !visible;
    item.type = visible ? original.type : "hidden";
    item.computeSize = visible ? original.computeSize : () => [0, -4];
    item.computeLayoutSize = visible ? original.computeLayoutSize : () => ({ minHeight: 0, maxHeight: 0, minWidth: 0 });
}

export function createStoryboardView(node, { button, onEdit, onExport, onUpload, onSelect, linked = false, preview = false, onError }) {
    const root = document.createElement("div");
    root.className = "soda-preview";
    const row = document.createElement("div");
    row.className = "soda-file-row";
    const select = document.createElement("select");
    select.setAttribute("aria-label", "已导入的分镜文件");
    select.onchange = () => onSelect?.(select.value);
    select.hidden = linked || preview;
    const upload = button("上传", () => onUpload?.());
    upload.hidden = linked || preview;
    const edit = button("编辑", () => onEdit?.());
    edit.title = "在编辑器中打开";
    const viewButton = button("⛶ 查看", () => openViewer(viewButton));
    const more = document.createElement("details");
    more.className = "soda-more";
    more.hidden = linked || preview;
    const summary = document.createElement("summary");
    summary.textContent = "⋯";
    summary.setAttribute("aria-label", "更多分镜操作");
    more.append(summary, button("另存为新分镜包", async () => { await onExport?.(); more.open = false; }));
    row.append(select, upload, viewButton, edit, more);
    const tags = document.createElement("div");
    tags.className = "soda-tags";
    const warnings = document.createElement("div");
    warnings.className = "soda-warnings";
    const line = document.createElement("div");
    line.setAttribute("role", "status");
    const tabs = document.createElement("div");
    tabs.className = "soda-tabs";
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "分镜内容");
    const body = document.createElement("div");
    body.className = "soda-tab-body";
    const imagePane = document.createElement("div");
    imagePane.className = "soda-image-pane";
    const draft = document.createElement("img");
    draft.alt = "分镜图，点击或按回车在大窗口查看";
    draft.tabIndex = 0;
    draft.hidden = true;
    draft.onclick = () => openViewer(draft);
    draft.ondblclick = () => openViewer(draft);
    draft.onkeydown = event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); openViewer(draft); } };
    const empty = document.createElement("span");
    empty.className = "soda-image-empty";
    empty.textContent = "上传或拖入分镜文件，查看整页分镜图";
    const imageFrame = document.createElement("div"); imageFrame.className = "soda-image-frame";
    imageFrame.append(draft, empty);
    const legend = document.createElement("div"); legend.className = "soda-image-legend";
    imagePane.append(imageFrame, legend);
    const promptPane = document.createElement("div");
    promptPane.className = "soda-prompt-pane";
    const prompt = document.createElement("textarea");
    prompt.readOnly = true;
    prompt.spellcheck = false;
    prompt.placeholder = "最终 MOSS JSON 提示词";
    prompt.setAttribute("aria-label", "最终 MOSS 提示词（只读）");
    const tools = document.createElement("div");
    tools.className = "soda-prompt-tools";
    let formatted = true;
    const renderText = () => {
        const text = node._sodaMeta?.moss_json || "";
        try { prompt.value = text ? JSON.stringify(JSON.parse(text), null, formatted ? 2 : 0) : ""; }
        catch { prompt.value = text; }
    };
    const copy = button("复制", async () => { await navigator.clipboard.writeText(prompt.value); });
    const toggle = button("压缩", () => { formatted = !formatted; toggle.textContent = formatted ? "压缩" : "格式化"; renderText(); });
    tools.append(copy, toggle);
    promptPane.append(tools, prompt);
    const list = document.createElement("ol");
    list.className = "soda-panel-list";
    body.append(imagePane, promptPane, list);
    const panes = [imagePane, promptPane, list];
    const tabButtons = ["分镜图", "提示词", "逐格"].map((label, index) => {
        const tab = button(label, () => activate(index));
        tab.setAttribute("role", "tab");
        tab.onkeydown = event => {
            const next = event.key === "ArrowRight" ? (index + 1) % 3 : event.key === "ArrowLeft" ? (index + 2) % 3 : null;
            if (next !== null) { event.preventDefault(); activate(next); tabButtons[next].focus(); }
        };
        tabs.append(tab);
        panes[index].setAttribute("role", "tabpanel");
        return tab;
    });
    function activate(index) {
        panes.forEach((pane, i) => { pane.hidden = i !== index; });
        tabButtons.forEach((tab, i) => { tab.setAttribute("aria-selected", String(i === index)); tab.tabIndex = i === index ? 0 : -1; });
    }
    activate(0);
    const advancedButton = button("▸ 高级", () => {
        view.advanced = !view.advanced;
        updateAdvanced();
    });
    advancedButton.className = "soda-advanced";
    advancedButton.hidden = preview;
    advancedButton.setAttribute("aria-expanded", "false");
    const sizeHint = document.createElement("div"); sizeHint.className = "soda-size-hint";
    sizeHint.textContent = "宽高填 0 为自动；正数覆盖文件尺寸。";
    root.append(row, tags, warnings, line, tabs, body, advancedButton, sizeHint);
    const domWidget = node.addDOMWidget("soda_preview", "soda-preview", root, {
        serialize: false, hideOnZoom: false, hideInPanel: true,
        getMinHeight: () => 136, getHeight: () => "100%",
    });
    if (domWidget) {
        domWidget.serialize = false;
        // Only the nonserialized DOM widget moves; input widget order is retained.
        const index = node.widgets.findIndex(item => ["dialogue_mode", "slant_mode", "include_triggers", "width"].includes(item.name));
        const current = node.widgets.indexOf(domWidget);
        if (index >= 0 && current > index) { node.widgets.splice(current, 1); node.widgets.splice(index, 0, domWidget); }
    }
    const dismissed = new Set();
    const view = { root, status: line, draft, prompt, renderText, select, edit, tools, toggle, copy, advancedButton,
        domWidget, advanced: false, metadata: null, viewer: null, kind: "page", activate,
        syncFiles(values, labels = {}) {
            const selected = field(node, "filename")?.value || "";
            select.replaceChildren(...values.map(value => new Option(labels[value] || displayFilename(value), value)));
            select.value = selected;
        },
        render(metadata) {
            if (metadata?.filename !== view.metadata?.filename) dismissed.clear();
            view.metadata = metadata;
            if (metadata?.kind) view.kind = metadata.kind;
            const model = metadata ? buildStoryboardModel(metadata) : null;
            draft.hidden = !model?.image;
            empty.hidden = !!model?.image;
            if (model?.image) draft.src = model.image;
            else draft.removeAttribute?.("src");
            tabButtons[2].textContent = model?.detailsLabel || "逐格";
            legend.replaceChildren(...(model?.legend || []).map(item => {
                const label = document.createElement("span"); label.textContent = item.label;
                label.style.borderColor = item.color; return label;
            }));
            legend.hidden = !model?.legend?.length;
            tags.replaceChildren(...(model?.tags || []).map(tag => {
                const element = document.createElement("span"); element.className = "soda-tag"; element.textContent = tag.label; return element;
            }));
            warnings.replaceChildren(...(model?.warnings || []).filter(text => !dismissed.has(text)).map(text => {
                const warning = document.createElement("div"); warning.className = "soda-warning";
                const content = document.createElement("span"); content.textContent = text;
                const close = button("×", () => { dismissed.add(text); view.render(view.metadata); });
                close.setAttribute("aria-label", `关闭提示：${text}`); warning.append(content, close); return warning;
            }));
            warnings.hidden = !warnings.children.length;
            let group;
            list.replaceChildren(...(model?.entries || []).flatMap(entry => {
                const rows = [];
                if (entry.groupLabel && group !== entry.group) {
                    const heading = document.createElement("li"); heading.className = "soda-entry-group";
                    heading.textContent = entry.groupLabel; rows.push(heading);
                }
                group = entry.group;
                const item = document.createElement("li"); item.className = "soda-panel-entry";
                const title = document.createElement("strong");
                const names = entry.characters.map(character => character.name).join("、");
                const label = entry.kind === "text" ? "页上文字" : entry.kind === "item" ? `条目 ${entry.number}` : `第 ${entry.number} 格`;
                title.textContent = `${label}${entry.shot ? ` · ${entry.shot}` : ""}${names ? ` · 出场角色：${names}` : ""}`;
                item.append(title);
                if (entry.description && entry.kind !== "text") { const description = document.createElement("p"); description.textContent = entry.description; item.append(description); }
                for (const text of entry.texts) {
                    const element = document.createElement("p");
                    const prefix = text.speaker || ({ narration: "旁白", sfx: "音效", thought: "心声", "文字": "文字" }[text.kind] || "台词");
                    element.textContent = `${prefix}：${text.text}`; item.append(element);
                }
                rows.push(item); return rows;
            }));
            edit.disabled = !metadata;
            edit.title = metadata?.kind === "moss" ? "转换为分镜单后编辑（近似转换）" : "在编辑器中打开";
            viewButton.disabled = !metadata;
            renderText(); updateAdvanced();
        },
        resize() {
            const compact = (root.clientHeight || 500) < 220;
            root.dataset.compact = String(compact);
            if (compact && view.advanced) { view.advanced = false; updateAdvanced(); }
        },
        destroy() { observer?.disconnect(); view.viewer?.close(); },
    };
    function updateAdvanced() {
        const visible = widgetVisibility({ kind: node._sodaMeta?.kind || view.kind, advanced: view.advanced, linked });
        for (const [name, shown] of Object.entries(visible)) setWidgetVisible(field(node, name), shown);
        advancedButton.textContent = view.advanced ? "▾ 高级" : "▸ 高级";
        advancedButton.setAttribute("aria-expanded", String(view.advanced));
        sizeHint.hidden = !view.advanced || (node._sodaMeta?.kind || view.kind) !== "moss";
        for (const [name, label] of [["width", "宽度（0 自动）"], ["height", "高度（0 自动）"]]) {
            const item = field(node, name); if (item) item.label = label;
        }
        node.setDirtyCanvas?.(true, true);
    }
    function openViewer(triggerElement) {
        if (!node._sodaMeta) return;
        view.viewer?.close();
        view.viewer = openStoryboardViewer({ metadata: node._sodaMeta, onEdit, onError, triggerElement });
    }
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(() => view.resize()) : null;
    observer?.observe(root);
    view.render(null);
    return view;
}
