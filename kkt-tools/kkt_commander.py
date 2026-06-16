#!/usr/bin/env python3
"""
Смена системы налогообложения на ККТ АТОЛ (ФФД 1.05).
Принимает маску СНО как аргумент командной строки.
Сам управляет портом и закрывает открытую смену.
"""

import sys
import time
from libfptr10 import IFptr

try:
    from conf import LIBRARY_PATH
except ImportError:
    print("Ошибка: не найден conf.py с переменной LIBRARY_PATH.")
    sys.exit(1)


def init_fptr():
    fptr = IFptr(LIBRARY_PATH)
    fptr.setSingleSetting(IFptr.LIBFPTR_SETTING_MODEL, str(IFptr.LIBFPTR_MODEL_ATOL_AUTO))
    fptr.setSingleSetting(IFptr.LIBFPTR_SETTING_PORT, str(IFptr.LIBFPTR_PORT_USB))
    fptr.setSingleSetting(IFptr.LIBFPTR_SETTING_OFD_CHANNEL, str(IFptr.LIBFPTR_OFD_CHANNEL_AUTO))
    fptr.applySingleSettings()
    return fptr


def open_connection(fptr):
    fptr.open()
    if fptr.isOpened() == 0:
        raise ConnectionError("Не удалось открыть соединение с ККТ.")
    fptr.enableOfdChannel()
    print("Соединение с ККТ установлено.")


def get_shift_status(fptr):
    fptr.setParam(IFptr.LIBFPTR_PARAM_DATA_TYPE, IFptr.LIBFPTR_DT_SHIFT_STATE)
    fptr.queryData()
    return fptr.getParamInt(IFptr.LIBFPTR_PARAM_SHIFT_STATE)


def close_shift(fptr):
    print("Смена открыта. Закрываем...")
    fptr.setParam(IFptr.LIBFPTR_PARAM_REPORT_TYPE, IFptr.LIBFPTR_RT_CLOSE_SHIFT)
    fptr.report()
    while fptr.checkDocumentClosed() < 0:
        time.sleep(0.5)
    if fptr.getParamBool(IFptr.LIBFPTR_PARAM_DOCUMENT_CLOSED):
        print("Смена закрыта.")
    else:
        print("Предупреждение: не удалось подтвердить закрытие смены.")


def get_tag_int(fptr, tag):
    fptr.setParam(IFptr.LIBFPTR_PARAM_FN_DATA_TYPE, IFptr.LIBFPTR_FNDT_TAG_VALUE)
    fptr.setParam(IFptr.LIBFPTR_PARAM_TAG_NUMBER, tag)
    fptr.fnQueryData()
    return fptr.getParamInt(IFptr.LIBFPTR_PARAM_TAG_VALUE)


def get_tag_str(fptr, tag):
    fptr.setParam(IFptr.LIBFPTR_PARAM_FN_DATA_TYPE, IFptr.LIBFPTR_FNDT_TAG_VALUE)
    fptr.setParam(IFptr.LIBFPTR_PARAM_TAG_NUMBER, tag)
    fptr.fnQueryData()
    return fptr.getParamString(IFptr.LIBFPTR_PARAM_TAG_VALUE)


def get_registration_data(fptr):
    return {
        "org_name":       get_tag_str(fptr, 1048),
        "org_inn":        get_tag_str(fptr, 1018),
        "address":        get_tag_str(fptr, 1009),
        "location":       get_tag_str(fptr, 1187),
        "email":          get_tag_str(fptr, 1117),
        "kkt_reg_number": get_tag_str(fptr, 1037),
        "ofd_inn":        get_tag_str(fptr, 1017),
        "ofd_name":       get_tag_str(fptr, 1046),
        "taxation_mask":  get_tag_int(fptr, 1062),
        "agent_mask":     get_tag_int(fptr, 1057),
        "auto_mode":      bool(get_tag_int(fptr, 1001)),
        "autonomous":     bool(get_tag_int(fptr, 1002)),
        "encryption":     bool(get_tag_int(fptr, 1056)),
        "internet":       bool(get_tag_int(fptr, 1108)),
        "services":       bool(get_tag_int(fptr, 1109)),
        "as_bso":         bool(get_tag_int(fptr, 1110)),
        "lottery":        bool(get_tag_int(fptr, 1126)),
        "gambling":       bool(get_tag_int(fptr, 1193)),
        "excise":         bool(get_tag_int(fptr, 1207)),
        "machine_install": bool(get_tag_int(fptr, 1221)),
    }


