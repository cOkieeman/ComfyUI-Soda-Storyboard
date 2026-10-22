import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { setImmediate as nextTurn } from "node:timers/promises";

class Element {
    constructor(tag) {
        Object.assign(this, { tag, children: [], value: "", style: {}, dataset: {}, attributes: {}, listeners: {}, listenerRecords: [],
            clientWidth: 800, clientHeight: 500, hidden: false });
        const classes = new Set();
        this.classList = { add: (...values) => values.forEach(value => classes.add(value)),
            remove: (...values) => values.forEach(value => classes.delete(value)), contains: value => classes.has(value),
            toggle(value, force) { const shown = force === undefined ? !classes.has(value) : force; shown ? classes.add(value) : classes.delete(value); return shown; } };
    }
    append(...children) { for (const child of children) { child.parentNode = this; this.children.push(child); } }
    add(child) { this.append(child); }
    replaceChildren(...children) { for (const child of this.children) child.parentNode = null; this.children = []; this.append(...children); }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return this.attributes[name] ?? null; }
    removeAttribute(name) { delete this.attributes[name]; delete this[name]; }
    addEventListener(name, fn, options = {}) {
        this.listeners[name] = fn;
        this.listenerRecords.push({ name, fn, signal: options.signal });
    }
    fire(type, fields = {}) {
        const event = { target: this, currentTarget: this, preventDefault() {}, stopPropagation() {}, ...fields };
        for (const record of this.listenerRecords) if (record.name === type && !record.signal?.aborted) record.fn(event);
    }
    async click() { this.clicked = true; if (this.tag === "a") calls.push({ download: this.download }); return this.onclick?.(); }
    focus() { document.activeElement = this; }
    remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.parentNode = null; }
    contains(element) { return this === element || this.children.some(child => child.contains(element)); }
    get childElementCount() { return this.children.length; }
    get isConnected() { return this === document.body || this === document.head || !!this.parentNode?.isConnected; }
    getBoundingClientRect() { return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight }; }
    getClientRects() { return this.hidden ? [] : [this.getBoundingClientRect()]; }
    closest(selector) { return selector === "[hidden]" && this.hidden ? this : this.parentNode?.closest(selector); }
}
const metadata = (name, revision = "r1") => ({
    filename: name, revision, kind: name.endsWith(".moss.json") ? "moss" : "page",
    summary: "320×240 · 2 格 · 1 句台词 · 建议：a LoRA a.safetensors 强度 0.8",
    warnings: ["建议一次只加载一个角色 LoRA"], width: 320, height: 240,
    draft_png_base64: `PNG-${revision}`, moss_json: JSON.stringify({ summary: { caption: revision }, items: [] }),
    page_info: JSON.stringify({ version: 1, page: { panels: [
        { id: "left", order: 2, character_ids: ["a", "b"] },
        { id: "right", order: 1, character_ids: ["a"] },
    ] }, characters: { a: {}, b: {} } }),
});
let extension, sidebar, ImportNode;
let revision = "r1", failed = false;
let nextId = 1;
const calls = [], toasts = [], files = new Map(), timers = new Set(), storage = new Map();
const graph = { _nodes: [], links: {}, add(node) { node.id = nextId++; node.graph = graph; this._nodes.push(node); },
    getNodeById(id) { return this._nodes.find(node => node.id === id); } };
