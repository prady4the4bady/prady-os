import { ToolRegistry } from './registry.js';

/**
 * Adapter to wrap our local Phase 2 tools into the format expected by the upstream Kryos architecture.
 * Upstream kryos expects: { name, description, schema, run: async (args) => string }
 */
export function wrapToolsForKryosUpstream(registry: ToolRegistry): any[] {
  return registry.list().map(tool => {
    return {
      name: tool.name,
      description: tool.description,
      schema: tool.parameters,
      run: async (args: any) => {
        try {
          const result = await registry.execute(tool.name, args);
          return JSON.stringify(result);
        } catch (e: any) {
          return JSON.stringify({ error: e.message });
        }
      }
    };
  });
}
