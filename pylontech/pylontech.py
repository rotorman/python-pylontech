from typing import Dict
import logging
import serial
import construct

logger = logging.getLogger(__name__)

class HexToByte(construct.Adapter):
    def _decode(self, obj, context, path) -> bytes:
        hexstr = ''.join([chr(x) for x in obj])
        return bytes.fromhex(hexstr)


class JoinBytes(construct.Adapter):
    def _decode(self, obj, context, path) -> bytes:
        return ''.join([chr(x) for x in obj]).encode()


class DivideBy1000(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 1000


class DivideBy100(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 100

class DivideBy10(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 10

class ToVolt(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 1000

class ToAmp(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return obj / 10

class ToCelsius(construct.Adapter):
    def _decode(self, obj, context, path) -> float:
        return (obj - 2731) / 10.0  # in Kelvin*10



class Pylontech:
    manufacturer_info_fmt = construct.Struct(
        "DeviceName" / JoinBytes(construct.Array(10, construct.Byte)),
        "SoftwareVersion" / construct.Array(2, construct.Byte),
        "ManufacturerName" / JoinBytes(construct.GreedyRange(construct.Byte)),
    )

    system_parameters_fmt = construct.Struct(
        "CellHighVoltageLimit" / ToVolt(construct.Int16ub),
        "CellLowVoltageLimit" / ToVolt(construct.Int16ub),
        "CellUnderVoltageLimit" / ToVolt(construct.Int16sb),
        "ChargeHighTemperatureLimit" / ToCelsius(construct.Int16sb),
        "ChargeLowTemperatureLimit" / ToCelsius(construct.Int16sb),
        "ChargeCurrentLimit" / DivideBy10(construct.Int16sb),
        "ModuleHighVoltageLimit" / ToVolt(construct.Int16ub),
        "ModuleLowVoltageLimit" / ToVolt(construct.Int16ub),
        "ModuleUnderVoltageLimit" / ToVolt(construct.Int16ub),
        "DischargeHighTemperatureLimit" / ToCelsius(construct.Int16sb),
        "DischargeLowTemperatureLimit" / ToCelsius(construct.Int16sb),
        "DischargeCurrentLimit" / DivideBy10(construct.Int16sb),
    )

    management_info_fmt = construct.Struct(
        "ChargeVoltageLimit" / DivideBy1000(construct.Int16sb),
        "DischargeVoltageLimit" / DivideBy1000(construct.Int16sb),
        "ChargeCurrentLimit" / ToAmp(construct.Int16sb),
        "DischargeCurrentLimit" / ToAmp(construct.Int16sb),
        "status"
        / construct.BitStruct(
            "ChargeEnable" / construct.Flag,
            "DischargeEnable" / construct.Flag,
            "ChargeImmediately2" / construct.Flag,
            "ChargeImmediately1" / construct.Flag,
            "FullChargeRequest" / construct.Flag,
            "ShouldCharge"
            / construct.Computed(
                lambda this: this.ChargeImmediately2
                | this.ChargeImmediately1
                | this.FullChargeRequest
            ),
            "_padding" / construct.BitsInteger(3),
        ),
    )

    module_serial_number_fmt = construct.Struct(
        "CommandValue" / construct.Byte,
        "ModuleSerialNumber" / JoinBytes(construct.Array(16, construct.Byte)),
    )

    get_values_fmt = construct.Struct(
        "NumberOfModules" / construct.Byte,
        "Module" / construct.Array(construct.this.NumberOfModules, construct.Struct(
            "NumberOfCells" / construct.Int8ub,
            "CellVoltages" / construct.Array(construct.this.NumberOfCells, ToVolt(construct.Int16sb)),
            "NumberOfTemperatures" / construct.Int8ub,
            "AverageBMSTemperature" / ToCelsius(construct.Int16sb),
            "GroupedCellsTemperatures" / construct.Array(construct.this.NumberOfTemperatures - 1, ToCelsius(construct.Int16sb)),
            "Current" / ToAmp(construct.Int16sb),
            "Voltage" / ToVolt(construct.Int16ub),
            "Power" / construct.Computed(construct.this.Current * construct.this.Voltage),
            "_RemainingCapacity1" / DivideBy1000(construct.Int16ub),
            "_UserDefinedItems" / construct.Int8ub,
            "_TotalCapacity1" / DivideBy1000(construct.Int16ub),
            "CycleNumber" / construct.Int16ub,
            "_OptionalFields" / construct.If(construct.this._UserDefinedItems > 2,
                                           construct.Struct("RemainingCapacity2" / DivideBy1000(construct.Int24ub),
                                                            "TotalCapacity2" / DivideBy1000(construct.Int24ub))),
            "RemainingCapacity" / construct.Computed(lambda this: this._OptionalFields.RemainingCapacity2 if this._UserDefinedItems > 2 else this._RemainingCapacity1),
            "TotalCapacity" / construct.Computed(lambda this: this._OptionalFields.TotalCapacity2 if this._UserDefinedItems > 2 else this._TotalCapacity1),
        )),
        "TotalPower" / construct.Computed(lambda this: sum([x.Power for x in this.Module])),
        "StateOfCharge" / construct.Computed(lambda this: sum([x.RemainingCapacity for x in this.Module]) / sum([x.TotalCapacity for x in this.Module])),

    )
    get_values_single_fmt = construct.Struct(
        "NumberOfModule" / construct.Byte,
        "NumberOfCells" / construct.Int8ub,
        "CellVoltages" / construct.Array(construct.this.NumberOfCells, ToVolt(construct.Int16sb)),
        "NumberOfTemperatures" / construct.Int8ub,
        "AverageBMSTemperature" / ToCelsius(construct.Int16sb),
        "GroupedCellsTemperatures" / construct.Array(construct.this.NumberOfTemperatures - 1, ToCelsius(construct.Int16sb)),
        "Current" / ToAmp(construct.Int16sb),
        "Voltage" / ToVolt(construct.Int16ub),
        "Power" / construct.Computed(construct.this.Current * construct.this.Voltage),
        "_RemainingCapacity1" / DivideBy1000(construct.Int16ub),
        "_UserDefinedItems" / construct.Int8ub,
        "_TotalCapacity1" / DivideBy1000(construct.Int16ub),
        "CycleNumber" / construct.Int16ub,
        "_OptionalFields" / construct.If(construct.this._UserDefinedItems > 2,
                                       construct.Struct("RemainingCapacity2" / DivideBy1000(construct.Int24ub),
                                                        "TotalCapacity2" / DivideBy1000(construct.Int24ub))),
        "RemainingCapacity" / construct.Computed(lambda this: this._OptionalFields.RemainingCapacity2 if this._UserDefinedItems > 2 else this._RemainingCapacity1),
        "TotalCapacity" / construct.Computed(lambda this: this._OptionalFields.TotalCapacity2 if this._UserDefinedItems > 2 else this._TotalCapacity1),
        "TotalPower" / construct.Computed(construct.this.Power),
        "StateOfCharge" / construct.Computed(construct.this.RemainingCapacity / construct.this.TotalCapacity),
    )

    def __init__(self, serial_port='/dev/ttyUSB0', baudrate=115200):
        self.s = serial.Serial(serial_port, baudrate, bytesize=8, parity=serial.PARITY_NONE, stopbits=1, timeout=2)


    @staticmethod
    def get_frame_checksum(frame: bytes):
        assert isinstance(frame, bytes)

        sum = 0
        for byte in frame:
            sum += byte
        sum = ~sum
        sum %= 0x10000
        sum += 1
        return sum

    @staticmethod
    def get_info_length(info: bytes) -> int:
        lenid = len(info)
        if lenid == 0:
            return 0

        lenid_sum = (lenid & 0xf) + ((lenid >> 4) & 0xf) + ((lenid >> 8) & 0xf)
        lenid_modulo = lenid_sum % 16
        lenid_invert_plus_one = 0b1111 - lenid_modulo + 1

        return (lenid_invert_plus_one << 12) + lenid


    def send_cmd(self, address: int, cmd, info: bytes = b''):
        raw_frame = self._encode_cmd(address, cmd, info)
        self.s.write(raw_frame)


    def _encode_cmd(self, address: int, cid2: int, info: bytes = b''):
        cid1 = 0x46

        info_length = Pylontech.get_info_length(info)

        frame = "{:02X}{:02X}{:02X}{:02X}{:04X}".format(0x20, address, cid1, cid2, info_length).encode()
        frame += info

        frame_chksum = Pylontech.get_frame_checksum(frame)
        whole_frame = (b"~" + frame + "{:04X}".format(frame_chksum).encode() + b"\r")
        return whole_frame


    def _decode_hw_frame(self, raw_frame: bytes) -> bytes:
        # XXX construct
        frame_data = raw_frame[1:len(raw_frame) - 5]
        frame_chksum = raw_frame[len(raw_frame) - 5:-1]

        got_frame_checksum = Pylontech.get_frame_checksum(frame_data)
        assert got_frame_checksum == int(frame_chksum, 16)

        return frame_data

    def _decode_frame(self, frame):
        format = construct.Struct(
            "ver" / HexToByte(construct.Array(2, construct.Byte)),
            "adr" / HexToByte(construct.Array(2, construct.Byte)),
            "cid1" / HexToByte(construct.Array(2, construct.Byte)),
            "cid2" / HexToByte(construct.Array(2, construct.Byte)),
            "infolength" / HexToByte(construct.Array(4, construct.Byte)),
            "info" / HexToByte(construct.GreedyRange(construct.Byte)),
        )

        return format.parse(frame)


    def read_frame(self):
        raw_frame = self.s.readline()
        f = self._decode_hw_frame(raw_frame=raw_frame)
        parsed = self._decode_frame(f)
        return parsed


    def scan_for_batteries(self, start=0, end=255) -> Dict[int, str]:
        """ Returns a map of the batteries id to their serial number """
        batteries = {}
        for adr in range(start, end, 1):
            bdevid = "{:02X}".format(adr).encode()
            self.send_cmd(adr, 0x93, bdevid) # Probe for serial number
            raw_frame = self.s.readline()

            if raw_frame:
                sn = self.get_module_serial_number(adr)
                sn_str = sn["ModuleSerialNumber"].decode()

                batteries[adr] = sn_str
                logger.debug("Found battery at address " + str(adr) + " with serial " + sn_str)
            else:
                logger.debug("No battery found at address " + str(adr))

        return batteries


    def get_protocol_version(self):
        self.send_cmd(0, 0x4f)
        return self.read_frame()


    def get_manufacturer_info(self):
        self.send_cmd(0, 0x51)
        f = self.read_frame()
        return self.manufacturer_info_fmt.parse(f.info)


    def get_system_parameters(self, dev_id=None):
        if dev_id:
            bdevid = "{:02X}".format(dev_id).encode()
            self.send_cmd(dev_id, 0x47, bdevid)
        else:
            self.send_cmd(2, 0x47)

        f = self.read_frame()
        return self.system_parameters_fmt.parse(f.info[1:])

    def get_management_info(self, dev_id):
        bdevid = "{:02X}".format(dev_id).encode()
        self.send_cmd(dev_id, 0x92, bdevid)
        f = self.read_frame()

        print(f.info)
        print(len(f.info))
        ff = self.management_info_fmt.parse(f.info[1:])
        print(ff)
        return ff

    def get_module_serial_number(self, dev_id=None):
        if dev_id:
            bdevid = "{:02X}".format(dev_id).encode()
            self.send_cmd(dev_id, 0x93, bdevid)
        else:
            self.send_cmd(2, 0x93)

        f = self.read_frame()
        # infoflag = f.info[0]
        return self.module_serial_number_fmt.parse(f.info[0:])

    def get_values(self):
        self.send_cmd(2, 0x42, b'FF')
        f = self.read_frame()

        # infoflag = f.info[0]
        d = self.get_values_fmt.parse(f.info[1:])
        return d

    def get_values_single(self, dev_id):
        bdevid = "{:02X}".format(dev_id).encode()
        self.send_cmd(dev_id, 0x42, bdevid)
        f = self.read_frame()
        # infoflag = f.info[0]
        d = self.get_values_single_fmt.parse(f.info[1:])
        return d


if __name__ == '__main__':
    p = Pylontech()
    # print(p.get_protocol_version())
    # print(p.get_manufacturer_info())
    # print(p.get_system_parameters())
    # print(p.get_management_info())
    # print(p.get_module_serial_number())
    # print(p.get_values())
    print(p.get_values_single(2))
