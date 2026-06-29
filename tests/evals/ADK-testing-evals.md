# ADK Testing and Evaluations Guide

This guide covers testing and evaluation procedures for the Paper Trading Agent using Google ADK framework.

**Note**: This documentation and evaluation tests have been moved from `examples/google-adk-agent/evals/` to `tests/evals/` for better organization alongside the main test suite.

## Prerequisites

### 1. Environment Setup
```bash
# Set required environment variables
export GOOGLE_API_KEY="your-google-api-key"
export GOOGLE_MODEL="gemini-2.0-flash"  # Optional, defaults to gemini-2.0-flash

# For Robinhood authentication (optional - enables environment-based login)
export ROBINHOOD_USERNAME="your_email@example.com"
export ROBINHOOD_PASSWORD="your_robinhood_password"
```

Or create a `.env` file in the project root:
```
GOOGLE_API_KEY=your-google-api-key
ROBINHOOD_USERNAME=your_email@example.com
ROBINHOOD_PASSWORD=your_robinhood_password
```

### 2. Install Dependencies
```bash
# From the google-adk-agent directory
pip install -r requirements.txt

# Verify ADK installation
adk --help
```

## Running ADK Evaluations

> **⚠️ Important**: Always run ADK evaluations from the **project root directory** (`/Users/wes/Development/open-paper-trading-mcp/`). The ADK expects the agent module path relative to the current working directory.

### ✅ Correct Way (From Project Root)
```bash
# Navigate to project root first
cd /Users/wes/Development/open-paper-trading-mcp

# Basic evaluation command (with recommended config)
adk eval examples/google_adk_agent tests/evals/list_available_tools_test.json --config_file_path tests/evals/test_config.json

# With custom configuration
adk eval examples/google_adk_agent tests/evals/list_available_tools_test.json --config_file_path tests/evals/test_config.json

# With detailed results output
adk eval examples/google_adk_agent tests/evals/list_available_tools_test.json --config_file_path tests/evals/test_config.json --print_detailed_results

# With specific run ID for tracking
adk eval examples/google_adk_agent tests/evals/list_available_tools_test.json --config_file_path tests/evals/test_config.json --run_id paper_trader_test_$(date +%s)

# With custom model
GOOGLE_MODEL="gemini-2.0-flash-exp" adk eval examples/google_adk_agent tests/evals/list_available_tools_test.json --config_file_path tests/evals/test_config.json
```

### ❌ Wrong Way (From Agent Directory)
```bash
# Don't do this - will cause path errors
cd examples/google_adk_agent
adk eval agent.py ../../tests/evals/list_available_tools_test.json  # ❌ Incorrect syntax
```

### 📋 Prerequisites Checklist
Before running evaluations, ensure:

1. **✅ Google ADK Installed**
   ```bash
   pip install google-agent-developer-kit
   adk --help  # Verify installation
   ```

2. **✅ Environment Variables Set**
   ```bash
   export GOOGLE_API_KEY="your-google-api-key"
   export ROBINHOOD_USERNAME="your_email@example.com"
   export ROBINHOOD_PASSWORD="your_robinhood_password"
   ```

3. **✅ Docker Services Running**
   ```bash
   # REQUIRED: Start Docker containers (MCP server runs inside Docker)
   docker-compose up -d
   
   # Verify both containers are healthy
   docker-compose ps
   
   # DO NOT start local servers - ADK evaluations must run against Docker endpoints
   # The MCP server runs on port 2081 inside the Docker container
   ```

4. **✅ Correct Working Directory**
   ```bash
   pwd  # Should show: /Users/wes/Development/open-paper-trading-mcp
   ```

5. **✅ Agent Module Available**
   ```bash
   ls examples/google_adk_agent/  # Should show: agent.py, __init__.py, etc.
   ```

### 🎯 Expected Results
A successful evaluation will show:
```
Using evaluation criteria: {'tool_trajectory_avg_score': 0.5, 'response_match_score': 0.5}
Running Eval: list_available_tools_test_set:list_available_tools_test
Result: ✅ Passed

*********************************************************************
Eval Run Summary
list_available_tools_test_set:
  Tests passed: 1
  Tests failed: 0
```

