"""CPU 本地 OCR；模型来自安装包，不向远端发送图片。"""
import cv2
from vision.models import TextLine


class LocalOCR:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR(text_score=.45, det_use_cuda=False, rec_use_cuda=False,
                               cls_use_cuda=False, intra_op_num_threads=2, inter_op_num_threads=1)

    def read(self, bgr):
        results, _ = self.engine(bgr, use_cls=False)
        lines = []
        for box, content, score in results or []:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            left, top = max(0, int(min(xs))), max(0, int(min(ys)))
            right, bottom = min(bgr.shape[1], int(max(xs))+1), min(bgr.shape[0], int(max(ys))+1)
            if right > left and bottom > top:
                lines.append(TextLine(str(content), float(score), [left, top, right-left, bottom-top]))
        return lines

    def read_crop(self, bgr, bbox, *, invert=False):
        x, y, w, h = bbox
        crop = bgr[y:y+h, x:x+w]
        if crop.size == 0:
            return []
        if invert:
            crop = 255-crop
        scale = 3
        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        results, _ = self.engine(enlarged, use_det=False, use_cls=False)
        # 关闭检测时 RapidOCR 返回 [文字, 置信度]，与整图的三元素记录不同。
        return [(str(item[0]).strip(), float(item[1])) if len(item) == 2
                else (str(item[1]).strip(), float(item[2])) for item in results or []]
