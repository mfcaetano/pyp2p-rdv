
import socket
import threading
from peer_db import PeerDatabase
from protocol_parser import ProtocolParser
from request_handler import RequestHandler
import json
import logging

log = logging.getLogger("rendezvous")

MAX_LINE = 32 * 1024  # 32KB

class RendezvousServer:
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.peer_db = PeerDatabase()
        self.parser = ProtocolParser()
        self.handler = RequestHandler(self.peer_db)
        
        
    def handle_client(self, connection, address):
        connection.settimeout(5)
        buf = b""
        line = None
        peer = f"{address[0]}:{address[1]}"
        log.info(f"Connection from {peer}")
        
        try:
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
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            
            connection.close()
            log.info("Connection closed with %s", peer)

            
            
    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen()
        log.info("Rendezvous server listening on %s:%d", self.host, self.port)
        
        
        while True:
            connection, address = server.accept()
            
            threading.Thread(
                target=self.handle_client,
                args=(connection, address),
                daemon=True,
                name=f"cli-{address[0]}:{address[1]}",
            ).start()
        



