from __future__ import annotations

from pathlib import Path
import unittest


class PipecatPipelineOrderTests(unittest.TestCase):
    def test_tts_receives_llm_text_before_assistant_aggregator_records_context(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")
        llm_index = source.index("            llm,")
        tts_index = source.index("            tts,")
        assistant_index = source.index("            assistant_aggregator,")
        opening_notifier_index = source.index("            opening_audio_ready_notifier,")
        output_index = source.index("            output_transport,")

        self.assertLess(llm_index, tts_index)
        self.assertLess(tts_index, assistant_index)
        self.assertLess(assistant_index, opening_notifier_index)
        self.assertLess(opening_notifier_index, output_index)

    def test_bot_notifies_browser_when_opening_audio_is_about_to_play(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")

        self.assertIn("def create_opening_audio_ready_notifier(", source)
        self.assertIn("OutputTransportMessageUrgentFrame", source)
        self.assertIn("TTSAudioRawFrame", source)
        self.assertIn('"voice_audio_ready"', source)
        self.assertIn('"voice_opening_audio_ready"', source)

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

    def test_bot_starts_rumik_preconnect_without_blocking_pipeline_start(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")

        tts_index = source.index("    tts = create_pipecat_rumik_tts_service()")
        preconnect_index = source.index("    rumik_preconnect_task = asyncio.create_task(tts.preconnect())")
        runner_index = source.index("    await runner.run()")

        self.assertLess(tts_index, preconnect_index)
        self.assertLess(preconnect_index, runner_index)
        self.assertIn("rumik_preconnect_task.add_done_callback", source)
        self.assertNotIn("await rumik_preconnect_task", source)

    def test_bot_queues_static_fillers_directly_to_output_during_turn_routing(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")

        self.assertIn("output_transport = transport.output()", source)
        self.assertIn('"voice_pipeline_configured"', source)
        self.assertIn("enable_filler_audio=settings.enable_filler_audio", source)
        self.assertIn("if settings.enable_filler_audio", source)
        self.assertIn("create_filler_audio_player(", source)
        self.assertIn("output=output_transport", source)
        self.assertIn("start_filler_audio=start_filler_audio", source)
        self.assertIn("            output_transport,", source)


if __name__ == "__main__":
    unittest.main()
