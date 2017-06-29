"""
Interfaces with Sector Alarm sensors.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.sectoralarm/
"""
import logging

from custom_components.sectoralarm import HUB as hub
from custom_components.sectoralarm import (CONF_THERMOMETERS)
from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Sector Alarm platform."""
    sensors = []

    if int(hub.config.get(CONF_THERMOMETERS, 1)):
        hub.update_temperature()
        sensors.extend([
            SectorAlarmThermometer(value['serialNo'])
            for value in hub.temperature_status.values()
            ])

    _LOGGER.error(sensors)
    add_devices(sensors)


class SectorAlarmThermometer(Entity):
    """Representation of a Verisure thermometer."""

    def __init__(self, device_id):
        """Initialize the sensor."""
        self._id = device_id

    @property
    def name(self):
        """Return the name of the device."""
        return '{} {}'.format(
            hub.temperature_status[self._id]['label'], 'Temperature')

    @property
    def state(self):
        """Return the state of the device."""
        return hub.temperature_status[self._id]['temperature']

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity."""
        return TEMP_CELSIUS


    def update(self):
        """Update the sensor."""
        hub.update_temperature()

