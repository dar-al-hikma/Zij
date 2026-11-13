/* The Tower's view module (plan C08), lane B4: tower/view/tower-view.js, API schema 1; M4 opt-in host revision 4.
   One global, TowerView. TowerView.create(host) builds the Tower view inside the page's one renderer, scene and
   camera and returns the Tower API of C08. Everything it takes from the page comes through host (HOST below lists
   the members and their kinds; HANDOVER.md says what each is for); its only other globals are THREE and the
   browser's own (document, performance). The page embeds this file as its exact bytes in the script element whose id
   is tower-view, after the core and the catalogue
   (tests/sayyids-sphere/tower/embed.py), and never edits it there. Moved out of sayyids-sphere/index.html unchanged
   in behaviour by the view hand-over stage (28 Oct 2026); from then on lane B4 owns it.
   M2: null Johnson V has V5 size; source priorities come from host; label textures are made only for visible
   candidates; selection retains the base Points buffer. Proposed host additions (not yet page-integrated):
   setReveal(boolean) presents/hides the host's reveal legend, and sourcePriority(id, record) returns exactly
   host.TW_PRIO.target or host.TW_PRIO.other. Selection priority is the module's. See README-view.md and
   m2-v333/HOST-FINDINGS.md. Optional sourceLabelRank(id, record) orders source labels within a priority;
   it returns a non-negative integer, or every source ranks 0 when absent. Figure names follow all sources
   of the same priority. Optional sourceZoomHint(id, record) marks crowded sources for a clickable
   zoom marker. No page element, catalogue or astronomy global is read here. */
