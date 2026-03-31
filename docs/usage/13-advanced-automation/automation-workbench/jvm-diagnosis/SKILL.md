---
name: jvm-diagnosis
description: Use when the user needs Java runtime diagnosis through CTS, such as thread issues, memory pressure, GC symptoms, classloading problems, or connection-pool stalls. This skill focuses on the JVM MCP-backed `cts ops jvm ...` commands.
---

# JVM Diagnosis

Use this skill only when a Java runtime check is relevant.

## Primary Command Area

- `cts ops jvm ...`

## Workflow

1. Confirm target host, service, environment, and current symptom.
2. Start with the least invasive runtime inspection.
3. Gather thread, memory, GC, or classloading evidence as needed.
4. Tie runtime evidence back to logs and observed impact.

## Guardrails

- Avoid invasive actions unless the task explicitly needs them.
- Summarize the runtime signal in plain language.
