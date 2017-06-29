"""
Interfaces with Sector Alarm alarm control panel.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/alarm_control_panel.sectoralarm/
"""
import logging

import homeassistant.components.alarm_control_panel as alarm
from custom_components.sectoralarm import HUB as hub
from custom_components.sectoralarm import (CONF_ALARM, CONF_CODE_DIGITS)
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY, STATE_ALARM_ARMED_HOME, STATE_ALARM_DISARMED,
    STATE_UNKNOWN)

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Sector Alarm platform."""
    alarms = []
    if int(hub.config.get(CONF_ALARM, 1)):
        hub.update_alarms()
        alarms.append(SectorAlarmAlarm())
    add_devices(alarms)


class SectorAlarmAlarm(alarm.AlarmControlPanel):
    """Representation of a Sector Alarm alarm status."""

    def __init__(self):
        """Initialize the Sector Alarm alarm panel."""
        self._state = STATE_UNKNOWN
        self._digits = hub.config.get(CONF_CODE_DIGITS)
        self._changed_by = None

    @property
    def name(self):
        """Return the name of the device."""
        return 'Alarm 0'

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def code_format(self):
        """Return the code format as regex."""
        return '^\\d{%s}$' % self._digits

    @property
    def changed_by(self):
        """Return the last change triggered by."""
        return self._changed_by

    @property
    def changed_at(self):
        """Return the last change triggered by."""
        return self._changed_at

    def update(self):
        """Update alarm status."""
        hub.update_alarms()

        if hub.alarm_status[0]['message'] == 'disarmed':
            self._state = STATE_ALARM_DISARMED
        elif hub.alarm_status[0]['message'] == 'armedhome':
            self._state = STATE_ALARM_ARMED_HOME
        elif hub.alarm_status[0]['message'] == 'armed':
            self._state = STATE_ALARM_ARMED_AWAY
        elif hub.alarm_status[0]['message'] != 'pending':
            _LOGGER.error(
                "Unknown alarm state %s", hub.alarm_status[self._id].status)
        self._changed_by = hub.alarm_status[0]['user']
        self._changed_at = hub.alarm_status[0]['timeex']

    def alarm_disarm(self, code=None):
        """Send disarm command."""
        hub.my_pages.alarm.set(code, 'DISARMED')
        _LOGGER.info("Verisure alarm disarming")
        hub.my_pages.alarm.wait_while_pending()

    def alarm_arm_home(self, code=None):
        """Send arm home command."""
        hub.my_pages.alarm.set(code, 'ARMED_HOME')
        _LOGGER.info("Verisure alarm arming home")
        hub.my_pages.alarm.wait_while_pending()

    def alarm_arm_away(self, code=None):
        """Send arm away command."""
        hub.my_pages.alarm.set(code, 'ARMED_AWAY')
        _LOGGER.info("Verisure alarm arming away")
        hub.my_pages.alarm.wait_while_pending()
