

from rendezvous import RendezvousServer
import logging
import argparse
from pathlib import Path


def setup_logging(mode: str, logfile: str | None):
    """
    mode: 'console' | 'file' | 'both'
    logfile: path for file logging when mode is 'file' or 'both'
    """
    # Clean existing handlers to avoid duplicates one reloads
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s [%(threadName)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handlers = []
    if mode in ("console", "both"):
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        handlers.append(ch)

    if mode in ("file", "both"):
        if not logfile:
            logfile = "server.log"
        # ensure parent directory exists (if provided)
        Path(logfile).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(logfile, mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        handlers.append(fh)
        
    for h in handlers:
        root.addHandler(h)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rendezvous server launcher with flexible logging.")
    parser.add_argument(
        "--log-mode",
        choices=["console", "file", "both"],
        default="console",
        help="Where to write logs: console, file, or both (default: console).",
    )
    parser.add_argument(
        "--log-file",
        default="server.log",
        help="Log file path when using modes 'file' or 'both' (default: server.log).",
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host/IP for the rendezvous server (default: 0.0.0.0).",
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for the rendezvous server (default: 8080).",
    )
    
    args = parser.parse_args()

    setup_logging(args.log_mode, args.log_file)
    
    server = RendezvousServer(args.host, args.port)
    server.start()
