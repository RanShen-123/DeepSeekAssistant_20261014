"""可选真实样例测试：路径由环境变量传入，不捆绑用户截图进 Git。"""
import os
import unittest
from PIL import Image, ImageOps
from vision.page_reader import PageReader

SINGLE = os.environ.get("VISION_SAMPLE_SINGLE")
BOOLEAN = os.environ.get("VISION_SAMPLE_BOOLEAN")


@unittest.skipUnless(SINGLE and BOOLEAN, "未提供 VISION_SAMPLE_SINGLE / VISION_SAMPLE_BOOLEAN 样例路径")
class RealScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = PageReader()
        with Image.open(SINGLE) as image:
            cls.single = image.convert("RGB")
        with Image.open(BOOLEAN) as image:
            cls.boolean = image.convert("RGB")

    def assert_controls(self, result, expected_labels):
        options = [c for c in result.controls if c.kind.endswith("option")]
        self.assertEqual([c.label for c in options], expected_labels)
        self.assertTrue(all(c.confidence > .8 for c in options))
        self.assertEqual({c.id for c in result.controls if c.kind == "button"}, {"submit", "previous", "next"})

    def test_original_single_choice_and_progress(self):
        result = self.reader.read(self.single)
        self.assert_controls(result, ["A", "B", "C", "D"])
        self.assertEqual(result.question_type, "single")
        self.assertEqual(result.current_question_number, 25)
        self.assertIsNone(result.sidebar_question_number)
        self.assertEqual((result.completed_count, result.total_count), (5, 50))
        completed = [c.question_number for c in result.controls if c.state == "completed_marker"]
        self.assertEqual(completed, [1, 2, 3, 4, 5])

    def test_original_boolean_and_current_question(self):
        result = self.reader.read(self.boolean)
        self.assert_controls(result, ["true", "false"])
        self.assertEqual(result.question_type, "boolean")
        self.assertEqual(result.header_question_number, 48)
        self.assertEqual(result.sidebar_question_number, 48)
        self.assertTrue(result.question_number_consistent)
        self.assertIsNone(result.completed_count)
        self.assertIsNone(result.total_count)

    def test_scaled_samples(self):
        for image, labels, number in ((self.single, ["A", "B", "C", "D"], 25),
                                      (self.boolean, ["true", "false"], 48)):
            for scale in (.75, 1.25):
                with self.subTest(number=number, scale=scale):
                    changed = image.resize((round(image.width*scale), round(image.height*scale)), Image.Resampling.LANCZOS)
                    result = self.reader.read(changed)
                    self.assert_controls(result, labels)
                    self.assertEqual(result.current_question_number, number)

    def test_position_changes_with_padding(self):
        original = self.reader.read(self.single)
        shifted = self.reader.read(ImageOps.expand(self.single, border=(30, 20, 20, 20), fill="white"))
        self.assert_controls(shifted, ["A", "B", "C", "D"])
        before = [c for c in original.controls if c.kind == "choice_option"]
        after = [c for c in shifted.controls if c.kind == "choice_option"]
        for first, second in zip(before, after):
            self.assertLessEqual(abs(second.center[0]-first.center[0]-30), 2)
            self.assertLessEqual(abs(second.center[1]-first.center[1]-20), 2)


if __name__ == "__main__":
    unittest.main()
