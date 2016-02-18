import os
from glob import glob

# TODO: these functions will need to change when the test bundle directory structure is changed!


def platform_to_ta_platform(platform):
    """ For a given platform, get the details needed to find the screenshots
    for tests for that platform
    :param platform: "aplite", "basalt" or "chalk"
    :return: ("tintin" or "snowy", (width, height))
    """
    if platform == 'aplite':
        return 'tintin', (144, 168)
    elif platform == 'basalt':
        return 'snowy', (144, 168)
    elif platform == 'chalk':
        return 'snowy', (180, 180)
    raise ValueError('Unrecognised platform')


def find_all_screenshots(base_dir):
    """ Look for existing examples of screenshots for each platform
    :param base_dir: Directory in which to search for screenshots
    :return: a dict with platforms as keys and paths to an existing screenshot for that platform as values
    """
    for platform in ('aplite', 'basalt', 'chalk'):
        test_platform, size = platform_to_ta_platform(platform)
        result = frozenset(glob(os.path.join(base_dir, "tests/*/*/%s/%s/*.png" % (test_platform, '%dx%d' % (size[0], size[1])))))
        if result:
            yield platform, result
