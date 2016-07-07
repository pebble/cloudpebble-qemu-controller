#!/usr/bin/env python
""" fake_runner.py pretends to be a test runner """

import logging
import time
import os
import re
import shutil
from glob import glob
from ta_utils import find_all_screenshots


def check_environment_vars():
    """ Check that all environment variables are present, warn if any are not. """
    logging.debug("Checking environment variables")
    keys = ('PEBBLE_VIRTUAL_ONLY', 'PEBBLE_DEVICE', 'PEBLE_BT_DEVICE')
    for name in keys:
        value = os.environ.get(name)
        if not value:
            logging.warning('Expected env-var %s', name)
        else:
            logging.info('Variable %s set to %s', name, value)
    loghash = os.environ.get('PEBBLE_LOGHASH_DICT')
    if loghash and not os.path.exists(loghash):
        logging.warning('loghash file %s does not exist', loghash)
    else:
        logging.debug('loghash dict found at %s', loghash)


def find_expected_screenshots(lines):
    """ Find screenshots in a monkeyscript file
    :param lines: an iterable of monkeyscript lines
    :return: yield screenshot filenames
    """
    for line in lines:
        match = re.match(r'\s*expect\s+screenshot\s+([a-zA-Z._-]+)', line)
        if match:
            yield match.group(1)


def make_screenshot_path(base_path, file_name, platform, language='english'):
    """ Get the path for a new screenshot
    :param base_path: Path to test directory
    :param file_name: File name for new screenshot
    :param platform: A platform name
    :param language: A language description (must be "english")
    :return: The full path to the screenshot
    """
    return os.path.join(base_path, language, platform, file_name)


def get_sample_screenshots():
    """ Look for existing examples of screenshots for each platform
    :return: a dict with platforms as keys and paths to an existing screenshot for that platform as values
    """
    return dict((name, next(iter(value))) for name, value in find_all_screenshots(os.getcwd()))


def verify_or_create_screenshot(base_path, screenshot_name, update=False, platform='basalt'):
    """ If the screenshot does not exist for the given name and platform,
    either create it or warn about it
    :param base_path: Path to test directory
    :param screenshot_name: File name for new screenshot
    :param update: Whether to create (True) the file or warn about it (False)
    :param platform: A platform name
    """

    new_path = make_screenshot_path(base_path, screenshot_name, platform)
    if not os.path.exists(new_path):
        if update:
            samples = get_sample_screenshots()
            logging.info("Copying screenshot from %s to %s", samples[platform], new_path)
            shutil.copy(samples[platform], new_path)
        else:
            logging.warning("Screenshot %s does not exist", new_path)
    else:
        logging.info("Screenshot %s already exists", new_path)

def find_tests():
    """ Find all the tests in the CWD
    :return: yield the absolute path of each monkey file
    """
    logging.debug("Looking for tests")
    tests = glob('./tests/*/*.monkey')
    if not len(tests):
        logging.warning("No tests found")
    else:
        for test_filename in tests:
            logging.info("Found test at %s", test_filename)
            yield os.path.abspath(test_filename)


def count(times=5):
    """ Print a message once per second
    :param times: Number of times to print
    """
    logging.debug("Print some messages for five seconds")
    for x in range(times):
        time.sleep(1)
        logging.info("Count: %d", x)


def verify_or_create_screenshots(update=False):
    """ Check for the existance of screenshots mentioned in all tests, optionally
      'creating' new ones by copying existing ones
    :param update: Whether to update or verify screenshots """
    for test_filename in find_tests():
            with open(test_filename, 'r') as f:
                for screenshot_name in find_expected_screenshots(f.readlines()):
                    logging.info("EXPECTING {}".format(screenshot_name))
                    verify_or_create_screenshot(os.path.dirname(test_filename), screenshot_name, update)


def run(update):
    check_environment_vars()
    verify_or_create_screenshots(update=update)
    logging.info("Done!")


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', help='Name of script to search for')
    parser.add_argument('--update', action='store_true', help='generate screenshots')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--ff', action='store_true')
    args = parser.parse_args()
    logging.info("CWD is %s", os.getcwd())
    logging.info("Script search string: '%s'", args.script)
    logging.info("Set --update = %s", args.update)
    logging.info("Set --ff     = %s", args.ff)
    logging.info("Set --debug  = %s", args.debug)
    run(args.update)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
