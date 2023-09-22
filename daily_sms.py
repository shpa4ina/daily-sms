from pyvcloud.vcd.client import BasicLoginCredentials
from pyvcloud.vcd.client import Client
from pyvcloud.vcd.system import System
from pyvcloud.vcd.vdc import PVDC
from pyvcloud.vcd.utils import pvdc_to_dict, vdc_to_dict
import requests
import datetime
import sys
import getpass
import os
import subprocess as sp

# глобальные переменнные
incorrect_login = 0
stor_tiers = {}
stor_tiers_used = {}
dict_2_0 = {}
dict_3_0 = {}
dict_66_0 = {}
vcd_admin_user = ""
iaas66 = False
vdc_count_2_0 = 0
vdc_count_3_0 = 0
vdc_count_66 = 0

# host = "dev-vmw.a1.by:443"
HOST = "vmw.a1.by:443"
HOST66 = "vmw62.a1.by:443"


# HOST66 = "dev-vmw.a1.by:443"

# функция проверки ввода и авторизации
def auth(incorrect_login=None, incorrect_login66=None):
    # проверяю введены ли параметры
    # print("len(sys.argv)",len(sys.argv))
    # print("incorrect_login =",incorrect_login)
    # print("incorrect_login66 =",incorrect_login66)
    global vcd_admin_password
    global vcd_admin_password66
    if len(sys.argv) < 3 or incorrect_login == 1 or incorrect_login66 == 1:
        print("\nRecommended:\nUsage cli: login password_public password_pci \n")
        if incorrect_login == 0:
            print("Параметры запуска не заданы, требуется ручной ввод УЗ.")
        else:
            pass
            # print("Параметры запуска не заданы, требуется ручно ввод УЗ.")
        vcd_admin_user = input("Введите логин: ")
        vcd_admin_password = getpass.getpass("Введите пароль: ")
        # print("Следующее поле не обязательно для заполнения, можно просто нажать Enter")
        vcd_admin_password66 = getpass.getpass("Введите пароль PCI (опционально): ")

        if len(vcd_admin_password66) > 2:
            print("Значит заглянем ещё и в 66 облако")
    else:
        if len(sys.argv) == 3:
            vcd_admin_user = sys.argv[1]
            vcd_admin_password = sys.argv[2]
            vcd_admin_password66 = ""
        if len(sys.argv) == 4:
            vcd_admin_user = sys.argv[1]
            vcd_admin_password = sys.argv[2]
            print("Значит заглянем ещё и в 66 облако")
            vcd_admin_user66 = sys.argv[1]
            vcd_admin_password66 = sys.argv[3]

    vcd_admin_user66 = vcd_admin_user

    requests.packages.urllib3.disable_warnings()

    # пробую авторизоваться + создание клиента public
    print("Logging in: host={0}, user={1}".format(HOST, vcd_admin_user))
    global client
    client = Client(HOST, verify_ssl_certs=False,
                    log_file=None,
                    log_requests=False,
                    log_headers=False,
                    log_bodies=False)

    try:

        client.set_credentials(BasicLoginCredentials(vcd_admin_user, "system", vcd_admin_password))
    except:
        print(
            f"Подключение к {HOST} не установлено. Возможные причины:\n1)Отсутствует сетевое подключение\n2)Не корректно введены логин и/или пароль")
        print("Повторная попытка ввода УЗ")
        auth(incorrect_login=1)

    # если введен пароль для 66, авторизируемся + создаём клиента 66
    if len(vcd_admin_password66) > 2:
        print("Logging in PCI: host={0}, user={1}".format(HOST66, vcd_admin_user66))
        global client66
        client66 = Client(HOST66, verify_ssl_certs=False,
                          log_file=None,
                          log_requests=False,
                          log_headers=False,
                          log_bodies=False)
        try:

            client66.set_credentials(BasicLoginCredentials(vcd_admin_user66, "system", vcd_admin_password66))
        except:
            print(
                f"Подключение к {HOST66} не установлено. Возможные причины:\n1)Отсутствует сетевое подключение\n2)Не корректно введены логин и/или пароль")
            print("Повторная попытка ввода УЗ")
            auth(incorrect_login66=1)
    else:
        pass


