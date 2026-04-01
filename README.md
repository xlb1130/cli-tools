# cts

[中文文档](README.zh.md)

`cts` turns heterogeneous capabilities into stable commands.

You can compile local CLIs, shell scripts, HTTP APIs, OpenAPI specs, GraphQL services, and MCP servers into one consistent command surface, then expose them through CLI, invoke, HTTP, and UI.

## Recommended Path

If you're new to `cts`, this order works best:

1. Import one local shell command and see it run immediately
2. Import one local CLI command
3. Try MCP / HTTP / OpenAPI / GraphQL
4. Move on to mounts, execution, plugins, and hooks

Useful entry points:

- [Usage Guide](docs/usage/README.md)
- [Quickstart](docs/usage/01-quickstart/README.md)
- [Local CLI](docs/usage/02-local-cli/README.md)
- [Shell](docs/usage/03-shell/README.md)
- [HTTP](docs/usage/04-http/README.md)
- [OpenAPI](docs/usage/05-openapi/README.md)
- [GraphQL](docs/usage/06-graphql/README.md)
- [MCP](docs/usage/07-mcp/README.md)
- [Mounts](docs/usage/08-mounts/README.md)
- [Execution](docs/usage/09-execution/README.md)
- [Plugins](docs/usage/10-plugins/README.md)
- [Hooks](docs/usage/11-hooks/README.md)

## Install

```bash
pip install cts
```

From a wheel file:

```bash
python3 -m pip install ./dist/cts-0.1.0-py3-none-any.whl
```

From source:

```bash
git clone https://github.com/xlb1130/cli-tools.git
cd cli-tools
pip install -e .
```

## Provider-Driven Import

`cts import` is now provider-driven:

```bash
cts import <provider-type> ...
cts import wizard
cts import wizard <provider-type>
```

Built-in provider types include:

- `shell`
- `cli`
- `http`
- `openapi`
- `graphql`
- `mcp`

Plugin-provided provider types can also expose their own import command and wizard automatically.

## Start With A One-Line Shell Import

This is the fastest starting point because it does not depend on external services or a config file you write by hand.

```bash
cts import shell hello --exec 'echo Hello cts!' --apply
cts hello
```

Then inspect the generated dynamic command:

```bash
cts hello --help
cts manage explain hello
```

This gives you a concrete model of:

- source: `hello`
- operation: `run`
- mount: `hello`
- command path: `hello`

## Import A Local CLI

The most common entry point is:

```bash
cts import cli <source-name> <command> [subcommand...] --apply
```

Example:

```bash
cts import cli git-status git status --apply
cts git-status --help
cts git-status
```

To import a full command tree:

```bash
cts import cli git git --all --apply --under git
```

Continue with [Local CLI](docs/usage/02-local-cli/README.md).

## Import An MCP Server

The shortest path is:

```bash
cts import mcp my-mcp \
  --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' \
  --apply
```

Then check what was discovered:

```bash
cts manage source show my-mcp --format json
cts manage source test my-mcp --discover --format json
cts my-mcp --help
```

If you only want to mount part of the discovered operations during import, add include/exclude filters:

```bash
cts import mcp my-mcp \
  --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' \
  --include 'search_*' \
  --exclude 'delete_*' \
  --apply
```

The same `--include` / `--exclude` pattern also works for bulk import providers such as `cli --all`, `openapi`, and `graphql`.

Continue with [MCP](docs/usage/07-mcp/README.md).

## Start the Web UI

Launch the built-in web interface to interact with your CTS instance:

```bash
cts manage ui
```

This starts the HTTP API together with the bundled frontend UI. By default it runs on `http://127.0.0.1:8787`.

Additional options:

```bash
# Open browser automatically
cts manage ui --open

# Use custom host/port
cts manage ui --host 0.0.0.0 --port 9000

# Use a custom UI directory
cts manage ui --ui-dir /path/to/ui/dist
```

If the UI assets are not found, build them first:

```bash
cd frontend/app
npm install
npm run build
```

For more control, you can also use the HTTP server command:

```bash
# Start HTTP API only
cts manage serve http

# Start HTTP API with UI
cts manage serve http --ui

# Start HTTP API with UI and open browser
cts manage serve http --ui --open
```

## Typical Scenarios

### Scenario 1: Travel Planning

Combine Gaode MCP, 12306 MCP, and Bing Search MCP into a comprehensive "travel planning assistant".

