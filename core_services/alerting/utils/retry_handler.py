"""
Retry handler with exponential backoff.
Retries failed operations with increasing delays.
"""

import time
from typing import Callable, Tuple, Optional, Any
from loguru import logger


class RetryHandler:
    """
    Retry handler with exponential backoff.

    Implements retry logic for failed operations with configurable
    max attempts and exponential delay between retries.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 5.0,
        backoff_factor: float = 2.0,
        max_delay: float = 60.0
    ):
        """
        Initialize retry handler.

        Args:
            max_attempts: Maximum number of retry attempts (including initial)
            initial_delay: Initial delay in seconds
            backoff_factor: Multiplier for delay on each retry (exponential backoff)
            max_delay: Maximum delay between retries in seconds
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay

    def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Tuple[bool, Optional[Exception]]:
        """
        Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Tuple of (success: bool, last_exception: Optional[Exception])
        """
        last_exception = None
        delay = self.initial_delay

        for attempt in range(1, self.max_attempts + 1):
            try:
                # Execute function
                result = func(*args, **kwargs)

                # If function returns a boolean, check it
                if isinstance(result, bool):
                    if result:
                        if attempt > 1:
                            logger.info(f"Operation succeeded on attempt {attempt}/{self.max_attempts}")
                        return True, None
                    else:
                        raise Exception("Function returned False")
                else:
                    # Non-boolean return value considered success
                    if attempt > 1:
                        logger.info(f"Operation succeeded on attempt {attempt}/{self.max_attempts}")
                    return True, None

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Attempt {attempt}/{self.max_attempts} failed: {str(e)}"
                )

                # If not last attempt, wait before retrying
                if attempt < self.max_attempts:
                    # Calculate delay with exponential backoff
                    current_delay = min(delay, self.max_delay)
                    logger.info(f"Retrying in {current_delay:.1f} seconds...")
                    time.sleep(current_delay)
                    delay *= self.backoff_factor

        # All attempts failed
        logger.error(
            f"Operation failed after {self.max_attempts} attempts. "
            f"Last error: {last_exception}"
        )
        return False, last_exception

    def execute_with_custom_retry(
        self,
        func: Callable,
        should_retry_fn: Optional[Callable[[Exception], bool]] = None,
        *args,
        **kwargs
    ) -> Tuple[bool, Optional[Exception]]:
        """
        Execute function with custom retry logic.

        Args:
            func: Function to execute
            should_retry_fn: Optional function to determine if exception should be retried.
                           Takes exception as input, returns True to retry.
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Tuple of (success: bool, last_exception: Optional[Exception])
        """
        last_exception = None
        delay = self.initial_delay

        for attempt in range(1, self.max_attempts + 1):
            try:
                # Execute function
                result = func(*args, **kwargs)

                # If function returns a boolean, check it
                if isinstance(result, bool):
                    if result:
                        if attempt > 1:
                            logger.info(f"Operation succeeded on attempt {attempt}/{self.max_attempts}")
                        return True, None
                    else:
                        raise Exception("Function returned False")
                else:
                    # Non-boolean return value considered success
                    if attempt > 1:
                        logger.info(f"Operation succeeded on attempt {attempt}/{self.max_attempts}")
                    return True, None

            except Exception as e:
                last_exception = e

                # Check if we should retry this exception
                if should_retry_fn and not should_retry_fn(e):
                    logger.warning(f"Exception is not retryable: {str(e)}")
                    return False, e

                logger.warning(
                    f"Attempt {attempt}/{self.max_attempts} failed: {str(e)}"
                )

                # If not last attempt, wait before retrying
                if attempt < self.max_attempts:
                    current_delay = min(delay, self.max_delay)
                    logger.info(f"Retrying in {current_delay:.1f} seconds...")
                    time.sleep(current_delay)
                    delay *= self.backoff_factor

        # All attempts failed
        logger.error(
            f"Operation failed after {self.max_attempts} attempts. "
            f"Last error: {last_exception}"
        )
        return False, last_exception


# Convenience function for quick retries
def retry_on_failure(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 5.0,
    *args,
    **kwargs
) -> bool:
    """
    Convenience function for simple retry scenarios.

    Args:
        func: Function to execute
        max_attempts: Maximum attempts
        initial_delay: Initial delay in seconds
        *args: Arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        True if successful, False otherwise
    """
    handler = RetryHandler(max_attempts=max_attempts, initial_delay=initial_delay)
    success, _ = handler.execute_with_retry(func, *args, **kwargs)
    return success
