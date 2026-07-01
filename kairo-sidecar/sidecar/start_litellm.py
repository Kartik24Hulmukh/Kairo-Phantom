import socket
import subprocess
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [LITELLM_LAUNCHER] %(levelname)s %(message)s"
)
log = logging.getLogger("start_litellm")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    port = 4000
    if is_port_in_use(port):
        log.info(f"Port {port} is already in use. Assuming LiteLLM proxy is already running.")
        sys.exit(0)

    log.info("Starting LiteLLM local gateway on port 4000...")
    config_path = Path(__file__).parent / "litellm_config.yaml"

    # Run litellm command using the proxy entrypoint directly to support all package managers
    cmd = [
        sys.executable,
        "-c",
        "from litellm.proxy.proxy_cli import run_server; run_server()",
        "--config",
        str(config_path),
        "--port",
        str(port),
    ]

    import os

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        # Hide console window on Windows to run completely silently in background
        startupinfo = None
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            startupinfo=startupinfo,
            close_fds=True,
        )
        log.info(f"LiteLLM background process spawned successfully with PID: {process.pid}")
    except Exception as e:
        log.error(f"Failed to start LiteLLM process: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
