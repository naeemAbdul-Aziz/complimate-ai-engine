"""
Production Logging System for CompliMate AI Engine
=================================================

Enterprise-grade logging configuration with colored console output,
file rotation, component separation, and performance monitoring.

This module provides a centralized logging system that follows industry
best practices for observability, debugging, and production monitoring.

Author: CompliMate AI Team
Version: 2.0.0
License: MIT
"""

import os
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Union
import locale

# Import application settings with fallback
try:
    from config.settings import settings
except ImportError:
    # Fallback settings if config module not available
    class DefaultSettings:
        LOG_LEVEL = "INFO"
    settings = DefaultSettings()

# Optional colorlog dependency for enhanced console output
try:
    import colorlog
    HAS_COLOR_SUPPORT = True
except ImportError:
    HAS_COLOR_SUPPORT = False


class LoggerAdapter(logging.LoggerAdapter):
    """
    Enhanced logger adapter that adds contextual information to log records.
    
    This adapter follows the standard logging adapter pattern but adds
    application-specific context like component names, request IDs, and
    session information for better traceability in production environments.
    
    Attributes:
        logger: The underlying logger instance
        extra: Additional context data to include in log records
    """
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        """
        Initialize the logger adapter with optional context.
        
        Args:
            logger: Base logger instance
            extra: Dictionary of extra context to add to all log records
        """
        super().__init__(logger, extra or {})
    
    def process(self, msg: Any, kwargs: Dict[str, Any]) -> tuple:
        """
        Process logging call to inject additional context.
        
        This method is called by the logging framework before each log
        record is emitted. It adds component context and session IDs
        to help with distributed tracing and debugging.
        
        Args:
            msg: The log message
            kwargs: Logging keyword arguments
            
        Returns:
            Tuple of (processed_message, updated_kwargs)
        """
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        
        # Inject component context from adapter
        if self.extra:
            kwargs['extra'].update(self.extra)
            
        # Add session/request ID if available on logger instance
        if hasattr(self.logger, '_session_id'):
            kwargs['extra']['session_id'] = getattr(self.logger, '_session_id')
            
        return msg, kwargs


