// The sky's host against recording stand-ins for the view and the world: the order
// of its calls, which the view asks of a host and does not check for itself
// (a missing one draws an empty sky with no error). Run by tests/test_sky_host_js.py.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const source = readFileSync(join(ROOT, "sky_host.js"), "utf-8");
const words = JSON.parse(readFileSync(join(ROOT, "sky_words.json"), "utf-8"));

// What the host finds of the page around it.
let thePage = null;
function newPage() {
  const heard = [];
  thePage = {heard, found: {},
    querySelector(selector) { return thePage.found[selector] || null; },
    addEventListener(name, fn, capture) { heard.push({name, fn, capture}); },
    removeEventListener(name, fn, capture) { const at = heard.findIndex((h) => h.name === name && h.fn === fn && h.capture === capture); if (at >= 0) heard.splice(at, 1); }};
  return thePage;
}

function element(tag) {
  const classes = new Set();
  const el = {tag, children: [], style: {setProperty(name, value) { el.style[name] = value; }}, hidden: false, listeners: {}, className: "", parentNode: null, disabled: false, attributes: {}, clientWidth: 1000, clientHeight: 500, offsetHeight: 444, scrollTop: 0, get ownerDocument() { return thePage; },
    classList: {toggle(name, on) { if (on) classes.add(name); else classes.delete(name); }, contains: (name) => classes.has(name)},
    setAttribute(name, value) { el.attributes[name] = value; },
    removeAttribute(name) { delete el.attributes[name]; },
    appendChild(child) { child.parentNode = el; el.children.push(child); return child; },
    remove() { el.removed = true; },
    addEventListener(name, fn) { el.listeners[name] = fn; },
    removeEventListener(name) { delete el.listeners[name]; },
    querySelector() { return null; },
    getBoundingClientRect() { return {top: 300}; },
    getRootNode() { return {}; },
    isConnected: true};
  return el;
}

function harness(options = {}) {
  newPage();
  const calls = [], log = (name, result) => (...args) => { calls.push(name); return result === undefined ? {status: "ok"} : (typeof result === "function" ? result(...args) : result); };
  let controller = null, host = null, frameHook = null, selectHook = null;
  const queries = [];
  const world = {scene: {children: [], background: null}, equGroup: {children: [], matrixWorld: {}, updateMatrixWorld() {}}, eclGroup: {children: []},
    towerHost: {label: (words) => { calls.push(`label(${words})`); return {}; }}, PREF: {}, L: {}, cam: {theta: 1, phi: 1, r: 4, tth: 1, tph: 1, tr: 4},
    setLayers: log("world.setLayers"), setObserver: log("world.setObserver"), kick: log("world.kick"), placeCamera: log("world.placeCamera"),
    setColours: log("world.setColours"), dispose: log("world.dispose"), onFrame(_, fn) { frameHook = fn; },
    setController(c) { calls.push(c ? "world.setController" : "world.clearController"); controller = c; },
    renderer: {forceContextLoss: log("renderer.forceContextLoss"), ratio: 1, getPixelRatio() { return this.ratio; }, setPixelRatio(r) { calls.push("renderer.setPixelRatio"); this.ratio = r; }},
    equLocal: () => ({applyMatrix4: () => ({x: 1, y: 0, z: 0, length: () => 1})})};
  world.scene.background = {set: log("background.set")};
  const tower = {setSources: log("tower.setSources"), setFigures: log("tower.setFigures"), show: (on) => calls.push(`tower.show(${on})`), mountUI: log("tower.mountUI"), refreshUI: log("tower.refreshUI"),
    refreshStarDisplay: log("tower.refreshStarDisplay"), renderAngles: log("tower.renderAngles"), update: (s) => { calls.push("tower.update"); tower.updated = s; return {status: "ok"}; }, setMode: log("tower.setMode"), select: log("tower.select"),
    invalidate: log("tower.invalidate"), look: {az: 1, alt: 2, fov: 70}, shown: {ground: true, labels: true, figures: true, foot: true, coRising: false},
    setCoRising(lon) { calls.push(`tower.setCoRising(${lon})`); tower.coLon = lon; return {status: "ok"}; },
    getLook() { return {...tower.look}; }, setLook(l) { calls.push("tower.setLook"); tower.look = {...tower.look, ...l}; if (tower.shown.ground) tower.look.alt = Math.max(tower.look.alt, -10); return {status: "ok"}; },
    layers(p) { if (!p) return {...tower.shown}; calls.push("tower.layers"); Object.assign(tower.shown, p); host.syncToggles(); return {status: "ok"}; }, onSelect(fn) { selectHook = fn; }, ownsCamera: () => false, tick: () => {},
    layout: log("tower.layout"), pick: () => ({id: "hip:1"}), pan: () => {}};
  const globals = {performance: {now: () => globals.now}, now: 1000, ResizeObserver: class { constructor(fn) { this.fn = fn; globals.watching = (globals.watching || 0) + 1; } observe() {} disconnect() { globals.watching--; } },
    document: {createElement: element, createTextNode: (words) => ({words})}, window: {innerHeight: 864, devicePixelRatio: 1, addEventListener() {}, removeEventListener() {}, matchMedia: (query) => { const q = {query, matches: false, heard: [], addEventListener(_, fn) { q.heard.push(fn); }, removeEventListener(_, fn) { q.heard = q.heard.filter((f) => f !== fn); }}; queries.push(q); return q; }},
    console: {error: (...a) => calls.push("console.error")},
    Event: class {}, THREE: {Color: class { constructor(c) { this.c = c; this.set = log("background.set"); } }},
    SphereWorld: {create(h) { calls.push("world.create"); globals.lastWorldHost = h; return world; }},
    TowerView: {create(h) { calls.push("tower.create"); host = h; return tower; }},
    FIGURES: [{key: "orion", lines: [["hip:1", "hip:2"], ["hip:1", "hip:9"]], extLines: [], label: {ra: 1, dec: 2}}], FIGURE_EXTRAS: [], SKY_WORDS: options.words || words};
  const timers = [];
  globals.setTimeout = globals.window.setTimeout = (fn, wait) => { timers.push({at: globals.now + (wait || 0), fn}); return timers.length; };
  globals.setInterval = globals.window.setInterval = (fn, wait) => { timers.push({at: globals.now + wait, every: wait, fn}); return timers.length; };
  const step = (ms) => {
    const end = globals.now + ms;
    for (let due = timers.find((t) => t.at <= end); due; due = timers.find((t) => t.at <= end)) {
      globals.now = Math.max(globals.now, due.at);
      if (due.every) due.at += due.every; else timers.splice(timers.indexOf(due), 1);
      due.fn();
    }
    globals.now = end;
  };
  const faces = [];
  if (options.face) {
    globals.FontFace = class { constructor(family, from) { faces.push([family, from]); } load() { return Promise.resolve(this); } };
    globals.document.fonts = {add() {}};
  }
  const body = source.replace("export default function", "return function");
  const run = new Function(...Object.keys(globals), body)(...Object.values(globals));
  return {step, faces, faceLoaded: () => new Promise((done) => setImmediate(done)), run, calls, world, tower, globals, queries, host: () => host, controller: () => controller, frame: () => frameHook, select: () => selectHook};
}

