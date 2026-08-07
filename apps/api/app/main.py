"""FastAPI application entry point."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the API application."""
    return FastAPI(title="A-share AI Advisor API", version="0.1.0")


app = create_app()