# функция сбора информации, фактически основная
def get_pvdc_info(client):
    # cоздаю сущность System, необходима для дальнейше работы с  Provider VDC
    system = System(client, admin_resource=client.get_admin())
    # получаю информацию по всем имеющимся стореджам в облаке
    provider_vdcs_storage = system.list_provider_vdc_storage_profiles()
    # Подсчет количества provider vdc
    # ty1 = system.list_provider_vdcs()
    # count = len(ty1)
    # print(count)
    for storage in sorted(provider_vdcs_storage):
        # получаю параметры каждого, конкретного storage
        storage_name = storage.get("name")
        storage_used = storage.get("storageUsedMB")
        storage_req = storage.get("storageRequestedMB")
        storage_total = storage.get("storageTotalMB")
        # storage_prov = storage.get("storageProvisionedMB")
        # до проверка, на случай если сторедж пуской( как в DEV)
        if int(storage_total) > 0:
            stor_tiers[storage_name] = round(int(storage_req) / 1048576, 2), round((int(storage_total) / 1048576), 2) # используем этот словарь если значение используемого места для Tier берется из Requested
            stor_tiers_used[storage_name] = round(int(storage_used) / 1048576, 2), round((int(storage_total) / 1048576), 2) # берется из Used
            # print(storage_name)
            # print(storage_total)
            # print(storage_used)
        else:
            # если пустой в качестве значений всего / % исользованя - "None"
            stor_tiers[storage_name] = "None", "None"

    # получаю  перечень всех PVDC
    provider_vdcs = system.list_provider_vdcs()
    # из полученнго списка, работаю с каждым PVDC по отдельности
    for pvdcs in provider_vdcs:
        # print(pvdcs.get("name"))
        # получаю ссылку на  PVDC
        pvdcs_href = pvdcs.get("href")
        # на основании ссылки, создаю объект класса PVDC
        pvdc_class = PVDC(client, href=pvdcs_href)
        # получаю в XML предсталвении все ресурсы этого PVDC
        pvdc = pvdc_class.get_resource()
        # из пакета utils.py беру функцию pvdc_to_dict( название говорит само за себя)
        pvdc_class_dict = pvdc_to_dict(pvdc)
        # далее работаю как со словарём, в котором вся информация по PVDC
        # print(pvdc_class_dict)  # показать содержимое словаря
        # получаем информацию по CPU в данном PVDC
        pvdc_cpu = pvdc_class_dict["cpu_capacity"]
        pvdc_cpu_allocation = round(int(pvdc_cpu["allocation"]) / 1000000, 2)
        pvdc_cpu_total = round(int(pvdc_cpu["total"]) / 1000000, 2)
        pvdc_cpu_used_procents = round(int(pvdc_cpu["allocation"]) / int(pvdc_cpu["total"]) * 100, 2)
        # получаю информацию по RAM в данном PVDC
        pvdc_mem = pvdc_class_dict["mem_capacity"]
        pvdc_mem_total = round(int(pvdc_mem["total"]) / 1048576, 2)
        pvdc_mem_allocation = round(int(pvdc_mem["allocation"]) / 1048576, 2)
        pvdc_mem_used_procents = round((pvdc_mem_allocation / pvdc_mem_total) * 100, 2)


        # наполняю словарь dict_2_0 параметрами относязимися к кластеру 2.0
        # print("pvdcs.get(name): ", pvdcs.get("name"))
        if "2.0" in pvdcs.get("name"):
            dict_2_0["Cloud-Tier-1"] = stor_tiers["Cloud-Tier-1"]
            dict_2_0["Cloud-Tier-2"] = stor_tiers["Cloud-Tier-2"]
            dict_2_0["Cloud-Tier-3"] = stor_tiers["Cloud-Tier-3"]
            dict_2_0["Cloud-Tier-4"] = stor_tiers_used["Cloud-Tier-4"]
            dict_2_0["pvdc_mem_total"] = pvdc_mem_total
            dict_2_0["pvdc_mem_allocation"] = pvdc_mem_allocation
            dict_2_0["pvdc_mem_used_procents"] = pvdc_mem_used_procents
            dict_2_0["pvdc_cpu_allocation"] = pvdc_cpu_allocation
            dict_2_0["pvdc_cpu_total"] = pvdc_cpu_total
            dict_2_0["pvdc_cpu_used_procents"] = pvdc_cpu_used_procents
            print("\n", "Получение данных по 2.0 кластеру :\n", dict_2_0, "\n\n")
        # наполняю словарь dict_3_0 параметрами относязимися к кластеру 3.0
        if "3.0" in pvdcs.get("name"):
            dict_3_0["c01-cl02-Tier-1"] = stor_tiers["c01-cl02-Tier-1"]
            dict_3_0["c01-cl02-Tier-2"] = stor_tiers["c01-cl02-Tier-2"]
            dict_3_0["c01-cl02-Tier-3"] = stor_tiers["c01-cl02-Tier-3"]
            dict_3_0["c01-cl02-Tier-4"] = stor_tiers_used["c01-cl02-Tier-4"]
            dict_3_0["pvdc_mem_total"] = pvdc_mem_total
            dict_3_0["pvdc_mem_allocation"] = pvdc_mem_allocation
            dict_3_0["pvdc_mem_used_procents"] = pvdc_mem_used_procents
            dict_3_0["pvdc_cpu_allocation"] = pvdc_cpu_allocation
            dict_3_0["pvdc_cpu_total"] = pvdc_cpu_total
            dict_3_0["pvdc_cpu_used_procents"] = pvdc_cpu_used_procents
            print("\n", "Получение данных по 3.0 кластеру :\n", dict_3_0, "\n\n")

        # в качестве теста, хост можно подкинуть dev вместо vmw66
        if "Security Cloud" in pvdcs.get("name"):
            dict_66_0["Tier-1"] = stor_tiers["Tier-1"]
            dict_66_0["Tier-2"] = stor_tiers["Tier-2"]
            dict_66_0["Tier-3"] = stor_tiers["Tier-3"]
            dict_66_0["Tier-4"] = stor_tiers["Tier-4"]
            dict_66_0["pvdc_mem_total"] = pvdc_mem_total
            dict_66_0["pvdc_mem_allocation"] = pvdc_mem_allocation
            dict_66_0["pvdc_mem_used_procents"] = pvdc_mem_used_procents
            dict_66_0["pvdc_cpu_allocation"] = pvdc_cpu_allocation
            dict_66_0["pvdc_cpu_total"] = pvdc_cpu_total
            dict_66_0["pvdc_cpu_used_procents"] = pvdc_cpu_used_procents
            print("\n", "Получение данных по PCI кластеру :\n", dict_66_0, "\n\n")
        else:
            # если инфы по PVDC нет - забиваю все данные нулями, актуально при использовании без доступа в PCI
            dict_66_0["Tier-1"] = "0", "0"
            dict_66_0["Tier-2"] = "0", "0"
            dict_66_0["Tier-3"] = "0", "0"
            dict_66_0["Tier-4"] = "0", "0"
            dict_66_0["pvdc_mem_total"] = "0"
            dict_66_0["pvdc_mem_allocation"] = "0"
            dict_66_0["pvdc_mem_used_procents"] = "0"
            dict_66_0["pvdc_cpu_allocation"] = "0"
            dict_66_0["pvdc_cpu_total"] = "0"
            dict_66_0["pvdc_cpu_used_procents"] = "0"

            # dict_2_0["Cloud-Tier-1"]="0","0"
            # dict_2_0["Cloud-Tier-2"]="0","0"
            # dict_2_0["Cloud-Tier-3"]="0","0"
            # dict_2_0["Cloud-Tier-4"]="0","0"
            # dict_2_0["pvdc_mem_total"]="0"
            # dict_2_0["pvdc_mem_used_procents"]="0"
            # dict_3_0["c01-cl02-Tier-1"]="0","0"
            # dict_3_0["c01-cl02-Tier-2"]="0","0"
            # dict_3_0["c01-cl02-Tier-3"]="0","0"
            # dict_3_0["c01-cl02-Tier-4"]="0","0"
            # dict_3_0["pvdc_mem_total"]="0"
            # dict_3_0["pvdc_mem_used_procents"]="0"

    client.logout()