function data(over) {
  return {stars: [{id: "hip:1", ra: 1, dec: 2}, {id: "hip:2", ra: 3, dec: 4}], objects: [{id: "ngc:869", ra: 5, dec: 6, kind: "cluster"}], names: {"hip:1": "One"}, anchors: {orion: {ra: 1.5, dec: 2.5}}, shown: ["hip:1"],
    observer: {lat: 43, lst: 100, obl: 23}, axes: {asc: 10}, descriptor: {mode: "apparentOfDate", epoch: 2, contextId: "zij:c"}, context: "c", population: "Curated List", angles: {}, angles_key: "k", mode: "orbit", theme: "dark",
    palette: {background: "#000000", colours: {brass: "#111111", star: "#222222", steelDim: "#333333"}}, turn: null, speeds: [{rate: 0.25, minutes: 1}, {rate: 0.5, minutes: 2}, {rate: 2.5, minutes: 10}, {rate: 15, minutes: 60}, {rate: 26, minutes: 104}], ...over};
}

function parent() {
  const p = element("div");
  p.isConnected = true;
  return p;
}

test("line 1 and 6: the view is shown, and its list refreshed after the sources", () => {
  const h = harness();
  h.run({data: data(), parentElement: parent(), setTriggerValue() {}});
  const at = (name) => h.calls.indexOf(name);
  assert.ok(at("tower.show(true)") > at("tower.setSources"));
  assert.ok(at("tower.refreshUI") > at("tower.setSources"));
  assert.ok(at("tower.mountUI") > -1);
  assert.equal(typeof h.host().figureName, "function");
  assert.equal(typeof h.host().figureAnchor, "function");
});

test("line 2: the controller is wired to the view", () => {
  const h = harness();
  h.run({data: data(), parentElement: parent(), setTriggerValue() {}});
  const c = h.controller();
  for (const name of ["ownsCamera", "tick", "layout"]) assert.equal(typeof c[name], "function", name);
  assert.equal(c.ownsCamera, h.tower.ownsCamera);
  assert.equal(c.tick, h.tower.tick);
});

test("line 3: figures go in the same task as their sources, and a new moment sends both", () => {
  const h = harness();
  const p = parent();
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  assert.equal(h.calls[h.calls.indexOf("tower.setSources") + 1], "tower.setFigures");
  h.calls.length = 0;
  h.run({data: data({context: "c2"}), parentElement: p, setTriggerValue() {}});
  assert.equal(h.calls[h.calls.indexOf("tower.setSources") + 1], "tower.setFigures");
  assert.ok(h.calls.indexOf("tower.refreshUI") > h.calls.indexOf("tower.setSources"), "line 6, on a new moment too");
});

test("line 3: a rerun of the same moment sets no sources, and keeps the mount", () => {
  const h = harness();
  const p = parent();
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  h.calls.length = 0;
  h.run({data: data({shown: ["hip:2"]}), parentElement: p, setTriggerValue() {}});
  assert.ok(!h.calls.includes("tower.setSources"));
  assert.ok(!h.calls.includes("world.create"));
});

test("line 5: the extras go in with the figures, and line 6: a name and a point before the first frame", () => {
  const h = harness();
  let extras = null;
  h.globals.FIGURE_EXTRAS.push({key: "leo-coma", lines: [["hip:1", "hip:2"]], extLines: [], label: {ra: 3, dec: 4}});
  h.tower.setFigures = (figures, more) => { extras = more; return {status: "ok"}; };
  h.run({data: data(), parentElement: parent(), setTriggerValue() {}});
  assert.equal(extras.length, 1);
  assert.equal(extras[0].key, "leo-coma");
  assert.equal(h.host().figureName({key: "orion"}), "Orion");
  assert.deepEqual(h.host().figureAnchor({key: "orion"}), {ra: 1.5, dec: 2.5});
});

test("line 8: a rerun keeps the mount, and the sky follows the control", () => {
  const h = harness();
  const p = parent();
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  h.calls.length = 0;
  h.run({data: data({population: "Sahl's 28", shown: ["hip:2"]}), parentElement: p, setTriggerValue() {}});
  assert.ok(!h.calls.includes("world.create"));
  assert.ok(h.calls.includes("tower.refreshStarDisplay"));
  assert.deepEqual(h.host().starDisplay().ids, ["hip:2"]);
});

test("a star not placed leaves its figure's lines, not the figure", () => {
  const h = harness();
  let seen = null;
  h.tower.setFigures = (figures) => { seen = figures; return {status: "ok"}; };
  h.run({data: data(), parentElement: parent(), setTriggerValue() {}});
  assert.deepEqual(seen[0].lines, [["hip:1", "hip:2"]]);
});

test("line 4: a throw in layout does not leave the controller", () => {
  const h = harness();
  h.tower.layout = () => { throw Error("boom"); };
  h.run({data: data(), parentElement: parent(), setTriggerValue() {}});
  assert.doesNotThrow(() => h.controller().layout([]));
  assert.doesNotThrow(() => h.controller().layout([]));
  assert.equal(h.calls.filter((c) => c === "console.error").length, 1);
});

test("line 7: the recipe runs once the container is gone, and only then", () => {
  const h = harness();
  const p = parent();
  const cleanup = h.run({data: data(), parentElement: p, setTriggerValue() {}});
  cleanup();
  assert.ok(!h.calls.includes("world.dispose"), "a superseded call's cleanup, with the component standing");
  p.isConnected = false;
  cleanup();
  const order = ["tower.show(false)", "world.clearController", "renderer.forceContextLoss", "world.dispose"].map((n) => h.calls.indexOf(n));
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  assert.ok(order[0] > -1);
  cleanup();
  assert.equal(h.calls.filter((c) => c === "world.dispose").length, 1);
});

test("line 9: a theme's change sets colours, then invalidates, then sets figures, with no re-mount", () => {
  const h = harness();
  const p = parent();
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  h.calls.length = 0;
  h.run({data: data({theme: "light", palette: {background: "#222222", colours: {brass: "#333333"}}}), parentElement: p, setTriggerValue() {}});
  const order = ["world.setColours", "tower.invalidate", "tower.setFigures"].map((n) => h.calls.indexOf(n));
  assert.ok(order[0] > -1);
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  assert.ok(!h.calls.includes("world.create"));
  assert.ok(!h.calls.includes("tower.setSources"));
});