const canvas = new Element("canvas");
const app = {
    graph, canvas: { canvas, convertEventToCanvasOffset: () => [250, 350] },
    async handleFile(file) { calls.push({ workflowFile: file.name }); },
    async loadGraphData(value) { calls.push({ workflow: value }); },
    registerExtension(value) { extension = value; },
    extensionManager: { registerSidebarTab(value) { sidebar = value; }, sidebarTab: {},
        toast: { add(value) { toasts.push(value); } } },
};
globalThis.__sodaTest = { app, api: { async fetchApi(path, options) {
    calls.push({ path, options });
    const url = new URL(path, "http://mock.invalid");
    const route = url.pathname.split("/soda_storyboard/")[1];
    let result;
    if (failed && ["upload", "inspect"].includes(route)) return { ok: false, async json() { return { error: "文件已损坏" }; } };
    if (route === "pages") result = { pages: [{ id: "p1", description: "Demo" }] };
    else if (route === "files") result = { files: [...files.keys()] };
    else if (route === "upload") {
        const file = options.body.get("file");
        files.set(file.name, metadata(file.name, revision));
        result = { name: file.name };
    } else if (route === "inspect") {
        const name = url.searchParams.get("filename");
        result = url.searchParams.get("revision") === revision ? { unchanged: true, revision } : metadata(name, revision);
    } else if (route === "link") result = metadata("linked", revision);
    else if (route.endsWith("/start")) result = { url: "http://127.0.0.1:8780/#page=p1" };
    else if (route === "import/edit") { revision = "r2"; result = {
        url: "http://127.0.0.1:8780/#page=p1", project_dir: "input/soda-storyboard/imported", page_id: "p1" }; }
    else if (route === "import/export") { files.set("saved.storyboard.json", metadata("saved.storyboard.json")); result = {
        name: "saved.storyboard.json", bundle: { format: "soda-storyboard-bundle-v1", page: {} } }; }
    else result = { stopped: true, message: "stopped" };
    return { ok: true, async json() { return result; } };
} } };
globalThis.document = Object.assign(new Element("document"), { head: new Element("head"), body: new Element("body"), hidden: false,
    createElement: tag => new Element(tag), createElementNS: (_ns, tag) => new Element(tag),
    getElementById(id) { const find = node => node.id === id ? node : node.children.map(find).find(Boolean); return find(this.head) || find(this.body); } });
globalThis.window = new Element("window");
globalThis.requestAnimationFrame = callback => { queueMicrotask(callback); return 1; };
globalThis.cancelAnimationFrame = () => {};
globalThis.Option = class extends Element {
    constructor(text, value) { super("option"); this.textContent = text; this.value = value; }
};
globalThis.localStorage = { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) };
Object.defineProperty(globalThis.navigator, "clipboard", {
    value: { async writeText(value) { calls.push({ clipboard: value }); } }, configurable: true,
});
globalThis.confirm = () => true;
globalThis.setInterval = (fn, ms) => { const timer = { fn, ms, unref() {} }; timers.add(timer); return timer; };
globalThis.clearInterval = timer => timers.delete(timer);
globalThis.LiteGraph = { createNode: () => { const node = new ImportNode(); node.onNodeCreated(); return node; } };
const source = (await readFile(new URL("../web/storyboard.js", import.meta.url), "utf8"))
    .replace('import { app } from "../../scripts/app.js";', "const { app } = globalThis.__sodaTest;")
    .replace('import { api } from "../../scripts/api.js";', "const { api } = globalThis.__sodaTest;")
    .replace(/from "(\.\/[^\"]+)";/g, (_match, relative) => `from ${JSON.stringify(new URL(`../web/${relative.slice(2)}`, import.meta.url).href)};`);
await import(`data:text/javascript;base64,${Buffer.from(source + "\n//# sourceURL=soda-storyboard-extension.js").toString("base64")}`);
extension.setup();

async function nodeType(type, values) {
    class Node {
        constructor() {
            this.widgets = Object.entries(values).map(([name, value]) => ({ name, value, options: {},
                type: ["filename", "dialogue_mode", "slant_mode"].includes(name) ? "combo" : typeof value === "boolean" ? "toggle" : typeof value === "number" ? "number" : "text",
                computeSize: () => [100, 20] }));
            this.size = [200, 100]; this.dom = new Map(); this.inputs = [];
        }
        addDOMWidget(name, type, element, options) {
            assert.equal(options.serialize, false); this.dom.set(name, element);
            const item = { name, type, element, options, value: null, serialize: false }; this.widgets.push(item); return item;
        }
        addWidget(type, name, value, callback, options) {
            const item = { type, name, value, callback, options }; this.widgets.push(item); return item;
        }
        setDirtyCanvas() {}
        setSize(size) { this.size = size; }
    }
    await extension.beforeRegisterNodeDef(Node, { name: type });
    return Node;
}
const field = (node, name) => node.widgets.find(w => w.name === name);
const create = Type => { const node = new Type(); node.onNodeCreated(); graph.add(node); return node; };
const findElement = (root, predicate) => predicate(root) ? root : root.children.map(child => findElement(child, predicate)).find(Boolean);
const uiButton = (node, label) => findElement(node._sodaView.root, element => element.tag === "button" && element.textContent === label);
ImportNode = await nodeType("SodaLoadStoryboard", { filename: "上传或拖入 .storyboard.json",
    dialogue_mode: "跟随页面", slant_mode: "cut", include_triggers: true, width: 1024, height: 1536 });
async function settle() { await nextTurn(); await nextTurn(); }

