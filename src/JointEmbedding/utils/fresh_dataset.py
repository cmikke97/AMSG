import configparser
import os
import sys

import numpy as np  # The fundamental package for scientific computing with Python
from logzero import logger  # Robust and effective logging for Python
# used to import data.Dataset -> we will subclass it; it will then be passed to data.Dataloader which is at the heart
# of PyTorch data loading utility
from torch.utils import data

# get config file path
utils_dir = os.path.dirname(os.path.abspath(__file__))
joint_embedding_dir = os.path.dirname(utils_dir)
src_dir = os.path.dirname(joint_embedding_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)


class Dataset(data.Dataset):

    def __init__(self,
                 ds_root,
                 return_shas=False):  # whether to return the sha256 of the data points or not

        self.return_shas = return_shas

        # get feature dimension from extractor
        ndim = 2381

        # set labels dimension to 1 (malware) + 1 (count) + n_tags (tags)
        labels_dim = 1

        # generate X (features vector), y (labels vector) and S (shas) file names
        X_path = os.path.join(ds_root, "X_{}_{}.dat")
        y_path = os.path.join(ds_root, "y_{}_{}.dat")
        S_path = os.path.join(ds_root, "S_{}_{}.dat")

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

        return self.N  # return the total number of samples

    def __getitem__(self,
                    index):  # index of the item to get

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
            shas = self.S[index]

            # return sha256, features and labels associated to the sample with index 'index'
            return shas, features, labels
        else:
            # return features and labels associated to the sample with index 'index'
            return features, labels
