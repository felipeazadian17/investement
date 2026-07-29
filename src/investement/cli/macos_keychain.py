import ctypes
from functools import lru_cache

ERR_SEC_ITEM_NOT_FOUND = -25300


class KeychainError(RuntimeError):
    pass


def read_password(account: str, service: str) -> str:
    security, _ = _frameworks()
    account_bytes = account.encode("utf-8")
    service_bytes = service.encode("utf-8")
    length = ctypes.c_uint32()
    data = ctypes.c_void_p()
    status = security.SecKeychainFindGenericPassword(
        None,
        len(service_bytes),
        service_bytes,
        len(account_bytes),
        account_bytes,
        ctypes.byref(length),
        ctypes.byref(data),
        None,
    )
    if status == ERR_SEC_ITEM_NOT_FOUND:
        return ""
    _require_success(status, "read")
    try:
        return ctypes.string_at(data, length.value).decode("utf-8")
    finally:
        security.SecKeychainItemFreeContent(None, data)


def write_password(account: str, service: str, value: str) -> None:
    security, core_foundation = _frameworks()
    account_bytes = account.encode("utf-8")
    service_bytes = service.encode("utf-8")
    value_bytes = value.encode("utf-8")
    item = ctypes.c_void_p()
    status = security.SecKeychainFindGenericPassword(
        None,
        len(service_bytes),
        service_bytes,
        len(account_bytes),
        account_bytes,
        None,
        None,
        ctypes.byref(item),
    )
    if status == ERR_SEC_ITEM_NOT_FOUND:
        status = security.SecKeychainAddGenericPassword(
            None,
            len(service_bytes),
            service_bytes,
            len(account_bytes),
            account_bytes,
            len(value_bytes),
            value_bytes,
            ctypes.byref(item),
        )
        _require_success(status, "write")
    else:
        _require_success(status, "find before write")
        status = security.SecKeychainItemModifyAttributesAndData(
            item,
            None,
            len(value_bytes),
            value_bytes,
        )
        _require_success(status, "update")
    _release(core_foundation, item)


def delete_password(account: str, service: str) -> None:
    security, core_foundation = _frameworks()
    account_bytes = account.encode("utf-8")
    service_bytes = service.encode("utf-8")
    item = ctypes.c_void_p()
    status = security.SecKeychainFindGenericPassword(
        None,
        len(service_bytes),
        service_bytes,
        len(account_bytes),
        account_bytes,
        None,
        None,
        ctypes.byref(item),
    )
    if status == ERR_SEC_ITEM_NOT_FOUND:
        return
    _require_success(status, "find before delete")
    try:
        _require_success(security.SecKeychainItemDelete(item), "delete")
    finally:
        _release(core_foundation, item)


@lru_cache(maxsize=1)
def _frameworks():
    security = ctypes.CDLL(
        "/System/Library/Frameworks/Security.framework/Security"
    )
    core_foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
    security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
    security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
    security.SecKeychainItemDelete.restype = ctypes.c_int32
    security.SecKeychainItemFreeContent.restype = ctypes.c_int32
    core_foundation.CFRelease.argtypes = (ctypes.c_void_p,)
    return security, core_foundation


def _release(core_foundation, item: ctypes.c_void_p) -> None:
    if item.value:
        core_foundation.CFRelease(item)


def _require_success(status: int, operation: str) -> None:
    if status != 0:
        raise KeychainError(f"macOS Keychain {operation} failed with status {status}")
