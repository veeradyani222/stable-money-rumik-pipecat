# Persistent Rumik WebSocket Through Pipecat

## Goal

Reduce the audible mid-reply pauses caused by opening a new Rumik HTTP session
and WebSocket connection for each sentence. Keep sentence-sized synthesis
requests so the first sentence can begin playing before the LLM finishes the
entire reply.

The change must remain inside Pipecat's TTS lifecycle. Browser playback and the
frontend voice transport are out of scope.

## Current Behavior

`PipecatRumikTTSService` inherits Pipecat's default sentence aggregation. This
is appropriate for first-audio latency, but its `run_tts()` implementation
calls `adapter.pcm_chunks(text)` for every sentence. The adapter then:

1. Calls `POST /v1/tts/ws-connect`.
2. Opens a new Rumik WebSocket with the returned one-time token.
3. Sends one complete sentence.
4. Reads PCM chunks until Rumik sends `{"type": "done"}`.
5. Closes the WebSocket.

For a two-sentence answer this repeats the HTTP session creation and WebSocket
handshake between sentences, producing a multi-second audible break.

## Rumik Protocol Constraints

The supplied Rumik Voice API guide documents:

- A Rumik WebSocket connection may accept multiple complete text messages.
- Each text request produces binary PCM chunks followed by a JSON `done`
  message.
- The connection has a one-minute idle timeout.
- The connection can be closed gracefully with `{"type": "close"}`.
- The protocol does not document incremental token continuation for a single
  utterance.
- Responses do not include a Pipecat context ID.

The implementation will therefore reuse one socket while keeping Pipecat's
sentence aggregation. It will not enable token aggregation.

## Design

### Pipecat Service

Replace the current Pipecat wrapper with a Rumik-specific subclass of
Pipecat's `WebsocketTTSService`.

The service will:

- Open a Rumik WebSocket when Pipecat starts the TTS service.
- Reuse that WebSocket for sentence-sized `run_tts()` requests.
- Use Pipecat's default sentence aggregation.
- Continue using Pipecat audio contexts, `TTSStartedFrame`,
  `TTSAudioRawFrame`, and `TTSStoppedFrame`.
- Close the Rumik socket when Pipecat stops or cancels the service.
- Reconnect through the Pipecat websocket lifecycle after an idle close or
  network failure.

### Ordered Requests

Rumik does not echo a Pipecat context ID. The adapter will maintain an ordered
queue of pending sentence requests. Each queued item stores the Pipecat
`context_id` associated with that sentence.

Only one complete Rumik text request will be active at a time:

1. `run_tts()` queues the sentence and ensures the sender task is running.
2. The sender task sends the next sentence over the persistent socket.
3. The receiver task associates incoming binary PCM chunks with the active
   queued request and appends `TTSAudioRawFrame` objects to its Pipecat audio
   context.
4. On Rumik `done`, the receiver appends a Pipecat `TTSStoppedFrame`, removes
   the completed audio context, and allows the next sentence to be sent.

Serial request handling matches the documented Rumik protocol and avoids
mixing audio from adjacent sentences.

### Interruption And Shutdown

On interruption or cancellation:

- Drop queued sentences that have not started.
- Clear the active request bookkeeping.
- Close the Rumik WebSocket gracefully when possible.
- Let Pipecat discard interrupted audio contexts.
- Establish a fresh Rumik socket before the next synthesis request.

On an idle timeout or network error:

- Let Pipecat's websocket reconnect lifecycle create a fresh Rumik session
  token and socket.
- Retry an unsent queued sentence after reconnect.
- Report a Pipecat error frame if reconnection cannot recover.

### Opening Prefetch

The existing opening prefetch mechanism creates a separate one-shot Rumik
stream. Remove it from the Pipecat bot integration when the persistent service
is introduced. Starting the Pipecat websocket service early provides the warm
connection needed for the opening and subsequent replies without maintaining
two competing Rumik connections.

## Expected Result

The change removes the avoidable mid-reply pause caused by repeated
`/v1/tts/ws-connect` calls and WebSocket handshakes. It preserves earlier first
audio because each complete sentence is still sent as soon as Pipecat detects
its boundary.

The design does not claim mathematically gapless sentence boundaries. A short
boundary pause may remain if Rumik cannot synthesize the next queued sentence
before playback reaches that boundary. If measurements still show an audible
gap, the next optimization is provider-supported parallel sentence synthesis
or an incremental continuation protocol from Rumik.

## Testing

Add focused backend tests for:

- One HTTP WebSocket-session creation across multiple sentence requests.
- Ordered reuse of the same Rumik WebSocket.
- PCM chunks mapped to the active Pipecat context.
- `done` advancing to the next queued sentence.
- Graceful close during stop or cancel.
- Reconnect after an idle or network close.
- Queued sentence cleanup after interruption.

Run the focused TTS tests and the backend test suite before completion.

