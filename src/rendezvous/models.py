from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

@dataclass
class PeerRecord:
    ip : str
    port: int
    name: str
    namespace: str
    ttl: int
    timestamp: datetime
    observed_ip: Optional[str] = None
    observed_port: Optional[int] = None

    
    
    def is_expired(self):
        return datetime.now(timezone.utc) > self.timestamp + timedelta(seconds=self.ttl)
