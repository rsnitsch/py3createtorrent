#!/usr/bin/env python3
"""
py3bencode is a new GPL-licensed Bencode module developed for Python 3.

= Motivation =

  There already have been some Bencode modules for Python, but I haven't
  found any reliable module which works with Python 3 as well.

  So I created this module from scratch.


= Version & Changelog =

  This is version 1.0 (initial release).

  No changelog so far.


= Future =

  Generally it might be useful to provide more specific error messages if
  anything goes wrong. However, the most common errors are already covered.


= Credits =

  Robert Nitsch <r.s.nitsch+dev@gmail.com> - July 2010 (Version 1.0)


= License =

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

def _bytes(_str):
    """
    Convert ordinary Python string (utf-8) into byte array (should be considered
    as c-string).

    @rtype:   bytes
    """
    return bytes(str(_str), "utf-8")

def _str(_bytes):
    """
    Attempt to decode byte array back to ordinary Python string (utf-8).

    Decoding cannot be guaranteed, so be careful.

    @rtype:   str, but will return the original data if it can't be interpreted as utf-8
    """
    try:
        return _bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _bytes

def bencode(thing):
    """
    bencodes the given object, returning a byte array
    containing the bencoded data.

    Allowed object types are:
    - list (list)
    - dictionary (dict)
    - integer (int)
    - string (str)
    - byte array (bytes)

    Note that all strings will be converted to byte arrays during the
    encoding process.

    @rtype:   bytes
    """
    if   isinstance(thing, int):
        return _bytes("i%se" % thing)

    elif isinstance(thing, str):
        return _bytes(str(len(_bytes(thing))) + ":" + thing)

    elif isinstance(thing, bytes):
        return _bytes(str(len(thing)) + ":") + thing

    elif isinstance(thing, bytearray):
        return bencode(bytes(thing))

    elif isinstance(thing, list):
        return b"l" + b"".join([bencode(i) for i in thing]) + b"e"

    elif isinstance(thing, dict):
        result = b"d"

        keys = list(thing.keys())
        keys.sort()

        for key in keys:
            result += bencode(key) + bencode(thing[key])

        return result + b"e"

    raise TypeError("bencoding objects of type %s not supported" % type(thing))

def bdecode(data, decode_strings=True, strict=False):
    """
    Restores/decodes bencoded data. The bencoded data must be given as byte array.

    Note that all bencode-strings are treated as byte arrays first. Unless
    decode_strings=False the bdecoder then tries to convert every byte array
    to an ordinary Python string, that means: it tries to interpret every
    byte string as utf-8 string.

    This behavior is meant to make this module more convenient.
    Though I strongly recommend to disable the automatic decoding attempts of
    strings. Your application should know which bencode-strings are meant to
    be utf-8 and which not.

    The strict parameter enforces additional bencode conventions, these are:
    - no negative zeroes are allowed for integers
    - no leading  zeroes are allowed for integers

    strict=False (default) means the decoder will just ignore glitches like that.
    Please note that a proper encoder will never produce errors like these at all.

    @rtype:   list, dict, int, str or bytes
    """
    if not isinstance(data, bytes):
        raise TypeError("bdecode expects byte array.")

    return BDecoder(data, decode_strings, strict).decode()

class DecodingException(Exception):
    """
    Raised by the decoder on error.
    """
    pass

class BDecoder(object):
    """
    The decoder itself.

    See bdecode() for how to use it. (Though I recommend not to do so.)
    """
    def __init__(self, data, decode_strings, strict):
        self.data   = data
        self.pos    = 0

        self.strict         = strict
        self.decode_strings = decode_strings

    def get_pos_char(self):
        """
        Get char (byte) at current position.
        """
        _res = self.data[self.pos:self.pos+1]

        # why use slice syntax instead of ordinary random access?
        # because self.data[some_index] would return a byte,
        # that is a number between 0-255.
        #
        # slice syntax, however, returns e.g. b'A' (instead of 65).

        if len(_res) == 0:
            raise DecodingException("Unexpected end of data. Unterminated list/dictionary?")
        return _res
    pos_char = property(get_pos_char)

    def decode(self):
        """Decode whatever we find at the current position."""
        _pos_char  =  self.pos_char

        if   _pos_char == b'i':
            self.pos  +=  1
            return self.decode_int()
        elif _pos_char == b'l':
            self.pos  +=  1
            return self.decode_list()
        elif _pos_char == b'd':
            self.pos  +=  1
            return self.decode_dict()
        elif _pos_char.isdigit():
            return self.decode_string()
        else:
            raise DecodingException

    def decode_int(self):
        _start = self.pos
        _end   = self.data.index(b'e', _start)

        if _start == _end:
            raise DecodingException("Empty integer.")

        self.pos = _end+1

        _int = int(self.data[_start:_end])

        # strict: forbig leading zeroes and negative zero
        if self.strict:
            if bytes(str(_int), "utf-8") != self.data[_start:_end]:
                raise DecodingException("Leading zeroes or negative zero detected.")

        return _int

    def decode_list(self):
        _list = []

        while True:
            if self.pos_char == b'e':
                self.pos += 1
                return _list

            _pos = self.pos

            try:
                _list.append(self.decode())
            except DecodingException:
                # did the exception happen because there is nothing to decode?
                if _pos == self.pos:
                    raise DecodingException("Unterminated list (or invalid list contents).")
                else:
                    raise

        assert False

    def decode_dict(self):
        _dict = {}

        while True:
            if self.pos_char == b'e':
                self.pos += 1
                return _dict

            if not self.pos_char.isdigit():
                raise DecodingException("Invalid dictionary key (must be string).")

            key        = self.decode_string()
            _dict[key] = self.decode()

        assert False

    def decode_string(self):
        _start = self.pos
        _colon = self.data.index(b':', _start)
        _len   = int(self.data[_start:_colon])

        if _len < 0:
            raise DecodingException("String with length < 0 found.")

        self.pos = _colon+1+_len

        _res = self.data[_colon+1:_colon+1+_len]

        if self.decode_strings:
            return _str(_res)
        else:
            return _res


if __name__ == '__main__':
    import sys, os

    if len(sys.argv) == 2:
        file = sys.argv[1]

        if not os.path.isfile(file):
            print("Error: '%s' is not a valid file." % file)
            sys.exit(1)

        with open(file, "rb") as fh:
            from pprint import pprint
            pprint(bdecode(fh.read()))

        sys.exit(0)

    ##################
    # RUN UNIT TESTS #
    import unittest

    class Test(unittest.TestCase):
        def setUp(self):
            pass

        def test_complex(self):
            # Complex tests with a lot of hierarchy in the data.
            test_data = [{'bar': 'spam', 'foo': 42},
                         {'foo': ['bar', [42, 'morespam'], 'spam']},
                         'gedons']

            for data in test_data:
                self.assertEqual(data, bdecode(bencode(data)))

            # all together
            self.assertEqual(test_data, bdecode(bencode(test_data)))

        def test_single_ints(self):
            # Testing with integers only.
            test_data = [-1337, 0, 1337**2, 2**33]
            for data in test_data:
                self.assertEquals(data, bdecode(bencode(data)))

        def test_single_strings_decoding(self):
            # Testing with strings only, automatic decoding enabled (the default).
            test_data = ["", "test", "utf8-string: ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¤ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¶ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¼"]
            for data in test_data:
                self.assertEquals(data, bdecode(bencode(data)))

        def test_single_strings_nodecoding(self):
            # same like above but without internal decoding attempts
            # (decode_strings = False)
            test_data = ["", "test", "utf8-string: ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¤ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¶ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¼"]
            for data in test_data:
                self.assertEquals(data,
                                  bdecode(bencode(data),
                                          decode_strings=False).decode("utf-8"))

        def test_single_strings_more(self):
            # decoding b"test" will result in "test" due
            # to string decoding, which is activated by default
            self.assertEquals("test",  bdecode(bencode(b"test")))

            # decoding b"test" will result in b"test"
            # if the string decoding gets disabled explicitly
            self.assertEquals(b"test", bdecode(bencode(b"test"), decode_strings=False))

            # however, if string decoding gets disabled explicility,
            # even "test" will not be restored. instead, b"test" will be
            # returned.
            self.assertEquals(b"test", bdecode(bencode("test"), decode_strings=False))

        def test_empty_list(self):
            self.assertEquals([], bdecode(bencode([])))

        def test_empty_dict(self):
            self.assertEquals({}, bdecode(bencode({})))

        def test_detect_bad_dict_keys(self):
            with self.assertRaisesRegexp(DecodingException,
                                         "^Invalid dictionary key"):
                bdecode(b"di123e4:spame")

        def test_detect_unterminated_list(self):
            with self.assertRaisesRegexp(DecodingException,
                                         "^Unexpected end of data"):
                bdecode(b"li123e")

        def test_detect_empty_integer(self):
            with self.assertRaisesRegexp(DecodingException,
                                         "^Empty integer"):
                bdecode(b"l4:spamiee")

        def test_detect_leading_zeroes(self):
            # Detect leading zero
            with self.assertRaisesRegexp(DecodingException,
                                         "^Leading zeroes"):
                bdecode(b"i01e", strict=True)

            # Detect leading zero of negative number
            with self.assertRaisesRegexp(DecodingException,
                                         "^Leading zeroes"):
                bdecode(b"i-01e", strict=True)

            # Detect negative zero
            with self.assertRaisesRegexp(DecodingException,
                                         "negative zero"):
                bdecode(b"i-0e", strict=True)

            # However, the zero itself must be accepted...
            self.assertEquals(0, bdecode(b"i0e", strict=True))

        def test_bad_sized_string(self):
            with self.assertRaises(DecodingException):
                bdecode(b"l12:normalstring-5:badstringe")

    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2), exit=False)