test("sidebar still opens/stops the editor", async () => {
    const container = new Element("section"); sidebar.render(container);
    const controls = container.children[0];
    controls.children[0].value = "project"; controls.children[1].value = "p1";
    await controls.children[2].onclick();
    assert.equal(container.children[1].tag, "iframe");
    assert.equal(container.children[1].src, "http://127.0.0.1:8780/#page=p1");
    await container.children[0].children[3].onclick();
    assert(!container.children.some(child => child.tag === "iframe"));
});

test("empty workflow restores show one inline error and never toast or inspect", async () => {
    const node = create(ImportNode); const count = toasts.length; const requests = calls.length;
    node.onConfigure(); node.onConfigure(); node.onConfigure(); await settle();
    assert.equal(node._sodaView.status.textContent, "请先导入分镜包");
    assert.equal(node._sodaView.status.dataset.error, "true");
    assert.equal(toasts.length, count);
    assert(calls.slice(requests).every(call => !call.path?.includes("inspect?")));
    node.onRemoved(); assert(!timers.has(node._sodaTimer));
});

test("drop creates unified nodes for bundles, bare pages and MOSS without swallowing workflows", async () => {
    for (const [name, value] of [
        ["p.storyboard.json", { format: "soda-storyboard-bundle-v1", page: {} }],
        ["p.json", { panels: [] }], ["p.moss.json", { summary: {}, items: [] }],
    ]) {
        const before = graph._nodes.length;
        const file = new File([JSON.stringify(value)], name, { type: "application/json" });
        canvas.listeners.drop({ dataTransfer: { files: [file] }, preventDefault() {}, stopImmediatePropagation() {} });
        await settle();
        assert.equal(graph._nodes.length, before + 1);
        const node = graph._nodes.at(-1);
        assert.deepEqual(node.pos, [250, 350]); assert.equal(field(node, "filename").value, name);
        assert.equal(node._sodaView.draft.hidden, false); assert(node._sodaView.draft.src.startsWith("data:image/png;base64,"));
        assert.deepEqual(JSON.parse(node._sodaView.prompt.value), JSON.parse(node._sodaMeta.moss_json));
        assert.equal(node._sodaView.prompt.readOnly, true);
    }
    await app.handleFile(new File([JSON.stringify({ nodes: [], links: [] })], "workflow.json"));
    assert(calls.some(call => call.workflowFile === "workflow.json"));
});

test("polling editor saves updates both draft and final JSON before execution", async () => {
    const node = graph._nodes.find(n => field(n, "filename")?.value === "p.storyboard.json");
    const before = node._sodaView.draft.src;
    revision = "saved-revision"; node._sodaTimer.fn(); await settle();
    assert.notEqual(node._sodaView.draft.src, before);
    assert.equal(JSON.parse(node._sodaView.prompt.value).summary.caption, "saved-revision");
    assert.equal(node._sodaView.prompt.value, node._sodaMeta.moss_json);
    await node._sodaView.toggle.onclick();
    assert(node._sodaView.prompt.value.includes("\n"));
    assert.deepEqual(JSON.parse(node._sodaView.prompt.value), JSON.parse(node._sodaMeta.moss_json));
    await node._sodaView.toggle.onclick();
    assert(!node._sodaView.prompt.value.includes("\n"));
    assert.equal(node._sodaView.prompt.value, node._sodaMeta.moss_json);
    await node._sodaView.copy.onclick();
    assert(calls.some(call => call.clipboard === node._sodaView.prompt.value));
    node._sodaView.root.clientHeight = 1100;
    node.onResize([900, 1100]);
    assert.equal(node._sodaView.root.dataset.compact, "false");
    assert.equal(node._sodaView.root.style.height, undefined, "frontend owns the fill-widget height");
    assert.equal(node._sodaView.domWidget.options.getHeight(), "100%");
    node._sodaView.root.clientHeight = 180;
    node.onResize([320, 320]);
    assert.equal(node._sodaView.root.dataset.compact, "true");
});

test("dropping on a template import node preserves that node and its connections", async () => {
    const node = create(ImportNode);
    const count = graph._nodes.length;
    const file = new File([JSON.stringify({ panels: [] })], "template-page.json");
    node._sodaView.root.listeners.drop({ dataTransfer: { files: [file] },
        preventDefault() {}, stopImmediatePropagation() {} });
    await settle();
    assert.equal(graph._nodes.length, count);
    assert.equal(field(node, "filename").value, "template-page.json");
    assert.equal(node._sodaView.draft.hidden, false);
});

