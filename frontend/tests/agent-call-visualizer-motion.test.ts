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
  assert.match(clientSource, /analyser=\{visualizerAnalyser\}/);
});

test('agent call client shows thinking sweep between user speech and Rumik speech', () => {
  assert.match(clientSource, /type AgentConversationPhase = 'user' \| 'thinking' \| 'agent'/);
  assert.match(clientSource, /const \[agentPhase, setAgentPhase\] = useState<AgentConversationPhase>\('user'\)/);
  assert.match(clientSource, /setAgentPhase\('thinking'\)/);
  assert.match(clientSource, /setAgentPhase\('agent'\)/);
  assert.match(clientSource, /const voiceOrbState = callState === 'connected' \? agentPhase : callState/);
  assert.match(clientSource, /voice-orb voice-orb--\$\{voiceOrbState\}/);
});

test('agent call client colors visualizer bars by the current speaker', () => {
  assert.match(clientSource, /if \(callState === 'connected' && agentPhase === 'agent'\) return 'agent'/);
  assert.match(clientSource, /if \(callState === 'connected' && isListening\) return 'user'/);
  assert.match(clientSource, /const visualizerAnalyser = callState === 'connected' && agentPhase !== 'agent' \? voiceAnalyser : null/);
  assert.match(clientSource, /analyser=\{visualizerAnalyser\}/);
});

test('agent visualizer stays gold during quiet gaps in the agent speaking turn', () => {
  assert.match(clientSource, /setAgentPhase\('agent'\)/);
  assert.doesNotMatch(clientSource, /RUMIK_VOICE_END_FRAMES/);
  assert.doesNotMatch(clientSource, /hasDetectedSpeech[\s\S]{0,240}setNextAgentPhase\('user'\)/);
});
