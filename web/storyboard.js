import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { createStoryboardView, previewCSS } from "./storyboard-ui.js";
import { pageTitle } from "./storyboard-model.js";

const TAB_ID = "soda-storyboard";
const EMPTY = "上传或拖入 .storyboard.json";
const IMPORT = "SodaLoadStoryboard";
const LINK = "SodaLoadStoryboardPage";
const PREVIEW = "SodaStoryboardPreview";
const PROJECTS_KEY = "soda-storyboard.projects.v1";
const state = { projectDir: "", pageId: "", url: "" };
const notices = new Map();
let sidebar;
let sidebarGeneration = 0;

async function request(path, body) {
    const options = body === undefined ? {} : body instanceof FormData ? { method: "POST", body } : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    };
    const response = await api.fetchApi(`/soda_storyboard/${path}`, options);
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
    return value;
}

function report(error) {
    const message = String(error.message || error);
    const now = Date.now();
    if (now - (notices.get(message) || 0) < 5000) return;
    notices.set(message, now);
    if (notices.size > 100) notices.delete(notices.keys().next().value);
    app.extensionManager.toast.add({ severity: "error", summary: "分镜", detail: message, life: 8000 });
}

function button(label, action) {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.onclick = async () => {
        element.disabled = true;
        try { return await action(); } catch (error) { report(error); }
        finally { element.disabled = false; }
    };
    return element;
}

const widget = (node, name) => node.widgets?.find(w => w.name === name);
function setValue(node, name, value) {
    const item = widget(node, name);
    if (!item) return;
    item.value = value;
    item.callback?.(value);
    if (name === "filename") node._sodaView?.syncFiles(item.options?.values || [], node._sodaFileLabels);
    node.setDirtyCanvas?.(true, true);
}
function status(node, message, error = false) {
    if (!node._sodaView) return;
    node._sodaView.status.textContent = message;
    node._sodaView.status.dataset.error = String(error);
    node._sodaView.status.hidden = !message;
}
function projects() {
    try {
        const stored = JSON.parse(globalThis.localStorage?.getItem(PROJECTS_KEY) || "[]");
        return Array.isArray(stored) ? stored.filter(p => typeof p === "string" && p) : [];
    } catch { return []; }
}
function remember(path) {
    if (!path) return;
    try { globalThis.localStorage?.setItem(PROJECTS_KEY, JSON.stringify([...new Set([...projects(), path])])); }
    catch { /* Browser storage can be disabled; this session still works. */ }
}
function combo(node, name, values) {
    const item = widget(node, name);
    if (!item) return;
    if (item._sodaOriginal) {
        item._sodaOriginal.type = "combo";
        if (!item.hidden) item.type = "combo";
    } else item.type = "combo";
    item.options = { ...item.options, values };
    if (name === "filename") node._sodaView?.syncFiles(values, node._sodaFileLabels);
}
async function pages(projectDir) {
    if (!projectDir) return [];
    return (await request(`pages?${new URLSearchParams({ project_dir: projectDir })}`)).pages;
}

function showEditor(result) {
    const url = new URL(result.url);
    if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || !url.port) {
        throw new Error("编辑器返回的地址无效");
    }
    state.url = result.url;
    if (result.project_dir) Object.assign(state, { projectDir: result.project_dir, pageId: result.page_id || "" });
    if (sidebar) renderSidebar(sidebar);
    const tabs = app.extensionManager.sidebarTab;
    if (tabs) tabs.activeSidebarTabId = TAB_ID;
}
async function startEditor(projectDir, pageId) {
    if (!projectDir || !pageId) throw new Error("请先选择项目和页面");
    const result = await request("editor/start", { project_dir: projectDir, page_id: pageId });
    Object.assign(state, { projectDir, pageId });
    showEditor(result);
}
function renderSidebar(container) {
    const generation = ++sidebarGeneration;
    let requestGeneration = 0;
    sidebar = container;
    container.replaceChildren();
    container.classList.add("soda-storyboard-sidebar");
    const directory = document.createElement("input");
    directory.placeholder = "项目目录（导入文件请使用节点上的编辑按钮）";
    directory.value = state.projectDir;
    directory.setAttribute("aria-label", "分镜项目目录");
    const page = document.createElement("select");
    page.setAttribute("aria-label", "分镜页面");
    page.add(new Option(state.pageId || "选择页面", state.pageId));
    const refresh = async () => {
        const requestId = ++requestGeneration;
        const current = () => generation === sidebarGeneration && requestId === requestGeneration && sidebar === container;
        try {
            const path = directory.value;
            const list = await pages(path);
            if (!current() || path !== directory.value) return;
            page.replaceChildren(...list.map(p => new Option(p.id, p.id)));
            if (list.some(p => p.id === state.pageId)) page.value = state.pageId;
            Object.assign(state, { projectDir: path, pageId: page.value });
        } catch (error) { if (current()) page.replaceChildren(new Option(error.message, "")); }
    };
    directory.onchange = () => { remember(directory.value); refresh(); };
    page.onchange = () => { state.pageId = page.value; };
    const controls = document.createElement("div");
    controls.className = "soda-storyboard-controls";
    controls.append(directory, page,
        button("打开 / 复用编辑器", () => startEditor(directory.value, page.value)),
        button("停止本项目编辑器", async () => {
            const result = await request("editor/stop", { project_dir: directory.value });
            if (result.stopped) { state.url = ""; renderSidebar(container); }
            app.extensionManager.toast.add({ severity: "info", summary: "分镜", detail: result.message });
        }));
    container.append(controls);
    if (state.url) {
        const frame = document.createElement("iframe");
        frame.title = "Soda Storyboard 分镜编辑器";
        frame.src = state.url;
        container.append(frame);
    }
    if (directory.value) refresh();
}