class SafeConsoleHandler(logging.StreamHandler):
    """Console handler that never crashes on Unicode encode errors.

    On Windows (cp1252), certain Unicode characters (emojis) cause
    UnicodeEncodeError when writing to the console. This handler falls back
    to replacing unsupported characters for console output while preserving
    full Unicode in file logs.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream = self.stream
            encoding = getattr(stream, 'encoding', None) or locale.getpreferredencoding(False) or 'utf-8'
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                safe = msg.encode(encoding, errors='replace').decode(encoding, errors='replace')
                stream.write(safe + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def configure_logging(
    enable_colors: bool = True,
    log_directory: Optional[str] = None,
    components: Optional[list] = None
) -> Dict[str, logging.Logger]:
    """
    Configure application-wide logging with file rotation and colored console output.
    
    This function sets up a production-ready logging system with:
    - Rotating file handlers for different log levels and components
    - Colored console output for development and debugging
    - Component-specific loggers for better organization
    - Performance monitoring and error tracking
    
    Args:
        enable_colors (bool): Enable colored console output (default: True)
        log_directory (str, optional): Custom directory for log files (default: ./logs)
        components (list, optional): Component names for separate loggers
        
    Returns:
        Dict[str, logging.Logger]: Dictionary mapping component names to logger instances
        
    Raises:
        OSError: If log directory cannot be created
        
    Example:
        >>> loggers = configure_logging(components=['api', 'engine'])
        >>> api_logger = loggers['api']
        >>> api_logger.info('API server started')
    """
    # Create logs directory
    if log_directory is None:
        log_dir_path = Path.cwd() / "logs"
    else:
        log_dir_path = Path(log_directory)
    
    log_dir_path.mkdir(exist_ok=True, parents=True)
    
    # Default components
    if components is None:
        components = [
            'api', 'engine', 'parsing', 'retrieval', 
            'violation', 'reporting', 'storage', 'auth'
        ]
    
    # Log file configuration
    log_files = {
        'main': log_dir_path / "complimate.log",
        'api': log_dir_path / "api.log",
        'engine': log_dir_path / "engine.log",
        'errors': log_dir_path / "errors.log",
        'performance': log_dir_path / "performance.log"
    }
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))
    root_logger.handlers.clear()
    
    # Silence noisy third-party loggers (e.g., ChromaDB telemetry/posthog)
    # These can emit benign errors/warnings on Windows or when telemetry is disabled.
    for noisy in [
        "chromadb.telemetry",
        "chromadb.telemetry.product.posthog",
        "posthog",
    ]:
        logging.getLogger(noisy).setLevel(logging.CRITICAL)
    
    # Create file formatter
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s:%(lineno)-4d | %(message)s"
    )
    
    # Create console formatter with colors
    if enable_colors and HAS_COLOR_SUPPORT:
        console_formatter = colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s | %(levelname)-8s%(reset)s | %(blue)s%(name)-20s%(reset)s | %(funcName)-15s:%(lineno)-4d | %(message)s',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green', 
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
    else:
        console_formatter = file_formatter
    
    # Console handler
    console_handler = SafeConsoleHandler()
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL))
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Main application log file
    main_handler = logging.handlers.RotatingFileHandler(
        log_files['main'],
        maxBytes=20 * 1024 * 1024,  # 20MB
        backupCount=10,
        encoding='utf-8'
    )
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(file_formatter)
    root_logger.addHandler(main_handler)
    
    # Error log file (only ERROR and CRITICAL)
    error_formatter = logging.Formatter(
        "%(asctime)s | ERROR | %(name)s | %(pathname)s:%(lineno)d | %(message)s\\n%(exc_text)s"
    )
    error_handler = logging.handlers.RotatingFileHandler(
        log_files['errors'],
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(error_formatter)
    root_logger.addHandler(error_handler)
    
    # Component-specific loggers
    loggers = {}
    
    for component in components:
        component_logger = logging.getLogger(f"complimate.{component}")
        
        # Component-specific file handler for important components
        if component in ['api', 'engine']:
            component_file = log_files.get(component, log_dir_path / f"{component}.log")
            component_handler = logging.handlers.RotatingFileHandler(
                component_file,
                maxBytes=15 * 1024 * 1024,  # 15MB
                backupCount=7,
                encoding='utf-8'
            )
            component_handler.setLevel(logging.DEBUG)
            component_handler.setFormatter(file_formatter)
            component_logger.addHandler(component_handler)
        
        loggers[component] = LoggerAdapter(
            component_logger, 
            extra={'component': component}
        )
    
    # Performance logger
    perf_logger = logging.getLogger("complimate.performance")
    perf_handler = logging.handlers.RotatingFileHandler(
        log_files['performance'],
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    perf_handler.setLevel(logging.INFO)
    perf_handler.setFormatter(file_formatter)
    perf_logger.addHandler(perf_handler)
    perf_logger.setLevel(logging.INFO)
    
    loggers['performance'] = LoggerAdapter(
        perf_logger,
        extra={'component': 'performance'}
    )
    
    # Log startup information
    main_logger = logging.getLogger("complimate.main")
    main_logger.info("=" * 60)
    main_logger.info("CompliMate AI Engine - Logging System Initialized")
    main_logger.info(f"Log Level: {settings.LOG_LEVEL}")
    main_logger.info(f"Log Directory: {log_dir_path}")
    main_logger.info(f"Color Support: {'Enabled' if enable_colors and HAS_COLOR_SUPPORT else 'Disabled'}")
    main_logger.info(f"Components: {', '.join(components)}")
    main_logger.info("=" * 60)
    
    return loggers


def get_logger(name: str) -> logging.Logger:
    """
    Get a simple, ready-to-use logger instance.
    
    This is the primary function for getting loggers throughout the application.
    It provides a standardized logger with file and console output, following
    industry best practices for log formatting and rotation.
    
    The logger automatically:
    - Writes to app.log file with rotation
    - Displays colored output in console (if colorlog available)
    - Uses consistent timestamp and message formatting
    - Creates log directory if it doesn't exist
    
    Args:
        name (str): Logger name, typically __name__ from calling module
        
    Returns:
        logging.Logger: Configured logger instance ready for use
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info('Application started successfully')
        >>> logger.error('Failed to connect to database')
        
    Note:
        This function is thread-safe and can be called multiple times
        with the same name - it will return the same logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers if logger already configured
    if not logger.handlers:
        # Ensure logs directory exists
        log_dir = Path.cwd() / "logs"
        log_dir.mkdir(exist_ok=True, parents=True)
        
        # File handler: Writes all logs to app.log with simple format
        file_handler = logging.FileHandler(log_dir / 'app.log')
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler: Colored output for development, plain for production
        console_handler = logging.StreamHandler()
        if HAS_COLOR_SUPPORT:
            color_formatter = colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'bold_red',
                }
            )
            console_handler.setFormatter(color_formatter)
        else:
            # Fallback to plain formatting if colorlog not available
            plain_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(plain_formatter)
        
        logger.addHandler(console_handler)

    return logger


