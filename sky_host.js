// The sky's host: mounts the view, hands it the places the engine computed, and
// takes it down whole before its container goes. Its colours, words and numbers
// all arrive from outside it.
const HELD = new WeakMap();
const STATS = {modules: 1, mounts: 0, disposes: 0, calls: 0, sourcesSet: 0, themes: 0, layoutThrows: 0, picks: 0, turns: 0, fits: 0, unable: 0, layoutError: null};
// Where the reader left the view, for a return to the page. Memory only, for as
// long as this page of the browser stands.
let SAVED = null;
// The widest the view looks, across (98 degrees). Past it a figure at
// the box's edge draws more than 2.3 times its width at the centre.
const WIDEST = Math.tan(49 * Math.PI / 180);
// The view's own bounds on its field.
const NARROWEST_FOV = 20, WIDEST_FOV = 100;
// What a name and its designation stand joined by, in the engine's label.
const SECOND_FORM = " · ";
// The view's own layers, as the reader's checkboxes.
const FILTERS = [["ground", "lay.ground"], ["labels", "tw.labels"], ["figures", "tw.figures"],
  ["foot", "tw.foot"],
  ["coRising", "tw.coRising"]];
// Which of the envelope's speeds Turn starts on: 2 chart minutes a second, the Tower's.
const TURN_START = 1;
// The wrapper's own angles, the offset and the sidereal time it hands on, stay in [0, 360),
// whichever way the sky turns.
const norm = (x) => ((x % 360) + 360) % 360;
// Expanded, Streamlit's row stands over the sky's column, whose width this is. Under the
// record's layer, which must open on top of it (Streamlit's dialog stands at 1000059).
const COLUMN = 340, LAYER = 1000000, ROW_KEY = ".st-key-zij-sky-controls";
// The page's stylesheet lets the row's buttons wrap in the column, by this mark.
const COLUMN_MARK = "data-zij-sky-column";
const ROW_STYLE = {position: "fixed", top: "0", right: "0", width: COLUMN + "px", zIndex: String(LAYER + 1), boxSizing: "border-box", padding: "12px 16px", margin: "0"};
// Through a rerun Streamlit fades whatever stands on the page, and a fade makes a stacking
// context of the element's container. The layer above would then count only inside it, and
// the app's sidebar and top band would stand over the expanded sky until the rerun ended.
const CONTAINER_KEY = '[data-testid="stElementContainer"]', STILL_STYLE = {opacity: "1", transition: "none"};

function text(key, args) {
  if (!Object.prototype.hasOwnProperty.call(SKY_WORDS, key)) throw Error("Missing string " + key);
  return SKY_WORDS[key].replace(/\{([^}]+)\}/g, (all, k) => (args && args[k] != null ? args[k] : all));
}

function shape(figures, known) {
  // A star the engine could not place at this moment is left out of its figure's lines.
  const whole = (lines) => lines.filter((line) => line.every((id) => known[id]));
  return figures.map((f) => Object.assign({}, f, {lines: whole(f.lines || []), extLines: whole(f.extLines || [])}));
}

