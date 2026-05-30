from __future__ import annotations

from pathlib import Path
import unittest


class PipecatPipelineOrderTests(unittest.TestCase):
    def test_tts_receives_llm_text_before_assistant_aggregator_records_context(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")
        llm_index = source.index("            llm,")
        tts_index = source.index("            tts,")
        assistant_index = source.index("            assistant_aggregator,")
        output_index = source.index("            transport.output(),")

        self.assertLess(llm_index, tts_index)
        self.assertLess(tts_index, assistant_index)
        self.assertLess(assistant_index, output_index)


if __name__ == "__main__":
    unittest.main()
