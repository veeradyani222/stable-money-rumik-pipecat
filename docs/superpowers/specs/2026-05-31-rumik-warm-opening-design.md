# Rumik Warm Opening Design

## Goal

Reduce the silence after a Pipecat call connects by preparing Rumik opening-line audio before the transport asks TTS to speak, and keep the ringing sound active until real assistant audio starts.

## Approach

The Pipecat backend will create one Rumik TTS service instance per call and prewarm the default opening text when the bot starts. The prewarm opens the Rumik websocket and sends the opening text, buffering early PCM chunks so `run_tts()` can replay them immediately when the opening `TTSSpeakFrame` is queued.

For later turns, the same service object remains alive for the call, but each utterance still uses its own Rumik session because the provider session is text-scoped. This keeps call-local state and cached opening audio warm without changing the rest of Pipecat's TTS contract.

The frontend already monitors the remote audio stream and stops ringing only when non-silent audio is detected. That behavior stays intact and gets a regression test so the ringtone does not stop merely because WebRTC connects or an audio element starts playback.

## Error Handling

If opening prewarm fails, the backend logs the error and falls back to normal just-in-time Rumik synthesis. The call should still connect and speak; only the latency optimization is lost.

## Tests

Backend tests cover:

- Opening prewarm starts before the `on_client_connected` opening queue point.
- Prefetched opening audio is consumed once by `pcm_chunks()`.
- Failed prewarm falls back to normal synthesis.

Frontend tests cover:

- Ringing starts on call start.
- Ringing stops on detected Rumik voice, not on WebRTC connection or audio element playback.
