// Shared, DOM-free data and geometry for the node preview and large viewer.
const object = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const list = value => Array.isArray(value) ? value : [];
const text = value => value == null ? "" : String(value);
const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const positive = (value, fallback = 1) => finite(value) > 0 ? Number(value) : fallback;

function parsed(value) {
    if (typeof value !== "string") return object(value);
    try { return object(JSON.parse(value)); } catch { return {}; }
}

function pageData(metadata) {
    const info = parsed(metadata.page_info);
    return { page: object(metadata.page || info.page), characters: object(info.characters) };
}

/** Restore the JSON filename from store_upload's <original stem>-<16 hex>.<type>.json. */
export function displayFilename(filename = "") {
    return text(filename).split(/[\\/]/).pop()
        .replace(/-([a-f0-9]{16})\.(?:storyboard|moss)\.json$/i, ".json");
}

export function pageTitle(metadata = {}, filename = "") {
    const { page } = pageData(metadata);
    if (metadata.kind !== "moss" && metadata.source_kind !== "moss") {
        const title = [metadata.title, page.title, metadata.page_id, page.id, page.page_id]
            .map(text).find(value => value.trim());
        if (title) return title.trim();
    }
    const original = metadata.original_filename ? text(metadata.original_filename).split(/[\\/]/).pop() :
        displayFilename(metadata.filename || filename);
    return original
        .replace(/(?:\.(?:storyboard|moss))?\.json$/i, "") || "未选择分镜";
}

export function shotLabel(shot) {
    return ({ extreme_long: "大远景", long: "远景", full: "全景", medium: "中景",
        close_up: "特写", extreme_close_up: "大特写", close: "近景", wide: "远景" })[shot] || text(shot);
}

function characterName(id, metadata, characters) {
    const card = object(characters[id]);
    return text(metadata.character_names?.[id] || card.display_name || card.name || id);
}

/** Convert a rect or quad into canvas-coordinate points, without changing source data. */
export function shapePolygon(shape) {
    if (!shape || typeof shape !== "object") return null;
    if (shape.type === "quad" || Array.isArray(shape.points)) {
        const points = list(shape.points);
        return points.length === 4 && points.every(point => Array.isArray(point) && point.length >= 2 &&
            point.slice(0, 2).every(value => Number.isFinite(Number(value)))) ?
            points.map(point => point.slice(0, 2).map(Number)) : null;
    }
    if (![shape.x, shape.y, shape.w, shape.h].every(value => value != null && Number.isFinite(Number(value))) ||
        Number(shape.w) <= 0 || Number(shape.h) <= 0) return null;
    const [x, y, w, h] = [shape.x, shape.y, shape.w, shape.h].map(Number);
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
}

function spatialCompare(a, b, direction) {
    const pa = shapePolygon(a.shape || a.bbox);
    const pb = shapePolygon(b.shape || b.bbox);
    if (!pa || !pb) return 0;
    const top = Math.min(...pa.map(point => point[1])) - Math.min(...pb.map(point => point[1]));
    if (top) return top;
    const horizontal = Math.min(...pa.map(point => point[0])) - Math.min(...pb.map(point => point[0]));
    return direction === "ltr" ? horizontal : -horizontal;
}

function ordered(values, direction) {
    return [...values].sort((a, b) => {
        if (a.order != null && b.order != null && Number.isFinite(Number(a.order)) && Number.isFinite(Number(b.order))) {
            const difference = Number(a.order) - Number(b.order);
            if (difference) return difference;
        }
        return spatialCompare(a, b, direction);
    });
}

function normalizeText(value, fallbackId, metadata, characters) {
    const entry = typeof value === "string" ? { text: value } : object(value);
    const speakerId = text(entry.speaker_id || entry.speaker || "");
    return {
        id: text(entry.id || fallbackId),
        kind: text(entry.kind || (entry.bubble === "narration" ? "narration" : "dialogue")),
        text: text(entry.text),
        speakerId,
        speaker: speakerId ? characterName(speakerId, metadata, characters) : "",
    };
}

