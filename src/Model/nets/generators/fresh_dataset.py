import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import sys  # system-specific parameters and functions

import numpy as np  # the fundamental package for scientific computing with Python
import torch  # tensor library like NumPy, with strong GPU support
from logzero import logger  # robust and effective logging for Python
from torch.utils import data  # used to import data.Dataset


class Dataset(data.Dataset):
    """ Fresh dataset class. """

    # list of malware tags
    tags = ["adware", "flooder", "ransomware", "dropper", "spyware", "packed",
            "crypto_miner", "file_infector", "installer", "worm", "downloader"]

    def __init__(self,
                 ds_root,  # fresh dataset root directory (where to find .dat files)
                 return_shas=False):  # whether to return the sha256 of the data points or not
        """ Initialize fresh dataset.

        Args:
            ds_root: Fresh dataset root directory (where to find .dat files)
            return_shas: Whether to return the sha256 of the data points or not
        """

        self.return_shas = return_shas

        # set feature dimension
        ndim = 2381

        # generate X (features vector), y (labels vector) and S (shas) file names
        X_path = os.path.join(ds_root, "X_fresh.dat")
        y_path = os.path.join(ds_root, "y_fresh.dat")
        S_path = os.path.join(ds_root, "S_fresh.dat")
        # generate sig-to-label filename
        sig_to_label_path = os.path.join(ds_root, "sig_to_label.json")

        # if at least one of those files does not exist -> error
        if not (os.path.exists(X_path)
                and os.path.exists(y_path)
                and os.path.exists(S_path)
                and os.path.exists(sig_to_label_path)):
            logger.error("Fresh Dataset's X, y, S files not found.")
            sys.exit(1)

        # open signature-to-label file and load its content in signature-to-label dict
        with open(sig_to_label_path, 'r') as sig_to_label_file:
            self._sig_to_label = json.load(sig_to_label_file)

        # generate signature-to-label inverse dictionary (label-to-signature)
        self._sig_to_label_inv = {v: k for k, v in self._sig_to_label.items()}

        self.n_families = len(self._sig_to_label.keys())

        logger.info('Opening fresh Dataset at {}.'.format(ds_root))

        # open S (shas) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.S = np.memmap(S_path, dtype=np.dtype('U64'), mode="r+")
        # get number of elements from S vector
        self.N = self.S.shape[0]

        # open y (labels) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.y = torch.from_numpy(np.memmap(y_path, dtype=np.float32, mode="r+", shape=(self.N,)))

        # open X (features) memory map in Read+ mode (+ because pytorch does not support read only ndarrays)
        self.X = torch.from_numpy(np.memmap(X_path, dtype=np.float32, mode="r+", shape=(self.N, ndim)))

        logger.info("{} samples loaded.".format(self.N))

    def __len__(self):
        """ Get Dataset total length.

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
            Sha256 (if required), features and labels associated to the sample with index 'index'.
        """

        # get feature vector
        features = self.X[index]

        # get label
        label = self.y[index]

        if self.return_shas:
            # get sha256
            sha = self.S[index]

            # return sha256, features and label associated to the sample with index 'index'
            return sha, features, label
        else:
            # return features and label associated to the sample with index 'index'
            return features, label

    def sig_to_label(self,
                     sig):  # family signature
        """ Convert family signature to numerical label.

        Args:
            sig: Family signature
        Returns:
            Numerical label.
        """
        # return corresponding label
        return self._sig_to_label[sig]

    def label_to_sig(self,
                     label):  # numerical label
        """ Convert numerical label to family signature.

        Args:
            label: Numerical label
        Returns:
            Family signature.
        """
        # return corresponding family signature
        return self._sig_to_label_inv[label]

    def get_as_tensors(self):
        """ Get dataset tensors (numpy memmap arrays).

        Returns:
            S (shas, if requested), X (features) and y (labels) dataset tensors.
        """

        if self.return_shas:
            return self.S, self.X, self.y
        else:
            return self.X, self.y
