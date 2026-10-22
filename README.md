# NBS 可视化视频生成器

一个使用 pynbs 解析 Minecraft Note Block Studio (`.nbs`) 文件，并用 Minecraft 风格贴图渲染成可视化视频的工具。

## 特性

- **pynbs 解析**：完整支持 NBS v1-v5 格式（旋律、和弦、多层、多乐器）
- **Minecraft 风格贴图**：16 种内置乐器方块 + 音符粒子 + MC 天空背景
- **钢琴卷帘可视化**：横轴时间、纵轴音高，播放头扫过，命中音符时迸发粒子
- **两种使用方式**：
  - 命令行（单文件快速生成）
  - Web 界面（拖拽上传、实时进度、在线预览/下载）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

需要：Python 3.10+，`pynbs`, `Pillow`, `opencv-python`, `numpy`, `Flask`

### 2. 命令行使用

```bash
python run_cli.py my_song.nbs
# 指定输出路径：
python run_cli.py my_song.nbs outputs/my_video.mp4
```

### 3. Web 界面

```bash
python app.py
# 然后浏览器打开 http://127.0.0.1:5000
```

Web 流程：
1. 拖拽 `.nbs` 文件到上传区
2. 后台自动渲染（每 500ms 轮询进度）
3. 完成后在页面内预览，点击"下载视频"保存

## 项目结构

```
nbs可视化/
├── app.py                       # Flask Web 应用
├── nbs_visualizer.py            # 核心可视化引擎（pynbs 解析 + 帧渲染 + OpenCV 合成）
├── run_cli.py                   # 命令行入口
├── generate_textures.py         # MC 风格贴图生成脚本
├── create_sample_nbs.py         # 样本 NBS 文件生成脚本
├── requirements.txt
├── assets/
│   └── textures/                # 自动生成的 MC 贴图（16 种乐器 + 8 种粒子 + 天空）
├── uploads/                     # Web 上传临时区
├── outputs/                     # 渲染输出
└── templates/
    └── index.html               # Web UI（Minecraft 配色 + 拖拽上传）
```

## 可视化设计

- **画布**：1280×720 @ 30 FPS
- **背景**：Minecraft 风格天空渐变（淡蓝→浅蓝）
- **播放区**：半透明深色面板 + 水平音高网格 + 垂直节拍网格
- **音符方块**：每个乐器一种颜色（Harp 金、Bass 棕、Snare 沙、Hat 玻璃蓝、Bell 金、Flute 黏土、Chime 冰、Guitar 木、Xylophone 骨、Iron Xylo 铁、Cow Bell 红、Didgeridoo 南瓜、Bit 绿、Banjo 干草、Pling 荧石）
- **播放头**：黄色高亮竖线，命中音符时迸发彩色粒子（带重力 + 寿命衰减）
- **顶部信息栏**：歌名、作者、当前时间/总时长
- **底部进度条**：实时渲染百分比

## 注意事项

- NBS 格式约束：每个 tick 在每个 layer 上只能有一个音符，否则文件会损坏
- 渲染速度取决于歌曲长度和机器性能，~7 秒的样本约 4 秒渲染完
- 生成的视频采用 mp4v 编码，浏览器可直接播放

## 样本文件

```bash
python assets/create_sample_nbs.py
# 在 uploads/sample.nbs 生成 6.8 秒的测试旋律
```
