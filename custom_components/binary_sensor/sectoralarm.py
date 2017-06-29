"""
Interfaces with Sector Alarm sensors.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/binary_sensor.sectoralarm/
"""
import logging

from custom_components.sectoralarm import HUB as hub
from custom_components.sectoralarm import (CONF_ALARM)
from homeassistant.components.binary_sensor import BinarySensorDevice

_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup Sensor Alarm binary sensors."""
    sensors = []
    if int(hub.config.get(CONF_ALARM, 1)):
        sensors.extend([SectorAlarmEthernetSensor()])
    add_devices(sensors)

class SectorAlarmEthernetSensor(BinarySensorDevice):
    """Securitas Alarm ethernet connectivity."""

    def __init__(self):
        """Initialize the binary sensor."""
        self._state = None

    @property
    def name(self):
        """Return the name of the binary sensor."""
        return 'Alarm 0 - Ethernet connectivity'

    @property
    def is_on(self):
        """Return the state of the sensor."""
        return self._state == 'online'

    def update(self):
        """Update the state of the sensor."""
        hub.update_ethernet()
        self._state = hub.ethernet_status[0]['ethernetStatus']
