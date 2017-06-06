import argparse
import json
import logging
import pprint
import time
from configparser import ConfigParser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

logger = logging.getLogger("main")


class AutoMowerConfig(ConfigParser):
    def __init__(self):
        super(AutoMowerConfig, self).__init__()
        self['husqvarna.net'] = {}
        self.login = ""
        self.password = ""
        self.log_level = 'INFO'
        self.expire_status = "30"

    def load_config(self):
        return self.read('automower.cfg')

    def save_config(self):
        with open('automower.cfg', mode='w') as f:
            return self.write(f)

    @property
    def login(self):
        return self['husqvarna.net']['login']

    @login.setter
    def login(self, value):
        self['husqvarna.net']['login'] = value

    @property
    def password(self):
        return self['husqvarna.net']['password']

    @password.setter
    def password(self, value):
        self['husqvarna.net']['password'] = value

    @property
    def log_level(self):
        return self['husqvarna.net']['log_level']

    @log_level.setter
    def log_level(self, value):
        self['husqvarna.net']['log_level'] = value

    @property
    def expire_status(self):
        return int(self['husqvarna.net']['expire_status'])

    @expire_status.setter
    def expire_status(self, value):
        self['husqvarna.net']['expire_status'] = str(value)


class API:
    _API_IM = 'https://iam-api.dss.husqvarnagroup.net/api/v3/'
    _API_TRACK = 'https://amc-api.dss.husqvarnagroup.net/v1/'
    _HEADERS = {'Accept': 'application/json', 'Content-type': 'application/json'}

    def __init__(self):
        self.logger = logging.getLogger("main.automower")
        self.session = requests.Session()
        self.device_id = None
        self.token = None

    def login(self, login, password):
        response = self.session.post(self._API_IM + 'token',
                                     headers=self._HEADERS,
                                     json={
                                         "data": {
                                             "attributes": {
                                                 "password": password,
                                                 "username": login
                                             },
                                             "type": "token"
                                         }
                                     })

        response.raise_for_status()
        self.logger.info('Logged in successfully')

        json = response.json()
        self.token = json["data"]["id"]
        self.session.headers.update({
            'Authorization': "Bearer " + self.token,
            'Authorization-Provider': json["data"]["attributes"]["provider"]
        })

        self.select_first_robot()

    def logout(self):
        response = self.session.delete(self._API_IM + 'token/%s' % self.token)
        response.raise_for_status()
        self.device_id = None
        self.token = None
        del (self.session.headers['Authorization'])
        self.logger.info('Logged out successfully')

    def list_robots(self):
        response = self.session.get(self._API_TRACK + 'mowers', headers=self._HEADERS)
        response.raise_for_status()

        return response.json()

    def select_first_robot(self):
        result = self.list_robots()
        self.device_id = result[0]['id']

    def status(self):
        response = self.session.get(self._API_TRACK + 'mowers/%s/status' % self.device_id, headers=self._HEADERS)
        response.raise_for_status()

        return json.dumps(response.json())

    def geo_status(self):
        response = self.session.get(self._API_TRACK + 'mowers/%s/geofence' % self.device_id, headers=self._HEADERS)
        response.raise_for_status()

        return response.json()

    def control(self, command):
        if command not in ['PARK', 'STOP', 'START']:
            raise Exception("Unknown command")

        response = self.session.post(self._API_TRACK + 'mowers/%s/control' % self.device_id,
                                    headers=self._HEADERS,
                                    json={
                                        "action": command
                                    })
        response.raise_for_status()


def create_config(args):
    config = AutoMowerConfig()
    config.load_config()
    if args.login:
        config.login = args.login
    if args.password:
        config.password = args.password
    if args.log_level:
        config.log_level = args.log_level
    if hasattr(args, "expire_status") and args.expire_status:
        config.expire_status = args.expire_status

    if not config.login or not config.password:
        logger.error('Missing login or password')
        return None

    if args.save:
        if config.save_config():
            logger.info('Configuration saved in "automower.cfg"')
        else:
            logger.info('Failed to saved configuration in "automower.cfg"')

    return config