test("linked project is remembered, selected via combos and lists pages automatically", async () => {
    const Type = await nodeType("SodaLoadStoryboardPage", { project_dir: "", page_id: "",
        dialogue_mode: "跟随页面", slant_mode: "cut", include_triggers: true });
    const node = create(Type);
    const picker = node.dom.get("soda_project_picker"); picker.children[0].value = "project & directory";
    await picker.children[1].onclick(); await settle();
    assert(calls.some(call => call.path === "/soda_storyboard/pages?project_dir=project+%26+directory"));
    assert.equal(field(node, "project_dir").type, "combo");
    assert.deepEqual(field(node, "page_id").options.values, ["p1"]);
    assert.equal(field(node, "page_id").value, "p1");
    assert.equal(node._sodaView.draft.hidden, false);
    const second = create(Type);
    assert(field(second, "project_dir").options.values.includes("project & directory"));
});

test("panel and character dropdowns come from page_info and track the selected panel", async () => {
    const Type = await nodeType("SodaCharacterMask", { panel: "1", character_id: "", page_info: metadata("p").page_info });
    const node = create(Type); await node._sodaRefreshChoices();
    assert.deepEqual(field(node, "panel").options.values, ["right", "left"]);
    assert.equal(field(node, "panel").value, "right");
    assert.deepEqual(field(node, "character_id").options.values, ["a"]);
    field(node, "panel").value = "left"; field(node, "panel").callback(); await settle();
    assert.deepEqual(field(node, "character_id").options.values, ["a", "b"]);
    const source = graph._nodes.find(n => n._sodaMeta);
    node.inputs = [{ name: "page_info", link: 42 }]; graph.links[42] = { origin_id: source.id };
    node.onConnectionsChange(); await settle();
    assert.deepEqual(field(node, "panel").options.values, ["right", "left"]);
});

test("MOSS editor action asks about approximate conversion and export creates a new selection", async () => {
    const node = graph._nodes.find(n => field(n, "filename")?.value === "p.moss.json");
    assert.equal(node._sodaView.edit.title, "转换为分镜单后编辑（近似转换）");
    const before = calls.filter(call => call.path === "/soda_storyboard/import/edit").length;
    globalThis.confirm = () => false;
    await node._sodaView.edit.onclick();
    assert.equal(calls.filter(call => call.path === "/soda_storyboard/import/edit").length, before);
    let confirmed = false; globalThis.confirm = () => { confirmed = true; return true; };
    await node._sodaView.edit.onclick();
    assert(confirmed);
    assert(calls.some(call => call.path === "/soda_storyboard/import/edit" && JSON.parse(call.options.body).convert_moss));
    node._sodaMeta.kind = "page";
    await uiButton(node, "另存为新分镜包").onclick(); await settle();
    assert.equal(field(node, "filename").value, "saved.storyboard.json");
    assert(calls.some(call => call.download === "saved.storyboard.json"));
});

test("native widgets retain serialized input order and values while advanced controls toggle", async () => {
    const node = create(ImportNode);
    const inputNames = ["filename", "dialogue_mode", "slant_mode", "include_triggers", "width", "height"];
    const serialized = () => node.widgets.filter(item => item.options?.serialize !== false && item.serialize !== false)
        .map(item => [item.name, item.value]);
    const original = serialized();
    assert.deepEqual(original.map(([name]) => name), inputNames);
    assert.deepEqual(node.size, [420, 720]);
    assert(node._sodaView.domWidget.options.getMinHeight() > 0);
    assert(node._sodaView.domWidget.options.getMinHeight() < node.size[1]);
    assert(inputNames.every(name => field(node, name).hidden));
    await node._sodaView.advancedButton.onclick();
    assert.equal(node._sodaView.advancedButton.attributes["aria-expanded"], "true");
    for (const name of ["dialogue_mode", "slant_mode", "include_triggers"]) {
        assert.equal(field(node, name).hidden, false);
        assert.notEqual(field(node, name).type, "hidden");
        assert.deepEqual(field(node, name).computeSize(), [100, 20]);
    }
    assert.equal(field(node, "width").hidden, true);
    assert.equal(field(node, "height").hidden, true);
    node.onExecuted({ soda: [metadata("advanced.moss.json")] });
    assert.equal(field(node, "width").hidden, false);
    assert.equal(field(node, "height").hidden, false);
    node._sodaMeta = null;
    node._sodaView.render(null);
    assert.equal(field(node, "width").hidden, false, "same-file refresh retains MOSS dimensions during a numeric drag");
    await node._sodaRefreshFiles();
    assert.equal(field(node, "filename").type, "hidden", "file-list refresh must not reveal the legacy filename widget");
    await node._sodaView.advancedButton.onclick();
    assert(inputNames.every(name => field(node, name).hidden));
    assert.deepEqual(serialized(), original, "visibility never removes, reorders, or overwrites native inputs");
    assert.equal(node.widgets.filter(item => item.name === "soda_preview").length, 1);
    node.onRemoved();
});

