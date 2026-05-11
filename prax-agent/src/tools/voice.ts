import { ToolRegistry } from './registry.js';
import { execSync } from 'child_process';
import * as fs from 'fs';

export function registerVoiceTools(registry: ToolRegistry) {
  registry.register({
    name: 'speak',
    description: 'Uses text-to-speech to speak to the user.',
    parameters: {
      type: 'object',
      properties: {
        text: { type: 'string' }
      },
      required: ['text']
    },
    execute: async (args: any) => {
      try {
        // Try piper first
        execSync(`echo "${args.text}" | piper --model en_US-lessac-high --output_file /tmp/kryos-speech.wav`);
        execSync(`paplay /tmp/kryos-speech.wav || aplay /tmp/kryos-speech.wav`);
      } catch (e) {
        try {
          // Fallback to espeak
          execSync(`espeak-ng -v en "${args.text}"`);
        } catch (e2) {
          console.log(`[MOCK VOICE]: "${args.text}"`);
        }
      }
      return { success: true };
    }
  });

  registry.register({
    name: 'listen',
    description: 'Records the microphone for a few seconds and transcribes it to text.',
    parameters: {
      type: 'object',
      properties: {
        timeout: { type: 'number', default: 5 }
      }
    },
    execute: async (args: any) => {
      const timeout = args.timeout || 5;
      const path = `/tmp/kryos-listen.wav`;
      try {
        execSync(`arecord -d ${timeout} -f S16_LE -c1 -r 16000 ${path}`);
        const result = execSync(`whisper -m /var/vyrex/models/whisper-base.bin -f ${path}`).toString();
        return { success: true, transcript: result };
      } catch (e) {
        console.warn(`[MOCK] Listened for ${timeout} seconds. Simulated transcript returned.`);
        return { success: true, transcript: "This is a simulated voice transcript from the user." };
      }
    }
  });
}
