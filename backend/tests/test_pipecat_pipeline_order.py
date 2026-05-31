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

    def test_bot_uses_local_vad_explicit_turn_strategies_muting_and_observers(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")

        self.assertIn("turn_detection=False", source)
        self.assertNotIn("turn_detection=None", source)
        self.assertIn("LLMUserAggregatorParams(", source)
        self.assertIn("vad_analyzer=SileroVADAnalyzer(params=VADParams())", source)
        self.assertIn("UserTurnStrategies(", source)
        self.assertIn("VADUserTurnStartStrategy()", source)
        self.assertIn("TranscriptionUserTurnStartStrategy()", source)
        self.assertIn("SmartTurnParams(stop_secs=0.8, max_duration_secs=5)", source)
        self.assertIn(
            "TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3(params=smart_turn_params))",
            source,
        )
        self.assertIn("MuteUntilFirstBotCompleteUserMuteStrategy()", source)
        self.assertIn("FunctionCallUserMuteStrategy()", source)
        self.assertIn("MetricsLogObserver()", source)
        self.assertIn("UserBotLatencyObserver()", source)
        self.assertIn("StartupTimingObserver()", source)
        self.assertIn("observers=[metrics_observer, latency_observer, startup_observer]", source)
        self.assertIn("@latency_observer.event_handler(\"on_latency_measured\")", source)
        self.assertIn("@startup_observer.event_handler(\"on_startup_timing_report\")", source)

    def test_bot_starts_rumik_preconnect_before_pipeline_runs(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")

        tts_index = source.index("    tts = create_pipecat_rumik_tts_service()")
        preconnect_index = source.index("    rumik_preconnect_task = asyncio.create_task(tts.preconnect())")
        runner_index = source.index("    await runner.run()")

        self.assertLess(tts_index, preconnect_index)
        self.assertLess(preconnect_index, runner_index)
        self.assertIn("await rumik_preconnect_task", source)


if __name__ == "__main__":
    unittest.main()
