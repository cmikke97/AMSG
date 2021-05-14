import configparser  # implements a basic configuration language for Python programs
import os  # Provides a portable way of using operating system dependent functionality
import sys  # System-specific parameters and functions

import numpy as np  # The fundamental package for scientific computing with Python
from logzero import logger  # Robust and effective logging for Python
from torch.utils import data  # used to import data.Dataset

# get config file path
utils_dir = os.path.dirname(os.path.abspath(__file__))
joint_embedding_dir = os.path.dirname(utils_dir)
src_dir = os.path.dirname(joint_embedding_dir)
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


class Dataset(data.Dataset):
    """ Pre-processed dataset class. """

    # list of malware tags
    tags = ["adware", "flooder", "ransomware", "dropper", "spyware", "packed",
            "crypto_miner", "file_infector", "installer", "worm", "downloader"]

    # create tag-index dictionary for the joint embedding
    tags2idx = {tag: idx for idx, tag in enumerate(tags)}
    # tags2idx = {'adware': 0, 'flooder': 1, ...}

    # create list of tag indices (tags encoding)
    encoded_tags = [idx for idx in range(len(tags))]

    def __init__(self,
                 ds_root,  # pre-processed dataset root directory (where to find .dat files)
                 mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                 n_samples=None,  # number of samples to consider (used just to access the right pre-processed files)
                 return_malicious=True,  # whether to return the malicious label for the data point or not
                 return_counts=True,  # whether to return the counts for the data point or not
                 return_tags=True,  # whether to return the tags for the data points or not
                 return_shas=False):  # whether to return the sha256 of the data points or not
        """ Initialize dataset.

        Args:
            ds_root: Pre-processed dataset root directory (where to find .dat files)
            mode: Mode of use of the dataset object (may be 'train', 'validation' or 'test')
            n_samples: Number of samples to consider (used just to access the right pre-processed files)
            return_malicious: Whether to return the malicious label for the data point or not
            return_counts: Whether to return the counts for the data point or not
            return_tags: Whether to return the tags for the data points or not
            return_shas: Whether to return the sha256 of the data points or not
        """

        # set some attributes
        self.return_counts = return_counts
        self.return_tags = return_tags
        self.return_malicious = return_malicious
        self.return_shas = return_shas

        # if mode is not in one of the expected values raise an exception
        if mode not in {'train', 'validation', 'test'}:
            raise ValueError('invalid mode {}'.format(mode))

        # if n_samples is not set or it is -1 -> set it to the max
        if n_samples is None or n_samples == -1:
            n_samples = total_n_samples[mode]

        # get feature dimension from extractor
        ndim = 2381

        # set labels dimension to 1 (malware) + 1 (count) + n_tags (tags)
        labels_dim = 1 + 1 + len(Dataset.tags)

        # generate X (features vector), y (labels vector) and S (shas) file names
        X_path = os.path.join(ds_root, "X_{}_{}.dat".format(mode, n_samples))
        y_path = os.path.join(ds_root, "y_{}_{}.dat".format(mode, n_samples))
        S_path = os.path.join(ds_root, "S_{}_{}.dat".format(mode, n_samples))

        if not (os.path.exists(X_path) and os.path.exists(y_path) and os.path.exists(S_path)):
            logger.error("X, y, S files for mode {} and amount {} not found.".format(mode, n_samples))
            sys.exit(1)

        # open S (shas) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.S = np.memmap(S_path, dtype=np.dtype('U64'), mode="r+")
        # get number of elements from y vector
        self.N = self.S.shape[0]

        # open y (labels) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=(self.N, labels_dim))

        # open X (features) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(self.N, ndim))

        # log info
        logger.info('Opening Dataset at {} in {} mode.'.format(ds_root, mode))

        # log info
        logger.info("{} samples loaded.".format(self.N))

    def __len__(self):
        """ Get dataset total length.

        Returns:
            Dataset length.
        """

        return self.N  # return the total number of samples

    def __getitem__(self,
                    index):  # index of the item to get
        """ Get item from dataset.

        Args:
            index: Index of the item to get
        Returns:
            sha256 (if required), features and labels associated to the sample with index 'index'
        """

        # initialize labels set for this particular sample
        labels = {}
        # get feature vector
        features = self.X[index]

        if self.return_malicious:
            # get malware label for this sample through the index
            labels['malware'] = self.y[index][0]

        if self.return_counts:
            # get count for this sample through the index
            labels['count'] = self.y[index][1]

        if self.return_tags:
            # get tags list for this sample through the index
            labels['tags'] = self.y[index][2:]

        if self.return_shas:
            # get sha256
            sha = self.S[index]

            # return sha256, features and labels associated to the sample with index 'index'
            return sha, features, labels
        else:
            # return features and labels associated to the sample with index 'index'
            return features, labels