def get_component_logger(component: str) -> LoggerAdapter:
    """
    Get or create a logger for a specific application component.
    
    Creates a component-specific logger with enhanced context information.
    This is useful for separating logs by functional area (api, engine, etc.)
    
    Args:
        component (str): Component name (e.g., 'api', 'engine', 'parsing')
        
    Returns:
        LoggerAdapter: Logger instance with component context
        
    Example:
        >>> logger = get_component_logger('api')
        >>> logger.info('Processing request')  # Will include component=api in log
    """
    logger = logging.getLogger(f"complimate.{component}")
    return LoggerAdapter(logger, extra={'component': component})


def log_performance(
    operation: str,
    duration: float,
    success: bool = True,
    extra_data: Optional[Dict[str, Any]] = None
):
    """
    Log performance metrics for monitoring and optimization.
    
    This function provides standardized performance logging that helps
    with monitoring application performance, identifying bottlenecks,
    and tracking system health in production environments.
    
    The performance data is logged in a structured format that can be
    easily parsed by log analysis tools like ELK stack, Splunk, or
    application monitoring services.
    
    Args:
        operation (str): Name of the operation being measured
        duration (float): Duration in seconds with decimal precision
        success (bool): Whether the operation completed successfully (default: True)
        extra_data (dict, optional): Additional metrics or context data
        
    Example:
        >>> start_time = time.time()
        >>> # ... perform database query ...
        >>> duration = time.time() - start_time
        >>> log_performance('database_query', duration, True, {'table': 'users', 'rows': 150})
        
    Note:
        Performance logs are written to a separate performance.log file
        for easier analysis and monitoring dashboard integration.
    """
    perf_logger = logging.getLogger("complimate.performance")
    
    # Build structured metrics dictionary
    metrics = {
        'operation': operation,
        'duration_seconds': round(duration, 4),
        'success': success,
        'timestamp': datetime.now().isoformat()
    }
    
    # Add any additional performance data
    if extra_data:
        metrics.update(extra_data)
    
    # Log in human-readable format for monitoring
    status = 'SUCCESS' if success else 'FAILED'
    perf_logger.info(f"PERF: {operation} ({status}) in {duration:.4f}s")
    
    # Log structured data as a separate debug entry for parsing
    perf_logger.debug(f"METRICS: {metrics}")


def create_request_logger(request_id: str) -> LoggerAdapter:
    """
    Create a logger for tracking a specific request or session.
    
    This is particularly useful for distributed tracing and debugging
    user-specific issues in production environments.
    
    Args:
        request_id (str): Unique identifier for the request/session
        
    Returns:
        LoggerAdapter: Logger instance with request context
        
    Example:
        >>> logger = create_request_logger('req_123456')
        >>> logger.info('Processing user request')  # Will include request_id in log
    """
    logger = logging.getLogger("complimate.request")
    # Add session_id as a custom attribute for filtering
    setattr(logger, '_session_id', request_id)
    
    return LoggerAdapter(
        logger,
        extra={'request_id': request_id}
    )


# =============================================================================
# Module Initialization and Exports
# =============================================================================

# Initialize the logging system when this module is imported
# This ensures consistent logging configuration across the entire application
_loggers = configure_logging(
    enable_colors=os.getenv("LOG_COLORS", "true").lower() == "true",
    components=['api', 'engine', 'parsing', 'retrieval', 'violation', 'reporting', 'storage']
)

# Export commonly used pre-configured loggers for convenience
# These can be imported directly: from config.logger import api_logger
api_logger = _loggers.get('api')
engine_logger = _loggers.get('engine') 
performance_logger = _loggers.get('performance')

# =============================================================================
# Public API - Main functions that should be used by application code
# =============================================================================

__all__ = [
    'get_logger',                # Primary function for getting loggers
    'get_component_logger',      # For component-specific logging  
    'create_request_logger',     # For request/session tracking
    'log_performance',           # For performance monitoring
    'api_logger',               # Pre-configured API logger
    'engine_logger',            # Pre-configured engine logger
    'performance_logger',       # Pre-configured performance logger
]