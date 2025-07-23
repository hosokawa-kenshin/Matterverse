#!/usr/bin/env python3
"""
Entry point for Matterverse application.
"""
import asyncio
import sys
import uvicorn
from matterverse_app import create_application


async def main():
    """Main entry point."""
    try:
        print("Starting Matterverse application...")
        app = await create_application()
        
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            reload=False
        )
        
        server = uvicorn.Server(config)
        await server.serve()
        
    except KeyboardInterrupt:
        print("\nApplication stopped by user")
    except Exception as e:
        print(f"Application error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
