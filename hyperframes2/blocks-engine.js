/* HF3D — NBS 3D 方块引擎（HyperFrames 用，确定性：只依赖传入时间 t） */
(function (global) {
  "use strict";

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function lerp(a, b, k) { return a + (b - a) * k; }
  function easeOutBack(x) { var c = 1.70158, u = x - 1; return 1 + (c + 1) * u * u * u + c * u * u; }

  function create(opts) {
    var canvas = opts.canvas;
    var D = opts.data;
    var W = opts.width || 1920, H = opts.height || 1080;

    var renderer = new THREE.WebGLRenderer({
      canvas: canvas, antialias: true, preserveDrawingBuffer: true, alpha: true
    });
    renderer.setPixelRatio(1);
    renderer.setSize(W, H, false);
    if (THREE.sRGBEncoding) renderer.outputEncoding = THREE.sRGBEncoding;

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(34, W / H, 0.1, 200);

    scene.add(new THREE.AmbientLight(0xffffff, 0.86));
    var key = new THREE.DirectionalLight(0xffffff, 0.52);
    key.position.set(3.2, 6.5, 4.2);
    scene.add(key);
    var rim = new THREE.DirectionalLight(0xffffff, 0.22);
    rim.position.set(-4, 2.4, -5);
    scene.add(rim);

    /* ---------- optional post (chromatic / glitch) ---------- */
    var post = null;
    if (opts.post === "chroma") {
      var rt = new THREE.WebGLRenderTarget(W, H, {
        minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter
      });
      var qScene = new THREE.Scene();
      var qCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
      var qMat = new THREE.ShaderMaterial({
        uniforms: { tDiffuse: { value: rt.texture }, uTime: { value: 0 } },
        vertexShader:
          "varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.0,1.0);}",
        fragmentShader: [
          "uniform sampler2D tDiffuse;uniform float uTime;varying vec2 vUv;",
          "void main(){",
          "  vec2 uv=vUv;",
          "  float line=floor(uv.y*240.0);",
          "  float n=fract(sin(line*12.9898+floor(uTime*12.0)*3.17)*43758.5453);",
          "  float slice=step(0.972,n);",
          "  uv.x+=(n-0.5)*0.0075*slice;",
          "  vec3 c;",
          "  c.r=texture2D(tDiffuse,uv+vec2(0.0026,0.0)).r;",
          "  c.g=texture2D(tDiffuse,uv).g;",
          "  c.b=texture2D(tDiffuse,uv-vec2(0.0026,0.0)).b;",
          "  c*=0.93+0.07*sin(uv.y*820.0);",
          "  vec2 d=uv-0.5;c*=1.0-dot(d,d)*0.7;",
          "  gl_FragColor=vec4(c,1.0);",
          "}"
        ].join("\n")
      });
      qScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), qMat));
      post = { rt: rt, scene: qScene, cam: qCam, mat: qMat };
    }

    /* ---------- layout ---------- */
    var groups = D.groups, tracks = D.tracks;
    var GAP_X = 1.62, GAP_Z = 1.9;
    var maxCols = 1;
    groups.forEach(function (g) { maxCols = Math.max(maxCols, g.tracks.length); });

    var loader = new THREE.TextureLoader();
    var boxGeo = new THREE.BoxGeometry(1, 1, 1);
    var outlineGeo = new THREE.BoxGeometry(1, 1, 1);
    var shadowGeo = new THREE.BoxGeometry(1, 1, 1);

    var blocks = [];       // per track
    var groupObjs = [];

    function place(groupIdx, n) {
      return { z: (groupIdx - (groups.length - 1) / 2) * GAP_Z };
    }

    groups.forEach(function (g, gi) {
      var holder = new THREE.Group();
      holder.position.z = (gi - (groups.length - 1) / 2) * GAP_Z;
      scene.add(holder);
      groupObjs.push(holder);

      g.tracks.forEach(function (ti, k) {
        var t = tracks[ti];
        var root = new THREE.Group();
        var cols = g.tracks.length;
        root.position.x = (k - (cols - 1) / 2) * GAP_X;
        root.position.y = 0;
        holder.add(root);

        var tex = loader.load(t.texture);
        if (THREE.sRGBEncoding) tex.encoding = THREE.sRGBEncoding;
        tex.magFilter = THREE.NearestFilter;
        tex.minFilter = THREE.NearestFilter;
        tex.generateMipmaps = false;
        tex.onUpdate = function () { invalidate(); };

        var mat = new THREE.MeshLambertMaterial({ map: tex });
        var mesh = new THREE.Mesh(boxGeo, mat);
        root.add(mesh);

        var outline = null;
        if (opts.outline) {
          outline = new THREE.Mesh(outlineGeo, new THREE.MeshBasicMaterial({
            color: 0x000000, side: THREE.BackSide
          }));
          outline.scale.setScalar(1.085);
          root.add(outline);
        }

        var shadow = null;
        if (opts.shadow) {
          shadow = new THREE.Mesh(shadowGeo, new THREE.MeshBasicMaterial({
            color: 0x000000, transparent: true, opacity: 0.92
          }));
          shadow.scale.set(1, 1, 1);
          shadow.renderOrder = -1;
          scene.add(shadow);
        }

        blocks[ti] = {
          root: root, mesh: mesh, outline: outline, shadow: shadow, mat: mat,
          starts: t.notes.map(function (n) { return n[0]; }),
          keys: t.notes.map(function (n) { return n[1]; }),
          vels: t.notes.map(function (n) { return n[2]; }),
          groupIndex: gi,
          baseY: 0,
          screen: { x: 0, y: 0, visible: false },
          energy: 0
        };
      });
    });

    /* ---------- camera fit ---------- */
    var halfW = (maxCols * GAP_X) / 2 + 0.9;
    var halfD = (groups.length * GAP_Z) / 2 + 0.9;
    var radius = Math.sqrt(halfW * halfW + halfD * halfD);
    var fitDist = radius / Math.tan((camera.fov * Math.PI) / 360) * 1.06;

    var camState = { dist: fitDist, yaw: 0, pitch: 0.36, panX: 0, panY: 0 };

    function lowerBound(arr, x) {
      var lo = 0, hi = arr.length;
      while (lo < hi) { var mid = (lo + hi) >> 1; if (arr[mid] < x) lo = mid + 1; else hi = mid; }
      return lo;
    }

    var PRESS_T = 0.07, HOLD_T = 0.13, REL_T = 0.46;

    function impulseAt(b, t) {
      var s = 1, glow = 0, vel = 0, idx = -1;
      var i0 = lowerBound(b.starts, t - 0.8);
      for (var i = i0; i < b.starts.length; i++) {
        var st = b.starts[i];
        if (st > t) break;
        var age = t - st;
        var si;
        if (age < PRESS_T) si = 1 - 0.2 * (age / PRESS_T);
        else if (age < HOLD_T) si = 0.8;
        else si = 0.8 + 0.2 * easeOutBack(clamp((age - HOLD_T) / REL_T, 0, 1));
        if (si < s) s = si;
        var g = age < PRESS_T ? age / PRESS_T : Math.exp(-(age - PRESS_T) / 0.30);
        if (g > glow) { glow = g; vel = b.vels[i]; idx = i; }
      }
      return { s: s, glow: glow, vel: vel, idx: idx };
    }

    var lastT = 0;
    function invalidate() { render(lastT); }

    var tmpV = new THREE.Vector3();

    function render(t) {
      lastT = t;
      var DUR = D.meta.duration;
      var p = clamp(t / Math.max(DUR, 0.001), 0, 1);

      /* --- camera: 连续推拉 + 轻微横移（确定性） --- */
      var dolly = lerp(1.24, 0.94, clamp(p * 1.15, 0, 1));
      var sway = Math.sin(t * 0.42) * 0.10;
      var lift = Math.sin(t * 0.31 + 1.1) * 0.05;
      var yaw = opts.orbit ? (Math.sin(t * 0.23) * 0.55 - 0.25) : (0.12 + sway);
      var pitch = 0.34 + lift + (opts.orbit ? Math.sin(t * 0.17) * 0.06 : 0);

      camState.dist = fitDist * dolly;
      camState.yaw = yaw;
      camState.pitch = pitch;

      camera.position.set(
        Math.sin(yaw) * Math.cos(pitch) * camState.dist,
        Math.sin(pitch) * camState.dist + 0.4,
        Math.cos(yaw) * Math.cos(pitch) * camState.dist
      );
      camera.lookAt(0, 0.15, 0);

      // 屏幕右/下方向，用于硬投影偏移
      var right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
      var up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
      camera.updateMatrixWorld();

      for (var ti = 0; ti < blocks.length; ti++) {
        var b = blocks[ti];
        if (!b) continue;
        var imp = impulseAt(b, t);
        var lift2 = imp.glow * 0.34 * (0.45 + 0.55 * imp.vel);
        var sc = imp.s * (1 + imp.glow * 0.10);

        // 逐块入场：按轨道序号错开
        var born = opts.bornAt ? opts.bornAt(ti) : 0.35 + ti * 0.16;
        var appear = clamp((t - born) / 0.42, 0, 1);
        var ea = easeOutBack(appear);
        sc *= appear <= 0 ? 0.001 : (0.55 + 0.45 * ea);

        b.root.position.y = b.baseY + lift2;
        b.root.scale.setScalar(sc);
        b.root.rotation.y = opts.orbit ? 0 : 0;
        b.root.visible = appear > 0.001;

        // 命中时提亮
        var k = 1 + imp.glow * 0.55;
        b.mat.color.setRGB(k, k, k);

        if (b.outline) {
          b.outline.scale.setScalar(1.085 / Math.max(sc, 0.001) * 1.0);
          b.outline.scale.multiplyScalar(1);
          b.outline.scale.set(1.085, 1.085, 1.085);
        }

        if (b.shadow) {
          b.shadow.visible = b.root.visible;
          b.shadow.position.copy(b.root.position);
          b.shadow.position.addScaledVector(right, 0.20);
          b.shadow.position.addScaledVector(up, -0.20);
          b.shadow.position.addScaledVector(
            new THREE.Vector3().subVectors(camera.position, b.root.position).normalize(), -0.06);
          b.shadow.scale.set(sc, sc, sc);
        }

        // 屏幕坐标（给 HTML 标签用）
        tmpV.set(b.root.position.x, b.root.position.y, b.root.position.z);
        b.root.getWorldPosition(tmpV);
        tmpV.project(camera);
        b.screen.x = (tmpV.x * 0.5 + 0.5) * W;
        b.screen.y = (-tmpV.y * 0.5 + 0.5) * H;
        b.screen.visible = tmpV.z < 1 && b.root.visible;
        b.energy = imp.glow;
      }

      if (post) {
        renderer.setRenderTarget(post.rt);
        renderer.render(scene, camera);
        renderer.setRenderTarget(null);
        post.mat.uniforms.uTime.value = t;
        renderer.render(post.scene, post.cam);
      } else {
        renderer.render(scene, camera);
      }
      if (opts.onFrame) opts.onFrame(t, blocks);
    }

    return { render: render, blocks: blocks, scene: scene, camera: camera, renderer: renderer };
  }

  global.HF3D = { create: create, mulberry32: mulberry32, clamp: clamp, lerp: lerp };
})(window);
