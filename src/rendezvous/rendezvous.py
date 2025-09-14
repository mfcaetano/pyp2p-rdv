
import socket
import threading
from peer_db import PeerDatabase
from protocol_parser import ProtocolParser
from request_handler import RequestHandler
import json


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
        
        try:
            while True:
                try:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        
                        request = self.parser.parse(line.decode("utf-8", errors="replace"))
                        response = self.handler.handle(request, address[0], observed_port=address[1])
                        connection.sendall((response + "\n").encode("utf-8"))
                        
                except (TimeoutError, socket.timeout):
                    msg = json.dumps({"status": "ERROR", "message": "Timeout: no data received, closing connection"}) + "\n"
                    
                    try:
                        connection.sendall(msg.encode("utf-8") + b"\n")
                        break
                    except Exception:
                        # the connection is probably already closed
                        pass
        finally:
            connection.close()
            
            
    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen()
        print(f"Rendezvous server listening on {self.host}:{self.port}")
        
        
        while True:
            connection, address = server.accept()
            threading.Thread(target=self.handle_client, args=(connection, address)).start()
        