test("linked and draft nodes share the preview component and upstream parsed metadata", async () => {
    const Type = await nodeType("SodaStoryboardPreview", { project_dir: "", page_id: "", page_info: "" });
    const node = create(Type);
    const source = graph._nodes.find(candidate => candidate._sodaMeta?.kind === "page");
    node.inputs = [{ name: "page_info", link: 77 }];
    graph.links[77] = { origin_id: source.id };
    node.onConnectionsChange(); await settle();
    assert.equal(node._sodaMeta, source._sodaMeta);
    assert.equal(node._sodaView.root.className, source._sodaView.root.className);
    assert.equal(node._sodaView.draft.src, source._sodaView.draft.src);
    assert.equal(node._sodaView.prompt.value, source._sodaMeta.moss_json);
    assert.equal(node._sodaView.prompt.readOnly, true);
    assert.equal(node._sodaView.select.hidden, true);
    assert.equal(node._sodaView.advancedButton.hidden, true);
    assert.deepEqual(node.size, [420, 720]);
    assert.equal(node._sodaView.domWidget.options.getHeight(), source._sodaView.domWidget.options.getHeight());
    node.onRemoved();
});

test("draft edit delegates to its source and clears the preview when upstream becomes unavailable", async () => {
    const source = create(ImportNode);
    source.onExecuted({ soda: [metadata("source.json")] });
    let edits = 0;
    source._sodaEdit = async () => { edits++; };
    const Type = await nodeType("SodaStoryboardPreview", { project_dir: "", page_id: "", page_info: "" });
    const node = create(Type);
    node.inputs = [{ name: "page_info", link: 88 }]; graph.links[88] = { origin_id: source.id };
    node.onConnectionsChange(); await settle();
    await node._sodaView.edit.onclick();
    assert.equal(edits, 1, "edit must use the actual source, even with blank draft project inputs");
    field(source, "filename").value = "上传或拖入 .storyboard.json";
    field(source, "filename").callback(); await settle();
    await node._sodaRefresh();
    assert.equal(node._sodaMeta, null);
    assert.equal(node._sodaView.draft.hidden, true);
    assert.equal(node._sodaView.prompt.value, "");
    assert.equal(node._sodaView.edit.disabled, true);
    assert.match(node._sodaView.status.textContent, /上游/);
    node.onRemoved(); source.onRemoved();
});

test("literal page_info previews survive polling and only edit an explicitly supplied project", async () => {
    const snapshot = metadata("snapshot.json");
    const Type = await nodeType("SodaStoryboardPreview", { project_dir: "", page_id: "", page_info: snapshot.page_info });
    const node = create(Type);
    node.onExecuted({ soda: [snapshot] });
    const requestCount = calls.length;
    node._sodaTimer.fn(); await settle();
    node.onConnectionsChange(); await settle();
    assert.equal(node._sodaMeta, snapshot);
    assert.equal(node._sodaView.draft.hidden, false);
    assert(calls.slice(requestCount).every(call => !call.path?.includes("/link?")));
    const before = calls.filter(call => call.path === "/soda_storyboard/editor/start").length;
    await node._sodaView.edit.onclick();
    assert.equal(calls.filter(call => call.path === "/soda_storyboard/editor/start").length, before);
    assert.match(toasts.at(-1).detail, /快照/);
    field(node, "project_dir").value = "chosen-project";
    field(node, "page_id").value = "chosen-page";
    await node._sodaView.edit.onclick();
    assert(calls.some(call => call.path === "/soda_storyboard/editor/start" &&
        JSON.parse(call.options.body).project_dir === "chosen-project" && JSON.parse(call.options.body).page_id === "chosen-page"));
    node.onRemoved();
});

