#!/bin/bash
# YouTube Community Manager Agent — Quick Start
# Assumes setup is already done (./setup.sh). Loads .env and starts services.

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# shellcheck source=scripts/services.sh
source "${SCRIPT_DIR}/scripts/services.sh"

LANGGRAPH_PID=""
FRONTEND_PID=""

cleanup() {
    if [ -n "$LANGGRAPH_PID" ]; then
        kill "$LANGGRAPH_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

echo -e "${BLUE}"
echo "=================================================================="
echo "       YOUTUBE COMMUNITY MANAGER - QUICK START"
echo "=================================================================="
echo -e "${NC}"

# Load environment
if [ ! -f ".env" ]; then
    echo -e "${RED}.env not found. Run setup first:${NC}"
    echo "  cp .env.example .env"
    echo "  ./setup.sh"
    exit 1
fi

set -a
load_dotenv ".env"
set +a

if [ -z "$GROQ_API_KEY" ]; then
    echo -e "${RED}GROQ_API_KEY is not set in .env${NC}"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Running setup...${NC}"
    ./setup.sh
    exit $?
fi

if ! uv run python -c "from agent import graph" 2>/dev/null; then
    echo -e "${YELLOW}Syncing dependencies...${NC}"
    uv sync --quiet
fi

ensure_frontend_deps() {
    if [ ! -d "frontend/node_modules" ]; then
        echo -e "${YELLOW}Installing frontend dependencies...${NC}"
        (cd frontend && npm install)
    fi
}

run_ui() {
    stop_frontend
    ensure_frontend_deps
    echo -e "${BLUE}Starting Agent Web UI (Vite)...${NC}"
    echo -e "${YELLOW}Open: http://localhost:${FRONTEND_PORT}${NC}"
    echo -e "${YELLOW}Tip: run ./start.sh both to start LangGraph + UI together${NC}"
    echo ""
    trap - EXIT INT TERM
    (cd frontend && npm run dev -- --port "${FRONTEND_PORT}" --host 127.0.0.1)
}

run_server() {
    stop_langgraph
    echo -e "${BLUE}Starting LangGraph Server...${NC}"
    echo -e "${YELLOW}API:    http://127.0.0.1:${LANGGRAPH_PORT}${NC}"
    echo -e "${YELLOW}Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:${LANGGRAPH_PORT}${NC}"
    echo ""
    trap - EXIT INT TERM
    uv run langgraph dev --port "${LANGGRAPH_PORT}"
}

run_both() {
    stop_all_services

    echo -e "${BLUE}Starting LangGraph Server + Agent Web UI...${NC}"
    echo -e "${YELLOW}Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:${LANGGRAPH_PORT}${NC}"
    echo -e "${YELLOW}UI:     http://localhost:${FRONTEND_PORT}${NC}"
    echo ""

    uv run langgraph dev --port "${LANGGRAPH_PORT}" &
    LANGGRAPH_PID=$!

    echo "Waiting for LangGraph server..."
    wait_for_port "${LANGGRAPH_PORT}" 20

    ensure_frontend_deps
    trap cleanup EXIT INT TERM

    echo "Starting Agent Web UI..."
    (cd frontend && npm run dev -- --port "${FRONTEND_PORT}" --host 127.0.0.1)
}

run_legacy_ui() {
    stop_streamlit
    echo -e "${BLUE}Starting legacy Streamlit UI...${NC}"
    echo -e "${YELLOW}Open: http://localhost:${STREAMLIT_PORT}${NC}"
    echo ""
    trap - EXIT INT TERM
    uv run streamlit run streamlit_ui.py --server.port "${STREAMLIT_PORT}"
}

run_stop() {
    trap - EXIT INT TERM
    stop_all_services
}

run_restart() {
    local target="${1:-both}"
    run_stop
    sleep 1
    case "$target" in
        ui) run_ui ;;
        server) run_server ;;
        both) run_both ;;
        streamlit) run_legacy_ui ;;
        *)
            echo -e "${RED}Unknown restart target: $target${NC}"
            echo "Use: ./start.sh restart [ui|server|both|streamlit]"
            exit 1
            ;;
    esac
}

show_help() {
    echo "Usage: ./start.sh [command]"
    echo ""
    echo "Commands:"
    echo "  ui              Start Agent Web UI (default, requires LangGraph for runs)"
    echo "  server          Start LangGraph Server + Studio"
    echo "  both            Start LangGraph Server + Agent Web UI"
    echo "  streamlit       Start legacy Streamlit UI (in-process graph)"
    echo "  stop            Stop services on ports ${LANGGRAPH_PORT} and ${FRONTEND_PORT}"
    echo "  restart [target] Restart ui, server, both, or streamlit (default: both)"
    echo ""
    echo "Examples:"
    echo "  ./start.sh"
    echo "  ./start.sh both"
    echo "  ./start.sh server"
    echo "  ./start.sh stop"
    echo ""
    echo "First time? Run: ./setup.sh"
    echo "Workflow docs:  AgentWorkflow.md"
}

MODE="${1:-ui}"
ARG2="${2:-}"

case "$MODE" in
    ui)
        run_ui
        ;;
    server)
        run_server
        ;;
    both)
        run_both
        ;;
    streamlit)
        run_legacy_ui
        ;;
    stop)
        run_stop
        ;;
    restart)
        run_restart "${ARG2:-both}"
        ;;
    -h|--help|help)
        show_help
        ;;
    "")
        run_ui
        ;;
    *)
        echo -e "${RED}Unknown option: $MODE${NC}"
        show_help
        exit 1
        ;;
esac