var TowerView = (function(){
  "use strict";   // as the page's own script is, where this module ran before the hand-over
  // copied from the page (C08's copied helpers, owner B4): the same constants and one-line helpers, byte for byte
  var D2R = Math.PI/180, R2D = 180/Math.PI, TAU = Math.PI*2;
  function norm360(x){ x = x % 360; return x < 0 ? x + 360 : x; }
  function clamp(x,a,b){ return x<a?a:(x>b?b:x); }
  // host's members and their kinds: objects the page never reassigns, passed by reference; a getter for a value the
  // page owns; the page's callbacks. A missing member, or one of the wrong kind, is refused loudly at create.
  var HOST = { S:"object", TW:"object", PREF:"object", TW_SHARED:"object", TW_PRIO:"object", C:"object", cam:"object",
    camera:"object", scene:"object", renderer:"object", view:"object", equGroup:"object", eclGroup:"object",
    reduced:"function", T:"function", label:"function", fmtZod:"function", eclV:"function", equLocal:"function",
    twActiveEcl:"function", twName:"function", twCopy:"function", twFinite:"function", kick:"function",
    applyVisibility:"function", syncToggles:"function", twSyncUI:"function",
    setReveal:"function", sourcePriority:"function" };
  function create(host){
    var k;
    if(!host || typeof host !== "object") throw new TypeError("TowerView.create: host must be an object");
    for(k in HOST) if(typeof host[k] !== HOST[k] || host[k] === null) throw new TypeError("TowerView.create: host." + k + " is missing or not a" + (HOST[k] === "object" ? "n object" : " function"));
    if(typeof host.sourceLabelRank !== "undefined" && typeof host.sourceLabelRank !== "function") throw new TypeError("TowerView.create: host.sourceLabelRank is not a function");
    if("sourceZoomHint" in host && typeof host.sourceZoomHint !== "function") throw new TypeError("TowerView.create: host.sourceZoomHint is not a function");
    var S = host.S, TW = host.TW, PREF = host.PREF, TW_SHARED = host.TW_SHARED, TW_PRIO = host.TW_PRIO, C = host.C,
      cam = host.cam, camera = host.camera, scene = host.scene, renderer = host.renderer, view = host.view,
      equGroup = host.equGroup, eclGroup = host.eclGroup, T = host.T, label = host.label, fmtZod = host.fmtZod,
      eclV = host.eclV, equLocal = host.equLocal, twActiveEcl = host.twActiveEcl, twName = host.twName,
      twCopy = host.twCopy, twFinite = host.twFinite, kick = host.kick, applyVisibility = host.applyVisibility,
      syncToggles = host.syncToggles, twSyncUI = host.twSyncUI;
    var root = new THREE.Group(), equRoot = new THREE.Group(), eclRoot = new THREE.Group();
    root.visible = equRoot.visible = eclRoot.visible = false;
    scene.add(root); equGroup.add(equRoot); eclGroup.add(eclRoot);
    // the Tower's own layers; ground, horizon, ecliptic, meridian and the cardinal points are the page's (PREF)
    var TP = { stars:true, objects:true, figures:true, labels:true, foot:true, coRising:false };
    var SHARED = TW_SHARED;
    var look = { az:90, alt:12, fov:70 }, ORBIT_FOV = 38, ORBIT_NEAR = 0.05, TOWER_NEAR = 0.01, LABEL_PX = 13;
    var transition = null, notify = function(){};
    var stars = [], objects = [], records = {}, index = {}, descriptor = null, figures = [], extras = [], segments = [];
    var state = { lat:S.lat, lst:S.lst, obl:S.obl, axes:null, linked:false, contextId:null };
    var coLon = null, dirty = true, sourcesDirty = true, figuresDirty = true,
      stats = { frames:0, transitionFrames:0, rebuilds:0, pointBuilds:0, figureBuilds:0 };
    var U = { groundOn:{ value:false } };
    var points = null, figureMesh = null, guideWorld = null, guideEcl = null, ground = null, footGroup = null;
    var markers = [], registry = [], activeLabels = [], foot = null, ascEntry = null, ascMarker = null, legendOn = null;
    var ZOOM_MARKER_OPACITY = 1;
    var SOURCE_LABEL_OFFSETS = [[1,0],[1,-1],[-1,0],[1,1],[-1,-1],[-1,1],[0,-1],[0,1]];
    var zoomTextures = Object.create(null), zoomSprites = [], zoomMarkers = [], zoomPlacements = [], zoomMarkersDropped = 0, hasZoomHints = false;
    var zoomWalk = null;
    var _w = new THREE.Vector3(), _c = new THREE.Vector3(), _q = new THREE.Quaternion(), _e = new THREE.Euler(0, 0, 0, "YXZ");

    var VS_PTS = "attribute float size; attribute vec3 color; varying vec3 vColor; varying float vAlt;"
      + "void main(){ vColor = color; vAlt = (modelMatrix*vec4(position,1.0)).y;"
      + " gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); gl_PointSize = size; }";
    var FS_PTS = "precision mediump float; uniform bool groundOn; varying vec3 vColor; varying float vAlt;"
      + "void main(){ if(groundOn && vAlt < 0.0) discard; float r = length(gl_PointCoord - vec2(0.5)); if(r > 0.5) discard;"
      + " vec3 c = vColor; float a = smoothstep(0.5, 0.15, r);"
      + " if(vAlt < 0.0){ c = vec3(dot(c, vec3(.299,.587,.114))); a *= .4; } gl_FragColor = vec4(c, a); }";
    var VS_LN = "attribute vec3 color; varying vec3 vColor; varying float vAlt;"
      + "void main(){ vColor = color; vAlt = (modelMatrix*vec4(position,1.0)).y; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }";
    var FS_LN = "precision mediump float; uniform bool groundOn; varying vec3 vColor; varying float vAlt;"
      + "void main(){ if(groundOn && vAlt < 0.0) discard; vec3 c = vColor; float a = 1.0;"
      + " if(vAlt < 0.0){ c = vec3(dot(c, vec3(.299,.587,.114))); a = .4; } gl_FragColor = vec4(c, a); }";

    function ok(){ return { status:"ok" }; }
    function bad(s){ return { status:s }; }
    // membership is own membership (C08, the C08 repair F02): a name inherited from Object.prototype, such as
    // "toString", is no source ID and no layer name, and a source ID is a string
    function has(o, k){ return Object.prototype.hasOwnProperty.call(o, k); }
    function known(id){ return typeof id === "string" && has(records, id); }
    function pref(k){ return SHARED[k] ? !!PREF[k] : !!TP[k]; }
    function dispose(o){
      if(!o) return;
      o.traverse(function(c){ if(c.geometry) c.geometry.dispose(); if(c.material){ if(c.material.map) c.material.map.dispose(); c.material.dispose(); } });
      if(o.parent) o.parent.remove(o);
    }
    // ---- camera poses (C09): the tower camera stands at the origin and is aimed by yaw and pitch, never by lookAt
    function poseTower(){
      _e.set(look.alt*D2R, -look.az*D2R, 0, "YXZ");
      return { p:new THREE.Vector3(0, 0, 0), q:new THREE.Quaternion().setFromEuler(_e), fov:look.fov, near:TOWER_NEAR };
    }
    function poseOrbit(){
      var sp = Math.sin(cam.tph), o = new THREE.Object3D();
      o.position.set(cam.tr*sp*Math.sin(cam.tth), cam.tr*Math.cos(cam.tph), cam.tr*sp*Math.cos(cam.tth));
      o.lookAt(0, 0, 0);    // an Object3D's lookAt points its +Z; a camera looks along −Z, so turn half round
      var c = new THREE.PerspectiveCamera(); c.position.copy(o.position); c.lookAt(0, 0, 0);
      return { p:c.position.clone(), q:c.quaternion.clone(), fov:ORBIT_FOV, near:ORBIT_NEAR };
    }
    function currentPose(){ return { p:camera.position.clone(), q:camera.quaternion.clone(), fov:camera.fov, near:camera.near }; }
    function assignPose(p){
      camera.position.copy(p.p); camera.quaternion.copy(p.q);
      if(camera.fov !== p.fov || camera.near !== p.near){ camera.fov = p.fov; camera.near = p.near; camera.updateProjectionMatrix(); }
      camera.updateMatrixWorld(true);
    }
    function setMode(m, immediate){
      if(m !== "tower" && m !== "orbit") return bad("unknownMode");
      if(m === "tower" && !TW.applied) return bad("noChart");      // the Tower stands in a chart's sky
      if(m === TW.mode && !transition) return ok();
      if(m !== TW.mode) zoomWalk = null;
      var from = currentPose();
      TW.mode = m;
      if(host.reduced() || immediate){
        transition = null;
        if(m === "orbit"){ cam.r = cam.tr; cam.theta = cam.tth; cam.phi = cam.tph; }
        assignPose(m === "tower" ? poseTower() : poseOrbit());
      } else transition = { from:from, start:performance.now(), duration:900 };
      dirty = true; applyVisibility(); kick();
      return ok();
    }
    function setLook(l){
      if(!l || !twFinite(l.az) || !twFinite(l.alt) || (l.fov != null && !twFinite(l.fov))) return bad("invalidLook");
      look = { az:norm360(l.az), alt:clamp(l.alt, PREF.ground ? -10 : -90, 90), fov:clamp(l.fov == null ? look.fov : l.fov, 20, 100) };
      kick(); return ok();
    }
    // the one camera owner: while the Tower holds the view or a transition runs, it places the camera; returns whether it is still moving
    function ownsCamera(){ return TW.mode === "tower" || !!transition; }
    function tick(now){
      if(transition){
        var t = clamp((now - transition.start)/transition.duration, 0, 1), e = t*t*(3 - 2*t), f = transition.from;
        var to = TW.mode === "tower" ? poseTower() : poseOrbit();
        // the last frame lands exactly on the target pose, not on an interpolation of it
        assignPose(t >= 1 ? to : { p:f.p.clone().lerp(to.p, e), q:f.q.clone().slerp(to.q, e), fov:f.fov + (to.fov - f.fov)*e, near:f.near + (to.near - f.near)*e });
        stats.transitionFrames++;
        if(t >= 1){
          transition = null;
          if(TW.mode === "orbit"){ cam.r = cam.tr; cam.theta = cam.tth; cam.phi = cam.tph; }
          return false;
        }
        return true;
      }
      if(TW.mode === "tower") assignPose(poseTower());
      return false;
    }
    // ---- sources: one paired batch of stars and objects, with one place descriptor (C08)
    function validDesc(d){ return !!d && typeof d.mode === "string" && twFinite(d.epoch) && typeof d.contextId === "string"; }
    function sameDesc(a, b){ return !!a && !!b && a.mode === b.mode && a.epoch === b.epoch && a.contextId === b.contextId; }
    // a batch is an array of ordinary records (K02): anything else is refused before any change; an ID that names
    // an Object.prototype member is refused as it always was, now explicitly rather than as a false repeat (F02)
    function checkRows(rows){
      var seen = {}, i, r;
      if(!Array.isArray(rows)) return false;
      for(i = 0; i < rows.length; i++){
        r = rows[i];
        if(!r || typeof r !== "object" || typeof r.id !== "string" || r.id in Object.prototype || has(seen, r.id) || !twFinite(r.ra) || !twFinite(r.dec) || r.dec < -90 || r.dec > 90) return false;
        seen[r.id] = true;
      }
      return true;
    }
    function reindex(){
      records = {}; index = {};
      stars.concat(objects).forEach(function(r, i){ records[r.id] = r; index[r.id] = i; });
    }
    // what setStars/setObjects would answer, without changing anything (exposed for tests)
    function checkDescriptor(which, d){
      if(!validDesc(d)) return bad("invalidPlaceDescriptor");
      var other = which === "stars" ? objects : stars;
      if(descriptor && other.length && !sameDesc(d, descriptor)) return bad("placeDescriptorMismatch");
      return ok();
    }
    function setRecords(which, rows, d){
      var c = checkDescriptor(which, d); if(c.status !== "ok") return c;
      // one ID, one record, across both batches (K01): a row whose ID the retained other batch holds is refused
      if(!checkRows(rows) || !checkRows(rows.concat(which === "stars" ? objects : stars))) return bad("invalidRecord");
      descriptor = twCopy(d);
      if(which === "stars") stars = twCopy(rows); else objects = twCopy(rows);
      reindex(); afterRecords(); return ok();
    }
    // Lane B4 left the replacement of both batches on a change of context as an open question (bridge.md).
    // Settled here: one call replaces both batches together under one descriptor, or refuses and changes
    // nothing, so two epochs are never drawn together; setStars/setObjects alone keep B4's refusal.
    function setSources(st, ob, d){
      if(!validDesc(d)) return bad("invalidPlaceDescriptor");
      if(!checkRows(st) || !checkRows(ob) || !checkRows((st || []).concat(ob || []))) return bad("invalidRecord");
      descriptor = twCopy(d); stars = twCopy(st); objects = twCopy(ob);
      reindex(); afterRecords(); return ok();
    }
    function afterRecords(){
      zoomWalk = null;
      if(TW.selected !== null && !known(TW.selected)){ TW.selected = null; uiEntry = null; highlighted = {}; notify(null); }
      syncStarDisplay();
      sourcesDirty = true; dirty = true; kick();
    }
    function setFigures(f, x){
      var unknown = [];
      (f || []).concat(x || []).forEach(function(g){ (g.lines || []).concat(g.extLines || []).forEach(function(line){ line.forEach(function(id){ if(!known(id)) unknown.push(id); }); }); });
      if(unknown.length) return { status:"unknownId", ids:unknown };
      figures = twCopy(f || []); extras = twCopy(x || []); figuresDirty = true; dirty = true; kick(); return ok();
    }
    function select(id){
      if(id !== null && !known(id)) return bad("unknownId");
      if(zoomWalk){
        if(zoomWalk.pending && zoomWalk.markerPick && id === zoomWalk.last) zoomWalk.pending = false;
        else zoomWalk = null;
      }
      if(id === TW.selected) return ok();
      TW.selected = id; uiEntry = null; highlighted = {}; dirty = true; notify(id); kick(); return ok();
    }
    // Name choices reveal a source once. Direct select and sky/marker picks never do this.
    var nameChoiceTimer = null;
    function cancelNameChoice(){
      if(nameChoiceTimer !== null){ clearTimeout(nameChoiceTimer); nameChoiceTimer = null; }
    }
    function showNamedSource(id){
      if(!known(id) || TW.selected !== id || !TW.applied) return;
      var r = records[id], patch = {};
      // Batch membership also covers ordinary C08 object rows without an optional kind.
      if(!pref(index[id] < stars.length ? "stars" : "objects")) patch[index[id] < stars.length ? "stars" : "objects"] = true;
      if(!sourceShown(r)) patch[r.kind ? "objects" : "stars"] = true;
      if(!TP.labels) patch.labels = true;
      if(Object.keys(patch).length) layers(patch);
      equGroup.updateMatrixWorld(true);
      var world = equLocal(r.ra,r.dec).applyMatrix4(equGroup.matrixWorld);
      if(TW.mode === "tower" && PREF.ground && world.y < 0) layers({ground:false});
      camera.updateMatrixWorld(true);
      if(project(world).visible){
        if(!transition) return;
        // An in-flight turn must not carry a new visible choice out of frame at its endpoint.
        var target = TW.mode === "tower" ? poseTower() : poseOrbit(), preview = camera.clone();
        preview.position.copy(target.p); preview.quaternion.copy(target.q); preview.fov = target.fov; preview.near = target.near;
        preview.updateProjectionMatrix(); preview.updateMatrixWorld(true);
        var projected = world.clone().project(preview), depth = -world.clone().applyMatrix4(preview.matrixWorldInverse).z;
        if(depth > preview.near && projected.z >= -1 && projected.z <= 1 && Math.abs(projected.x) <= 1 && Math.abs(projected.y) <= 1) return;
      }
      var from = currentPose(), length = world.length();
      if(TW.mode === "tower") setLook({az:Math.atan2(world.x,-world.z)*R2D,alt:Math.asin(clamp(world.y/length,-1,1))*R2D});
      else {
        cam.tth = Math.atan2(world.x,world.z);
        cam.tph = clamp(Math.acos(clamp(world.y/length,-1,1)),0.12,Math.PI-0.12);
      }
      if(host.reduced()){
        transition = null;
        if(TW.mode === "orbit"){ cam.r = cam.tr; cam.theta = cam.tth; cam.phi = cam.tph; }
        assignPose(TW.mode === "tower" ? poseTower() : poseOrbit());
      } else transition = {from:from,start:performance.now(),duration:900};
      kick();
    }
    function chooseNamedSource(id, wait){
      zoomWalk = null;
      cancelNameChoice();
      var result = select(id);
      if(result.status !== "ok") return result;
      if(wait) nameChoiceTimer = setTimeout(function(){ nameChoiceTimer = null; showNamedSource(id); },250);
      else showNamedSource(id);
      refreshUI(); return result;
    }
    function setCoRising(lon){
      if(lon !== null && !twFinite(lon)) return bad("invalidLongitude");
      if(lon !== coLon){ coLon = lon; dirty = true; kick(); }
      return ok();
    }
    function update(s){
      if(!s || !twFinite(s.lat) || !twFinite(s.lst) || !twFinite(s.obl)) return bad("invalidState");
      if(zoomWalk && (state.lat !== s.lat || state.lst !== s.lst || state.obl !== s.obl)) zoomWalk = null;
      state.lat = s.lat; state.lst = s.lst; state.obl = s.obl; state.axes = s.axes || null;
      state.linked = !!s.linked; state.contextId = s.contextId || null;
      return ok();
    }
    function layers(p){
      if(!p){ var out = twCopy(TP); Object.keys(SHARED).forEach(function(k){ out[k] = !!PREF[k]; }); return out; }
      var keys = Object.keys(p), i;
      for(i = 0; i < keys.length; i++) if(!has(SHARED, keys[i]) && !has(TP, keys[i])) return bad("unknownLayer");
      if(zoomWalk) for(i = 0; i < keys.length; i++) if(pref(keys[i]) !== !!p[keys[i]]){ zoomWalk = null; break; }
      keys.forEach(function(k){ if(has(SHARED, k)) PREF[k] = !!p[k]; else TP[k] = !!p[k]; });
      if(PREF.ground && look.alt < -10) look.alt = -10;
      dirty = true; applyVisibility(); syncToggles(); twSyncUI(); kick(); return ok();
    }
    // ---- M4 UI. Resolved view models, scientific values and all copy belong to the host.
    // This opt-in boundary leaves C08's existing ordinary-input host domain intact. Calling it
    // without the proposed M4 members is an error, never an inert control. See m4-v3314/HOST.md.
    var ui = null, uiEntry = null, highlighted = {}, uiLast = {}, uiForm = null;
    // C09 v3.3.15: the host owns the significant IDs and reader setting. Every base
    // point and figure remains drawn; this map gates source names, picking and list.
    // Existing unmounted C08 hosts retain their documented legacy full-list domain.
    var display = { mode:typeof host.starDisplay === "function" ? "significant" : "full", status:"unavailable", available:typeof host.starDisplay !== "function", count:0, missing:[] }, displayIds = {};
    function syncStarDisplay(){
      if(typeof host.starDisplay !== "function"){
        display = {mode:"full",status:"legacyHost",available:true,count:stars.length+objects.length,missing:[]}; return ok();
      }
      var value = host.starDisplay(), map = {}, missing = [], mode;
      if(!value || typeof value !== "object") return bad("invalidStarDisplay");
      mode = value.mode == null ? "significant" : value.mode;
      if((mode !== "significant" && mode !== "full") || typeof value.status !== "string") return bad("invalidStarDisplay");
      if(value.status === "ok"){
        if(!Array.isArray(value.ids)) return bad("invalidStarDisplay");
        for(var i=0;i<value.ids.length;i++){
          var id=value.ids[i];
          if(typeof id !== "string" || id in Object.prototype || has(map,id)) return bad("invalidStarDisplay");
          map[id]=true; if(!known(id)) missing.push(id);
        }
      } else if(value.ids !== null) return bad("invalidStarDisplay");
      var status = missing.length ? "unknownId" : value.status;
      displayIds = map;
      display = {mode:mode,status:status,available:mode === "full" || status === "ok",count:mode === "full" ? stars.length+objects.length : Object.keys(map).length,missing:missing};
      if(zoomWalk) checkZoomWalk();
      return display.available ? ok() : bad(status);
    }
    function displayAllows(id){ return display.mode === "full" || (display.available && has(displayIds,id)); }
    function refreshStarDisplay(){
      var result = syncStarDisplay();
      if(result.status === "invalidStarDisplay") return result;
      if(ui) refreshSources(); kick(); return result;
    }
    var uiStats = { cardMs:0, anglesMs:0, listMs:0, formMs:0 };
    var UI_HOST = ["uiText", "uiFormat", "sourceEntries", "entryView", "sourceDetails",
      "alternativeIdentifications", "civilFields", "validateCivil", "applyCivil", "onCivilInput", "onEntrySelect", "starDisplay"];
    function utext(key, args){
      var s = host.uiText(key, args || {});
      if(typeof s !== "string" || s === key) throw new TypeError("TowerView: untranslated UI key " + key);
      return s;
    }
    function ufmt(value, kind){
      if(value == null) return utext("m4.unavailable");
      var s = host.uiFormat(value, kind);
      if(typeof s !== "string") throw new TypeError("TowerView: host.uiFormat must return a string");
      return s;
    }
    function node(tag, text, cls){
      var el = document.createElement(tag);
      if(text != null) el.textContent = text;
      if(cls) el.className = cls;
      return el;
    }
    function putRow(dl, key, value){
      dl.appendChild(node("dt", utext(key)));
      var dd = node("dd"); dd.style.overflowWrap = "anywhere";
      if(value && typeof value === "object" && value.nodeType) dd.appendChild(value); else dd.textContent = value;
      dl.appendChild(dd); return dd;
    }
    function statusText(status){ return utext("m4.status." + (status || "unavailable")); }
    // Card parts are optional independently. The host supplies the separator verbatim;
    // templates wrap already joined parts and never own a leading/trailing separator.
    function cardParts(parts){
      return parts.filter(function(p){ return typeof p === "string" && p.trim().length > 0; });
    }
    function cardText(parts){ return cardParts(parts).join(utext("m4.separator")); }
    function memberDetails(m){
      var certainty = m.certainty ? utext("m4.certainty." + m.certainty) : "",
        role = m.role ? utext("m4.role." + m.role) : "";
      return utext("m4.memberDetails", {certainty:certainty,role:role,parts:cardText([certainty,role])});
    }
    function appendCardPart(parent, part){
      var text = typeof part === "string" ? part : part.textContent;
      if(!cardParts([text]).length) return;
      if(cardParts([parent.textContent]).length) parent.appendChild(node("span", utext("m4.separator")));
      parent.appendChild(typeof part === "string" ? node("span", part) : part);
    }
    function listText(list, render){
      if(!Array.isArray(list)) return node("p", utext("m4.unavailable"));
      if(!list.length) return node("p", utext("m4.none"));
      var ul = node("ul"); list.forEach(function(v){ var li = node("li"); li.appendChild(render(v)); ul.appendChild(li); }); return ul;
    }
    function replaceUI(key, content){
      // Avoid rewriting a focused card button and announcing unchanged content on animation frames.
      var signature = content.outerHTML;
      if(uiLast[key] !== signature){
        var focused = ui[key].contains(document.activeElement) ? document.activeElement : null;
        var token = focused && focused.dataset.focusToken;
        ui[key].replaceChildren(content); uiLast[key] = signature;
        if(token) Array.prototype.some.call(ui[key].querySelectorAll("button"),function(button){if(button.dataset.focusToken === token){button.focus();return true;}return false;});
      }
    }
    function namedMember(m){
      var b = node("button", twName(m.id)); b.type = "button"; b.className = "btn"; b.dataset.focusToken = m.id;
      b.addEventListener("click", function(){ uiEntry = null; chooseNamedSource(m.id,false); });
      return b;
    }
    function presentEntry(e, alt){
      var v = host.entryView(e, alt, TW.selected);
      if(!v || typeof v.id !== "string" || (!Array.isArray(v.sets) || !Array.isArray(v.selectedMembership))) throw new TypeError("TowerView: invalid entry view");
      v.sets.forEach(function(set){ if(!Array.isArray(set)) throw new TypeError("TowerView: invalid identification set");
        set.forEach(function(m){ if(!known(m.id)) throw new TypeError("TowerView: entry member is not a supplied source " + m.id); }); });
      return v;
    }
    function syncHighlights(sets){
      var next = {};
      (sets || []).forEach(function(set){ set.forEach(function(m){ var id = typeof m === "string" ? m : m.id;
        if(!known(id)) throw new TypeError("TowerView: identification is not a supplied source " + id);
        next[id] = true; }); });
      if(JSON.stringify(Object.keys(next).sort()) !== JSON.stringify(Object.keys(highlighted).sort())){
        highlighted = next; dirty = true; kick();
      }
    }
    function entryCard(v){
      var section = node("section"), choose = node("button", utext("m4.category." + v.category));
      choose.type = "button"; choose.className = "btn"; choose.dataset.focusToken = v.id; choose.setAttribute("aria-pressed", uiEntry === v.id ? "true" : "false");
      choose.addEventListener("click", function(){
        uiEntry = v.id; syncHighlights(v.sets);
        host.onEntrySelect(v.id, twCopy(v.sets.map(function(set){ return set.map(function(m){ return m.id; }); })));
        renderCard();
      }); section.appendChild(choose);
      var dl = node("dl");
      putRow(dl, "m4.relation", utext("m4.relation." + v.relation));
      putRow(dl, "m4.scope", utext("m4.scope." + v.scope));
      putRow(dl, "m4.certainty", utext("m4.certainty." + v.certainty));
      putRow(dl, "m4.membership", listText(v.selectedMembership, function(m){
        return node("span", memberDetails(m));
      }));
      (v.qualifications || []).forEach(function(q){ putRow(dl, "m4.qualification", utext("m4.qualification." + q)); });
      section.appendChild(dl);
      v.sets.forEach(function(set, i){
        section.appendChild(node("h6", utext("m4.memberSet", {number:ufmt(i + 1,"integer")})));
        section.appendChild(listText(set, function(m){
          var span = node("span"); appendCardPart(span,namedMember(m));
          appendCardPart(span,memberDetails(m));
          return span;
        }));
      });
      return section;
    }
    function renderCard(){
      if(!ui) throw new TypeError("TowerView: mountUI must precede renderCard");
      var start = performance.now(), body = node("div");
      if(!TW.applied || !known(TW.selected)){
        syncHighlights([]); body.appendChild(node("p", utext("m4.noSelection"))); replaceUI("card", body);
        uiStats.cardMs = performance.now() - start; return ok();
      }
      var id = TW.selected, alt = host.alternativeIdentifications();
      if(typeof alt !== "boolean") throw new TypeError("TowerView: alternativeIdentifications must return boolean");
      var detail = host.sourceDetails(id, alt), result = host.sourceEntries(id);
      if(!detail || !result || typeof result.status !== "string") throw new TypeError("TowerView: invalid card host result");
      var entries = result.status === "ok" && Array.isArray(result.entries) ? result.entries.map(function(e){ return presentEntry(e, alt); }) : null;
      body.appendChild(node("h5", twName(id)));
      var caveat = !!detail.caveat || !!(entries && entries.some(function(v){ return v.caveat; }));
      if(caveat) body.appendChild(node("p", utext("m4.sourcesDisagree"), "tw-caveat"));
      var selected = entries && entries.filter(function(v){ return v.id === uiEntry; })[0];
      if(!selected) uiEntry = null;
      syncHighlights(selected ? selected.sets : (detail.identificationSets || [[id]]));
      var dl = node("dl");
      putRow(dl,"m4.kind",utext("m4.kind." + detail.kind));
      putRow(dl,"m4.place",utext("m4.pair",{first:ufmt(detail.ra,"degrees"),second:ufmt(detail.dec,"degrees")}));
      putRow(dl,"m4.horizon",utext("m4.pair",{first:ufmt(detail.az,"degrees"),second:ufmt(detail.alt,"degrees")}));
      putRow(dl,"m4.ecliptic",utext("m4.pair",{first:ufmt(detail.lon,"zodiac"),second:ufmt(detail.lat,"degrees")}));
      if(detail.eclipticMoved) putRow(dl,"m4.geometry",utext("m4.eclipticMoved"));
      putRow(dl,detail.kind === "star" ? "m4.v" : "m4.integratedV",detail.vmag == null ? utext("m4.vMissing") : ufmt(detail.vmag,"magnitude"));
      if(detail.bv != null) putRow(dl,"m4.bv",ufmt(detail.bv,"decimal"));
      putRow(dl,"m4.motion",utext("m4.motion." + detail.motion));
      // Longitude and state remain present when ground, foot or label layers are hidden.
      var fp = detail.foot || {};
      putRow(dl,"m4.footLongitude",ufmt(fp.lon,"zodiac"));
      putRow(dl,"m4.footState",utext("m4.footState." + (fp.state || "unavailable")));
      putRow(dl,"m4.footAltitude",ufmt(fp.alt,"degrees"));
      ["rise","culm","set","anti"].forEach(function(kind){
        putRow(dl,"m4.event." + kind,listText(detail.events && detail.events[kind],function(e){ return node("span",ufmt(e,"event")); }));
        putRow(dl,"m4.co." + kind,ufmt(detail.co && detail.co[kind],"zodiac"));
      });
      if(detail.events){
        putRow(dl,"m4.horizonStatus",statusText(detail.events.horizonStatus));
        putRow(dl,"m4.meridianStatus",statusText(detail.events.meridianStatus));
      }
      if(detail.day != null) putRow(dl,"m4.eventDay",ufmt(detail.day,"civilDay"));
      body.appendChild(dl);
      body.appendChild(node("h6",utext("m4.entries")));
      if(entries) entries.forEach(function(v){ body.appendChild(entryCard(v)); });
      else body.appendChild(node("p",utext("m4.unavailable")));
      if(entries && !entries.length) body.appendChild(node("p",utext("m4.none")));
      body.appendChild(node("h6",utext("m4.natures")));
      body.appendChild(listText(detail.natures,function(n){
        var content = node("span");
        if(n.sourceLabelKey) appendCardPart(content,utext(n.sourceLabelKey));
        appendCardPart(content, n.nature ? utext("m4.naturePair",{planets:cardText(n.nature.map(function(p){return p ? utext("m4.planet."+p) : "";}))}) : (n.presence ? utext("m4.presence."+n.presence) : ""));
        return content;
      }));
      body.appendChild(node("h6",utext("m4.associations")));
      body.appendChild(listText(detail.associations,function(a){
        var figure = a.figureId ? host.figureName(a.figureId) : "", number = a.number == null ? "" : ufmt(a.number,"pnum"),
          certainty = a.certainty ? utext("m4.certainty."+a.certainty) : "", source = a.sourceLabelKey ? utext(a.sourceLabelKey) : "";
        var span = node("span",utext("m4.association",{figure:figure,number:number,certainty:certainty,source:source,parts:cardText([figure,number,certainty,source])}));
        if(a.caveat && !caveat){ caveat = true; body.insertBefore(node("p",utext("m4.sourcesDisagree"),"tw-caveat"),body.children[1]); }
        return span;
      }));
      replaceUI("card",body); uiStats.cardMs = performance.now() - start; return ok();
    }
    function renderAngles(result, options){
      if(!ui) throw new TypeError("TowerView: mountUI must precede renderAngles");
      var start = performance.now(), body = node("div"), linked = !!(options && options.linked);
      body.appendChild(node("h5",utext("m4.angles")));
      if(!linked) body.appendChild(node("p",utext("m4.snapshotDeltasDisabled")));
      body.appendChild(node("p",statusText(result && result.status)));
      [["horizon",["asc","dsc"]],["meridian",["mc","ic"]]].forEach(function(family){
        var section = node("section"); section.appendChild(node("h6",utext("m4.family."+family[0])));
        family[1].forEach(function(angle){
          var block = result && result[angle], group = node("section");
          group.appendChild(node("h6",utext("m4.angle."+angle)));
          group.appendChild(node("p",utext("m4.longitudeCriterion")));
          group.appendChild(listText(block && block.byLongitude,function(r){return node("span",utext("m4.longitudeRow",{name:twName(r.id),delta:ufmt(r.dlon,"signedDegrees")}));}));
          group.appendChild(node("p",utext("m4.crossingCriterion")));
          group.appendChild(node("p",statusText(block && block.crossingStatus)));
          group.appendChild(listText(block && block.crossing,function(r){return node("span",utext(linked ? "m4.crossingRow" : "m4.crossingSnapshotRow",{
            name:twName(r.id),event:utext("m4.event."+r.eventType),delta:linked ? ufmt(r.dtMinutes,"minutes") : utext("m4.nowUnavailable")}));}));
          if(block && block.refused && block.refused.length){
            group.appendChild(node("p",utext("m4.refusedSources")));
            group.appendChild(listText(block.refused,function(id){return node("span",twName(id));}));
          }
          section.appendChild(group);
        }); body.appendChild(section);
      });
      replaceUI("angles",body); uiStats.anglesMs = performance.now() - start; return ok();
    }
    function refreshSources(){
      if(!ui) throw new TypeError("TowerView: mountUI must precede refreshSources");
      var start = performance.now(), search = ui.sources.querySelector("input"), list = ui.sources.querySelector("select"), q = search.value.trim().toLocaleLowerCase();
      var focused = document.activeElement === list, old = list.value, fragment = document.createDocumentFragment();
      stars.concat(objects).forEach(function(r){
        if(!displayAllows(r.id)) return;
        var name = twName(r.id);
        if((name + " " + r.id).toLocaleLowerCase().indexOf(q) < 0) return;
        var option = node("option",name); option.value = r.id; fragment.appendChild(option);
      });
      list.disabled = !display.available;
      list.replaceChildren(fragment); list.value = known(TW.selected) && Array.prototype.some.call(list.options,function(o){return o.value === TW.selected;}) ? TW.selected : old;
      if(list.selectedIndex < 0 && list.options.length) list.selectedIndex = 0;
      ui.sources.querySelector("output").textContent = display.available ? utext("m4.sourceCount",{count:ufmt(list.options.length,"integer"),total:ufmt(stars.length+objects.length,"integer")}) : utext("m4.significantUnavailable");
      if(focused) list.focus(); uiStats.listMs = performance.now() - start; return ok();
    }
    function rawCivil(){ var values = {}; uiForm.fields.forEach(function(name){values[name] = uiForm.inputs[name].value;}); return values; }
    function refreshFormMessage(){
      var result = uiForm.lastResult;
      if(result) uiForm.message.textContent = utext(result.messageKey || "m4.form.message." + result.status);
    }
    function formMessage(result){
      uiForm.lastResult = result;
      refreshFormMessage();
      uiForm.fields.forEach(function(name){uiForm.inputs[name].setAttribute("aria-invalid",result.field === name ? "true" : "false");});
    }
    function setCivilFields(values, force){
      if(!uiForm) throw new TypeError("TowerView: mountUI must precede setCivilFields");
      if(!force && (uiForm.draft || uiForm.form.contains(document.activeElement))) return bad("editing");
      uiForm.fields.forEach(function(name){ if(typeof values[name] !== "string") throw new TypeError("TowerView: civil field must be a string"); uiForm.inputs[name].value = values[name]; });
      uiForm.draft = false; return ok();
    }
    function mountUI(containers){
      UI_HOST.concat(["figureName"]).forEach(function(name){if(typeof host[name] !== "function") throw new TypeError("TowerView.mountUI: host."+name+" is missing or not a function");});
      ["card","angles","form","sources"].forEach(function(name){if(!containers || !containers[name] || containers[name].nodeType !== 1) throw new TypeError("TowerView.mountUI: missing container " + name);});
      if(ui) throw new TypeError("TowerView: UI already mounted");
      var start = performance.now(), displayResult=syncStarDisplay();
      if(displayResult.status === "invalidStarDisplay") throw new TypeError("TowerView.mountUI: invalid host.starDisplay result");
      ui = containers;
      Object.keys(containers).forEach(function(name){containers[name].style.minWidth = "0";});
      var sourceBox = node("div"), searchLabel = node("label",utext("m4.search")), search = node("input"); search.type = "search"; search.autocomplete = "off";
      search.style.width = "100%"; search.style.boxSizing = "border-box"; searchLabel.appendChild(search); sourceBox.appendChild(searchLabel);
      var listLabel = node("label",utext("m4.sourceList")), list = node("select"); list.size = 8; list.style.width = "100%"; list.style.maxWidth = "100%";
      listLabel.appendChild(list); sourceBox.appendChild(listLabel);
      var count = node("output"); count.setAttribute("aria-live","polite"); sourceBox.appendChild(count); ui.sources.replaceChildren(sourceBox);
      var listArrows = false, listPointerChange = false;
      search.addEventListener("input",function(){cancelNameChoice();refreshSources();});
      search.addEventListener("keydown",function(e){if(e.key === "ArrowDown"){e.preventDefault();list.focus();}else if(e.key === "Enter" && list.value){e.preventDefault();chooseNamedSource(list.value,false);}});
      list.addEventListener("pointerdown",function(){listArrows = false;listPointerChange = false;});
      list.addEventListener("change",function(){if(list.value){listPointerChange = !listArrows;chooseNamedSource(list.value,listArrows);}});
      list.addEventListener("click",function(){if(!listArrows && list.value && !listPointerChange) chooseNamedSource(list.value,false);listPointerChange = false;});
      list.addEventListener("keydown",function(e){
        listArrows = ["ArrowUp","ArrowDown","Home","End","PageUp","PageDown"].indexOf(e.key) >= 0;
        if(e.key === "Enter" && list.value){e.preventDefault();chooseNamedSource(list.value,false);}
      });
      var form = node("form"), fieldset = node("fieldset"); fieldset.style.minWidth = "0";
      fieldset.appendChild(node("legend",utext("m4.form.title"))); form.noValidate = true;
      uiForm = {form:form,fields:["date","time","offset","latitude","longitude"],inputs:{},message:node("p"),lastResult:null,draft:false};
      uiForm.fields.forEach(function(name){
        var lab = node("label",utext("m4.form."+name)), input = node("input"); input.type = "text";
        input.name = name; input.autocomplete = "off"; input.spellcheck = false;
        input.style.width = "100%"; input.style.boxSizing = "border-box";
        input.inputMode = name === "date" || name === "time" ? "text" : "decimal";
        lab.style.display = "block"; lab.appendChild(input); fieldset.appendChild(lab); uiForm.inputs[name] = input;
        input.addEventListener("input",function(){uiForm.draft = true;host.onCivilInput(rawCivil());});
      });
      var submit = node("button",utext("m4.form.apply")); submit.type = "submit"; submit.className = "btn"; fieldset.appendChild(submit);
      uiForm.message.setAttribute("role","status"); fieldset.appendChild(uiForm.message); form.appendChild(fieldset); ui.form.replaceChildren(form);
      form.addEventListener("submit",function(e){
        e.preventDefault(); var raw = rawCivil(), result = host.validateCivil(raw);
        if(!result || typeof result.status !== "string") throw new TypeError("TowerView: invalid civil validation result");
        if(result.status === "ok"){
          result = host.applyCivil(raw,result);
          if(!result || typeof result.status !== "string") throw new TypeError("TowerView: invalid civil application result");
          if(result.status === "ok") uiForm.draft = false;
        }
        formMessage(result);
      });
      setCivilFields(host.civilFields(),true); refreshSources(); renderCard(); renderAngles(null,{linked:false});
      uiStats.formMs = performance.now()-start; return ok();
    }
    function refreshUI(){
      if(!ui) throw new TypeError("TowerView: mountUI must precede refreshUI");
      var displayResult=syncStarDisplay();
      if(displayResult.status === "invalidStarDisplay") return displayResult;
      renderCard(); refreshSources(); setCivilFields(host.civilFields(),false);
      ui.sources.querySelectorAll("label")[0].firstChild.nodeValue = utext("m4.search");
      ui.sources.querySelectorAll("label")[1].firstChild.nodeValue = utext("m4.sourceList");
      uiForm.form.querySelector("legend").textContent = utext("m4.form.title");
      uiForm.fields.forEach(function(name){uiForm.inputs[name].parentNode.firstChild.nodeValue = utext("m4.form."+name);});
      uiForm.form.querySelector("button").textContent = utext("m4.form.apply");
      // A language refresh changes only the message's text, not its field state.
      refreshFormMessage(); return ok();
    }

    // ---- scene construction -------------------------------------------------------------
    function lineMesh(segs, hex, groundAware){
      var p = new Float32Array(segs.length*6), c = new Float32Array(segs.length*6), col = new THREE.Color(hex), i, k;
      for(i = 0; i < segs.length; i++) for(k = 0; k < 2; k++){
        var v = segs[i][k], o = i*6 + k*3;
        p[o] = v.x; p[o+1] = v.y; p[o+2] = v.z; c[o] = col.r; c[o+1] = col.g; c[o+2] = col.b;
      }
      var g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(p, 3));
      g.setAttribute("color", new THREE.BufferAttribute(c, 3));
      var m = new THREE.ShaderMaterial({ uniforms: groundAware ? U : { groundOn:{ value:false } }, vertexShader:VS_LN, fragmentShader:FS_LN, transparent:true, depthTest:false });
      var mesh = new THREE.LineSegments(g, m); mesh.frustumCulled = false; mesh.renderOrder = 6;
      return mesh;
    }
    function circle(fn, hex, groundAware, dashed){
      var segs = [], i;
      for(i = 0; i < 360; i++){ if(dashed && i % 4 >= 2) continue; segs.push([fn(i), fn(i + 1)]); }
      return lineMesh(segs, hex, groundAware);
    }
    function horVec(az, alt){
      var a = az*D2R, b = alt*D2R;
      return new THREE.Vector3(Math.cos(b)*Math.sin(a), Math.sin(b), -Math.cos(b)*Math.cos(a));
    }
    function ringTexture(){
      var cv = document.createElement("canvas"); cv.width = cv.height = 64;
      var x = cv.getContext("2d"); x.strokeStyle = "#FFFFFF"; x.lineWidth = 3;
      x.beginPath(); x.arc(32, 32, 18, 0, TAU); x.stroke();
      return new THREE.CanvasTexture(cv);
    }
    function addMarker(parent, pos, cssColor, id, part){
      var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map:ringTexture(), transparent:true, depthTest:false }));
      sp.position.copy(pos); sp.renderOrder = 19;
      sp.userData.marker = { id:id, part:part, color:cssColor };
      parent.add(sp); markers.push(sp);
      return sp;
    }
    function labelColor(e){ return e.below ? "#A1A1A1" : e.color; }
    function makeLabel(e){
      var sp = label(e.text, labelColor(e), 36);
      sp.position.copy(e.pos); sp.userData.tower = e; sp.visible = false; e.parent.add(sp); e.sp = sp;
    }
    function addLabel(parent, pos, text, cssColor, prio, cat, id, part, lazy){
      var e = { text:text, color:cssColor, prio:prio, rank:0, cat:cat, id:id, part:part, below:false, sp:null, pos:pos.clone(), parent:parent };
      if(!lazy) makeLabel(e);
      registry.push(e);
      return e;
    }
    function relabel(e){
      var made = label(e.text, labelColor(e), 36);
      if(e.sp.material.map) e.sp.material.map.dispose();
      e.sp.material.map = made.material.map; e.sp.material.needsUpdate = true; made.material.dispose();
      e.sp.userData.ink = made.userData.ink;
    }
    function starColor(r){
      var col = new THREE.Color(C.star);
      if(r.bv != null){ var t = clamp((r.bv + 0.4)/2.4, 0, 1); col.setRGB(1, 0.95 - 0.28*t, 0.94 - 0.52*t); }
      if(r.id === TW.selected || highlighted[r.id]) col.setHex(C.verdigris);
      return col;
    }
    function clearZoomMarkers(){
      zoomSprites.forEach(function(sp){ sp.visible = false; });
      zoomMarkers = []; zoomPlacements = []; zoomMarkersDropped = 0;
    }
    function zoomTexture(count){
      if(zoomTextures[count]) return zoomTextures[count];
      var cv = document.createElement("canvas"); cv.height = 80; cv.width = 1;
      var x = cv.getContext("2d"), digits = String(count), font = 53;
      x.font = font + "px sans-serif";
      var width = Math.ceil(x.measureText(digits).width);
      cv.width = 70 + width + 18;
      x.font = font + "px sans-serif"; x.fillStyle = x.strokeStyle = "#FFFFFF";
      // Same dark halo as host.label(), scaled from its 54px texture to this 80px texture.
      x.shadowColor = "rgba(0,0,0,.95)"; x.shadowBlur = 8*80/54;
      x.lineWidth = 8; x.lineCap = "round";
      x.beginPath(); x.arc(28, 32, 17, 0, TAU); x.stroke();
      x.beginPath(); x.moveTo(41, 45); x.lineTo(54, 60); x.stroke();
      x.fillText(digits, 66, 59);
      // Conservative ink bounds only; the halo is deliberately not a collision obstacle.
      return zoomTextures[count] = { texture:new THREE.CanvasTexture(cv), ink:[7/cv.width,11/80,(68+width)/cv.width,64/80] };
    }
    // Sources and zoom markers share the exact offsets, viewport margin and collision test.
    // Required source labels retain their existing best-overlap fallback; markers never use it.
    function labelPlace(pj, iw, ih, icx, icy, order, placed, W, H, required, gap){
      var best = null, bestCost = Infinity;
      for(var j = 0; j < order.length; j++){
        var ax = order[j][0], ay = order[j][1], g = gap == null ? 9 : gap, gy = ax === 0 ? g : 2;
        var cx = ax > 0 ? g + iw/2 : ax < 0 ? -(g + iw/2) : 0, cy = ay > 0 ? gy + ih/2 : ay < 0 ? -(gy + ih/2) : 0;
        var b = { x0:pj.x + cx - iw/2, x1:pj.x + cx + iw/2, y0:pj.y + cy - ih/2, y1:pj.y + cy + ih/2, dx:cx - icx, dy:cy - icy };
        if(b.x0 < 2 || b.x1 > W - 2 || b.y0 < 2 || b.y1 > H - 2) continue;
        var cost = 0;
        for(var q = 0; q < placed.length; q++){
          var o = placed[q], ox = Math.min(b.x1, o.x1) - Math.max(b.x0, o.x0) + 3, oy = Math.min(b.y1, o.y1) - Math.max(b.y0, o.y0) + 3;
          if(ox > 0 && oy > 0) cost += ox*oy;
        }
        if(cost === 0){ best = b; break; }
        if(required && cost < bestCost){ bestCost = cost; best = b; }
      }
      return best;
    }
    function placeZoomMarkers(unplaced, placed, W, H, tanH){
      if(!unplaced.length) return;
      // Canonical-ID order makes the connected components and their order deterministic.
      unplaced.sort(function(a,b){ return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; });
      var parent = unplaced.map(function(_,i){ return i; }), groups = [], byRoot = Object.create(null);
      function find(i){ while(parent[i] !== i){ parent[i] = parent[parent[i]]; i = parent[i]; } return i; }
      for(var i = 0; i < unplaced.length; i++) for(var j = 0; j < i; j++){
        var dx = unplaced[i].x - unplaced[j].x, dy = unplaced[i].y - unplaced[j].y;
        if(dx*dx + dy*dy <= 24*24){ var a = find(i), b = find(j); parent[Math.max(a,b)] = Math.min(a,b); }
      }
      unplaced.forEach(function(p,i){ var key = find(i), group = byRoot[key]; if(!group){ group = byRoot[key] = []; groups.push(group); } group.push(p); });
      groups.forEach(function(group){
        var x = 0, y = 0, depth = 0, below = true;
        group.forEach(function(p){ x += p.x; y += p.y; depth += p.depth; below = below && p.below; });
        x /= group.length; y /= group.length; depth /= group.length;
        var image = zoomTexture(group.length), cv = image.texture.image, h = LABEL_PX*1.5, wd = h*cv.width/cv.height, ink = image.ink;
        var iw = (ink[2]-ink[0])*wd, ih = (ink[3]-ink[1])*h, icx = ((ink[0]+ink[2])/2-0.5)*wd, icy = ((ink[1]+ink[3])/2-0.5)*h;
        var best = null;
        for(var gap = 9; gap <= 33 && !best; gap += 12) best = labelPlace({x:x,y:y}, iw, ih, icx, icy, SOURCE_LABEL_OFFSETS, placed, W, H, false, gap);
        if(!best){ zoomMarkersDropped++; return; }
        var sp = zoomSprites[zoomMarkers.length];
        if(!sp){
          sp = new THREE.Sprite(new THREE.SpriteMaterial({map:image.texture,transparent:true,depthTest:false,depthWrite:false,opacity:ZOOM_MARKER_OPACITY}));
          sp.renderOrder = 20; sp.raycast = function(){}; root.add(sp); zoomSprites.push(sp);
        }
        if(sp.material.map !== image.texture){ sp.material.map = image.texture; sp.material.needsUpdate = true; }
        sp.material.color.set(labelColor({below:below,color:"#EAE3D2"})); sp.material.opacity = ZOOM_MARKER_OPACITY;
        var world = new THREE.Vector3((2*x/W-1)*depth*tanH*W/H, (1-2*y/H)*depth*tanH, -depth).applyMatrix4(camera.matrixWorld);
        sp.position.copy(root.worldToLocal(world));
        var worldH = h*2*depth*tanH/H; sp.scale.set(worldH*cv.width/cv.height,worldH,1);
        sp.center.set(0.5-best.dx/wd,0.5+best.dy/h); sp.visible = true;
        var ids = group.map(function(p){ return p.id; });
        sp.userData.zoomMarker = {ids:ids.slice(),count:ids.length,below:below,centroid:{x:x,y:y},box:{x0:best.x0,x1:best.x1,y0:best.y0,y1:best.y1}};
        placed.push(best);
        var record = {ids:ids,count:ids.length,position:{x:(best.x0+best.x1)/2,y:(best.y0+best.y1)/2}};
        zoomMarkers.push(record); zoomPlacements.push({box:best,sprite:sp,record:record});
      });
    }
    function preserveRequiredLabel(best, placed){
      // Selection/target labels retain their original placement and best-overlap rule.
      // A marker cannot force one aside or survive underneath a later required label.
      for(var i = zoomPlacements.length-1; i >= 0; i--){
        var z = zoomPlacements[i], b = z.box;
        if(Math.min(best.x1,b.x1)-Math.max(best.x0,b.x0)+3 > 0 && Math.min(best.y1,b.y1)-Math.max(best.y0,b.y0)+3 > 0){
          z.sprite.visible = false; placed.splice(placed.indexOf(b),1);
          zoomMarkers.splice(zoomMarkers.indexOf(z.record),1); zoomPlacements.splice(i,1); zoomMarkersDropped++;
        }
      }
    }
    function rebuild(){
      clearZoomMarkers(); hasZoomHints = false;
      if(sourcesDirty) dispose(points);
      if(sourcesDirty || figuresDirty) dispose(figureMesh);
      dispose(guideWorld); dispose(guideEcl); dispose(footGroup);
      markers.forEach(dispose); registry.forEach(function(e){ dispose(e.sp); });
      guideWorld = guideEcl = footGroup = null; markers = []; registry = []; activeLabels = []; foot = null; ascEntry = null; ascMarker = null;
      stats.rebuilds++;
      // the stars: one Points draw; selection changes a colour attribute only (C10)
      var n = stars.length, pr = renderer.getPixelRatio();
      if(sourcesDirty || !points){
      var p = new Float32Array(n*3), c = new Float32Array(n*3), sz = new Float32Array(n);
      stars.forEach(function(r, i){
        var v = equLocal(r.ra, r.dec), col = starColor(r);
        p[i*3] = v.x; p[i*3+1] = v.y; p[i*3+2] = v.z; c[i*3] = col.r; c[i*3+1] = col.g; c[i*3+2] = col.b;
        sz[i] = Math.max(3.5, 9 - (r.vmag == null ? 5 : r.vmag))*pr; // C02: unknown Johnson V uses exactly the V 5.0 size
      });
      var g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(p, 3));
      g.setAttribute("color", new THREE.BufferAttribute(c, 3));
      g.setAttribute("size", new THREE.BufferAttribute(sz, 1));
      points = new THREE.Points(g, new THREE.ShaderMaterial({ uniforms:U, vertexShader:VS_PTS, fragmentShader:FS_PTS, transparent:true, depthTest:false }));
      points.frustumCulled = false; points.renderOrder = 8; equRoot.add(points);
      stats.pointBuilds++;
      } else {
        // Selection/layer/name changes retain the base Points and update its colour attribute.
        var colors = points.geometry.attributes.color;
        stars.forEach(function(r, i){ var col = starColor(r); colors.setXYZ(i, col.r, col.g, col.b); });
        colors.needsUpdate = true;
      }
      // extended objects: ring markers at their anchors
      objects.forEach(function(r){ addMarker(equRoot, equLocal(r.ra, r.dec), r.id === TW.selected || highlighted[r.id] ? "#6FBCA5" : "#7FB6E0", r.id, "object"); });
      // figures: one batched LineSegments draw; a segment shared by two figures is drawn once
      if(sourcesDirty || figuresDirty || !figureMesh){
      segments = []; var used = {};
      figures.concat(extras).forEach(function(f){ (f.lines || []).concat(f.extLines || []).forEach(function(line){
        for(var j = 1; j < line.length; j++){
          var key = [line[j-1], line[j]].sort().join("|"); if(used[key]) continue; used[key] = true;
          var a = records[line[j-1]], b = records[line[j]];
          segments.push([equLocal(a.ra, a.dec), equLocal(b.ra, b.dec)]);
        }
      }); });
      figureMesh = lineMesh(segments, C.steel, true); equRoot.add(figureMesh);
      stats.figureBuilds++;
      }
      figures.concat(extras).forEach(function(f){
        if(!f.label) return; // historical C08 synthetic fixtures may carry lines only
        if(typeof host.figureName !== "function" || typeof host.figureAnchor !== "function") throw new TypeError("TowerView: C07 labels require host.figureName and host.figureAnchor");
        var anchor = host.figureAnchor(f,twCopy(descriptor));
        if(!anchor || !twFinite(anchor.ra) || !twFinite(anchor.dec) || anchor.dec < -90 || anchor.dec > 90) throw new TypeError("TowerView: invalid active figure anchor");
        var name = host.figureName(f);
        if(typeof name !== "string" || !name) throw new TypeError("TowerView: missing figure name");
        addLabel(equRoot,equLocal(anchor.ra,anchor.dec),name,"#7FB6E0",TW_PRIO.other,"figure",f.key,"figure",true);
      });
      // the observer's guides, drawn thin from inside (the page's rings are made to be seen from outside)
      guideWorld = new THREE.Group(); root.add(guideWorld);
      guideWorld.userData.horizon = circle(function(a){ return horVec(a, 0); }, C.brass, false, false);
      guideWorld.userData.meridian = circle(function(a){ return new THREE.Vector3(0, Math.sin(a*D2R), Math.cos(a*D2R)); }, C.brassDim, true, false);
      guideWorld.add(guideWorld.userData.horizon); guideWorld.add(guideWorld.userData.meridian);
      guideWorld.userData.cardinals = [];
      [["lbl.N", 0], ["lbl.E", 90], ["lbl.S", 180], ["lbl.W", 270]].forEach(function(o){
        guideWorld.userData.cardinals.push(addLabel(guideWorld, horVec(o[1], 0), T(o[0]), "#E3AA3E", TW_PRIO.guide, "cardinal", null, "cardinal"));
      });
      guideEcl = new THREE.Group(); eclRoot.add(guideEcl);
      guideEcl.userData.ecliptic = circle(function(a){ return eclV(a, 0); }, C.madder, true, false);
      guideEcl.add(guideEcl.userData.ecliptic);
      // the foot point of the selected object: its longitude on the ecliptic, reached along a dashed arc of constant longitude
      footGroup = new THREE.Group(); eclRoot.add(footGroup);
      var target = records[TW.selected];
      var ec = target ? twActiveEcl(target) : null;
      if(ec && ec.lon != null){
        var lat = ec.lat || 0, arc = [];
        for(var k = 0; k < 80; k++) if(k % 4 < 2) arc.push([eclV(ec.lon, lat*k/80), eclV(ec.lon, lat*(k + 1)/80)]);
        footGroup.add(lineMesh(arc, C.madder, true));
        var fv = eclV(ec.lon, 0);
        foot = { id:target.id, lon:ec.lon, local:fv, marker:addMarker(footGroup, fv, "#E4674C", target.id, "foot"),
                 label:addLabel(footGroup, fv, fmtZod(ec.lon), "#E4674C", TW_PRIO.target, "foot", target.id, "foot") };
      }
      // the Ascendant: moved along the ecliptic every frame, rebuilt only when its text changes
      ascMarker = addMarker(eclRoot, new THREE.Vector3(), "#E3AA3E", null, "asc");
      ascEntry = addLabel(eclRoot, new THREE.Vector3(), "", "#E3AA3E", TW_PRIO.guide, "asc", null, "asc");
      // the co-rising degree of the selected object, when asked for
      if(coLon != null && TP.coRising){
        var cv = eclV(coLon, 0);
        addMarker(eclRoot, cv, "#6FBCA5", null, "coRising");
        addLabel(eclRoot, cv, T("tw.lblCo") + " " + fmtZod(coLon), "#6FBCA5", TW_PRIO.other, "coRising", null, "coRising");
      }
      // one label for each source; the selected one first
      stars.concat(objects).forEach(function(r){
        var sel = r.id === TW.selected || highlighted[r.id];
        var prio = host.sourcePriority(r.id, r);
        if(prio !== TW_PRIO.target && prio !== TW_PRIO.other) throw new TypeError("TowerView: host.sourcePriority must return target or other priority");
        var rank = typeof host.sourceLabelRank === "undefined" ? 0 : host.sourceLabelRank(r.id, r);
        if(typeof rank !== "number" || rank < 0 || rank % 1 !== 0) throw new TypeError("TowerView: host.sourceLabelRank must return a non-negative integer");
        var hint = typeof host.sourceZoomHint === "undefined" ? false : host.sourceZoomHint(r.id, r);
        if(typeof hint !== "boolean") throw new TypeError("TowerView: host.sourceZoomHint must return true or false");
        var sourceLabel = addLabel(equRoot, equLocal(r.ra, r.dec), twName(r.id), sel ? "#6FBCA5" : "#EAE3D2", sel ? TW_PRIO.select : prio, "source", r.id, "source", true);
        sourceLabel.rank = rank; sourceLabel.zoomHint = hint; hasZoomHints = hasZoomHints || hint;
      });
      if(!ground){
        ground = new THREE.Mesh(new THREE.SphereGeometry(0.98, 96, 32, 0, TAU, Math.PI/2, Math.PI/2), new THREE.MeshBasicMaterial({ color:C.ground, side:THREE.DoubleSide }));
        ground.renderOrder = 1; root.add(ground);
      }
      sourcesDirty = figuresDirty = dirty = false;
    }
    function ascText(){ return state.axes && state.axes.asc != null ? T("chart.asc") + " " + fmtZod(state.axes.asc) : ""; }
    // ---- per frame: what is shown, where the labels go, the ground and the legend --------
    function project(world){
      _c.copy(world).applyMatrix4(camera.matrixWorldInverse);
      var depth = -_c.z, W = view.clientWidth, H = view.clientHeight;
      _w.copy(world).project(camera);
      return { x:(_w.x + 1)*W/2, y:(1 - _w.y)*H/2, depth:depth,
               visible: depth > camera.near && _w.z >= -1 && _w.z <= 1 && Math.abs(_w.x) <= 1 && Math.abs(_w.y) <= 1 };
    }
    function worldOf(o){ return o.getWorldPosition(new THREE.Vector3()); }
    function hiddenByGround(world){ return TW.mode === "tower" && PREF.ground && world.y < -1e-9; }
    function sourceShown(r){ return r.kind ? TP.objects : TP.stars; }
    function eligible(r){
      if(!r || !displayAllows(r.id) || !TW.applied || !shownParents(equRoot) || !sourceShown(r)) return false;
      return !hiddenByGround(equLocal(r.ra, r.dec).applyMatrix4(equGroup.matrixWorld));
    }
    function layout(obstacles){
      // Observe host-owned pose/size changes while the walk is alive, before an early return or redraw.
      if(zoomWalk) checkZoomWalk();
      clearZoomMarkers();
      if(!TW.applied) return;
      if(dirty) rebuild();
      // Pixel ratio can change without a new source batch (moving between displays).
      var sizes = points.geometry.attributes.size, ratio = renderer.getPixelRatio(), sizeChanged = false;
      stars.forEach(function(r, i){ var size = Math.max(3.5, 9 - (r.vmag == null ? 5 : r.vmag))*ratio;
        if(sizes.getX(i) !== Math.fround(size)){ sizes.setX(i, size); sizeChanged = true; } });
      if(sizeChanged) sizes.needsUpdate = true;
      var tower = TW.mode === "tower", W = view.clientWidth, H = view.clientHeight;
      if(!W || !H) return;
      U.groundOn.value = tower && !!PREF.ground;
      equRoot.updateMatrixWorld(true); root.updateMatrixWorld(true);
      // what each layer and the mode allow
      points.visible = TP.stars && stars.length > 0;
      figureMesh.visible = TP.figures && segments.length > 0;
      guideWorld.visible = tower; guideEcl.visible = tower && !!PREF.ecliptic;
      guideWorld.userData.horizon.visible = !!PREF.horizon; guideWorld.userData.meridian.visible = !!PREF.meridian;
      footGroup.visible = TP.foot;
      ground.visible = tower && !!PREF.ground;
      // the Ascendant moves with the sidereal time
      var asc = state.axes && state.axes.asc != null ? state.axes.asc : null;
      ascMarker.visible = asc != null;
      if(asc != null){
        ascMarker.position.copy(eclV(asc, 0)); ascEntry.sp.position.copy(ascMarker.position);
        var at = ascText(); if(at !== ascEntry.text){ ascEntry.text = at; relabel(ascEntry); }
      }
      camera.updateMatrixWorld();
      var tanH = Math.tan(camera.fov*D2R/2), anyBelow = false;
      // markers: 20 CSS px rings, dim below the horizon, hidden there when the ground is on
      markers.forEach(function(sp){
        var d = sp.userData.marker, w = worldOf(sp), below = w.y < -1e-9 && d.part !== "asc";
        var on = shownParents(sp.parent) && !(below && hiddenByGround(w)) && !(d.part === "object" && !TP.objects);
        var pj = project(w);
        sp.visible = on && pj.visible;
        if(sp.visible){
          var hgt = 20*2*pj.depth*tanH/H; sp.scale.set(hgt, hgt, 1);
          var hex = below ? "#A1A1A1" : (d.part === "object" && (d.id === TW.selected || highlighted[d.id]) ? "#6FBCA5" : d.color);
          sp.material.color.set(hex); sp.material.opacity = below ? 0.4 : 1;
          if(below && tower) anyBelow = true;
        }
      });
      // labels by priority; each finds a free place beside its point or is culled (C09)
      var placed = (obstacles || []).slice();
      activeLabels = [];
      registry.sort(function(a, b){ return a.prio - b.prio || (a.part === "figure") - (b.part === "figure") || a.rank - b.rank || (a.text < b.text ? -1 : a.text > b.text ? 1 : 0); });
      var unplaced = [], lastHint = -1;
      if(hasZoomHints && TP.labels) for(var zi = registry.length-1; zi >= 0; zi--) if(registry[zi].zoomHint){ lastHint = zi; break; }
      function placeLabel(e){
        var sp = e.sp; if(sp) sp.visible = false;
        if(!TP.labels || !e.text) return;
        if(e.part === "figure" && !TP.figures) return;
        if(e.part === "source" && (!displayAllows(e.id) || !sourceShown(records[e.id] || {}))) return;
        if(e.part === "cardinal" && !PREF.cardinals) return;          // the page's own "N E S W" layer
        var w = sp ? worldOf(sp) : e.pos.clone().applyMatrix4(e.parent.matrixWorld), below = w.y < -1e-9 && e.part !== "asc" && e.part !== "cardinal";
        if(e.part === "asc" && asc == null) return;
        if(!shownParents(e.parent) || (below && hiddenByGround(w))) return;
        var pj = project(w); if(!pj.visible) return;
        if(!sp){ e.below = below; makeLabel(e); sp = e.sp; }
        else if(below !== e.below){ e.below = below; relabel(e); }
        if(below && tower) anyBelow = true;
        var img = sp.material.map.image, h = LABEL_PX*1.5, wd = h*img.width/img.height, ink = sp.userData.ink;
        var worldH = h*2*pj.depth*tanH/H; sp.scale.set(worldH*img.width/img.height, worldH, 1);
        var iw = (ink[2] - ink[0])*wd, ih = (ink[3] - ink[1])*h, icx = ((ink[0] + ink[2])/2 - 0.5)*wd, icy = ((ink[1] + ink[3])/2 - 0.5)*h;
        var order = e.part === "cardinal" ? [[0,-1],[0,1],[1,0],[-1,0]]
          : e.part === "asc" ? [[0,-1],[1,-1],[-1,-1],[0,1],[1,1],[-1,1],[1,0],[-1,0]]
          : e.part === "foot" ? [[0,1],[1,1],[-1,1],[1,0],[-1,0],[0,-1],[1,-1],[-1,-1]]
          : SOURCE_LABEL_OFFSETS;
        var required = e.prio <= TW_PRIO.target, collisionBoxes = placed;
        if(required && zoomPlacements.length) collisionBoxes = placed.filter(function(b){ return !zoomPlacements.some(function(z){ return z.box === b; }); });
        var best = labelPlace(pj,iw,ih,icx,icy,order,collisionBoxes,W,H,required);
        if(!best){ if(e.zoomHint) unplaced.push({id:e.id,x:pj.x,y:pj.y,depth:pj.depth,below:below}); return; }
        if(required && zoomPlacements.length) preserveRequiredLabel(best,placed);
        sp.center.set(0.5 - best.dx/wd, 0.5 + best.dy/h);
        sp.visible = true;
        placed.push(best);
        activeLabels.push({ text:e.text, id:e.id, part:e.part, prio:e.prio, below:below, fontCSS:LABEL_PX,
                            box:{ x0:best.x0, x1:best.x1, y0:best.y0, y1:best.y1 } });
      }
      registry.forEach(function(e,i){ placeLabel(e); if(i === lastHint) placeZoomMarkers(unplaced,placed,W,H,tanH); });
      // the reveal's legend: shown in the Tower when the ground is lifted and something below it is drawn
      if(tower && root.visible && !PREF.ground) stars.concat(objects).forEach(function(r){
        if(sourceShown(r) && equLocal(r.ra, r.dec).applyMatrix4(equGroup.matrixWorld).y < 0) anyBelow = true; });
      var leg = tower && !PREF.ground && anyBelow;
      if(leg !== legendOn){ legendOn = leg; host.setReveal(leg); }
      stats.frames++;
    }
    function shownParents(o){ for(; o; o = o.parent) if(!o.visible) return false; return true; }   // the object's own flag aside
    // ---- picking (C09): the nearest eligible source within 14 CSS px; ties to the brighter, then the ID
    // Setters end a walk at a real change; layout also observes host-owned changes. Once ended it cannot revive.
    function walkStamp(){
      return { pose:[camera.position.x,camera.position.y,camera.position.z,camera.quaternion.x,camera.quaternion.y,camera.quaternion.z,camera.quaternion.w,camera.fov]
          .concat(camera.matrixWorld.elements,camera.projectionMatrix.elements),
        width:view.clientWidth,height:view.clientHeight,canvasWidth:renderer.domElement.width,canvasHeight:renderer.domElement.height,mode:TW.mode,lst:state.lst,lat:state.lat,obl:state.obl,
        // Observe every host preference, with key order ignored for an unchanged map.
        layers:JSON.stringify(layers())+JSON.stringify(PREF,Object.keys(PREF).sort()),stars:stars,objects:objects,
        displayMode:display.mode,displayStatus:display.status,displayAvailable:display.available,displayIds:displayIds };
    }
    function sameWalkStamp(a,b){
      if(a.width !== b.width || a.height !== b.height || a.canvasWidth !== b.canvasWidth || a.canvasHeight !== b.canvasHeight || a.mode !== b.mode || a.lst !== b.lst || a.lat !== b.lat || a.obl !== b.obl
          || a.layers !== b.layers || a.stars !== b.stars || a.objects !== b.objects || a.displayMode !== b.displayMode
          || a.displayStatus !== b.displayStatus || a.displayAvailable !== b.displayAvailable) return false;
      for(var i=0;i<a.pose.length;i++) if(a.pose[i] !== b.pose[i]) return false;
      // UI refreshes may replace the map without changing the display. Compare membership only then.
      if(a.displayIds !== b.displayIds){
        var ids=Object.keys(a.displayIds);
        if(ids.length !== Object.keys(b.displayIds).length) return false;
        for(i=0;i<ids.length;i++) if(!has(b.displayIds,ids[i])) return false;
        a.displayIds=b.displayIds;
      }
      return true;
    }
    function checkZoomWalk(){
      if(TW.selected !== zoomWalk.last || !sameWalkStamp(zoomWalk.stamp,walkStamp())) zoomWalk = null;
    }
    function inWalkBox(x,y,b){ return x >= b.x0 && x <= b.x1 && y >= b.y0 && y <= b.y1; }
    function pick(x, y){
      if(!TW.applied || !shownParents(equRoot)){ zoomWalk = null; return null; }
      if(zoomWalk && (zoomWalk.pending || TW.selected !== zoomWalk.last || !sameWalkStamp(zoomWalk.stamp,walkStamp()))) zoomWalk = null;
      if(zoomWalk && inWalkBox(x,y,zoomWalk.box)){
        zoomWalk.last = zoomWalk.ids[(zoomWalk.ids.indexOf(zoomWalk.last)+1)%zoomWalk.ids.length]; zoomWalk.pending = true; zoomWalk.markerPick = true;
        return {id:zoomWalk.last,part:"zoomMarker",distance:0,vmag:99};
      }
      if(zoomWalk){ zoomWalk.pending = true; zoomWalk.markerPick = false; }
      for(var zi = 0; zi < zoomPlacements.length; zi++){
        var marker = zoomPlacements[zi], box = marker.box;
        if(marker.sprite.visible && shownParents(marker.sprite.parent) && x >= box.x0-6 && x <= box.x1+6 && y >= box.y0-6 && y <= box.y1+6){
          var ids = marker.record.ids, next = ids[0];
          for(var mi = 0; mi < ids.length; mi++) if(TW.selected === null || ids[mi] > TW.selected){ next = ids[mi]; break; }
          zoomWalk = {box:{x0:box.x0-6,x1:box.x1+6,y0:box.y0-6,y1:box.y1+6},ids:ids.slice().sort(),last:next,pending:true,markerPick:true,stamp:walkStamp()};
          return {id:next,part:"zoomMarker",distance:0,vmag:99};
        }
      }
      equRoot.updateMatrixWorld(true);
      var hits = [];
      stars.concat(objects).forEach(function(r){
        if(!eligible(r)) return;
        var pj = project(equLocal(r.ra, r.dec).applyMatrix4(equGroup.matrixWorld)); if(!pj.visible) return;
        var d = (pj.x - x)*(pj.x - x) + (pj.y - y)*(pj.y - y);
        if(d <= 196) hits.push({ id:r.id, part:"source", distance:Math.sqrt(d), vmag:r.vmag == null ? 99 : r.vmag });
      });
      if(foot && displayAllows(foot.id) && TP.foot && footGroup && shownParents(foot.marker)){
        var fw = worldOf(foot.marker);
        if(!hiddenByGround(fw)){
          var fp = project(fw), fd = (fp.x - x)*(fp.x - x) + (fp.y - y)*(fp.y - y);
          if(fp.visible && fd <= 196) hits.push({ id:foot.id, part:"foot", distance:Math.sqrt(fd), vmag:99 });
        }
      }
      hits.sort(function(a, b){ return Math.abs(a.distance - b.distance) > 1e-9 ? a.distance - b.distance : (a.vmag - b.vmag) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0); });
      return hits[0] || null;
    }
    // whether a view point lies on the Tower's opaque ground (its ray from the observer points below the horizon)
    function onGround(x, y){
      if(TW.mode !== "tower" || !PREF.ground) return false;
      var W = view.clientWidth, H = view.clientHeight;
      _w.set(x/W*2 - 1, 1 - y/H*2, 0.5).unproject(camera).sub(camera.position);
      return _w.y < 0;
    }
    function zoom(k){   // k > 0 zooms out
      if(TW.mode === "tower") setLook({ az:look.az, alt:look.alt, fov:look.fov + 5*k });
      else { cam.tr = clamp(cam.tr + 0.3*k, 1.7, 9); kick(); }
    }
    function pan(dx, dy){   // drag in CSS px: the sky follows the pointer
      var per = look.fov/Math.max(1, view.clientHeight);
      setLook({ az:look.az - dx*per, alt:look.alt + dy*per });
    }
    function show(on){ root.visible = equRoot.visible = eclRoot.visible = !!on; if(on) dirty = true;
      if(!on) clearZoomMarkers();
      if(!on && legendOn !== false){ legendOn = false; host.setReveal(false); } }
    function inspect(){
      equRoot.updateMatrixWorld(true);
      var f = null;
      if(foot){ var fw = worldOf(foot.marker); f = { id:foot.id, lon:foot.lon, alt:Math.asin(clamp(fw.y, -1, 1))*R2D, world:{ x:fw.x, y:fw.y, z:fw.z }, projection:project(fw), hiddenByGround:hiddenByGround(fw) }; }
      var a = null;
      if(ascMarker && state.axes && state.axes.asc != null){ var aw = worldOf(ascMarker); a = { lon:state.axes.asc, projection:project(aw), world:{ x:aw.x, y:aw.y, z:aw.z } }; }
      return { schemaVersion:1, applied:TW.applied, linked:TW.linked, mode:TW.mode, transition:!!transition, look:twCopy(look),
        orbit:{ r:cam.r, theta:cam.theta, phi:cam.phi, tr:cam.tr, tth:cam.tth, tph:cam.tph, fov:ORBIT_FOV, near:ORBIT_NEAR },
        state:{ lat:state.lat, lst:state.lst, obl:state.obl, axes:state.axes ? twCopy(state.axes) : null, linked:state.linked, contextId:state.contextId },
        descriptor:descriptor ? twCopy(descriptor) : null, index:twCopy(index), selection:TW.selected, layers:layers(),
        labels:twCopy(activeLabels), zoomMarkers:twCopy(zoomMarkers), zoomMarkersDropped:zoomMarkersDropped, figureLabels:registry.filter(function(e){return e.part === "figure";}).map(function(e){return {id:e.id,text:e.text,position:{x:e.pos.x,y:e.pos.y,z:e.pos.z}};}), ui: { mounted:!!ui, starDisplay:twCopy(display), entry:uiEntry, highlighted:Object.keys(highlighted), timings:twCopy(uiStats) }, foot:f, asc:a, coRising:coLon, legend:!!legendOn, stats:twCopy(stats),
        starCount:stars.length, objectCount:objects.length, figureSegments:segments.length,
        pointsDraw: points && points.visible && root.visible ? 1 : 0, figureDraw: figureMesh && figureMesh.visible && root.visible ? 1 : 0,
        positions:stars.concat(objects).map(function(r){
          var v = equLocal(r.ra, r.dec).applyMatrix4(equGroup.matrixWorld);
          return { id:r.id, world:{ x:v.x, y:v.y, z:v.z }, alt:Math.asin(clamp(v.y, -1, 1))*R2D, projection:project(v), eligible:eligible(r) };
        }) };
    }
    return { setMode:setMode, setLook:setLook, getLook:function(){ return twCopy(look); }, setStars:function(r, d){ return setRecords("stars", r, d); },
      setObjects:function(r, d){ return setRecords("objects", r, d); }, setSources:setSources, checkDescriptor:checkDescriptor,
      setFigures:setFigures, select:select, onSelect:function(fn){ notify = fn; }, setCoRising:setCoRising, update:update, layers:layers,
      tick:tick, layout:layout, ownsCamera:ownsCamera, transitioning:function(){ return !!transition; }, pick:pick, onGround:onGround, zoom:zoom, pan:pan,
      refreshStarDisplay:refreshStarDisplay, mountUI:mountUI, refreshUI:refreshUI, renderCard:renderCard, renderAngles:renderAngles, refreshSources:refreshSources, setCivilFields:setCivilFields,
      show:show, inspect:inspect, invalidate:function(){ dirty = true; kick(); }, records:function(){ return records; } };
  }
  return { schemaVersion:1, create:create };
})();
