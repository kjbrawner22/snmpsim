#
# This file is part of snmpsim software.
#
# Copyright (c) 2010-2019, Ilya Etingof <etingof@gmail.com>
# License: https://www.pysnmp.com/snmpsim/license.html
#
import re

from pyasn1.codec.ber import encoder
from pyasn1.compat.octets import octs2str
from pyasn1.type import univ
from pysnmp.proto import rfc1902

from snmpsim import error
from snmpsim.grammar import abstract


class WalkGrammar(abstract.AbstractGrammar):
    # case-insensitive keys as snmpwalk output tend to vary
    TAG_MAP = {
        'OID:': rfc1902.ObjectName,
        'NULL:': univ.Null,
        'INTEGER:': rfc1902.Integer,
        'STRING:': rfc1902.OctetString,
        'BITS:': rfc1902.Bits,
        'HEX-STRING:': rfc1902.OctetString,
        'GAUGE32:': rfc1902.Gauge32,
        'COUNTER32:': rfc1902.Counter32,
        'COUNTER64:': rfc1902.Counter64,
        'IPADDRESS:': rfc1902.IpAddress,
        'OPAQUE:': rfc1902.Opaque,
        'UNSIGNED32:': rfc1902.Unsigned32,  # this is not needed
        'TIMETICKS:': rfc1902.TimeTicks  # this is made up
    }

    @staticmethod
    def _integer_filter(value):
        try:
            int(value)
            return value

        except ValueError:
            # Clean enumeration values
            # .1.3.6.1.2.1.2.2.1.3.1 = INTEGER: ethernetCsmacd(6)
            match = re.match(r'.*?\((\-?[0-9]+)\)', value)
            if match:
                return match.group(1)

            # Clean values with UNIT suffix
            # .1.3.6.1.2.1.4.13.0 = INTEGER: 60 seconds
            match = re.match(r'(\-?[0-9]+)\s.+', value)
            if match:
                return match.group(1)

            return value

    # possible DISPLAY-HINTs parsing should occur here
    @staticmethod
    def _string_filter(value):
        if not value:
            return value

        elif value[0] == value[-1] == '"':
            return value[1:-1]

        # .1.3.6.1.2.1.2.2.1.6.201752832 = STRING: 60:9c:9f:ec:a3:38
        elif re.match(r'^[0-9a-fA-F]{1,2}(\:[0-9a-fA-F]{1,2})+$', value):
            return [int(x, 16) for x in value.split(':')]

        else:
            return value

    @staticmethod
    def _opaque_filter(value):
        opaque_tag = ''
        match = re.match(r'^(\w+: +)', value)
        if match:
            opaque_tag = match.group(1).upper()
            value = value[len(opaque_tag):]

        if opaque_tag.startswith('FLOAT: '):
            # .1.3.6.1.4.1.6574.4.3.1.1.0 = Opaque: Float: 100.000000
            return encoder.encode(univ.Real(float(value[7:])))

        elif opaque_tag.startswith('UINT64: '):
            # .1.3.6.1.4.1.2021.10.1.6.2 = Opaque: UInt64: 18446744073709551614
            # there should be BER encoder, but really I not how do this,
            # I just convert to HEX value instead
            hex = '{:X}'.format(int(value))
            add = len(hex) % 2
            hex = add * '0' + hex
            parts = [hex[i:i + 2] for i in range(0, len(hex), 2)]

            # value len
            hex = '{:X}'.format(len(parts))
            add = len(hex) % 2
            hex = add * '0' + hex
            parts = [hex[i:i + 2] for i in range(0, len(hex), 2)] + parts

            # UInt64 subtag is 9f7b
            value = '9F 7B ' + ' '.join(parts)

        elif opaque_tag.startswith('INT64: '):
            # .1.3.6.1.4.1.2021.10.1.6.3 = Opaque: Int64: 9223372036854775806
            # .1.3.6.1.4.1.2021.10.1.6.4 = Opaque: Int64: -2
            hex = '{:X}'.format(int(value) & (2**64-1))
            add = len(hex) % 2
            hex = add * '0' + hex
            parts = [hex[i:i + 2] for i in range(0, len(hex), 2)]

            # value len
            hex = '{:X}'.format(len(parts))
            add = len(hex) % 2
            hex = add * '0' + hex
            parts = [hex[i:i + 2] for i in range(0, len(hex), 2)] + parts

            # Int64 subtag is 9f7a
            value = '9F 7A ' + ' '.join(parts)

        return [int(y, 16) for y in value.split(' ')]

    @staticmethod
    def _bits_filter(value):
        # rfc1902.Bits does not really initialize from sequences
        if value == '':
            # .1.3.6.1.2.1.10.7.9.1.1.509 = BITS:
            return value
        
        # Clean bits values
        # .1.3.6.1.2.1.17.6.1.1.1.0 = BITS: 5B 00 00 00   [[...]1 3 4 6 7
        # .1.3.6.1.2.1.17.6.1.1.1.0 = BITS: 5B 00 00 00   clear(1)        
        match = re.match(r'^([0-9a-fA-F]{2}(\s+[0-9a-fA-F]{2})*)', value)
        if match:
            return bytes([int(y, 16) for y in match.group(1).split(' ')])

        return bytes([int(y, 16) for y in value.split(' ')])

    @staticmethod
    def _hex_string_filter(value):
        # .1.3.6.1.2.1.3.1.1.2.2.1.172.30.1.30 = Hex-STRING: 00 C0 FF 43 CE 45   [...C.E]
        match = re.match(r'^([0-9a-fA-F]{2}(\s+[0-9a-fA-F]{2})*)\s+\[', value)
        if match:
            return [int(y, 16) for y in match.group(1).split(' ')]
        elif ' ' in value:
            return [int(y, 16) for y in value.split(' ')]
        else:
            # This could be the format returned by some unknown windows snmpwalk tool:
            # .1.3.6.1.2.1.2.2.1.6.1 = HEX-STRING: 00029929AE3C
            return [int(value[i:i+2], 16) for i in range(0, len(value), 2)]

    @staticmethod
    def _gauge_filter(value):
        try:
            int(value)
            return value

        except ValueError:
            # Clean values with UNIT suffix
            # .1.3.6.1.2.1.4.31.1.1.47.1 = Gauge32: 10000 milli-seconds
            match = re.match(r'(\-?[0-9]+)\s.+', value)
            if match:
                return match.group(1)

            return value

    @staticmethod
    def _net_address_filter(value):
        return '.'.join([str(int(y, 16)) for y in value.split(':')])

    @staticmethod
    def _time_ticks_filter(value):
        match = re.match(r'.*?\(([0-9]+)\)', value)
        if match:
            return match.group(1)

        return value

    def parse(self, line):

        filters = {
            'OPAQUE:': self._opaque_filter,
            'INTEGER:': self._integer_filter,
            'STRING:': self._string_filter,
            'BITS:': self._bits_filter,
            'HEX-STRING:': self._hex_string_filter,
            'GAUGE32:': self._gauge_filter,
            'NETWORK ADDRESS:': self._net_address_filter,
            'TIMETICKS:': self._time_ticks_filter
        }

        # drop possible 8-bits
        line = line.decode('ascii', 'ignore').encode()

        try:
            oid, value = octs2str(line).strip().split(' = ', 1)

        except Exception:
            raise error.SnmpsimError('broken record <%s>' % line)

        if oid and oid[0] == '.':
            oid = oid[1:]

        if value.startswith('Wrong Type (should be'):
            value = value[value.index(': ') + 2:]

        if value.startswith('No more variables left in this MIB View'):
            value = 'STRING: '

        match = re.match(r'^(\w+(?:[\-\ ]\w+)?:)\ ?(.*)', value)
        if match:
            tag = match.group(1)
            value = match.group(2)

        # this is implicit snmpwalk's fuzziness
        elif value == '""' or value == 'STRING:':
            tag = 'STRING:'
            value = ''

        elif value == 'NULL':
            tag = 'NULL:'
            value = ''

        else:
            tag = 'TimeTicks:'

        if oid and tag:
            handler = filters.get(tag.upper(), lambda x: x)

            # Need rewrite tag for Network Address after filters
            if tag == 'Network Address:':
                tag = 'IpAddress:'

            return oid, tag.upper(), handler(value.strip())

        raise error.SnmpsimError('broken record <%s>' % line)
