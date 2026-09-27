"""Connector interfaces.

A connector answers one or more of four questions about an address. Each method
returns None when the connector can't answer (not configured, no match), and the
registry moves on to the next connector in the chain.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import Comp, Neighborhood, PropertyProfile, RentEstimate


class ConnectorError(RuntimeError):
    """Raised when a configured provider fails (HTTP error, bad payload)."""


@runtime_checkable
class PropertyConnector(Protocol):
    name: str
    def available(self) -> bool: ...
    def property_profile(self, address: str) -> PropertyProfile | None: ...


@runtime_checkable
class RentConnector(Protocol):
    name: str
    def available(self) -> bool: ...
    def rent_estimate(self, prop: PropertyProfile) -> RentEstimate | None: ...


@runtime_checkable
class NeighborhoodConnector(Protocol):
    name: str
    def available(self) -> bool: ...
    def neighborhood(self, prop: PropertyProfile) -> Neighborhood | None: ...


@runtime_checkable
class CompsConnector(Protocol):
    name: str
    def available(self) -> bool: ...
    def comps(self, prop: PropertyProfile) -> list[Comp] | None: ...