function visiblePanel(node, linked, preview) {
    node._sodaView = createStoryboardView(node, {
        button, linked, preview, onError: report,
        onUpload: () => node._sodaUploadInput?.click(),
        onSelect: value => setValue(node, "filename", value),
        onEdit: () => node._sodaEdit?.(),
        onExport: () => exportImported(node),
    });
    status(node, "请先导入分镜包");
}
function previewSource(node) {
    const input = node.inputs?.find(item => item.name === "page_info" && item.link != null);
    const link = input ? app.graph?.links[input.link] : null;
    return link ? app.graph.getNodeById(link.origin_id) : null;
}
function applyMetadata(node, metadata) {
    node._sodaMeta = metadata;
    node._sodaView?.render(metadata);
    if (node.comfyClass === IMPORT || widget(node, "filename")) node.title = `导入分镜 · ${pageTitle(metadata, widget(node, "filename")?.value)}`;
    status(node, "");
    for (const other of app.graph?._nodes || []) other._sodaRefreshChoices?.();
    node.setDirtyCanvas?.(true, true);
}
function query(node) {
    return Object.fromEntries(["filename", "project_dir", "page_id", "dialogue_mode", "slant_mode",
        "include_triggers", "width", "height"].flatMap(name => {
        const item = widget(node, name);
        return item ? [[name, String(item.value)]] : [];
    }));
}
async function refreshNode(node, linked) {
    if (node._sodaPending) return node._sodaPending;
    const values = query(node);
    const absent = linked ? !values.project_dir || !values.page_id : !values.filename || values.filename === EMPTY;
    if (absent) {
        node._sodaMeta = null;
        if (node._sodaView) node._sodaView.kind = "page";
        node._sodaView?.render(null);
        status(node, "请先导入分镜包", true);
        return null;
    }
    const generation = node._sodaGeneration || 0;
    const pending = (async () => {
        try {
            if (node._sodaMeta?.revision) values.revision = node._sodaMeta.revision;
            const metadata = await request(`${linked ? "link" : "inspect"}?${new URLSearchParams(values)}`);
            if ((node._sodaGeneration || 0) !== generation) return null;
            if (!metadata.unchanged) applyMetadata(node, metadata);
            return node._sodaMeta;
        } catch (error) {
            if ((node._sodaGeneration || 0) === generation) {
                node._sodaMeta = null;
                node._sodaView?.render(null);
                status(node, error.message, true);
            }
            return null; // Automatic restore/refresh failures never create toasts.
        } finally { if (node._sodaPending === pending) node._sodaPending = null; }
    })();
    node._sodaPending = pending;
    return pending;
}
function watch(node, names, changed) {
    for (const name of names) {
        const item = widget(node, name);
        if (!item) continue;
        const previous = item.callback;
        item.callback = function (...args) { previous?.apply(this, args); changed(name); };
    }
}
async function uploadFile(node, file) {
    const generation = node._sodaUploadGeneration = (node._sodaUploadGeneration || 0) + 1;
    const form = new FormData();
    form.append("file", file, file.name);
    let result;
    try { result = await request("upload?kind=storyboard", form); }
    catch (error) { if (generation !== node._sodaUploadGeneration) return null; throw error; }
    const item = widget(node, "filename");
    node._sodaFileLabels = { ...node._sodaFileLabels, [result.name]: result.original_filename || file.name };
    combo(node, "filename", [...new Set([EMPTY, ...(item.options?.values || []), result.name])]);
    if (generation !== node._sodaUploadGeneration) return result;
    setValue(node, "filename", result.name);
    await node._sodaRefresh?.();
    return result;
}
function attachImporter(node) {
    node._sodaRefreshFiles = async () => {
        try {
            const result = await request("files?kind=storyboard");
            const selected = widget(node, "filename").value;
            node._sodaFileLabels = { ...node._sodaFileLabels, ...result.file_labels };
            combo(node, "filename", [...new Set([EMPTY, ...result.files, ...(selected && selected !== EMPTY ? [selected] : [])])]);
        } catch { /* Automatic list refresh never raises a toast. */ }
    };
    node._sodaRefreshFiles();
    node._sodaView.root.addEventListener("dragover", event => event.preventDefault());
    node._sodaView.root.addEventListener("drop", event => {
        const file = [...(event.dataTransfer?.files || [])].find(item => item.name.toLowerCase().endsWith(".json"));
        if (!file) return;
        event.preventDefault(); event.stopImmediatePropagation();
        uploadFile(node, file).catch(error => { status(node, error.message, true); report(error); });
    });
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,.storyboard.json,.moss.json";
    input.onchange = async () => {
        if (!input.files?.[0]) return;
        try { await uploadFile(node, input.files[0]); } catch (error) { status(node, error.message, true); report(error); }
        input.value = "";
    };
    node._sodaUploadInput = input;
}
async function editImported(node) {
    const metadata = node._sodaMeta || await node._sodaRefresh();
    if (!metadata) { status(node, "请先导入分镜包", true); return; }
    const convert = metadata.kind === "moss";
    if (convert && !globalThis.confirm("MOSS JSON 转换为分镜单是近似的，需检查格子和文字位置。继续转换？")) return;
    showEditor(await request("import/edit", { ...query(node), convert_moss: convert }));
    node._sodaGeneration = (node._sodaGeneration || 0) + 1;
    node._sodaPending = null;
    await node._sodaRefresh();
}
async function exportImported(node) {
    if (!node._sodaMeta || node._sodaMeta.kind === "moss") {
        status(node, "请先导入分镜包；MOSS JSON 请先转换后编辑", true); return;
    }
    const result = await request("import/export", { filename: widget(node, "filename").value });
    if (result.bundle) {
        const url = URL.createObjectURL(new Blob([JSON.stringify(result.bundle, null, 2)], { type: "application/json" }));
        const download = document.createElement("a");
        download.href = url; download.download = result.name; download.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    await node._sodaRefreshFiles();
    setValue(node, "filename", result.name);
}
async function refreshPages(node) {
    const project = widget(node, "project_dir");
    remember(project.value);
    combo(node, "project_dir", [...new Set(["", ...projects(), project.value])]);
    if (!project.value) { status(node, "请先导入分镜包", true); return; }
    try {
        const path = project.value;
        const list = await pages(path);
        if (path !== project.value) return;
        combo(node, "page_id", list.map(p => p.id));
        if (!list.some(p => p.id === widget(node, "page_id").value)) {
            widget(node, "page_id").value = list[0]?.id || "";
        }
        await node._sodaRefresh();
    } catch (error) { status(node, error.message, true); }
}
function attachProject(node) {
    combo(node, "project_dir", [...new Set(["", ...projects(), widget(node, "project_dir")?.value || ""])]);
    combo(node, "page_id", [widget(node, "page_id")?.value || ""]);
    const row = document.createElement("div");
    row.className = "soda-storyboard-controls";
    const directory = document.createElement("input");
    directory.placeholder = "首次填写项目目录，之后从下拉选择";
    row.append(directory, button("记住项目", async () => {
        if (!directory.value.trim()) return;
        setValue(node, "project_dir", directory.value.trim());
        await refreshPages(node);
    }));
    node.addDOMWidget("soda_project_picker", "soda-project-picker", row, { serialize: false });

}
async function sourceInfo(node, seen = new Set()) {
    if (!node || seen.has(node.id)) return null;
    seen.add(node.id);
    if (node._sodaMeta?.page_info) return JSON.parse(node._sodaMeta.page_info);
    if (node._sodaRefresh) {
        const metadata = await node._sodaRefresh();
        return metadata?.page_info ? JSON.parse(metadata.page_info) : null;
    }
    const input = node.inputs?.find(i => i.name === "page_info") || node.inputs?.[0];
    if (input?.link != null) {
        const link = app.graph.links[input.link];
        return sourceInfo(app.graph.getNodeById(link?.origin_id), seen);
    }
    const value = widget(node, "page_info")?.value;
    if (value) return JSON.parse(value);
    return null;
}
function attachChoices(node) {
    node._sodaRefreshChoices = async () => {
        const generation = node._sodaChoicesGeneration = (node._sodaChoicesGeneration || 0) + 1;
        try {
            const input = node.inputs?.find(i => i.name === "page_info");
            const linkId = input?.link;
            const snapshot = widget(node, "page_info")?.value;
            const link = input?.link != null ? app.graph.links[input.link] : null;
            const value = link ? await sourceInfo(app.graph.getNodeById(link.origin_id)) :
                JSON.parse(widget(node, "page_info")?.value || "null");
            if (generation !== node._sodaChoicesGeneration || input?.link !== linkId ||
                widget(node, "page_info")?.value !== snapshot || !value?.page) return;
            const panels = [...value.page.panels].sort((a, b) => a.order - b.order);
            const ids = panels.map(p => p.id);
            combo(node, "panel", ids);
            const current = widget(node, "panel");
            if (!ids.includes(current.value)) current.value = ids[Number(current.value) - 1] || ids[0] || "";
            const panel = panels.find(p => p.id === current.value);
            const characters = [...new Set([...(panel?.character_ids || []),
                ...(panel?.figures || []).map(f => f.character_id)])];
            combo(node, "character_id", characters);
            const character = widget(node, "character_id");
            if (character && !characters.includes(character.value)) character.value = characters[0] || "";
            node.setDirtyCanvas?.(true, true);
        } catch { /* Missing upstream data is normal while restoring a workflow. */ }
    };
    watch(node, ["page_info", "panel"], () => node._sodaRefreshChoices());
}

function recognized(value) {
    return value && (value.format === "soda-storyboard-bundle-v1" || Array.isArray(value.panels) ||
        (value.summary && Array.isArray(value.items)));
}
async function importDropped(file, event) {
    const value = JSON.parse(await file.text());
    if (!recognized(value)) return false;
    // Validate/upload first; a corrupt file must not leave an orphan canvas node.
    const form = new FormData();
    form.append("file", file, file.name);
    const uploaded = await request("upload?kind=storyboard", form);
    const node = globalThis.LiteGraph.createNode(IMPORT);
    if (!node) throw new Error("导入分镜节点尚未注册，请重启 ComfyUI");
    node.pos = event && app.canvas.convertEventToCanvasOffset ? app.canvas.convertEventToCanvasOffset(event) : [100, 100];
    app.graph.add(node);
    const item = widget(node, "filename");
    combo(node, "filename", [...new Set([EMPTY, ...(item.options?.values || []), uploaded.name])]);
    setValue(node, "filename", uploaded.name);
    await node._sodaRefresh?.();
    return true;
}
function installDrop() {
    const original = app.handleFile;
    if (typeof original === "function") app.handleFile = async function (file, ...args) {
        if (file.name?.toLowerCase().endsWith(".json")) {
            try { if (await importDropped(file)) return; }
            catch (error) { report(error); return; }
        }
        return original.call(this, file, ...args);
    };
    const canvas = app.canvas?.canvas;
    canvas?.addEventListener("dragover", event => {
        if ([...(event.dataTransfer?.items || [])].some(item => item.kind === "file")) event.preventDefault();
    }, true);
    canvas?.addEventListener("drop", event => {
        const files = [...(event.dataTransfer?.files || [])].filter(file => file.name.toLowerCase().endsWith(".json"));
        if (!files.length) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        (async () => {
            for (const file of files) {
                try {
                    if (!await importDropped(file, event)) {
                        if (typeof original === "function") await original.call(app, file);
                        else await app.loadGraphData(JSON.parse(await file.text()));
                    }
                } catch (error) { report(error); }
            }
        })();
    }, true);
}

app.registerExtension({
    name: "Soda.Storyboard",
    setup() {
        const css = document.createElement("style");
        css.textContent = `
            .soda-storyboard-sidebar { display:flex; flex-direction:column; height:100%; min-height:0; }
            .soda-storyboard-controls { display:flex; flex-wrap:wrap; gap:6px; padding:6px; }
            .soda-storyboard-controls input { width:100%; }
            .soda-storyboard-sidebar iframe { flex:1; min-height:400px; width:100%; border:0; background:white; }
            ${previewCSS}
        `;
        document.head.append(css);
        app.extensionManager.registerSidebarTab({ id: TAB_ID, title: "分镜", tooltip: "Soda Storyboard",
            icon: "pi pi-book", type: "custom", render: renderSidebar,
            destroy: () => { sidebarGeneration++; sidebar = undefined; } });
        installDrop();
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const linked = nodeData.name === LINK;
        const imported = nodeData.name === IMPORT;
        const preview = nodeData.name === PREVIEW;
        const choices = ["SodaCropPanel", "SodaCharacterMask"].includes(nodeData.name);
        if (!linked && !imported && !preview && !choices) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            if (choices) attachChoices(this);
            else {
                this._sodaEdit = async () => {
                    if (imported) return editImported(this);
                    const source = preview ? previewSource(this) : null;
                    if (source && source !== this && source._sodaEdit) return source._sodaEdit();
                    const projectDir = widget(this, "project_dir")?.value;
                    const pageId = widget(this, "page_id")?.value;
                    if (projectDir && pageId) return startEditor(projectDir, pageId);
                    if (preview) throw new Error("当前是 page_info 分镜快照，请在来源分镜节点中编辑，或填写项目目录和页面后打开编辑器。");
                    return startEditor(projectDir, pageId);
                };
                visiblePanel(this, linked, preview);
                this._sodaRefresh = async () => {
                    const previewInput = preview && this.inputs?.find(input => input.name === "page_info" && input.link != null);
                    if (previewInput) {
                        this._sodaPreviewLink = previewInput.link;
                        const generation = this._sodaGeneration || 0;
                        const source = previewSource(this);
                        const metadata = source?._sodaMeta || await source?._sodaRefresh?.();
                        if ((this._sodaGeneration || 0) !== generation || previewSource(this) !== source) return null;
                        if (metadata) applyMetadata(this, metadata);
                        else {
                            this._sodaMeta = null;
                            this._sodaView.render(null);
                            status(this, "上游尚未提供可预览的分镜");
                        }
                        return metadata;
                    }
                    if (preview && String(widget(this, "page_info")?.value || "").trim()) {
                        if (!this._sodaMeta) status(this, "运行节点后预览 page_info 分镜");
                        return this._sodaMeta;
                    }
                    return refreshNode(this, linked || preview);
                };
                if (linked) attachProject(this); else if (imported) attachImporter(this);
                watch(this, ["filename", "project_dir", "page_id", "dialogue_mode", "slant_mode", "include_triggers", "width", "height", "page_info"], name => {
                    this._sodaGeneration = (this._sodaGeneration || 0) + 1;
                    this._sodaMeta = null;
                    this._sodaPending = null;
                    if (name === "filename") this._sodaView.kind = "page";
                    this._sodaView.render(null);
                    if (imported && name === "filename") {
                        const selected = widget(this, "filename").value;
                        this.title = selected && selected !== EMPTY ? `导入分镜 · ${pageTitle({ filename: selected })}` : "导入分镜";
                        for (const other of app.graph?._nodes || []) other._sodaRefreshFiles?.();
                    }
                    if (name === "project_dir") refreshPages(this); else this._sodaRefresh();
                });
                const timer = setInterval(() => {
                    if (!document.hidden && this.graph) this._sodaRefresh();
                }, 1500);
                timer.unref?.();
                this._sodaTimer = timer;
                if (imported && (!widget(this, "filename").value || widget(this, "filename").value === EMPTY)) this.title = "导入分镜";
                this.setSize([420, 720]);
            }
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = configured?.apply(this, arguments);
            if (choices) this._sodaRefreshChoices?.();
            else if (linked) refreshPages(this);
            else if (preview) this._sodaRefresh?.();
            else { this._sodaRefreshFiles?.(); this._sodaRefresh?.(); }
            return result;
        };
        const connections = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = connections?.apply(this, arguments);
            this._sodaRefreshChoices?.();
            if (preview) {
                this._sodaGeneration = (this._sodaGeneration || 0) + 1;
                this._sodaPending = null;
                const link = this.inputs?.find(input => input.name === "page_info")?.link ?? null;
                if (link !== (this._sodaPreviewLink ?? null)) {
                    this._sodaMeta = null;
                    this._sodaView?.render(null);
                }
                this._sodaPreviewLink = link;
                this._sodaRefresh?.();
            }
            return result;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            executed?.apply(this, arguments);
            if (message?.soda?.[0]) applyMetadata(this, message.soda[0]);
        };
        const removed = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            clearInterval(this._sodaTimer);
            this._sodaGeneration = (this._sodaGeneration || 0) + 1;
            this._sodaChoicesGeneration = (this._sodaChoicesGeneration || 0) + 1;
            this._sodaUploadGeneration = (this._sodaUploadGeneration || 0) + 1;
            this._sodaView?.destroy();
            return removed?.apply(this, arguments);
        };
        const resized = nodeType.prototype.onResize;
        nodeType.prototype.onResize = function (size) {
            resized?.apply(this, arguments);
            this._sodaView?.resize();
        };
    },
});
