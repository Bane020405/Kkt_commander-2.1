#!/usr/bin/env python3
"""
Восстановительная перерегистрация ККТ (ФФД 1.05) с корректными параметрами.
Используйте, если после предыдущих экспериментов касса стала выдавать ошибки 148, 1036 и т.п.
"""

import sys
import time
from libfptr10 import IFptr

try:
    from conf import LIBRARY_PATH
except ImportError:
    print("Укажите LIBRARY_PATH в conf.py или внутри скрипта")
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
        raise ConnectionError("Нет связи с ККТ")
    fptr.enableOfdChannel()
    print("Связь установлена.")

def get_shift_status(fptr):
    fptr.setParam(IFptr.LIBFPTR_PARAM_DATA_TYPE, IFptr.LIBFPTR_DT_SHIFT_STATE)
    fptr.queryData()
    return fptr.getParamInt(IFptr.LIBFPTR_PARAM_SHIFT_STATE)

def close_shift(fptr):
    print("Закрываем смену...")
    fptr.setParam(IFptr.LIBFPTR_PARAM_REPORT_TYPE, IFptr.LIBFPTR_RT_CLOSE_SHIFT)
    fptr.report()
    while fptr.checkDocumentClosed() < 0:
        time.sleep(0.5)
    print("Смена закрыта.")

def get_tag_str(fptr, tag):
    fptr.setParam(IFptr.LIBFPTR_PARAM_FN_DATA_TYPE, IFptr.LIBFPTR_FNDT_TAG_VALUE)
    fptr.setParam(IFptr.LIBFPTR_PARAM_TAG_NUMBER, tag)
    fptr.fnQueryData()
    return fptr.getParamString(IFptr.LIBFPTR_PARAM_TAG_VALUE)

def get_tag_int(fptr, tag):
    fptr.setParam(IFptr.LIBFPTR_PARAM_FN_DATA_TYPE, IFptr.LIBFPTR_FNDT_TAG_VALUE)
    fptr.setParam(IFptr.LIBFPTR_PARAM_TAG_NUMBER, tag)
    fptr.fnQueryData()
    return fptr.getParamInt(IFptr.LIBFPTR_PARAM_TAG_VALUE)

def reregister_safe(fptr):
    # Считываем текстовые реквизиты
    org_name = get_tag_str(fptr, 1048)
    org_inn = get_tag_str(fptr, 1018)
    address = get_tag_str(fptr, 1009)
    location = get_tag_str(fptr, 1187)
    email = get_tag_str(fptr, 1117)
    kkt_reg = get_tag_str(fptr, 1037)
    ofd_inn = get_tag_str(fptr, 1017)
    ofd_name = get_tag_str(fptr, 1046)
    
    # Текущую маску СНО можно взять из тега 1062, но мы запросим новую
    current_mask = get_tag_int(fptr, 1062)
    print(f"Текущая маска СНО: {current_mask}")

    # Запрос новой маски
    tax_choices = {
        '1': IFptr.LIBFPTR_TT_OSN,
        '2': IFptr.LIBFPTR_TT_USN_INCOME,
        '3': IFptr.LIBFPTR_TT_USN_INCOME_OUTCOME,
        '4': IFptr.LIBFPTR_TT_ESN,
        '5': IFptr.LIBFPTR_TT_PATENT,
    }
    print("Выберите новую СНО (или оставьте ту же, чтобы только исправить параметры):")
    for num, name in [('1','ОСН'), ('2','УСН доход'), ('3','УСН доход-расход'),
                      ('4','ЕСХН'), ('5','Патент')]:
        print(f"  {num} - {name}")
    choice = input("Номера через пробел: ").strip()
    new_mask = 0
    for c in choice.split():
        code = tax_choices.get(c)
        if code:
            new_mask |= code

    if new_mask == 0:
        print("Маска не изменена, оставляем текущую.")
        new_mask = current_mask

    # Параметры перерегистрации – только обязательные, без признаков, которые не используются
    fptr.setParam(IFptr.LIBFPTR_PARAM_FN_OPERATION_TYPE, IFptr.LIBFPTR_FNOP_CHANGE_PARAMETERS)
    fptr.setParam(1060, "www.nalog.gov.ru")
    fptr.setParam(1009, address)
    fptr.setParam(1018, org_inn)
    fptr.setParam(1048, org_name)
    fptr.setParam(1062, new_mask)
    fptr.setParam(1117, email)
    fptr.setParam(1057, 0)               # агент – нет
    fptr.setParam(1187, location)
    fptr.setParam(1037, kkt_reg)
    fptr.setParam(1209, IFptr.LIBFPTR_FFD_1_0_5)

    # ВСЕ ПРИЗНАКИ РЕЖИМОВ – ЯВНО ВЫКЛЮЧЕНЫ (False не передаём, чтобы не активировать)
    # Не вызываем setParam для 1001, 1002, 1056, 1108, 1109, 1110, 1126, 1193, 1207, 1221
    # Они останутся такими, какие были раньше. Если хотите явно выключить, передайте 0 (но лучше не трогать)
    # ОФД
    fptr.setParam(1017, ofd_inn)
    fptr.setParam(1046, ofd_name)
    # Причина перерегистрации (изменение параметров)
    fptr.setParam(1101, 3)

    # Отключаем печать отчёта (по возможности)
    try:
        fptr.setParam(IFptr.LIBFPTR_PARAM_REPORT_ELECTRONICALLY, True)
    except:
        pass

    print("Выполняется перерегистрация...")
    fptr.fnOperation()
    while fptr.checkDocumentClosed() < 0:
        time.sleep(0.5)
    if not fptr.getParamBool(IFptr.LIBFPTR_PARAM_DOCUMENT_CLOSED):
        raise RuntimeError(f"Ошибка: {fptr.errorCode()} {fptr.errorDescription()}")
    print("Перерегистрация успешна. Касса восстановлена.")

def main():
    fptr = init_fptr()
    open_connection(fptr)
    shift = get_shift_status(fptr)
    if shift != IFptr.LIBFPTR_SS_CLOSED:
        close_shift(fptr)
    try:
        reregister_safe(fptr)
    finally:
        fptr.close()

if __name__ == "__main__":
    main()