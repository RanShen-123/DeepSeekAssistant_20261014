# 控件定位交互测试

这是独立的手动测试入口，没有接入原助手 main.py。
只定位题型、A/B/C/D、√/×、上一题、下一题和提交；不输出左侧题号或进度。
采用本地 OCR、OpenCV 轮廓检测和符号几何匹配，不调用 DeepSeek，不读取 API 密钥。
普通识别按钮不操作鼠标；“点击对应选项（一次）”“点击提交（一次）”及
“点击下一题（一次）”分别在用户手动触发后发送一次真实单击。

## 启动

在 CMD 中执行：

```cmd
cd /d D:\Users\ranshen1\Codex\deepseek_answer\DeepSeekAssistant-v2
.\.venv\Scripts\python.exe tools\preview_screen.py
```

已验证窗口图片显示、模拟截图后台流程和两张已有截图的真实本地 OCR 到预览流程。
实际桌面上的手动框选仍需验收。
若提示缺少本地识别依赖，可自行安装：

```cmd
.\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
```

## 操作

1. 将答题页面完整显示在一个显示器上。
2. 点击“框选并识别”，拖动框入顶部题型、全部选项和底部按钮；建议直接从主答题内容左缘开始框选，避开侧栏。
3. 释放鼠标后，测试窗口暂时隐藏，后台截取这一次选区并识别。窗口不会出现在本次截图内。
4. 查看“控件标注”中的红色中心十字、绿色边框和实际标签；可切换“本次原图”对照。
5. 右侧表格同时显示图内中心与屏幕中心。点击“原始尺寸”检查定位细节。
6. 手动切换题目后，点击“重新识别当前区域”，复用内存中的选区，截取新图。
7. 要保存本次结果时，点击“保存结果”。再次框选会替换内存中的选区，不改 config.yaml。

Esc 或右键仅用于取消框选。识别过程中需等待后台任务结束后关闭窗口。
本工具不解答题目；选择、提交、下一题分别需要手动点击面板对应按钮，不自动串联。

## 输出位置

预览不会自动保存；点击保存后才生成独立目录：

```text
D:\Users\ranshen1\Codex\deepseek_answer\DeepSeekAssistant-v2\outputs\screen_test_日期_时间_随机编号\
    original.png
    marked.png
    result.json
```

original.png 是本次截图，marked.png 在同一张截图上绘制十字和标签。
result.json 保存当次物理选区、题型、控件边界、图内中心、屏幕中心、识别证据和警告。
outputs/ 被 Git 忽略。关闭程序后内存选区丢失；重新启动需要再次框选。

## 模块与坐标

tools/preview_screen.py 管理窗口和后台任务，复用 ui/selector.py 框选物理区域。
vision/screen_session.py 在内存截图、检查坐标范围、标注和显式保存。
vision/control_reader.py 从本次图片识别题型与目标控件，复用 vision/controls.py 的轮廓及文字匹配。
旧 tools/inspect_page.py 是较早的整页图片实验，与本次精简交互入口分别使用。

坐标换算使用当次截图的物理像素原点：

```text
屏幕中心 x = screen_region.x + center[0]
屏幕中心 y = screen_region.y + center[1]
```

center 和 bbox 属于原尺寸截图，screen_center 和 screen_bbox 属于物理屏幕像素。
预览缩放仅用于显示，不改变 JSON 坐标。不再次乘 Windows 缩放比例。
负屏幕坐标允许；一次选区限单个显示器。移动浏览器或改变屏幕设置后需要重新截图或框选。

## 当前限制

针对已有两张示例的页面样式开发，需要实际手动验证。
按实际字母识别 A/B/C/D，按内部笔画区分 √/×，不会按选项排列位置补猜。
底部按钮依赖可见文字，顶部题型依赖可见标题。
可自动尝试排除长竖分隔线左侧的侧栏，但不是通用版式分割；异常时请仅框选主答题区。
OCR 会处理主答题图片中的文字；除控件和题型外，现输出 question_identity 中的题干和选项文字，
用于点击前确认题目一致。它不使用题号，也不将页面文字作为执行指令。
多选题目前只识别标题，不支持方形多选框。
selected 表示圆形选项是否蓝底选中，无法确认时为 null；
enabled 仅用于提交和下一题状态，其余为 null。
匹配分数不是点击可靠性的保证。
识别未知或漏检时会列出警告，需要人工对照标注图，不应直接据此接入自动点击。

## 预览崩溃修复与回归

曾在生成图片预览的 QPixmap.scaled 阶段复现 Windows 0xC0000005 内存访问冲突，
无需真实截图或 OCR 即可复现。现在移除临时 ImageQt 转换，改为 RGB 字节构造 QImage
并立即 copy，让 Qt 拥有独立像素内存后再生成 QPixmap，修复后同一路径通过。

回归命令：

```cmd
.\.venv\Scripts\python.exe -X faulthandler -m unittest tests.test_screen_preview tests.test_vision tests.test_assistant -v
```

tests.test_screen_preview 包含图片对象释放后缩放、替换预览，以及模拟截图的后台回传验证。
设置 VISION_SAMPLE_SINGLE 和 VISION_SAMPLE_BOOLEAN 为已有图片路径时，另验证真实 OCR 到预览。
本次提供两张样例路径运行，共 24 项测试通过，无真实桌面截图、点击或业务 API 请求。

## 新增：已提交和下一题状态（待手动验收）

