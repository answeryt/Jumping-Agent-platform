<div align="center">
  <img src="8315c2b3b7fabe9b0e95a8c6c7b4f9db.jpg" alt="Jumping Agent: a super simple Agent building platform (Task split -> Community / Code / Data agent -> Aggregator)" width="90%">
  <h1>Jumping-Agent</h1>
  <p><strong>A super simple Agent building platform</strong></p>
  <p>
    <a href="README_EN.md">English</a> |
    <a href="README.md">中文</a>
  </p>
</div>

## Project Overview

Jumping Agent is a fun and approachable project that uses a "jumping game" style interaction to help beginners build their own Agents on mobile devices, especially tablets. It turns abstract Agent workflows into visible, touchable, step-by-step jumps, making the whole process easier to understand and use.

Instead of showing users a flat workflow full of complex lines and arrows, this project presents the workflow in a spatial and game-like way. By pressing the screen and controlling a character to jump forward, users can intuitively understand how an Agent workflow moves from one step to the next.

![Jumping-style Agent builder interface: press to jump and understand how the workflow moves forward](b27fe65904b078f84f58a00f6d6e7488.jpg)

## Architecture

- **`Frontend/`**: The jumping-style Agent building interface. It handles workflow display, node configuration, and the chat entry point.
- **`agent_builder/`**: Agent skeletons and templates, including workflow templates, Agent templates, project templates, and configuration generation logic.
- **`back_agent/`**: Reads skeleton code and uses the user's frontend input to complete, modify, and generate the Agent implementation.
- **`backend/`**: The orchestration service. `orchestrator.py` connects frontend requests, dynamically loads `agent_builder`, generates Agent workspaces, and calls `back_agent` through local HTTP requests.
- **`sandbox/` / `sandbox-main/`**: Provides sandbox tool capabilities for generated Agents, such as file operations, shell commands, and browser automation. This helps prevent Agents from operating directly on the host machine. Many thanks to the provider of this sandbox project: [agent-infra/sandbox](https://github.com/agent-infra/sandbox).

Default service URLs:

- Frontend: `http://localhost:6301`
- back_agent: `http://localhost:8000/chat`
- backend / Orchestrator: `http://localhost:8001`
- Sandbox: `http://localhost:8080`

## Quick Start

### Prerequisites

- Git
- Python 3.11+
- Node.js 18+
- npm
- Docker

### Clone

```bash
git clone https://github.com/answeryt/Fat-Cat-Agent-platform-1.0.git
cd Jumping-Agent-platform-1.0
```

### Install Frontend Dependencies

```bash
cd Frontend
npm install
cd ..
```

### Install Backend Dependencies

It is recommended to create a virtual environment first:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Install Python dependencies:

```bash
python -m pip install "fastapi" "uvicorn[standard]" "pydantic" "openai"
```

### Configure API Key

`back_agent/config/model_config.toml` reads the `OPENAI_API_KEY` environment variable by default. You can set the environment variable directly, or use the built-in project script to write it into `.env`.

Option 1: use an environment variable.

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
```

macOS / Linux:

```bash
export OPENAI_API_KEY="your_api_key_here"
```

Option 2: use the project script.

```bash
python backend/set_agent_api_key.py
```

The script will ask for your API key and update `back_agent/.env` as well as the `.env` files in generated workspaces.

### Start Sandbox

```bash
docker run --security-opt seccomp=unconfined --rm -it -p 8080:8080 ghcr.io/agent-infra/sandbox:latest
```

### Start Services

Open 3 terminals and run each command from the repository root.

Terminal A: start `back_agent`.

```bash
cd back_agent
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

Terminal B: start `backend` / Orchestrator.

```bash
cd backend
python -m uvicorn orchestrator:app --host 0.0.0.0 --port 8001
```

Terminal C: start the frontend.

```bash
cd Frontend
npm run server -- --host 0.0.0.0 --port 6301 --allowed-hosts all
```

Open the browser and visit:

```text
http://localhost:6301
```

## iPad / LAN Access

If you want to access the frontend from an iPad, make sure the iPad and your computer are on the same local network, then visit the computer's LAN IP address.

Check the IP address on Windows:

```powershell
ipconfig
```

Check the IP address on macOS / Linux:

```bash
ifconfig
```

Find the IPv4 address of your current network adapter, for example `192.168.x.x`, then open this address in the iPad browser:

```text
http://192.168.x.x:6301
```

## CLI Plan

The repository can currently be run with the manual source commands above. To make it easier for GitHub users to get started, a CLI could later wrap these steps, for example:

```bash
agent-jump setup
agent-jump config set OPENAI_API_KEY
agent-jump dev
```

Ideally:

- `agent-jump setup` installs frontend and backend dependencies.
- `agent-jump config set OPENAI_API_KEY` writes the model API key.
- `agent-jump dev` starts Sandbox, back_agent, backend, and Frontend together.

Before the CLI is officially implemented, please use the manual startup steps in `Quick Start`.

## Acknowledgements

This project was independently developed by me. The sandbox capability is based on [agent-infra/sandbox](https://github.com/agent-infra/sandbox), and I sincerely appreciate their work.

Due to limited personal time and experience, the current version still has some limitations. For example, sandbox operations may occasionally fail, the Agent workflow currently provides only 7 templates, and the jump-platform orchestration plus final build process are not yet fully stable. I will continue improving the project.

If you would like to help make this project better, issues and pull requests are welcome. You can also contact me directly at [answeryt@qq.com](mailto:answeryt@qq.com). Chinese users may contact me on WeChat: `answerYTAarun`.

I also hope more beginners can use it to explore their imagination and build their own Agents.
