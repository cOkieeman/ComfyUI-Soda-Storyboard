import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const TAB_ID = "soda-storyboard";
const state = { projectDir: "", pageId: "", url: "" };
let sidebar;

async function request(path, body) {
    const options = body === undefined ? {} : {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    };
    const response = await api.fetchApi(`/soda_storyboard/${path}`, options);
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
    return value;
}

function report(error) {
    app.extensionManager.toast.add({
        severity: "error", summary: "分镜", detail: String(error.message || error), life: 8000,
    });
}

function button(label, action) {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.onclick = async () => {
        element.disabled = true;
        try { await action(); } catch (error) { report(error); }
        finally { element.disabled = false; }
    };
    return element;
}

async function pages(projectDir) {
    return (await request(`pages?project_dir=${encodeURIComponent(projectDir)}`)).pages;
}

async function startEditor(projectDir, pageId) {
    const result = await request("editor/start", { project_dir: projectDir, page_id: pageId });
    // Accept only the loopback editor URL constructed by the backend.
    const url = new URL(result.url);
    if (url.protocol !== "http:" || url.hostname !== "127.0.0.1" || !url.port) {
        throw new Error("编辑器返回的地址无效");
    }
    Object.assign(state, { projectDir, pageId, url: result.url });
    if (sidebar) renderSidebar(sidebar);
    const tabs = app.extensionManager.sidebarTab;
    if (tabs) tabs.activeSidebarTabId = TAB_ID;
}

function renderSidebar(container) {
    sidebar = container;
    container.replaceChildren();
    container.classList.add("soda-storyboard-sidebar");
    const directory = document.createElement("input");
    directory.placeholder = "分镜项目目录（ComfyUI 所在电脑）";
    directory.value = state.projectDir;
    directory.setAttribute("aria-label", "分镜项目目录");
    const page = document.createElement("select");
    page.setAttribute("aria-label", "分镜页面");
    const current = new Option(state.pageId || "选择页面", state.pageId);
    page.add(current);
    directory.onchange = () => {
        state.projectDir = directory.value;
        state.pageId = "";
        page.replaceChildren(new Option("刷新页面列表", ""));
    };
    page.onchange = () => { state.pageId = page.value; };
    const controls = document.createElement("div");
    controls.className = "soda-storyboard-controls";
    controls.append(directory, page,
        button("刷新页面", async () => {
            const projectDir = directory.value;
            const list = await pages(projectDir);
            if (directory.value !== projectDir) return;
            page.replaceChildren(...list.map(p => new Option(`${p.id} ${p.description || ""}`, p.id)));
            if (list.some(p => p.id === state.pageId)) page.value = state.pageId;
            state.projectDir = projectDir;
            state.pageId = page.value;
        }),
        button("打开 / 复用编辑器", () => startEditor(directory.value, page.value)),
        button("停止本项目编辑器", async () => {
            const result = await request("editor/stop", { project_dir: directory.value });
            if (result.stopped && state.projectDir === directory.value) {
                state.url = "";
                renderSidebar(container);
            }
            app.extensionManager.toast.add({severity: "info", summary: "分镜", detail: result.message});
        }),
    );
    container.append(controls);
    if (state.url) {
        const frame = document.createElement("iframe");
        frame.title = "Soda Storyboard 分镜编辑器";
        frame.src = state.url;
        container.append(frame);
    } else {
        const hint = document.createElement("p");
        hint.textContent = "填写项目目录并打开编辑器。修改分镜后，下次运行节点会重新编译。";
        container.append(hint);
    }
}

app.registerExtension({
    name: "Soda.Storyboard",
    setup() {
        const css = document.createElement("style");
        css.textContent = `
            .soda-storyboard-sidebar { display:flex; flex-direction:column; height:100%; min-height:0; }
            .soda-storyboard-controls { display:flex; flex-wrap:wrap; gap:8px; padding:12px; }
            .soda-storyboard-controls input, .soda-storyboard-controls select { width:100%; padding:8px; }
            .soda-storyboard-controls button { padding:8px; cursor:pointer; }
            .soda-storyboard-sidebar iframe { flex:1; min-height:400px; width:100%; border:0; background:white; }
            .soda-storyboard-sidebar p { padding:12px; }
            .soda-page-picker { display:flex; gap:4px; width:100%; }
            .soda-page-picker select { min-width:0; flex:1; }
        `;
        document.head.append(css);
        app.extensionManager.registerSidebarTab({
            id: TAB_ID, title: "分镜", tooltip: "Soda Storyboard", icon: "pi pi-book",
            type: "custom", render: renderSidebar,
            destroy: () => { sidebar = undefined; },
        });
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!["SodaLoadStoryboardPage", "SodaStoryboardPreview"].includes(nodeData.name)) return;
        const original = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = original?.apply(this, arguments);
            const widget = name => this.widgets?.find(w => w.name === name);
            const picker = document.createElement("div");
            picker.className = "soda-page-picker";
            const select = document.createElement("select");
            select.setAttribute("aria-label", "选择分镜页面");
            select.append(new Option("刷新后选择页面", ""));
            select.onchange = () => {
                if (!select.value) return;
                const page = widget("page_id");
                page.value = select.value;
                page.callback?.(page.value);
                this.setDirtyCanvas(true, true);
            };
            picker.append(select, button("刷新页面", async () => {
                const projectDir = widget("project_dir").value;
                const list = await pages(projectDir);
                if (widget("project_dir").value !== projectDir) return;
                select.replaceChildren(...list.map(p => new Option(p.id, p.id)));
                select.value = widget("page_id").value;
            }));
            this.addDOMWidget("soda_page_picker", "soda-page-picker", picker, { serialize: false });
            this.addWidget("button", "在编辑器中打开", null, () => {
                startEditor(widget("project_dir").value, widget("page_id").value).catch(report);
            }, { serialize: false });
            this.setSize([Math.max(this.size[0], 360), this.computeSize()[1]]);
            return result;
        };
    },
});
