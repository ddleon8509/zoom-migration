#!/usr/bin/env python3
import json
import time
import requests
import glob
import shutil
from utils import logging, read_json_file, write_json_file, html_parser, send_email
from cucm import get_extension, get_report, lookup_report, get_did

# Loading private parameters

headers = read_json_file('./configs/headers.json')
feature = read_json_file('./configs/feature.json')
calling_plans = read_json_file('./configs/calling_plans.json')

# Creating log file for Zoom API calls.

def get_log_path(resource):
    name = resource.split('v2/')[1].replace('/', '-')
    return f'./logs/{name}.log'

# Return a list of json objects returned by the API.

def get_bulk(resource, key):
    next_page_token = 'token'
    temp = []
    logfile = get_log_path(resource)
    while next_page_token:
        if next_page_token == 'token':
            url = f'{resource}?page_size=300'
        else:
            url = f'{resource}?page_size=300&next_page_token={next_page_token}'
        logging(logfile, f'INFO: GET request to {url}')
        response = requests.get(url, headers=headers)       
        if response.status_code == 200:
            data = response.json()
            temp.extend(data[key])
            next_page_token = data['next_page_token']
            logging(logfile, 'INFO: Batch copied successfully')
        else:
            logging(logfile, f'ERROR: Batch was not copied successfully. Response code {response.status_code}')
            break
    return temp

# Save the list of Zoom users at ./data/zoom-users.json file

def get_users():
    write_json_file('./data/zoom-users.json', get_bulk('https://api.zoom.us/v2/users', 'users'))

def get_phone_users():
    write_json_file('./data/zoom-phone-users.json', get_bulk('https://api.zoom.us/v2/phone/users', 'users'))

def get_phone_numbers():
    write_json_file('./data/zoom-phone-numbers.json', get_bulk('https://api.zoom.us/v2/phone/numbers', 'phone_numbers'))

def get_sites():
    write_json_file('./data/zoom-sites.json', get_bulk('https://api.zoom.us/v2/phone/sites', 'sites'))

# Return the user id if the user exist in Zoom or an empty string

def get_user_id(username):
    user_list = read_json_file('./data/zoom-users.json')
    for user in user_list:
        if user['email'] == f'{username}@fsw.edu':
            return user['id']
    return ''

def get_user(id):
    response = requests.get(f'https://api.zoom.us/v2/users/{id}', headers=headers)       
    if response.status_code == 200:
        return response.json()
    else:
        return {}

# Find the id related with the full number(phone funct param) 
# and return the dict {"phone_numbers": [{"id": "XXXXXXX", "number": "XXXXXXXXXX"}
# This dict converted to json with json.dumps() is payload requested 
# for the API https://api.zoom.us/v2/phone/users/userID/phone_numbers

def get_number_id(number):
    phone_numbers = read_json_file('./data/zoom-phone-numbers.json')
    for phone_number in phone_numbers:
        if phone_number['number'] == number:
            return {"phone_numbers": [{"id": phone_number['id'], "number": number}]}
    return {}

def get_site_id(site_code):
    sites_list = read_json_file('./data/zoom-sites.json')
    for site in sites_list:
        if site['site_code'] == int(site_code):
            return site['id']
    return ''      

# Set Zoom info

def set(verb, resource, logfile, response_code, data):
    logging(logfile, f'INFO: {verb} request to {resource}')
    response = requests.request(verb, resource, headers = headers, data = data)
    if response.status_code == response_code:
        logging(logfile, f'INFO: {resource} processed successfully')
        return True
    else:
        logging(logfile, f'ERROR: {verb} {resource}: Response code {response.status_code}')
        return False

#-----------------------------------Get port status-----------------------------------#
# After the initial port step, print the number that are availables

