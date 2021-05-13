import os

import numpy as np  # The fundamental package for scientific computing with Python
from logzero import logger  # Robust and effective logging for Python
# used to import data.Dataset -> we will subclass it; it will then be passed to data.Dataloader which is at the heart
# of PyTorch data loading utility
from torch.utils import data


class Dataset(data.Dataset):

    # list of malware tags
    tags = ["adware", "flooder", "ransomware", "dropper", "spyware", "packed",
            "crypto_miner", "file_infector", "installer", "worm", "downloader"]

    # create tag-index dictionary for the joint embedding
    tags2idx = {tag: idx for idx, tag in enumerate(tags)}
    # tags2idx = {'adware': 0, 'flooder': 1, ...}

    # create list of tag indices (tags encoding)
    encoded_tags = [idx for idx in range(len(tags))]

    def __init__(self,
                 ds_root,
                 mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                 return_malicious=True,  # whether to return the malicious label for the data point or not
                 return_counts=True,  # whether to return the counts for the data point or not
                 return_tags=True,  # whether to return the tags for the data points or not
                 return_shas=False,  # whether to return the sha256 of the data points or not
                 binarize_tag_labels=True):  # whether to binarize or not the tag values

        # set some attributes
        self.return_counts = return_counts
        self.return_tags = return_tags
        self.return_malicious = return_malicious
        self.return_shas = return_shas

        # if mode is not in one of the expected values raise an exception
        if mode not in {'train', 'validation', 'test'}:
            raise ValueError('invalid mode {}'.format(mode))

        # get feature dimension from extractor
        ndim = 2381

        # set labels dimension to 1 (malware) + 1 (count) + n_tags (tags)
        labels_dim = 1 + 1 + len(Dataset.tags)

        # generate X (features vector), y (labels vector) and S (shas) file names
        X_path = os.path.join(ds_root, "X_{}.dat".format(mode))
        y_path = os.path.join(ds_root, "y_{}.dat".format(mode))
        S_path = os.path.join(ds_root, "S_{}.dat".format(mode))

        # open S (shas) memory map in Read mode
        self.S = np.memmap(y_path, dtype=np.dtype('U256'), mode="r")
        # get number of elements from y vector
        self.N = self.S.shape[0]

        # open y (labels) memory map in Read mode
        self.y = np.memmap(y_path, dtype=np.float32, mode="r", shape=(self.N, labels_dim))

        # open X (features) memory map in Read mode
        self.X = np.memmap(X_path, dtype=np.float32, mode="r", shape=(self.N, ndim))

        # log info
        logger.info('Opening Dataset at {} in {} mode.'.format(ds_root, mode))

        # log info
        logger.info("{} samples loaded.".format(self.N))

        if binarize_tag_labels:
            # binarize the tag labels -> if the tag is different from 0 then it is set 1, otherwise it is set to 0
            self.y[:, 2:] = (self.y[:, 2:] != 0).astype(int)

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
