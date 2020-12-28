# NDC Dec 2020
# Neil Trimboy 2011
# Assume Python 2.7.x +
#
import sys
import serial
import yaml
import logging
from . import constants
import pkg_resources
config_yml = pkg_resources.resource_string(__name__, "config.yml")

_LOGGER = logging.getLogger(__name__)

#
# Believe this is known as CCITT (0xFFFF)
# This is the CRC function converted directly from the Heatmiser C code
# provided in their API


class CRC16:
    """This is the CRC hashing mechanism used by the V3 protocol."""
    LookupHigh = [
        0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70,
        0x81, 0x91, 0xa1, 0xb1, 0xc1, 0xd1, 0xe1, 0xf1
    ]
    LookupLow = [
        0x00, 0x21, 0x42, 0x63, 0x84, 0xa5, 0xc6, 0xe7,
        0x08, 0x29, 0x4a, 0x6b, 0x8c, 0xad, 0xce, 0xef
    ]

    def __init__(self):
        self.high = constants.BYTEMASK
        self.low = constants.BYTEMASK

    def extract_bits(self, val):
        """Extras the 4 bits, XORS the message data, and does table lookups."""
        # Step one, extract the Most significant 4 bits of the CRC register
        thisval = self.high >> 4
        # XOR in the Message Data into the extracted bits
        thisval = thisval ^ val
        # Shift the CRC Register left 4 bits
        self.high = (self.high << 4) | (self.low >> 4)
        self.high = self.high & constants.BYTEMASK    # force char
        self.low = self.low << 4
        self.low = self.low & constants.BYTEMASK      # force char
        # Do the table lookups and XOR the result into the CRC tables
        self.high = self.high ^ self.LookupHigh[thisval]
        self.high = self.high & constants.BYTEMASK    # force char
        self.low = self.low ^ self.LookupLow[thisval]
        self.low = self.low & constants.BYTEMASK      # force char

    def update(self, val):
        """Updates the CRC value using bitwise operations."""
        self.extract_bits(val >> 4)    # High nibble first
        self.extract_bits(val & 0x0f)   # Low nibble

    def run(self, message):
        """Calculates a CRC"""
        for value in message:
            self.update(value)
        return [self.low, self.high]