function pageTexts(metadata, page, panels) {
    // New metadata already includes adapted legacy dialogue and sfx.
    if (Array.isArray(metadata.texts)) return metadata.texts;
    const result = [...list(page.texts)];
    const ids = new Set(result.map(entry => entry.id));
    for (const panel of panels) {
        for (const [index, dialogue] of list(panel.dialogue).entries()) {
            const id = `${panel.id}-dialogue-${index + 1}`;
            if (!ids.has(id)) result.push({ ...object(dialogue), id, panel_id: panel.id });
        }
        for (const [index, value] of list(panel.sfx).entries()) {
            const id = `${panel.id}-sfx-${index + 1}`;
            if (!ids.has(id)) result.push({ id, text: text(value), panel_id: panel.id, kind: "sfx" });
        }
    }
    return result;
}

const MOSS_TYPES = { text: "文字", character: "角色", object: "物件", panel: "物件" };
const MOSS_ORDER = { text: 0, character: 1, object: 2, panel: 2 };

function mossPolygon(item, metadata, moss) {
    if (item.shape) return shapePolygon(item.shape);
    if (!Array.isArray(item.bbox) || item.bbox.length !== 4 || !item.bbox.every(value => Number.isFinite(Number(value)))) return null;
    const [a, b, c, d] = item.bbox.map(Number);
    let [x, y, right, bottom] = moss.bbox_format === "xyxy" ? [a, b, c, d] : [b, a, d, c];
    const width = positive(metadata.width), height = positive(metadata.height);
    const space = moss.bbox_coord_space || "abs_centralized";
    if (space === "abs_centralized") { x += Math.floor(width / 2); right += Math.floor(width / 2); y += Math.floor(height / 2); bottom += Math.floor(height / 2); }
    else if (space === "normalized") { x *= width; right *= width; y *= height; bottom *= height; }
    x = Math.max(0, x); y = Math.max(0, y); right = Math.min(width, right); bottom = Math.min(height, bottom);
    return shapePolygon({ x, y, w: right - x, h: bottom - y });
}

function mossEntries(metadata) {
    const moss = parsed(metadata.moss_json);
    const layout = object(metadata.moss_layout);
    const items = list(layout.items || metadata.items || moss.items).map((value, index) => {
        const item = object(value), id = text(item.id || `item-${index + 1}`), label = text(item.label || "object");
        const content = text(item.text) || (label === "text" ? text(item.caption).slice(0, 12) : "");
        return { id, number: item.index || index + 1, kind: "item", itemType: label, group: label,
            groupLabel: MOSS_TYPES[label] || "物件", shot: "", characters: [],
            description: label === "text" ? "" : text(item.caption), polygon: mossPolygon(item, metadata, moss),
            texts: content ? [normalizeText({ ...item, id: `${id}-text`, text: content, kind: "文字" }, `${id}-text`, metadata, {})] : [] };
    });
    const panels = list(layout.panels || metadata.panels).filter(panel => panel.shape && Array.isArray(panel.item_ids));
    const used = new Set(panels.flatMap(panel => [panel.item_id, ...panel.item_ids]));
    const entries = ordered(panels, "rtl").map((panel, index) => {
        const children = items.filter(item => item.id !== panel.item_id && panel.item_ids.includes(item.id));
        return { id: panel.id, number: index + 1, kind: "panel", group: "panels", groupLabel: "", shot: "",
            characters: children.filter(item => item.itemType === "character").map(item => ({ id: item.id, name: item.description.slice(0, 24) })),
            description: [text(panel.description), ...children.filter(item => item.description).map(item => `${item.groupLabel}：${item.description}`)].filter(Boolean).join("\n"),
            texts: children.flatMap(item => item.texts), polygon: shapePolygon(panel.shape) };
    });
    const unassigned = items.filter(item => !used.has(item.id)).sort((a, b) => (MOSS_ORDER[a.itemType] ?? 2) - (MOSS_ORDER[b.itemType] ?? 2));
    entries.push(...unassigned.map(item => ({ ...item, groupLabel: `${panels.length ? "其他条目 · " : ""}${item.groupLabel}` })));
    return entries;
}

