"""
Support for Sector Alarm component.
For more details about this component, please refer to the documentation at
https://home-assistant.io/components/sectoralarm/
"""
import logging
import threading
from datetime import timedelta
import voluptuous as vol

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import discovery
from homeassistant.util import Throttle
import homeassistant.config as conf_util
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = [
    'https://github.com/petterl/python-sectoralarm'
    '/archive/3c4f557823997df3657168f1b0a6e1e7f384b0e9.zip'
    '#python-sectoralarm==1.0.0']
_LOGGER = logging.getLogger(__name__)

CONF_ALARM = 'alarm'
CONF_LOCKS = 'locks'
CONF_THERMOMETERS = 'temperature'
CONF_PANEL = 'panel'
CONF_CODE_DIGITS = 'code_digits'

DOMAIN = 'sectoralarm'
HUB = None

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PANEL): cv.string,
        vol.Optional(CONF_ALARM, default=True): cv.boolean,
        vol.Optional(CONF_LOCKS, default=True): cv.boolean,
        vol.Optional(CONF_THERMOMETERS, default=True): cv.boolean,
        vol.Optional(CONF_CODE_DIGITS, default=6): cv.positive_int,
    }),
}, extra=vol.ALLOW_EXTRA)

def setup(hass, config):
    """Set up the Sector Alarm component."""
    import sectoralarm
    global HUB
    HUB = SectorAlarmHub(config[DOMAIN], sectoralarm)

    for component in ('alarm_control_panel', 'binary_sensor', 'lock', 'sensor'):
        discovery.load_platform(hass, component, DOMAIN, {}, config)

    return True

class SectorAlarmHub(object):
    """A SectorAlarm hub wrapper class."""

    def __init__(self, domain_config, sectoralarm):
        """Initialize the Sector Alarm hub."""
        self.alarm_status = {}
        self.ethernet_status = {}
        self.lock_status = {}
        self.temperature_status = {}
        self.smartplug_status = {}

        self.config = domain_config
        self._sectoralarm = sectoralarm

        self._lock = threading.Lock()

        self.session = sectoralarm.Session(
            domain_config[CONF_USERNAME],
            domain_config[CONF_PASSWORD],
            domain_config[CONF_PANEL])

    @Throttle(timedelta(seconds=1))
    def update_alarms(self):
        """Update the status of the alarm."""
        self.alarm_status[0] = self.session.get_arm_state()

    @Throttle(timedelta(seconds=1))
    def update_ethernet(self):
        """Update the status of the alarm."""
        self.ethernet_status[0] = self.session.get_ethernet_status()

    @Throttle(timedelta(seconds=1))
    def update_locks(self):
        """Update the status of the locks."""
        for lock in self.session.get_lock_status()['DoorlockStatusList']:
            self.lock_status[lock['Serial']] = lock

    @Throttle(timedelta(seconds=1))
    def update_temperature(self):
        """Update the status of the temperature sensors."""
        for device in self.session.get_temperature(None)['temperatureComponentList']:
            self.temperature_status[device['serialNo']] = device
        _LOGGER.error(self.temperature_status)