**Last Successful Run**: 2025-08-06T15:00:00Z (Docker-based evaluation - Phase 2 Complete)

## Available Evaluation Tests

### 1. List Available Tools Test
**File**: `tests/evals/1_acc_list_tools_test.json` (renamed to follow numbered prefix convention)  
**Purpose**: Validates that the agent can successfully list all available MCP tools  
**Expected Output**: Alphabetically sorted bullet list of 43 MCP tools

```bash
adk eval examples/google_adk_agent tests/evals/1_acc_list_tools_test.json --config_file_path tests/evals/test_config.json
```

### ADK Evaluation Naming Convention ✅ **ALL GROUPS COMPLETED**

ADK evaluation files use a standardized numbered prefix system aligned with user journey marks:

```bash
# Phase 2 Status: ALL EVALUATION GROUPS COMPLETED ✅
1_acc_*  # Core System & Account Tools (9 tools) - ✅ 100% agent behavior validated
2_mkt_*  # Market Data Tools (8 tools) - ✅ 100% agent behavior validated
3_stk_*  # Stock Trading Tools (8 tools) - ✅ 100% agent behavior validated  
4_opt_*  # Single-Step Options Tools (1 tool) - ✅ 100% agent behavior validated
5_ord_*  # Order Management Tools (4 tools) - ✅ 100% agent behavior validated
8_opt_*  # Complex Options Workflows (9 tools) - ✅ 100% agent behavior validated
9_can_*  # Order Cancellation Tools (4 tools) - ✅ 100% agent behavior validated

# Total: 42/42 evaluations with validated agent behavior
# All agents correctly use proper multi-step workflows with live market data

# Optimized Configuration (focuses on functionality over format):
# tests/evals/test_config.json: tool_trajectory_avg_score: 0.9, response_match_score: 0.2
```

### 2. Creating Custom Evaluation Tests

#### Test File Structure
```json
{
  "eval_set_id": "your_test_set_id",
  "name": "Your Test Name",
  "description": "Description of what this test validates",
  "eval_cases": [
    {
      "eval_id": "your_test_case_id",
      "conversation": [
        {
          "invocation_id": "unique-invocation-id",
          "user_content": {
            "parts": [
              {
                "text": "Your test prompt here"
              }
            ],
            "role": "user"
          },
          "final_response": {
            "parts": [
              {
                "text": "Expected response from agent"
              }
            ],
            "role": "model"
          },
          "intermediate_data": {
            "tool_uses": [
              {
                "id": "adk-tool-use-id",
                "args": {"param": "value"},
                "name": "tool_name"
              }
            ],
            "intermediate_responses": []
          }
        }
      ],
      "session_input": {
        "app_name": "paper_trading_agent",
        "user_id": "test_user",
        "state": {}
      }
    }
  ]
}
```

#### Example Test Cases to Create

1. **Portfolio Analysis Test**
```bash
# Test prompt: "Show me my current portfolio holdings"
# Expected tools: portfolio, positions, account_details
```

2. **Paper Trading Test**
```bash
# Test prompt: "Place a limit buy order for 10 shares of AAPL at $150"
# Expected tools: buy_stock_limit, stock_price
```

3. **Options Trading Test**
```bash
# Test prompt: "Show me the options chain for AAPL"
# Expected tools: options_chains, find_options
```

4. **Market Data Test**
```bash
# Test prompt: "What's the current price and rating for Tesla?"
# Expected tools: stock_price, stock_ratings, stock_info
```

## Evaluation Configuration

### Test Configuration File
**File**: `tests/evals/test_config.json` ✅ **Optimized for Functionality Focus**

```json
{
  "criteria": {
    "tool_trajectory_avg_score": 0.9,
    "response_match_score": 0.2
  }
}
```

**Configuration Rationale**: 
- **High tool_trajectory_avg_score (0.9)**: Ensures agents use correct tools in proper sequences
- **Low response_match_score (0.2)**: Focuses on functionality over exact text formatting
- **Result**: Validates core agent behavior while allowing natural response variations

### Scoring Criteria
- **tool_trajectory_avg_score**: Measures if the agent uses the correct tools in the right sequence
- **response_match_score**: Measures if the agent's response matches the expected output

