# Filler Audio Environment Toggle

## Goal

Make static filler audio opt-in through an environment variable. When filler audio is disabled, the voice pipeline must follow the existing route-to-LLM-to-TTS flow without constructing or invoking the filler audio player.

## Configuration

Add `ENABLE_FILLER_AUDIO=false` to `backend/.env.example`.

Expose the value as `Settings.enable_filler_audio: bool`. Missing, empty, or false-like values disable filler audio. The values `true`, `1`, `yes`, and `on`, compared case-insensitively after trimming whitespace, enable it.

The default is disabled so deployments must explicitly opt in.

## Pipeline Wiring

In `run_pipeline()`, create the filler audio player only when `settings.enable_filler_audio` is true. Pass the player's `start` callback to `create_stable_turn_context_processor()` when enabled. Pass `None` when disabled.

The turn context processor already treats a missing callback as normal operation, so routing, LLM generation, and Rumik TTS continue unchanged when filler audio is disabled.

When enabled, retain the current filler selection, verification skip behavior, static audio queuing, and structured logs.

## Error Handling

Keep the current enabled-mode behavior: asset loading and output errors are recorded as `voice_filler_failed` events without interrupting the normal voice response.

Disabled mode does not load assets or emit filler-specific events.

## Tests

Add configuration tests covering the disabled default and enabled parsing.

Update the pipeline wiring source test to verify that construction of the filler audio player is conditional and that disabled mode passes no callback. Existing filler audio and turn context tests continue covering enabled behavior.
