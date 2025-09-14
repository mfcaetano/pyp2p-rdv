
import json


class Request:
    def __init__(self, command, args):
        self.command = command
        self.args = args


class ProtocolParser:
    def parse(self, raw_data):
        try:
            data = json.loads(raw_data)
            
            if not isinstance(data.get("type"), str):
                return Request("ERROR", {"error": "missing_type"})
            
            return Request(data.get("type").upper(), data)
        
        
        except json.JSONDecodeError:
            return Request("ERROR", {"error": "invalid_json", "hint": "Expect JSON object per line"})
        except Exception:
            return Request("ERROR", {"message": "Invalid JSON"})
        