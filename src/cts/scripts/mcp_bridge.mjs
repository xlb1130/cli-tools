import { readFile } from 'node:fs/promises'
import process from 'node:process'

import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'

function parseArgs(argv) {
  const command = argv[2]
  const options = {}
  let index = 3
  while (index < argv.length) {
    const token = argv[index]
    if (!token.startsWith('--')) {
      index += 1
      continue
    }
    const key = token.slice(2)
    const value = argv[index + 1]
    options[key] = value
    index += 2
  }
  return { command, options }
}

async function main() {
  const { command, options } = parseArgs(process.argv)
  if (!command) {
    fail('missing command')
  }

  const context = await buildContext(options)
  const client = new Client({ name: 'cts-mcp-bridge', version: '0.1.0' }, { capabilities: {} })

  try {
    await client.connect(context.transport)

    if (command === 'list-primitives') {
      const payload = await listPrimitives(client)
      ok({
        server: context.serverName,
        transport_type: context.transportType,
        capabilities: client.getServerCapabilities(),
        primitives: payload,
      })
    } else if (command === 'call-tool') {
      const tool = required(options.tool, '--tool is required')
      const args = parseJSON(options.args || '{}', '--args must be valid JSON')
      const result = await client.callTool({ name: tool, arguments: args })
      ok({
        server: context.serverName,
        transport_type: context.transportType,
        primitive_type: 'tool',
        target: tool,
        result,
      })
    } else if (command === 'read-resource') {
      const uri = required(options.uri, '--uri is required')
      const result = await client.readResource({ uri })
      ok({
        server: context.serverName,
        transport_type: context.transportType,
        primitive_type: 'resource',
        target: uri,
        result,
      })
    } else if (command === 'get-prompt') {
      const prompt = required(options.prompt, '--prompt is required')
      const args = parseJSON(options.args || '{}', '--args must be valid JSON')
      const result = await client.getPrompt({ name: prompt, arguments: args })
      ok({
        server: context.serverName,
        transport_type: context.transportType,
        primitive_type: 'prompt',
        target: prompt,
        result,
      })
    } else {
      fail(`unsupported command: ${command}`)
    }
  } catch (error) {
    fail(error?.message || String(error), error)
  } finally {
    try {
      await client.close()
    } catch {}
    try {
      await context.transport.close()
    } catch {}
  }
}

async function buildContext(options) {
  if (options.url) {
    return {
      serverName: options.server || 'remote',
      transportType: options.transport || 'streamable_http',
      transport: buildRemoteTransport(options.transport || 'streamable_http', { url: options.url }),
    }
  }

  const configPath = required(options.config, '--config is required when --url is not used')
  const serverName = required(options.server, '--server is required when --url is not used')
  const config = JSON.parse(await readFile(configPath, 'utf-8'))
  const serverConfig = config?.mcpServers?.[serverName]
  if (!serverConfig) {
    fail(`server '${serverName}' not found in config`)
  }

  return {
    serverName,
    transportType: normalizeTransportType(serverConfig),
    transport: buildTransport(serverConfig),
  }
}

function buildTransport(serverConfig) {
  const transportType = normalizeTransportType(serverConfig)
  if (transportType === 'streamable_http') {
    return buildRemoteTransport('streamable_http', serverConfig)
  }
  if (transportType === 'sse') {
    return buildRemoteTransport('sse', serverConfig)
  }
  if (!serverConfig.command) {
    fail('stdio MCP server config requires command')
  }
  const env = serverConfig.env ? { ...serverConfig.env, PATH: process.env.PATH } : undefined
  return new StdioClientTransport({
    command: serverConfig.command,
    args: serverConfig.args || [],
    env,
  })
}

function buildRemoteTransport(type, serverConfig) {
  const url = required(serverConfig.url, 'remote MCP config requires url')
  if (type === 'sse') {
    return new SSEClientTransport(new URL(url))
  }
  return new StreamableHTTPClientTransport(new URL(url))
}

function normalizeTransportType(serverConfig) {
  if (serverConfig.type) {
    return String(serverConfig.type).toLowerCase()
  }
  if (serverConfig.url && String(serverConfig.url).includes('/sse')) {
    return 'sse'
  }
  if (serverConfig.url) {
    return 'streamable_http'
  }
  return 'stdio'
}

async function listPrimitives(client) {
  const capabilities = client.getServerCapabilities()
  const primitives = []
  const tasks = []

  if (capabilities.tools) {
    tasks.push(
      client.listTools().then(({ tools }) => {
        for (const tool of tools) {
          primitives.push({
            primitive_type: 'tool',
            name: tool.name,
            description: tool.description || null,
            input_schema: tool.inputSchema || { type: 'object', properties: {} },
            raw: tool,
          })
        }
      }),
    )
  }

  if (capabilities.prompts) {
    tasks.push(
      client.listPrompts().then(({ prompts }) => {
        for (const prompt of prompts) {
          primitives.push({
            primitive_type: 'prompt',
            name: prompt.name,
            description: prompt.description || null,
            input_schema: prompt.arguments
              ? {
                  type: 'object',
                  properties: Object.fromEntries(
                    prompt.arguments.map((argument) => [
                      argument.name,
                      {
                        type: 'string',
                        description: argument.description || null,
                      },
                    ]),
                  ),
                  required: prompt.arguments.filter((arg) => arg.required).map((arg) => arg.name),
                }
              : { type: 'object', properties: {} },
            raw: prompt,
          })
        }
      }),
    )
  }

  if (capabilities.resources) {
    tasks.push(
      client.listResources().then(({ resources }) => {
        for (const resource of resources) {
          primitives.push({
            primitive_type: 'resource',
            name: resource.name || resource.uri,
            description: resource.description || null,
            target: resource.uri,
            input_schema: { type: 'object', properties: {} },
            raw: resource,
          })
        }
      }),
    )

    tasks.push(
      client.listResourceTemplates().then(({ resourceTemplates }) => {
        for (const template of resourceTemplates) {
          primitives.push({
            primitive_type: 'resource-template',
            name: template.name || template.uriTemplate,
            description: template.description || null,
            target: template.uriTemplate,
            input_schema: { type: 'object', properties: {} },
            raw: template,
          })
        }
      }),
    )
  }

  await Promise.all(tasks)
  return primitives
}

function parseJSON(value, message) {
  try {
    return JSON.parse(value)
  } catch (error) {
    fail(message, error)
  }
}

function required(value, message) {
  if (!value) {
    fail(message)
  }
  return value
}

function ok(data) {
  process.stdout.write(JSON.stringify({ ok: true, ...data }, null, 2) + '\n')
}

function fail(message, error) {
  process.stderr.write(
    JSON.stringify(
      {
        ok: false,
        error: {
          message,
          stack: error?.stack || null,
        },
      },
      null,
      2,
    ) + '\n',
  )
  process.exit(1)
}

await main()
