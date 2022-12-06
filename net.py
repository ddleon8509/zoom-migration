#!/usr/bin/env python3
import re
from netmiko import ConnectHandler
from utils import read_json_file

net = read_json_file('./configs/net.json')

def get_building(campus, interface):
    for i in net:
        if i['campus'] == campus:
            return i['locations'][interface]

def get_location(name, mac_table):
    mac = '.'.join(name[i:i + 4] for i in range(3, len(name), 4)).lower()     # MAC addr with xxxx.xxxx.xxxx format
    for i in mac_table:
        for j in i['table']:
            if mac == j[0]:
                return f'{i["campus"]}-{get_building(i["campus"], j[1])}'
    return 'NotFound'

def get_mac_table():
    mac_table = []
    for i in net:
        table = []
        dev = i['credential']
        with ConnectHandler(**dev) as net_connect:
            output = net_connect.send_command(f'sh mac addr dynamic')
        if i['campus'] == 'coll':
            table = re.findall(r'([0-9a-f.]+)\s+\w+\s+[a-z, ]+(\w+\/\d+)', output)
            mac_table.append({'campus': 'coll', 'table': table})
        else:
            table = re.findall(r'([0-9a-f.]+)\s+\w+\s+(\w+\/\d\/\d+)', output)
            mac_table.append({'campus': i['campus'], 'table': table})
    return mac_table