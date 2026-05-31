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
  assert.match(pipelineSource, /const turnConfigResponse[\s\S]*this\.ensureActive\(\);[\s\S]*const iceServers/);
  assert.match(pipelineSource, /if \(this\.stopped\) return;/);
  assert.match(pipelineSource, /this\.stopped = true;/);
});

test('voice pipeline client reports remote audio playback diagnostics', () => {
  assert.match(pipelineSource, /onRemoteAudioStarted\?: \(\) => void;/);
  assert.match(pipelineSource, /onDiagnostic\?: \(event: string, detail\?: Record<string, unknown>\) => void;/);
  assert.match(pipelineSource, /this\.options\.onDiagnostic\?\.\('remote_audio:track'/);
  assert.match(pipelineSource, /this\.remoteAudio\.play\(\)\s+\.then\(\(\) => \{/);
  assert.match(pipelineSource, /this\.options\.onRemoteAudioStarted\?\.\(\);/);
  assert.match(pipelineSource, /this\.options\.onDiagnostic\?\.\('remote_audio:play:failed'/);
});