class HeatmiserThermostat(object):
    """Initialises a heatmiser thermostat, by taking an address and model."""

    def __init__(self, address, model, uh1):
        
        _LOGGER.debug("Heatmiser Thermostat initialisation")
        self.address = address
        self.model = model
        try:
            self.config = yaml.safe_load(config_yml)[model]
        except yaml.YAMLError as exc:
            _LOGGER.error("The YAML file is invalid: %s", exc)
        self.conn = uh1.registerThermostat(self)
        self.dcb = ""
        # Is there a need to read stat at this point, slows down initialisation
        # comment it out to see
        #self.read_dcb()

    def _hm_form_message(
            self,
            thermostat_id,
            protocol,
            source,
            function,
            start,
            payload
    ):
        """Forms a message payload, excluding CRC"""
        if protocol == constants.HMV3_ID:
            start_low = (start & constants.BYTEMASK)
            start_high = (start >> 8) & constants.BYTEMASK
            if function == constants.FUNC_READ:
                payload_length = 0
                length_low = (constants.RW_LENGTH_ALL & constants.BYTEMASK)
                length_high = (constants.RW_LENGTH_ALL >> 8) & constants.BYTEMASK
            else:
                payload_length = len(payload)
                length_low = (payload_length & constants.BYTEMASK)
                length_high = (payload_length >> 8) & constants.BYTEMASK
            msg = [
                thermostat_id,
                10 + payload_length,
                source,
                function,
                start_low,
                start_high,
                length_low,
                length_high
            ]
            if function == constants.FUNC_WRITE:
                msg = msg + payload
                type(msg)
            return msg
        else:
            assert 0, "Un-supported protocol found %s" % protocol

    def _hm_form_message_crc(
            self,
            thermostat_id,
            protocol,
            source,
            function,
            start,
            payload
    ):
        """Forms a message payload, including CRC"""
        data = self._hm_form_message(
            thermostat_id, protocol, source, function, start, payload)
        crc = CRC16()
        data = data + crc.run(data)
        return data

    def _hm_verify_message_crc_uk(
            self,
            thermostat_id,
            protocol,
            source,
            expectedFunction,
            expectedLength,
            datal
    ):
        """Verifies message appears legal"""
        # expectedLength only used for read msgs as always 7 for write
        
        _LOGGER.debug(f'Verifying message- source: {source}')
        badresponse = 0
        if protocol == constants.HMV3_ID:
            checksum = datal[len(datal) - 2:]
            rxmsg = datal[:len(datal) - 2]
            crc = CRC16()   # Initialises the CRC
            expectedchecksum = crc.run(rxmsg)
            if expectedchecksum == checksum:
                _LOGGER.debug("Correct CRC")
            else:
                _LOGGER.error("Bad CRC")
                serror = "Bad CRC"
                sys.stderr.write(serror)
                badresponse += 1
            dest_addr = datal[0]
            frame_len_l = datal[1]
            frame_len_h = datal[2]
            frame_len = (frame_len_h << 8) | frame_len_l
            source_addr = datal[3]
            func_code = datal[4]

            if (dest_addr != 129 and dest_addr != 160):
                _LOGGER.error("dest_addr is ILLEGAL")
                serror = "Illegal Dest Addr: %s\n" % (dest_addr)
                sys.stderr.write(serror)
                badresponse += 1

            if dest_addr != thermostat_id:
                _LOGGER.error("dest_addr is INCORRECT")
                serror = "Incorrect Dest Addr: %s\n" % (dest_addr)
                sys.stderr.write(serror)
                badresponse += 1

            if (source_addr < 1 or source_addr > 32):
                _LOGGER.error("source_addr is ILLEGAL")
                serror = "Illegal Src Addr: %s\n" % (source_addr)
                sys.stderr.write(serror)
                badresponse += 1

            if source_addr != source:
                _LOGGER.error("source addr is INCORRECT")
                serror = "Incorrect Src Addr: %s\n" % (source_addr)
                sys.stderr.write(serror)
                badresponse += 1

            if (
                func_code != constants.FUNC_WRITE and
                func_code != constants.FUNC_READ
            ):
                _LOGGER.error("Func Code is UNKNWON")
                serror = "Unknown Func Code: %s\n" % (func_code)
                sys.stderr.write(serror)
                badresponse += 1

            if func_code != expectedFunction:
                _LOGGER.error("Func Code is UNEXPECTED")
                serror = "Unexpected Func Code: %s\n" % (func_code)
                sys.stderr.write(serror)
                badresponse += 1

            if (
                    func_code == constants.FUNC_WRITE and frame_len != 7
            ):
                # Reply to Write is always 7 long
                _LOGGER.error("Write length is not 7")
                serror = "Incorrect length: %s\n" % (frame_len)
                sys.stderr.write(serror)
                badresponse += 1

            if len(datal) != frame_len:
                _LOGGER.error("response length MISMATCHES header")
                serror = "Mismatch length: %s %s\n" % (len(datal), frame_len)
                sys.stderr.write(serror)
                badresponse += 1

            # if (func_code == constants.FUNC_READ and
            #   expectedLength !=len(datal) ):
            #   # Read response length is wrong
            #   _LOGGER.error("response length
            #    not EXPECTED value")
            #   _LOGGER.error("Got %s when expecting %s",
            #   len(datal), expectedLength)
            #   _LOGGER.error("Data is:\n %s", datal)
            #   s = "Incorrect length: %s\n" % (frame_len)
            #   sys.stderr.write(s)
            #   badresponse += 1

            if (badresponse == 0):
                return True
            else:
                return False

        else:
            assert 0, "Un-supported protocol found %s" % protocol

    def _hm_send_msg(self, message):
        """This is the only interface to the serial connection."""
        try:
            _LOGGER.debug(f'Sending to serial - length: {len(message)}')
            serial_message = message
            self.conn.write(serial_message)   # Write a string
        except serial.SerialTimeoutException:
            _LOGGER.error("Serial timeout")
            serror = "Write timeout error: \n"
            sys.stderr.write(serror)
        # Now wait for reply
        byteread = self.conn.read(159)
        # NB max return is 75 in 5/2 mode or 159 in 7day mode
        datal = list(byteread)
        _LOGGER.debug(f'Reply read, length {len(datal)}')
        return datal

    def _hm_send_address(self, thermostat_id, address, state, readwrite):
        
        _LOGGER.debug(f'Sending - therm id {thermostat_id} addr {address}, state {state}, R/W {readwrite}')
        protocol = constants.HMV3_ID
        if protocol == constants.HMV3_ID:
            payload = [state]
            msg = self._hm_form_message_crc(
                thermostat_id,
                protocol,
                constants.RW_MASTER_ADDRESS,
                readwrite,
                address,
                payload
            )
        else:
            assert 0, "Un-supported protocol found %s" % protocol
        string = bytes(msg)
        datal = self._hm_send_msg(string)
        pro = protocol
        if readwrite == 1:
            verification = self._hm_verify_message_crc_uk(
                0x81, pro, thermostat_id, readwrite, 1, datal)
            if verification is False:
                _LOGGER.error(f'Verify failed (1) for Therm {thermostat_id}')
            return datal
        else:
            verification = self._hm_verify_message_crc_uk(
                0x81, pro, thermostat_id, readwrite, 75, datal)
            if verification is False:
                _LOGGER.error(f'Verify failed (75) for Therm {thermostat_id}')
            return datal

    def _hm_read_address(self):
        """Reads from the DCB and maps to yaml config file."""
        _LOGGER.debug(f'hm read_address {self.address}')
        response = self._hm_send_address(self.address, 0, 0, 0)
        lookup = self.config['keys']
        offset = self.config['offset']
        keydata = {}
        for i in lookup:
            try:
                
                kdata = lookup[i]
                ddata = response[i + offset]
                #special debug for stat no, target temp, and room temps
                if i in [11,18,29,33]:
                    _LOGGER.debug(f'hm read_address i, kdata, ddata  = {i} {kdata} {ddata}')

                keydata[i] = {
                    'label': kdata,
                    'value': ddata
                }
            except IndexError:
                _LOGGER.error(f'Index error at {i}')
        
        return keydata

    def read_dcb(self):
        """
        Updates DCB by sending message to stat via serial i/f, and then reading reply from stat
        Only use for non read-only operations
        Use self.dcb for read-only operations.
        """
        _LOGGER.debug("hm read_dcb ")
        self.dcb = self._hm_read_address()
        return self.dcb

    def get_frost_temp(self):
        value = self._hm_read_address()[17]['value']
        _LOGGER.debug(f'hm get frost temp {value}')
        return value

    def get_target_temp(self):
        #value = self._hm_read_address()[18]['value']
        value = self.dcb[18]['value']
        _LOGGER.debug(f'hm get target temp {value}')
        return value

    def get_floormax_temp(self):
        value = self._hm_read_address()[19]['value']
        _LOGGER.debug(f'hm get floormax temp {value}')
        return value

    def get_status(self):
        value = self._hm_read_address()[21]['value']
        _LOGGER.debug(f'hm get status {value}')
        return value

    def get_heating(self):
        value = self._hm_read_address()[23]['value']
        _LOGGER.debug(f'hm get heating {value}')
        return value

    def get_thermostat_id(self):
        value = self.dcb[11]['value']
        _LOGGER.debug(f'hm get thermostat id {value}')
        return value

    def get_temperature_format(self):
        value = self.dcb[5]['value']
        _LOGGER.debug(f'hm get temp format {value}')
        if value == 00:
            return "C"
        else:
            return "F"

    def get_sensor_selection(self):
        sensor = self.dcb[13]['value']
        _LOGGER.debug(f'hm get sensor select ={sensor}')
        answers = {
            0: "Built in air sensor",
            1: "Remote air sensor",
            2: "Floor sensor",
            3: "Built in + floor",
            4: "Remote + floor"
        }
        return answers[sensor]

    def get_program_mode(self):
        mode = self.dcb[16]['value']
        _LOGGER.debug(f'hm get prog mode {mode}')
        modes = {
            0: "5/2 mode",
            1: "7 day mode"
        }
        return modes[mode]

    #tbc why is this null?    
    def get_frost_protection(self):
        pass

    # tbc - does this need to return 2 byte value
    def get_floor_temp(self):
        value = self.dcb[31]['value'] / 10
        _LOGGER.debug(f'hm get floor temp {value}')
        return value

    def get_sensor_error(self):
        value = self.dcb[34]['value']
        _LOGGER.debug(f'hm get sensor error {value}')
        return value

    def get_current_state(self):
        value = self.dcb[35]['value']
        _LOGGER.debug(f'hm get current state {value}')
        return value

    def set_frost_protect_mode(self, onoff):
        _LOGGER.debug(f'hm set frost protect mode {onoff}')
        self._hm_send_address(self.address, 23, onoff, 1)
        return True

    def set_frost_protect_temp(self, frost_temp):
        _LOGGER.debug(f'Set frost temp {frost_temp}')
        if 17 < frost_temp < 7:
            _LOGGER.error("Atempt to set bad frost tempe %s ", frost_temp)
            return False
        else:
            self._hm_send_address(self.address, 17, frost_temp, 1)
            return True

    def set_target_temp(self, temperature):
        _LOGGER.debug(f'hm set target temp {temperature}')
        if 35 < temperature < 5:
            _LOGGER.error(f'Attempt to set bad target temp {temperature}')
            return False
        else:
            self._hm_send_address(self.address, 18, temperature, 1)
            return True

    def set_floormax_temp(self, floor_max):
        _LOGGER.debug(f'hm set floormax temp {floor_max}')
        if 45 < floor_max < 20:
            _LOGGER.error(f'Attempt to set bad floormax temp {floor_max}')
            return False
        else:
            self._hm_send_address(self.address, 19, floor_max, 1)
            return True
