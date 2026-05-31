import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const pipelineSource = fs.readFileSync(
  path.join(process.cwd(), 'lib', 'voice', 'pipeline-client.ts'),
  'utf8',
);

test('voice pipeline client can start a Pipecat Cloud session before creating the offer', () => {
  assert.match(pipelineSource, /NEXT_PUBLIC_PIPECAT_CLOUD_AGENT_NAME/);
  assert.match(pipelineSource, /NEXT_PUBLIC_PIPECAT_CLOUD_PUBLIC_API_KEY/);
  assert.match(pipelineSource, /startPipecatCloudSession/);
  assert.match(pipelineSource, /transport: 'webrtc'/);
  assert.match(pipelineSource, /Authorization': `Bearer \$\{cloudConfig\.publicApiKey\}`/);
  assert.match(pipelineSource, /sessionId/);
  assert.match(pipelineSource, /enableDefaultIceServers: true/);
});

test('voice pipeline client sends WebRTC signaling to the cloud session endpoint when configured', () => {
  assert.match(pipelineSource, /private offerUrl = apiUrl\('\/offer'\);/);
  assert.match(pipelineSource, /private patchOfferUrl = apiUrl\('\/offer'\);/);
  assert.match(pipelineSource, /this\.offerUrl = cloudSession\.offerUrl;/);
  assert.match(pipelineSource, /this\.patchOfferUrl = cloudSession\.offerUrl;/);
  assert.match(pipelineSource, /private signalingHeaders: HeadersInit = \{ 'Content-Type': 'application\/json' \};/);
  assert.match(pipelineSource, /private signalingFetchOptions: RequestCredentials = 'include';/);
  assert.match(pipelineSource, /credentials: this\.signalingFetchOptions/);
  assert.match(pipelineSource, /this\.signalingFetchOptions = 'omit';/);
  assert.match(pipelineSource, /headers: this\.signalingHeaders/);
  assert.match(pipelineSource, /fetch\(this\.offerUrl/);
  assert.match(pipelineSource, /fetch\(this\.patchOfferUrl/);
});
