
import socket
import threading
import time
from collections import defaultdict, deque
from peer_db import PeerDatabase
from protocol_parser import ProtocolParser
from request_handler import RequestHandler
import json
import logging


log = logging.getLogger("rendezvous")

MAX_LINE = 32 * 1024  # 32KB

class RendezvousServer:
    """
    Rendezvous server with thread-safe IP blocking mechanism.
    
    The server implements a sliding window approach to track connection attempts
    and block IPs that exceed the configured threshold. This helps protect against
    simple DoS attacks and excessive connection attempts.
    
    Limitations:
    - NAT/proxy scenarios: Multiple legitimate clients behind the same NAT/proxy
      share the same public IP and may trigger false-positive blocks.
    - IPv4/IPv6 normalization: The current implementation treats IPv4 and IPv6
      addresses separately without normalization.
    - Memory: While old entries are cleaned during block expiration, very long-running
      servers with many unique IPs may accumulate entries. In production, consider
      periodic cleanup of unused entries.
    
    Recommendations for production:
    - Adjust max_attempts, window_seconds, and block_time based on expected traffic
    - Consider implementing IP whitelisting for trusted sources
    - Monitor false-positive blocks in NAT/proxy environments
    - Consider using external rate-limiting solutions (e.g., fail2ban, iptables)
      for more sophisticated protection
    """
    def __init__(self, host='0.0.0.0', port=5000, max_attempts=50, window_seconds=60, block_time=60):
        self.host = host
        self.port = port
        self.peer_db = PeerDatabase()
        self.parser = ProtocolParser()
        self.handler = RequestHandler(self.peer_db)
        
        # IP blocking configuration
        self.max_attempts = max_attempts  # Maximum connection attempts in the time window
        self.window_seconds = window_seconds  # Time window for counting attempts (in seconds)
        self.block_time = block_time  # Duration to block an IP (in seconds)
        
        # Thread-safe data structures for IP blocking
        self.attempts = defaultdict(deque)  # IP -> deque of connection timestamps
        self.blocked_ips = {}  # IP -> block timestamp
        self.attempts_lock = threading.Lock()  # Lock to protect shared data structures
        
        
    def handle_client(self, connection, address):
        connection.settimeout(5)
        buf = b""
        line = None
        peer = f"{address[0]}:{address[1]}"
        client_ip = address[0]
        
        # IP blocking check with thread-safe access
        with self.attempts_lock:
            now = time.time()
            
            # Check if IP is currently blocked
            if client_ip in self.blocked_ips:
                block_timestamp = self.blocked_ips[client_ip]
                time_since_block = now - block_timestamp
                
                if time_since_block < self.block_time:
                    # Still blocked
                    log.warning(f"Connection from {peer} blocked due to too many attempts "
                               f"({int(self.block_time - time_since_block)}s remaining)")
                    try:
                        connection.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    connection.close()
                    return
                else:
                    # Block expired, remove from blocked list and clear attempts
                    del self.blocked_ips[client_ip]
                    if client_ip in self.attempts:
                        self.attempts[client_ip].clear()
            
            # Clean old timestamps from the sliding window
            attempts_deque = self.attempts[client_ip]
            while attempts_deque and attempts_deque[0] < now - self.window_seconds:
                attempts_deque.popleft()
            
            # Check if this IP has exceeded the maximum attempts
            if len(attempts_deque) >= self.max_attempts:
                # Block this IP
                self.blocked_ips[client_ip] = now
                log.warning(f"Connection from {peer} blocked due to too many attempts "
                           f"({len(attempts_deque)} attempts in {self.window_seconds}s)")
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                connection.close()
                return
            
            # Record this connection attempt
            attempts_deque.append(now)
        
        log.info(f"Connection from {peer}")
        t = threading.current_thread()
        old_name = t.name
        
        try:
            # Changing thread name for better logging
            t.name = f"cli-{address[0]}:{address[1]}"
            
            while True:
                try:
                    chunk = connection.recv(4096)
                    if not chunk:
                        # EOF: se já tem algo no buffer, processa como uma linha; senão encerra.
                        if buf.strip():
                            line = buf
                        break
                    buf += chunk
                    
                    if len(buf) > MAX_LINE:
                        log.warning("Request line too long from %s: %d bytes (limit=%d). Closing.", peer, len(buf), MAX_LINE)
                        log.debug("First 200 bytes from %s: %r", peer, buf[:200])
                        
                        msg = json.dumps({"status": "ERROR","error": "line_too_long","limit": MAX_LINE})
                        try:
                            connection.sendall((msg + "\n").encode("utf-8"))
                        except (socket.timeout, BrokenPipeError, ConnectionResetError) as e:
                            # Quieter log to avoid clutter in DoS scenarios
                            log.debug("Failed to send 'line_too_long' to %s: %s", peer, e)
                        return # close connection at finally block
                    
                    if b"\n" in buf:
                        line, _rest = buf.split(b"\n", 1)
                        break
                    
                except (TimeoutError, socket.timeout):
                    msg = json.dumps({"status": "ERROR", "message": "Timeout: no data received, closing connection"}) 
                    
                    log.warning("Timeout waiting data from %s; sending error and closing", peer)

                    try:
                        connection.sendall((msg + "\n").encode("utf-8"))
                    finally:
                        return # close connection at finally block
                    
            # if did come useful data, process it and close connection        
            if not line or not line.strip():
                msg = json.dumps({"status": "ERROR", "message": "Empty request line"})
                log.warning("Empty request line from %s; sending error", peer)

                connection.sendall((msg + "\n").encode("utf-8"))
                return
            
            # parse and handle request    
            raw = line.decode("utf-8", errors="replace")         
            log.info("Received from %s: %s", peer, raw.strip())  
        
            request = self.parser.parse(raw)
            
            log.info("Parsed request (%s) from %s", request.command, peer)

            response = self.handler.handle(request, address[0], observed_port=address[1])
            connection.sendall((response + "\n").encode("utf-8"))
            
            try:  
                status = json.loads(response).get("status") 
            except Exception:
                status = "?"
            log.info("Responded to %s (status=%s)", peer, status)

            # after sending response, just close connection
            return
               
        finally:
            t.name = old_name
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            
            connection.close()
            log.info("Connection closed with %s", peer)

            
            
    def start(
        self,
        max_workers: int = 64,
        backlog: int = 128,
        ka_idle: int = 60,
        ka_intvl: int = 15,
        ka_cnt: int = 4,
    ):
        import concurrent.futures  # keep import local to avoid new global deps
            
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Enable TCP keepalive on the listening socket (best effort / platform-aware)
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                server.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, ka_idle)
            if hasattr(socket, "TCP_KEEPINTVL"):
                server.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, ka_intvl)
            if hasattr(socket, "TCP_KEEPCNT"):
                server.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, ka_cnt)
            # macOS uses TCP_KEEPALIVE (idle time)
            if hasattr(socket, "TCP_KEEPALIVE"):
                server.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, ka_idle)
        except Exception as e:
            log.debug("Keepalive tuning not supported on listener: %s", e)

        server.bind((self.host, self.port))
        server.listen(backlog)
        
        log.info("Rendezvous server listening on %s:%d (backlog=%d, workers=%d)",
                 self.host, self.port, backlog, max_workers)
        
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix='cli'
        ) as executor:
            while True:
                connection, address = server.accept()
                
                # Also enable keepalive on accepted sockets (some OSes don't inherit all opts)
                try:
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    if hasattr(socket, "TCP_KEEPIDLE"):
                        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, ka_idle)
                    if hasattr(socket, "TCP_KEEPINTVL"):
                        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, ka_intvl)
                    if hasattr(socket, "TCP_KEEPCNT"):
                        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, ka_cnt)
                    if hasattr(socket, "TCP_KEEPALIVE"):
                        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, ka_idle)
                except Exception as e:
                    log.debug("Keepalive not supported on accepted socket %s:%s: %s", *address, e)

                # Hand over to the pool (limits concurrency)
                executor.submit(self.handle_client, connection, address)


