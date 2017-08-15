#!/usr/bin/python3.5
# import os
import HD_Test_Tools

def Position_Drift_Test():
    ODROID = True
    VS_DEBUG = False                        # Set True if debugging with Visual Studio

    # For Odroid only, we have head button control via GPIO
    if ODROID == True:
        from head_button_control import HEAD_BUTTON
        button = HEAD_BUTTON(21)            # Use GPIO pin 1 for head button solenoid.

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
    # from collections import namedtuple
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

    hub_URL = 'http://' + config['HUB_IP_1'] + '/api/'     # Hub 2.0   HD Office
    power_switch_IP_addr = config['POWER_SWITCH_IP_ADDR']
    database_name = config['DATABASE_NAME']
    target_shade_name = config['DUT_SHADE_NAME']
    keithley_DMM_serial_num = config['VISA_DMM_1']  # For Keithley USM DMMs, use the serial number from
                                                    #  the data tag or rear of meter.
    keithley_DMM_USB_num = 'USB0'                   # Always seems to enumerate on USB0. Not sure why.

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

    scenes = {"Open": "44051",
              "Top Mid": "57236",
              "Mid": "8832",
              "Low": "8014",
              "Closed": "33766",
              }

    right_target_in = {"Open": 2.008,  # Target is the desired rail position in inches for each scene
                       "Top Mid": 16.575,
                       "RT_UP LT_DN": 16.575,
                       "LT_UP RT_DN": 71.417,
                       "Mid": 47.220,
                       "Bad Scene": 99.99,
                       "Low": 71.417,
                       "Closed": 83.937
                       }
    left_target_in = {"Open": 2.441,  # Target is the desired rail position in inches for each scene
                      "Top Mid": 15.512,
                      "RT_UP LT_DN": 70.315,
                      "LT_UP RT_DN": 15.512,
                      "Mid": 25.354,
                      "Bad Scene": 99.99,
                      "Low": 70.315,
                      "Closed": 43.346
                      }
    position_tolerance_in = .25  # Acceptable position tollerance in +- inches.
    max_idle_current = .000080  # Current must be < 80 uA to pass idele current test
    dwell_time = 30  # Wait 120 seconds between scene moves so as to not toast the gearboxes

    ############################################################################################
    # Scene_runner
    ############################################################################################
    def scene_runner(target_scene_name):
        shade_name = "test shade"
        print("\r\n\nRunning scene: " + target_scene_name)
        hub.run_scene(scenes[target_scene_name])
        time.sleep(dwell_time)
        print("Measuring current.")
        average_current = keithley_dmm.calc_average_current()
        if average_current > max_idle_current:
            print("Sleep current test FAILED. Avg. current of %6.6f A exceeds 80uA" % average_current)
            sleep_current_result = False
        else:
            print("Sleep current test PASSED. Avg. current was %6.6f A" % average_current)
            sleep_current_result = True

        actual_position_in = laser_1.read_distance()
        desired_position_in = left_target_in[target_scene_name]
        deviation_in = desired_position_in - actual_position_in
        print("Target position = %6.3f and actual position = %6.3f inches" % (desired_position_in, actual_position_in))
        if abs(deviation_in) < position_tolerance_in:
            print("Deviation = %6.3f in." % deviation_in)
            print("PASS: Position in range")
            position_test_result = True
        else:
            print("Deviation = %6.3f in." % deviation_in)
            print("FAIL: Position out of range")
            position_test_result = False

        pass_number = loop
        now = datetime.now()
        db_cursor.execute(
            '''INSERT INTO scene_runner (Run_Time,Shade_Name,Current_Test_Passed,Average_Current,Position_Test_Passed,Pass_Number,Scene_Name, Target_Distance, Deviation,Scene_ID) VALUES(?,?,?, ?, ?, ?, ?, ?, ?, ?)''',
            (now, shade_name, sleep_current_result, average_current, position_test_result, pass_number,
             target_scene_name, desired_position_in, deviation_in, scenes[target_scene_name],))
        db_conn.commit()

    def dual_scene_runner(target_scene_name):

        print("\r\n\nRunning scene: " + target_scene_name)
        pass_number = loop
        hub.run_scene(scenes[target_scene_name])
        time.sleep(dwell_time)  # Allow time to run to scene and settle
        print("Measuring Left current.")
        average_current = left_dmm.calc_average_current()
        if average_current > max_idle_current:
            print("Left Sleep current test FAILED. Avg. current of %6.6f A exceeds 80uA" % average_current)
            sleep_current_result = False
        else:
            print("Left Sleep current test PASSED. Avg. current was %6.6f A" % average_current)
            sleep_current_result = True

        print("Measuring Left Distance.")
        actual_position_in = laser_1.read_distance()
        desired_position_in = left_target_in[target_scene_name]
        deviation_in = desired_position_in - actual_position_in
        print("Target position = %6.3f and actual position = %6.3f inches" % (desired_position_in, actual_position_in))
        if abs(deviation_in) < position_tolerance_in:
            print("Deviation = %6.3f in." % deviation_in)
            print("PASS: Position in range")
            position_test_result = True
        else:
            print("Deviation = %6.3f in." % deviation_in)
            print("FAIL: Position out of range")
            position_test_result = False

        now = datetime.now()
        shade_name = "Left Shade"
        db_cursor.execute(
            '''INSERT INTO scene_runner (Run_Time,Shade_Name,Current_Test_Passed,Average_Current,Position_Test_Passed,Pass_Number,Scene_Name, Target_Distance, Deviation,Scene_ID) VALUES(?,?,?, ?, ?, ?, ?, ?, ?, ?)''',
            (now, shade_name, sleep_current_result, average_current, position_test_result, pass_number,
             target_scene_name, desired_position_in, deviation_in, scenes[target_scene_name],))
        db_conn.commit()

        print("Measuring Right current.")
        average_current = right_dmm.calc_average_current()
        if average_current > max_idle_current:
            print("Right Sleep current test FAILED. Avg. current of %6.6f A exceeds 80uA" % average_current)
            sleep_current_result = False
        else:
            print("Right Sleep current test PASSED. Avg. current was %6.6f A" % average_current)
            sleep_current_result = True

        print("Measuring Right Distance.")
        actual_position_in = right_laser.read_distance()
        desired_position_in = right_target_in[target_scene_name]
        deviation_in = desired_position_in - actual_position_in
        print("Target position = %6.3f and actual position = %6.3f inches" % (desired_position_in, actual_position_in))
        if abs(deviation_in) < position_tolerance_in:
            print("Deviation = %6.3f in." % deviation_in)
            print("PASS: Position in range")
            position_test_result = True
        else:
            print("Deviation = %6.3f in." % deviation_in)
            print("FAIL: Position out of range")
            position_test_result = False

        now = datetime.now()
        shade_name = "Right Shade"
        db_cursor.execute(
            '''INSERT INTO scene_runner (Run_Time,Shade_Name,Current_Test_Passed,Average_Current,Position_Test_Passed,Pass_Number,Scene_Name, Target_Distance, Deviation,Scene_ID) VALUES(?,?,?, ?, ?, ?, ?, ?, ?, ?)''',
            (now, shade_name, sleep_current_result, average_current, position_test_result, pass_number,
             target_scene_name, desired_position_in, deviation_in, scenes[target_scene_name],))
        db_conn.commit()

    # ###############################################################
    #       TEST EACH SCENE IN SCENES. LOOP AS DESIRED.
    #################################################################
    # psVoltage = 18.0  # Initial test value, can be reset as desired
    # ps1.powerON()  # Remote control for Keysight E3642A Bench Supply
    # time.sleep(5)  # Allow shade to power up

    loop = 1
    # switch.on(8)
    while loop <= 5:
        # results are displayed on console and logged to database
        # NOTE: Operation pauses for dwell_time after the move before measurements are taken.

        # print("\r\n\nRunning scene MID with power fail\r\n")
        # hub.run_scene(scenes["Mid"])    #Returns immediately
        # time.sleep(4)
        # switch.off(8)                   # Kill power while moving to Closed position
        # time.sleep(5)                   # 5 Seconds should be enough to disipate power.
        # switch.on(8)
        # time.sleep(5)                   # Allow time to boot.
        scene_runner("Open")  # Returns when move is complete. Logs status.
        scene_runner("Mid")
        scene_runner("Closed")
        scene_runner("Mid")
        loop += 1
        # ps1.powerOFF()
        # time.sleep(10)
        # psVoltage -= .5  # Decrease by .5 volts after each loop
        # ps1.setVolt_Current(psVoltage, 2.0)
        # ps1.powerON()
        # time.sleep(5)

    # ps1.powerOFF()  # Remote control for Keysight E2A Bench Supply
    print("TEST COMPLETE!")
    return "PASSED"                         # Report test result to Test Rail


#################################################
def test_case_2():
    print("Running test_case_2")
    return "PASSED"                         # Report test result to Test Rail

#################################################
def test_case_3():
    result = 3
    print("Running Test Case 3")
    return "FAILED"                         # Report test result to Test Rail
