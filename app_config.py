# Use this file to store all the configuration variables for the application
# This will allow for easy configuration of the application
# TODO: Refactor to use this file for all configuration variables

BIKE = {
    'ID': '000001'
}
MQTT = {
    'HOST': 'localhost',
    'USER': '',
    'PASSWORD': '',
    'PORT': 1883,
    'ENVIRONMENT': 'dev' # set to 'prod' for tls connection to broker, may solve connection issues
}
TOPICS = {
    # read topics
    'FAN_CONTROL': f'bike/{BIKE["ID"]}/fan/control',
    'BIKE_INCLINE_REPORT': f'bike/{BIKE["ID"]}/incline/control',
    'BIKE_RESISTANCE_REPORT': f'bike/{BIKE["ID"]}/resistance/control',
    'BIKE_SPEED_REPORT': f'bike/{BIKE["ID"]}speed',
    'BIKE_CADENCE_REPORT': f'bike/{BIKE["ID"]}/cadence',
    'BIKE_POWER_REPORT': f'bike/{BIKE["ID"]}/power',
    'BIKE_BUTTON_REPORT': f'bike/{BIKE["ID"]}/button/report',
    # Workout selector
    'WORKOUT_SELECTOR_TOPIC': f'bike/{BIKE["ID"]}/workout'
}

