"""Independent telemetry providers."""
import logging

LOG = logging.getLogger(__name__)


class Provider:
    def close(self):
        """Release resources in the sampling worker."""

    def cancel(self):
        """Request cancellation without waiting on a blocking query."""


class WindowsRemoteProvider(Provider):
    def sample(self):
        raise NotImplementedError("Remote Windows telemetry is planned")