test("a pending source preview cannot reappear after its connection is removed", async () => {
    const source = create(ImportNode);
    let resolveSource;
    source._sodaRefresh = () => new Promise(resolve => { resolveSource = resolve; });
    const Type = await nodeType("SodaStoryboardPreview", { project_dir: "", page_id: "", page_info: "" });
    const node = create(Type);
    node.inputs = [{ name: "page_info", link: 89 }]; graph.links[89] = { origin_id: source.id };
    const pending = node._sodaRefresh();
    node.inputs[0].link = null;
    node.onConnectionsChange();
    resolveSource(metadata("outdated.json"));
    await pending; await settle();
    assert.equal(node._sodaMeta, null);
    assert.equal(node._sodaView.draft.hidden, true);
    node.onRemoved(); source.onRemoved();
});

test("single-canvas MOSS shares item groups, legend and hover boxes across node and viewer", async () => {
    const node = create(ImportNode);
    const items = [
        { id: "object", label: "object", index: 1, caption: "台灯", shape: { x: 200, y: 20, w: 60, h: 100 } },
        { id: "character", label: "character", index: 2, caption: "抱书的旅人", shape: { x: 80, y: 30, w: 100, h: 180 } },
        { id: "text", label: "text", index: 3, text: "欢迎光临", caption: "English placeholder", shape: { x: 20, y: 20, w: 60, h: 180 } },
    ];
    node.onExecuted({ soda: [{ ...metadata("external.moss.json"), items, panels: [], panel_count: 0,
        moss_layout: { items, panels: [], single_canvas: true }, dimensions_inferred: true }] });
    assert(uiButton(node, "条目"));
    const list = findElement(node._sodaView.root, element => element.className === "soda-panel-list");
    assert.deepEqual(list.children.filter(element => element.className === "soda-entry-group").map(element => element.textContent),
        ["文字", "角色", "物件"]);
    assert.equal(findElement(node._sodaView.root, element => element.className === "soda-image-legend").children.length, 3);
    assert(findElement(list, element => element.textContent === "文字：欢迎光临"));
    assert(!findElement(list, element => element.textContent === "English placeholder"));
    await uiButton(node, "⛶ 查看").onclick();
    const viewer = node._sodaView.viewer.element;
    assert.equal(findElement(viewer, element => element.className === "soda-sv-tab").textContent, "条目");
    findElement(viewer, element => element.className === "soda-sv-entry").fire("pointerenter");
    assert.equal(findElement(viewer, element => element.tag === "polygon").classList.contains("soda-sv-active"), true);
    node.onRemoved();
});

test("large viewer opens current metadata, closes with Escape, and refreshes on next opening", async () => {
    const node = create(ImportNode);
    node.onExecuted({ soda: [{ ...metadata("viewer.json"), title: "第一张", draft_png_base64: "FIRST" }] });
    await uiButton(node, "⛶ 查看").onclick(); await settle();
    const first = node._sodaView.viewer;
    assert.equal(first.element.parentNode, document.body);
    assert.equal(findElement(first.element, element => element.className === "soda-sv-title").textContent, "第一张");
    assert.equal(findElement(first.element, element => element.tag === "img").src, "data:image/png;base64,FIRST");
    document.fire("keydown", { key: "Escape" });
    assert.equal(first.element.parentNode, null);
    node.onExecuted({ soda: [{ ...metadata("viewer-next.json"), title: "第二张", draft_png_base64: "SECOND" }] });
    node._sodaView.draft.ondblclick(); await settle();
    const second = node._sodaView.viewer;
    assert.notEqual(second, first);
    assert.equal(findElement(second.element, element => element.className === "soda-sv-title").textContent, "第二张");
    assert.equal(findElement(second.element, element => element.tag === "img").src, "data:image/png;base64,SECOND");
    node.onRemoved();
    assert.equal(second.element.parentNode, null);
});

test("automatic failures stay inline, explicit duplicate upload errors only toast once", async () => {
    failed = true; const node = create(ImportNode);
    field(node, "filename").value = "bad.json";
    const count = toasts.length;
    await node._sodaRefresh(); await node._sodaRefresh(); await node._sodaRefresh();
    assert.equal(toasts.length, count); assert.equal(node._sodaView.status.textContent, "文件已损坏");
    node._sodaUploadInput.files = [new File(["broken"], "bad.json")];
    await node._sodaUploadInput.onchange(); await node._sodaUploadInput.onchange();
    assert.equal(toasts.length, count + 1);
    failed = false;
});
