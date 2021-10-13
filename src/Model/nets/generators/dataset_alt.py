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

import configparser  # implements a basic configuration language for Python programs
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions

import numpy as np  # the fundamental package for scientific computing with Python
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python

# get config file path
generators_dir = os.path.dirname(os.path.abspath(__file__))
nets_dir = os.path.dirname(generators_dir)
model_dir = os.path.dirname(nets_dir)
src_dir = os.path.dirname(model_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get variables from config file
training_n_samples = config['sorel20mDataset']['total_training_samples']
validation_n_samples = config['sorel20mDataset']['total_validation_samples']
test_n_samples = config['sorel20mDataset']['total_test_samples']

# instantiate key-n_samples dict
total_n_samples = {'train': training_n_samples,
                   'validation': validation_n_samples,
                   'test': test_n_samples}


class Dataset:
    """ Pre-processed dataset class. """

    # list of malware tags
    tags = ["adware", "flooder", "ransomware", "dropper", "spyware", "packed",
            "crypto_miner", "file_infector", "installer", "worm", "downloader"]

    # create tag-index dictionary for the joint embedding
    # e.g. tags2idx = {'adware': 0, 'flooder': 1, ...}
    tags2idx = {tag: idx for idx, tag in enumerate(tags)}

    # create list of tag indices (tags encoding)
    encoded_tags = [idx for idx in range(len(tags))]

    def __init__(self,
                 ds_root,  # pre-processed dataset root directory (where to find .dat files)
                 mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                 n_samples=None,  # number of samples to consider (used just to access the right pre-processed files)
                 return_shas=False):  # whether to return the sha256 of the data points or not
        """ Initialize Dataset class.

        Args:
            ds_root: Pre-processed dataset root directory (where to find .dat files)
            mode: Mode of use of the dataset object (it may be 'train', 'validation' or 'test') (default: 'train')
            n_samples: Number of samples to consider (used just to access the right pre-processed files) (default: None)
            return_shas: Whether to return the sha256 of the data points or not (default: False)
        """

        self.return_shas = return_shas

        # if mode is not in one of the expected values raise an exception
        if mode not in {'train', 'validation', 'test'}:
            raise ValueError('invalid mode {}'.format(mode))

        # if n_samples is not set or it is <= 0 -> set it to the max
        if n_samples is None or n_samples <= 0:
            n_samples = total_n_samples[mode]

        # set feature dimension
        ndim = 2381

        # set labels dimension to 1 (malware) + 1 (count) + n_tags (tags)
        labels_dim = 1 + 1 + len(Dataset.tags)

        # generate X (features vector), y (labels vector) and S (shas) file names
        X_path = os.path.join(ds_root, "X_{}_{}.dat".format(mode, n_samples))
        y_path = os.path.join(ds_root, "y_{}_{}.dat".format(mode, n_samples))
        S_path = os.path.join(ds_root, "S_{}_{}.dat".format(mode, n_samples))

        # log error and exit if at least one of the dataset files (X, y, S) does not exist
        if not (os.path.exists(X_path) and os.path.exists(y_path) and os.path.exists(S_path)):
            logger.error("X, y, S files for mode {} and amount {} not found.".format(mode, n_samples))
            sys.exit(1)

        logger.info('Opening Dataset at {} in {} mode.'.format(ds_root, mode))

        # open S (shas) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.S = np.memmap(S_path, dtype=np.dtype('U64'), mode="r+")
        # get number of elements from S vector
        self.N = self.S.shape[0]

        # open y (labels) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.y = torch.from_numpy(np.memmap(y_path, dtype=np.float32, mode="r+", shape=(self.N, labels_dim)))

        # open X (features) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.X = torch.from_numpy(np.memmap(X_path, dtype=np.float32, mode="r+", shape=(self.N, ndim)))

        logger.info("{} samples loaded.".format(self.N))

    def __len__(self):
        """ Get dataset total length.

        Returns:
            Dataset length.
        """

        return self.N  # return the total number of samples

    def get_as_tensors(self):
        """ Get dataset tensors (numpy memmap arrays).

        Returns:
            S (shas, if requested), X (features) and y (labels) dataset tensors.
        """

        if self.return_shas:
            return self.S, self.X, self.y
        else:
            return self.X, self.y
