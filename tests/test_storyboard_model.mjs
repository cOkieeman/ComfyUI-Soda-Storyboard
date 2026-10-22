import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

// The browser serves .js as ESM; importing the same source also supports Node without package.json.
const source = await readFile(new URL("../web/storyboard-model.js", import.meta.url), "utf8");
const { displayFilename, pageTitle, informationTags, panelEntries, widgetVisibility, shapePolygon, shotLabel,
    buildStoryboardModel, viewerTransform, transformPoint, transformPolygon, zoomAt } =
    await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

const page = {
    id: "library", title: "图书馆的胡子", canvas_width: 1000, canvas_height: 1500, reading_direction: "rtl",
    panels: [
        { id: "left", order: 2, shape: { type: "quad", points: [[0, 0], [450, 0], [470, 700], [0, 700]] },
            shot: "close", character_ids: ["sylvia"], description: "她发现了一根胡子。", sfx: ["咦"] },
        { id: "right", order: 1, shape: { type: "rect", x: 500, y: 0, w: 500, h: 700 }, shot: "medium",
            character_ids: ["sylvia"], figures: [{ character_id: "friend" }],
            dialogue: [{ speaker_id: "sylvia", text: "这里很安静。" }] },
    ],
    texts: [
        { id: "n1", panel_id: "left", text: "书页轻轻翻动。", kind: "narration" },
        { id: "t1", panel_id: "left", speaker_id: "friend", text: "怎么啦？", kind: "dialogue" },
        { id: "free", text: "午后。", kind: "narration" },
    ],
};
const characters = { sylvia: { display_name: "Sylvia" }, friend: { display_name: "小蓝" } };
const metadata = { width: 1000, height: 1500, kind: "page", source_kind: "bundle",
    page_info: JSON.stringify({ page, characters }), panel_count: 2, dialogue_count: 2,
    lora: { character_id: "sylvia", path: "cast\\sylvia.safetensors", strength: 0.8 },
    moss_json: '{"summary":{},"items":[]}', draft_png_base64: "PNG", warnings: ["多角色提醒"] };

test("upload display names restore the original extension without stripping natural hashes", () => {
    assert.equal(displayFilename("图书馆胡子.storyboard-aeb2b81a6d2fa7e8.storyboard.json"), "图书馆胡子.storyboard.json");
    assert.equal(displayFilename("p.moss-0123456789abcdef.storyboard.json"), "p.moss.json");
    assert.equal(displayFilename("p-0123456789abcdef.moss.json"), "p.json");
    assert.equal(displayFilename("scene-0123456789abcdef.json"), "scene-0123456789abcdef.json");
    assert.equal(displayFilename("folder\\nested.storyboard.json"), "nested.storyboard.json");
    assert.equal(displayFilename("folder/nested.moss.json"), "nested.moss.json");
});

test("page title prefers page title or id and MOSS uses its cleaned original filename", () => {
    assert.equal(pageTitle(metadata, "ignored.json"), "图书馆的胡子");
    assert.equal(pageTitle({ page_info: JSON.stringify({ page: { id: "page-2" } }) }), "page-2");
    assert.equal(pageTitle({ ...metadata, title: "显式标题" }), "显式标题");
    assert.equal(pageTitle({ kind: "moss", title: "imported", filename: "library.moss-aeb2b81a6d2fa7e8.storyboard.json" }), "library");
    assert.equal(pageTitle({ kind: "moss", original_filename: "原稿.moss.json" }), "原稿");
    assert.equal(pageTitle({ kind: "moss", original_filename: "原稿-0123456789abcdef.moss.json" }), "原稿-0123456789abcdef");
    assert.equal(buildStoryboardModel({ original_filename: "原稿-0123456789abcdef.moss.json" }).filename,
        "原稿-0123456789abcdef.moss.json");
    assert.equal(pageTitle({ title: "  ", page_id: "page-3" }), "page-3");
    assert.equal(pageTitle({ page_info: "bad json" }), "未选择分镜");
});

