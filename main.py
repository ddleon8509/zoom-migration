#!/usr/bin/env python3

import sys
import zoom
from cucm import get_report

# ./zoom.py --get report
# ./zoom.py --get port
# ./zoom.py --get zoom-users
# ./zoom.py --get zoom-phone-users
# ./zoom.py --get zoom-phone-number
# ./zoom.py --get get-number-status

# ./zoom.py --set users
# ./zoom.py --set user?number=+13057800769,user=ddelgadoleon

#-------------Script options-------------#

if __name__ == "__main__":
  option = sys.argv[1]
  param = sys.argv[2]
  print('INFO: Script Started')
  if option == '--get':
    if param == 'report':
        get_report()
        print('INFO: Script Finished\n')
    elif param == 'port':
        zoom.get_phone_numbers()
        zoom.get_port()
        zoom.notify_port()
        print('INFO: Script Finished\n')
    elif param == 'zoom-users':
        zoom.get_users()
        print('INFO: Script Finished\n')
    elif param == 'zoom-phone-user':
        zoom.get_phone_users()
        print('INFO: Script Finished\n')
    elif param == 'zoom-phone-number':
        zoom.get_phone_numbers()
        print('INFO: Script Finished\n')
    elif param == 'get-number-status':
        zoom.get_numbers_status()
        print('INFO: Script Finished\n')
    else:
        print('ERROR: Param not supported\n')
  elif option == '--set':
    if param == 'users':
        zoom.set_users()
        print('INFO: Script Finished\n')
    elif param.split('?')[0] == 'user':
        zoom.set_user_from_file(param.split('?')[1].split(',')[0].split('=')[1], param.split('?')[1].split(',')[1].split('=')[1])
        print('INFO: Script Finished\n')
    else:
        print('ERROR: Param not supported\n')
  else:
    print('ERROR: Option not supported\n')