# ComfyUI-Soda-Storyboard

把分镜文件拖入 ComfyUI，即可在“导入分镜”节点的标签页中查看**分镜图**、**最终投入 MOSS 的完整 JSON 提示词**和**逐格内容**。支持分镜包、单独分镜单和 MOSS 布局 JSON；编辑时再打开侧边栏编辑器，后续可切格、换人、贴回、斜切裁剪和排字。

## 第一次使用：三步跑通

1. 装好节点包和核心库 wheel，重启 ComfyUI。
2. 在 Codex / Claude 插件里导出 `<页id>.storyboard.json` 分镜包，或运行核心库 0.4.0 的 `soda-storyboard export-bundle <项目>/pages/<页id>.json --json`。也支持现有单页分镜 JSON 和下文格式的手工分镜包。
3. 打开 `example_workflows/minimal_page.json` 模板，将分镜文件拖到模板导入节点的预览区域（或点“上传”），即可复用原连线。检查节点内分镜图、MOSS 文本，按本机实际文件选择主模型、编码器、VAE 和需要的 LoRA，再点运行。无需 LoRA 时旁路原生 LoRA Loader。

拖到空白画布会自动新建一个“导入分镜”节点；拖到已有导入节点的预览区或使用上传按钮则直接复用其连线。未选文件时显示“上传或拖入 .storyboard.json”和导入提示，自动刷新不会反复弹出错误窗口。

节点默认约 420×720，预览随节点尺寸调整。点击“查看”或分镜图可打开大窗口，滚轮缩放、拖动平移，悬停逐格内容可高亮对应格子；Esc 或点击遮罩关闭。提示词支持复制和格式化。“高级”默认折叠，台词模式、斜切模式、触发词开关仍保存在原工作流输入中，宽高只在 MOSS JSON 的高级选项中出现。“另存为新分镜包”位于“⋯”菜单。链接项目和草稿节点使用同样的预览组件。