test("information tags contain readable character names, no paths, and omit absent LoRA", () => {
    assert.deepEqual(informationTags(metadata), [
        { id: "canvas", label: "1000×1500" }, { id: "panels", label: "2 格" },
        { id: "dialogue", label: "2 句台词" }, { id: "lora", label: "建议 LoRA：Sylvia 0.8" },
        { id: "kind", label: "分镜包" },
    ]);
    for (const lora of [undefined, {}, { strength: 0 }, { path: "" }]) {
        assert(!informationTags({ ...metadata, lora }).some(tag => tag.id === "lora"));
    }
    assert.equal(informationTags({ ...metadata, lora: { path: "cast/Example.safetensors" } })
        .find(tag => tag.id === "lora").label, "建议 LoRA：Example 1");
    assert.equal(informationTags({ ...metadata, lora: { path: "a.safetensors", display_name: "Alice", strength: 0 } })
        .find(tag => tag.id === "lora").label, "建议 LoRA：Alice 0");
});

test("panel entries follow reading order, join characters and all supported text sources", () => {
    const entries = panelEntries(metadata);
    assert.deepEqual(entries.map(entry => entry.id), ["right", "left", "page-texts"]);
    assert.equal(entries[0].number, 1);
    assert.deepEqual(entries[0].characters, [{ id: "sylvia", name: "Sylvia" }, { id: "friend", name: "小蓝" }]);
    assert.deepEqual(entries[0].texts[0], { id: "right-dialogue-1", kind: "dialogue", text: "这里很安静。",
        speakerId: "sylvia", speaker: "Sylvia" });
    assert.deepEqual(entries[0].polygon, [[500, 0], [1000, 0], [1000, 700], [500, 700]]);
    assert.equal(entries[1].shot, "近景");
    assert.deepEqual(entries[1].texts.map(value => value.kind), ["narration", "dialogue", "sfx"]);
    assert.equal(entries[2].texts[0].text, "午后。");
    assert.equal(entries[2].polygon, null);
    assert.equal(entries[2].number, null);
    assert.deepEqual(page.panels.map(panel => panel.id), ["left", "right"], "source was not sorted in-place");
});

test("schema shot sizes use consistent Chinese labels and custom names remain readable", () => {
    assert.deepEqual(["extreme_long", "long", "full", "medium", "close_up", "extreme_close_up"].map(shotLabel),
        ["大远景", "远景", "全景", "中景", "特写", "大特写"]);
    assert.equal(shotLabel("双人近景"), "双人近景");
});

test("metadata's already resolved texts avoid duplicate legacy dialogue", () => {
    const entries = panelEntries({ ...metadata, panels: page.panels, texts: [
        { id: "right-dialogue-1", panel_id: "right", text: "这里很安静。", speaker_id: "sylvia" },
    ], character_names: { sylvia: "希尔薇娅" } });
    assert.equal(entries[0].texts.length, 1);
    assert.equal(entries[0].texts[0].speaker, "希尔薇娅");
});

test("panels without explicit order fall back to top-to-bottom and right-to-left coordinates", () => {
    const panels = page.panels.map(({ order, ...panel }) => panel);
    assert.deepEqual(panelEntries({ page: { ...page, panels } }).slice(0, 2).map(entry => entry.id), ["right", "left"]);
    assert.deepEqual(panelEntries({ page: { ...page, panels, reading_direction: "ltr" } }).slice(0, 2).map(entry => entry.id), ["left", "right"]);
});

test("MOSS lists original captions and text in item order and never invents highlights", () => {
    const items = [{ label: "object", caption: "A quiet library", bbox: [0, 0, 10, 10] },
        { label: "text", caption: "Vertical dialogue", text: "你好", speaker_id: "sylvia", bbox: [0, 0, 10, 10] }];
    const moss = { ...metadata, kind: "moss", source_kind: "moss", items, panels: [], moss_json: JSON.stringify({ summary: {}, items }) };
    const entries = panelEntries(moss);
    assert.equal(entries.length, 2);
    assert.equal(entries[0].description, "A quiet library");
    assert.equal(entries[1].texts[0].text, "你好");
    assert(entries.every(entry => entry.kind === "item" && entry.polygon === null));
    assert.equal(informationTags(moss).find(tag => tag.id === "panels").label, "2 个条目");
    assert.equal(panelEntries({ kind: "moss", moss_json: JSON.stringify({ items }) }).length, 2);
});