test("line 11: uiText never returns its key, and throws on one it lacks", () => {
  const h = harness();
  h.run({data: data(), parentElement: parent(), setTriggerValue() {}});
  const say = h.host().uiText;
  assert.equal(say("m4.angles"), "Stars on the axes");
  assert.equal(say("m4.longitudeCriterion"), "Longitude within 1° of the axis");
  assert.throws(() => say("m4.noSuchKey"));
  for (const [key, value] of Object.entries(words)) assert.notEqual(value, key);
});

test("settled 9: no zoom hint, and a pick selects the id and asks for its record", () => {
  const h = harness();
  const picked = [];
  h.run({data: data(), parentElement: parent(), setTriggerValue: (k, v) => picked.push([k, v])});
  assert.ok(!("sourceZoomHint" in h.host()));
  assert.ok(h.controller().click(1, 1));
  assert.ok(h.calls.includes("tower.select"));
  assert.deepEqual(picked, [["picked", "hip:1"]]);
});

test("the same turn is not taken twice, and a mount with none selects nothing", () => {
  const h = harness();
  const p = parent();
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  assert.ok(!h.calls.includes("tower.select"));
  h.run({data: data({turn: {seq: 1, id: "hip:1"}}), parentElement: p, setTriggerValue() {}});
  assert.equal(h.calls.filter((c) => c === "tower.select").length, 1);
  h.run({data: data({turn: {seq: 1, id: "hip:1"}, shown: []}), parentElement: p, setTriggerValue() {}});
  assert.equal(h.calls.filter((c) => c === "tower.select").length, 1);
});

test("the view's position is kept across a leaving, in memory", () => {
  const h = harness();
  const one = parent();
  const cleanup = h.run({data: data(), parentElement: one, setTriggerValue() {}});
  h.world.cam.theta = 2.5; h.world.cam.phi = 1.25; h.world.cam.r = 3;
  one.isConnected = false;
  cleanup();
  h.world.cam.theta = 0;
  h.run({data: data(), parentElement: parent(), setTriggerValue() {}});
  assert.equal(h.world.cam.theta, 2.5);
  assert.equal(h.world.cam.tr, 3);
});

test("a ratio changed under a standing page reaches the renderer, capped as the world caps it", () => {
  const h = harness(), box = parent();
  const cleanup = h.run({data: data(), parentElement: box, setTriggerValue() {}});
  const listening = () => h.queries.filter((q) => q.heard.length);
  assert.equal(listening().length, 1);
  assert.match(listening()[0].query, /resolution: 1dppx/);
  for (const [ratio, want] of [[1.5, 1.5], [3, 2], [1.25, 1.25]]) {
    h.globals.window.devicePixelRatio = ratio;
    listening()[0].heard[0]();
    assert.equal(h.world.renderer.ratio, want);
    assert.equal(listening().length, 1, "one query heard at a time");
    assert.ok(listening()[0].query.includes(`resolution: ${ratio}dppx`));
  }
  h.globals.window.devicePixelRatio = 1.5;    // no word from the browser: the next frame reads it
  h.frame()();
  assert.equal(h.world.renderer.ratio, 1.5);
  const set = h.calls.filter((c) => c === "renderer.setPixelRatio").length;
  h.frame()();
  assert.equal(h.calls.filter((c) => c === "renderer.setPixelRatio").length, set, "an unchanged ratio leaves the canvas alone");
  box.isConnected = false;
  cleanup();
  assert.equal(listening().length, 0, "a sky taken down hears no more");
});

// Everything the host makes, by the class it gave it, under the parent.
function find(root, test) {
  for (const child of root.children || []) { if (test(child)) return child; const inner = find(child, test); if (inner) return inner; }
  return null;
}
const named = (root, name) => find(root, (e) => e.className === name);
const expanded = (box) => named(box, "zs").classList.contains("zs-full");
const press = (button) => button.listeners.click();
const escape = (h) => thePage.heard.filter((l) => l.name === "keydown").forEach((l) => l.fn({key: "Escape"}));

test("expand: a class on the sky's own element, nothing on the document or the body", () => {
  const h = harness(), box = parent();
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  assert.equal(expanded(box), false);
  assert.equal(thePage.heard.length, 0, "no Escape listener until it is expanded");
  press(named(box, "zs-expand"));
  assert.equal(expanded(box), true);
  assert.ok(!source.includes("document.body") && !source.includes("documentElement"));
});

test("expand: Escape and the button bring it back, and the height is fitted once on the way", () => {
  for (const back of [(h, box) => escape(h), (h, box) => press(named(box, "zs-expand"))]) {
    const h = harness(), box = parent();
    h.run({data: data(), parentElement: box, setTriggerValue() {}});
    const inst = named(box, "zs").zijSky;
    press(named(box, "zs-expand"));
    const fits = inst.stats.fits;
    h.run({data: data(), parentElement: box, setTriggerValue() {}});
    assert.equal(inst.stats.fits, fits, "expanded, the window sets the box");
    back(h, box);
    assert.equal(expanded(box), false);
    assert.equal(inst.stats.fits, fits + 1);
    assert.equal(thePage.heard.length, 0, "and the listener goes with it");
  }
});

test("expand: Escape with the record or a list open is theirs, whichever opened first", () => {
  for (const selector of ['[data-testid="stDialog"],[role="listbox"]']) {
    const h = harness(), box = parent();
    h.run({data: data(), parentElement: box, setTriggerValue() {}});
    press(named(box, "zs-expand"));
    thePage.found[selector] = {};
    escape(h);
    assert.equal(expanded(box), true);
    delete thePage.found[selector];
    escape(h);
    assert.equal(expanded(box), false);
  }
  assert.ok(thePage.heard.every((l) => l.capture !== false));
});

test("expand: the Escape listener is first in line, so the record is still there to be seen", () => {
  const h = harness(), box = parent();
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  press(named(box, "zs-expand"));
  assert.deepEqual(thePage.heard.map((l) => [l.name, l.capture]), [["keydown", true]]);
});

test("expand: a sky taken down while expanded leaves no listener and no style on the row", () => {
  const h = harness(), box = parent(), row = element("div");
  thePage.found[".st-key-zij-sky-controls"] = row;
  const cleanup = h.run({data: data(), parentElement: box, setTriggerValue() {}});
  press(named(box, "zs-expand"));
  assert.equal(row.style.position, "fixed");
  assert.ok("data-zij-sky-column" in row.attributes);
  assert.equal(thePage.heard.length, 1);
  assert.equal(h.globals.watching, 1);
  box.isConnected = false;
  cleanup();
  assert.equal(thePage.heard.length, 0);
  assert.equal(row.style.position, "");
  assert.ok(!("data-zij-sky-column" in row.attributes));
  assert.equal(h.globals.watching, 0);
  assert.equal(Object.keys(row.listeners).length, 0);
});

