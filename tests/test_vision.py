"""离线识别单元测试，使用生成图片与假 OCR，不访问桌面、密钥或 API。"""
import unittest
from unittest.mock import MagicMock
from PIL import Image, ImageDraw
import cv2
import numpy as np
from vision.models import TextLine
from vision.ocr_engine import LocalOCR
from vision.page_reader import PageReader
from vision.controls import classify_boolean_symbol, options, buttons, header_without_accent
from vision.annotation import annotate


class FakeOCR:
    def __init__(self, lines=(), cropped=()):
        self.lines, self.cropped = list(lines), list(cropped)

    def read(self, bgr):
        return self.lines

    def read_crop(self, bgr, box, **kwargs):
        return self.cropped


def blank():
    return Image.new("RGB", (1000, 700), "white")


def sidebar_image(number=48):
    image = blank()
    ImageDraw.Draw(image).rounded_rectangle((40, 330, 100, 390), radius=6, fill=(47, 105, 244))
    lines = [TextLine("48.判断题 (1分)", .98, [220, 40, 200, 30]),
             TextLine(str(number), .99, [54, 344, 30, 30])]
    return image, lines


class VisionTests(unittest.TestCase):
    def test_header_and_sidebar_agree(self):
        image, lines = sidebar_image()
        result = PageReader(FakeOCR(lines)).read(image)
        self.assertEqual(result.question_type, "boolean")
        self.assertEqual(result.header_question_number, 48)
        self.assertEqual(result.sidebar_question_number, 48)
        self.assertTrue(result.question_number_consistent)
        self.assertEqual(result.current_question_number, 48)
        self.assertIsNone(result.completed_count)

    def test_header_sidebar_conflict_is_not_guessed(self):
        image, lines = sidebar_image(47)
        result = PageReader(FakeOCR(lines)).read(image)
        self.assertFalse(result.question_number_consistent)
        self.assertIsNone(result.current_question_number)
        self.assertTrue(any("冲突" in warning for warning in result.warnings))

    def test_header_25_is_not_completed_25(self):
        lines = [TextLine("25.单选题", .99, [220, 40, 180, 30]),
                 TextLine("5/50题", .99, [40, 100, 80, 25])]
        result = PageReader(FakeOCR(lines)).read(blank())
        self.assertEqual(result.current_question_number, 25)
        self.assertIsNone(result.sidebar_question_number)
        self.assertEqual((result.completed_count, result.total_count), (5, 50))

    def test_conflicting_progress_counters_remain_unknown(self):
        lines = [TextLine("5/50", .99, [30, 30, 80, 25]), TextLine("6/50", .99, [30, 60, 80, 25])]
        result = PageReader(FakeOCR(lines)).read(blank())
        self.assertIsNone(result.completed_count)

    def test_empty_image_is_unknown(self):
        result = PageReader(FakeOCR()).read(blank())
        self.assertEqual(result.controls, [])
        self.assertIsNone(result.question_type)
        self.assertIsNone(result.current_question_number)

    def test_boolean_symbols_are_classified_by_strokes_not_side(self):
        for reverse in (False, True):
            image = blank()
            draw = ImageDraw.Draw(image)
            boxes = [[220, 220, 41, 41], [300, 220, 41, 41]]
            labels = ["false", "true"] if reverse else ["true", "false"]
            for box, label in zip(boxes, labels):
                x, y, w, h = box
                draw.ellipse((x, y, x+w-1, y+h-1), outline=(160, 160, 160), width=1)
                if label == "true":
                    draw.line([(x+10, y+20), (x+17, y+27), (x+29, y+12)], fill=(150, 150, 150), width=2)
                else:
                    draw.line([(x+13, y+13), (x+27, y+27)], fill=(150, 150, 150), width=2)
                    draw.line([(x+13, y+27), (x+27, y+13)], fill=(150, 150, 150), width=2)
            bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            actual = [classify_boolean_symbol(bgr, box)[0] for box in boxes]
            self.assertEqual(actual, labels)

    def test_empty_circle_symbol_is_unknown(self):
        image = blank()
        ImageDraw.Draw(image).ellipse((220, 220, 260, 260), outline="gray", width=1)
        bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        self.assertIsNone(classify_boolean_symbol(bgr, [220, 220, 41, 41])[0])

    def test_letters_use_ocr_not_vertical_order(self):
        image = blank()
        draw = ImageDraw.Draw(image)
        lines = []
        for y, label in ((200, "D"), (270, "A")):
            draw.ellipse((220, y, 260, y+40), outline="gray", width=1)
            lines.append(TextLine(label, .99, [230, y+10, 20, 20]))
        bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        result = options(bgr, lines, FakeOCR(), "single", 150)
        self.assertEqual([c.label for c in result], ["D", "A"])

    def test_no_letter_ocr_does_not_invent_abcd(self):
        image = blank()
        draw = ImageDraw.Draw(image)
        for y in (200, 270):
            draw.ellipse((220, y, 260, y+40), outline="gray", width=1)
        bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        result = options(bgr, [], FakeOCR(), "single", 150)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(c.label is None for c in result))

    def test_button_meaning_comes_from_text_not_position(self):
        lines = [TextLine("下一题", .99, [250, 630, 90, 25]),
                 TextLine("上一题", .99, [800, 630, 90, 25])]
        bgr = cv2.cvtColor(np.array(blank()), cv2.COLOR_RGB2BGR)
        result = buttons(bgr, lines)
        self.assertEqual([c.id for c in result], ["next", "previous"])
        self.assertTrue(all(c.enabled is None for c in result))

    def test_cropped_ocr_accepts_recognition_only_result_format(self):
        reader = LocalOCR.__new__(LocalOCR)
        reader.engine = MagicMock(return_value=([["C", .98]], [0]))
        bgr = np.full((100, 100, 3), 255, np.uint8)
        self.assertEqual(reader.read_crop(bgr, [10, 10, 20, 20]), [("C", .98)])

    def test_header_crop_ignores_thin_blue_antialiasing_noise(self):
        bgr = np.full((700, 1000, 3), 255, np.uint8)
        cv2.rectangle(bgr, (220, 40), (225, 66), (255, 110, 60), -1)
        cv2.line(bgr, (250, 45), (250, 55), (255, 110, 60), 1)
        ocr = MagicMock()
        ocr.read_crop.return_value = [("48.判断题", .99)]
        header_without_accent(bgr, TextLine("148.判断题", .9, [210, 38, 200, 35]), ocr)
        bbox = ocr.read_crop.call_args.args[1]
        self.assertLess(bbox[0], 240)

    def test_annotation_does_not_resize_or_mutate_original(self):
        image, lines = sidebar_image()
        result = PageReader(FakeOCR(lines)).read(image)
        original = image.tobytes()
        marked = annotate(image, result)
        self.assertEqual(marked.size, image.size)
        self.assertEqual(image.tobytes(), original)
        self.assertNotEqual(marked.tobytes(), original)


if __name__ == "__main__":
    unittest.main()
