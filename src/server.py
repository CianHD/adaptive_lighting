"""
Production-ready server startup configuration for containerized deployment.
"""

import uvicorn
from main import app
from src.core.config import settings

def get_server_config():
    """Get server configuration based on environment"""

    # Server configuration from settings
    config = {
        'app': app,
        'host': settings.HOST,
        'port': settings.PORT,
        'log_level': settings.LOG_LEVEL.lower(),
        'access_log': settings.ENVIRONMENT != 'production',  # Disable access logs in production (handled by middleware)
    }

    if settings.ENVIRONMENT == 'production':
        # Production optimizations
        config.update({
            'workers': settings.WORKERS,
            'worker_class': 'uvicorn.workers.UvicornWorker',
            'timeout_keep_alive': settings.TIMEOUT_KEEP_ALIVE,
            'timeout_graceful_shutdown': settings.TIMEOUT_GRACEFUL_SHUTDOWN,
            'max_requests': settings.MAX_REQUESTS,
            'max_requests_jitter': settings.MAX_REQUESTS_JITTER,
        })
    else:
        # Development configuration
        config.update({
            'reload': True,
            'reload_dirs': ['src'],
        })

    return config

def start_server():
    """Start the server with appropriate configuration"""
    config = get_server_config()

    # Extract uvicorn-specific config
    uvicorn_config = {
        'app': config['app'],
        'host': config['host'],
        'port': config['port'],
        'log_level': config['log_level'],
        'access_log': config['access_log'],
    }

    environment = settings.ENVIRONMENT

    if environment == 'development':
        uvicorn_config.update({
            'reload': config['reload'],
            'reload_dirs': config['reload_dirs'],
        })

    uvicorn.run(**uvicorn_config)
if __name__ == "__main__":
    start_server()
