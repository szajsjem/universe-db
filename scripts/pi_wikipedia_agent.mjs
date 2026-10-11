// JSON-lines bridge: Pi owns the agent loop; Python owns validated database tools.
import { createInterface } from 'node:readline';
import { Agent } from '@earendil-works/pi-agent-core';
import { createModels } from '@earendil-works/pi-ai';
import { openrouterProvider } from '@earendil-works/pi-ai/providers/openrouter';

const lines = createInterface({ input: process.stdin });
const iterator = lines[Symbol.asyncIterator]();
const receive = async () => {
  const next = await iterator.next();
  if (next.done) throw new Error('Python bridge disconnected');
  return JSON.parse(next.value);
};
const send = value => process.stdout.write(JSON.stringify(value) + '\n');
try {
  const config = await receive();
  const models = createModels();
  models.setProvider(openrouterProvider());
  await models.refresh({ providers: ['openrouter'], force: true });
  const model = models.getModel('openrouter', config.model);
  if (!model) throw new Error(`OpenRouter model unavailable: ${config.model}`);
  let rounds = 0;
  let committed = false;
  // Omitting the key means global search; source-specific searches still have
  // to use an actual archived key before Python will accept a final decision.
  const localSearch = config.tools.find(tool => tool.function.name === 'search_wikipedia');
  localSearch.function.parameters.required = ['query', 'limit'];
  localSearch.function.description += ' Omit source_entry_key for global search; never send the string "null".';
  const tools = config.tools.map(({ function: tool }) => ({
    name: tool.name, label: tool.name, description: tool.description,
    parameters: tool.parameters, executionMode: 'sequential',
    execute: async (_id, args) => {
      send({ type: 'tool', name: tool.name, arguments: args });
      const result = await receive();
      if (result.error) throw new Error(result.error);
      if (result.committed) committed = true;
      return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result, terminate: committed };
    },
  }));
  const agent = new Agent({
    initialState: { systemPrompt: config.system, model: { ...model, baseUrl: config.base_url }, tools, thinkingLevel: config.thinking ? 'low' : 'off' },
    streamFn: (model, context, options) => models.streamSimple(model, context, {
      ...options, maxTokens: config.max_tokens, maxRetries: config.retries,
      // The bridge executes one tool at a time; request the same from providers.
      onPayload: payload => ({ ...payload, parallel_tool_calls: false }),
    }),
    getApiKey: () => process.env[config.api_key_env],
    toolExecution: 'sequential',
    prepareRequest: () => {
      if (++rounds > config.max_steps) throw new Error('Pi exceeded configured review rounds');
      send({ type: 'progress', round: rounds });
    },
    finishTurn: () => committed ? { action: 'end' } : undefined,
  });
  const timer = setTimeout(() => agent.abort(), config.timeout * 1000);
  agent.subscribe(event => {
    if (event.type === 'tool_execution_end' && event.isError) {
      send({ type: 'diagnostic', error: JSON.stringify(event.result.content).slice(0, 500) });
    }
  });
  try {
    await agent.prompt(JSON.stringify(config.candidate));
    if (!committed) throw new Error(agent.state.errorMessage || 'Pi stopped without a validated decision');
    send({ type: 'done' });
  } finally { clearTimeout(timer); }
} catch (error) {
  send({ type: 'error', error: String(error.message || error) });
  process.exitCode = 1;
} finally { lines.close(); }