# вызываю авторизацию
auth()
# получаю инфу из public
get_pvdc_info(client)

# получаю инфу из PCI, при условии что пароль задан
if len(sys.argv) == 4 or len(vcd_admin_password66) > 1:
    get_pvdc_info(client66)
    iaas66 = True

# получаю текущую дату
cdt = datetime.datetime.now()
# получаю "вчера"
yesterday = cdt - datetime.timedelta(days=1)

# полученную дату перводу в формат   ['23', '06','21']
list_cdt = datetime.datetime.strftime(cdt, '%d %m %y').split()
list_yesterday = datetime.datetime.strftime(yesterday, '%d %m %y').split()

vdc_count_2_0 = input("Введите кол-во VDC в Public IaaS 2.0: ")
vdc_count_3_0 = input("Введите кол-во VDC в Public IaaS 3.0: ")
vdc_count_66 = input("Введите кол-во VDC в IaaS66: ")


resault_str = f"""Ежедневный отчёт за 24 часа
Период: с {int(list_yesterday[0])}.{list_yesterday[1]}.20{list_yesterday[2]} 20:30 по {int(list_cdt[0])}.{list_cdt[1]}.20{list_cdt[2]} 20:30

==========================
    #Количество клиентов
==========================
IaaS 2.0: {vdc_count_2_0}
IaaS 3.0: {vdc_count_3_0}
IaaS-66: {vdc_count_66}
==========================
    #Доступность сервисов
==========================
IaaS – 100%
BaaS – 100%
Colo – 100%
IaaS-66 – 100%
BaaS-66 – 100%
Colo-66 – 100%
CloudConnect - 100%
WAFaaS– 100%
VMaaS – 100%
DRaaS – 100%
SD-WAN – 100%
VPS – 100%
NGFW – 100%
==========================
    #CPU
==========================
Выделено клиентам, THz / Всего, THz (Переподписка):
IaaS 2.0: {dict_2_0.get("pvdc_cpu_allocation")} THz / {dict_2_0.get("pvdc_cpu_total")} THz ({dict_2_0.get("pvdc_cpu_used_procents")}%)
IaaS 3.0: {dict_3_0.get("pvdc_cpu_allocation")} THz / {dict_3_0.get("pvdc_cpu_total")} THz ({dict_3_0.get("pvdc_cpu_used_procents")}%)
IaaS-66:  {dict_66_0.get("pvdc_cpu_allocation")} THz / {dict_66_0.get("pvdc_cpu_total")} THz ({dict_66_0.get("pvdc_cpu_used_procents")}%)
==========================
    #RAM 
==========================
Выделено клиентам, TB / Всего, TB (Утилизация):
IaaS 2.0: {dict_2_0.get("pvdc_mem_allocation")} TB / {dict_2_0.get("pvdc_mem_total")} TB ({dict_2_0.get("pvdc_mem_used_procents")}%) 
IaaS 3.0: {dict_3_0.get("pvdc_mem_allocation")} TB / {dict_3_0.get("pvdc_mem_total")} TB ({dict_3_0.get("pvdc_mem_used_procents")}%)
IaaS-66: {dict_66_0.get("pvdc_mem_allocation")} TB / {dict_66_0.get("pvdc_mem_total")} TB ({dict_66_0.get("pvdc_mem_used_procents")}%)
==========================
    #Storage IaaS 2.0/3.0
==========================
Выделено клиентам, TB / Всего, TB (Переподписка)
----------------------
Huawei 18800
----------------------
Tier-1: {round((dict_2_0.get("Cloud-Tier-1")[0] + dict_3_0.get("c01-cl02-Tier-1")[0]), 2)} ({round((dict_2_0.get("Cloud-Tier-1")[0] + dict_3_0.get("c01-cl02-Tier-1")[0]) * 100 / 531, 2)}%)
Tier-2: {(dict_2_0.get("Cloud-Tier-2")[0] + dict_3_0.get("c01-cl02-Tier-2")[0])} ({round((dict_2_0.get("Cloud-Tier-2")[0] + dict_3_0.get("c01-cl02-Tier-2")[0]) * 100 / 531, 2)}%)
Tier-3: {round((dict_2_0.get("Cloud-Tier-3")[0] + dict_3_0.get("c01-cl02-Tier-3")[0]), 2)} ({round((dict_2_0.get("Cloud-Tier-3")[0] + dict_3_0.get("c01-cl02-Tier-3")[0]) * 100 / 531, 2)}%)
ИТОГО: {round(((dict_2_0.get("Cloud-Tier-1")[0] + dict_3_0.get("c01-cl02-Tier-1")[0]) + (dict_2_0.get("Cloud-Tier-2")[0] + dict_3_0.get("c01-cl02-Tier-2")[0]) + (dict_2_0.get("Cloud-Tier-3")[0] + dict_3_0.get("c01-cl02-Tier-3")[0])), 2)} / 531 ({round(((dict_2_0.get("Cloud-Tier-1")[0] + dict_3_0.get("c01-cl02-Tier-1")[0]) + (dict_2_0.get("Cloud-Tier-2")[0] + dict_3_0.get("c01-cl02-Tier-2")[0]) + (dict_2_0.get("Cloud-Tier-3")[0] + dict_3_0.get("c01-cl02-Tier-3")[0])) / 5.31, 2)}%)
----------------------
Storage Huawei 5500
----------------------
Tier-4: {round((dict_2_0.get("Cloud-Tier-4")[0] + dict_3_0.get("c01-cl02-Tier-4")[0]), 2)} / 503.8 ({round((dict_2_0.get("Cloud-Tier-4")[0] + dict_3_0.get("c01-cl02-Tier-4")[0]) * 100 / 503.8, 2)}%)
======================
 #Инциденты
======================
Не зарегистрировано
"""