### Local-model configs (Stockade)

Stockade runs the same goldens against the self-hosted local model (`tinman` /
`qwen2.5-coder-7b-instruct`). Two local configs exist alongside the Gemini gate
(`test_config.json`, which is **unchanged** and stays at `response_match_score: 0.2`):

**1. `tests/evals/test_config.local.json` — trajectory-only (no judge key needed)**

```json
{
  "criteria": {
    "tool_trajectory_avg_score": 0.9,
    "response_match_score": 0.0
  }
}
```

`response_match_score` (ROUGE) is set to `0.0` because ROUGE is **noise** against our
masked-asterisk goldens — scores cluster at 0.04–0.06 regardless of answer quality, so
it carries no signal. This config grades tool trajectory only and needs no API keys.

**2. `tests/evals/test_config.local_judge.json` — trajectory + LLM-judge response quality**

```json
{
  "criteria": {
    "tool_trajectory_avg_score": 0.9,
    "final_response_match_v2": {
      "threshold": 0.5,
      "judge_model_options": {
        "judge_model": "gemini-2.5-flash",
        "num_samples": 5
      }
    }
  }
}
```

`final_response_match_v2` is ADK's built-in **LLM-as-a-judge** metric for final-response
quality (ADK ≥ 2.x). Instead of n-gram overlap, a judge model reads the user prompt, the
agent's final response, and the (masked) golden reference and votes valid/invalid; the
score is the fraction of valid samples across `num_samples` repeats. This gives the
local model a *real* correctness/adequacy signal that ROUGE could not.

**Configuring the judge model.** The judge is set by `judge_model_options.judge_model`
(default `gemini-2.5-flash`). It is resolved through ADK's `LLMRegistry`, so any
Gemini model id works out of the box. To run the judge you **must** export a Google API
key — no secret is stored in the repo:

```bash
export GOOGLE_API_KEY="your-google-api-key"
adk eval examples/google_adk_agent tests/evals/1_acc_*_test.json \
  --config_file_path tests/evals/test_config.local_judge.json
```

`num_samples: 5` is ADK's recommended default for judge stability. Note the judge model
is independent of the model under test — here the agent under test is the local
`tinman` model (`LLM_PROVIDER=local`), while Gemini acts only as the grader. Using the
local model itself as the judge would require registering a `LiteLlm`-backed judge in
ADK's `LLMRegistry` and is out of scope for this config.

## Running local-LLM evals (operational runbook)

