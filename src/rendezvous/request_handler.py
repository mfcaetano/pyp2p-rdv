import json
from models import PeerRecord
from datetime import datetime, timezone

class RequestHandler:
    def __init__(self, peer_db):
        self.peer_db = peer_db

    def handle(self, request, client_ip, observed_port=None):
        cmd = request.command
        args = request.args
        
        if cmd == "REGISTER":
            namespace = request.args.get("namespace")
            name = request.args.get("name")
            port = request.args.get("port")
            ttl = request.args.get("ttl", 7200)
            
            #lets validate required fields
            if not isinstance(namespace, str) or not namespace or len(namespace) > 64:
                return json.dumps({"status": "ERROR", "error": "bad_namespace"})
            try:
                port = int(port)
                if not (1 <= port <= 65535):
                    raise ValueError()
            except (ValueError, TypeError):
                return json.dumps({"status": "ERROR", "error": "bad_port"})
            
            try:
                peer = PeerRecord(
                    ip=client_ip,
                    port=int(args.get("port")),
                    name=args.get("name"),
                    namespace=args["namespace"],
                    ttl=int(args.get("ttl", 7200)),
                    timestamp=datetime.now(timezone.utc),
                    observed_ip=client_ip,
                    observed_port=observed_port
                )
                self.peer_db.add_peer(peer)
                return json.dumps({
                    "status": "OK",
                    "ttl": peer.ttl,
                    "observed_ip": peer.observed_ip,       
                    "observed_port": peer.observed_port    
                })  
                          
            except Exception as e:
                return json.dumps({"status": "ERROR", "message": str(e)})
            
        elif cmd == "DISCOVER":
            namespace = args.get("namespace")
            peers = self.peer_db.get_peers(namespace)
            
            peer_list = [{
                "ip": p.ip,
                "port": p.port,
                "name": p.name,
                "namespace": p.namespace,
                "ttl": p.ttl,
                "observed_ip": p.observed_ip,             # << novo
                "observed_port": p.observed_port          # << novo
            } for p in peers]
            
            return json.dumps({"status": "OK", "peers": peer_list})
        
        elif cmd == "UNREGISTER":
            try:
                namespace = args.get("namespace")
                self.peer_db.remove_peer(client_ip, namespace)
                return json.dumps({"status": "OK"})
            
            except Exception as e:
                return json.dumps({"status": "ERROR", "message": str(e)})

        return json.dumps({"status": "ERROR", "message": "Unknown command"})    