**Problem Solved:**
While maps, railways, and search can each answer part of the question, travel planning usually requires chaining them together:
- Gaode MCP for location search, route planning, and commute time estimation
- 12306 MCP for train schedules, ticket availability, and transfer options
- Bing Search MCP for attraction info, opening hours, and travel tips

**Recommended Tool Combination:**
- `map`: Gaode MCP → location search, route planning
- `rail`: 12306 MCP → train schedules, ticket availability, transfer options
- `search`: Bing Search MCP → attractions, weather, travel guides

**Use Cases:**
- Weekend short trips
- Intercity high-speed rail + subway connections
- Multi-attraction day trips
- Business travel route planning

Detailed documentation: [Advanced Practice: Travel Planning](docs/usage/12-travel-planning/README.md)

### Scenario 2: Automated Issue Analysis, Requirement Development, and Deployment

Chain multiple MCP tools into a sustainable engineering pipeline: automatic issue analysis when problems occur, automatic development context generation when requirements come in, and automatic deployment and verification after development.

**Problem Solved:**
Covers the most common aspects of R&D delivery:
- `aliyun-sls`: Log retrieval, error localization, time window analysis
- `mysql`: Business data verification, exception sampling, post-release data validation
- `redis`: Cache, queue, rate limiting, session troubleshooting
- `nacos`: Configuration center, service registry, environment difference checking
- `jvm-mcp-server`: Remote JVM / Arthas diagnostics
- `yunxiao`: Requirements, tasks, R&D collaboration, code workflow integration
- `jenkins-mcp`: Build, deploy, rollback, pipeline status checking
- `dingding-bot`: Task completion notifications, key node broadcasts, exception escalation alerts

**Recommended Four Automation Pipelines:**

1. **Automated Issue Analysis**
   - Check logs → Extract data → Check cache → Check config → JVM diagnosis → Update issue → Send notification

2. **Automated Requirement Development Assistance**
   - Read requirements → Supplement context → Output technical solution → Update subtasks → Send notification

3. **Automated Deployment and Release Verification**
   - Config check → Trigger deployment → Verify logs/data/cache → Update status → Send notification

4. **Task Completion or Key Node Automated Notification**
   - Determine notification conditions → Aggregate context → Generate notification → Send DingTalk

**Recommended Implementation Order:**
1. First connect `aliyun-sls + mysql + nacos`, complete "automated issue analysis"
2. Then connect `yunxiao`, complete "automated issue/requirement task generation"
3. Finally connect `jenkins + redis + jvm-mcp-server`, complete "automated deployment and release verification"

Detailed documentation: [Advanced Practice: Automated Issue Analysis, Requirement Development, and Deployment](docs/usage/13-advanced-automation/README.md)

## Core Model

```text
source -> operation -> mount -> surface
```

- `source`: where the capability comes from
- `operation`: one concrete action in that source
- `mount`: stable id and command path bound to the operation
- `surface`: how the mount is exposed

## Common Commands

```bash
# View source details
cts manage source show <source> --format json

# Test and discover operations
cts manage source test <source> --discover --format json

# List mounts
cts manage mount list --format json

# Remove a source
cts manage source remove <source_name> --force --format json

# Invoke a mount
cts manage invoke <mount-id> --input-json '{"key":"value"}' --format json

# Explain a mount
cts manage explain <mount-id> --input-json '{"key":"value"}'
```

## Development

```bash
git clone https://github.com/xlb1130/cli-tools.git
cd cli-tools
python3 -m pip install -e ".[dev]"
```

Recommended day-to-day workflow:

```bash
# Run the local source tree directly
PYTHONPATH=src python3 -m cts.main --help

# Try the shell quickstart against local code
PYTHONPATH=src python3 -m cts.main import shell hello --exec 'echo Hello cts!' --apply
PYTHONPATH=src python3 -m cts.main hello
```

Useful validation commands:

```bash
# Compile and lint config/runtime
PYTHONPATH=src python3 -m cts.main config lint --compile --format json

# Run tests
python3 -m pytest

# Run one focused test file
python3 -m pytest tests/test_cli_management.py -q
```

Frontend development:

```bash
cd frontend/app
npm install
npm run build
```

If you want the installed `cts` command to use your local changes immediately:

```bash
python3 -m pip install -e .
```

This matters when you add CLI commands such as `cts import shell`, because your terminal may still be using an older installed package.

## More

- [Usage Guide](docs/usage/README.md)
- [Architecture](docs/00-rfc-master-architecture.md)
- [Install And Usage](docs/15-install-and-usage.md)

## License

[MIT](LICENSE)
