# DeepSeek AI 答题助手

Windows / Python 3.11+ / PyQt6。支持悬浮窗口、框选题目区域、保存配置、
mss 截图、DeepSeek 图片分析和答案显示。

## 安装与启动

在本项目目录运行 PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

现有虚拟环境已安装依赖时，只需运行最后一条命令。Python 3.12 同样支持。

## 使用流程

1. 首次启动没有选区时自动显示半透明屏幕遮罩。
2. 左键拖动框选题目，松开保存到 config.yaml；Esc 或右键取消。
   选区需要至少 10 × 10 像素，且限于单个显示器内。支持多屏和不同缩放比例。
3. 以后点击“识别题目”，助手暂时隐藏，自动截取保存区域并发送至 DeepSeek。
4. 截图后助手恢复，状态显示 AI 正在分析，最终在答案区显示题干、答案和解析。
5. 题目位置变化或显示器布局变化时，点击“设置题目区域”重新框选。

拖动标题栏移动，拖动右下角缩放；答案可以选中复制。
请求期间仍可操作其他应用，但为了安全释放后台线程，需等待请求结束后关闭助手。
API 等待时间默认 90 秒，无自动重试。

## 配置

config.yaml 保存在项目目录中，启动位置改变也能找到配置。
config.example.yaml 是不含密钥的配置样例。实际 config.yaml 已由 .gitignore 排除。

```yaml
api_key: "填写你的密钥"
base_url: "https://api.deepseek.com"
model: "deepseek-flash"
timeout: 90
screen_region: null
```

选区保存后为 x、y、width、height 的物理像素坐标，允许负坐标。
每次识别重新读取配置，修改 API Key 后无需重启。
timeout 允许 1 到 300 秒。模型使用当前官方支持图片输入的 deepseek-flash；
参考：https://api-docs.deepseek.com/guides/vision/

截图存放在 screenshots/，不自动删除，也不加入版本控制；
图片会发送至配置中的 API 服务。不要框入题目之外的私人内容。

## 文件作用

| 文件 | 作用 |
| --- | --- |
| main.py | DPI 初始化、应用入口、连接窗口与控制器、首次启动检查。 |
| ui/main_window.py | 置顶悬浮窗口、拖动缩放、按钮、状态、答案、忙碌时关闭保护。 |
| ui/selector.py | 各屏幕遮罩、鼠标框选、取消、逻辑与物理像素转换。 |
| ui/controller.py | 配置读取、首次框选、保存、隐藏窗口截图、任务生命周期。 |
| core/config.py | YAML 读取、选区校验、原子保存与固定项目路径。 |
| core/screenshot.py | 校验当前屏幕范围、mss 截图、Pillow 保存 PNG。 |
| core/deepseek.py | 图片 Base64 编码、OpenAI SDK、Prompt、网络及 API 错误处理。 |
| core/worker.py | 后台线程执行截图与 API 请求，通过信号更新主窗口。 |
| config.yaml | 本地密钥、模型、请求超时与选区配置。 |
| config.example.yaml | 无密钥配置模板。 |
| requirements.txt | 项目运行依赖。 |
| tests/test_assistant.py | 无网络、无用户密钥的回归测试。 |
| tests/live_api_check.py | 使用程序生成的算术题图片测试真实 API，不截取桌面。 |

## 故障处理

- 没有区域：点击“设置题目区域”；首次框选取消后也需要手动选择。
- 密钥无效或余额不足：按界面提示更新配置或检查 DeepSeek 账户。
- 模型不支持图片：确认 base_url 和 model 与官方文档匹配。
- 网络/超时：检查网络、代理设置，随后重试；必要时适当调整 timeout。
- 截图失败或区域不在屏幕内：重新框选，检查 screenshots 目录写入权限。
- YAML 格式错误：对照 config.example.yaml 修正。
- 功能仍显示“尚未接入”：关闭之前启动的旧窗口，重新运行 main.py。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_assistant -v
.\.venv\Scripts\python.exe -m tests.live_api_check
```

第一条是本地测试。第二条会读取本地密钥并发送一次真实 API 请求，可能消耗少量额度。

## 第二版自动答题

第二版在原悬浮助手中新增“开始自动答题”和“停止（Esc）”，保留原单次识别。
启动仍使用 `.\.venv\Scripts\python.exe main.py`。
先重新框入题型、完整题干、全部选项、提交及下一题；点击开始后会真实调用 AI 并操作页面。
使用方法、停止方式、当前限制与验证情况见 [自动答题说明](docs/AUTO_ANSWER.md)。
完整依赖组为 requirements-auto.txt。已执行离线识别和模拟回归；真实 AI 与页面点击仍需手动验收。
异常暂停会在 outputs/auto_debug_日期时间_编号 中保存最近截图及识别证据，不包含 API 密钥。
确认提交成功后不再保留待确认锁。重新作答或切换另一套题，可使用“新一轮答题（清除旧记录）”；
核验中断后恢复同一题，使用“重新检查并重试本题”。普通开始保留尚未确认的提交记录。