test("advanced visibility keeps native inputs hidden by default and dimensions exclusive to MOSS", () => {
    const closed = { filename: false, dialogue_mode: false, slant_mode: false, include_triggers: false, width: false, height: false };
    assert.deepEqual(widgetVisibility(), closed);
    assert.deepEqual(widgetVisibility({ kind: "moss" }), closed);
    assert.deepEqual(widgetVisibility({ kind: "page", advanced: true }), { ...closed, dialogue_mode: true, slant_mode: true, include_triggers: true });
    assert.deepEqual(widgetVisibility({ kind: "moss", advanced: true }), { ...closed, dialogue_mode: true, slant_mode: true, include_triggers: true, width: true, height: true });
});

test("rects and quads yield copied polygons and invalid geometry cannot produce highlights", () => {
    const shape = { type: "quad", points: [[0, 0], [100, 10], [90, 200], [0, 190]] };
    assert.deepEqual(shapePolygon(shape), shape.points);
    assert.notEqual(shapePolygon(shape)[0], shape.points[0]);
    assert.equal(shapePolygon({ type: "rect", x: 0, y: 0, w: 0, h: 20 }), null);
    assert.equal(shapePolygon({ type: "quad", points: [[0, 0], [1, 1], [2, 2], [Infinity, 3]] }), null);
});

test("viewer geometry maps canvas points through fit, centered zoom and CSS-pixel pan", () => {
    const options = { width: 1000, height: 1500, viewportWidth: 800, viewportHeight: 900 };
    const fit = viewerTransform(options);
    assert.deepEqual(fit, { scale: 0.6, x: 100, y: 0, width: 600, height: 900 });
    assert.deepEqual(transformPoint([500, 750], fit), [400, 450]);
    const transformed = viewerTransform({ ...options, zoom: 2, panX: 40, panY: -20 });
    assert.deepEqual(transformed, { scale: 1.2, x: -160, y: -470, width: 1200, height: 1800 });
    assert.deepEqual(transformPolygon([[500, 0], [1000, 0], [1000, 700], [500, 700]], transformed),
        [[440, -470], [1040, -470], [1040, 370], [440, 370]]);
    assert.equal(viewerTransform({ ...options, mode: "actual" }).scale, 1);
});

test("cursor zoom preserves the same canvas point including existing pan", () => {
    const options = { width: 1000, height: 1500, viewportWidth: 800, viewportHeight: 900, zoom: 1.4, panX: 35, panY: -18 };
    const anchor = [675, 213], before = viewerTransform(options);
    const point = [(anchor[0] - before.x) / before.scale, (anchor[1] - before.y) / before.scale];
    const updated = zoomAt(options, 2.3, anchor);
    const actual = transformPoint(point, viewerTransform(updated));
    assert(Math.abs(actual[0] - anchor[0]) < 1e-9);
    assert(Math.abs(actual[1] - anchor[1]) < 1e-9);
    assert.equal(zoomAt(options, 100, anchor).zoom, 20);
    assert.equal(zoomAt(options, 0.01, anchor).zoom, 0.1);
    assert.equal(zoomAt(options, 0, anchor).zoom, 0.1);
    assert.equal(zoomAt(options, -2, anchor).zoom, 0.1);
});

test("shared model exposes one consistent node/viewer document", () => {
    const model = buildStoryboardModel(metadata, "page.storyboard-aeb2b81a6d2fa7e8.storyboard.json");
    assert.equal(model.title, "图书馆的胡子");
    assert.equal(model.filename, "page.storyboard.json");
    assert.equal(model.image, "data:image/png;base64,PNG");
    assert.equal(model.prompt, metadata.moss_json);
    assert.deepEqual(model.tags, informationTags(metadata));
    assert.deepEqual(model.warnings, ["多角色提醒"]);
});
