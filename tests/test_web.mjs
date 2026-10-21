import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

class Element {
    constructor(tag) {
        this.tag = tag;
        this.children = [];
        this.value = "";
        this.classList = { add() {} };
    }
    append(...children) { this.children.push(...children); }
    add(child) { this.append(child); }
    replaceChildren(...children) { this.children = children; }
    setAttribute() {}
}

let extension;
let tab;
const calls = [];
const app = {
    registerExtension(value) { extension = value; },
    extensionManager: {
        registerSidebarTab(value) { tab = value; },
        sidebarTab: {},
        toast: { add(value) { calls.push({ toast: value }); } },
    },
};
globalThis.__sodaTest = {
    app,
    api: { async fetchApi(path, options) {
        calls.push({ path, options });
        return { ok: true, async json() {
            if (path.includes("/pages?")) return { pages: [{ id: "p1", description: "Demo" }] };
            if (path.endsWith("/start")) return { url: "http://127.0.0.1:8780/#page=p1" };
            return { stopped: true, message: "stopped" };
        }};
    }},
};
globalThis.document = { head: new Element("head"), createElement: tag => new Element(tag) };
globalThis.Option = class extends Element {
    constructor(text, value) { super("option"); this.textContent = text; this.value = value; }
};
const source = (await readFile(new URL("../web/storyboard.js", import.meta.url), "utf8"))
    .replace('import { app } from "../../scripts/app.js";', "const { app } = globalThis.__sodaTest;")
    .replace('import { api } from "../../scripts/api.js";', "const { api } = globalThis.__sodaTest;");
await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

test("sidebar opens the editor and clears iframe on confirmed stop", async () => {
    extension.setup();
    assert.equal(tab.id, "soda-storyboard");
    const container = new Element("section");
    tab.render(container);
    let controls = container.children[0];
    controls.children[0].value = "project with spaces";
    controls.children[1].value = "p1";
    await controls.children[3].onclick();
    assert.equal(container.children[1].tag, "iframe");
    assert.equal(container.children[1].src, "http://127.0.0.1:8780/#page=p1");
    assert.equal(app.extensionManager.sidebarTab.activeSidebarTabId, tab.id);
    controls = container.children[0];
    await controls.children[4].onclick();
    assert.equal(container.children[1].tag, "p");
});

test("page picker uses encoded project paths and updates the node page widget", async () => {
    class Node {
        constructor() {
            this.widgets = [{ name: "project_dir", value: "project & directory" }, { name: "page_id", value: "p1" }];
            this.size = [200, 100];
        }
        addDOMWidget(name, type, element, options) { this.picker = element; assert.equal(options.serialize, false); }
        addWidget(type, title, value, callback, options) { this.open = callback; assert.equal(options.serialize, false); }
        setDirtyCanvas() {}
        setSize(size) { this.size = size; }
        computeSize() { return [200, 250]; }
    }
    await extension.beforeRegisterNodeDef(Node, { name: "SodaLoadStoryboardPage" });
    const node = new Node();
    node.onNodeCreated();
    await node.picker.children[1].onclick();
    assert(calls.some(c => c.path === "/soda_storyboard/pages?project_dir=project%20%26%20directory"));
    node.picker.children[0].value = "p1";
    node.picker.children[0].onchange();
    assert.equal(node.widgets[1].value, "p1");
    assert.equal(node.size[0], 360);
});