function expandedInStreamlit() {
  const h = harness(), box = parent(), container = element("div");
  box.getRootNode = () => ({host: {closest: (selector) => (selector === '[data-testid="stElementContainer"]' ? container : null)}});
  const shown = {data: data(), parentElement: box, setTriggerValue() {}};
  const cleanup = h.run(shown);
  return {h, box, container, shown, cleanup};
}

test("expand: a rerun's fade cannot put the page's sidebar over the sky, by either route", () => {
  const {h, box, container, shown} = expandedInStreamlit();
  assert.equal(container.style.opacity, undefined, "on the page Streamlit's own fade stands as it was");
  assert.equal(container.style.transition, undefined);
  press(named(box, "zs-expand"));
  assert.equal(container.style.opacity, "1");
  assert.equal(container.style.transition, "none");
  container.style.transition = "";
  h.run(shown);
  assert.equal(container.style.transition, "none", "and a rerun does not lose it");
  h.controller().click(1, 1);
  assert.equal(container.style.opacity, "1");
  press(named(box, "zs-expand"));
  assert.equal(container.style.opacity, "", "the way back gives the container back");
  assert.equal(container.style.transition, "");
});

test("expand: a sky taken down while expanded gives its container back", () => {
  const {box, container, cleanup} = expandedInStreamlit();
  press(named(box, "zs-expand"));
  box.isConnected = false;
  cleanup();
  assert.equal(container.style.opacity, "");
  assert.equal(container.style.transition, "");
});

test("expand: the row stands under the record's layer and over the sky's", () => {
  const h = harness(), box = parent(), row = element("div");
  thePage.found[".st-key-zij-sky-controls"] = row;
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  press(named(box, "zs-expand"));
  const css = readFileSync(join(ROOT, "sky_host.css"), "utf-8"), sky = Number(css.match(/\.zs\.zs-full\{[^}]*z-index:(\d+)/)[1]);
  assert.ok(sky < Number(row.style.zIndex) && Number(row.style.zIndex) < 1000059);
  // The row a rerun drew is found again, and takes the same.
  const next = element("div");
  thePage.found[".st-key-zij-sky-controls"] = next;
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  assert.equal(next.style.position, "fixed");
  assert.equal(row.style.position, "");
});

test("the ceiling: the look is held to the box's shape, and the reader's field given back on a wider one", () => {
  const h = harness(), box = parent();
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  const sky = named(box, "zs-sky"), most = (w, high) => Math.min(100, 2 * Math.atan(Math.tan(49 * Math.PI / 180) * high / w) * 180 / Math.PI);
  sky.clientWidth = 906; sky.clientHeight = 473;
  h.frame()();
  assert.ok(Math.abs(h.tower.look.fov - most(906, 473)) < 1e-6 && h.tower.look.fov < 70);
  sky.clientWidth = 1026; sky.clientHeight = 768;
  h.frame()();
  assert.equal(h.tower.look.fov, 70, "expanded keeps the full 70");
  const set = h.calls.filter((c) => c === "tower.setLook").length;
  h.frame()();
  assert.equal(h.calls.filter((c) => c === "tower.setLook").length, set, "an unchanged box leaves the look alone");
});

test("the labels' face: the first mount waits for it, and a later call does not", async () => {
  const h = harness({face: true}), box = parent();
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  assert.equal(box.children.length, 0, "no mount before the face has loaded");
  assert.deepEqual(h.faces, [["IBM Plex Sans Condensed", "url(/zij-font/zij-interface-400.ttf)"]]);
  await h.faceLoaded();
  assert.equal(box.children.length, 1, "mounted once it has");
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  assert.equal(h.faces.length, 1, "one face, however many calls");
});

test("the labels' face: a container gone while it loads is not mounted", async () => {
  const h = harness({face: true}), box = parent();
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  box.isConnected = false;
  await h.faceLoaded();
  assert.equal(box.children.length, 0);
});

test("the ceiling: the wheel meets it going out, a narrower field is the reader's own", () => {
  const h = harness(), box = parent();
  h.run({data: data({mode: "tower"}), parentElement: box, setTriggerValue() {}});
  h.host().TW.mode = "tower";
  const sky = named(box, "zs-sky");
  sky.clientWidth = 906; sky.clientHeight = 473;
  h.frame()();
  const limit = h.tower.look.fov;
  h.controller().zoom(1000, "wheel");
  assert.ok(Math.abs(h.tower.look.fov - limit) < 1e-6);
  h.controller().zoom(-200, "wheel");
  const narrow = h.tower.look.fov;
  assert.ok(narrow < limit);
  sky.clientWidth = 1026; sky.clientHeight = 768;
  h.frame()();
  assert.equal(h.tower.look.fov, narrow);
  h.controller().zoom(-100000, "wheel");
  h.frame()();
  assert.equal(h.tower.look.fov, 20, "the view's own floor, and no setLook at each frame fighting it");
});

test("the ceiling: a box of no size asks nothing of the view", () => {
  const h = harness(), box = parent();
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  const sky = named(box, "zs-sky");
  sky.clientWidth = 0; sky.clientHeight = 0;
  h.frame()();
  assert.equal(h.tower.look.fov, 70);
});

test("the filters: three boxes on the view's layers, read back from it, held across a leaving", () => {
  const h = harness(), box = parent();
  const cleanup = h.run({data: data(), parentElement: box, setTriggerValue() {}});
  const lines = named(box, "zs-filters").children, input = (n) => lines[n].children[0];
  assert.deepEqual(lines.map((l) => l.children[1].words), ["Shaded ground", "Labels", "Constellation figures", "Foot point and arc", "Co-rising degree"]);
  assert.deepEqual(lines.map((l) => l.children[0].checked), [true, true, true, true, false]);
  input(0).checked = false; input(0).listeners.change();
  assert.equal(h.tower.shown.ground, false);
  h.tower.layers({labels: false});     // as the view does itself on some choices
  assert.equal(input(1).checked, false);
  box.isConnected = false;
  cleanup();
  h.tower.shown.ground = h.tower.shown.labels = true;
  const next = parent();
  h.run({data: data(), parentElement: next, setTriggerValue() {}});
  assert.equal(h.tower.shown.ground, false);
  assert.equal(h.tower.shown.labels, false);
  assert.equal(h.tower.shown.figures, true);
});

test("one name: the label's door takes the name alone, and everything else passes as it was", () => {
  const h = harness();
  h.run({data: data({names: {"hip:1": "Spica · α Vir", "hip:2": "η Ori · HIP 25281", "hip:3": "HIP 46952"}}), parentElement: parent(), setTriggerValue() {}});
  for (const [given, drawn] of [["Spica · α Vir", "Spica"], ["η Ori · HIP 25281", "η Ori"], ["HIP 46952", "HIP 46952"], ["ASC 12° · 16′", "ASC 12° · 16′"], ["Orion", "Orion"]]) {
    h.host().label(given, "#fff", 36);
    assert.equal(h.calls.at(-1), `label(${drawn})`);
  }
  assert.equal(h.host().twName("hip:1"), "Spica · α Vir", "the lists and the record keep both");
});