// What a mount has taken so far goes into `undo`, so that a throw part way leaves nothing.
function mount(parent, data, undo) {
  const panel = document.createElement("div");
  panel.className = "zs";
  const sky = document.createElement("div");
  sky.className = "zs-sky";
  panel.appendChild(sky);
  const panels = document.createElement("div");
  panels.className = "zs-panels";
  panel.appendChild(panels);
  const expand = document.createElement("button");
  expand.type = "button";
  expand.className = "zs-expand";
  panel.appendChild(expand);
  const filters = document.createElement("div");
  filters.className = "zs-filters";
  filters.setAttribute("role", "group");
  filters.setAttribute("aria-label", text("zij.filters"));
  panels.appendChild(filters);
  const noDegree = document.createElement("p"), moment = document.createElement("p");
  noDegree.className = moment.className = "zs-note";
  noDegree.hidden = moment.hidden = true;
  moment.textContent = text("zij.moment");
  panels.appendChild(noDegree);
  panels.appendChild(moment);
  const turnBar = document.createElement("div"), turnButton = document.createElement("button"), speedLine = document.createElement("label"),
    speedChoice = document.createElement("select"), backButton = document.createElement("button"), reverseButton = document.createElement("button");
  turnBar.className = "zs-turn";
  turnButton.type = backButton.type = reverseButton.type = "button";
  reverseButton.className = "zs-reverse";
  reverseButton.textContent = text("zij.reverse");
  backButton.textContent = text("zij.return");
  backButton.title = text("zij.returnTitle");
  backButton.hidden = true;
  speedLine.appendChild(document.createTextNode(text("tw.speed")));
  speedLine.appendChild(speedChoice);
  [turnButton, reverseButton, speedLine, backButton].forEach((part) => turnBar.appendChild(part));
  panel.appendChild(turnBar);
  parent.appendChild(panel);
  undo.push(() => panel.remove());
  const ui = {};
  ["sources", "angles", "card", "form"].forEach((name) => {
    const section = document.createElement("section");
    panels.appendChild(section);
    ui[name] = section;
  });
  // The record is the page's own, and the chart's moment is the sidebar's.
  ui.card.hidden = true;
  ui.form.hidden = true;
  ui.angles.className = "zs-angles";
  const inst = {byId: {}, names: {}, shown: [], anchors: {}, trigger: null, context: null, population: null, theme: data.theme, angles: null, turnSeq: null, mode: "orbit",
    state: Object.assign({}, data.observer), desc: data.descriptor, axes: null, ui: ui, sky: sky, panel: panel, stats: STATS};

  function fit() {
    // Expanded, the window sets its box; the way back runs this once.
    if (inst.full) return;
    STATS.fits++;
    const scroller = parent.getRootNode().host && parent.getRootNode().host.closest ? parent.getRootNode().host.closest('[data-testid="stMain"]') : null;
    const top = sky.getBoundingClientRect().top + (scroller ? scroller.scrollTop : 0);
    // The panels' first line shows under it, so the page reads as going on.
    sky.style.height = Math.max(320, Math.floor(window.innerHeight - top - 40)) + "px";
  }
  fit();
  window.addEventListener("resize", fit);
  undo.push(() => window.removeEventListener("resize", fit));
  inst.fit = fit;

  let world = SphereWorld.create({container: sky, T: text, colours: data.palette.colours, reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches, observer: inst.state});
  undo.push(() => {
    if (ratioQuery) ratioQuery.removeEventListener("change", onRatio);
    world.setController(null);
    world.renderer.forceContextLoss();
    world.dispose();
  });
  world.scene.background = new THREE.Color(data.palette.background);
  // The world takes the screen's ratio once, at its start. A window moved to another
  // screen brings the new one here, capped as the world caps it: heard where the
  // browser says so, and read at each frame where it does not.
  let ratioQuery = null;
  function syncRatio() {
    const wanted = Math.min(window.devicePixelRatio || 1, 2);
    if (world.renderer.getPixelRatio() !== wanted) world.renderer.setPixelRatio(wanted);
  }
  function watchRatio() {
    if (ratioQuery) ratioQuery.removeEventListener("change", onRatio);
    ratioQuery = window.matchMedia("(resolution: " + (window.devicePixelRatio || 1) + "dppx)");
    ratioQuery.addEventListener("change", onRatio);
  }
  function onRatio() {
    watchRatio();
    syncRatio();
    world.kick();
  }
  watchRatio();
  world.setLayers({horizon: true, ground: true, meridian: true, primeVertical: false, cardinals: true, zenith: true, equator: true, poles: true, decCircles: false, raTicks: false, ecliptic: true, zodiacBand: false, signGlyphs: true, quadrants: false});
  const TW = {applied: true, mode: "orbit", selected: null, linked: false};
  const host = Object.assign({}, world.towerHost);
  let tower = null;
  const boxes = {};
  // The view sets a layer itself on some choices of a star, so the boxes read it back.
  function syncBoxes() {
    if (!tower) return;
    const on = tower.layers();
    FILTERS.forEach(([layer]) => { boxes[layer].checked = on[layer]; });
    syncCoRising();
  }
  // The degree that rises with the chosen star, or a plain line where it has none.
  function syncCoRising() {
    const id = TW.selected, row = id ? inst.byId[id] : null, none = !!row && row.co == null;
    tower.setCoRising(row && !none ? row.co : null);
    noDegree.hidden = !(none && tower.layers().coRising);
    if (!noDegree.hidden) noDegree.textContent = text("zij.noCoRising", {name: oneName.get(inst.names[id]) || id});
  }
  FILTERS.forEach(([layer, key]) => {
    const line = document.createElement("label"), box = document.createElement("input");
    box.type = "checkbox";
    box.checked = true;
    box.addEventListener("change", () => { tower.layers({[layer]: box.checked}); });
    boxes[layer] = box;
    line.appendChild(box);
    line.appendChild(document.createTextNode(text(key)));
    filters.appendChild(line);
  });
  // On the map a star has one name. The view asks one thing for its lists, its record
  // and its labels, but every label on the map is drawn through this door alone.
  const drawLabel = host.label, oneName = new Map();
  // The armillary is made to be read from outside: within it the view's own thin guides
  // stand for its rings and letters, and read the same preferences.
  function visible() {
    Object.keys(world.PREF).forEach((k) => { if (world.L[k] && world.L[k].isGroup) world.L[k].visible = !!world.PREF[k] && TW.mode !== "tower"; });
  }
  Object.assign(host, {TW: TW, TW_PRIO: {select: 0, target: 1, guide: 2, other: 3}, twActiveEcl: (r) => { const row = inst.byId[r.id]; return row && row.lon != null ? {lon: row.lon, lat: row.lat} : null; }, twName: (id) => inst.names[id] || id, twCopy: (v) => JSON.parse(JSON.stringify(v)), twFinite: Number.isFinite, applyVisibility: visible, syncToggles: syncBoxes, label: (words, ...rest) => drawLabel(oneName.has(words) ? oneName.get(words) : words, ...rest), twSyncUI: () => {}, setReveal: () => {}, sourcePriority: () => 3, sourceLabelRank: (r) => (r.vmag != null && r.vmag <= 2.5 ? 0 : 1),
    uiText: text, uiFormat: (v) => String(v), sourceEntries: () => ({status: "unavailable", entries: null}), entryView: () => { throw Error("No entries"); },
    sourceDetails: (id) => { const r = inst.byId[id]; return {kind: r.kind || "star", ra: r.ra, dec: r.dec, az: null, alt: null, lon: null, lat: null, vmag: r.vmag, bv: null, motion: "measured", foot: {state: "unavailable"}, events: null, co: null, identificationSets: [[id]]}; },
    alternativeIdentifications: () => false, civilFields: () => ({date: "", time: "", offset: "", latitude: "", longitude: ""}), validateCivil: () => ({status: "unavailable", messageKey: "m4.unavailable"}), applyCivil: () => ({status: "unavailable", messageKey: "m4.unavailable"}), onCivilInput: () => {}, onEntrySelect: () => {},
    starDisplay: () => ({mode: "significant", status: "ok", ids: inst.shown}),
    figureName: (f) => text("figure." + f.key), figureAnchor: (f) => inst.anchors[f.key] || null});
  const parents = [world.scene, world.equGroup, world.eclGroup], before = parents.map((p) => p.children.slice());
  tower = TowerView.create(host);
  syncBoxes();
  let roots = [];
  parents.forEach((p, i) => { p.children.forEach((c) => { if (before[i].indexOf(c) < 0) roots.push(c); }); });

  const open = document.createElement("button");
  open.type = "button";
  open.className = "zs-open";
  open.textContent = text("zij.open");
  open.disabled = true;
  open.addEventListener("click", () => { if (TW.selected) openRecord(TW.selected); });
  tower.onSelect((id) => { open.disabled = !id; syncCoRising(); });

  // The reader's own field, kept apart from what the box's shape allows it, so the page
  // can narrow it and the expanded form give it back.
  inst.wanted = tower.getLook().fov;
  function ceiling() {
    const across = sky.clientWidth, high = sky.clientHeight;
    return across > 0 && high > 0 ? Math.min(WIDEST_FOV, Math.max(NARROWEST_FOV, 2 * Math.atan(WIDEST * high / across) * 180 / Math.PI)) : WIDEST_FOV;
  }
  // Each frame comes here, so each change of the box does: the window, the sidebar, the expanding.
  function holdLook() {
    const look = tower.getLook(), fov = Math.min(inst.wanted, ceiling());
    if (Math.abs(look.fov - fov) > 1e-6) { look.fov = fov; tower.setLook(look); }
  }
  // Turn moves the sidereal time alone: every star stands at the engine's place. The
  // turn is held apart from the chart's own time, which any rerun hands in afresh, and
  // lives in this page's memory alone: nothing of it goes to Python.
  // `back` is the sky turning the other way, as if the chart's clock ran backward.
  const turn = {offset: 0, moved: false, playing: false, back: false, speed: TURN_START, clock: 0};
  inst.turn = turn;
  function showTurn() {
    turnButton.textContent = text(turn.playing ? "ui.hold" : "ui.turn");
    turnButton.setAttribute("aria-pressed", String(turn.playing));
    reverseButton.setAttribute("aria-pressed", String(turn.back));
    backButton.hidden = moment.hidden = !turn.moved;
  }
  // Every start, stop and change of speed counts the clock up to its own moment first,
  // so time at rest is never charged and the time before a stop is never lost. A frame
  // stamped before the clock counts nothing.
  function clockTo(t) {
    if (!(t > turn.clock)) return;
    const seconds = (t - turn.clock) / 1000;
    turn.clock = t;
    if (!turn.playing) return;
    turn.offset = norm(turn.offset + (turn.back ? -1 : 1) * inst.speeds[turn.speed].rate * seconds);
    if (!turn.moved) { turn.moved = true; showTurn(); }
  }
  function setTurning(on) {
    clockTo(performance.now());
    turn.playing = on;
    showTurn();
    world.kick();
  }
  function backToChart() {
    clockTo(performance.now());
    turn.playing = turn.moved = turn.back = false;
    turn.offset = 0;
    showTurn();
    turnTime();
    world.kick();
  }
  function turnTime() {
    inst.state.lst = norm(inst.chartLst + turn.offset);
    world.setObserver(inst.state);
  }
  // A star's record opening from the sky holds Turn, as the button does, and it stays held
  // when the record closes, until the reader presses Turn again.
  function holdTurn() {
    if (turn.playing) setTurning(false);
  }
  function openRecord(id) {
    holdTurn();
    if (inst.trigger) inst.trigger("picked", id);
  }
  turnButton.addEventListener("click", () => setTurning(!turn.playing));
  backButton.addEventListener("click", backToChart);
  // The time since the last charge is charged the old way first, then the direction turns;
  // pressed while Turn is held, it only sets which way the next Turn goes.
  reverseButton.addEventListener("click", () => { clockTo(performance.now()); turn.back = !turn.back; showTurn(); });
  speedChoice.addEventListener("change", () => { clockTo(performance.now()); turn.speed = Number(speedChoice.value); });
  showTurn();
  // The Ascendant's mark and degree are the engine's for the chart's moment, and no other.
  function place() {
    tower.update({lat: inst.state.lat, lst: inst.state.lst, obl: inst.state.obl, axes: turn.moved ? null : inst.axes, linked: false, contextId: inst.desc.contextId});
  }
  // A throw here would skip the frame and end the loop until the next kick: the
  // sky goes on without its labels, and the first error is said once.
  function guardedLayout(boxes) {
    try { return tower.layout(boxes); }
    catch (e) { if (!STATS.layoutThrows++) { STATS.layoutError = String(e); console.error("Sky labels:", e); } }
  }
  // Nearer than the world's own start: the sphere and its labels fill the height, whole.
  world.cam.r = world.cam.tr = 3.6;
  world.placeCamera();
  world.setController({ownsCamera: tower.ownsCamera, tick: tower.tick, layout: guardedLayout, dragThreshold: () => 5,
    drag: (dx, dy) => { if (TW.mode !== "tower") return false; tower.pan(dx, dy); return true; },
    zoom: (delta, kind) => { if (TW.mode !== "tower") return false; const look = tower.getLook(), limit = ceiling(), next = look.fov + (kind === "wheel" ? 0.03 : -0.12) * delta; inst.wanted = next < limit ? Math.max(NARROWEST_FOV, next) : Math.max(inst.wanted, limit); look.fov = Math.min(inst.wanted, limit); tower.setLook(look); return true; },
    click: (x, y) => { const hit = tower.pick(x, y); if (hit) { tower.select(hit.id); STATS.picks++; openRecord(hit.id); } return !!hit; }});
  world.onFrame("before", (now) => { if (!STATS.firstMode) STATS.firstMode = TW.mode; syncRatio(); holdLook(); clockTo(now); if (turn.moved) turnTime(); place(); return turn.playing; });

  // The whole window, the row and the panels in a column beside the sky. The class stands
  // on the sky's own element, so whatever takes the sky away takes this with it.
  const page = parent.ownerDocument;
  let row = null, rowWatch = null, still = null;
  function holdStill() {
    const root = parent.getRootNode(), found = root.host && root.host.closest ? root.host.closest(CONTAINER_KEY) : null;
    if (found !== still) freeStill();
    still = found;
    if (still) Object.assign(still.style, STILL_STYLE);
  }
  function freeStill() {
    if (still) Object.keys(STILL_STYLE).forEach((k) => { still.style[k] = ""; });
    still = null;
  }
  function moveRow() {
    if (row) row.style.transform = "translateY(" + -panels.scrollTop + "px)";
  }
  function measureRow() {
    if (row) panels.style.paddingTop = row.offsetHeight + "px";
  }
  // The row and the panels are two trees that scroll as one column.
  function wheelRow(e) { panels.scrollTop += e.deltaY; }
  function topOfRow() { panels.scrollTop = 0; }
  function freeRow() {
    if (rowWatch) { rowWatch.disconnect(); rowWatch = null; }
    if (!row) return;
    row.removeEventListener("wheel", wheelRow);
    row.removeEventListener("focusin", topOfRow);
    Object.keys(ROW_STYLE).concat("transform").forEach((k) => { row.style[k] = ""; });
    row.removeAttribute(COLUMN_MARK);
    row = null;
  }
  function holdRow() {
    const found = page.querySelector(ROW_KEY);
    if (found !== row) {
      freeRow();
      row = found;
      if (!row) return;
      row.addEventListener("wheel", wheelRow, {passive: true});
      row.addEventListener("focusin", topOfRow);
      rowWatch = new ResizeObserver(measureRow);
      rowWatch.observe(row);
    }
    if (!row) return;
    Object.assign(row.style, ROW_STYLE);
    row.setAttribute(COLUMN_MARK, "");
    moveRow();
    measureRow();
  }
  // Looked at before the record's own listener: its Escape closes it and nothing else.
  function onEscape(e) {
    if (e.key === "Escape" && !page.querySelector('[data-testid="stDialog"],[role="listbox"]')) setFull(false);
  }
  function setFull(on) {
    if (on === !!inst.full) return;
    inst.full = on;
    panel.classList.toggle("zs-full", on);
    expand.textContent = text(on ? "zij.back" : "zij.expand");
    expand.title = text(on ? "zij.backTitle" : "zij.expandTitle");
    expand.setAttribute("aria-pressed", String(on));
    if (on) {
      page.addEventListener("keydown", onEscape, true);
      panels.addEventListener("scroll", moveRow, {passive: true});
      holdRow();
      holdStill();
    } else {
      page.removeEventListener("keydown", onEscape, true);
      panels.removeEventListener("scroll", moveRow);
      freeRow();
      freeStill();
      panels.style.paddingTop = "";
      panels.scrollTop = 0;
      fit();
    }
    world.kick();
  }
  inst.full = false;
  inst.setFull = setFull;
  expand.textContent = text("zij.expand");
  expand.title = text("zij.expandTitle");
  expand.setAttribute("aria-pressed", "false");
  expand.addEventListener("click", () => setFull(!inst.full));

  inst.apply = function (d) {
    inst.shown = d.shown;
    inst.anchors = d.anchors;
    inst.axes = d.axes;
    inst.chartLst = d.observer.lst;
    if (!inst.speeds) {
      inst.speeds = d.speeds;
      d.speeds.forEach((speed, at) => {
        const option = document.createElement("option");
        option.value = String(at);
        option.textContent = speed.minutes === 60 ? text("tw.hourPerSec") : text("tw.perSec", {n: speed.minutes});
        speedChoice.appendChild(option);
      });
      speedChoice.value = String(turn.speed);
    }
    if (d.context !== inst.context) {
      // A new chart stands at its own moment at once.
      if (inst.context !== null) { turn.playing = turn.moved = turn.back = false; turn.offset = 0; showTurn(); }
      inst.context = d.context;
      inst.desc = d.descriptor;
      inst.names = d.names;
      oneName.clear();
      Object.values(d.names).forEach((name) => { oneName.set(name, name.split(SECOND_FORM)[0]); });
      inst.byId = {};
      d.stars.concat(d.objects).forEach((r) => { inst.byId[r.id] = r; });
      const placed = tower.setSources(d.stars, d.objects, d.descriptor);
      if (placed.status !== "ok") throw Error("setSources " + placed.status);
      inst.drawFigures();
      STATS.sourcesSet++;
      if (!inst.mounted) {
        tower.show(true);
        tower.mountUI(ui);
        inst.mounted = true;
        ui.sources.appendChild(open);
      }
      tower.refreshUI();
      syncCoRising();
    }
    if (d.population !== inst.population) {
      inst.population = d.population;
      tower.refreshStarDisplay();
      tower.refreshUI();
    }
    if (d.angles_key !== inst.angles) {
      inst.angles = d.angles_key;
      tower.renderAngles(d.angles, {linked: true});
    }
    if (d.theme !== inst.theme) inst.setTheme(d);
    // The page's finder sends `turn` only in the run that opens a record, once for each.
    if (d.turn && d.turn.seq !== inst.turnSeq) holdTurn();
    Object.assign(inst.state, d.observer);
    turnTime();
    place();
    if (d.mode !== inst.mode) { inst.mode = d.mode; tower.setMode(d.mode, true); }
    if (d.turn && d.turn.seq !== inst.turnSeq) { inst.turnSeq = d.turn.seq; inst.turnTo(d.turn.id); }
    // The button stands on the sky, which is dark under both themes.
    panel.style.setProperty("--zs-ink", d.palette.colours.star);
    panel.style.setProperty("--zs-ground", d.palette.background);
    panel.style.setProperty("--zs-edge", d.palette.colours.steelDim);
    if (inst.full) { holdRow(); holdStill(); }
    fit();
    world.kick();
  };
  inst.drawFigures = function () {
    const figures = tower.setFigures(shape(FIGURES, inst.byId), shape(FIGURE_EXTRAS, inst.byId));
    if (figures.status !== "ok") throw Error("setFigures " + figures.status);
  };
  inst.setTheme = function (d) {
    inst.theme = d.theme;
    STATS.themes++;
    world.setColours(d.palette.colours);
    world.scene.background.set(d.palette.background);
    tower.invalidate();
    inst.drawFigures();
  };
  inst.turnTo = function (id) {
    STATS.turns++;
    if (tower.select(id).status !== "ok") return;
    const r = inst.byId[id];
    world.equGroup.updateMatrixWorld(true);
    const v = world.equLocal(r.ra, r.dec).applyMatrix4(world.equGroup.matrixWorld), len = v.length();
    if (TW.mode === "tower") {
      tower.setLook({az: Math.atan2(v.x, -v.z) * 180 / Math.PI, alt: Math.asin(Math.max(-1, Math.min(1, v.y / len))) * 180 / Math.PI});
    } else {
      world.cam.tth = world.cam.theta = Math.atan2(v.x, v.z);
      world.cam.tph = world.cam.phi = Math.max(0.12, Math.min(Math.PI - 0.12, Math.acos(Math.max(-1, Math.min(1, v.y / len)))));
    }
    world.placeCamera();
    world.kick();
  };
  inst.save = function () {
    const on = tower.layers(), held = {};
    FILTERS.forEach(([layer]) => { held[layer] = on[layer]; });
    SAVED = {theta: world.cam.theta, phi: world.cam.phi, r: world.cam.r, look: tower.getLook(), wanted: inst.wanted, layers: held, speed: turn.speed, back: turn.back, context: inst.context};
  };
  inst.restore = function () {
    if (!SAVED) return;
    const cam = world.cam;
    cam.theta = cam.tth = SAVED.theta;
    cam.phi = cam.tph = SAVED.phi;
    cam.r = cam.tr = SAVED.r;
    world.placeCamera();
    // The layers first: with the ground on, the view holds the look above it.
    tower.layers(SAVED.layers);
    inst.wanted = SAVED.wanted;
    tower.setLook(SAVED.look);
    holdLook();
    // The speed and the direction are the reader's; the turn itself ended with the page.
    // The direction is the reader's for the chart it was set on: a new chart, made on another page
    // meanwhile, comes back forward, as one made here does.
    turn.speed = SAVED.speed;
    turn.back = SAVED.back && SAVED.context === inst.context;
    speedChoice.value = String(turn.speed);
    showTurn();
  };
  inst.dispose = function () {
    inst.save();
    turn.playing = false;
    setFull(false);
    window.removeEventListener("resize", fit);
    ratioQuery.removeEventListener("change", onRatio);
    // The view's search holds a timer until its input is told; then the recipe,
    // whose order the view's own contract gives.
    const search = ui.sources.querySelector("input");
    if (search) search.dispatchEvent(new Event("input", {bubbles: true}));
    tower.show(false);
    world.setController(null);
    const released = new Set();
    const free = (r) => { if (r && !released.has(r)) { released.add(r); r.dispose(); } };
    roots.forEach((root) => {
      root.traverse((o) => {
        free(o.geometry);
        const materials = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
        materials.forEach((m) => { Object.keys(m).forEach((k) => { if (m[k] && m[k].isTexture) free(m[k]); }); free(m); });
      });
      if (root.parent) root.parent.remove(root);
    });
    world.renderer.forceContextLoss();
    world.dispose();
    panel.remove();
    inst.world = inst.tower = null;
    tower = null; world = null; roots = null;
  };
  inst.world = world;
  inst.tower = tower;
  inst.TW = TW;
  panel.zijSky = inst;
  return inst;
}

