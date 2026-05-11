import { ToolRegistry } from './tools/registry.js';
import { registerScreenTools } from './tools/screen.js';
import { registerMouseTools } from './tools/mouse.js';
import { registerKeyboardTools } from './tools/keyboard.js';
import { registerSystemTools } from './tools/system.js';
import { registerFilesystemTools } from './tools/filesystem.js';
import { registerBrowserTools } from './tools/browser.js';
import { registerVoiceTools } from './tools/voice.js';
import { ReactLoop } from './core/react-loop.js';
import { SessionMemory } from './memory/session.js';
import { VyrexClient } from './vyrex-client.js';
import { TaskResult, TaskSession } from './types.js';

export interface KryosConfig {
  dbPath?: string;
  socketPath?: string;
}

export class PraxAgent {
  private loop: ReactLoop;
  private memory: SessionMemory;
  private registry: ToolRegistry;
  private vyrex: VyrexClient;

  constructor(config?: KryosConfig) {
    this.memory = new SessionMemory(config?.dbPath);
    this.vyrex = new VyrexClient(config?.socketPath);
    this.registry = new ToolRegistry();

    // Register all OS tools
    registerScreenTools(this.registry);
    registerMouseTools(this.registry);
    registerKeyboardTools(this.registry);
    registerSystemTools(this.registry);
    registerFilesystemTools(this.registry);
    registerBrowserTools(this.registry);
    registerVoiceTools(this.registry);

    this.loop = new ReactLoop(this.registry, this.vyrex, this.memory);
  }

  async executeTask(goal: string): Promise<TaskResult> {
    const sessionId = `session_${Date.now()}`;
    return this.loop.run(goal, sessionId);
  }

  async cancelCurrentTask(): Promise<void> {
    this.loop.abort();
  }

  on(event: string, handler: (...args: any[]) => void): this {
    this.loop.on(event, handler);
    return this;
  }

  getHistory(): TaskSession[] {
    return this.memory.listSessions();
  }
}

// CLI entrypoint for testing
if (process.argv[2] && process.argv[1].endsWith('index.js')) {
  const agent = new PraxAgent();
  const goal = process.argv.slice(2).join(' ');
  console.log(`Starting autonomous task: "${goal}"`);
  
  agent.on('thought', t => console.log(`[THOUGHT] ${t}`));
  agent.on('step', s => console.log(`[STEP] ${s.thought}`));
  
  agent.executeTask(goal).then(result => {
    console.log('\nFinal Result:');
    console.log(JSON.stringify(result, null, 2));
    process.exit(0);
  });
}
