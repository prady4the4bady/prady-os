import { LumynAgent } from './lumyn-agent.js';

/**
 * Adapter connecting our local LumynAgent wrapper to the upstream Lumyn-Agent repo logic.
 * The upstream Lumyn-Agent typically expects raw LLM generation strings that it parses.
 */
export class LumynUpstreamAdapter {
  constructor(private localLumyn: LumynAgent) {}

  async evaluateUpstreamPrompt(prompt: string, context: string): Promise<string> {
    const response = await this.localLumyn.reason(prompt, context);
    // Format the response back into what upstream lumyn-agent parsers might expect
    return `<thinking>\n${response.thinking}\n</thinking>\n${response.answer}`;
  }
}
