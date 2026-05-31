from __future__ import annotations

import json
import logging
import unittest

from app.api.voice import timing_log


class VoiceTimingLogTests(unittest.IsolatedAsyncioTestCase):
    async def test_timing_log_records_frontend_voice_diagnostics(self) -> None:
        with self.assertLogs("app.api.voice", level=logging.INFO) as captured:
            response = await timing_log({"event": "ringtone:play:failed", "reason": "NotAllowedError"})

        self.assertEqual({"ok": True}, response)
        events = [json.loads(line.split(" ", 1)[1]) for line in captured.output]
        self.assertEqual("ringtone:play:failed", events[0]["event"])
        self.assertEqual("NotAllowedError", events[0]["reason"])


if __name__ == "__main__":
    unittest.main()
