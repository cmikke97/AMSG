import os  # provides a portable way of using operating system dependent functionality

from logzero import logger  # robust and effective logging for Python

# initialize some variables
steps = ['train', 'validation', 'test']


def check_files(destination_dir,  # the directory where to search for the pre-processed dataset files
                n_samples_dict):  # key-n_samples dict
    """ Check if the dataset was already pre-processed.

    Args:
        destination_dir: The directory where to search for the pre-processed dataset files
        n_samples_dict: Key-n_samples dict
    Returns:
        False if at least one file is not present inside the destination dir, True otherwise.
    """

    # set files prefixes
    prefixes = ['X', 'y', 'S']

    # get all file names to be checked
    paths = [os.path.join(destination_dir, "{}_{}_{}.dat".format(pre, key, n_samples_dict[key]))
             for key in steps
             for pre in prefixes]

    # if at least one file is not present on the destination dir, return false
    for path in paths:
        if not os.path.exists(path):
            logger.info("{} does not exist.".format(path))
            return False

    # otherwise return true
    return True
