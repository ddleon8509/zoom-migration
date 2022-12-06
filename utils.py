#!/usr/bin/env python3
import csv
import json
import os
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def read_json_file(name):
	os.chdir("/home/ddelgadoleon/Projects/zoom-migration")
	with open(os.getcwd() + name[1:], 'r') as f:
		return json.load(f)

# Loading private parameters

email = read_json_file('./configs/email.json')

def write_json_file(name, data):
	os.chdir("/home/ddelgadoleon/Projects/zoom-migration")
	with open(os.getcwd() + name[1:], 'w+') as f:
		json.dump(data, f)

def logging(file, log):
	timestamp = datetime.now().strftime('%m%d%Y%H%M%S')
	print(f'{timestamp} {log}')
	with open(file, 'a+') as f:
		f.write(f'{timestamp} {log}\n')

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def csv_to_json(csv_path):
	os.chdir("/home/ddelgadoleon/Projects/zoom-migration")
	jsonArray = [] 
	with open(os.getcwd() + csv_path[1:], encoding='utf-8') as csvf: 
		csvReader = csv.DictReader(csvf) 
		for row in csvReader: 
			jsonArray.append(row)
	return jsonArray

def html_parser(data):
	with open('template.html', 'r', encoding='utf-8') as f:
		html = f.read()
	index = html.find('<!--number-->')
	html = html[:index] + str(len(data)) + html[index:]
	index = html.find('<!--begin-->')
	for i in data:
		seq = ''
		seq = '<td>' + i['zoom_number']['number'] + '</td><td>' + i['zoom_number']['extension']['extension_number'] + '</td><td><ul>'
		for j in i['warnings']:
			seq = seq + '<li>' + j['message'] + '</li>'
		seq = seq + '</ul></td>'
		html = html[:index] + '<tr class="underlined-row">' + seq + '</tr>' + html[index:]
	return html

def send_email(body):
	from_addr = 'no-reply@fsw.edu'
	msg = MIMEMultipart('alternative')
	msg['Subject'] = 'Zoom port number status report'
	msg['From'] = from_addr
	msg.attach(MIMEText(body, 'html'))
	s = smtplib.SMTP(host = email['smtp']['url'], port = email['smtp']['port'])
	logging('./logs/email.log', 'Connected to SMTP server')
	for to_addr in email['to_addrs']:
		msg['To'] = to_addr
		s.sendmail(from_addr, to_addr, msg.as_string())
	logging('./logs/email.log', 'Email sent completed')
	s.quit()