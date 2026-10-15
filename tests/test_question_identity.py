"""题目标识回归：装饰条误读/分行不影响同题，题干与选项变化必须拦截。"""
import unittest
import os
from vision.models import Control, TextLine
from vision.question_identity import build_identity


def sample(header="28.单选题", stem="Runway在数字人制作中的作用是()", option="动态视频生成"):
    choices = [Control("option_"+label, "choice_option", label,
                       [20, 200+i*70, 50, 50], [45, 225+i*70], .99, "测试")
               for i, label in enumerate("ABCD")]
    lines = [TextLine(header, .99, [20, 20, 220, 30]),
             TextLine(stem, .99, [20, 100, 500, 30])]
    lines.extend(TextLine(text, .99, [90, 205+i*70, 180, 30])
                 for i, text in enumerate((option, "语音合成", "对话交互", "数据分析")))
    return lines, choices


class QuestionIdentityTests(unittest.TestCase):
    def test_boolean_symbols_do_not_become_neighbor_text(self):
        choices = [Control("true", "boolean_option", "true", [20, 200, 50, 50], [45, 225], .99, "测试"),
                   Control("false", "boolean_option", "false", [100, 200, 50, 50], [125, 225], .99, "测试")]
        lines = [TextLine("48.判断题", .99, [20, 20, 200, 30]),
                 TextLine("互动时不需要考虑上下文信息()", .99, [20, 100, 500, 30])]
        baseline = build_identity(lines, choices, "boolean", 50)[1]
        for text, bbox in (("X", [115, 215, 20, 20]), ("V", [35, 215, 20, 20]),
                           ("√ ×", [30, 210, 110, 30])):
            with self.subTest(text=text):
                identity, signature = build_identity(lines+[TextLine(text, .99, bbox)], choices, "boolean", 50)
                self.assertEqual(baseline, signature)
                self.assertEqual([c["text"] for c in identity["options"]], ["", ""])

    @unittest.skipUnless(os.environ.get("VISION_IDENTITY_SAMPLE"), "未提供 Runway 题目样例路径")
    def test_real_ocr_decorative_bar_regression(self):
        from PIL import Image, ImageOps
        from tools.diagnose_question import diagnose_image
        from vision.ocr_engine import LocalOCR
        with Image.open(os.environ["VISION_IDENTITY_SAMPLE"]) as source:
            image = source.convert("RGB")
        engine = LocalOCR()
        results = [diagnose_image(changed, engine)[0] for changed in
                   (image, ImageOps.expand(image, border=(2, 0, 0, 0), fill="white"),
                    image.resize((image.width+1, image.height), Image.Resampling.BICUBIC))]
        signatures = [r["report"]["question_signature"] for r in results]
        self.assertIsNotNone(signatures[0])
        self.assertEqual(len(set(signatures)), 1)
        self.assertTrue(all(r["signature_rebuild_matches"] for r in results))

    def test_blue_accent_read_as_one_does_not_change_signature(self):
        a, choices = sample()
        b, _ = sample(header="128.单选题（1分）")
        self.assertEqual(build_identity(a, choices, "single", 50)[1], build_identity(b, choices, "single", 50)[1])

    def test_line_breaks_do_not_change_signature(self):
        lines, choices = sample()
        other = [line for line in lines if line.bbox[1] != 100]
        other.extend([TextLine("Runway在数字人", .99, [20, 100, 250, 25]),
                      TextLine("制作中的作用是()", .99, [20, 135, 250, 25])])
        self.assertEqual(build_identity(lines, choices, "single", 50)[1], build_identity(other, choices, "single", 50)[1])

    def test_changed_stem_or_options_is_not_same_question(self):
        lines, choices = sample()
        original = build_identity(lines, choices, "single", 50)[1]
        for changes in ({"stem": "Runway不具备的作用是()"}, {"option": "静态图像生成"}):
            other, _ = sample(**changes)
            self.assertNotEqual(original, build_identity(other, choices, "single", 50)[1])

    def test_missing_stem_does_not_use_title_as_identity(self):
        lines, choices = sample(stem="")
        self.assertIsNone(build_identity(lines, choices, "single", 50)[1])

    def test_merged_option_label_is_stable(self):
        lines, choices = sample()
        other = list(lines)
        other[2] = TextLine("A 动态视频生成", .99, [25, 205, 245, 30])
        self.assertEqual(build_identity(lines, choices, "single", 50)[1], build_identity(other, choices, "single", 50)[1])
