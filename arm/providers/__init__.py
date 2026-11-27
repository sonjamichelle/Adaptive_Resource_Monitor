# Adaptive Resource Monitor
# Original developer: Sonja M Thomas
# Copyright 2010-2026 SLT Design Creations, LLC
# Licensed under the Design Creations Attribution-NonCommercial-ShareAlike License v1.0.
# See LICENSE.md for complete license terms.
# https://www.designcreations.us/

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
