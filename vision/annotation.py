"""在原尺寸图片上绘制识别边界、中心十字与页面状态摘要。"""
from pathlib import Path
from PIL import ImageDraw, ImageFont


def font(size=16):
    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def annotate(image, result):
    output = image.convert("RGB").copy()
    draw = ImageDraw.Draw(output)
    face = font(max(13, min(18, image.width//90)))
    colors = {"choice_option": "#dd2525", "boolean_option": "#dd2525", "button": "#00a050",
              "question_navigation": "#e69000"}
    boolean_index = 0
    for control in result.controls:
        x, y, w, h = control.bbox
        cx, cy = control.center
        color = "#dc00c8" if control.state == "current" else colors.get(control.kind, "#008899")
        draw.rectangle((x, y, x+w-1, y+h-1), outline=color, width=2)
        radius = min(14, max(8, w//5))
        draw.line((cx-radius, cy, cx+radius, cy), fill="red", width=2)
        draw.line((cx, cy-radius, cx, cy+radius), fill="red", width=2)
        label = {"true": "正确 √", "false": "错误 ×"}.get(control.label, control.label) or "标识未知"
        if control.kind == "question_navigation":
            state = {"current": "当前", "completed_marker": "完成", "unmarked": "未标记"}[control.state]
            label = f"{label} {state}"
            tx, ty = x+w+4, y+h//2-10
        else:
            label = f"{label} ({cx},{cy})"
            tx, ty = x, y-25
            if control.kind == "boolean_option":
                # 横排判断选项的标签错行，避免两段说明互相遮盖。
                tx, ty = x, y+h+6+boolean_index*26
                boolean_index += 1
        bounds = draw.textbbox((0, 0), label, font=face)
        tw, th = bounds[2]-bounds[0]+6, bounds[3]-bounds[1]+6
        tx, ty = max(0, min(tx, image.width-tw)), max(0, min(ty, image.height-th))
        draw.rectangle((tx, ty, tx+tw, ty+th), fill="white")
        draw.text((tx+3-bounds[0], ty+3-bounds[1]), label, font=face, fill=color)
    kind = {"single": "单选题", "boolean": "判断题", "multiple": "多选题"}.get(result.question_type, "未知")
    done = f"{result.completed_count}/{result.total_count}" if result.completed_count is not None else "未知（未用题号代替）"
    summary = (f"本地 OCR + OpenCV\n题型：{kind}    当前题号：{result.current_question_number or '未知'}\n"
               f"顶部：{result.header_question_number or '未知'}    侧栏：{result.sidebar_question_number or '未见当前框'}\n"
               f"已完成：{done}")
    bounds = draw.multiline_textbbox((0, 0), summary, font=face, spacing=5)
    pw, ph = bounds[2]-bounds[0]+20, bounds[3]-bounds[1]+20
    px, py = max(0, image.width-pw-20), 12
    draw.rectangle((px, py, px+pw, py+ph), fill="#f5f9ff", outline="#2e65b5", width=2)
    draw.multiline_text((px+10-bounds[0], py+10-bounds[1]), summary, font=face, fill="#153c70", spacing=5)
    return output