// The sky's labels in the house face. The view asks by name for a face (sphere-world.js,
// UIFONT) that this page serves as "Zij Interface", so they drew in the fallback. This lends
// the name to the page's own file, and holds the first mount until it has loaded, since a
// canvas does not redraw when a face arrives. Nothing else leans on it: to take it out, write
// `const labelFace = (go) => go();` for this block, and the labels return to the fallback.
let labelFaceState = null;
const labelFace = (go) => {
  if (typeof FontFace !== "function" || typeof document === "undefined" || !document.fonts || labelFaceState === "ready") return go();
  if (!labelFaceState) {
    const face = new FontFace("IBM Plex Sans Condensed", "url(/zij-font/zij-interface-400.ttf)");
    document.fonts.add(face);
    labelFaceState = Promise.race([face.load().catch(() => null), new Promise((done) => setTimeout(done, 3000))]).then(() => { labelFaceState = "ready"; });
  }
  labelFaceState.then(go);
};

// A sky that could not stand leaves its one sentence, and is not tried again in that place.
const UNABLE = new WeakSet();
function unable(parentElement, error, undo) {
  STATS.unable++;
  console.error("Sky:", error);
  undo.reverse().forEach((step) => {
    try { step(); }
    catch (e) { console.error("Sky:", e); }
  });
  HELD.delete(parentElement);
  UNABLE.add(parentElement);
  const note = document.createElement("p");
  note.className = "zs-unable";
  note.textContent = text("zij.unable");
  parentElement.appendChild(note);
}

export default function (component) {
  const {data, parentElement, setTriggerValue} = component;
  STATS.calls++;
  if (!data || !data.stars) return;
  labelFace(() => {
    if (UNABLE.has(parentElement)) return;
    let inst = HELD.get(parentElement), undo = [];
    const whole = () => [() => inst.panel.remove(), () => inst.dispose()];
    try {
      if (!inst) {
        if (!parentElement.isConnected) return;
        const started = performance.now();
        inst = mount(parentElement, data, undo);
        undo = whole();
        HELD.set(parentElement, inst);
        STATS.mounts++;
        inst.trigger = setTriggerValue;
        inst.apply(data);
        inst.restore();
        STATS.lastMountMs = performance.now() - started;
      } else {
        undo = whole();
        inst.trigger = setTriggerValue;
        inst.apply(data);
      }
    } catch (error) {
      unable(parentElement, error, undo);
    }
  });
  // Streamlit runs a superseded call's cleanup at once, with the component
  // standing: only a gone container takes the sky down.
  return function () {
    if (parentElement.isConnected) return;
    const held = HELD.get(parentElement);
    if (!held) return;
    HELD.delete(parentElement);
    STATS.disposes++;
    held.dispose();
  };
}