test("the filters: a look below the horizon comes back below it, the ground being off", () => {
  const h = harness(), box = parent();
  const cleanup = h.run({data: data(), parentElement: box, setTriggerValue() {}});
  h.tower.layers({ground: false});
  h.tower.setLook({alt: -40});
  box.isConnected = false;
  cleanup();
  h.tower.shown.ground = true;
  h.tower.look.alt = 0;
  h.run({data: data(), parentElement: parent(), setTriggerValue() {}});
  assert.equal(h.tower.look.alt, -40);
});

// The bar's parts are found by name and role, never by place, so another part shifts nothing.
function turnParts(root) {
  const bar = find(root, (el) => el.className === "zs-turn"), buttons = bar.children.filter((el) => el.tag === "button"),
    turnButton = buttons.find((el) => el.className !== "zs-reverse" && el.textContent !== words["zij.return"]),
    backButton = buttons.find((el) => el.textContent === words["zij.return"]), reverseButton = buttons.find((el) => el.className === "zs-reverse"),
    speedLine = bar.children.find((el) => el.tag === "label");
  return {bar, turnButton, backButton, reverseButton, speed: speedLine.children[1], moment: find(root, (el) => el.className === "zs-note" && el.textContent === words["zij.moment"])};
}

function turned() {
  const h = harness(), p = parent();
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  return {h, p, inst: p.children[0].zijSky, ...turnParts(p)};
}

test("the filters: foot and co-rising are the view's own layers, the second off", () => {
  const h = harness(), p = parent();
  h.tower.shown.coRising = false;
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  const boxes = find(p, (el) => el.className === "zs-filters").children.map((line) => line.children[0]);
  assert.deepEqual(boxes.map((box) => box.checked), [true, true, true, true, false]);
  boxes[4].checked = true;
  boxes[4].listeners.change();
  assert.equal(h.tower.shown.coRising, true);
});

test("the foot: the view is handed the row's own longitude and latitude", () => {
  const h = harness(), p = parent();
  h.run({data: data({stars: [{id: "hip:1", ra: 1, dec: 2, lon: 12.25, lat: -3.5, co: 40}]}), parentElement: p, setTriggerValue() {}});
  assert.deepEqual(h.host().twActiveEcl({id: "hip:1"}), {lon: 12.25, lat: -3.5});
  assert.equal(h.host().twActiveEcl({id: "ngc:869"}), null);
});

test("co-rising: the chosen star's degree goes to the view; none is said plainly, only with its box on", () => {
  const h = harness(), p = parent();
  h.tower.shown.coRising = true;
  const stars = [{id: "hip:1", ra: 1, dec: 2, lon: 1, lat: 1, co: 40.5}, {id: "hip:2", ra: 3, dec: 4, lon: 2, lat: 2, co: null}];
  h.run({data: data({stars, names: {"hip:1": "One", "hip:2": "Two · β X"}}), parentElement: p, setTriggerValue() {}});
  const inst = p.children[0].zijSky, note = find(p, (el) => el.className === "zs-note" && el !== turnParts(p).moment);
  inst.TW.selected = "hip:1"; h.select()("hip:1");
  assert.equal(h.tower.coLon, 40.5);
  assert.equal(note.hidden, true);
  inst.TW.selected = "hip:2"; h.select()("hip:2");
  assert.equal(h.tower.coLon, null);
  assert.equal(note.hidden, false);
  assert.equal(note.textContent, "No co-rising degree is given at this latitude for Two.");
  h.tower.layers({coRising: false});
  assert.equal(note.hidden, true);
});

test("Turn: only the sidereal time moves, by the clock, at the speed the envelope gives", () => {
  const {h, inst, turnButton} = turned();
  h.globals.now = 2000;
  turnButton.listeners.click();
  assert.equal(inst.turn.playing, true);
  assert.equal(turnButton.textContent, words["ui.hold"]);
  assert.equal(h.frame()(3000), true);
  assert.equal(h.tower.updated.lst, 100.5);
  assert.equal(h.tower.updated.lat, 43);
  assert.equal(h.tower.updated.obl, 23);
  h.globals.now = 3500;
  turnButton.listeners.click();
  assert.equal(inst.turn.offset, 0.75);
  assert.equal(turnButton.textContent, words["ui.turn"]);
  assert.notEqual(h.frame()(4000), true);
});

// The sky's own two doors ask through the trigger; the page's finder answers in a rerun's `turn`.
const RECORD_ROUTES = {
  "a click on the star": ({h}) => h.controller().click(1, 1),
  "Open record": ({h, p}) => { h.host().TW.selected = "hip:1"; find(p, (el) => el.className === "zs-open").listeners.click(); },
  "Find with one hit": ({h, p}, seq) => h.run({data: data({turn: {seq, id: "hip:1"}}), parentElement: p, setTriggerValue() {}}),
  "Find with a choice, then its Open record": ({h, p}, seq) => h.run({data: data({turn: {seq, id: "hip:2"}}), parentElement: p, setTriggerValue() {}}),
};
for (const [route, opening] of Object.entries(RECORD_ROUTES)) {
  test(`a record opening by ${route} holds Turn as the button does, and it stays held`, () => {
    const seen = turned(), {h, p, inst, turnButton} = seen;
    const picked = [];
    inst.trigger = (k, v) => picked.push([k, v]);
    h.globals.now = 2000;
    turnButton.listeners.click();
    h.globals.now = 3500;
    opening(seen, 1);
    if (route === "a click on the star" || route === "Open record") assert.deepEqual(picked, [["picked", "hip:1"]], "the record opens");
    assert.equal(inst.turn.playing, false);
    assert.equal(inst.turn.offset, 0.75, "the clock's rule: stopped where it stopped");
    assert.equal(turnButton.textContent, words["ui.turn"]);
    assert.equal(turnButton.attributes["aria-pressed"], "false");
    assert.notEqual(h.frame()(9000), true, "nothing runs on, and the record's closing starts nothing");
    assert.equal(inst.turn.offset, 0.75);
    // A minute of the page's clock past the record's closing, its frames and a rerun in it.
    h.step(60000);
    h.run({data: data(), parentElement: p, setTriggerValue() {}});
    assert.notEqual(h.frame()(h.globals.now + 16), true);
    assert.equal(inst.turn.playing, false, "nothing the opening left waiting starts it again");
    assert.equal(inst.turn.offset, 0.75);
    assert.equal(turnButton.textContent, words["ui.turn"]);
    h.globals.now += 1000;
    turnButton.listeners.click();
    assert.equal(inst.turn.playing, true, "until the reader presses Turn again");
    h.globals.now += 500;
    opening(seen, 2);
    assert.equal(inst.turn.offset, 1, "and on from where it stopped");
  });

  test(`a record opening by ${route} with Turn at rest starts nothing`, () => {
    const seen = turned(), {h, inst, turnButton} = seen;
    inst.trigger = () => {};
    h.globals.now = 2000;
    opening(seen, 1);
    assert.equal(inst.turn.playing, false);
    assert.equal(inst.turn.offset, 0);
    assert.equal(turnButton.textContent, words["ui.turn"]);
  });
}