/** One shared list for node/viewer, with actual MOSS geometry and text-first item groups. */
export function panelEntries(metadata = {}) {
    const { page, characters } = pageData(metadata);
    if (metadata.kind === "moss" || metadata.source_kind === "moss") return mossEntries(metadata);
    const sourcePanels = Array.isArray(metadata.panels) && metadata.panels.every(panel => panel.shape) ?
        metadata.panels : list(page.panels);
    const direction = metadata.reading_direction || page.reading_direction || "rtl";
    const panels = ordered(sourcePanels, direction);
    const texts = pageTexts(metadata, page, panels);
    const panelIds = new Set(panels.map(panel => panel.id));
    const entries = panels.map((panel, index) => {
        const associated = ordered(texts.filter(entry => entry.panel_id === panel.id), direction)
            .map((entry, i) => normalizeText(entry, `${panel.id}-text-${i + 1}`, metadata, characters))
            .filter(entry => entry.text.trim());
        const ids = [...new Set([...list(panel.character_ids), ...list(panel.figures).map(figure => figure.character_id),
            ...list(page.overlays).filter(overlay => overlay.panel_id === panel.id).map(overlay => overlay.character_id),
            ...associated.map(entry => entry.speakerId)].filter(Boolean))];
        return { id: text(panel.id || `panel-${index + 1}`), number: index + 1, kind: "panel",
            shot: shotLabel(panel.shot), characters: ids.map(id => ({ id, name: characterName(id, metadata, characters) })),
            description: text(panel.description || panel.caption_en), texts: associated, polygon: shapePolygon(panel.shape) };
    });
    // Keep page-level narration visible even when it is not owned by a panel.
    const unassigned = texts.filter(entry => !panelIds.has(entry.panel_id))
        .map((entry, index) => normalizeText(entry, `page-text-${index + 1}`, metadata, characters))
        .filter(entry => entry.text.trim());
    if (unassigned.length) entries.push({ id: "page-texts", number: null, kind: "text", shot: "",
        characters: [], description: "页上文字", texts: unassigned, polygon: null });
    return entries;
}

export function informationTags(metadata = {}) {
    const { page, characters } = pageData(metadata);
    const width = finite(metadata.width || page.canvas_width);
    const height = finite(metadata.height || page.canvas_height);
    const entries = panelEntries(metadata);
    const sourceKind = metadata.source_kind || metadata.kind || "page";
    const panelCount = sourceKind === "moss" ? entries.filter(entry => entry.kind === "panel").length :
        metadata.panel_count ?? entries.filter(entry => entry.kind === "panel").length;
    const dialogueCount = metadata.dialogue_count ?? entries.reduce((sum, entry) => sum +
        entry.texts.filter(value => value.kind === "dialogue").length, 0);
    const tags = [];
    if (width > 0 && height > 0) tags.push({ id: "canvas", label: `${width}×${height}` });
    if (sourceKind === "moss") {
        const items = list(metadata.items || metadata.moss_layout?.items || parsed(metadata.moss_json).items);
        const count = metadata.text_count ?? items.filter(item => item.label === "text").length;
        tags.push({ id: "items", label: `${items.length} 个条目` });
        tags.push({ id: "text-items", label: `${count} 个文字条目` });
        tags.push({ id: "panels", label: panelCount ? `${panelCount} 格` : "单画布" });
        if (metadata.dimensions_inferred) tags.push({ id: "inferred", label: "尺寸推断" });
    } else {
        tags.push({ id: "panels", label: `${panelCount} 格` });
        tags.push({ id: "dialogue", label: `${dialogueCount} 句台词` });
        const status = object(metadata.translation_status);
        const label = ({ fresh: "新鲜", stale: "过期", missing: "缺失" })[status.state];
        if (label) {
            const states = Object.values(object(status.panels));
            const missing = states.filter(state => state === "missing").length;
            const stale = states.filter(state => state === "stale").length;
            tags.push({ id: "translation", label: `英文译文：${label}${missing && stale ? `（${stale} 格过期、${missing} 格缺失）` : ""}` });
        }
    }
    const lora = object(metadata.lora);
    if (text(lora.path).trim()) {
        const name = lora.display_name || characterName(lora.character_id || "", metadata, characters) ||
            displayFilename(lora.path).replace(/\.[^.]+$/, "");
        tags.push({ id: "lora", label: `建议 LoRA：${name} ${finite(lora.strength, 1)}` });
    }
    tags.push({ id: "kind", label: ({ bundle: "分镜包", page: "分镜单", moss: "MOSS JSON" })[sourceKind] || "分镜单" });
    return tags;
}

