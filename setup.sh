#!/bin/bash
# YouTube Community Manager Agent Setup & Run Script
# This script sets up the project and runs the LangGraph server and other services

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# shellcheck source=scripts/services.sh
source "${SCRIPT_DIR}/scripts/services.sh"

# Banner (ASCII for terminal compatibility)
echo -e "${BLUE}"
echo "=================================================================="
echo "              YOUTUBE COMMUNITY MANAGER - SETUP"
echo "=================================================================="
echo -e "${NC}"

# ============================================================================
# 1. CHECK ENVIRONMENT
# ============================================================================
echo -e "${YELLOW}Step 1: Checking environment...${NC}"

if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo "Please create .env from .env.example:"
    echo "  cp .env.example .env"
    echo "Then add your API keys to .env"
    exit 1
fi

# Load environment variables
set -a
load_dotenv ".env"
set +a

if [ -z "$GROQ_API_KEY" ]; then
    echo -e "${RED}Error: GROQ_API_KEY not set in .env${NC}"
    exit 1
fi

echo -e "${GREEN}Environment check passed${NC}"
echo -e "   GROQ_API_KEY: $(echo "$GROQ_API_KEY" | cut -c1-10)..."
if [ -n "$LANGSMITH_API_KEY" ]; then
    echo -e "   LANGSMITH_API_KEY: Set"
fi

# ============================================================================
# 2. CHECK DEPENDENCIES
# ============================================================================
echo ""
echo -e "${YELLOW}Step 2: Checking dependencies...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 not found. Please install Python 3.11+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    echo -e "${RED}Python $PYTHON_VERSION found. Python 3.11+ is required.${NC}"
    exit 1
fi

echo -e "${GREEN}Python found: $PYTHON_VERSION${NC}"

if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}uv not found. Installing uv...${NC}"
    python3 -m pip install uv
fi

echo -e "${GREEN}uv available${NC}"

# ============================================================================
# 3. INSTALL DEPENDENCIES
# ============================================================================
echo ""
echo -e "${YELLOW}Step 3: Installing/Syncing dependencies...${NC}"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv .venv
fi

echo "Syncing dependencies (includes langgraph-cli)..."
uv sync --quiet

echo -e "${GREEN}Dependencies installed${NC}"

if command -v npm &> /dev/null; then
    echo "Installing frontend dependencies..."
    (cd frontend && npm install --silent)
    echo -e "${GREEN}Frontend dependencies installed${NC}"
else
    echo -e "${YELLOW}npm not found — install Node.js 20+ for the Agent Web UI${NC}"
fi

echo "Installing Playwright Chromium browser..."
uv run playwright install chromium

# ============================================================================
# 4. VERIFY CLI TOOLS
# ============================================================================
echo ""
echo -e "${YELLOW}Step 4: Verifying CLI tools...${NC}"

uv run langgraph --version > /dev/null
echo -e "${GREEN}LangGraph CLI available${NC}"

uv run streamlit --version > /dev/null
echo -e "${GREEN}Streamlit available${NC}"

# ============================================================================
# 5. VERIFY SETUP
# ============================================================================
echo ""
echo -e "${YELLOW}Step 5: Verifying setup...${NC}"

uv run python -c "
import sys
try:
    from langchain_groq import ChatGroq
    from agent import graph
    from agent.custom_tools.browser_tools import launch_browser
    from agent.custom_tools.youtube_tools import fetch_channel_data
    from agent.custom_tools.email_tools import send_email
    from agent.custom_tools.pdf_generator import generate_pdf_report
    print('All imports successful')
    print(f'Graph: {graph.name}')
    sys.exit(0)
except Exception as e:
    print(f'Import failed: {e}')
    sys.exit(1)
" || {
    echo -e "${RED}Verification failed${NC}"
    exit 1
}

# ============================================================================
# 6. DISPLAY OPTIONS
# ============================================================================
echo ""
echo -e "${BLUE}=================================================================="
echo "                     SETUP COMPLETE!"
echo -e "==================================================================${NC}"

echo ""
echo -e "${YELLOW}Choose an option:${NC}"
echo ""
echo -e "${GREEN}1${NC} - Run LangGraph Server (Recommended for debugging)"
echo -e "${GREEN}2${NC} - Run Agent Web UI (Vite + LangGraph SDK)"
echo -e "${GREEN}3${NC} - Run Both Services (LangGraph + Agent UI)"
echo -e "${GREEN}4${NC} - Run Legacy Streamlit UI"
echo -e "${GREEN}5${NC} - Exit"
echo ""
echo -e "${YELLOW}Tip: After setup, use ./start.sh both for quick starts${NC}"
echo -e "${YELLOW}Workflow docs: AgentWorkflow.md${NC}"
echo ""

# ============================================================================
# 7. HANDLE USER CHOICE
# ============================================================================
read -p "Enter your choice (1-5): " choice

case $choice in
    1)
        echo ""
        stop_langgraph
        echo -e "${BLUE}Starting LangGraph Server...${NC}"
        echo -e "${YELLOW}Server: http://127.0.0.1:${LANGGRAPH_PORT}${NC}"
        echo -e "${YELLOW}Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:${LANGGRAPH_PORT}${NC}"
        echo ""
        uv run langgraph dev --port "${LANGGRAPH_PORT}"
        ;;
    2)
        echo ""
        stop_frontend
        if command -v npm &> /dev/null; then
            (cd frontend && npm install --silent)
        fi
        echo -e "${BLUE}Starting Agent Web UI...${NC}"
        echo -e "${YELLOW}UI: http://localhost:${FRONTEND_PORT}${NC}"
        echo -e "${YELLOW}Start LangGraph separately: ./start.sh server${NC}"
        echo ""
        (cd frontend && npm run dev -- --port "${FRONTEND_PORT}" --host 127.0.0.1)
        ;;
    3)
        echo ""
        stop_all_services
        echo -e "${BLUE}Starting LangGraph Server and Agent Web UI...${NC}"
        echo ""
        echo -e "${YELLOW}LangGraph Server: http://127.0.0.1:${LANGGRAPH_PORT}${NC}"
        echo -e "${YELLOW}Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:${LANGGRAPH_PORT}${NC}"
        echo -e "${YELLOW}Agent UI: http://localhost:${FRONTEND_PORT}${NC}"
        echo ""
        echo "Starting LangGraph Server in background..."
        uv run langgraph dev --port "${LANGGRAPH_PORT}" &
        LANGGRAPH_PID=$!
        trap "kill $LANGGRAPH_PID 2>/dev/null; stop_all_services" EXIT INT TERM

        echo "Waiting for LangGraph server..."
        wait_for_port "${LANGGRAPH_PORT}" 20

        if command -v npm &> /dev/null; then
            (cd frontend && npm install --silent)
        fi
        echo "Starting Agent Web UI..."
        (cd frontend && npm run dev -- --port "${FRONTEND_PORT}" --host 127.0.0.1)
        ;;
    4)
        echo ""
        stop_streamlit
        echo -e "${BLUE}Starting legacy Streamlit UI...${NC}"
        echo -e "${YELLOW}UI: http://localhost:${STREAMLIT_PORT}${NC}"
        echo ""
        uv run streamlit run streamlit_ui.py --server.port "${STREAMLIT_PORT}"
        ;;
    5)
        echo -e "${YELLOW}Exiting...${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid choice. Exiting.${NC}"
        exit 1
        ;;
esac
