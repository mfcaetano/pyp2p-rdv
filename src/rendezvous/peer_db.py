import json
import os
from models import PeerRecord
from datetime import datetime
import threading, tempfile
from dataclasses import asdict
import logging

log = logging.getLogger("peer_db")

class PeerDatabase:
    def __init__(self, filename="peers.json"):
        self.filename = filename
        self._lock = threading.RLock()
        self.peers = self._load()

    def _load(self):
        if not os.path.exists(self.filename):
            log.info("Peer DB file not found (%s); starting empty", self.filename)
            return []

        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError:
            log.error("File %s is corrupted; starting empty", self.filename)
            return []

        records = []
        for peer in raw:
            data = dict(peer)  # cópia
            ts = data.get("timestamp")

            #  Normalize to timezone-aware datetime
            if isinstance(ts, str):
                s = ts.strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                data["timestamp"] = datetime.fromisoformat(s)
            elif isinstance(ts, (int, float)):
                data["timestamp"] = datetime.fromtimestamp(ts, tz=timezone.utc)

            records.append(PeerRecord(**data))
            
        log.info("Loaded %d peer(s) from %s", len(records), self.filename)
        return records


    def _save_locked(self):
        # MUST be called with self._lock held
        tmpf = self.filename + ".tmp"

        # prepara conteúdo serializável
        payload = []
        for p in self.peers:
            d = dict(p.__dict__)  # se for dataclass, poderia usar asdict(p)
            ts = d.get("timestamp")
            if isinstance(ts, datetime):
                d["timestamp"] = ts.isoformat()
            else:
                # se por algum motivo já for str/epoch, garante string ISO
                d["timestamp"] = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
            payload.append(d)

        with open(tmpf, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmpf, self.filename)
        
        log.info("Saved %d peer(s) into %s", len(self.peers), self.filename)
        
    def _save(self):
        with self._lock:
            self._save_locked()

    def _sweep(self):
        with self._lock:
            before = len(self.peers)
            self.peers = [p for p in self.peers if not p.is_expired()]
            expired = before - len(self.peers)
        if expired:
            log.info("Expired %d peer(s) removed", expired)


    def add_peer(self, peer: PeerRecord):
        with self._lock:
            # optional dedup key: (ip, namespace, name)
            self.peers = [p for p in self.peers
                          if not (p.ip == peer.ip and p.namespace == peer.namespace and p.name == peer.name)]
            self._sweep()
            self.peers.append(peer)
            self._save_locked()

    def remove_peer(self, ip, namespace, name=None, port=None):
        with self._lock:
            before = len(self.peers)
            
            def match(p):
                ok = (p.ip == ip and p.namespace == namespace)
                if name is not None:
                    ok &= (p.name == name)
                if port is not None:
                    ok &= (p.port == port)
                return ok
            
            self.peers = [p for p in self.peers if not match(p)]
            removed = before - len(self.peers)
            log.info("Removed %d peer(s) ip=%s ns=%s name=%r port=%r",
                     removed, ip, namespace, name, port)
            self._save_locked()

        

    def get_peers(self, namespace=None):
        with self._lock:
            self._sweep()
            if namespace:
                return [p for p in self.peers if p.namespace == namespace]
            return self.peers  # return a shallow copy
    
    def get_all_db(self):
        with self._lock:
            return self.peers
