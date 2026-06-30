import time
from typing import Dict, Any, List

class ProviderHealthMonitor:
    """Monitors, tracks, and exposes diagnostic statistics for all AI Providers."""
    
    def __init__(self):
        self.stats: Dict[str, Dict[str, Any]] = {}

    def get_stats(self, provider: str) -> Dict[str, Any]:
        p = provider.lower().strip()
        if p not in self.stats:
            self.stats[p] = {
                "available": False,
                "latency_history": [],
                "failures": 0,
                "successes": 0,
                "last_success_time": 0.0,
                "average_response_time": 0.0,
                "success_rate": 0.0,
                "status": "UNKNOWN"
            }
        return self.stats[p]

    def record_success(self, provider: str, latency: float) -> None:
        stats = self.get_stats(provider)
        stats["successes"] += 1
        stats["available"] = True
        stats["last_success_time"] = time.time()
        stats["latency_history"].append(latency)
        
        # Keep sliding window of 50 latencies
        if len(stats["latency_history"]) > 50:
            stats["latency_history"].pop(0)
            
        stats["average_response_time"] = sum(stats["latency_history"]) / len(stats["latency_history"])
        self._update_rates(stats)

    def record_failure(self, provider: str) -> None:
        stats = self.get_stats(provider)
        stats["failures"] += 1
        self._update_rates(stats)

    def _update_rates(self, stats: Dict[str, Any]) -> None:
        total = stats["successes"] + stats["failures"]
        if total > 0:
            stats["success_rate"] = (stats["successes"] / total) * 100
        else:
            stats["success_rate"] = 0.0
            
        if stats["success_rate"] >= 95:
            stats["status"] = "HEALTHY"
        elif stats["success_rate"] >= 50:
            stats["status"] = "DEGRADED"
        else:
            stats["status"] = "UNAVAILABLE"

    def get_diagnostics(self) -> Dict[str, Any]:
        """Returns provider metrics ready for formatting or logging, hiding history lists."""
        return {
            p: {k: v for k, v in v_data.items() if k != "latency_history"} 
            for p, v_data in self.stats.items()
        }