def change_taxation(fptr, reg_data, new_tax_mask):
    fptr.setParam(IFptr.LIBFPTR_PARAM_FN_OPERATION_TYPE, IFptr.LIBFPTR_FNOP_CHANGE_PARAMETERS)
    fptr.setParam(1060, "www.nalog.gov.ru")
    fptr.setParam(1009, reg_data["address"])
    fptr.setParam(1018, reg_data["org_inn"])
    fptr.setParam(1048, reg_data["org_name"])
    fptr.setParam(1062, new_tax_mask)
    fptr.setParam(1117, reg_data["email"])
    fptr.setParam(1057, reg_data["agent_mask"])
    fptr.setParam(1187, reg_data["location"])
    fptr.setParam(1037, reg_data["kkt_reg_number"])
    fptr.setParam(1209, IFptr.LIBFPTR_FFD_1_0_5)

    fptr.setParam(1001, False)      # выключаем автоматический режим
    fptr.setParam(1221, False)      # выключаем установку в автомате
    fptr.setParam(1002, reg_data["autonomous"])
    fptr.setParam(1056, reg_data["encryption"])
    fptr.setParam(1108, reg_data["internet"])
    fptr.setParam(1109, reg_data["services"])
    fptr.setParam(1110, reg_data["as_bso"])
    fptr.setParam(1126, reg_data["lottery"])
    fptr.setParam(1193, reg_data["gambling"])
    fptr.setParam(1207, reg_data["excise"])

    fptr.setParam(1017, reg_data["ofd_inn"])
    fptr.setParam(1046, reg_data["ofd_name"])
    fptr.setParam(1101, 3)          # изменение параметров регистрации
    try:
        fptr.setParam(IFptr.LIBFPTR_PARAM_REPORT_ELECTRONICALLY, True)
    except AttributeError:
        pass

    print("Выполняется перерегистрация...")
    fptr.fnOperation()
    while fptr.checkDocumentClosed() < 0:
        time.sleep(0.5)

    if not fptr.getParamBool(IFptr.LIBFPTR_PARAM_DOCUMENT_CLOSED):
        err_code = fptr.errorCode()
        err_desc = fptr.errorDescription()
        raise RuntimeError(f"Ошибка перерегистрации: [{err_code}] {err_desc}")

    print("Система налогообложения успешно изменена!")


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "change_taxation_system":
        print("Использование: kkt_commander.py change_taxation_system <маска>")
        sys.exit(1)

    try:
        new_mask = int(sys.argv[2])
    except ValueError:
        print("Маска должна быть целым числом")
        sys.exit(1)

    fptr = init_fptr()
    open_connection(fptr)

    shift = get_shift_status(fptr)
    if shift == IFptr.LIBFPTR_SS_OPENED or shift == IFptr.LIBFPTR_SS_EXPIRED:
        close_shift(fptr)

    print("Чтение регистрационных данных из ФН...")
    reg = get_registration_data(fptr)
    print(f"Организация: {reg['org_name']}")
    print(f"Текущая маска СНО: {reg['taxation_mask']}")

    try:
        change_taxation(fptr, reg, new_mask)
    except Exception as e:
        print(f"ОШИБКА: {e}")
        sys.exit(1)
    finally:
        fptr.close()
        print("Соединение закрыто.")


if __name__ == "__main__":
    main()