# Update files inside ./data/port/pending if numbers went from any state to available state (Not Tested)
def get_numbers_status():
    response = dict()
    number_list = list()
    file_list = glob.glob('./data/port/pending/*.*')
    for filename in file_list:
        data = read_json_file(filename)
        if data['zoom_number']['status'] != 'available':
            response = requests.get(f'https://api.zoom.us/v2/phone/numbers/{data["zoom_number"]["id"]}', headers=headers)      
        if response.status_code == 200:
            update_data = response.json()
            if update_data['status'] == 'available':
                data['zoom_number']['status'] = 'available'
                temp = [i for i in data['warnings'] if i['code'] != 6]
                data['warnings'] = temp
                write_json_file(filename, data)
                number_list.append(data["zoom_number"]["number"])
    if number_list:
        send_email(f'Number {number_list} is available to be configure.')

def get_port():
    phone_number_list = read_json_file('./data/zoom-phone-numbers.json')
    current_phone_id_list = read_json_file('./data/port-live-status.json')
    for i in phone_number_list:
        if i['id'] not in current_phone_id_list:
            data = check_port(i)
            write_json_file(f'./data/port/new/{i["number"]}.json', data)
            current_phone_id_list.append(i['id'])
            write_json_file('./data/port-live-status.json', current_phone_id_list)

def notify_port():
    file_list = glob.glob('./data/port/new/*.*')
    data = list()
    for filename in file_list:
        data.append(read_json_file(filename))
        shutil.move(filename, f'./data/port/pending/{filename.split("/")[-1]}')  
    if data:
        send_email(html_parser(data))

def update_port():
    file_list = glob.glob('./data/port/pending/*.*')
    data = list()
    for filename in file_list:
        data.append(read_json_file(filename))
    if data:
        send_email(html_parser(data)) 

def check_port(number):
    data = dict()
    data['zoom_number'] = number
    data['zoom_number']['extension'] = get_extension(number['number'][2:])
    data['fsw_ref'] = lookup_report(data['zoom_number']['extension']['extension_number'])               # return all AD users with that extension and all the CUCM phones with that extension
    data['zoom_users'] = list()
    data['warnings'] = list()
    if data['fsw_ref']:      
        for record in data['fsw_ref']:
            # Moving 'CUCMWarnings' to 'warnings' 
            for w in record['CUCMWarnings']:
                data['warnings'].append(w)
            record.pop('CUCMWarnings')
            #-----------------------------------
            if record['ActiveDirectoryUsername']:
                user_id = get_user_id(record['ActiveDirectoryUsername'])
                if user_id:
                    data['zoom_users'].append(get_user(user_id))
                else:
                    data['warnings'].append({ 'code': 3, 'message': f'WARNING: User {record["ActiveDirectoryUsername"]}@fsw.edu not available in Zoom'})                                            # Tested OK
            else:
                data['warnings'].append({ 'code': 5, 'message': f'INFO: Common area phone number or unassigned phone number {data["zoom_number"]["extension"]["extension_number"]} available'})     # Tested OK
    else:
        data['warnings'].append({ 'code': 4, 'message': f'INFO: Not FSW reference number {data["zoom_number"]["extension"]["extension_number"]}. Number available in Zoom'})                        # Tested OK

    if data['zoom_number']['status'] != 'available':
        data['warnings'].append({ 'code': 6, 'message': f'WARNING: Zoom number {number["number"]} pending to port'})                                                                                # Tested OK

    if data['zoom_users']:
        if len(data['zoom_users']) == 1:
            data['warnings'].append({ 'code': 7, 'message': f'INFO: Single Zoom user: {data["zoom_users"][0]["email"]} linked to {data["zoom_number"]["extension"]["extension_number"]}'})          # Tested OK
    #Removing warnings redundacy
    temp = list()
    dup = list()
    for w in range(len(data['warnings'])):
        if data['warnings'][w]['code'] in temp:
            dup.append(w)
        else:
            temp.append(data['warnings'][w]['code'])
    for w in dup:
        data['warnings'].pop(w)
    #---------------------------
    return data
        
#-----------------------------------End get port status-----------------------------------#