本包要求 [soda-storyboard](https://github.com/cOkieeman/soda-storyboard) **0.4.0 或更高版本**，通过预构建 wheel 安装，不内置或复制核心库代码。讨论剧情、编写分镜单仍使用 Codex / Claude 插件。需要 Python 3.12+ 和支持 MOSS 的新版 ComfyUI。

## 安装

`requirements.txt` 与 `pyproject.toml` 使用核心库 **v0.4.0** 的同一 wheel URL。安装需要对应 Release 文件可下载；本轮开发验证使用本地源码路径依赖，未联网验证下载。

### ComfyUI Manager

在 ComfyUI Manager 中通过 Git URL 安装本节点仓库，允许 Manager 为 ComfyUI 使用的 Python 安装 `requirements.txt`，然后重启 ComfyUI：

```text
https://github.com/cOkieeman/ComfyUI-Soda-Storyboard
```

若 Manager 未自动安装依赖，按下面对应环境的命令补装。Registry 发布和 Manager 索引收录需另外完成。

### Windows 便携版手动安装

将本仓库放入 `ComfyUI/custom_nodes/ComfyUI-Soda-Storyboard`。在 portable 根目录，用内嵌解释器直接安装 wheel，然后重启 ComfyUI：

```powershell
.\python_embeded\python.exe -m pip install --upgrade "https://github.com/cOkieeman/soda-storyboard/releases/download/v0.4.0/soda_storyboard-0.4.0-py3-none-any.whl"
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

未装核心库时十一个节点仍注册，需要核心库的节点运行时提示“请先安装 soda-storyboard：pip install -r requirements.txt”。启动时若检测到核心库低于 0.4.0，会在 ComfyUI 控制台输出含便携版内嵌 Python 和完整 wheel URL 的升级命令，节点包继续加载。加载分镜 LoRA 节点只依赖 ComfyUI 运行时，空名称直接返回输入模型。

## 导入与链接的区别

**导入是副本**：主要入口“导入分镜 · Load Storyboard”接受三类 JSON。文件保存到 ComfyUI 的 `input/soda-storyboard/`，下拉列出已导入文件，不会修改 Codex / Claude 的原项目。外部源项目改了，要重新导出并上传。

- 分镜包：`format` 为 `soda-storyboard-bundle-v1`，包含 `project` 项目设置、`page` 完整分镜单、`characters`（角色 id 到完整角色卡的映射），以及可选的 `exported_at` 和 `sketch_png_base64`。页面显式设置优先于项目默认设置。
- 单独分镜单：包含 `panels`，没有角色卡也能编译；节点会提示“未包含角色卡，LoRA 和外观描述缺失”。
- MOSS JSON：包含 `summary` 和 `items`，保持原始提示词。物件、角色、文字使用绿、蓝、橙色框并配图例；文字优先显示 `text`，按框的长宽横排或竖排。尺寸推断、格子识别和单画布判断统一使用核心库 `canvas_sizes` / `importers.import_moss`。高级宽高填 `0` 为自动，正数优先于文件尺寸；旧工作流已有的正数仍视为手动覆盖。支持核心库的中心、左上角、0～1、0～1000 坐标及 yxyx / xyxy / xywh 格式。无法识别的条目由核心报告，原始 JSON 仍保留。

分镜包和分镜单通过核心库 `bundle.load_bundle` / `compile_bundle` 读取、继承默认值和编译。节点显示编译 warnings 中的英文译文状态：新鲜 / 过期 / 缺失；混合状态同时列出过期和缺失格数，详细原因保留在提示中。没有译文警告时显示“新鲜”（包括手动覆盖或原样保留的 caption）；节点不另算翻译缓存哈希。提示词标签页默认原样显示实际 `moss_json` 输出，格式化只改变显示空白。旧 `caption_en` 是否生效由核心库的 `use_custom_caption` / `legacy_caption_en` 规则决定；需要手动覆盖时请显式开启。

格子识别采用核心库 0.4.0 的启发式规则：含“格”的描述（例如“水墨风格的背景”）可能识别为格子，包含整页背景的大框也可能影响平铺识别。节点不再额外修正规则，复杂外来布局仍需核对预览。

MOSS 的格子来自含 panel / 格 / コマ 的物件说明，或多个基本平铺、互不包含的大物件框；这只是显示用的启发式识别，不会重写提示词。识别出格子时按格列出，没有时显示“单画布”，查看器切换为“条目”，按文字、角色、物件分组，悬停可高亮对应框。归一化坐标和空条目无法单独推断原始比例，自动回退为 1024×1536，并保留尺寸推断提示。

三类输入都无需先运行工作流即可预览。分镜包和分镜单的草稿始终用核心库重新渲染火柴人图，避免附件缩略图过期。节点可拉大，图片随可用空间缩放；完整 JSON 在只读滚动文本框中显示，支持复制及格式化 / 压缩切换。新节点额外输出 `draft` IMAGE，与节点显示的是同一张图（最长边不超过 1024）。

点击“在编辑器中打开”，首次会在 `input/soda-storyboard/<文件名>/` 建立工作项目，补齐最小项目设置并启动核心库编辑器。节点随后读取这个工作副本，编辑器保存后约 1.5 秒内刷新分镜图、最终提示词及下拉选项，下次运行也使用相同新内容。“另存为新分镜包”把修改后的项目、角色卡和新缩略图写入新的包文件，下载到浏览器并选中该包；不会覆盖原上传文件。节点删除后会停止自己的预览轮询。

MOSS JSON 没有完整分镜结构，编辑按钮显示“转换为分镜单后编辑”，确认近似转换后才建立工作项目：object / panel 的 bbox 转格子，text 转文字框，caption 转描述，人物条目只在框图中显示。转换无法还原原始斜边、人物火柴人站位等信息；复杂重叠布局可能需要在编辑器内调整。未经转换时 MOSS JSON 原样送入采样流程。

**链接项目会自动同步**：“链接分镜项目（进阶）· Link Storyboard Project”用于直接读取本机项目目录。首次输入目录并点“记住项目”，以后从下拉选择；页面自动列出，不用手动刷新。目录记在当前浏览器本地。分镜页、角色卡或项目设置改变时，预览自动刷新，下次运行重新编译。该节点也直接显示草稿和完整 MOSS 文本，保留原先八个输出口，旧工作流无需改端口索引。

**LoRA 由使用者控制**：角色卡路径和强度只作为建议，摘要显示建议角色、LoRA 和强度；导入或预览不会加载 LoRA。三个模板使用原生 `LoraLoaderModelOnly`，由使用者手选文件和强度。两个以上出场角色带 LoRA 时只提示“建议一次只加载一个角色 LoRA”，不拦截编译。“提示词包含触发词”默认开启，把出场角色触发词写到对应格子的描述；关闭时省去自动添加的触发词，外观描述始终保留。用户手写在描述中的文字不会被删掉。核心插件 / CLI 的自动出图行为不受此节点包影响。

## 分镜项目

输入的是 ComfyUI 所在电脑上的项目目录，内容应包括：

```text
project.json
pages/
  page-id.json
characters/
  hero.json
```

此结构只用于进阶链接项目。页面 id 对应 `pages` 内文件名，不带 `.json`，前端会自动列成下拉。底层 STRING 输入保持兼容旧工作流和连线；页面、角色卡及项目设置的内容哈希用于缓存失效。预览更新不会自动提交生成任务。

角色卡的 `lora.path` 应相对于 ComfyUI 的 `models/loras`，例如 `characters/hero.safetensors`。建议主角按出场格数最多选择，平票按 id 排序；这不会自动加载任何 LoRA。无建议时输出空字符串和强度 0。

## 节点

分类均为 **Soda Storyboard**。IMAGE 使用 `[B,H,W,C]` float32，MASK 输出 `[B,H,W]`，值域均为 0～1。图像 batch 逐张处理，所有图使用同一份页面几何。

| 类名 | 显示名 | 输入 | 输出 |
| --- | --- | --- | --- |
| `SodaLoadStoryboard` | 导入分镜 · Load Storyboard | 上传文件、台词模式、cut/hint、触发词开关、MOSS 宽高 | 下行全部八个输出，另加 `draft` IMAGE |
| `SodaLoadStoryboardPage` | 链接分镜项目（进阶）· Link Storyboard Project | 项目下拉、页面下拉、台词模式、cut/hint、触发词开关 | `moss_json` STRING、`width` INT、`height` INT、`resolution_json` STRING、`lora_name` STRING、`lora_strength` FLOAT、`negative` STRING、`page_info` STRING |
| `SodaLoadStoryboardLoRA` | 加载分镜 LoRA · Load Storyboard LoRA | MODEL、`lora_name` STRING、`strength` FLOAT | MODEL |
| `SodaLoadMossJSON` | 载入 MOSS JSON · Load MOSS JSON | 保留旧工作流和粘贴文本兼容；新导入推荐统一入口 | `moss_json` STRING、宽高 INT、`resolution_json` STRING |
| `SodaStoryboardPreview` | 分镜草稿图 · Storyboard Preview | 项目目录和页面 id，或可选 `page_info` | 火柴人草稿 IMAGE |
| `SodaCropPanel` | 切格 · Crop Panel | 整页 IMAGE、`page_info`、格子 id/阅读序号、缩放开关 | 单格 IMAGE、四边形 MASK、`panel_prompt` STRING、`panel_box` STRING |
| `SodaCharacterMask` | 人物遮罩 · Character Mask | 单格或整页 IMAGE、`page_info`、格子、角色 id、余量、羽化、图像范围 | 人物 MASK |
| `SodaPastePanel` | 贴回格子 · Paste Panel | 整页 IMAGE、重画格子 IMAGE、`panel_box`、保护文字开关 | 整页 IMAGE |
| `SodaCutQuads` | 斜切裁剪 · Cut Quads | 整页 IMAGE、`page_info`、收缩像素、格框粗细 | 整页 IMAGE |
| `SodaLetterPage` | 排字 · Letter Page | 整页 IMAGE、`page_info`、可选字体路径 | 整页 IMAGE |
| `SodaExtractLayout` | 参考图生成版式 · Extract Layout | 参考页 IMAGE、rtl/ltr、保存开关、可选项目目录和模板名 | `layout_json` STRING、叠加预览 IMAGE |

`page_info` 是含版本号、页面和角色卡的 JSON 快照，保留台词模式覆盖后的结果。连接到后处理节点即可，不需要后处理时重新读取磁盘。`panel_box` 包括裁剪位置、原图/目标尺寸、横纵缩放比例及页面快照，贴回时自动恢复原格尺寸。整页图必须与分镜画布尺寸一致，避免悄悄错位。

切格、人物遮罩的格子下拉从上游 `page_info` 按阅读顺序列出，角色下拉列出所选格子的出场角色；连接、切换文件或格子时自动更新。底层 STRING 仍接受 id，旧数字值按从 1 开始的阅读序号兼容。切格默认把长边缩放到 1024，两个维度对齐 16；比例可能产生小幅取整误差。人物遮罩默认余量 24px、羽化 16px，单位为原分镜画布像素；会在羽化后清除同格另一角色的区域。“图像范围”默认是“格子”：输入切格节点得到的单格，遮罩缩放到该单格的尺寸。选择“整页”时输入完整页面，遮罩按分镜页坐标放到整页上，整页尺寸必须与分镜画布一致。

贴回支持相同 batch 数，以及一张整页配多个重画候选或一张重画格子广播到多张整页；其他 batch 组合报错。格外浮点像素保留原值，斜切格通过四边形遮罩贴回。保护文字默认开启，复用核心库的原文字区域保护规则。

单格重画优先使用 `caption_en`；没有时按核心库的景别、角度短语及角色描述，结合 `description` 生成提示词，支持中文描述。只有两个描述字段都为空时才报错。提示词固定带 `one frame, no panel borders, no gutters, no text, no speech bubbles`，不附加整页布局前缀、格子位置或阅读顺序。

台词模式可跟随页面、强制 MOSS 画字或强制程序排字。排字节点只处理 `lettering` 模式和明确标记 `render_mode=lettering` 的文字。可指定字体文件；中文建议安装思源黑体或 Noto Sans CJK，默认由核心库发现可用字体。

参考图识别复用核心库的 PIL 接口 `extract_image`（等价于文件接口 `extract_layout`）。单图 `layout_json` 是对象，多图 batch 为按输入顺序排列的数组；叠加预览保持 batch。保存开关开启时写入项目 `templates/`，每张参考页保存一个唯一模板，只存归一化格子几何和来源名称，不保存图片。每次排队都会执行保存，请在模板生成后关闭开关。识别结果带可靠性和警告，使用前检查预览。

## 接到 Soda-MOSS v2

1. 将导入分镜的 `moss_json` 接到原 JSON 文字框的 STRING 输入。若 String Literal 节点只能输出而不能接入，将它的原输出线改接 `moss_json`，直接送到相同的下游输入。不要把 JSON 再套一层引号。
2. 把 `resolution_json` 接到 ResolutionPreset 的 `resolution_json` 输入；必要时右键把其文字控件转为输入。格式为 `{"version":1,"width":W,"height":H}`。也可把两个 INT 输出直接接原生 latent 的宽高。
3. `negative` 接负面文本编码器。默认模板中 `UNETLoader` 接原生 `LoraLoaderModelOnly`，由使用者自己选文件、强度，再接 `ModelSamplingAuraFlow`（shift 5）。不使用 LoRA 时旁路这个 Loader。
4. 若明确想自动采用角色卡建议，可以自行把原生 Loader 替换成“加载分镜 LoRA”：连接 MODEL、`lora_name`、`lora_strength`（接 `strength`）。这个可选节点直接接收 STRING，名称为空时透传模型，找不到文件会报中文错误。它不在默认示例中。
5. 解码后依次连接斜切裁剪、排字、保存图像；两个后处理节点的 `page_info` 都接导入分镜。可把 `draft` 接到 PreviewImage 等节点复用草稿。

## 侧边栏编辑器

导入节点上的编辑按钮会自动建立工作项目并打开侧边栏，不需要另填目录。链接项目也可从侧边栏填写目录，页面自动列出后点击“打开 / 复用编辑器”。服务使用空闲本地端口，iframe 打开 `http://127.0.0.1:<port>/#page=<id>`。

后端复用核心库 `edit` 的启动、健康检查、`.soda/server.json` 状态和停止逻辑。只有核对项目、进程及实例身份后才停止服务。关闭侧边栏不会停止服务，使用“停止本项目编辑器”显式停止。接口通过 `asyncio.to_thread` 执行耗时操作，不阻塞 ComfyUI 事件循环。

路由包括页面 / 文件列表、上传、预览、工作副本编辑 / 导出，以及编辑器启动 / 停止。只接受回环 IP 的请求、回环 Host，以及同源 Origin（若浏览器提供），因此浏览器和 ComfyUI 应在同一台电脑上使用。上传限 16 MiB，禁止目录穿越，不会覆盖不同内容的已有文件。远程浏览器或经不同来源的反向代理不支持 iframe 入口。

## 示例工作流

拖入 `example_workflows/` 的 UI 格式 JSON，三个模板都以“上传或拖入 .storyboard.json”的统一导入节点开头。上传分镜文件，重画模板再选择已有整页图片。LoRA 都使用 ComfyUI 原生 Loader，文件和强度由使用者手选；建议输出没有自动连到模型。

模型文件名采用核心库 README / `production/graphs.py` 中的 MOSS-Image 默认值：

| 用途 | 示例值 |
| --- | --- |
| SFT 主模型 | `moss_image_sft_int8_convrot.safetensors` |
| 文本编码器 | `qwen3.5_9b_w4a8_gptq.safetensors`，类型 `moss_image` |
| VAE | `flux2-vae.safetensors` |

模板刻意只保存模型文件的基本名，不保存子目录：Windows 下拉使用反斜杠，其他系统可能使用正斜杠，统一写死任一分隔符都可能校验失败。用户必须在下拉中按自己 `models/diffusion_models`、`models/text_encoders` 和 `models/vae` 目录里的实际位置重新选择。模型不会随节点包下载。

- `minimal_page.json`：载入 → MOSS 原生采样 → 斜切裁剪 → 排字 → 保存。shift 5，25 步，er_sde，simple，CFG 2.5。
- `panel_redraw.json`：载入已有整页图 → 切格 → 图生图（降噪 0.45）→ 贴回 → 保存。
- `character_swap.json`：切格 → 人物遮罩 → 局部重绘（降噪 0.85）→ 用同一遮罩合成回原单格 → 贴回。在原生 Loader 中选**要换上的那个角色的 LoRA**和强度，人物遮罩下拉选择对应角色；切格与遮罩的格子选择必须一致。节点摘要只是建议，不会替你决定。

示例只使用本包及 ComfyUI 核心节点，要求核心提供 `moss_image` CLIP 类型和 `EmptyFlux2LatentImage`。已做静态结构及连线检查；真实 ComfyUI 导入、模型运行和出图质量需在目标安装环境验收。

## 开发与验证

联网安装开发依赖后可执行以下检查；离线验证使用后面的本地路径依赖流程。

```powershell
uv sync --group dev
uv run ruff format --check .
uv run ruff check .
uv run pytest
node --test tests/*.mjs
```

离线开发将两个仓库放在同一父目录，在节点仓库中用已有 pytest / ruff / Pillow 的 `.venv`，将 `PYTHONPATH` 指向核心库 0.4.0 的 `src`。这是本地路径依赖，绕过 wheel 解析，不写入核心仓库，也不修改 ComfyUI 的 Python。首次准备环境需要预先提供依赖；以下命令均不访问网络：

```powershell
$env:PYTHONPATH = (Resolve-Path ..\soda-storyboard\src).Path
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
uv run --offline --no-project --python .venv\Scripts\python.exe -c "import soda_storyboard.bundle as b; print(b.__file__)"
uv run --offline --no-project --python .venv\Scripts\python.exe -m ruff format --check .
uv run --offline --no-project --python .venv\Scripts\python.exe -m ruff check .
uv run --offline --no-project --python .venv\Scripts\python.exe -m pytest -ra
node --test tests/*.mjs
```

可选设置 `COMFYUI_SOURCE` 为只读 ComfyUI 源码目录，让测试对照真实类名检查工作流。缺少 torch 时跳过张量及 batch 形状测试，PIL 几何、编译、文字保护、草稿、参考图识别、路由访问控制与模拟编辑器生命周期测试照常运行。前端测试使用 Node 内置测试器和模拟 DOM/API；未启动真实服务或提交生成任务。pytest 的 `confcutdir=tests` 避免带连字符的仓库名被按裸 `__init__` 收集。

本轮还通过临时只读代理加载真实 ComfyUI 前端，验证三种译文状态、节点及大窗口的提示词原样显示、格式化往返、复制和窄节点布局；未提交生成任务。

## English

Drop a storyboard bundle, bare page JSON or MOSS layout JSON into ComfyUI. The unified Load Storyboard node shows a draft and the exact final MOSS JSON before execution, with copy/format controls and translation freshness warnings. Core 0.4.0 public bundle/import APIs own compilation, canvas inference and panel detection. Export real bundles with `soda-storyboard export-bundle <page.json> --json`. Edit an imported working copy in the local sidebar, then save a new bundle; advanced project linking stays in sync with local files. LoRA metadata is advisory: default examples use the native loader with manual selection. Requires Python 3.12+, a MOSS-capable ComfyUI and the prebuilt soda-storyboard 0.4.0+ wheel. Model paths must be selected from your own installation. Editor routes accept loopback, same-origin requests only. The offline development commands above use a sibling core checkout as a read-only Python path dependency.

## License

Apache-2.0. The separately installed soda-storyboard library and model files retain their own licenses.
