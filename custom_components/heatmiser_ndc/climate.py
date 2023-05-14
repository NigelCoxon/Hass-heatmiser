"""
  Home Assistant component to access PRT Heatmiser themostats using the V3 protocol
  via the heatmiser library
"""

# Dec 2020 NDC version
# In this code, we will not access the dcb directly (as other versions have done)
# We let the library decode and access the dcb fields

import logging
from typing import List

import threading
sema = threading.Semaphore(1)

from . import heatmiser
import voluptuous as vol

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import (
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    HVAC_MODE_AUTO,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_HUMIDITY
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_HOST,
    CONF_ID,
    CONF_NAME,
    CONF_PORT,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    PRECISION_WHOLE,
)

import homeassistant.helpers.config_validation as cv
_LOGGER = logging.getLogger(__name__)

DOMAIN = "heatmiser_ndc"
CONF_THERMOSTATS = "tstats"

TSTAT_SCHEMA = vol.Schema(
    {vol.Required(CONF_ID): vol.Range(1, 32),
     vol.Required(CONF_NAME): cv.string, }
)

TSTATS_SCHEMA = vol.All(cv.ensure_list, [TSTAT_SCHEMA])

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.port,
        vol.Required(CONF_THERMOSTATS, default=[]): TSTATS_SCHEMA,
    }
)

COMPONENT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.port,
        vol.Required(CONF_THERMOSTATS): TSTATS_SCHEMA,
    }
)
CONFIG_SCHEMA = vol.Schema({DOMAIN: COMPONENT_SCHEMA}, extra=vol.ALLOW_EXTRA)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the heatmiser thermostat."""
    _LOGGER.info("Setting up platform")
    statobject = heatmiser.HeatmiserStat

    host = config[CONF_HOST]
    port = str(config.get(CONF_PORT))
    statlist = config[CONF_THERMOSTATS]
    uh1_hub = heatmiser.HM_UH1(host, port)

    # Add all entities - True in call requests update before adding
    # necessary to setup the dcb fields
    add_entities([HMV3Stat(statobject, stat, uh1_hub)
                  for stat in statlist], True, )

    _LOGGER.info("Platform setup complete")


class HMV3Stat(ClimateEntity):
    """Representation of a HeatmiserV3 thermostat."""

    def __init__(self, therm, device, uh1):
        """Initialize the thermostat."""

        self.therm = therm(device[CONF_ID], "prt", uh1)
        self._name = device[CONF_NAME]
        _LOGGER.info(f'Initialised thermostat {self._name}')
        _LOGGER.debug(f'Init uh1 = {uh1}')

    @property
    def supported_features(self):
        result = SUPPORT_TARGET_TEMPERATURE + SUPPORT_TARGET_HUMIDITY
        _LOGGER.debug(f'supported features returning {result}')
        return result

    @property
    def name(self):
        _LOGGER.debug(f'name returning {self._name}')
        return self._name

    @property
    def unique_id(self):
        _stat = self.therm.get_thermostat_id()
        _id = f"Heatmiser Prt {_stat}"
        _LOGGER.debug(f'unique_id returning {_id}')
        return _id
        
    @property
    def temperature_unit(self):

        _temp_format = self.therm.get_temperature_format()
        value = TEMP_CELSIUS if (_temp_format == 0) else TEMP_FAHRENHEIT
        _LOGGER.debug(f'temperature unit returning {value}')
        return value

    @property
    def hvac_mode(self) -> str:
        # Returns Hvac mode - Off / Auto / Heat
        # stat has frost protect on/off and heat state on/off
        # we map frost protect to hvac mode off
        _run_mode=self.therm.get_run_mode()
        _heat_state =self.therm.get_heat_state()
        if _run_mode == 1:   #frost protect
            value = HVAC_MODE_OFF
        elif _heat_state == 0:  # not heating
            value = HVAC_MODE_AUTO
        else:
            value = HVAC_MODE_HEAT
        _LOGGER.debug(f'hvac mode returning {value}')
        return value

    def set_hvac_mode(self, hvac_mode):
        # If Off , set stat to frost protect mode
        # If Heat or Auto, set stat to normal
        _LOGGER.debug(f'set hvac mode to {hvac_mode}')
        if hvac_mode == HVAC_MODE_OFF:
            self.therm.set_run_mode(1)
        else:
            self.therm.set_run_mode(0)

    def turn_off(self):
        """Turn off the stat"""
        _LOGGER.debug(f'turn off called')
        self.set_hvac_mode(HVAC_MODE_OFF)

    def turn_on(self):
        """Turn on the zone"""
        _LOGGER.debug(f'turn on called')
        self.set_hvac_mode(HVAC_MODE_AUTO)

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        _LOGGER.debug(f'target temp step returning {PRECISION_WHOLE}')
        return PRECISION_WHOLE

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        _LOGGER.debug(f'min temp returning 5')
        return 5

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        _LOGGER.debug(f'max temp returning 35')
        return 35

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes"""
        # Need to be a subset of HVAC_MODES.
        
        result = [HVAC_MODE_HEAT, HVAC_MODE_OFF, HVAC_MODE_AUTO]
        _LOGGER.debug(f'hvac modes returning {result}')
        return result

    @property
    def current_temperature(self):
        """Return the current temperature depending on sensor select"""
        temp = self.therm.get_current_temp()
        _LOGGER.debug(f'Current temperature returned {temp}')
        return (temp)

    @property
    def target_temperature(self):
        temp = self.therm.get_target_temp()
        _LOGGER.debug(f'Target temp returned {temp}')
        return temp

    @property
    def min_humidity(self):
        """Return the minimum humidity."""
        _LOGGER.debug(f'min humidity returning 7')
        return 7

    @property
    def max_humidity(self):
        """Return the maximum humidity."""
        _LOGGER.debug(f'max humidity returning 17')
        return 17

    @property
    def current_humidity(self):
        """Return the current humidity."""
        # same as target humidity
        temp = self.therm.get_frost_temp()
        _LOGGER.debug(f'Current humidity returned {temp}')
        return temp

    @property
    def target_humidity(self):
        """Return the target humidity """
        temp = self.therm.get_frost_temp()
        _LOGGER.debug(f'Target humidity returned {temp}')
        return temp

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        _LOGGER.debug(f'Set target temp: {temperature}')

        try:
            self._target_temperature = int(temperature)
            self.therm.set_target_temp(self._target_temperature)
        except ValueError as err:
            _LOGGER.error(
                f'Error - Set Temperature exception {err} for {self._name}')

    def set_humidity(self, humidity):
        """Set new target humidity."""
        _hum = int(humidity) 
        _LOGGER.debug(f'set humidity to {_hum}')
        self.therm.set_frost_temp(_hum)
        
    def update(self):
        """Get the latest data."""
        _LOGGER.debug(f'Update started for {self._name}')

        try:
            sema.acquire()
            self.therm.read_dcb()
            sema.release()
        except ValueError as err:
            _LOGGER.error(f'Error - Update exception {err} for {self._name}')
        _LOGGER.debug(f'Update done')
