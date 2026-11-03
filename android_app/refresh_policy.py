"""Pure-Python render budget for Android dashboard pages.

The background service continues polling at its existing rate. Only Kivy
widget refreshes are coalesced; actions and the newest snapshot remain live.
"""

# These pages have time-dependent UI even without new service data.
# Keep chat's send-ack timeout responsive; other pages need only 1 Hz.
PERIODS = {'聊天': 0.5, '遠征': 1.0, '製作': 1.0,
           '副本資料': 1.0, '經驗效率': 1.0}
IDLE_REFRESH_SECONDS = 5.0
MIN_RENDER_SECONDS = 0.9


class RefreshPolicy:
    """Limit expensive Kivy refresh work without dropping state transitions."""

    def __init__(self):
        self.page = None
        self.revision = None
        self.live = None
        self.last = float('-inf')

    def should_refresh(self, page, revision, live, now):
        if page is None:
            return False
        # A navigation change or connection loss/restoration updates at once.
        urgent = page != self.page or live != self.live
        elapsed = now - self.last
        if not urgent:
            interval = 0.5 if page == '聊天' else MIN_RENDER_SECONDS
            if elapsed < interval:
                return False
            if (revision == self.revision and elapsed <
                    PERIODS.get(page, IDLE_REFRESH_SECONDS)):
                return False
        self.page, self.revision, self.live, self.last = page, revision, live, now
        return True