test("Turn: a rerun that opens no record leaves it running, a list's change among them", () => {
  const {h, p, inst, turnButton} = turned();
  h.globals.now = 2000;
  turnButton.listeners.click();
  h.globals.now = 3000;
  h.run({data: data({population: "Full Catalogue"}), parentElement: p, setTriggerValue() {}});
  assert.equal(inst.population, "Full Catalogue");
  assert.equal(inst.turn.playing, true, "a list's change");
  h.run({data: data({mode: "orbit"}), parentElement: p, setTriggerValue() {}});
  assert.equal(inst.turn.playing, true, "a view's change");
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  assert.equal(inst.turn.playing, true, "a plain rerun");
  assert.equal(turnButton.textContent, words["ui.hold"]);
});

test("Turn: the finder's one answer holds it once, and a call repeating it holds nothing", () => {
  const {h, p, inst, turnButton} = turned(), asked = {data: data({turn: {seq: 4, id: "hip:1"}}), parentElement: p, setTriggerValue() {}};
  h.globals.now = 2000;
  turnButton.listeners.click();
  h.globals.now = 3000;
  h.run(asked);
  assert.equal(inst.turn.playing, false);
  h.globals.now = 4000;
  turnButton.listeners.click();
  h.run(asked);
  assert.equal(inst.turn.playing, true, "the reader pressed Turn since");
});

test("Turn's clock: time at rest is not charged, whichever comes first", () => {
  const {h, inst, turnButton} = turned();
  h.frame()(50000);
  h.globals.now = 60000;
  turnButton.listeners.click();
  assert.equal(inst.turn.offset, 0);
  h.frame()(60000);
  assert.equal(inst.turn.offset, 0);
  h.frame()(59000);
  assert.equal(inst.turn.offset, 0, "a frame stamped before the start counts nothing");
  h.globals.now = 61000;
  turnButton.listeners.click();
  assert.equal(inst.turn.offset, 0.5, "the time before a stop is not lost");
  h.frame()(90000);
  assert.equal(inst.turn.offset, 0.5);
});

test("Turn's clock: a change of speed runs the old speed up to itself", () => {
  const {h, inst, turnButton, speed} = turned();
  h.globals.now = 1000;
  turnButton.listeners.click();
  h.globals.now = 3000;
  speed.value = "4";
  speed.listeners.change();
  assert.equal(inst.turn.offset, 1);
  h.frame()(4000);
  assert.equal(inst.turn.offset, 27);
});

test("Turn: its five speeds in the Tower's words, starting at the second", () => {
  const {speed} = turned();
  assert.deepEqual(speed.children.map((o) => o.textContent), ["1 chart min/s", "2 chart min/s", "10 chart min/s", "1 chart h/s", "104 chart min/s"]);
  assert.equal(speed.value, "1");
});

test("Turn: the Ascendant goes on the first moved frame and a stop does not bring it back", () => {
  const {h, inst, turnButton, backButton, moment} = turned();
  assert.deepEqual(h.tower.updated.axes, {asc: 10});
  assert.equal(backButton.hidden, true);
  assert.equal(moment.hidden, true);
  h.globals.now = 2000;
  turnButton.listeners.click();
  h.frame()(2000);
  assert.deepEqual(h.tower.updated.axes, {asc: 10}, "nothing has moved yet");
  h.frame()(2016);
  assert.equal(h.tower.updated.axes, null);
  assert.equal(moment.hidden, false);
  assert.equal(backButton.hidden, false);
  h.globals.now = 2100;
  turnButton.listeners.click();
  h.frame()(2200);
  assert.equal(h.tower.updated.axes, null);
  assert.ok(inst.turn.offset > 0);
});

test("Turn: a rerun does not move it, and Return brings all of it back", () => {
  const {h, p, inst, turnButton, backButton, moment} = turned();
  h.globals.now = 1000;
  turnButton.listeners.click();
  h.frame()(9000);
  const held = inst.turn.offset;
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  assert.equal(inst.turn.offset, held);
  assert.equal(inst.state.lst, 100 + held);
  assert.equal(h.tower.updated.axes, null);
  backButton.listeners.click();
  assert.equal(inst.turn.playing, false);
  assert.equal(inst.turn.offset, 0);
  assert.equal(inst.state.lst, 100);
  assert.equal(moment.hidden, true);
  assert.equal(backButton.hidden, true);
  h.frame()(10000);
  assert.deepEqual(h.tower.updated.axes, {asc: 10});
  assert.equal(h.tower.updated.lst, 100);
});

test("Turn: a new chart returns it at once, and sets it still", () => {
  const {h, p, inst, turnButton, moment} = turned();
  h.globals.now = 1000;
  turnButton.listeners.click();
  h.frame()(9000);
  h.run({data: data({context: "d", observer: {lat: 43, lst: 200, obl: 23}}), parentElement: p, setTriggerValue() {}});
  assert.equal(inst.turn.playing, false);
  assert.equal(inst.turn.offset, 0);
  assert.equal(inst.state.lst, 200);
  assert.equal(moment.hidden, true);
  assert.equal(turnButton.textContent, words["ui.turn"]);
  assert.deepEqual(h.tower.updated.axes, {asc: 10});
});

test("Turn: nothing of it goes to Python, and a page move leaves it stopped with only its speed held", () => {
  const {h, p, inst, turnButton, speed} = turned();
  let told = 0;
  inst.trigger = () => { told++; };
  h.globals.now = 1000;
  turnButton.listeners.click();
  speed.value = "3";
  speed.listeners.change();
  h.frame()(9000);
  assert.equal(told, 0);
  const cleanup = h.run({data: data(), parentElement: p, setTriggerValue() {}});
  p.isConnected = false;
  cleanup();
  assert.equal(inst.turn.playing, false);
  const q = parent();
  h.run({data: data(), parentElement: q, setTriggerValue() {}});
  const again = q.children[0].zijSky;
  assert.equal(again.turn.playing, false);
  assert.equal(again.turn.offset, 0);
  assert.equal(again.turn.speed, 3);
});