#-----------------------------------Set phone capabilities-----------------------------------#
def set_user(user_id, phone):
    # Adding phone features
    if set('patch', f'https://api.zoom.us/v2/users/{user_id}/settings', f'./logs/{phone}.log', 204, json.dumps(feature)):
        time.sleep(5)       # Delay to permit zoom update db of users

        # Adding calling plans
        if set('post', f'https://api.zoom.us/v2/phone/users/{user_id}/calling_plans', f'./logs/{phone}.log', 201, json.dumps(calling_plans)):

            # Changing extension
            # e164toextension = get_extension(phone[2:])
            # e164toextension['site_id'] = get_site_id(e164toextension['extension_number'][0])
            # if set('patch', f'https://api.zoom.us/v2/phone/users/{user_id}', f'./logs/{phone}.log', 204, json.dumps(e164toextension)):

            # Adding number
            number_id = get_number_id(phone)
            if number_id:
                if set('post', f'https://api.zoom.us/v2/phone/users/{user_id}/phone_numbers', f'./logs/{phone}.log', 201, json.dumps(number_id)):
                    return True
                else:
                    logging(f'./logs/{phone}.log', f'ERROR: Adding full number. UserID: {user_id}. Phone: {phone}')

            # else:
                # logging(f'./logs/{phone}.log', f'ERROR: Changing extension. UserID: {user_id}. Phone: {phone}')
        else:
            logging(f'./logs/{phone}.log', f'ERROR: Adding calling plans. UserID: {user_id}. Phone: {phone}')
    else:
        logging(f'./logs/{phone}.log', f'ERROR: Adding phone features. UserID: {user_id}. Phone: {phone}')
    return False

def set_user_from_file(filename, username):
    # data = read_json_file(f'./data/port/pending/{filename}.json')
    # if set_user(get_user_id(username), data['zoom_number']['number']):
        # shutil.move(f'./data/port/pending/{filename}.json', f'./data/port/processed/{filename}.json')
        # logging(f'./logs/{data["zoom_number"]["number"]}.log', f'INFO: {data["zoom_number"]["number"]} assigned successfully to {username}')
    # else:
        # logging(f'./logs/{data["zoom_number"]["number"]}.log', f'ERROR: {data["zoom_number"]["number"]} pending to config due errors')

    if set_user(get_user_id(username), filename):
        print(f'./logs/{filename}.log', f'INFO: {filename} assigned successfully to {username}')
    else:
        print(f'./logs/{filename}.log', f'ERROR: {filename} not assigned successfully to {username}')


# def create_commmon():
#     print('Creating common area')

# def set_common():
#     print('Setting common area phone...')

# def set_common_from_file():
#     print('Setting common area phone from file...')

def set_users():
    file_list = glob.glob('./data/port/pending/*.*')
    for filename in file_list:
        data = read_json_file(filename)
        # Users without warnings
        if len(data['warnings']) == 1 and data['warnings'][0]['code'] == 7:
            if set_user(data['zoom_users'][0]['id'], data['zoom_number']['number']):
                shutil.move(filename, f'./data/port/processed/{filename.split("/")[-1]}')
                logging(f'./logs/{data["zoom_number"]["number"]}.log', f'INFO: {data["zoom_number"]["number"]} assigned successfully to {data["zoom_users"][0]["email"]}')  
        # Number availables in Zoom without any pending config
        elif len(data['warnings']) == 1 and data['warnings'][0]['code'] == 4:
            shutil.move(filename, f'./data/port/processed/{filename.split("/")[-1]}')
            logging(f'./logs/{data["zoom_number"]["number"]}.log', f'INFO: {data["zoom_number"]["number"]} available in Zoom after porting. No further config needed')
        #Number for common areas phones
        # elif len(data['warnings']) == 1 and data['warnings'][0]['code'] == 5:
        #     if set_common():
        #         shutil.move(filename, f'./data/port/processed/{filename.split("/")[-1]}')
        #         logging(f'./logs/{data["zoom_number"]["number"]}.log', f'INFO: {data["zoom_number"]["number"]} assigned successfully to a common area')
        else:
            logging(f'./logs/{data["zoom_number"]["number"]}.log', f'INFO: {data["zoom_number"]["number"]} pending to config due warnings')

#-----------------------------------End set phone capabilities-----------------------------------#