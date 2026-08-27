"""§18 发送前会话切换校验：右侧会话标题区域出现目标昵称才算切换成功。"""

from core import automation


class _B:
    def __init__(self, box):
        self._box = box

    def bounding_box(self):
        return self._box


class _L:
    def __init__(self, boxes):
        self._boxes = [_B(b) for b in boxes]

    def count(self):
        return len(self._boxes)

    def nth(self, i):
        return self._boxes[i]


class _Page:
    def __init__(self, boxes):
        self._boxes = boxes

    def get_by_text(self, text, exact=False):
        return _L(self._boxes)


def test_verify_in_conversation_true_when_title_in_right_top():
    # 右上区域（x>300 且 y<100）出现目标昵称 → 判定已切换成功
    page = _Page([{"x": 400, "y": 50, "width": 100, "height": 30}])
    assert automation._verify_in_conversation(page, "甲") is True


def test_verify_in_conversation_false_when_title_elsewhere():
    # 昵称出现在左侧聊天列表（x<300），说明右侧会话并未切换 → 防错发
    page = _Page([{"x": 100, "y": 50, "width": 100, "height": 30}])
    assert automation._verify_in_conversation(page, "甲") is False


def test_verify_in_conversation_false_when_not_found():
    assert automation._verify_in_conversation(_Page([]), "甲") is False