交互窗口增加页面状态摘要和“可用状态”列，标注图的下一题标签显示可用、禁用或未知。
保存的 JSON 增加 page_state，包含 submitted、next_enabled、all_completed、suggested_action
及检测证据。状态依据本次截图，不使用题号或完成数量。

- “已提交”且下一题浅灰禁用：all_completed=true，suggested_action=stop。
- “已提交”且下一题深色可用：all_completed=false，suggested_action=next。
- 底部文字仍是“提交”：submitted=false，suggested_action=answer。
- OCR 置信度不足、控件缺失、重复控件或颜色不确定：保留 null，不能据此结束。

vision/button_state.py 在 OCR 文字区域提取前景灰度，按当前白底页面样式区分深色和浅灰。
颜色阈值不是浏览器真实 disabled 属性，只是视觉推断；更换主题后需要重新验证。
提交和翻题的 suggested_action 只用于展示，不会自动执行；用户可以手动点击面板对应操作。
本次状态扩展及 tests/test_button_state.py 尚未运行；上面的 24 项结果是扩展之前的验证记录。

### 是否可提交

新增 page_state.can_submit：蓝色背景白色文字的“提交”为 true；
非蓝背景且文字浅灰的“提交”为 false；“已提交”为 false；缺失或样式无法确认则为 null。
颜色只分析 OCR 已定位的提交控件区域，不以页面上其他蓝色元素判断可提交。
窗口摘要、控件可用状态列和标注图同步显示；可提交时 suggested_action=submit，
灰色不可提交时 suggested_action=answer，不确定时为 pause，仍只展示而不执行。
本次蓝色提交状态扩展只做代码与静态检查，未运行程序或测试，待手动验收。

### 选项是否已选择

vision/selection_state.py 分析每个已定位圆形选项的内圆颜色：蓝色占主导为 selected=true，
白色占主导且存在灰色笔画或边框为 false；其它外观或像素不足保留 null。
窗口表格新增“选择状态”列；标注图显示已选择、未选择、选择未知；
JSON 中每个选项控件的 selected 同步更新，evidence 保留颜色占比。
状态不表示答案正确，也不表示已提交，提交仍通过底部文字另行确认。

蓝底白色 √/× 提取白色笔画进行几何匹配；蓝底白字的局部 OCR 转为白底黑字，
避免选中背景影响符号含义的识别。不按选项位置推断含义。
需要完整框入选项圆圈，绿色判分标记遮挡等情况仍可能漏检。
本次新增 tests/test_selection_state.py，但未运行程序或测试，需手动验收。

## 手动答案单击测试

1. 启动命令不变，先框入完整题型、题干、全部选项和底部提交区域。
2. 对照预览确认选项含义、选择状态与坐标，输入 A/B/C/D 或 √/×、正确/错误。
3. 点击“点击对应选项（一次）”。输入框回车不会触发鼠标操作。
4. 面板隐藏后，重新截图与本地 OCR，确认题目与原预览一致、当前未提交，定位对应选项。
5. 目标已选择则跳过单击；未选择则使用 Windows 物理屏幕坐标发送一次左键单击。
6. 等待页面更新，再截图识别，回到面板显示是否确认选中。失败不会重试。

请在过程中保持答题窗口位置及题目不变，不移动鼠标或用其他窗口遮挡目标。
按 Esc 可请求停止，面板隐藏时仍轮询 Esc；正在进行的 OCR 要等返回后停止，
已发送的单击无法撤销。只支持单选和判断题，多选及状态未知会拒绝执行。
不会自动点击提交或下一题；不调用 AI；不自动保存，按保存结果可保存验证截图及 JSON。
JSON 的 manual_click 记录输入答案、实际点击坐标及 clicked、verified 和结果说明。

模块职责：vision/manual_answer.py 负责答案规范化、匹配及一次选择状态流程；
vision/mouse_input.py 负责 Windows 原生物理坐标输入和 Esc 检查，不引入新依赖；
tools/preview_screen.py 管理输入控件、隐藏窗口和后台任务。
以后 AI 答案可通过同一个规范化与匹配入口接入，不需要改变鼠标坐标层。

本步完成实现与静态检查，新增 tests/test_manual_answer.py 使用模拟鼠标，尚未运行。
未执行真实点击或本次新增功能测试；首次实际点击由用户手动验收。

## 手动提交与下一题

新增两个独立按钮，启动命令不变。不依赖答案输入框，也不自动完成下一步。

- 点击提交（一次）：本次重新截图必须仍为同一题、明确未提交且蓝色提交按钮可用。
  单击后最多重新读取三次页面，检测同一题出现“已提交”即确认成功；不会重发提交。
  如果提交后页面自动切换，会显示页面切换提示，不补点下一题，也不宣称已单独验证提交成功。
- 点击下一题（一次）：必须确认当前题已提交、下一题可用，单击后检查题目识别标识是否变化。
  已提交且下一题灰色禁用时拒绝点击，页面摘要按约定显示全部完成。
- 题目变化、控件缺失、状态未知、坐标无效均拒绝执行。Esc 停止流程。
- 本次进程中一题只允许尝试一次提交。发送阶段报错或未确认成功时保留该题提交锁，
  重新识别不会清除锁，请人工核对页面；此锁不跨程序重启保存。

vision/manual_buttons.py 负责按钮条件检查与单击后的验证；复用原有后台任务及物理鼠标输入。
JSON 的 manual_action 包含 action、clicked、verified、question_changed、screen_center 和说明。
测试代码 tests/test_manual_buttons.py 覆盖提交、禁用状态、自动翻题、题目切换和停止，
本次只编写与静态检查，未运行测试、程序或真实页面点击。
