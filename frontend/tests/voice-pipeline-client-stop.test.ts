import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const pipelineSource = fs.readFileSync(
  path.join(process.cwd(), 'lib', 'voice', 'pipeline-client.ts'),
  'utf8',
);

test('voice pipeline client stops in-flight connection setup before it can reconnect UI state', () => {
  assert.match(pipelineSource, /private stopped = false;/);
  assert.match(pipelineSource, /private ensureActive\(\): void/);
  assert.match(pipelineSource, /if \(this\.stopped\) throw new Error\('Voice pipeline stopped'\);/);
  assert.match(pipelineSource, /const turnConfigPromise = fetch\(apiUrl\('\/turn-config'\)/);
  assert.match(pipelineSource, /const localStreamPromise = navigator\.mediaDevices\.getUserMedia/);
  assert.match(pipelineSource, /await Promise\.all\(\[turnConfigPromise, localStreamPromise\]\)/);
  assert.doesNotMatch(pipelineSource, /waitForIceGathering/);
  assert.doesNotMatch(pipelineSource, /1800/);
  assert.match(pipelineSource, /if \(this\.stopped\) return;/);
  assert.match(pipelineSource, /this\.stopped = true;/);
});

test('voice pipeline client trickles queued ICE candidates after offer returns pc id', () => {
  assert.match(pipelineSource, /private pcId: string \| null = null;/);
  assert.match(pipelineSource, /private pendingIceCandidates: RTCIceCandidateInit\[\] = \[\];/);
  assert.match(pipelineSource, /peer\.onicecandidate = \(event\) => \{/);
  assert.match(pipelineSource, /this\.queueOrPatchIceCandidate\(event\.candidate\.toJSON\(\)\)/);
  assert.match(pipelineSource, /sdp_mid: candidate\.sdpMid/);
  assert.match(pipelineSource, /sdp_mline_index: candidate\.sdpMLineIndex/);
  assert.match(pipelineSource, /method: 'PATCH'/);
  assert.match(pipelineSource, /this\.pcId = typeof answer\.pc_id === 'string' \? answer\.pc_id : null;/);
  assert.match(pipelineSource, /void this\.flushPendingIceCandidates\(\);/);
});

test('voice pipeline client emits setup diagnostics with elapsed milliseconds', () => {
  assert.match(pipelineSource, /private readonly startedAt = performance\.now\(\);/);
  assert.match(pipelineSource, /private diagnostic\(event: string, detail: Record<string, unknown> = \{\}\): void/);
  assert.match(pipelineSource, /elapsed_ms: Math\.round\(performance\.now\(\) - this\.startedAt\)/);
  assert.match(pipelineSource, /this\.diagnostic\('setup:turn_config_ready'/);
  assert.match(pipelineSource, /this\.diagnostic\('setup:microphone_ready'/);
  assert.match(pipelineSource, /this\.diagnostic\('offer:answer_received'/);
  assert.match(pipelineSource, /this\.diagnostic\('setup:complete'/);
});

test('voice pipeline client reports remote audio playback diagnostics', () => {
  assert.match(pipelineSource, /onRemoteAudioStarted\?: \(\) => void;/);
  assert.match(pipelineSource, /onDiagnostic\?: \(event: string, detail\?: Record<string, unknown>\) => void;/);
  assert.match(pipelineSource, /this\.options\.onDiagnostic\?\.\('remote_audio:track'/);
  assert.match(pipelineSource, /this\.remoteAudio\.play\(\)\s+\.then\(\(\) => \{/);
  assert.match(pipelineSource, /this\.options\.onRemoteAudioStarted\?\.\(\);/);
  assert.match(pipelineSource, /this\.options\.onDiagnostic\?\.\('remote_audio:play:failed'/);
});
