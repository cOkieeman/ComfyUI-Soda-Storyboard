# ComfyUI-Soda-Storyboard

在 ComfyUI 画布上读取 Soda Storyboard 分镜单，输出 MOSS 布局 JSON、尺寸与主角 LoRA 信息，生成火柴人草稿，并完成切格、换人遮罩、贴回、斜切裁剪和程序排字。侧边栏提供网页分镜编辑器入口。

本包要求 [soda-storyboard](https://github.com/cOkieeman/soda-storyboard) **0.3.1 或更高版本**，通过预构建 wheel 安装，不内置或复制核心库代码。讨论剧情、编写分镜单仍使用 Codex / Claude 插件。需要 Python 3.12+ 和支持 MOSS 的新版 ComfyUI。

## 安装

以下 wheel 地址暂按 **v0.3.1** 约定填写，发布者需在核心库 GitHub Release 中上传对应文件并确认版本；发布前下载可能返回 404。`requirements.txt` 与 `pyproject.toml` 使用同一 wheel URL。

### ComfyUI Manager

在 ComfyUI Manager 中通过 Git URL 安装本节点仓库，允许 Manager 为 ComfyUI 使用的 Python 安装 `requirements.txt`，然后重启 ComfyUI：

```text
https://github.com/cOkieeman/ComfyUI-Soda-Storyboard
```

若 Manager 未自动安装依赖，按下面对应环境的命令补装。Registry 发布和 Manager 索引收录需另外完成。

### Windows 便携版手动安装

将本仓库放入 `ComfyUI/custom_nodes/ComfyUI-Soda-Storyboard`。在 portable 根目录，用内嵌解释器直接安装 wheel，然后重启 ComfyUI：

```powershell
.\python_embeded\python.exe -m pip install --upgrade "https://github.com/cOkieeman/soda-storyboard/releases/download/v0.3.1/soda_storyboard-0.3.1-py3-none-any.whl"
```

也可以使用已经指向同一 wheel 的依赖文件：

```powershell
.\python_embeded\python.exe -m pip install -r .\ComfyUI\custom_nodes\ComfyUI-Soda-Storyboard\requirements.txt
```

便携版内嵌 Python 的 `._pth` 隔离配置可能使源码包的隔离构建环境无法导入 `uv_build`，从 Git 源码安装会出现 `BackendUnavailable: Cannot import 'uv_build'`。wheel 已预先构建，安装时不运行源码构建后端，因此便携版应使用 wheel。无需修改 `._pth` 或安装构建后端。

### 普通 Python 环境

将本仓库放入 `ComfyUI/custom_nodes/ComfyUI-Soda-Storyboard`，在 ComfyUI 使用的虚拟环境中进入节点包目录：

```powershell
python -m pip install --upgrade -r requirements.txt
```

随后重启 ComfyUI。torch、numpy 使用 ComfyUI 环境提供的版本；Pillow 是核心库的依赖，本包不会主动安装另一套 torch。wheel 依赖安装不要求 Git 构建核心库。

未装核心库时十个节点仍注册，需要核心库的节点运行时提示“请先安装 soda-storyboard：pip install -r requirements.txt”。启动时若检测到核心库低于 0.3.1，会在 ComfyUI 控制台输出一行升级提示，节点包继续加载。加载分镜 LoRA 节点只依赖 ComfyUI 运行时，空名称直接返回输入模型。

## 分镜项目

输入的是 ComfyUI 所在电脑上的项目目录，内容应包括：

```text
project.json
pages/
  page-id.json
characters/
  hero.json
```

页面 id 填 `pages` 内文件名，不带 `.json`。点击节点的“刷新页面”可下拉选择，原 STRING 输入仍可编辑或转为连线。页面和全部角色文件的内容哈希用于缓存失效，保存分镜后再次排队会重新编译；不会自动提交生成任务。

角色卡的 `lora.path` 应相对于 ComfyUI 的 `models/loras`，例如 `characters/hero.safetensors`。主角按出场格数最多选择，平票按 id 排序，一次只选一个 LoRA。无 LoRA 输出空字符串和强度 0。

## 节点

分类均为 **Soda Storyboard**。IMAGE 使用 `[B,H,W,C]` float32，MASK 输出 `[B,H,W]`，值域均为 0～1。图像 batch 逐张处理，所有图使用同一份页面几何。

| 类名 | 显示名 | 输入 | 输出 |
| --- | --- | --- | --- |
| `SodaLoadStoryboardPage` | 载入分镜页 · Load Storyboard Page | 项目目录、页面 id、台词模式、cut/hint | `moss_json` STRING、`width` INT、`height` INT、`resolution_json` STRING、`lora_name` STRING、`lora_strength` FLOAT、`negative` STRING、`page_info` STRING |
| `SodaLoadStoryboardLoRA` | 加载分镜 LoRA · Load Storyboard LoRA | MODEL、`lora_name` STRING、`strength` FLOAT | MODEL |
| `SodaLoadMossJSON` | 载入 MOSS JSON · Load MOSS JSON | `.moss.json` 路径或 JSON 文本、宽高 | `moss_json` STRING、宽高 INT、`resolution_json` STRING |
| `SodaStoryboardPreview` | 分镜草稿图 · Storyboard Preview | 项目目录和页面 id，或可选 `page_info` | 火柴人草稿 IMAGE |
| `SodaCropPanel` | 切格 · Crop Panel | 整页 IMAGE、`page_info`、格子 id/阅读序号、缩放开关 | 单格 IMAGE、四边形 MASK、`panel_prompt` STRING、`panel_box` STRING |
| `SodaCharacterMask` | 人物遮罩 · Character Mask | 单格或整页 IMAGE、`page_info`、格子、角色 id、余量、羽化、图像范围 | 人物 MASK |
| `SodaPastePanel` | 贴回格子 · Paste Panel | 整页 IMAGE、重画格子 IMAGE、`panel_box`、保护文字开关 | 整页 IMAGE |
| `SodaCutQuads` | 斜切裁剪 · Cut Quads | 整页 IMAGE、`page_info`、收缩像素、格框粗细 | 整页 IMAGE |
| `SodaLetterPage` | 排字 · Letter Page | 整页 IMAGE、`page_info`、可选字体路径 | 整页 IMAGE |
| `SodaExtractLayout` | 参考图生成版式 · Extract Layout | 参考页 IMAGE、rtl/ltr、保存开关、可选项目目录和模板名 | `layout_json` STRING、叠加预览 IMAGE |

`page_info` 是含版本号、页面和角色卡的 JSON 快照，保留台词模式覆盖后的结果。连接到后处理节点即可，不需要后处理时重新读取磁盘。`panel_box` 包括裁剪位置、原图/目标尺寸、横纵缩放比例及页面快照，贴回时自动恢复原格尺寸。整页图必须与分镜画布尺寸一致，避免悄悄错位。

格子优先按 id 匹配，否则将数字解释为从 1 开始的阅读顺序。切格默认把长边缩放到 1024，两个维度对齐 16；比例可能产生小幅取整误差。人物遮罩默认余量 24px、羽化 16px，单位为原分镜画布像素；会在羽化后清除同格另一角色的区域。“图像范围”默认是“格子”：输入切格节点得到的单格，遮罩缩放到该单格的尺寸。选择“整页”时输入完整页面，遮罩按分镜页坐标放到整页上，整页尺寸必须与分镜画布一致。

贴回支持相同 batch 数，以及一张整页配多个重画候选或一张重画格子广播到多张整页；其他 batch 组合报错。格外浮点像素保留原值，斜切格通过四边形遮罩贴回。保护文字默认开启，复用核心库的原文字区域保护规则。

单格重画优先使用 `caption_en`；没有时按核心库的景别、角度短语及角色描述，结合 `description` 生成提示词，支持中文描述。只有两个描述字段都为空时才报错。提示词固定带 `one frame, no panel borders, no gutters, no text, no speech bubbles`，不附加整页布局前缀、格子位置或阅读顺序。

台词模式可跟随页面、强制 MOSS 画字或强制程序排字。排字节点只处理 `lettering` 模式和明确标记 `render_mode=lettering` 的文字。可指定字体文件；中文建议安装思源黑体或 Noto Sans CJK，默认由核心库发现可用字体。

参考图识别复用核心库的 PIL 接口 `extract_image`（等价于文件接口 `extract_layout`）。单图 `layout_json` 是对象，多图 batch 为按输入顺序排列的数组；叠加预览保持 batch。保存开关开启时写入项目 `templates/`，每张参考页保存一个唯一模板，只存归一化格子几何和来源名称，不保存图片。每次排队都会执行保存，请在模板生成后关闭开关。识别结果带可靠性和警告，使用前检查预览。

## 接到 Soda-MOSS v2

1. 将载入分镜页的 `moss_json` 接到原 JSON 文字框的 STRING 输入。若 String Literal 节点只能输出而不能接入，将它的原输出线改接 `moss_json`，直接送到相同的下游输入。不要把 JSON 再套一层引号。
2. 把 `resolution_json` 接到 ResolutionPreset 的 `resolution_json` 输入；必要时右键把其文字控件转为输入。格式为 `{"version":1,"width":W,"height":H}`。也可把两个 INT 输出直接接原生 latent 的宽高。
3. `negative` 接负面文本编码器。把 `UNETLoader.MODEL` 接“加载分镜 LoRA”的 `model`，`载入分镜页.lora_name` 接它的 `lora_name`，`lora_strength` 接它的 `strength`。再把 MODEL 输出接 `ModelSamplingAuraFlow`（shift 5）。
4. 新 LoRA 节点直接接收 STRING，不受原生 COMBO 下拉框的连线限制；名称为空时自动跳过，保留原模型。名称是相对于 `models/loras` 的路径，找不到文件会给出中文错误。换人时只加载目标角色的一个人物 LoRA。
5. 解码后依次连接斜切裁剪、排字、保存图像；两个后处理节点的 `page_info` 都接载入分镜页。

## 侧边栏编辑器

点击 ComfyUI 侧边栏“分镜”，填写项目目录，刷新并选择页面，点击“打开 / 复用编辑器”。节点上的“在编辑器中打开”会跳到同一侧边栏并定位对应页面。服务使用空闲本地端口，iframe 打开 `http://127.0.0.1:<port>/#page=<id>`。

后端复用核心库 `edit` 的启动、健康检查、`.soda/server.json` 状态和停止逻辑。只有核对项目、进程及实例身份后才停止服务。关闭侧边栏不会停止服务，使用“停止本项目编辑器”显式停止。接口通过 `asyncio.to_thread` 执行耗时操作，不阻塞 ComfyUI 事件循环。

路由包括 `GET /soda_storyboard/pages`、`POST /soda_storyboard/editor/start`、`POST /soda_storyboard/editor/stop`。只接受回环 IP 的请求、回环 Host，以及同源 Origin（若浏览器提供），因此浏览器和 ComfyUI 应在同一台电脑上使用。远程浏览器或经不同来源的反向代理不支持 iframe 入口。

## 示例工作流

拖入 `example_workflows/` 的 UI 格式 JSON。先填写项目目录、页面 id 和已有整页图片。三个示例都使用“加载分镜 LoRA”，名称和强度连接到载入分镜页的输出，没有写死人物 LoRA。

模型文件名采用核心库 README / `production/graphs.py` 中的 MOSS-Image 默认值：

| 用途 | 示例值 |
| --- | --- |
| SFT 主模型 | `MOSS-Image/MOSS-Image-SFT/moss_image_sft_int8_convrot.safetensors` |
| 文本编码器 | `qwen3.5_9b_w4a8_gptq.safetensors`，类型 `moss_image` |
| VAE | `flux2-vae.safetensors` |

用户仍需按自己 `models/diffusion_models`、`models/text_encoders` 和 `models/vae` 目录里的实际相对路径选择文件。子目录不同就重新选择；这些模型不会随节点包下载。

- `minimal_page.json`：载入 → MOSS 原生采样 → 斜切裁剪 → 排字 → 保存。shift 5，25 步，er_sde，simple，CFG 2.5。
- `panel_redraw.json`：载入已有整页图 → 切格 → 图生图（降噪 0.45）→ 贴回 → 保存。
- `character_swap.json`：切格 → 人物遮罩 → 局部重绘（降噪 0.85）→ 用同一遮罩合成回原单格 → 贴回。默认加载页面主角 LoRA，人物遮罩的 `character_id` 留空供填写，必须填写同一主角的 id。若换其他角色，断开 LoRA 节点的 `lora_name` 和 `strength` 输入，改填该目标角色卡中的路径、强度，同时修改人物遮罩的角色 id。若修改切格选择，也要同步修改人物遮罩中的格子选择。

示例只使用本包及 ComfyUI 核心节点，要求核心提供 `moss_image` CLIP 类型和 `EmptyFlux2LatentImage`。已做静态结构及连线检查；真实 ComfyUI 导入、模型运行和出图质量需在目标安装环境验收。

## 开发与验证

核心库 wheel 发布且 URL 确认后，运行 `uv lock` 生成新的锁文件，再执行以下命令。旧的 Git 源码依赖锁文件已移除，避免继续拉取旧版本。wheel 发布前可使用下方离线验证方式。

```powershell
uv sync --group dev
uv run ruff format --check .
uv run ruff check .
uv run pytest
node --test tests/test_web.mjs
```

离线开发可借用已经安装 pytest / ruff / Pillow 的解释器，设置 `PYTHONPATH` 指向本地核心库的 `src`，无需安装核心库或访问网络：

```powershell
$env:PYTHONPATH = (Resolve-Path ..\soda-storyboard\src).Path
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest
```

可选设置 `COMFYUI_SOURCE` 为只读 ComfyUI 源码目录，让测试对照真实类名检查工作流。缺少 torch 时跳过张量及 batch 形状测试，PIL 几何、编译、文字保护、草稿、参考图识别、路由访问控制与模拟编辑器生命周期测试照常运行。前端测试使用 Node 内置测试器和模拟 DOM/API；未启动真实服务或提交生成任务。pytest 的 `confcutdir=tests` 避免带连字符的仓库名被按裸 `__init__` 收集。

## English

ComfyUI nodes for compiling Soda Storyboard pages into MOSS layout JSON and post-processing manga images. Includes a STRING-compatible LoRA loader, sketch previews, panel cropping/pasting, character masks, quad cuts, lettering, reference layout extraction, and a local editor sidebar. Install the prebuilt soda-storyboard 0.3.1+ wheel with ComfyUI's Python, restart, and find **Soda Storyboard** in the node menu. The v0.3.1 Release URL is provisional until publication. Portable Python must use the wheel to avoid isolated source-build failures. Requires Python 3.12+ and a MOSS-capable ComfyUI. Example model filenames follow the core defaults; select the actual relative paths in your installation. Only one character LoRA should be loaded at a time. The editor routes accept loopback, same-origin requests only.

## License

Apache-2.0. The separately installed soda-storyboard library and model files retain their own licenses.