if iaas66 == True:
    Tier_1_66 = input("Введите значение Tier-1 в IaaS66 в формате XX.X / XXX (XX.XX%): ")

    resault_str = resault_str + f""" 
==========================
    #Storage IaaS-66
==========================
Выделено клиентам, TB / Всего, TB (Утилизация)
----------------------
HP 3PAR 20850 SSD
----------------------
Tier-1: {Tier_1_66} - При компрессии 1.7:1
----------------------
HP 3PAR 8400 NL-SAS
----------------------
Tier-2: {dict_66_0.get("Tier-2")[0]} / 173 ({round(dict_66_0.get("Tier-2")[0] * 100 / 173, 2)}%)
Tier-3: {dict_66_0.get("Tier-3")[0]} / 332 ({round(dict_66_0.get("Tier-3")[0] * 100 / 332, 2)}%)
Tier-4: {(dict_66_0.get("Tier-4")[0])} / 300 ({round((dict_66_0.get("Tier-4")[0]) * 100 / 300, 2)}%)
ИТОГО: {round(dict_66_0.get("Tier-2")[0] + dict_66_0.get("Tier-3")[0] + +dict_66_0.get("Tier-4")[0], 2)} / 805 ({round((dict_66_0.get("Tier-2")[0] + dict_66_0.get("Tier-3")[0] + dict_66_0.get("Tier-4")[0]) * 100 / 805, 2)}%)
======================
 #Инциденты
======================
Не зарегистрировано
"""

print(resault_str)

def check_and_create_dir(dir_name):
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)


check_and_create_dir("txt")

file_name = f"txt/daily_sms_{list_cdt[0]}.{list_cdt[1]}.{list_cdt[2]}.txt"

# создание тхт с результатом + открытие блокнота с этим результатом
with open(f'{file_name}', 'w') as fp:
    fp.write(resault_str)

programName = "notepad.exe"
sp.Popen([programName, file_name])

input("Для завершения работы программы, нажмите Enter.")