def configure_log(config):
    logger.setLevel(logging.INFO)
    if config.log_level == 'ERROR':
        logger.setLevel(logging.ERROR)

    steam_handler = logging.StreamHandler()
    logger.addHandler(steam_handler)

    logger.info('Logger configured')


def run_cli(config, args):
    retry = 5
    while retry > 0:
        try:
            mow = API()

            mow.login(config.login, config.password)

            if args.command == 'control':
                mow.control(args.action)
            elif args.command == 'status':
                print(mow.status())
            retry = 0
        except Exception as ex:
            retry -= 1
            if retry > 0:
                logger.error(ex)
                logger.error("[ERROR] Retrying to send the command %d" % retry)
            else:
                logger.error("[ERROR] Failed to send the command")
                exit(1)

    logger.info("Done")

    mow.logout()


class HTTPRequestHandler(BaseHTTPRequestHandler):
    config = None
    last_status = ""
    last_status_check = 0

    def do_GET(self):
        logger.info("Try to execute " + self.path)

        # use cache for status command
        if self.path == '/status':
            # XXX where do we store status properly ? Class variables are not thread safe...
            if HTTPRequestHandler.last_status_check > time.time() - config.expire_status:
                logger.info("Get status from cache")
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(HTTPRequestHandler.last_status).encode('ascii'))
                return

        retry = 3
        while retry > 0:
            try:
                mow = API()

                mow.login(config.login, config.password)

                if self.path == '/start':
                    mow.control('START')
                    self.send_response(200)
                    self.end_headers()
                elif self.path == '/stop':
                    mow.control('STOP')
                    self.send_response(200)
                    self.end_headers()
                elif self.path == '/park':
                    mow.control('PARK')
                    self.send_response(200)
                    self.end_headers()
                elif self.path == '/status':
                    logger.info("Get status from Husqvarna servers")
                    HTTPRequestHandler.last_status = mow.status()
                    HTTPRequestHandler.last_status_check = time.time()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(HTTPRequestHandler.last_status).encode('ascii'))
                else:
                    self.send_response(400)
                    self.end_headers()

                retry = 0
            except Exception as ex:
                retry -= 1
                if retry > 0:
                    logger.error(ex)
                    logger.error("[ERROR] Retrying to send the command %d" % retry)
                else:
                    logger.error("[ERROR] Failed to send the command")
                    self.send_response(500)

            logger.info("Done")

            mow.logout()


def run_server(config, args):
    server_address = (args.address, args.port)
    HTTPRequestHandler.config = config
    httpd = HTTPServer(server_address, HTTPRequestHandler)
    httpd.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Speak with your automower')
    subparsers = parser.add_subparsers(dest='command')

    parser_control = subparsers.add_parser('control', help='Send command to your automower')
    parser_control.add_argument('action', choices=['STOP', 'START', 'PARK'],
                                help='the command')

    parser_status = subparsers.add_parser('status', help='Get the status of your automower')

    parser_server = subparsers.add_parser('server', help='Run an http server to handle commands')
    parser_server.add_argument('--address', dest='address', default='127.0.0.1',
                               help='IP address for server')
    parser_server.add_argument('--port', dest='port', type=int, default=1234,
                               help='port for server')
    parser_server.add_argument('--expire', dest='expire_status', type=int, default=30,
                               help='Status needs to be refreshed after this time')

    parser.add_argument('--login', dest='login', help='Your login')
    parser.add_argument('--password', dest='password', help='Your password')
    parser.add_argument('--save', dest='save', action='store_true',
                        help='Save command line information in automower.cfg')

    parser.add_argument('--log-level', dest='log_level', choices=['INFO', 'ERROR'],
                        help='Display all logs or just in case of error')

    args = parser.parse_args()

    config = create_config(args)
    if not config:
        parser.print_help()
        exit(1)

    configure_log(config)

    if args.command == 'server':
        run_server(config, args)
    else:
        run_cli(config, args)

    exit(0)
