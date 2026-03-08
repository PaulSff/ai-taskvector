"""Thermodynamic units: Source, Valve, Tank, Sensor. Each unit lives in its own folder with a README."""

from units.thermodynamic.source import register_source
from units.thermodynamic.valve import register_valve
from units.thermodynamic.tank import register_tank
from units.thermodynamic.sensor import register_sensor


def register_thermodynamic_units() -> None:
    """Register Source, Valve, Tank, Sensor. Canonical units are env-agnostic (see units.register_env_agnostic)."""
    from units.registry import UNIT_REGISTRY

    register_source()
    register_valve()
    register_tank()
    register_sensor()
    for name in ("Source", "Valve", "Tank", "Sensor"):
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["thermodynamic"]


from units.env_loaders import register_env_loader

register_env_loader("thermodynamic", register_thermodynamic_units)

__all__ = ["register_thermodynamic_units"]