test("Reverse: a button after Turn in the bar, pressed or not, its word fixed", () => {
  const {bar, turnButton, reverseButton, backButton} = turned();
  assert.ok(reverseButton, "found by its own mark, not its place");
  assert.equal(bar.children.indexOf(reverseButton), bar.children.indexOf(turnButton) + 1);
  assert.equal(reverseButton.textContent, words["zij.reverse"]);
  assert.equal(reverseButton.hidden, false);
  assert.equal(reverseButton.attributes["aria-pressed"], "false");
  press(reverseButton);
  assert.equal(reverseButton.attributes["aria-pressed"], "true");
  assert.equal(reverseButton.textContent, words["zij.reverse"], "the word does not change with the press");
  assert.equal(turnButton.attributes["aria-pressed"], "false", "Turn's own press is its own");
  press(reverseButton);
  assert.equal(reverseButton.attributes["aria-pressed"], "false");
  assert.equal(backButton.hidden, true, "a press that moves nothing brings no Return");
});

test("Reverse: pressed with Turn at rest only sets the way; the next Turn goes that way", () => {
  const {h, inst, turnButton, reverseButton} = turned();
  h.globals.now = 1000;
  press(reverseButton);
  assert.equal(inst.turn.back, true);
  assert.equal(inst.turn.playing, false);
  assert.equal(inst.turn.offset, 0);
  h.frame()(5000);
  assert.equal(inst.turn.offset, 0, "nothing moves at rest");
  h.globals.now = 6000;
  press(turnButton);
  h.frame()(7000);
  assert.equal(inst.turn.offset, 359.5, "half a degree back, from 0");
  assert.equal(h.tower.updated.lst, 99.5);
});

test("Reverse: the time before a switch is charged the old way, the time after the new", () => {
  const {h, inst, turnButton, reverseButton} = turned();
  h.globals.now = 1000;
  press(turnButton);
  h.globals.now = 3000;
  press(reverseButton);
  assert.equal(inst.turn.offset, 1, "two seconds at 0.5 a second, forward, charged before the flip");
  h.frame()(4000);
  assert.equal(inst.turn.offset, 0.5, "one second back");
  h.globals.now = 5000;
  press(reverseButton);
  assert.equal(inst.turn.offset, 0, "three seconds in all: back to the start, charged back before the flip");
  h.frame()(6000);
  assert.equal(inst.turn.offset, 0.5, "and forward again");
  assert.equal(inst.turn.playing, true, "a switch does not stop it");
});

test("Reverse: the wrapper's angles stay in [0, 360) whichever way, at the fastest speed too", () => {
  const {h, p, inst, turnButton, reverseButton, speed} = turned();
  const inRange = (x) => x >= 0 && x < 360;
  press(reverseButton);
  h.globals.now = 1000;
  press(turnButton);
  h.frame()(2000);
  assert.ok(inRange(inst.turn.offset) && inst.turn.offset > 359, "a wrap below 0 comes round from the top");
  assert.ok(inRange(h.tower.updated.lst));
  speed.value = "4";
  speed.listeners.change();
  h.frame()(101000);
  assert.ok(inRange(inst.turn.offset), "2600 degrees back");
  assert.ok(inRange(inst.state.lst) && inRange(h.tower.updated.lst));
  h.run({data: data({observer: {lat: 43, lst: 0, obl: 23}}), parentElement: p, setTriggerValue() {}});
  assert.ok(inRange(inst.state.lst), "a chart standing at 0, turned back past it");
  assert.equal(inst.state.lst, inst.turn.offset);
});

test("Reverse: Return and a new chart set it forward, unpressed", () => {
  const {h, p, inst, turnButton, reverseButton, backButton} = turned();
  h.globals.now = 1000;
  press(reverseButton);
  press(turnButton);
  h.frame()(9000);
  press(backButton);
  assert.equal(inst.turn.back, false, "Return");
  assert.equal(reverseButton.attributes["aria-pressed"], "false");
  h.globals.now = 10000;
  press(turnButton);
  h.frame()(11000);
  assert.equal(inst.turn.offset, 0.5, "forward after Return");
  press(reverseButton);
  assert.equal(inst.turn.back, true);
  h.run({data: data({context: "d", observer: {lat: 43, lst: 200, obl: 23}}), parentElement: p, setTriggerValue() {}});
  assert.equal(inst.turn.back, false, "a new chart");
  assert.equal(reverseButton.attributes["aria-pressed"], "false");
  h.globals.now = 12000;
  press(turnButton);
  h.frame()(13000);
  assert.equal(inst.turn.offset, 0.5, "forward on the new chart");
});

test("Reverse: a rerun that is no new chart leaves it pressed", () => {
  const {h, p, inst, reverseButton} = turned();
  press(reverseButton);
  h.run({data: data({population: "Full Catalogue"}), parentElement: p, setTriggerValue() {}});
  assert.equal(inst.turn.back, true);
  assert.equal(reverseButton.attributes["aria-pressed"], "true");
});

test("Reverse: nothing of it goes to Python, and a page move keeps it, as it keeps the speed", () => {
  const {h, p, inst, turnButton, reverseButton} = turned();
  let told = 0;
  inst.trigger = () => { told++; };
  h.globals.now = 1000;
  press(reverseButton);
  press(turnButton);
  h.frame()(9000);
  press(reverseButton);
  press(reverseButton);
  assert.equal(told, 0);
  const cleanup = h.run({data: data(), parentElement: p, setTriggerValue() {}});
  p.isConnected = false;
  cleanup();
  const q = parent();
  h.run({data: data(), parentElement: q, setTriggerValue() {}});
  const again = q.children[0].zijSky, parts = turnParts(q);
  assert.equal(again.turn.playing, false, "the turn itself ended with the page");
  assert.equal(again.turn.back, true, "the direction is kept");
  assert.equal(parts.reverseButton.attributes["aria-pressed"], "true");
  h.globals.now = 20000;
  press(parts.turnButton);
  h.frame()(21000);
  assert.equal(again.turn.offset, 359.5, "and the next Turn on the new page goes back");
});

test("Reverse: a new chart made on another page comes back forward; the same chart keeps it; the speed keeps its own rule", () => {
  const {h, p, inst, reverseButton} = turned();
  press(reverseButton);
  inst.turn.speed = 3;
  const cleanup = h.run({data: data(), parentElement: p, setTriggerValue() {}});
  p.isConnected = false;
  cleanup();
  const q = parent();
  h.run({data: data({context: "d"}), parentElement: q, setTriggerValue() {}});
  const again = q.children[0].zijSky, parts = turnParts(q);
  assert.equal(again.turn.back, false, "a chart made elsewhere sets it forward");
  assert.equal(parts.reverseButton.attributes["aria-pressed"], "false", "and the button shows it");
  assert.equal(again.turn.speed, 3, "the speed is kept, as before");
  h.globals.now = 20000;
  press(parts.turnButton);
  h.frame()(21000);
  assert.equal(again.turn.offset, 15, "and the next Turn goes forward, at the kept speed");
});

