"""通过 OpenAI SDK 调用 DeepSeek Flash 图像理解。"""
import base64
from pathlib import Path
from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError

PROMPT = """请分析图片中的题目，使用中文回答。
先准确读出题干和选项。选择题给出选项编号、答案和简洁解析；
计算题给出计算过程和最终结果；文字题给出简洁解释。
多道题按题号逐一回答。图片模糊或条件缺失时明确指出，不要猜测。
请按“题目 / 答案 / 解析”的结构输出。"""


def analyze_image(image_path: str | Path, config: dict) -> str:
    key = str(config.get("api_key") or "").strip()
    if not key:
        raise ValueError("缺少 API Key，请在 config.yaml 中填写 api_key。")
    model = str(config.get("model") or "deepseek-flash")
    raw = Path(image_path).read_bytes()
    if len(raw) > 30 * 1024 * 1024:
        raise ValueError("截图过大，请缩小题目区域。")
    content = [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(raw).decode("ascii")}},
    ]
    try:
        with OpenAI(api_key=key, base_url=str(config.get("base_url") or "https://api.deepseek.com"),
                    timeout=float(config.get("timeout", 90)), max_retries=0) as client:
            reply = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": content}],
                max_tokens=4096, extra_body={"thinking": {"type": "disabled"}},
            )
        if not reply.choices:
            raise RuntimeError("API 没有返回答案，请重试。")
        answer = reply.choices[0].message.content
        if not answer or not answer.strip():
            raise RuntimeError("API 返回空答案，请重试。")
        if reply.choices[0].finish_reason == "length":
            answer += "\n\n[回答达到长度限制，建议一次识别一道题。]"
        return answer
    except APITimeoutError:
        raise RuntimeError("API 请求超时，请检查网络后重试。") from None
    except APIConnectionError:
        raise RuntimeError("无法连接 DeepSeek，请检查网络或代理设置。") from None
    except APIStatusError as exc:
        messages = {400: "API 请求被拒绝，请检查模型是否支持图片及请求配置。",
                    401: "API Key 无效，请更新 config.yaml 中的 api_key。",
                    402: "API 余额不足，请检查 DeepSeek 账户余额。",
                    403: "当前 API Key 没有此模型的访问权限。",
                    404: "模型或 API 地址不存在，请检查配置。",
                    429: "请求过于频繁或额度不足，请稍后重试。"}
        raise RuntimeError(messages.get(exc.status_code,
                           f"DeepSeek 服务错误（HTTP {exc.status_code}），请稍后重试。")) from None
