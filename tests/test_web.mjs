import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { setImmediate as nextTurn } from "node:timers/promises";

class Element {
    constructor(tag) {
        Object.assign(this, { tag, children: [], value: "", style: {}, attributes: {}, listeners: {}, classList: { add() {} } });
    }
    append(...children) { this.children.push(...children); }
    add(child) { this.append(child); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    click() { this.clicked = true; if (this.tag === "a") calls.push({ download: this.download }); }
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
globalThis.document = { head: new Element("head"), hidden: false, createElement: tag => new Element(tag) };
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
    .replace('import { api } from "../../scripts/api.js";', "const { api } = globalThis.__sodaTest;");
await import(`data:text/javascript;base64,${Buffer.from(source + "\n//# sourceURL=soda-storyboard-extension.js").toString("base64")}`);
extension.setup();

async function nodeType(type, values) {
    class Node {
        constructor() {
            this.widgets = Object.entries(values).map(([name, value]) => ({ name, value, options: {} }));
            this.size = [200, 100]; this.dom = new Map(); this.inputs = [];
        }
        addDOMWidget(name, type, element, options) { assert.equal(options.serialize, false); this.dom.set(name, element); }
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
    assert.equal(node._sodaView.status.style.color, "#e65d68");
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
    await node._sodaView.root.children[2].children[1].onclick();
    assert(!node._sodaView.prompt.value.includes("\n"));
    await node._sodaView.root.children[2].children[0].onclick();
    assert(calls.some(call => call.clipboard === node._sodaView.prompt.value));
    node.onResize([800, 1200]); assert.equal(node._sodaView.root.style.height, "900px");
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
    assert.equal(node._sodaEditButton.name, "转换为分镜单后编辑");
    const before = calls.filter(call => call.path === "/soda_storyboard/import/edit").length;
    globalThis.confirm = () => false;
    await node._sodaEditButton.callback();
    assert.equal(calls.filter(call => call.path === "/soda_storyboard/import/edit").length, before);
    let confirmed = false; globalThis.confirm = () => { confirmed = true; return true; };
    await node._sodaEditButton.callback();
    assert(confirmed);
    assert(calls.some(call => call.path === "/soda_storyboard/import/edit" && JSON.parse(call.options.body).convert_moss));
    node._sodaMeta.kind = "page";
    await node.widgets.find(w => w.name === "另存为新分镜包").callback(); await settle();
    assert.equal(field(node, "filename").value, "saved.storyboard.json");
    assert(calls.some(call => call.download === "saved.storyboard.json"));
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