test("Reverse: its word is the words file's, not one typed in the host", () => {
  const h = harness({words: {...words, "zij.reverse": "Backwards"}}), p = parent();
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  assert.equal(turnParts(p).reverseButton.textContent, "Backwards");
  assert.ok(!/["']Reverse["']/.test(source), "no literal of the word in sky_host.js");
});

test("the armillary: from within every group is off, its preference kept, and from outside it shows what it did", () => {
  const h = harness(), p = parent();
  h.world.PREF = {horizon: true, ecliptic: true, equator: true, zodiacBand: false};
  h.world.L = {horizon: {isGroup: true}, ecliptic: {isGroup: true}, equator: {isGroup: true}, zodiacBand: {isGroup: true}};
  h.run({data: data(), parentElement: p, setTriggerValue() {}});
  const inst = p.children[0].zijSky, seen = () => Object.fromEntries(Object.entries(h.world.L).map(([k, g]) => [k, g.visible]));
  inst.TW.mode = "tower";
  h.host().applyVisibility();
  assert.deepEqual(seen(), {horizon: false, ecliptic: false, equator: false, zodiacBand: false});
  assert.deepEqual(h.world.PREF, {horizon: true, ecliptic: true, equator: true, zodiacBand: false});
  inst.TW.mode = "orbit";
  h.host().applyVisibility();
  assert.deepEqual(seen(), {horizon: true, ecliptic: true, equator: true, zodiacBand: false});
});

test("co-rising: a new chart gives the chosen star its new degree, and its foot reads the new row", () => {
  const h = harness(), p = parent();
  h.run({data: data({stars: [{id: "hip:1", ra: 1, dec: 2, lon: 5, lat: 1, co: 40}]}), parentElement: p, setTriggerValue() {}});
  const inst = p.children[0].zijSky;
  inst.TW.selected = "hip:1"; h.select()("hip:1");
  assert.equal(h.tower.coLon, 40);
  h.run({data: data({context: "d", stars: [{id: "hip:1", ra: 1, dec: 2, lon: 6, lat: 1, co: 50}]}), parentElement: p, setTriggerValue() {}});
  assert.equal(h.tower.coLon, 50);
  assert.deepEqual(h.host().twActiveEcl({id: "hip:1"}), {lon: 6, lat: 1});
});

test("co-rising: the plain line gives the star's one name, not its two", () => {
  const h = harness(), p = parent();
  h.tower.shown.coRising = true;
  h.run({data: data({stars: [{id: "hip:2", ra: 3, dec: 4, lon: 2, lat: 2, co: null}], names: {"hip:2": "Polaris · α UMi"}}), parentElement: p, setTriggerValue() {}});
  const inst = p.children[0].zijSky;
  inst.TW.selected = "hip:2"; h.select()("hip:2");
  assert.equal(find(p, (el) => el.className === "zs-note" && !el.hidden).textContent, "No co-rising degree is given at this latitude for Polaris.");
});

// A sky unable to stand: what the reader gets is one sentence, whatever threw and whenever.
const SENTENCE = "The sky cannot be drawn in this window.";
const sentences = (box) => box.children.filter((el) => el.className === "zs-unable");
function assertOneSentence(h, box) {
  const notes = sentences(box);
  assert.equal(notes.length, 1, "one sentence");
  assert.equal(notes[0].textContent, SENTENCE);
  assert.ok(box.children.filter((el) => el.className === "zs").every((el) => el.removed), "the part-built panel, its Speed with it, is out");
  assert.equal(h.calls.filter((c) => c === "console.error").length > 0, true, "said once on the console");
}
function unableHarness() {
  const h = harness(), listeners = [];
  h.globals.window.addEventListener = (name, fn) => listeners.push([name, fn]);
  h.globals.window.removeEventListener = (name, fn) => { const at = listeners.findIndex((l) => l[0] === name && l[1] === fn); if (at >= 0) listeners.splice(at, 1); };
  return {h, listeners};
}

test("no sky at the view's start: one sentence, no stray control, nothing left listening", () => {
  const {h, listeners} = unableHarness(), box = parent();
  let tries = 0;
  h.globals.SphereWorld.create = () => { tries++; throw Error("Error creating WebGL context"); };
  const shown = {data: data(), parentElement: box, setTriggerValue() {}};
  const cleanup = h.run(shown);
  assertOneSentence(h, box);
  assert.equal(listeners.length, 0);
  h.run(shown);
  h.run({data: data({population: "Full Catalogue"}), parentElement: box, setTriggerValue() {}});
  assert.equal(tries, 1, "reruns do not throw again");
  assert.equal(sentences(box).length, 1, "and do not stack it");
  box.isConnected = false;
  cleanup();
  const back = parent();
  h.run({data: data(), parentElement: back, setTriggerValue() {}});
  assert.equal(tries, 2, "a page move and back asks once more");
  assertOneSentence(h, back);
  assert.equal(listeners.length, 0);
});

test("no sky part way into the mount: the world it had is let go, and the same one sentence", () => {
  const {h, listeners} = unableHarness(), box = parent();
  h.globals.TowerView.create = () => { throw Error("the view"); };
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  assertOneSentence(h, box);
  assert.ok(h.calls.includes("world.dispose") && h.calls.includes("renderer.forceContextLoss"));
  assert.equal(listeners.length, 0);
});

test("no sky at the first apply: the whole recipe runs, and the same one sentence", () => {
  const {h, listeners} = unableHarness(), box = parent();
  h.tower.setSources = () => ({status: "refused"});
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  assertOneSentence(h, box);
  assert.ok(h.calls.includes("tower.show(false)") && h.calls.includes("world.dispose"));
  assert.equal(listeners.length, 0);
  const worlds = h.calls.filter((c) => c === "world.create").length;
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  assert.equal(h.calls.filter((c) => c === "world.create").length, worlds, "and no second mount");
});

test("no sky at a later rerun: the standing sky goes the same way, expanded or not", () => {
  const {h, listeners} = unableHarness(), box = parent();
  const shown = {data: data(), parentElement: box, setTriggerValue() {}};
  h.run(shown);
  const inst = box.children[0].zijSky;
  inst.setFull(true);
  h.tower.renderAngles = () => { throw Error("the angles"); };
  h.run({data: data({angles_key: "other"}), parentElement: box, setTriggerValue() {}});
  assertOneSentence(h, box);
  assert.equal(thePage.heard.length, 0, "no Escape listener left");
  assert.equal(listeners.length, 0);
  h.run(shown);
  assert.equal(sentences(box).length, 1);
});

test("a throw in the sky's labels is not that: the sky stands and no sentence comes", () => {
  const h = harness(), box = parent();
  h.run({data: data(), parentElement: box, setTriggerValue() {}});
  h.tower.layout = () => { throw Error("labels"); };
  h.controller().layout([]);
  assert.equal(sentences(box).length, 0);
  assert.equal(box.children[0].removed, undefined);
});
