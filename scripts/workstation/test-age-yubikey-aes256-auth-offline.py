#!/usr/bin/env python3
"""Offline simulation of PIV protected AES256 management-key authentication.

Fake PIV objects only. NEVER connects to a card or accepts a real PIN or key.
"""
import argparse


class FakeSession:
    def __init__(self, pin_valid=True, stored_key_valid=True):
        self.events = []
        self.pin_valid = pin_valid
        self.stored_key_valid = stored_key_valid

    def verify_pin(self, pin):
        self.events.append("verify_pin")
        if not self.pin_valid or pin != "MOCK_ONLY":
            raise ValueError("Mock PIN rejected")

    def authenticate(self, key):
        self.events.append("authenticate")
        if not self.stored_key_valid or key != bytes(range(32)):
            raise ValueError("Mock AES256 key rejected")


class FakePivman:
    has_stored_key = True
    has_derived_key = False


def authenticate_mock(session, pivman, protected_key):
    """Model SDK 5.8 flow with a fake 32-byte management key only."""
    if not pivman.has_stored_key or pivman.has_derived_key:
        raise ValueError("Unexpected management-key mode")
    if not isinstance(protected_key, bytes) or len(protected_key) != 32:
        raise ValueError("Not an AES256 key")
    session.verify_pin("MOCK_ONLY")
    session.authenticate(protected_key)
    session.verify_pin("MOCK_ONLY")


def self_test():
    key = bytes(range(32))
    good = FakeSession()
    authenticate_mock(good, FakePivman(), key)
    assert good.events == ["verify_pin", "authenticate", "verify_pin"]
    failures = 0
    for session, candidate in [
        (FakeSession(pin_valid=False), key),
        (FakeSession(stored_key_valid=False), key),
        (FakeSession(), key[:-1]),
    ]:
        try:
            authenticate_mock(session, FakePivman(), candidate)
        except ValueError:
            failures += 1
        else:
            raise AssertionError("Unexpected mock authentication success")
    assert failures == 3
    print("PASS: protected AES256 mock sequence and 3 negative paths")
    print("NO-GO hardware: no card, PIN, stored key, signing or certificate import")


def main():
    parser = argparse.ArgumentParser(description="Fake PIV AES256 auth only; no hardware")
    parser.parse_args()
    self_test()


if __name__ == "__main__":
    main()
