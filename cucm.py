#!/usr/bin/env python3

from zeep import Client, Plugin, Settings
from zeep.cache import SqliteCache
from zeep.exceptions import Fault
from zeep.plugins import HistoryPlugin
from zeep.transports import Transport
from requests import Session
from requests.auth import HTTPBasicAuth
from xml import etree
import urllib3
from urllib.parse import uses_query
import time
import csv
from utils import read_json_file, write_json_file, logging, chunks, csv_to_json
from net import get_mac_table, get_location

# Loading private parameters

cucm = read_json_file('./configs/cucm.json')
did =read_json_file('./configs/did.json')

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class axl(object):
    def __init__(self, username = cucm['username'], password = cucm['password'],cucm = cucm['ipaddr']):
        self.history = HistoryPlugin()

        wsdl = 'AXLAPI.wsdl'
        session = Session()
        session.verify = False
        session.auth = HTTPBasicAuth(username, password)
        transport = Transport(cache = SqliteCache(), session = session, timeout = 20)
        axl_client = Client(wsdl, transport = transport, plugins = [self.history])
        self.service = axl_client.create_service('{http://www.cisco.com/AXLAPIService/}AXLAPIBinding', f'https://{cucm}:8443/axl/')

    def show_history(self):
        for item in [self.history.last_sent, self.history.last_received]:
            logging('./logs/axl.log', etree.tostring(item["envelope"], encoding="unicode", pretty_print=True))

    def get_phone_name_list(self):
        PhoneList = []
        try:
            resp = self.service.listPhone(searchCriteria={'name': '%'}, returnedTags={'name':''})
            for device in resp['return'].phone:
                PhoneList.append(device.name)
            return PhoneList
        except Fault:
            self.show_history()

class ris(object):
    def __init__(self, username = cucm['username'], password = cucm['password'],cucm = cucm['ipaddr']):
        wsdl = 'https://' + cucm + ':8443/realtimeservice2/services/RISService70?wsdl'
        session = Session()
        session.verify = False
        session.auth = HTTPBasicAuth(username, password)
        settings = Settings(strict = False, xml_huge_tree = True)
        transport = Transport(session = session, timeout = 10, cache = SqliteCache())
        ris_client = Client(wsdl, settings = settings, transport = transport)
        self.service = ris_client.create_service('{http://schemas.cisco.com/ast/soap}RisBinding', f'https://{cucm}:8443/realtimeservice2/services/RISService70')


    def get_registered_phones(self, phone_mac_list):
        status_phone_list = []
        querylimit = 1000                                               # Maximun amount of devices returned in 1 API call
        phone_mac_list = list(chunks(phone_mac_list, querylimit))
        i = 0
        for batch_of_phones in phone_mac_list:
            i += 1
            batch_phone_results_list = []
            CmSelectionCriteria = {
                'MaxReturnedDevices': querylimit,
                'DeviceClass': 'Any',
                'Model': '255',                                         # Any model
                'Status': 'Any',
                'NodeName': '',
                'SelectBy': 'Name',
                'SelectItems': {
                    'item': batch_of_phones
                },
                'Protocol': 'Any',
                'DownloadStatus': 'Any'
            }
            try:
                resp = self.service.selectCmDeviceExt(CmSelectionCriteria = CmSelectionCriteria, StateInfo = '')
            except Fault:
                logging('./logs/ris.log', 'ERROR: Problem querying the RIS API')

            CmNodes = resp.SelectCmDeviceResult.CmNodes.item
            for CmNode in CmNodes:
                if len(CmNode.CmDevices.item) > 0:
                    for item in CmNode.CmDevices.item:
                        item['PubName'] = CmNode.Name
                        batch_phone_results_list.append(item)
            status_phone_list += batch_phone_results_list

            if(len(phone_mac_list) != i):
                time.sleep(10)                                          # delay a little in between querying Serviceability to prevent overloading system
        return status_phone_list


def get_extension(phone):
    if did[phone[:-2] + "00"]:
        return {"extension_number": did[phone[:-2] + "00"] + phone[-2:]}
    else:
        return 'ExtensionOutOfRange'

def get_did(extension):
    for i in did.items():
        if i[1] == extension[:-2]:
          return f'{i[0][:-2] + extension[-2:]}'
    return 'DIDOutOfRange'

def lookup_report(extension):
    info = []
    data = read_json_file('./data/report.json')
    for item in data:
        if item['ActiveDirectoryLine'] == extension:
            info.append(item)
        elif item['CUCMPhones']:
            for phone in item['CUCMPhones']:
                if extension in phone['CUCMLines']:
                    info.append(item)
    return info

