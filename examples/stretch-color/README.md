# 起身舒展：彩色分镜示例

![彩色五格漫画](../../docs/images/stretch-color-finished.png)

本例使用纯文字提示词定义 25 岁原创女主绯音，五格从右至左阅读，第三格为全身舒展主画面。图像由 MOSS 生成，三句中文台词由程序排字。完整操作见 [节点教程](../../docs/tutorial-stretch-color.md)。

## 先运行一次

1. 安装节点和 soda-storyboard 核心库 0.4.1，重启 ComfyUI。
2. 打开 [配套工作流](../../example_workflows/stretch-color.json)。
3. 在“导入分镜”中上传 [stretch-color.storyboard.json](stretch-color.storyboard.json)。
4. 重新选择本机 MOSS SFT、qwen3.5 文本编码器和 flux2 VAE，编码器类型为 `moss_image`。
5. 核对 1024×1536、5 格、3 句台词、英文译文新鲜，批次数量为 1，再点击运行。

工作流为 50 步、CFG 3、Euler / simple、SLG 单层 22（start 0、end 1）、种子 20261022。无需角色 LoRA 或图片条件输入。本页不接斜切裁剪节点，直接在解码后排字并保存。

## 文件与修改

| 文件 | 内容 |
| --- | --- |
| [project.json](project.json) | 彩色画风、右至左阅读、程序排字等默认设置 |
| [pages/stretch-color.json](pages/stretch-color.json) | 五格构图、姿势、场景与独立文字框 |
| [characters/hiyone.json](characters/hiyone.json) | 中英文外观和服装 |
| [translations.json](translations.json) | 本页英文场景译文与来源哈希 |
| [output/character-prompt.txt](output/character-prompt.txt) | 角色英文提示词 |
| [output/stretch-color.moss.json](output/stretch-color.moss.json) | 生成时使用的布局与提示词 |

复制此目录作为自己的故事项目后，可让插件或网页编辑器继续修改。原项目修改后需要补译、重新导出并上传分镜包；节点中的上传副本另行保存。项目中的 ComfyUI 地址只是默认值，直接使用 CLI 出图前应配置本机端口和模型文件名。项目的 `final` 是 CLI 预设；本例实际出图以配套节点工作流中的参数为准。

成图与此示例的 MOSS 描述一致，但模型没有完全落实第二格的起身动作。调整新角色或姿势时，请核对实际成图。
