from __future__ import annotations

from pathlib import Path
import unittest


class PipecatCloudEntrypointTests(unittest.TestCase):
    def test_cloud_bot_entrypoint_delegates_to_backend_package(self) -> None:
        source = Path("bot.py").read_text(encoding="utf-8")

        self.assertIn("from app.pipecat_pipeline.bot import bot", source)
        self.assertIn("__all__ = [\"bot\"]", source)

    def test_pipeline_bot_accepts_small_webrtc_runner_arguments(self) -> None:
        source = Path("app/pipecat_pipeline/bot.py").read_text(encoding="utf-8")

        self.assertIn("async def bot(runner_args: Any) -> None:", source)
        self.assertIn("SmallWebRTCRunnerArguments", source)
        self.assertIn("runner_args.webrtc_connection", source)
        self.assertIn("runner_args.body", source)

    def test_pipecat_cloud_deploy_files_exist_and_use_backend_context(self) -> None:
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        deploy_config = Path("../pcc-deploy.toml").read_text(encoding="utf-8")

        self.assertIn("FROM dailyco/pipecat-base:", dockerfile)
        self.assertIn("COPY ./bot.py bot.py", dockerfile)
        self.assertIn("COPY ./app ./app", dockerfile)
        self.assertIn("agent_name = \"stable-money-rumik\"", deploy_config)
        self.assertIn("secret_set = \"stable-money-rumik-secrets\"", deploy_config)
        self.assertIn('context_dir = "backend"', deploy_config)
        self.assertIn('dockerfile = "Dockerfile"', deploy_config)


if __name__ == "__main__":
    unittest.main()