def get_report():
    data_list = []
    processed_dev = []
    cucm_data = ris().get_registered_phones(axl().get_phone_name_list())
    active_directory_data = csv_to_json('./data/ad-users.csv')
    mac_table = get_mac_table()
    for user in active_directory_data:

        # Active AD Users 
        
        data_item = {}
        data_item['ActiveDirectoryName'] = user['Name']
        data_item['ActiveDirectoryUsername'] = user['samaccountname']
        data_item['ActiveDirectoryMail'] = user['mail']
        data_item['ActiveDirectoryLine'] = user['ipPhone']
        data_item['ActiveDirectoryDepartment(FieldNotTrusted)'] = user['department']
        data_item['CUCMdid'] = ''
        data_item['CUCMPhones'] = []

        # Active AD user with IpPhone field

        if user['ipPhone']:
            data_item['CUCMdid'] = get_did(user['ipPhone'])
            for phone in cucm_data:
                if phone['LinesStatus']:
                    for line in phone['LinesStatus']['item']:
                        if user['ipPhone'] == line['DirectoryNumber']:
                            data_item['CUCMPhones'].append({
                                'CUCMDeviceClass': phone['DeviceClass'],
                                'CUCMPhoneName': phone['Name'],
                                'CUCMLines': [i['DirectoryNumber'] for i in phone['LinesStatus']['item']],
                                'CUCMModel': phone['Model'],
                                'CUCMDescription(FieldNotTrusted)': phone['Description'],
                                'CUCMIPAddr': phone['IPAddress']['item'][0]['IP'],
                                'NetLocation': get_location(phone['Name'], mac_table)
                            })
                            processed_dev.append(phone['Name'])
                            break
        data_list.append(data_item)

    # CUCM phones not linked to a AD User

    for phone in cucm_data:
        if phone['Name'] not in processed_dev:
            data_item = {}
            data_item['ActiveDirectoryName'] = ''
            data_item['ActiveDirectoryUsername'] = ''
            data_item['ActiveDirectoryMail'] = ''
            data_item['ActiveDirectoryLine'] = ''
            data_item['ActiveDirectoryDepartment(FieldNotTrusted)'] = ''
            data_item['CUCMdid'] = ''
            data_item['CUCMPhones'] = []
            data_item['CUCMPhones'].append({
                'CUCMDeviceClass': phone['DeviceClass'],
                'CUCMPhoneName': phone['Name'],
                'CUCMModel': phone['Model'],
                'CUCMDescription(FieldNotTrusted)': phone['Description'],
                'NetLocation': get_location(phone['Name'], mac_table)
            })
            if phone['IPAddress']:
                data_item['CUCMPhones'][0]['CUCMIPAddr'] = phone['IPAddress']['item'][0]['IP']
            else:
                data_item['CUCMPhones'][0]['CUCMIPAddr'] = 'NotAvailable'
            if phone['LinesStatus']:
                data_item['CUCMPhones'][0]['CUCMLines'] = [i['DirectoryNumber'] for i in phone['LinesStatus']['item']]
            else:
                data_item['CUCMPhones'][0]['CUCMLines'] = []
            data_list.append(data_item)            

    # Validating multiples AD Users with the same extension and CUCM Phone Line in multiples phones

    for x in range(len(data_list)):
        data_list[x]['CUCMWarnings'] = []
        if data_list[x]['CUCMPhones']:
            adlmp = [i['CUCMPhoneName'] for i in data_list[x]['CUCMPhones'] if i['CUCMPhoneName'].startswith('SEP')]
        if data_list[x]['ActiveDirectoryUsername'] and data_list[x]['ActiveDirectoryLine']:
            adld = []
            adld.append(data_list[x]['ActiveDirectoryUsername'])
            for data in data_list:
                if data['ActiveDirectoryUsername'] and data['ActiveDirectoryLine']:
                    if data_list[x]['ActiveDirectoryLine'] == data['ActiveDirectoryLine']:
                        if data_list[x]['ActiveDirectoryUsername'] != data['ActiveDirectoryUsername']:
                            adld.append(data['ActiveDirectoryUsername'])
            if len(adld) > 1:
                data_list[x]['CUCMWarnings'].append ({ 'code': 0, 'message': f'WARNING: Duplicated active directory line. Users: ({adld})'})    # Tested OK
            if len(adlmp) > 1:
                data_list[x]['CUCMWarnings'].append({ 'code': 1, 'message': f'WARNING: Duplicated CUCM line. Phones: ({adlmp})'})               # Tested OK

    write_json_file('./data/report.json', data_list)
    
    # Generating CSV file 

    header = [
        'ActiveDirectoryName',
        'ActiveDirectoryUsername',
        'ActiveDirectoryMail',
        'ActiveDirectoryLine',
        'ActiveDirectoryDepartment(FieldNotTrusted)',
        'CUCMWarnings',
        'CUCMdid'
    ]
    header_plus = [
        'CUCMDeviceClass',
        'CUCMPhoneName',
        'CUCMLines',
        'CUCMModel',
        'CUCMDescription(FieldNotTrusted)',
        'CUCMIPAddr',
        'NetLocation'
    ]
    max = 0
    for i in data_list:
        if len(i['CUCMPhones']) > max:
            max = len(i['CUCMPhones'])
    
    for i in range(max):
        for j in header_plus:
            header.append(j + str(i)) 

    with open('./data/report.csv', 'w', encoding='UTF8') as f:  
        writer = csv.writer(f)
        writer.writerow(header)
        for i in data_list:
            row = []
            row.append(i['ActiveDirectoryName'])
            row.append(i['ActiveDirectoryUsername'])
            row.append(i['ActiveDirectoryMail'])
            row.append(i['ActiveDirectoryLine'])
            row.append(i['ActiveDirectoryDepartment(FieldNotTrusted)'])
            row.append(i['CUCMWarnings'])
            row.append(i['CUCMdid'])
            if i['CUCMPhones']:
                for j in i['CUCMPhones']:
                    row.append(j['CUCMDeviceClass'])
                    row.append(j['CUCMPhoneName'])
                    if j['CUCMLines']:
                        row.append(j['CUCMLines'])
                    else:
                        row.append('')
                    row.append(j['CUCMModel'])
                    row.append(j['CUCMDescription(FieldNotTrusted)'])
                    row.append(j['CUCMIPAddr'])
                    row.append(j['NetLocation'])
            writer.writerow(row)