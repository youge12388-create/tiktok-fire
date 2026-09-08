from core import automation


class _ContactPage:
    def __init__(self):
        self.responses = [
            {"items": [{"name": "有火花", "streak": "12"}, {"name": "普通私信", "streak": ""}], "atBottom": False},
            {"items": [{"name": "有火花", "streak": "12"}, {"name": "第二位", "streak": "3"}], "atBottom": True},
        ]
        self.scrolls = 0

    def evaluate(self, script):
        if script == automation._EXTRACT_JS:
            return self.responses.pop(0)
        assert script == automation._SCROLL_CHAT_LIST_JS
        self.scrolls += 1
        return True

    def wait_for_timeout(self, _timeout):
        pass


def test_contact_sync_keeps_only_streak_contacts_and_deduplicates():
    page = _ContactPage()
    collected = []

    automation._scroll_and_extract(page, collected)

    assert collected == [{"name": "有火花", "streak": "12"}, {"name": "第二位", "streak": "3"}]
    assert page.scrolls == 1


class _StalledContactPage:
    def evaluate(self, script):
        if script == automation._EXTRACT_JS:
            return {"items": [{"name": "有火花", "streak": "12"}], "atBottom": False}
        assert script == automation._SCROLL_CHAT_LIST_JS
        return False

    def wait_for_timeout(self, _timeout):
        pass


def test_contact_sync_reports_incomplete_when_scrolling_stalls():
    collected = []
    status = automation._scroll_and_extract(_StalledContactPage(), collected)

    assert [item["name"] for item in collected] == ["有火花"]
    assert status == {"complete": False, "rounds": 1, "stop_reason": "scroll_stalled"}
