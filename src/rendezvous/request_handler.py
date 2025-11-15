import json
from models import PeerRecord
from datetime import datetime, timezone
import logging

log = logging.getLogger("Handler")

class RequestHandler:
    def __init__(self, peer_db):
        self.peer_db = peer_db

    def handle(self, request, client_ip):
        cmd = request.command
        args = request.args
        
        if cmd == "REGISTER":
            namespace = request.args.get("namespace")
            name = request.args.get("name")
            port = request.args.get("port")
            ttl = request.args.get("ttl", 7200)
            
            log.info(
                "REGISTER from ip=%s ns=%r name=%r port=%r ttl=%r",
                client_ip, namespace, name, port, ttl
            )
            
            if not isinstance(name, str) or not name or len(name) > 64:
                log.warning("REGISTER invalid (name)")
                return json.dumps({"status": "ERROR", "message": "bad_name"})
            
            # TTL clamp (1 .. 86400)
            try:
                ttl = int(ttl)
                if ttl < 1 or ttl > 86400:
                    ttl = max(1, min(ttl, 86400))
            except (ValueError, TypeError):
                log.warning("REGISTER invalid (ttl)")
                return json.dumps({"status": "ERROR", "message": "bad_ttl"})
            
            #lets validate required fields
            if not isinstance(namespace, str) or not namespace or len(namespace) > 64:
                log.warning("REGISTER invalid (namespace)")
                return json.dumps({"status": "ERROR", "message": "bad_namespace"})
            
            try:
                port = int(port)
                if not (1 <= port <= 65535):
                    raise ValueError()
            except (ValueError, TypeError):
                log.warning("REGISTER invalid (port)")
                return json.dumps({"status": "ERROR", "message": "bad_port"})
            
            try:
                peer = PeerRecord(
                    ip=client_ip,
                    port=int(args.get("port")),
                    name=args.get("name"),
                    namespace=args["namespace"],
                    ttl=ttl,
                    timestamp=datetime.now(timezone.utc),
                )
                self.peer_db.add_peer(peer)
                
                log.info("REGISTER OK: %s:%d ns=%s ttl=%d", peer.ip, peer.port, peer.namespace, peer.ttl)
                
                return json.dumps({
                    "status": "OK",
                    "ttl": peer.ttl,
                    "ip": peer.ip,       
                    "port": peer.port    
                })  
                          
            except Exception as e:
                log.exception("REGISTER failed")
                return json.dumps({"status": "ERROR", "message": str(e)})

            
        elif cmd == "DISCOVER":
            namespace = args.get("namespace")
            peers = self.peer_db.get_peers(namespace)
            now = datetime.now(timezone.utc)
            
            peer_list = [{
                "ip": p.ip,
                "port": p.port,
                "name": p.name,
                "namespace": p.namespace,
                "ttl": p.ttl,
                "expires_in": max(0, int(p.ttl - (now - p.timestamp).total_seconds()))
            } for p in peers]
            
            log.info("DISCOVER ns=%r -> %d peer(s)", namespace, len(peer_list)) 
            
            return json.dumps({"status": "OK", "peers": peer_list})
        
        elif cmd == "UNREGISTER":
            try:
                namespace = args.get("namespace")
                name = args.get("name")
                port = args.get("port")
                
                if port is not None:
                    try:
                        port = int(port)
                    except (ValueError, TypeError):
                        log.warning(f"UNREGISTER invalid (port:{port})")
                        return json.dumps({"status": "ERROR", "message": f"bad_port ({port})"})
                    
                self.peer_db.remove_peer(client_ip, namespace, name=name, port=port)
                
                log.info("UNREGISTER ip=%s ns=%r name=%r port=%r OK", 
                         client_ip, namespace, name, port)

                return json.dumps({"status": "OK"})
            
            except Exception as e:
                log.exception("UNREGISTER failed")
                return json.dumps({"status": "ERROR", "message": str(e)})

        log.warning("Unknown command: %s", cmd)
        return json.dumps({"status": "ERROR", "message": "Unknown command"})    

