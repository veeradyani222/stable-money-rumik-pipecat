import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const clientSource = fs.readFileSync(
  path.join(process.cwd(), 'components', 'agent', 'AgentCallClient.tsx'),
  'utf8',
);

test('agent call client attaches a local stream analyser for the visualizer', () => {
  assert.match(clientSource, /onLocalStream/);
  assert.match(clientSource, /attachLocalAnalyser/);
  assert.match(clientSource, /createAnalyser\(\)/);
  assert.match(clientSource, /analyser\.fftSize = 1024/);
  assert.match(clientSource, /source\.connect\(analyser\)/);
  assert.match(clientSource, /setVoiceAnalyser\(analyser\)/);
});

test('agent call client uses connected listening state to drive the visualizer', () => {
  assert.match(clientSource, /callState === 'connected' && isListening/);
  assert.match(clientSource, /speaker=\{visualizerSpeaker\}/);
  assert.match(clientSource, /analyser=\{callState === 'connected' \? voiceAnalyser : null\}/);
});
