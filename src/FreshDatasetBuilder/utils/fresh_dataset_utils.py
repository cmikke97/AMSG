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

# needed fresh dataset objects
needed_objects = {"sig_to_label": "sig_to_label.json",
                  "X": "X_fresh.dat",
                  "y": "y_fresh.dat",
                  "S": "S_fresh.dat"}


def check_files(destination_dir):  # path to the destination folder where to save the elements to
    """ Check if the fresh dataset needed files were already created.

    Args:
        destination_dir: Path to the destination folder where to save the elements to
    Returns:
        True if there are all objects are present, False otherwise.
    """

    # select just the objects not already present from the needed objects
    absent_objects = {key: obj for key, obj in needed_objects.items()
                      if not os.path.exists(os.path.join(destination_dir, obj))}

    # if there are no objects to download return true
    return len(absent_objects) == 0
