"""
Interfaces with Sector Alarm locks.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sectoralarm/
"""
import logging
from time import sleep
from time import time
from custom_components.sectoralarm import HUB as hub
from custom_components.sectoralarm import (CONF_LOCKS, CONF_CODE_DIGITS)
from homeassistant.components.lock import LockDevice
from homeassistant.const import (
    ATTR_CODE, STATE_LOCKED, STATE_UNKNOWN, STATE_UNLOCKED)

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Sector Alarm platform."""
    locks = []
    if int(hub.config.get(CONF_LOCKS, 1)):
        hub.update_locks()
        locks.extend([
            SectorAlarmDoorlock(device_id)
            for device_id in hub.lock_status.keys()
        ])

    add_devices(locks)

class SectorAlarmDoorlock(LockDevice):
    """Representation of a Sector Alarm doorlock."""

    def __init__(self, device_id):
        """Initialize the lock."""
        self._id = device_id
        self._state = STATE_UNKNOWN
        self._digits = hub.config.get(CONF_CODE_DIGITS)
        self._label = hub.lock_status[self._id]['Label']

    @property
    def name(self):
        """Return the name of the lock."""
        return self._label

    @property
    def state(self):
        """Return the state of the lock."""
        return self._state

    @property
    def code_format(self):
        """Return the required six digit code."""
        return '^\\d{%s}$' % self._digits

    @property
    def is_locked(self):
        """Return true if lock is locked."""
        return hub.lock_status[self._id].status

    def update(self):
        """Update lock status."""
        hub.update_locks()

        if hub.lock_status[self._id]['Status'] == 'unlock':
            self._state = STATE_UNLOCKED
        elif hub.lock_status[self._id]['Status'] == 'lock':
            self._state = STATE_LOCKED
        elif hub.lock_status[self._id]['Status'] != 'pending':
            _LOGGER.error(
                'Unknown lock state %s',
                hub.lock_status[self._id]['Status'])

