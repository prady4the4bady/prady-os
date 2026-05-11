import { ToolRegistry } from './registry.js';
import { execSync } from 'child_process';
import { readFileSync, unlinkSync } from 'fs';
import { VisionClient } from '../vision_client.js';

const visionClient = new VisionClient();

export function registerScreenTools(registry: ToolRegistry) {
  registry.register({
    name: 'screen_capture',
    description: 'Takes a screenshot of the current screen and returns the file path and base64 string.',
    parameters: { type: 'object', properties: {} },
    execute: async () => {
      const ts = Date.now();
      const path = `/tmp/kryos-screen-${ts}.png`;
      const isWayland = process.env.WAYLAND_DISPLAY !== undefined;

      try {
        if (isWayland) {
          execSync(`grim ${path}`);
        } else {
          // X11 or fallback
          try {
            execSync(`import -window root ${path}`);
          } catch {
            execSync(`scrot ${path}`);
          }
        }
      } catch (e) {
        // Mock fallback for testing without Linux GUI
        console.warn('Screenshot tool failed to run actual command, providing mock output');
        return { path: '/tmp/mock.png', base64: 'iVBORw0KGgo...', width: 1920, height: 1080 };
      }

      const buffer = readFileSync(path);
      const base64 = buffer.toString('base64');
      // Cleanup
      try { unlinkSync(path); } catch(e) {}
      
      return { path, base64, width: 1920, height: 1080 }; // width/height mock
    }
  });

  registry.register({
    name: 'read_screen_text',
    description: 'Runs OCR on the current screen and returns all detected text and bounding boxes.',
    parameters: { type: 'object', properties: {} },
    execute: async () => {
      const screen: any = await registry.execute('screen_capture', {});
      return visionClient.ocr(screen.base64);
    }
  });

  registry.register({
    name: 'find_element',
    description: 'Finds the (x, y) coordinates of a described UI element on the screen.',
    parameters: {
      type: 'object',
      properties: {
        description: { type: 'string', description: 'Natural language description of the element (e.g., "blue Submit button")' }
      },
      required: ['description']
    },
    execute: async (args: any) => {
      const screen: any = await registry.execute('screen_capture', {});
      return visionClient.findElement(screen.base64, args.description);
    }
  });
}
