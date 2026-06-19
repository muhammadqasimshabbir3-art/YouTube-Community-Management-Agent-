#!/bin/bash
# Shared helpers for starting/stopping YouTube Community Manager services.

LANGGRAPH_PORT="${LANGGRAPH_PORT:-2024}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"

load_dotenv() {
    local env_file="${1:-.env}"
    if [ ! -f "$env_file" ]; then
        return 1
    fi

    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|\#*) continue ;;
        esac

        local key="${line%%=*}"
        local value="${line#*=}"

        key="$(echo "$key" | xargs)"
        if [ -z "$key" ]; then
            continue
        fi

        if [[ "$value" =~ ^\"(.*)\"$ ]]; then
            value="${BASH_REMATCH[1]}"
        elif [[ "$value" =~ ^\'(.*)\'$ ]]; then
            value="${BASH_REMATCH[1]}"
        fi

        export "${key}=${value}"
    done < "$env_file"
}

stop_port() {
    local port="$1"
    local pids=""

    if command -v lsof &>/dev/null; then
        pids="$(lsof -ti:"${port}" 2>/dev/null || true)"
    elif command -v fuser &>/dev/null; then
        fuser -k "${port}/tcp" 2>/dev/null || true
        sleep 1
        return 0
    elif command -v ss &>/dev/null; then
        pids="$(ss -lptn "sport = :${port}" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u | tr '\n' ' ')"
    fi

    if [ -n "$pids" ]; then
        # shellcheck disable=SC2086
        kill ${pids} 2>/dev/null || true
        sleep 1
        # shellcheck disable=SC2086
        kill -9 ${pids} 2>/dev/null || true
    fi

    sleep 1
}

stop_langgraph() {
    pkill -f "langgraph dev" 2>/dev/null || true
    stop_port "${LANGGRAPH_PORT}"
}

stop_streamlit() {
    pkill -f "streamlit run streamlit_ui.py" 2>/dev/null || true
    stop_port "${STREAMLIT_PORT}"
}

stop_frontend() {
    pkill -f "vite.*${FRONTEND_PORT}" 2>/dev/null || true
    pkill -f "node.*vite" 2>/dev/null || true
    stop_port "${FRONTEND_PORT}"
}

stop_all_services() {
    echo "Stopping services on ports ${LANGGRAPH_PORT} and ${FRONTEND_PORT}..."
    stop_langgraph
    stop_frontend
    stop_streamlit
    echo "Services stopped."
}

wait_for_port() {
    local port="$1"
    local retries="${2:-15}"
    local i=0

    while [ "$i" -lt "$retries" ]; do
        if command -v curl &>/dev/null && curl -fsS "http://127.0.0.1:${port}/ok" >/dev/null 2>&1; then
            return 0
        fi
        if command -v curl &>/dev/null && curl -fsS "http://127.0.0.1:${port}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done

    return 0
}
