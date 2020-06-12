#! /usr/bin/python3
import coincurve
from io import BufferedIOBase
from pyln.proto.message import FieldType, split_field
from .utils import check_hex, privkey_expand
from typing import Union, Tuple, Dict, Any, Optional, cast


class Sig(object):
    """The value of a signature, either as a privkey/hash pair or a raw
signature.  This has the property that if the raw signature is a valid
signature of privkey over hash, they are considered "equal"

"""
    def __init__(self, *args):
        """Either a 64-byte hex/bytes value, or a PrivateKey and a hash"""
        if len(args) == 1:
            if type(args[0]) is bytes:
                if len(args[0]) != 64:
                    raise ValueError('Sig() with 1 arg expects 64 bytes or 128 hexstr')
                self.sigval: Union[bytes, None] = cast(bytes, args[0])
            else:
                if type(args[0]) is not str:
                    raise TypeError('Expected hexsig or Privkey, hash')
                self.sigval = bytes.fromhex(check_hex(cast(str, args[0]), 128))
        elif len(args) == 2:
            self.sigval = None
            self.privkey = privkey_expand(args[0])
            self.hashval = bytes.fromhex(check_hex(args[1], 64))
        else:
            raise TypeError('Expected hexsig or Privkey, hash')

    @staticmethod
    def to_der(b: bytes) -> bytes:
        """Seriously fuck off with DER encoding :("""
        r = b[0:32]
        s = b[32:64]
        # Trim zero bytes
        while r[0] == 0:
            r = r[1:]
        # Prepend 0 again if would be negative
        if r[0] & 0x80:
            r = bytes([0]) + r
        # Trim zero bytes
        while s[0] == 0:
            s = s[1:]
        # Prepend 0 again if would be negative
        if s[0] & 0x80:
            s = bytes([0]) + s

        # 2 == integer, next == length
        ret = bytes([0x02, len(r)]) + r + bytes([0x02, len(s)]) + s
        # 30 == compound, next = length
        return bytes([0x30, len(ret)]) + ret

    @staticmethod
    def from_der(b: bytes) -> bytes:
        """Sigh.  Seriously, WTF is it with DER encoding?"""
        rlen = b[3]
        r = b[4:4 + rlen].rjust(32, bytes(1))[-32:]
        assert(len(r) == 32)
        s = b[4 + rlen + 1 + 1:].rjust(32, bytes(1))[-32:]
        assert(len(s) == 32)
        return r + s

    def __eq__(self, other) -> bool:
        # For convenience of using stashed objects, we allow comparison with str
        if isinstance(other, str):
            other = Sig(other)
        if self.sigval and other.sigval:
            return self.sigval == other.sigval
        elif not self.sigval and not other.sigval:
            return self.privkey == other.privkey and self.hashval == other.hashval
        elif not self.sigval:
            a = self
            b = other
        else:
            a = other
            b = self
        # A has a privkey/hash, B has a sigval.
        pubkey = coincurve.PublicKey.from_secret(a.privkey.secret)
        if coincurve.verify_signature(self.to_der(b.sigval), a.hashval, pubkey.format(), hasher=None):
            return True
        return False

    def to_str(self) -> str:
        if self.sigval:
            return self.sigval.hex()
        else:
            return 'Sig({},{})'.format(self.privkey.secret.hex(), self.hashval.hex())

    @staticmethod
    def from_str(s: str) -> Tuple['Sig', str]:
        a, b = split_field(s)
        if a.startswith('Sig('):
            privkey = a[4:]
            a, b = split_field(b)
            # Trim ) off Sig()
            return Sig(privkey, a[:-1]), b
        return Sig(bytes.fromhex(a)), b

    def to_bin(self) -> bytes:
        if not self.sigval:
            return self.from_der(self.privkey.sign(self.hashval, hasher=None))
        else:
            return self.sigval


class SigType(FieldType):
    """A signature type which has special comparison properties"""
    def __init__(self):
        super().__init__('signature')

    def val_to_str(self, v: Sig, otherfields: Dict[str, Any]) -> str:
        return v.to_str()

    def val_from_str(self, s: str) -> Tuple['Sig', str]:
        return Sig.from_str(s)

    def write(self, io_out: BufferedIOBase, v: Sig, otherfields: Dict[str, Any]) -> None:
        io_out.write(v.to_bin())

    def read(self, io_in: BufferedIOBase, otherfields: Dict[str, Any]) -> Optional[Sig]:
        val = io_in.read(64)
        if len(val) == 0:
            return None
        elif len(val) != 64:
            raise ValueError('{}: not enough remaining'.format(self))
        return Sig(val)


def test_der():
    der = b'0E\x02!\x00\xa0\xb3\x7f\x8f\xbah<\xc6\x8fet\xcdC\xb3\x9f\x03C\xa5\x00\x08\xbfl\xce\xa9\xd121\xd9\xe7\xe2\xe1\xe4\x02 \x11\xed\xc8\xd3\x07%B\x96&J\xeb\xfc=\xc7l\xd8\xb6h7:\x07/\xd6Fe\xb5\x00\x00\xe9\xfc\xceR'
    sig = Sig.from_der(der)
    der2 = Sig.to_der(sig)
    assert der == der2


def test_signature():
    s = Sig('01', '00' * 32)

    assert s == s
    b = s.to_bin()
    s2 = Sig(b)

    assert s == s2
    assert s2 == s