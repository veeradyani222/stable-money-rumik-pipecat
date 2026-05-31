import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const clientSource = fs.readFileSync(
  path.join(process.cwd(), 'components', 'agent', 'AgentCallClient.tsx'),
  'utf8',
);

test('agent call client plays the dragon ringing asset while connecting', () => {
  assert.match(clientSource, /CONNECTING_RINGTONE_SRC = '\/assets\/dragon-ringing\.mp3'/);
  assert.match(clientSource, /ringtoneRef = useRef<HTMLAudioElement \| null>\(null\)/);
  assert.match(clientSource, /const \[ringtoneActive, setRingtoneActive\] = useState\(false\)/);
  assert.match(clientSource, /ringtone\.loop = true/);
  assert.match(clientSource, /const playConnectingRingtone = useCallback/);
  assert.match(clientSource, /logVoiceTimingEvent\('ringtone:play:request'/);
  assert.match(clientSource, /logVoiceTimingEvent\('ringtone:play:started'/);
  assert.match(clientSource, /logVoiceTimingEvent\('ringtone:play:failed'/);
  assert.match(clientSource, /playConnectingRingtone\(\);\s+setNextCallState\('connecting'\);/);
  assert.match(clientSource, /if \(!ringtoneActive\)/);
  assert.match(clientSource, /ringtone\.pause\(\)/);
  assert.match(clientSource, /ringtone\.currentTime = 0/);
  assert.match(clientSource, /void ringtone\.play\(\)\s+\.then/);
});

test('agent call client keeps connecting calls cancellable and hides the timer until connected', () => {
  assert.match(clientSource, /const stopConnectingRingtone = useCallback/);
  assert.match(clientSource, /logVoiceTimingEvent\('ringtone:stop'/);
  assert.match(clientSource, /stopConnectingRingtone\('user_end_call'\);\s+pipelineClientRef\.current\?\.stop\(\);/);
  assert.match(clientSource, /if \(pipelineClientRef\.current !== client\) return;/);
  assert.match(clientSource, /function getCallStatusLabel/);
  assert.match(clientSource, /if \(callState === 'connecting'\) return 'Connecting\.\.\.'/);
  assert.doesNotMatch(clientSource, /callState === 'error' \? error \|\| 'Call failed' : formatDuration\(duration\)/);
});

test('agent call client keeps ringing until Rumik voice audio is detected', () => {
  assert.match(clientSource, /const monitorRemoteStreamForRumikVoice = useCallback/);
  assert.match(clientSource, /onRemoteStream: \(stream\) => \{/);
  assert.match(clientSource, /void monitorRemoteStreamForRumikVoice\(stream\);/);
  assert.match(clientSource, /analyser\.getByteTimeDomainData\(data\);/);
  assert.match(clientSource, /window\.requestAnimationFrame\(sample\)/);
  assert.match(clientSource, /stopConnectingRingtone\('rumik_voice_started'\);/);
  assert.match(clientSource, /logVoiceTimingEvent\('remote_audio:voice_detected'/);
  assert.match(clientSource, /if \(ringtoneActive\) return 'Ringing\.\.\.'/);
  assert.doesNotMatch(clientSource, /if \(state === 'connected'\) \{[\s\S]{0,220}stopConnectingRingtone/);
  assert.doesNotMatch(clientSource, /onRemoteAudioStarted: \(\) => \{[\s\S]{0,180}stopConnectingRingtone/);
  assert.doesNotMatch(clientSource, /pipeline:remote_audio:element_started[\s\S]{0,120}stopConnectingRingtone/);
});
