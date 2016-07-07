import os
from glob import glob


def find_all_screenshots(base_dir):
    """ Look for existing examples of screenshots for each platform
    :param base_dir: Directory in which to search for screenshots
    :return: a dict with platforms as keys and paths to an existing screenshot for that platform as values
    """
    for platform in ('aplite', 'basalt', 'chalk'):
        result = frozenset(glob(os.path.join(base_dir, "tests/*/*/%s/*.png" % platform)))
        if result:
            yield platform, result
