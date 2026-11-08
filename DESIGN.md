# NBS Visualizer v2 — 设计定稿（HyperFrames + three.js）

## 硬约束
- 渲染引擎：**HyperFrames CLI**（`npx hyperframes lint/inspect/render`）。
- 3D：**three.js 官方 API + 官方 adapter contract**，禁止自写渲染引擎/自写场景图/自写后处理。
  - adapter contract（来自 registry `three-orbiting-cards`）：
    `window.__hfThreeRender_<name> = { state, render }`，
    由 paused GSAP timeline `tl.to(state, {progress|t, duration, ease:'none', onUpdate: render})` 驱动。
  - 只用 three.js 原生：WebGLRenderer / Scene / PerspectiveCamera / BoxGeometry / MeshLambertMaterial / TextureLoader / DirectionalLight。
  - 需要后处理时用 three 官方 addons（EffectComposer/RGBShiftShader），不自写 shader 之外的东西。
- 复用 HyperFrames registry 现成组件（已安装在 `hfpkg/`）：
  - `three-orbiting-cards`（three.js seek 范式）
  - `caption-kinetic-slam` / `kinetic-type-swap`（歌词快闪）
  - `glitch` / `rgb-glitch-text` / `caption-glitch-rgb`（故障风）
  - `vfx-liquid-background`（流体背景）
  - `beat-pulse-background`（节拍脉冲背景）

## 参考视频拆解（rea-video 结论）
- 类型：**代码模板渲染**（非实拍/AI），2D 平面卡片网格。
- **只借运镜**：随声部逐个加入，相机连续拉远（3 张 → 18 张）；命中卡片缩放+白边闪。
- 不借其配色/版式（原版偏灰、静态）。

## 视觉定案
### 主风格：BlockFrame（新粗野主义）× 3D MC 方块
- 纸白 `#FFFDF5` + 点阵网格；纯黑 `#000` 4px 边框 / 8px 硬投影；糖果色
  `#FE90E8 #C0F7FE #99E885 #F7CB46 #FFDC8B`。
- 3D 方块：MC 16×16 贴图 `NearestFilter`，黑色 BackSide 描边盒，屏幕空间硬投影。
- 字体：`Noto Sans CJK SC 900`（中文大字）/ `Fira Code`（标签、时间码）/ Nimbus Sans（西文）。
- 装饰：星芒、斜置色块、贴纸式歌词。

### 备选风格（给用户选样片）
- **B · Glitch**：近黑底 + 青/品红像散 + 扫描线 + 切片错位；orbited camera。
- **C · Liquid**：流体背景（radial-gradient 错峰）+ 玻璃方块 + 衬线巨字。

## 运镜（统一，确定性）
- 相机固定俯角 0.34rad，dist 由布局包围盒计算
- `dolly = lerp(1.24, 0.94, clamp(p*1.15,0,1))` 连续拉远
- 轻微 sway/lift：`sin(t*0.42)*0.10`、`sin(t*0.31+1.1)*0.05`
- 轨道逐个入场：`born = 0.25 + i*0.13`，`easeOutBack`
- 命中：scale 0.8→1 回弹 + 上浮 0.34 + 材质提亮
- 严禁 idle wobble（motion-doctrine）

## 歌词（captions-overlay 模型）
- 默认 **rail**：单行底部/侧边，逐词高亮。
- 能量峰值 → **embed/快闪**：整屏大字，词级弹入（waterfall entry，±2 帧重叠）。
- 逐句由 LRC 时间轴驱动；副歌判定 = 规则引擎（音符密度）或 LLM。

## 数据流
```
.nbs ──pynbs──► extract_tracks ──► song_data.js (含 base64 贴图)
        .lrc ─► lrc.py ─► lyric.json ─┘
                                   ├─► index.html (模板替换)
                                   └─► hyperframes render ─► .mp4
```

## 样式样片（已出片，8.4s / 1920×1080 / 30fps / draft）
- 产物：`outputs/style_samples/{blockframe,glitch,liquid}.mp4`
- 生成器：`src/nbs_visualizer/hf2_export.py`（NBS + LRC → HF 项目目录）
- 模板：`hyperframes2/index.template.html`（同一模板切 `body[data-style]` 三套皮肤）
- 三套共用的「模具」特征：3D MC 方块 + 连续 dolly + 命中回弹 + 底部歌词轨 + 整屏歌词快闪 + 同款 HUD/页脚
- 差异仅在皮肤层：底色/描边色/字体气质/装饰，不改运镜与版式骨架

### 已验证
- `hyperframes lint` 0 error（唯一 warning：单文件行数偏多）
- `hyperframes inspect` 0 layout issue
- headless Chrome 走 ANGLE/SwiftShader 捕获 WebGL 成功（three.js UMD 经典脚本，避开 file:// 下 ES module CORS）
- 关键坑：three 场景脚本必须包 IIFE，否则顶层 `const D/STYLE` 与前面 classic 脚本的 `var D` 冲突 → 白屏

## LLM 导演
- 先规则引擎：读音符密度/声部数/音域 → 生成 shot list。
- 预留 `director.py` 接口：`script = plan(data)`，可替换为 LLM 输出。