/** Visibility only: callers retain native widgets and their serialization values. */
export function widgetVisibility({ kind = "page", source_kind, advanced = false } = {}) {
    const open = Boolean(advanced);
    const moss = (source_kind || kind) === "moss";
    return { filename: false, dialogue_mode: open, slant_mode: open,
        include_triggers: open, width: open && moss, height: open && moss };
}

export function buildStoryboardModel(metadata = {}, filename = "") {
    const { page } = pageData(metadata);
    return { title: pageTitle(metadata, filename), filename: metadata.original_filename || displayFilename(metadata.filename || filename),
        width: positive(metadata.width || page.canvas_width), height: positive(metadata.height || page.canvas_height),
        tags: informationTags(metadata), warnings: list(metadata.warnings).map(text), entries: panelEntries(metadata),
        prompt: typeof metadata.moss_json === "string" ? metadata.moss_json : JSON.stringify(metadata.moss_json || {}),
        image: metadata.draft_png_base64 ? `data:image/png;base64,${metadata.draft_png_base64}` : "",
        detailsLabel: (metadata.kind === "moss" || metadata.source_kind === "moss") && !panelEntries(metadata).some(entry => entry.kind === "panel") ? "条目" : "逐格",
        legend: (metadata.kind === "moss" || metadata.source_kind === "moss") ? list(metadata.legend).length ? metadata.legend :
            [{label:"物件",color:"#2d805a"},{label:"角色",color:"#2563a6"},{label:"文字",color:"#b34922"}] : [],
        kind: metadata.source_kind || metadata.kind || "page" };
}

/** Fit is independent of image raster size: all polygons remain in original canvas coordinates. */
export function viewerTransform({ width, height, viewportWidth, viewportHeight, zoom = 1, panX = 0, panY = 0, mode = "fit" } = {}) {
    width = positive(width); height = positive(height);
    viewportWidth = Math.max(0, finite(viewportWidth)); viewportHeight = Math.max(0, finite(viewportHeight));
    const base = mode === "actual" ? 1 : Math.min(viewportWidth / width, viewportHeight / height);
    const scale = base * positive(zoom);
    const displayedWidth = width * scale, displayedHeight = height * scale;
    return { scale, x: (viewportWidth - displayedWidth) / 2 + finite(panX),
        y: (viewportHeight - displayedHeight) / 2 + finite(panY), width: displayedWidth, height: displayedHeight };
}

export function transformPoint(point, transform) {
    return [transform.x + point[0] * transform.scale, transform.y + point[1] * transform.scale];
}

export function transformPolygon(points, transform) {
    return Array.isArray(points) ? points.map(point => transformPoint(point, transform)) : [];
}

/** Cursor-anchored zoom; pan is measured in viewport CSS pixels. */
export function zoomAt(options, nextZoom, anchor) {
    const before = viewerTransform(options);
    const zoom = Math.min(20, Math.max(0.1, finite(nextZoom, positive(options.zoom))));
    const after = viewerTransform({ ...options, zoom });
    if (!before.scale) return { ...options, zoom };
    const point = [(anchor[0] - before.x) / before.scale, (anchor[1] - before.y) / before.scale];
    return { ...options, zoom, panX: finite(options.panX) + anchor[0] - after.x - point[0] * after.scale,
        panY: finite(options.panY) + anchor[1] - after.y - point[1] * after.scale };
}
