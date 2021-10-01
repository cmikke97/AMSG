# Copyright 2021, Crepaldi Michele.
#
# Developed as a thesis project at the TORSEC research group of the Polytechnic of Turin (Italy) under the supervision
# of professor Antonio Lioy and engineer Andrea Atzeni and with the support of engineer Andrea Marcelli.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

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
