/* Portable Sphere world, schema 1. See CONTRACT.txt for host members and lifecycle.
   Only SphereWorld is exported. THREE and browser/language built-ins are external. */
var SphereWorld = (function(){
  "use strict";
  var HOST = {container:"object", T:"function", colours:"object", reducedMotion:"boolean", observer:"object"};
  var ROLES = ["brass","brassDim","steel","steelDim","madder","madderDim","verdigris","star","ground",
    "labelBrass","labelPrime","labelDim","labelQuadrant","labelSteel","labelSteelDim","labelMadder","labelShadow"];
  function finite(x){ return typeof x === "number" && isFinite(x); }
  function observer(o){
    if(!o || !finite(o.lat) || Math.abs(o.lat)>90 || !finite(o.lst) || !finite(o.obl) || o.obl<0 || o.obl>90)
      throw new TypeError("SphereWorld: observer requires lat [-90,90], finite lst, obl [0,90], in degrees");
    return {lat:o.lat, lst:((o.lst%360)+360)%360, obl:o.obl};
  }
  function palette(p){
    var out = {}, k;
    if(!p || typeof p !== "object") throw new TypeError("SphereWorld: colours must be an object");
    for(k in p) if(Object.prototype.hasOwnProperty.call(p,k)) out[k] = p[k];
    ROLES.forEach(function(role){
      var v = out[role];
      if(!(typeof v === "string" && v.length) && !(finite(v) && Math.floor(v)===v && v>=0 && v<=16777215))
        throw new TypeError("SphereWorld: colours."+role+" must be a colour string or RGB integer");
    });
    return out;
  }
  function create(host){
    var k;
    if(!host || typeof host !== "object") throw new TypeError("SphereWorld.create: host must be an object");
    for(k in HOST) if(host[k] === null || typeof host[k] !== HOST[k])
      throw new TypeError("SphereWorld.create: host."+k+" must be "+HOST[k]);
    var view = host.container;
    if(!view.ownerDocument || !view.ownerDocument.defaultView ||
       !(view instanceof view.ownerDocument.defaultView.HTMLElement) ||
       typeof view.appendChild !== "function" || typeof view.addEventListener !== "function" ||
       typeof view.removeEventListener !== "function" || !finite(view.clientWidth) || !finite(view.clientHeight))
      throw new TypeError("SphereWorld.create: host.container must be an element with client dimensions");
    var S = observer(host.observer), C = palette(host.colours), T = host.T, reduced = host.reducedMotion;
    var D2R = Math.PI/180, R2D = 180/Math.PI, TAU = Math.PI*2, R = 1;
    var UIFONT = '"IBM Plex Sans Condensed", Arial, "PingFang SC", "Hiragino Sans", "Yu Gothic", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif';
    var SYMFONT = '"Noto Sans Symbols 2","Segoe UI Symbol","Apple Symbols","DejaVu Sans",serif';
    function pad(n,w){ n = String(Math.round(n)); while(n.length<w) n = "0"+n; return n; }
    function cssColour(value){
      if(typeof value!=="number")return value;
      var text=value.toString(16);while(text.length<6)text="0"+text;return "#"+text;
    }
    var renderer = new THREE.WebGLRenderer({antialias:true,alpha:true});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
    var scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(38,1,0.05,60);
    var horGroup = new THREE.Group(), equGroup = new THREE.Group(), eclGroup = new THREE.Group();
    scene.add(horGroup); scene.add(equGroup); equGroup.add(eclGroup); equGroup.matrixAutoUpdate = false;
    var L = {}, PREF = {}, TW_SHARED = {ground:1,horizon:1,ecliptic:1,meridian:1,cardinals:1};
    var cam = {r:4.2,theta:0.72,phi:1.07,tr:4.2,tth:0.72,tph:1.07};
    var dead = false, rafId = 0, prevT = 0, inFrame = false, phase = "", invalidated = false;
    var controller = null, wheelPolicy = null, interactions = [], listeners = [], resizeObserver = null;
    var hooks = {before:[],update:[],after:[]}, labelRegistry = [], ownedObjects = [], themedMaterials = [];
    var stats = {frames:0,requests:0};
    function alive(){ if(dead) throw new Error("SphereWorld: disposed"); }
    function listen(target,name,fn,options){
      target.addEventListener(name,fn,options);
      listeners.push(function(){target.removeEventListener(name,fn,options);});
    }
    function emit(type,event){ interactions.slice().forEach(function(fn){fn(type,event);}); }
    function subscription(list,fn){
      alive(); if(typeof fn !== "function") throw new TypeError("SphereWorld: listener must be a function");
      list.push(fn); var attached = true;
      return function(){ if(!attached)return; attached=false; var i=list.indexOf(fn);if(i>=0)list.splice(i,1); };
    }
    function onFrame(name,fn){
      if(!Object.prototype.hasOwnProperty.call(hooks,name)) throw new TypeError("SphereWorld: unknown frame phase");
      return subscription(hooks[name],fn);
    }
    function run(name,now,dt,moving){
      phase=name;
      var again=false;
      hooks[name].slice().forEach(function(fn){if(!dead && fn(now,dt,moving)===true)again=true;});
      return again;
    }
    function kick(){
      if(dead)return;
      if(inFrame){invalidated=true;return;}
      if(!rafId){prevT=performance.now();stats.requests++;rafId=requestAnimationFrame(frame);}
    }
    function applyObserver(){
      buildEquBasis(S.lat,S.lst);equGroup.matrix.copy(equMatrix);equGroup.matrixWorldNeedsUpdate=true;
      eclGroup.rotation.x=S.obl*D2R;
      if((S.lat<0)!==poleSouth)setPoleLabels(S.lat<0);
    }
    function setObserver(data){
      alive();var next=observer(data),changed=next.lat!==S.lat||next.lst!==S.lst||next.obl!==S.obl;
      S.lat=next.lat;S.lst=next.lst;S.obl=next.obl;
      if(changed && phase!=="before")kick();
      return {status:"ok"};
    }
    function placeCamera(){
      var sp=Math.sin(cam.phi);
      camera.position.set(cam.r*sp*Math.sin(cam.theta),cam.r*Math.cos(cam.phi),cam.r*sp*Math.cos(cam.theta));
      camera.lookAt(0,0,0);
    }
    function frame(now){
      rafId=0;if(dead)return;
      inFrame=true;invalidated=false;
      var dt=Math.min(Math.max(0,(now-prevT)/1000),0.1),moving=false,again=false;
      prevT=now;
      try{
        again=run("before",now,dt,false);if(dead)return;
        applyObserver();
        if(controller && controller.ownsCamera && controller.ownsCamera()){
          moving=!!(controller.tick && controller.tick(now));
        }else{
          [["r","tr"],["theta","tth"],["phi","tph"]].forEach(function(p){
            var d=cam[p[1]]-cam[p[0]];
            if(reduced||Math.abs(d)<1e-4)cam[p[0]]=cam[p[1]];
            else{cam[p[0]]+=d*0.08;moving=true;}
          });
          placeCamera();
        }
        again=run("update",now,dt,moving)||again;if(dead)return;
        var obstacles=layoutLabels();
        if(controller && controller.layout)controller.layout(obstacles);
        if(dead)return;
        renderer.render(scene,camera);stats.frames++;
        again=run("after",now,dt,moving)||again;
      }finally{
        phase="";inFrame=false;prevT=now;
        if(!dead && (again||moving||invalidated) && !rafId){
          stats.requests++;rafId=requestAnimationFrame(frame);
        }
      }
    }
    function resize(){
      if(dead)return;
      var w=view.clientWidth,h=view.clientHeight;
      if(!w||!h)return;
      renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();kick();
    }
    function setController(next){
      alive();
      if(next!==null && (!next || typeof next!=="object"))throw new TypeError("SphereWorld: controller must be object or null");
      if(next)Object.keys(next).forEach(function(name){
        if(["ownsCamera","tick","layout","dragThreshold","drag","zoom","key","click"].indexOf(name)<0 || typeof next[name]!=="function")
          throw new TypeError("SphereWorld: invalid controller."+name);
      });
      controller=next;kick();return {status:"ok"};
    }
    function setWheelPolicy(fn){
      alive();if(fn!==null && typeof fn!=="function")throw new TypeError("SphereWorld: wheel policy must be function or null");
      wheelPolicy=fn;return {status:"ok"};
    }
    function stepCam(dir,a){
      alive();
      if(dir==="left")cam.tth+=a;else if(dir==="right")cam.tth-=a;
      else if(dir==="up")cam.tph=clamp(cam.tph+a,0.12,Math.PI-0.12);
      else if(dir==="down")cam.tph=clamp(cam.tph-a,0.12,Math.PI-0.12);
      kick();
    }
    function installGestures(){
      var ptrs={},nptr=0,active=null,lx=0,ly=0,pinch=0,gest=null;
      listen(view,"pointerdown",function(e){
        if(e.target!==view && e.target!==renderer.domElement)return;
        if(!ptrs[e.pointerId]){ptrs[e.pointerId]=true;nptr++;}
        active=nptr===1?e.pointerId:null;
        if(nptr===1)gest={id:e.pointerId,x:e.clientX,y:e.clientY,max:0,multi:false};
        else if(gest)gest.multi=true;
        lx=e.clientX;ly=e.clientY;emit("start",e);
        if(view.setPointerCapture)view.setPointerCapture(e.pointerId);
      });
      listen(view,"pointermove",function(e){
        if(active===null||e.pointerId!==active)return;
        var mx=e.clientX-lx,my=e.clientY-ly;lx=e.clientX;ly=e.clientY;
        if(gest)gest.max=Math.max(gest.max,Math.hypot(e.clientX-gest.x,e.clientY-gest.y));
        var threshold=controller&&controller.dragThreshold?controller.dragThreshold():0;
        if(gest && gest.max<=threshold)return;
        if(controller&&controller.drag&&controller.drag(mx,my)===true)return;
        cam.tth-=mx*0.006;cam.tph=clamp(cam.tph-my*0.006,0.12,Math.PI-0.12);kick();
      });
      function end(e){
        var g=gest,click=e.type==="pointerup"&&!!g&&g.id===e.pointerId&&!g.multi&&g.max<=5;
        if(g&&(g.id===e.pointerId||e.type==="pointercancel"))gest=null;
        if(click&&controller&&controller.click){
          var rc=renderer.domElement.getBoundingClientRect();controller.click(e.clientX-rc.left,e.clientY-rc.top);
        }
        if(ptrs[e.pointerId]){delete ptrs[e.pointerId];nptr--;}
        if(e.pointerId===active||nptr===0)active=null;
        if(!nptr)emit("end",e);
      }
      listen(view,"pointerup",end);listen(view,"pointercancel",end);
      listen(view,"wheel",function(e){
        if(wheelPolicy&&wheelPolicy(e)===false)return;
        e.preventDefault();
        if(controller&&controller.zoom&&controller.zoom(e.deltaY,"wheel")===true)return;
        cam.tr=clamp(cam.tr+e.deltaY*0.0022,1.7,9);kick();
      },{passive:false});
      listen(view,"touchmove",function(e){
        if(e.touches.length!==2)return;
        var dx=e.touches[0].clientX-e.touches[1].clientX,dy=e.touches[0].clientY-e.touches[1].clientY,d=Math.sqrt(dx*dx+dy*dy);
        if(pinch && !(controller&&controller.zoom&&controller.zoom(d-pinch,"pinch")===true))cam.tr=clamp(cam.tr-(d-pinch)*0.006,1.7,9);
        pinch=d;e.preventDefault();kick();
      },{passive:false});
      listen(view,"touchend",function(){pinch=0;});
      var dirs={ArrowLeft:"left",ArrowRight:"right",ArrowUp:"up",ArrowDown:"down"};
      listen(renderer.domElement,"keydown",function(e){
        if(e.altKey||e.ctrlKey||e.metaKey)return;
        if(controller&&controller.key&&controller.key(e.key)===true){e.preventDefault();return;}
        if(dirs[e.key])stepCam(dirs[e.key],0.1);
        else if(e.key==="+"||e.key==="=")cam.tr=clamp(cam.tr-0.3,1.7,9);
        else if(e.key==="-"||e.key==="_"||e.key==="−")cam.tr=clamp(cam.tr+0.3,1.7,9);
        else return;
        e.preventDefault();kick();
      });
      listen(renderer.domElement,"focus",function(e){emit("focus",e);});
      listeners.push(function(){
        Object.keys(ptrs).forEach(function(id){
          if(view.hasPointerCapture && view.hasPointerCapture(+id))view.releasePointerCapture(+id);
        });
        ptrs={};gest=null;active=null;nptr=0;
      });
    }
    function registerLabel(sp,options){
      alive();options=options||{};
      if(!sp||!sp.isSprite)throw new TypeError("SphereWorld: label must be a sprite");
      if(options.order!=null&&!finite(options.order))throw new TypeError("SphereWorld: label order must be finite");
      var item={sp:sp,fixed:!!options.fixed,order:options.order||0};
      labelRegistry.push(item);kick();var attached=true;
      return function(){if(!attached)return;attached=false;var i=labelRegistry.indexOf(item);if(i>=0)labelRegistry.splice(i,1);kick();};
    }
    function unregisterTextLabel(sp){
      alive();var i=LABELS.indexOf(sp);if(i>=0)LABELS.splice(i,1);
      labelRegistry=labelRegistry.filter(function(item){return item.sp!==sp;});kick();
    }
    function keyLabel(key,role,px,weight,family){
      var sp=tlabel(key,C[role],px,weight,family);labelData(sp).colourRole=role;return sp;
    }
    function labelData(sp){return sp.userData.i18n||sp.userData.worldText;}
    function themeMaterial(material,role){themedMaterials.push({material:material,role:role});return material;}
    function setColours(patch){
      alive();if(!patch||typeof patch!=="object")throw new TypeError("SphereWorld: colour patch must be an object");
      var next={},key;
      for(key in C)if(Object.prototype.hasOwnProperty.call(C,key))next[key]=C[key];
      for(key in patch)if(Object.prototype.hasOwnProperty.call(patch,key))next[key]=patch[key];
      next=palette(next);Object.keys(next).forEach(function(name){C[name]=next[name];});
      themedMaterials.forEach(function(entry){entry.material.color.set(C[entry.role]);});
      LABELS.forEach(function(sp){var d=labelData(sp);if(d.colourRole)d.color=C[d.colourRole];});
      relabelAll();kick();return {status:"ok"};
    }
    function setReducedMotion(value){
      alive();if(typeof value!=="boolean")throw new TypeError("SphereWorld: reduced motion must be boolean");
      reduced=value;kick();return {status:"ok"};
    }
    function setLayers(patch){
      alive();if(!patch||typeof patch!=="object")throw new TypeError("SphereWorld: layer patch must be object");
      var keys=Object.keys(patch);keys.forEach(function(name){
        if(!Object.prototype.hasOwnProperty.call(L,name)||!L[name].isGroup||typeof patch[name]!=="boolean")
          throw new TypeError("SphereWorld: invalid layer "+name);
      });
      keys.forEach(function(name){PREF[name]=patch[name];L[name].visible=patch[name];});kick();return {status:"ok"};
    }
      var vE = new THREE.Vector3(1,0,0), vW = new THREE.Vector3(-1,0,0);
  var vN = new THREE.Vector3(0,0,-1), vS = new THREE.Vector3(0,0,1);
  var vZen = new THREE.Vector3(0,1,0), vNad = new THREE.Vector3(0,-1,0);

  var _A = new THREE.Vector3(), _B = new THREE.Vector3(), _P = new THREE.Vector3();
  var _M = new THREE.Vector3(), _Wv = new THREE.Vector3(-1,0,0);
  var equMatrix = new THREE.Matrix4();

  function buildEquBasis(latDeg, lstDeg){
    var f = latDeg*D2R, t = lstDeg*D2R;
    // upper-meridian point of the equator: due south, altitude 90-lat
    _M.set(0, Math.cos(f), Math.sin(f));
    // north celestial pole: due north, altitude = lat
    _P.set(0, Math.sin(f), -Math.cos(f));
    // vernal point (RA 0) sits at hour angle H = LST
    _A.copy(_M).multiplyScalar(Math.cos(t)).addScaledVector(_Wv, Math.sin(t));
    // RA 90 sits at H = LST - 90
    _B.copy(_M).multiplyScalar(Math.sin(t)).addScaledVector(_Wv, -Math.cos(t));
    equMatrix.makeBasis(_A,_B,_P);
    return equMatrix;
  }
  // equatorial unit vector in the equ-group's own local frame
  function equLocal(raDeg, decDeg, out){
    var a = raDeg*D2R, d = decDeg*D2R, c = Math.cos(d);
    return (out||new THREE.Vector3()).set(c*Math.cos(a), c*Math.sin(a), Math.sin(d));
  }
  // ecliptic (lon,lat) -> equatorial local, via rotation about local X by obliquity
  function eclToEqu(lonDeg, latDeg, oblDeg, out){
    var l = lonDeg*D2R, b = latDeg*D2R, e = oblDeg*D2R, cb = Math.cos(b);
    var x = cb*Math.cos(l), y = cb*Math.sin(l), z = Math.sin(b);
    return (out||new THREE.Vector3()).set(x, y*Math.cos(e) - z*Math.sin(e), y*Math.sin(e) + z*Math.cos(e));
  }
  function equToEcl(v, oblDeg){
    var e = oblDeg*D2R, ce = Math.cos(e), se = Math.sin(e);
    var ye = v.y*ce + v.z*se, ze = -v.y*se + v.z*ce;
    return { lon: norm360(Math.atan2(ye, v.x)*R2D), lat: Math.asin(clamp(ze,-1,1))*R2D };
  }
  function equToRaDec(v){
    return { ra: norm360(Math.atan2(v.y, v.x)*R2D), dec: Math.asin(clamp(v.z,-1,1))*R2D };
  }
  function worldToHor(v){
    // at the zenith or the nadir the direction has no horizontal part, so azimuth has no value (judged on the vector)
    var h = Math.sqrt(v.x*v.x + v.z*v.z);
    return { alt: Math.asin(clamp(v.y,-1,1))*R2D, az: norm360(Math.atan2(v.x, -v.z)*R2D), pole: h < 1e-9 ? (v.y > 0 ? "zenith" : "nadir") : null };
  }
  function norm360(x){ x = x % 360; return x < 0 ? x + 360 : x; }
  function clamp(x,a,b){ return x<a?a:(x>b?b:x); }

  var _tmp = new THREE.Vector3();
  function eclWorld(lon){
    eclToEqu(lon, 0, S.obl, _tmp);
    return _tmp.applyMatrix4(equMatrix);
  }
  // equMatrix is a rotation (columns A, B, P), so its inverse is its transpose
  function worldToEqu(v, out){
    var m = equMatrix.elements;
    return out.set(m[0]*v.x + m[1]*v.y + m[2]*v.z, m[4]*v.x + m[5]*v.y + m[6]*v.z, m[8]*v.x + m[9]*v.y + m[10]*v.z);
  }


      function fmtZod(lon){
    var m = Math.round(norm360(lon)*60) % 21600;          // whole minutes of arc
    return pad(Math.floor((m % 1800)/60),2)+"° "+T("sphere.glyph."+Math.floor(m/1800))+" "+pad(m % 60,2)+"′";
  }

      function ring(radius, tube, color, opacity, role){
    alive();
    var g = new THREE.TorusGeometry(radius, tube, 6, 180);
    var m = new THREE.MeshBasicMaterial({ color:color, transparent:opacity<1, opacity:opacity==null?1:opacity });
    if(role)themeMaterial(m,role);
    return new THREE.Mesh(g, m);
  }
  function seg(points, color, opacity, role){
    alive();
    var g = new THREE.BufferGeometry().setFromPoints(points);
    var m = new THREE.LineBasicMaterial({ color:color, transparent:true, opacity:opacity==null?1:opacity });
    if(role)themeMaterial(m,role);
    return new THREE.Line(g, m);
  }
  function label(text, cssColor, px, weight, family){
    alive();
    var pxs = px||46, fam = family || UIFONT;
    var cv = document.createElement("canvas"), ctx = cv.getContext("2d");
    ctx.font = (weight||500)+" "+pxs+"px "+fam;
    var w = Math.ceil(ctx.measureText(text).width)+16, h = Math.ceil(pxs*1.5);
    cv.width = w; cv.height = h;
    ctx = cv.getContext("2d");
    ctx.font = (weight||500)+" "+pxs+"px "+fam;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.shadowColor = cssColour(C.labelShadow); ctx.shadowBlur = 8;
    ctx.fillStyle = cssColour(cssColor); ctx.fillText(text, w/2, h/2);
    // where the ink lies inside the texture (fractions), so labels can keep clear of each other
    var mt = ctx.measureText(text), ink = [8/w, 0.17, 1-8/w, 0.83];
    if(mt.actualBoundingBoxAscent != null){
      ink = [(w/2 - mt.actualBoundingBoxLeft)/w, (h/2 - mt.actualBoundingBoxAscent)/h, (w/2 + mt.actualBoundingBoxRight)/w, (h/2 + mt.actualBoundingBoxDescent)/h];
    }
    var tex = new THREE.CanvasTexture(cv);
    tex.minFilter = THREE.LinearFilter;
    var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map:tex, transparent:true, depthTest:false }));
    var k = 0.0016;
    sp.scale.set(w*k, h*k, 1);
    sp.renderOrder = 20;
    sp.userData.ink = ink;
    return sp;
  }
  var LABELS = [];
  function tlabel(key, cssColor, px, weight, family){
    alive();
    var sp = label(T(key), cssColor, px, weight, family);
    var data = { key:key, color:cssColor, px:px, weight:weight, family:family };
    if(key.indexOf("sphere.")===0)sp.userData.worldText=data;else sp.userData.i18n=data;
    LABELS.push(sp);
    return sp;
  }
  function redrawLabel(sp){
    var d = labelData(sp);
    var made = label(T(d.key), d.color, d.px, d.weight, d.family);
    if(sp.material.map) sp.material.map.dispose();
    sp.material.map = made.material.map;
    sp.material.needsUpdate = true;
    made.material.dispose();
    sp.scale.copy(made.scale);
    sp.userData.ink = made.userData.ink;
  }
  function relabelAll(){ alive(); LABELS.forEach(redrawLabel); }
  // in the southern hemisphere the south pole is the raised one, and gets the bright label;
  // that label then stands a little further out, and the meridian's name crosses to the
  // north side, so that neither prints over the other or the W
  var poleSouth = false;
  function setPoleLabels(south){
    poleSouth = south;
    L.spoleLbl.position.set(0, 0, -(south ? 1.36 : 1.24));
    L.meridianLbl.position.copy(MERIDIAN_LBL).multiplyScalar(1.02);
    if(south) L.meridianLbl.position.z = -L.meridianLbl.position.z;
    [[L.npoleLbl, south ? POLE_DOWN : POLE_UP], [L.spoleLbl, south ? POLE_UP : POLE_DOWN]].forEach(function(o){
      var d = o[0].userData.i18n;
      if(d.colourRole === o[1][0] && d.px === o[1][1]) return;
      d.colourRole = o[1][0]; d.color = C[d.colourRole]; d.px = o[1][1];
      redrawLabel(o[0]);
    });
  }
  function put(obj, vec, out){
    alive();
    obj.position.copy(vec).multiplyScalar(out==null?1.09:out);
    return obj;
  }
  function group(parent, name, visible){
    alive();
    var g = new THREE.Group(); g.visible = !!visible; parent.add(g); L[name] = g; return g;
  }


      // Label colours: the dim ones (lower pole, nadir, the quadrants below the earth) are
  // still at least 4.5:1 on the sky; the bright ones are well above that.
  // -- horizon frame ------------------------------------------------------
  // Where the meridian and prime-vertical names sit: low on their own circles, 20° above
  // the south and east points, clear of the cardinal letters in every orbit view
  // and of the point where the equator (and 0° RA, and the Sun at 0° Aries) crosses the
  // meridian at the default latitude. South of the equator the meridian's name moves to
  // the north side, out of the way of the raised south pole (see setPoleLabels).
  var MERIDIAN_LBL = new THREE.Vector3(0,0.342,0.940).normalize();
  var PV_LBL = new THREE.Vector3(0.940,0.342,0).normalize();
  (function(){
    var g = group(horGroup, "horizon", true);
    var h = ring(R, 0.0075, C.brass, 1, "brass"); h.rotation.x = Math.PI/2; g.add(h);

    var gr = group(horGroup, "ground", true);
    var disk = new THREE.Mesh(
      new THREE.CircleGeometry(R*0.998, 96),
      themeMaterial(new THREE.MeshBasicMaterial({ color:C.ground, transparent:true, opacity:0.72, side:THREE.DoubleSide, depthWrite:false }),"ground")
    );
    disk.rotation.x = -Math.PI/2; gr.add(disk);

    var m = group(horGroup, "meridian", false);
    var mr = ring(R, 0.0055, C.brass, 0.95, "brass"); mr.rotation.y = Math.PI/2; m.add(mr);
    L.meridianLbl = put(keyLabel("lbl.meridian", "labelBrass", 36), MERIDIAN_LBL, 1.02); m.add(L.meridianLbl);

    var pv = group(horGroup, "primeVertical", false);
    var pr = ring(R, 0.004, C.brassDim, 0.9, "brassDim"); pv.add(pr);
    pv.add(put(keyLabel("lbl.pv", "labelPrime", 32), PV_LBL, 1.02));

    var c = group(horGroup, "cardinals", true);
    c.add(put(keyLabel("lbl.N", "labelBrass", 58, 600), vN));
    c.add(put(keyLabel("lbl.E", "labelBrass", 58, 600), vE));
    c.add(put(keyLabel("lbl.S", "labelBrass", 58, 600), vS));
    c.add(put(keyLabel("lbl.W", "labelBrass", 58, 600), vW));

    var z = group(horGroup, "zenith", false);
    z.add(seg([vNad.clone().multiplyScalar(R), vZen.clone().multiplyScalar(R)], C.brassDim, 0.8, "brassDim"));
    z.add(put(keyLabel("lbl.zenith", "labelBrass", 38), vZen, 1.10));
    z.add(put(keyLabel("lbl.nadir", "labelDim", 34), vNad, 1.10));

    var q = group(horGroup, "quadrants", false);
    // each label inside its quadrant: eastern above and east, southern above and west,
    // western below and west, northern below and east
    var qn = [["lbl.qe","labelQuadrant",new THREE.Vector3(0.709,0.50,0.497)],
              ["lbl.qs","labelQuadrant",new THREE.Vector3(-0.62,0.50,0.60)],
              ["lbl.qw","labelDim",new THREE.Vector3(-0.62,-0.50,0.60)],
              ["lbl.qn","labelDim",new THREE.Vector3(0.62,-0.50,-0.60)]];
    qn.forEach(function(o){ q.add(put(keyLabel(o[0], o[1], 28), o[2].normalize(), 1.0)); });

  })();

  // -- equatorial frame ---------------------------------------------------
  var POLE_UP = ["labelSteel", 36], POLE_DOWN = ["labelSteelDim", 32];
  // RA figures sit a little south of the equator and outside the ticks, so the one
  // standing at the east or west point does not print over the cardinal letter there
  var RA_LBL_DEC = -7, RA_LBL_R = 1.22, RA_LBLS = [];
  (function(){
    var e = group(equGroup, "equator", false);
    var er = ring(R, 0.0075, C.steel, 1, "steel"); e.add(er);
    L.equatorLbl = put(keyLabel("lbl.equator", "labelSteel", 36), new THREE.Vector3(-0.86,-0.51,0).normalize(), 1.05); e.add(L.equatorLbl);

    var p = group(equGroup, "poles", false);
    p.add(seg([new THREE.Vector3(0,0,-R*1.18), new THREE.Vector3(0,0,R*1.18)], C.steel, 0.85, "steel"));
    // the pole above the horizon gets the bright label (see setPoleLabels)
    L.npoleLbl = put(keyLabel("lbl.npole", POLE_UP[0], POLE_UP[1]), new THREE.Vector3(0,0,1), 1.24); p.add(L.npoleLbl);
    L.spoleLbl = put(keyLabel("lbl.spole", POLE_DOWN[0], POLE_DOWN[1]), new THREE.Vector3(0,0,-1), 1.24); p.add(L.spoleLbl);

    var d = group(equGroup, "decCircles", false);
    [-75,-60,-45,-30,-15,15,30,45,60,75].forEach(function(dec){
      var rr = ring(R*Math.cos(dec*D2R), 0.0022, C.steelDim, 0.55, "steelDim");
      rr.position.z = R*Math.sin(dec*D2R); d.add(rr);
    });

    var t = group(equGroup, "raTicks", false);
    for(var a=0;a<360;a+=10){
      var v = equLocal(a,0), big = (a%90===0);
      t.add(seg([v.clone().multiplyScalar(R*(big?1.0:1.0)), v.clone().multiplyScalar(R*(big?1.085:1.04))], big?C.steel:C.steelDim, big?1:0.6, big?"steel":"steelDim"));
    }
    [0,90,180,270].forEach(function(ra){
      var sp = put(keyLabel("sphere.ra."+ra, "labelSteel", 28), equLocal(ra,RA_LBL_DEC), RA_LBL_R);
      RA_LBLS.push(sp); t.add(sp);
    });
  })();

  // -- ecliptical frame ---------------------------------------------------
  (function(){
    var e = group(eclGroup, "ecliptic", false);
    var er = ring(R, 0.0065, C.madder, 1, "madder"); e.add(er);

    var b = group(eclGroup, "zodiacBand", false);
    var band = new THREE.Mesh(
      new THREE.SphereGeometry(R*0.995, 96, 20, 0, TAU, (90-8)*D2R, 16*D2R),
      themeMaterial(new THREE.MeshBasicMaterial({ color:C.madder, transparent:true, opacity:0.115, side:THREE.DoubleSide, depthWrite:false }),"madder")
    );
    band.rotation.x = Math.PI/2; b.add(band);
    for(var s=0;s<12;s++){
      var lon = s*30, p1 = eclV(lon,-8.6), p2 = eclV(lon,8.6);
      b.add(seg([p1,p2], C.madderDim, 0.85, "madderDim"));
    }

    var gl = group(eclGroup, "signGlyphs", false);
    for(var i=0;i<12;i++){
      var sp = keyLabel("sphere.glyph."+i, "labelMadder", 58, 400, SYMFONT);
      sp.position.copy(eclV(i*30+15, 13.5)).multiplyScalar(1.05);
      gl.add(sp);
    }

  })();

      function eclV(lon, lat){
    var l = lon*D2R, b = lat*D2R, cb = Math.cos(b);
    return new THREE.Vector3(cb*Math.cos(l), cb*Math.sin(l), Math.sin(b)).multiplyScalar(R);
  }

      var _lv = new THREE.Vector3(), _lc = new THREE.Vector3();
  var NUDGES = [[0,0]];
  [0.7, 1.1, 1.6, 2.2].forEach(function(m){
    [[0,-1],[0,1],[1,0],[-1,0],[1,-1],[-1,-1],[1,1],[-1,1]].forEach(function(d){ NUDGES.push([d[0]*m, d[1]*m]); });
  });
  function shown(o){ for(; o; o = o.parent) if(!o.visible) return false; return true; }
  function screenBox(sp, W, H, tanH){
    sp.getWorldPosition(_lv);
    _lc.copy(_lv).applyMatrix4(camera.matrixWorldInverse);
    var depth = -_lc.z; if(depth <= 0) return null;
    var ppw = H/(2*depth*tanH);
    _lv.project(camera);
    var x = (_lv.x+1)/2*W, y = (1-_lv.y)/2*H, w = sp.scale.x*ppw, h = sp.scale.y*ppw, k = sp.userData.ink || [0,0,1,1];
    return { x0:x-w/2+k[0]*w, y0:y-h/2+k[1]*h, x1:x-w/2+k[2]*w, y1:y-h/2+k[3]*h, w:w, h:h };
  }
  function layoutLabels(){
    var FIXED_LBLS = labelRegistry.filter(function(item){return item.fixed;}).map(function(item){return item.sp;});
    var MOVING_LBLS = labelRegistry.filter(function(item){return !item.fixed;}).sort(function(a,b){return a.order-b.order;}).map(function(item){return item.sp;});
    var W = view.clientWidth, H = view.clientHeight, G = 3;
    if(!W || !H) return [];
    camera.updateMatrixWorld();
    var tanH = Math.tan(camera.fov*D2R/2), placed = [];
    function cost(b){
      var c = 0;
      for(var i=0;i<placed.length;i++){
        var p = placed[i], ox = Math.min(b.x1, p.x1) - Math.max(b.x0, p.x0) + G, oy = Math.min(b.y1, p.y1) - Math.max(b.y0, p.y0) + G;
        if(ox > 0 && oy > 0) c += ox*oy;
      }
      var ex = Math.max(0, -b.x0) + Math.max(0, b.x1 - W), ey = Math.max(0, -b.y0) + Math.max(0, b.y1 - H);
      return c + 50*(ex + ey);
    }
    FIXED_LBLS.forEach(function(sp){ if(shown(sp)){ var b = screenBox(sp, W, H, tanH); if(b) placed.push(b); } });
    MOVING_LBLS.forEach(function(sp){
      if(!shown(sp)) return;
      var base = screenBox(sp, W, H, tanH); if(!base) return;
      var bw = base.x1 - base.x0, bh = base.y1 - base.y0, prev = sp.userData.nudge || 0;
      var order = [0]; if(prev) order.push(prev);
      for(var i=1;i<NUDGES.length;i++) if(i !== prev) order.push(i);
      var best = 0, bestBox = base, bestCost = Infinity;
      for(var j=0;j<order.length;j++){
        var n = NUDGES[order[j]], dx = n[0]*(bw*0.6 + G), dy = n[1]*(bh + G);
        var b = { x0:base.x0+dx, x1:base.x1+dx, y0:base.y0+dy, y1:base.y1+dy, dx:dx, dy:dy };
        var c = cost(b);
        if(c < bestCost){ bestCost = c; best = order[j]; bestBox = b; }
        if(c === 0) break;
      }
      sp.userData.nudge = best;
      sp.center.set(0.5 - (bestBox.dx||0)/base.w, 0.5 + (bestBox.dy||0)/base.h);
      placed.push(bestBox);
    });
    return placed;            // the Tower's labels keep clear of these
  }


    LABELS.filter(function(sp){return /^lbl\.(N|E|S|W|zenith|nadir|meridian|pv|q[eswn])$/.test(labelData(sp).key);}).forEach(function(sp){
      registerLabel(sp,{fixed:true});
    });
    [L.npoleLbl,L.spoleLbl].concat(RA_LBLS,[L.equatorLbl]).forEach(function(sp,i){registerLabel(sp,{order:i+10});});
    Object.keys(L).forEach(function(name){if(L[name].isGroup)PREF[name]=L[name].visible;});
    scene.traverse(function(o){ownedObjects.push(o);});
    function dispose(){
      if(dead)return;dead=true;
      if(rafId)cancelAnimationFrame(rafId);rafId=0;
      listeners.forEach(function(remove){remove();});listeners=[];
      if(resizeObserver)resizeObserver.disconnect();
      var seen=[];
      function release(resource){if(resource&&seen.indexOf(resource)<0){seen.push(resource);resource.dispose();}}
      ownedObjects.forEach(function(o){
        release(o.geometry);
        var materials=o.material?(Array.isArray(o.material)?o.material:[o.material]):[];
        materials.forEach(function(m){release(m.map);release(m);});
      });
      renderer.dispose();
      if(renderer.domElement.parentNode===view)view.removeChild(renderer.domElement);
      controller=null;interactions=[];hooks={before:[],update:[],after:[]};labelRegistry=[];LABELS=[];ownedObjects=[];
    }
    var partial={S:S,PREF:PREF,TW_SHARED:TW_SHARED,C:C,cam:cam,camera:camera,scene:scene,renderer:renderer,view:view,
      equGroup:equGroup,eclGroup:eclGroup,reduced:function(){return reduced;},T:T,label:label,fmtZod:fmtZod,eclV:eclV,equLocal:equLocal,kick:kick};
    var api={schemaVersion:1,towerHost:partial,S:S,C:C,PREF:PREF,TW_SHARED:TW_SHARED,cam:cam,scene:scene,camera:camera,
      renderer:renderer,view:view,horGroup:horGroup,equGroup:equGroup,eclGroup:eclGroup,L:L,equMatrix:equMatrix,
      vE:vE,vW:vW,vN:vN,vS:vS,vZen:vZen,vNad:vNad,
      buildEquBasis:buildEquBasis,equLocal:equLocal,eclToEqu:eclToEqu,equToEcl:equToEcl,equToRaDec:equToRaDec,
      worldToHor:worldToHor,eclWorld:eclWorld,worldToEqu:worldToEqu,eclV:eclV,fmtZod:fmtZod,
      ring:ring,seg:seg,put:put,group:group,label:label,tlabel:tlabel,relabelAll:relabelAll,layoutLabels:layoutLabels,
      registerLabel:registerLabel,unregisterTextLabel:unregisterTextLabel,onFrame:onFrame,
      onInteraction:function(fn){return subscription(interactions,fn);},setController:setController,setWheelPolicy:setWheelPolicy,
      stepCam:stepCam,placeCamera:placeCamera,setObserver:setObserver,setColours:setColours,setReducedMotion:setReducedMotion,
      setLayers:setLayers,resize:resize,kick:kick,pending:function(){return !!rafId;},stats:function(){return {frames:stats.frames,requests:stats.requests};},dispose:dispose};
    view.appendChild(renderer.domElement);
    renderer.domElement.setAttribute("role","img");renderer.domElement.setAttribute("tabindex","0");
    listen(renderer.domElement,"webglcontextrestored",kick);
    installGestures();
    if(window.ResizeObserver){resizeObserver=new window.ResizeObserver(resize);resizeObserver.observe(view);}
    else listen(window,"resize",resize);
    applyObserver();placeCamera();resize();
    return api;
  }
  return {schemaVersion:1,create:create};
})();
