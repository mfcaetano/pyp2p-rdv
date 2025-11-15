
import json
import logging

log = logging.getLogger("parser")

class Request:
    def __init__(self, command, args):
        self.command = command
        self.args = args


class ProtocolParser:
    def parse(self, raw_data):
        try:
            data = json.loads(raw_data)
            
            if not isinstance(data.get("type"), str):
                log.warning("Missing 'type' in JSON: %s", raw_data)
                return Request("ERROR", {"message": "missing_type"})
            
            return Request(data.get("type").upper(), data)
        
        
        except json.JSONDecodeError:
            log.warning("Invalid JSON: %s", raw_data)
            return Request("ERROR", {"message": "invalid_json", "hint": "Expect JSON object per line"})
        except Exception:
            log.exception("Unexpected parser error")
            return Request("ERROR", {"message": "Invalid JSON"})
        