This section is the step-by-step procedure for pointing the ADK evals at the
self-hosted local model on `tinman`. It **complements** the
[Local-model configs](#local-model-configs-stockade) section above — see there for the
rubric rationale and which `--config_file_path` to pass (`test_config.local.json` for
trajectory-only, `test_config.local_judge.json` for the LLM-judge). This section covers
only the operational setup that has actually bitten us and is documented nowhere else.

### 1. Load the model with a large enough context window (the #1 trap)

The ADK agent's **initial** prompt — system instruction plus the schemas for ~40 MCP
tools — is roughly **8.2k tokens before any conversation turn happens**. If LM Studio on
`tinman` serves the model with a small context window (e.g. the 8192 default), every
single request fails immediately with an HTTP 400 like:

```
n_keep: 8218 >= n_ctx: 8192 ... load the model with a larger context length
```

The eval run then produces **empty results with no metrics** — it looks like a total
capability failure, but it is pure context overflow before the model ever reasons about
the task.

**Require `n_ctx` ≥ 16k (32k per the tinman spec).** Verify the *loaded* context length
before running — LM Studio's native `/api/v0/models` endpoint reports it, whereas the
OpenAI-compatible `/v1/models` does not:

```bash
curl -s http://tinman.tailc095b7.ts.net:1234/api/v0/models | python3 -c "import sys,json;[print(m['id'],m.get('state'),'loaded_ctx=',m.get('loaded_context_length')) for m in json.load(sys.stdin)['data']]"
```

The model you intend to test should show `state=loaded` and `loaded_ctx` ≥ 16384.

### 2. `.env` for a local run

The locally-run `adk eval` agent reads `.env` from the project root. `.env` is
**gitignored**, and it is **not** read by the Docker container — only by the agent
process you launch from the shell. Set:

```bash
LLM_PROVIDER=local
LLM_BASE_URL=http://tinman.tailc095b7.ts.net:1234/v1
LLM_API_KEY=lm-studio
LLM_MODEL=qwen2.5-coder-14b-instruct   # must match the served/loaded model id
MCP_HTTP_URL=http://localhost:2081/mcp
QUOTE_ADAPTER_TYPE=test
```

(If you also run the LLM-judge config, additionally `export GOOGLE_API_KEY=...` per the
config section above — the judge is a separate Gemini call.)

### 3. Toolchain install + the `uv run` gotcha

`google-adk[eval]` and `litellm` are **eval-only** dependencies; they are deliberately
not in `pyproject.toml` or the lockfile. Install them into the venv:

```bash
uv pip install "google-adk[eval]" litellm "mcp>=1.24,<2"
```

**CRITICAL: do not use `uv run` after this install.** `uv run` re-syncs the venv to the
lock and will silently *uninstall* `google-adk`, so the next eval invocation breaks.
Invoke the eval through the venv binary directly instead:

```bash
PYTHONPATH="$PWD" .venv/bin/adk eval examples/google_adk_agent \
  tests/evals/1_acc_*_test.json \
  --config_file_path tests/evals/test_config.local.json
```

When you are done evaluating, restore the venv to the locked state:

```bash
uv sync --extra dev
```

### 4. `PYTHONPATH=$PWD` is required

The agent module imports `app.*`, so the project root must be on `PYTHONPATH`. Always
prefix the eval command with `PYTHONPATH="$PWD"` (shown above). Without it the agent
fails to import at startup.

### 5. Hub must be up; rebuild the container after docstring changes

The MCP tools are served by the **Docker container**, not your local working tree.

```bash
docker-compose up -d
```

A bare `GET http://localhost:2081/mcp` returning **HTTP 406** means the MCP server is
alive (it rejects the non-MCP request). If you edit tool docstrings in
`app/mcp_tools.py`, the model will **not** see the change until you rebuild the
container — the local file edit alone has no effect on the served schemas:

```bash
docker-compose up -d --build
```

### 6. Run-to-run variance caveat

The local model (especially the 14b) is **non-deterministic**: individual `1_acc_*`
cases have flipped trajectory `1.0 ↔ 0.0` between identical back-to-back runs. Treat a
single pass as a **noisy signal** — prefer multiple runs and/or a low temperature.
Tracked in [`phix/stockade#25`](https://github.com/phix/stockade/issues/25).

Also budget time: a full `1_acc_*` run is **~1.5 hours** on the 14b at 32k context.

## Troubleshooting

### Common Issues

#### 1. MCP Server Connection Issues
```bash
# ❌ DO NOT start local servers - ADK must use Docker endpoints
# uv run python app/main.py  # DON'T DO THIS

# ✅ Check Docker container status
docker-compose ps

# ✅ Check MCP server logs inside Docker
docker logs open-paper-trading-mcp-app-1

# ✅ Test MCP server endpoint (should be accessible on port 2081)
curl -X POST http://localhost:2081/mcp/v1/initialize \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}}}'
```

#### 2. Authentication Errors
```bash
# Verify environment variables are set
echo "GOOGLE_API_KEY: ${GOOGLE_API_KEY:0:10}..."
echo "ROBINHOOD_USERNAME: $ROBINHOOD_USERNAME"

# Test Google API key
python3 -c "
import os
from google import genai
genai.configure(api_key=os.environ['GOOGLE_API_KEY'])
print('Google API key is valid')
"
```

#### 3. ADK Command Not Found
```bash
# Reinstall Google ADK
pip install --upgrade google-adk

# Verify installation
python3 -c "import google.adk; print('ADK installed successfully')"
```

#### 4. Tool Connection Issues
```bash
# Check if MCP server is accessible
python3 -c "
from examples.google_adk_agent.agent import create_agent
agent = create_agent()
print('Agent created successfully')
"
```

#### 5. Docker Container Issues
```bash
# Check container status
docker-compose ps

# Check container logs
docker logs open-paper-trading-mcp-app-1

# Restart containers if needed
docker-compose down && docker-compose up -d
```

### Local Testing Script
```bash
#!/bin/bash
# test-all-evals.sh

set -e

echo "Running all ADK evaluations..."

# Ensure we're in the right directory
cd /Users/wes/Development/open-paper-trading-mcp

# REQUIRED: Ensure Docker containers are running (not local servers)
docker-compose up -d

# Wait for services to be ready and verify health
sleep 15
docker-compose ps  # Both containers should show "healthy" status

# List available tools test
echo "Testing tool listing..."
adk eval examples/google_adk_agent tests/evals/1_acc_list_tools_test.json --config_file_path tests/evals/test_config.json

# Add more tests as they are created
# echo "Testing portfolio analysis..."
# adk eval examples/google_adk_agent tests/evals/portfolio_analysis_test.json --config_file_path tests/evals/test_config.json

echo "All evaluations completed successfully!"
```

## Performance Monitoring

### Evaluation Metrics to Track
- **Tool Selection Accuracy**: How often the agent chooses the correct tools
- **Response Quality**: How well the agent's responses match expected outputs
- **Execution Time**: How long evaluations take to complete
- **Error Rate**: Frequency of evaluation failures

### Monitoring Script
```python
#!/usr/bin/env python3
"""Monitor ADK evaluation performance over time."""

import json
import time
import subprocess
from datetime import datetime

def run_evaluation(test_file):
    """Run a single evaluation and return results."""
    start_time = time.time()
    try:
        result = subprocess.run(
            ["adk", "eval", "examples/google_adk_agent", test_file, "--config_file_path", "tests/evals/test_config.json"],
            capture_output=True,
            text=True,
            check=True
        )
        duration = time.time() - start_time
        return {
            "success": True,
            "duration": duration,
            "output": result.stdout
        }
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        return {
            "success": False,
            "duration": duration,
            "error": e.stderr
        }

if __name__ == "__main__":
    tests = ["tests/evals/1_acc_list_tools_test.json"]
    
    for test in tests:
        print(f"Running {test}...")
        result = run_evaluation(test)
        
        timestamp = datetime.now().isoformat()
        print(f"[{timestamp}] {test}: {'PASS' if result['success'] else 'FAIL'} ({result['duration']:.2f}s)")
        
        if not result['success']:
            print(f"Error: {result['error']}")
```

## Best Practices ✅ **PROVEN EFFECTIVE**

### 1. Test Design
- ✅ **Complete Coverage**: All 42 evaluations cover major tool categories across 7 functional sets
- ✅ **Multi-Step Workflows**: Complex options evaluations validate proper agent workflow chains
- ✅ **Live Data Integration**: All evaluations use real Robinhood market data
- ✅ **Tool Parameter Validation**: Account-specific tools properly validated with account_id parameters

### 2. Evaluation Maintenance ✅ **SYSTEMATIC APPROACH ESTABLISHED**
- ✅ **Regular Validation**: Phase 2 systematic evaluation completed with 100% agent behavior validation
- ✅ **Configuration Optimization**: Focused scoring on functionality (tool_trajectory: 0.9) over format (response_match: 0.2)
- ✅ **Performance Monitoring**: All agents demonstrate proper multi-step workflow execution
- ✅ **Comprehensive Documentation**: Complete process documented in EVAL_PROCESS.md

### 3. Debugging ✅ **PROVEN PATTERNS**
- ✅ **Agent Behavior Focus**: Prioritize correct tool usage over exact response text
- ✅ **Multi-Step Validation**: Verify agents properly chain discovery workflows (e.g., option_expirations → find_options)
- ✅ **Live API Integration**: All evaluations validated with real market data connections
- ✅ **Docker-Based Testing**: Reliable containerized environment for consistent evaluation results

## Additional Resources

- [Google ADK Documentation](https://developers.google.com/agent-development-kit)
- [MCP Protocol Documentation](https://modelcontextprotocol.io/)
- [Open Paper Trading MCP Documentation](../../README.md)
- [Paper Trading Agent Documentation](../../examples/google_adk_agent/README.md)