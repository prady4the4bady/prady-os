import { TaskPlan, Step, ScreenState } from '../types.js';
import { VyrexClient } from '../vyrex-client.js';

export class Planner {
  constructor(private vyrex: VyrexClient) {}

  async createPlan(goal: string, context?: string): Promise<TaskPlan> {
    const prompt = `
You are Kryos, an autonomous computer agent. Given a user goal, create a step-by-step plan.
Goal: ${goal}
Context: ${context || 'None'}
Available tools: screen_capture, mouse_click, keyboard_type, execute_shell, browse_web
Return ONLY valid JSON matching this schema:
{
  "goal": string,
  "steps": [
    { "id": "1", "description": string, "tool": string, "args": {}, "expectedOutcome": string, "isSensitive": boolean }
  ]
}
Mark isSensitive=true for payments, deletions, sending messages, or accessing personal data.
`;
    
    try {
      const response = await this.vyrex.chat([{ role: 'system', content: prompt }]);
      // In production we would validate with AJV here
      return JSON.parse(response) as TaskPlan;
    } catch (e) {
      console.warn("Vyrex parsing failed, using fallback mock plan.");
      return {
        goal,
        steps: [
          {
            id: '1',
            description: `Mock step for: ${goal}`,
            tool: 'execute_shell',
            args: { command: 'echo "mock step"' },
            expectedOutcome: 'Command completes',
            isSensitive: false
          }
        ]
      };
    }
  }

  async replan(goal: string, completedSteps: Step[], currentScreen: ScreenState): Promise<TaskPlan> {
    console.log(`Replanning for goal: ${goal}`);
    return this.createPlan(goal, `Completed steps: ${completedSteps.length}`);
  }
}
