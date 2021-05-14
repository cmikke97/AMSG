import os

# initialize some variables
steps = ['train', 'validation', 'test']


def _check_files(destination_dir,  # the directory to which to write the 'results.csv' file
                 n_samples_dict):  # key-n_samples dict

    # set files prefixes
    prefixes = ['X', 'y', 'S']

    # get all file names to be checked
    paths = [os.path.join(destination_dir, "{}_{}_{}.dat".format(pre, key, n_samples_dict[key]))
             for key in steps
             for pre in prefixes]

    # if at least one file si not present on the destination dir, return false
    for path in paths:
        if not os.path.exists(path):
            return False

    # otherwise return true
    return True
