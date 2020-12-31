"""This module is effectively a singleton for serial comms"""
import serial
import logging
from . import constants
from . import heatmiser
import asyncio
import serial_asyncio

_LOGGER = logging.getLogger(__name__)

class HeatmiserUH1(object):
    """
    Represents the UH1 interface that holds the serial
    connection, and can have multiple thermostats
    """

    def __init__(self, ipaddress, port):
        _LOGGER.info(f'Initialising interface {ipaddress} : {port}')
        self.thermostats = {}
        self._serport = serial.serial_for_url("socket://" + ipaddress + ":" + port)
        # Ensures that the serial port has not
        # been left hanging around by a previous process.
        serport_response = self._serport.close()
        _LOGGER.debug(f'SerialPortResponse: {serport_response}')
        self._serport.baudrate = constants.COM_BAUD
        self._serport.bytesize = constants.COM_SIZE
        self._serport.parity = constants.COM_PARITY
        self._serport.stopbits = constants.COM_STOP
        self._serport.timeout = constants.COM_TIMEOUT
        self.status = False
        self._open()

    def _open(self):
        if not self.status:
            _LOGGER.debug("Opening serial port.")
            self._serport.open()
            self.status = True
            _LOGGER.debug("Opened serial port OK")
            return True
        else:
            _LOGGER.error("Attempting to access already open port")
            return False

    def reopen(self):
        if not self.status:
            _LOGGER.debug("Re-opening serial port.")
            self._serport.open()
            self.status = True
            return self.status
        else:
            _LOGGER.error("Cannot open serial port")

    def __del__(self):
        _LOGGER.debug("Closing serial port.")
        self._serport.close()

    def registerThermostat(self, thermostat):
        """Registers a thermostat with the UH1"""
        try:
            type(thermostat) == heatmiser.HeatmiserThermostat
            if thermostat.address in self.thermostats.keys():
                raise ValueError("Key already present")
            else:
                self.thermostats[thermostat.address] = thermostat
                _LOGGER.debug(f'Register Thermostat addr {thermostat.address}  ')
        except ValueError:
            pass
        except Exception as err:
            _LOGGER.error(f'Not a HeatmiiserThermostat Object {err}')
        return self._serport

    def listThermostats(self):
        if self.thermostats:
            return self.thermostats
        else:
            return None
