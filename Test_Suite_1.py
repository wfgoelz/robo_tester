#!/usr/bin/python3.5
# import os
import HD_Test_Tools

def test_case_1():
    ODROID = False
    VS_DEBUG = False                        # Set True if debugging with Visual Studio

    if VS_DEBUG == True:
        # Use ptvsd for remote debugging on Linux target using Visual Studio
        import ptvsd                           # Used for remote debugging of Python script using Visual Studio 2017
        ptvsd.enable_attach('my_secret')       # "my_secret" is the remote connection password.
        print('Waiting for remote debugger to attach')
        ptvsd.wait_for_attach()
        print("Attached!")

    # For Odroid only, we have head button control via GPIO
    if ODROID == True:
        from head_button_control import HEAD_BUTTON
        button = HEAD_BUTTON(1)                	# Use GPIO pin 1 for head button solenoid.

    hexOpen_cmd = '52 55'                   # Hex commands used for hub REST payload
    hexClose_cmd = '52 44'
    hexStop_cmd = '52 53'
    hexFavorite_cmd = '52 48'

    ###############################################################################################
    #                            IMPORTS
    ###############################################################################################
    import time								# Required for sleep()
    import fileinput                        # Used to access default values for hub ip address, VISA_DMM serial numbers etc.
    from HD_Test_Tools import VISA_DMM, KeysightE3642A, Hub_REST
    from laser_functions import distance_laser
    import sqlite3                          # Results logging database
    from datetime import date, datetime     # Required for timestamp entries in database.
    import json								# Required for extracting shade_id from shade list from hub.
    import base64							# Required for extracting shade_id from shade list from hub.
    from collections import namedtuple
    import dlipower                         # Required for remote IP power switch
    ###############################################################################################
    #                            READ CONFIGURATION ITEMS from config.txt
    ###############################################################################################
    # ToDo: If shades were named by test station number e.g. RoboTest#1 we could
    # api/shades, search for Robotest# and extract the shade ID fromthe response.
    # That way, a test station can be semi-permanently labeled and new shades configured
    #  for a specific station.
    # ToDO: Error trap bad/missing comport for laser

    config = {}                             # Config dictionary containing default setup values.
                                            # Test for value with:
                                            # if(config.has_key('VISA_DMM_1)):
                                            #   serial_number_1 = config['VISA_DMM_1']
    with fileinput.input('config.txt') as config_file:
        for line in config_file:
            (key,value) = line.split(':')
            config[key] = value.rstrip()

    if ODROID == True:
        laser_1_port = '/dev/ttyUSB0'           # For Linux
    else:
        laser_1_port = 'COM3'                   # For Windows overload value from config.txt

    hub_URL = 'http://' + config['HUB_IP_1'] + ':3000/api/'     # Hub 2.0   HD Office
    power_switch_IP_addr = config['POWER_SWITCH_IP_ADDR']
    database_name = config['DATABASE_NAME']
    target_shade_name = config['DUT_SHADE_NAME']
    keithley_DMM_serial_num = config['VISA_DMM_1']  # For Keithley USM DMMs, use the serial number from the data tag or rear of meter.
    keithley_DMM_USB_num = 'USB0'               # Always seems to enumerate on USB0. Not sure why.

    default_shade_id = '9999'
    shade_id = default_shade_id                 # Default value. Match will be found by comparing
                                                # DUT_SHADE_NAME defined in config.txt with shade list from hub.

    max_travel_seconds = 20                     # Seconds to wait for shade to move anywhere.
    allowable_favorite_error = 3.0              # Allowable position error in inches.

    ###############################################################################################
    #                                   INITIALIZE CONNECTIONS
    ###############################################################################################
    print("Initializing laser on port ", laser_1_port)
    laser_1 = distance_laser(laser_1_port, 'Top')   # Initialize Laser. INCLUDES Top/Bottom MOUNT FLAG

    print("Connecting to Power Switch @ ", power_switch_IP_addr)
    switch = dlipower.PowerSwitch(hostname=power_switch_IP_addr, userid='admin', password='1234')

    # Keysight 2110 USB connection on Linux. Find the USB number with ls \
    print("Initializing Keithley DMM")
    keithley_DDM1_address  = keithley_DMM_USB_num + '::0x05E6::0x2110::' + keithley_DMM_serial_num + '::INSTR'
    keithley_dmm = VISA_DMM(keithley_DDM1_address, 0.00)

    #print("Initializing Keysight E3642A Bench Power Supply")
    #ps1 = KeysightE3642A(ps1_port, 18.0, 2.0)  # Initialize power supply @ 18 Volts 2.0 Amps

    print("Opening database")
    db_conn = sqlite3.connect(database_name)
    db_cursor = db_conn.cursor()  # cursor is a quirky yet necessary object for accessing the database.
    # db_cursor.execute('SELECT * from test_results')

    print("Initializing Hub Connection @ ", hub_URL)
    hub = Hub_REST(hub_URL)                     # Initialize hub

    ###############################################################################################
    #                         Query Hub and determine ID of device under test.
    ###############################################################################################
    shade_data = hub.get_shade_list()       # Query hub to get shade data for shades on file.
    shade_list = json.loads(shade_data)         # Convert to dictionary
    for shade in shade_list['shadeData']:       # Check each shade on hub for match of target_shade_name (DUT)
        b64Name = shade['name']
        bName = base64.b64decode(b64Name)
        sName=bName.decode("utf-8")
        if sName.find(target_shade_name) != -1: # Found a match for DUT.
            shade_id = str(shade['id'])
    if shade_id == default_shade_id:
        print("WARNING! Using default shade id of ",default_shade_id)
    else:
        print("Using Shade ", target_shade_name, " with id: ",shade_id," for testing.")

    ###############################################################################################
    #                                   WRITE HEADER TO TEST DATABASE
    ###############################################################################################
    time.sleep(5)
    test_name = "Initial power up and FW read"
    firmware_rev = hub.get_firmware_revision(shade_id)
    print("Shade reports it is running firmware version ",firmware_rev)

    now = datetime.now()
    result = 'PASS'
    details = 'NONE'
    db_cursor.execute(
        '''INSERT INTO basic_ops_test (Date_time,Firmware_Rev,Test_Name,Result,Details) VALUES(?,?,?, ?, ?)''',
        (now, firmware_rev, test_name, result, details,))
    db_conn.commit()

    # Execute firmware update if requested in config.txt file.
    if config['FORCE_FIRMWARE_UPDATE'] == 'TRUE':
        print('Updating firmware before continuing')
        hub.start_OTA_update(shade_id,config['FIRMWARE_INDEX'])   # FIRMWARE_INDEX is read from the config.txt file.
        time.sleep(240)                      # Wait four minutes for update.
        firmware_rev = hub.get_firmware_revision(shade_id)
        print("After update, shade reports it is running firmware version ",firmware_rev)
    else:
        print('No firmware update attempted')

#################################################
def test_case_2():
    print("Running test_case_2")
    return (2)

#################################################
def test_case_3():
    result = 3
    print("Running Test Case 3")
    return (result)
