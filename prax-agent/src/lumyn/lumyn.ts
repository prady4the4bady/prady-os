import { VyrexClient } from '../vyrex-client.js';
import { DetailedPlan } from './structured-plan.js';
import { Tool } from '../types.js';

export class LumynAgent {
  constructor(private vyrex: VyrexClient) {}

  async reason(problem: string, context: string): Promise<{ thinking: string, answer: string, confidence: number }> {
    const prompt = `
You are Lumyn, a reasoning agent. Think step by step using <thinking>...</thinking> tags before giving your final answer.
Be precise, logical, and consider edge cases.
Problem: ${problem}
Context: ${context}
`;
    
    const response = await this.vyrex.chat([{ role: 'system', content: prompt }]);
    
    const thinkingMatch = response.match(/<thinking>([\s\S]*?)<\/thinking>/);
    const thinking = thinkingMatch ? thinkingMatch[1].trim() : '';
    const answer = response.replace(/<thinking>[\s\S]*?<\/thinking>/, '').trim();

    return {
      thinking,
      answer,
      confidence: 0.95 // Mocked confidence
    };
  }

  async planWithReasoning(goal: string, tools: Tool[]): Promise<DetailedPlan> {
    const toolList = tools.map(t => t.name).join(', ');
    const res = await this.reason(
      `Create a highly detailed execution plan for the goal: "${goal}". You have access to these tools: ${toolList}`,
      "Ensure the plan breaks complex tasks down into subTasks with dependencies."
    );

    // Mock parsed output for the plan
    return {
      thoughtProcess: res.thinking,
      subTasks: [
        {
          name: "Initial reasoning subtask",
          description: res.answer.substring(0, 50),
          requiredTools: ["execute_shell"],
          dependencies: []
        }
      ]
    };
  }
}
