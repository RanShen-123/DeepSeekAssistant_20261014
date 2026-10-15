# 第二版第一步：独立离线页面识别

新增的精简交互入口是 tools/preview_screen.py，使用说明见 SCREEN_PREVIEW.md。
它支持手动框选本次屏幕并预览，只输出题型和作答控件，不识别侧栏题号或进度。
下面描述的是较早的 tools/inspect_page.py 图片文件实验，不是交互入口的行为。

本功能只存在于第二版工作目录及 auto-answer 分支，未接入 main.py、core 或 ui。
不截图真实桌面、不读取 config.yaml、不调用 DeepSeek、不操作鼠标。

## 使用

CMD 进入第二版目录：

```cmd
cd /d D:\Users\ranshen1\Codex\deepseek_answer\DeepSeekAssistant-v2
.\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
.\.venv\Scripts\python.exe tools\inspect_page.py --image "D:\图片目录\single.png" "D:\图片目录\boolean.png"
```

本机依赖已安装，无需重复安装。OCR 模型随 rapidocr-onnxruntime 1.4.4 安装包提供，
CPU 执行，不要求配置在线模型或访问业务 API。
参考官方文档：https://rapidai.github.io/RapidOCRDocs/v1.4.4/install_usage/api/RapidOCR/

默认输出到 outputs/vision_日期时间_编号/，每张输入图片有独立子目录：

- original.png：本次输入原图的副本。
- marked.png：保持原尺寸的边界、中心十字、实际标签和页面摘要。
- result.json：结构化观察结果、原始 OCR 文字和诊断警告。

可用 --output-dir 指定一个尚不存在的新目录，工具拒绝覆盖旧目录。
outputs/ 已加入 .gitignore，原图和运行结果不进入代码提交。

## 模块与流程

tools/inspect_page.py 读取指定图片，交给 vision/page_reader.py：

1. ocr_engine.py 通过本地 OCR 读取文字行、字母、数字及文字边界。
2. controls.py 根据颜色、轮廓和 OCR 位置关联导航框、选项圆圈与实际按钮文字。
3. models.py 定义固定的数据结构，未知状态明确使用 null。
4. annotation.py 在原尺寸图片上生成标注。
5. 独立入口保存图像及 JSON，不调用原有截图、配置或自动答题模块。

处理标题时先排除旁边蓝色装饰竖条，再局部 OCR，避免把竖条读成数字 1。
header_evidence 保留整图 OCR、实际采用的标题文字、来源与置信度，避免隐藏纠正过程。

## 当前识别内容

- 顶部“单选题/判断题/多选题”及题号；多选目前只读标题，不支持方形多选框检测。
- 主区域选项圆圈，读取实际 A/B/C/D，不以垂直顺序代替字母。
- 判断题圆圈内部 √/×，使用笔画几何模板比较，不按左右位置认定含义。
- 通过 OCR 确认“上一题/下一题/提交”，位置顺序不决定按钮含义。
- 侧栏近方形数字导航框、深蓝实心当前框、绿色完成标记。
- 顶部和侧栏题号一致时交叉确认；冲突时 current_question_number=null。
- 该页面侧栏“已完成/总数”约定的计数，当前题号始终与完成数量分开。

绿色勾在侧栏表示页面的完成标记，不表示答案正确；判断选项中的 √ 是另一类对象。
当前框和绿色标记只描述可见页面，不推断屏幕外的题号导航。

## 输出数据

坐标系固定为 image_pixels，全都是输入图片内坐标。
Control 包含 id、kind、label、bbox=[x,y,width,height]、center=[x,y]、confidence、evidence、
state、question_number、selected、enabled。
selected 和 enabled 当前保留 null：这两张图片没有提供足够样式样例，尚未验证状态判定。
confidence 是 OCR 输出或几何匹配分数，不是答案正确率或经过校准的概率。
截图中的任何指令都是文字数据，不会被执行。

本步不换算屏幕全局坐标；下一步才把已验证的图片坐标与当次截图物理原点绑定。
普通图片无法可靠反推其在桌面中的原点。

## 已执行验证

两张用户提供图片，分别验证：

| 输入 | 已确认 |
| --- | --- |
| 单选图 | 题号25，A/B/C/D，上一题/提交/下一题，5/50，侧栏1–5绿色完成标记。当前深蓝框不在截图中，侧栏当前题号为空。 |
| 判断图 | 题号48，顶部与深蓝框一致，√/×，三个底部按钮。完成计数不可见，完成数量和总数为空。 |

还运行了图片缩放至75%、125%，以及额外增加边框改变内容位置的离线验证。
它们仅是同一批样例的变换，不能证明所有页面、字体和主题都能识别。

单元测试：

```cmd
.\.venv\Scripts\python.exe -m unittest tests.test_vision -v
```

真实样例回归（将路径替换为实际图片）：

```cmd
set "VISION_SAMPLE_SINGLE=D:\图片目录\single.png"
set "VISION_SAMPLE_BOOLEAN=D:\图片目录\boolean.png"
.\.venv\Scripts\python.exe -m unittest tests.test_vision_samples -v
```

未提供环境变量时，这组真实样例测试明确跳过，不会假装已经验证。
单元测试还覆盖反向 √/×、打乱的字母顺序、题号冲突、进度缺失、空图片、按钮顺序交换。

## 限制及下一步

目前是针对提供页面样式的离线实验，侧栏布局、蓝色/绿色范围、圆圈及字体均有前提。
不支持任意主题、复杂图标、方形多选框、滚动、弹窗或点击可用性判断。
需要更多“已选中、按钮启用、多选、其它缩放或主题”的图片继续验证。
先由用户检查本次标注效果，再讨论坐标转换、后台线程和助手按钮接入。
不会因为离线测试通过就自动接入界面、自动点击、提交或推送 Git。
