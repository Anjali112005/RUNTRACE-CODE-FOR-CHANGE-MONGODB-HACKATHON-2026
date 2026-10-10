from . import ai, analysis, health, metrics, projects, runs

ROUTERS = [health.router, projects.router, runs.router, analysis.router, metrics.router, ai.router]

__all__ = ["ROUTERS"]
