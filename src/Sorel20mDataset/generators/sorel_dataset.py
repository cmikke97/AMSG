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
import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import sqlite3  # provides a SQL interface compliant with the DB-API 2.0 specification
import zlib  # allows compression and decompression, using the zlib library

import lmdb  # python binding for the LMDB ‘Lightning’ Database
import msgpack  # efficient binary serialization format
import numpy as np  # the fundamental package for scientific computing with Python
from logzero import logger  # robust and effective logging for Python
from torch.utils import data  # used to import data.Dataset
from tqdm import tqdm  # instantly makes loops show a smart progress meter

# get config file path
generators_dir = os.path.dirname(os.path.abspath(__file__))
sorel20m_dataset_dir = os.path.dirname(generators_dir)
src_dir = os.path.dirname(sorel20m_dataset_dir)
config_filepath = os.path.join(src_dir, 'config.ini')

# instantiate config parser and read config file
config = configparser.ConfigParser()
config.read(config_filepath)

# get the train_validation_split from config file
train_validation_split = float(config['sorel20mDataset']['train_validation_split'])
# get the validation_test_split from config file
validation_test_split = float(config['sorel20mDataset']['validation_test_split'])


class LMDBReader(object):  # lmdb (lightning database) reader
    """ Class used to read features in lmdb format. """

    def __init__(self,
                 path,  # location of lmdb database
                 postproc_func=None):  # post processing function to apply to data points
        """ Init LMDBReader.

        Args:
            path: Location of lmdb database
            postproc_func: Post processing function to apply to data points (default: None)
        """

        # set self data post processing function
        self.postproc_func = postproc_func

        # open the lmdb (lightning database) -> the result is an open lmdb environment
        self.env = lmdb.open(path,  # Location of directory
                             readonly=True,  # Disallow any write operations
                             map_size=1e13,  # Maximum size database may grow to; used to size the memory mapping
                             max_readers=1024)  # Maximum number of simultaneous read transactions

    def __call__(self,
                 key):  # key (sha256) of the data point to retrieve
        """ LMDBReader call method.

        Args:
            key: Key (sha256) of the data point to retrieve
        Returns:
            Data point.
        """

        # Execute a transaction on the database
        with self.env.begin() as txn:
            x = txn.get(key.encode('ascii'))  # Fetch the first value matching key (encoded in ascii)

        if x is None:
            return None  # is no value was found matching key then return None
        # otherwise decompress the (x) bytes, returning a bytes object containing
        # the uncompressed data (x) and unpack it (from msgpack's array) to Python's list
        x = msgpack.loads(zlib.decompress(x), strict_map_key=False)

        if self.postproc_func is not None:  # if the data post processing function was defined
            x = self.postproc_func(x)  # apply post processing function on the data point

        return x  # return the data point


def features_postproc_func(x):  # data point to apply the post processing function to
    """ Features post-processing function.

    Args:
        x: Data point to apply the post processing function to
    Returns:
        x.
    """

    x = np.asarray(x[0], dtype=np.float32)  # Convert the input (x[0]) to a numpy array of float32
    lz = x < 0  # create a numpy array of boolean -> lz[i] is true when x[i] < 0
    gz = x > 0  # create a numpy array of boolean -> lz[i] is true when x[i] > 0
    x[lz] = - np.log(1 - x[lz])  # if lz[i] is true -> assign x[i] = -np.log(1-x[i])
    x[gz] = np.log(1 + x[gz])  # if gz[i] is true -> assign x[i] = np.log(1+x[i])
    return x


def tags_postproc_func(x):  # data point to apply the post processing function to
    """ Tags post-processing function.

    Args:
        x: Data point to apply the post processing function to
    Returns:
        x.
    """

    x = list(x[b'labels'].values())  # return datapoint labels as a list of labels
    x = np.asarray(x)  # transform list to a numpy array of labels
    return x


class Dataset(data.Dataset):
    """ Sorel20M Dataset class. """

    # list of malware tags
    tags = ["adware", "flooder", "ransomware", "dropper", "spyware", "packed",
            "crypto_miner", "file_infector", "installer", "worm", "downloader"]

    # create tag-index dictionary for the joint embedding
    # e.g. tags2idx = {'adware': 0, 'flooder': 1, ...}
    tags2idx = {tag: idx for idx, tag in enumerate(tags)}

    # create list of tag indices (tags encoding)
    encoded_tags = [idx for idx in range(len(tags))]

    def __init__(self,
                 metadb_path,  # path to the metadb file
                 features_lmdb_path,  # path to the features lmbd file
                 return_malicious=True,  # whether to return the malicious label for the data point or not
                 return_counts=True,  # whether to return the counts for the data point or not
                 return_tags=True,  # whether to return the tags for the data points or not
                 return_shas=False,  # whether to return the sha256 of the data points or not
                 mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                 binarize_tag_labels=True,  # whether to binarize or not the tag values
                 n_samples=-1,  # maximum number of data points to consider (-1 if you want to consider them all)
                 offset=0,  # offset where to start retrieving samples
                 remove_missing_features=True,
                 # whether to remove data points with missing features or not; it can be False/None/'scan'/filepath
                 # in case it is 'scan' a scan will be performed on the database in order to remove the data points
                 # with missing features;
                 # in case it is a filepath then a file (in Json format) will be used to determine
                 # the data points with missing features
                 postprocess_function=features_postproc_func):  # post processing function to use on each data point
        """ Initialize dataset class.

        Args:
            metadb_path: Path to the metadb file
            features_lmdb_path: Path to the features lmbd file
            return_malicious: Whether to return the malicious label for the data point or not (default: True)
            return_counts: Whether to return the counts for the data point or not (default: True)
            return_tags: Whether to return the tags for the data points or not (default: True)
            return_shas: Whether to return the sha256 of the data points or not (default: False)
            mode: Mode of use of the dataset object (may be 'train', 'validation' or 'test') (default: 'train')
            binarize_tag_labels: Whether to binarize or not the tag values (default: True)
            n_samples: Maximum number of data points to consider (-1 if you want to consider them all) (default: -1)
            offset: Offset where to start retrieving samples (default: 0)
            remove_missing_features: Whether to remove data points with missing features or not; it can be
                                     False/None/'scan'/filepath. In case it is 'scan' a scan will be performed on the
                                     database in order to remove the data points with missing features; in case it is
                                     a filepath then a file (in Json format) will be used to determine the data points
                                     with missing features (default: True)
            postprocess_function: Post processing function to use on each data point
        """

        # set some attributes
        self.return_counts = return_counts
        self.return_tags = return_tags
        self.return_malicious = return_malicious
        self.return_shas = return_shas

        # define a lmdb reader with the features lmbd path (LMDB directory with baseline features) and post
        # processing function
        self.features_lmdb_reader = LMDBReader(features_lmdb_path,
                                               postproc_func=postprocess_function)

        retrieve = ["sha256"]  # initialize list of strings with "sha256"

        if return_malicious:
            retrieve += ["is_malware"]  # add to the list of strings "is_malware"

        if return_counts:
            retrieve += ["rl_ls_const_positives"]  # add to the list of strings "rl_ls_const_positives"

        if return_tags:
            # adds all the elements of tags list (iterable) to the end of the list of strings
            retrieve.extend(Dataset.tags)

        # connect to the sqlite3 database containing index, labels, tags, and counts for the data
        conn = sqlite3.connect(metadb_path)
        cur = conn.cursor()  # create a cursor object for the db

        # create SQL query
        # concatenate strings from the previously define list of strings with ','
        query = 'select ' + ','.join(retrieve)
        query += " from meta"

        # if in training select all data points before train_validation_split timestamp
        if mode == 'train':
            query += ' where(rl_fs_t <= {})'.format(train_validation_split)

        # if in validation select all data points between two timestamps (train_validation_split and
        # validation_test_split)
        elif mode == 'validation':
            query += ' where((rl_fs_t >= {}) and (rl_fs_t < {}))'.format(train_validation_split,
                                                                         validation_test_split)

        # if in test select all data points after validation_test_split timestamp
        elif mode == 'test':
            query += ' where(rl_fs_t >= {})'.format(validation_test_split)

        # else provide an error
        else:
            raise ValueError('invalid mode: {}'.format(mode))

        # log info
        logger.info('Opening Dataset at {} in {} mode.'.format(metadb_path, mode))

        # if n_samples is not None then limit the query to output a maximum of n_samples rows
        if type(n_samples) is not None and n_samples != -1:
            if type(offset) is not None and offset != 0:
                query += ' limit {} offset {}'.format(n_samples, offset)
            else:
                query += ' limit {}'.format(n_samples)

        vals = cur.execute(query).fetchall()  # execute the SQL query and fetch all results as a list
        conn.close()  # close database connection

        logger.info(f"{len(vals)} samples loaded.")

        # map the items we're retrieving to an index (e.g. {'sha256': 0, 'is_malware': 1, ...})
        retrieve_ind = dict(zip(retrieve, list(range(len(retrieve)))))

        if remove_missing_features == 'scan':  # if remove_missing_features is equal to the keyword 'scan'
            logger.info("Removing samples with missing features...")

            # initialize list of indexes to remove
            indexes_to_remove = []

            logger.info("Checking dataset for keys with missing features.")

            # open the lmdb (lightning database) -> the result is an open lmdb environment
            temp_env = lmdb.open(features_lmdb_path,  # Location of directory
                                 readonly=True,  # Disallow any write operations
                                 map_size=1e13,  # Maximum size database may grow to; used to size the memory mapping
                                 max_readers=256)  # Maximum number of simultaneous read transactions

            # Execute a transaction on the database
            with temp_env.begin() as txn:
                # perform a loop -> for index, item in decorated iterator over samples (from metadb)
                for index, item in tqdm(enumerate(vals),  # Iterable to decorate with a progressbar
                                        total=len(vals),  # The number of expected iterations
                                        mininterval=.5,  # Minimum progress display update interval seconds
                                        # Exponential moving average smoothing factor for speed estimates
                                        smoothing=0.):

                    # if in the features lmbd no element with the specified sha256 (got by metadb item) is found
                    if txn.get(item[retrieve_ind['sha256']].encode('ascii')) is None:
                        indexes_to_remove.append(index)  # add index to the list of indexes to remove

            indexes_to_remove = set(indexes_to_remove)  # create a set from list (duplicate values will be ignored)

            # remove from vals all the items that are in indexes_to_remove set
            vals = [value for index, value in enumerate(vals) if index not in indexes_to_remove]

            # log info
            logger.info(f"{len(indexes_to_remove)} samples had no associated feature and were removed.")
            logger.info(f"Dataset now has {len(vals)} samples.")

        elif (remove_missing_features is False) or (remove_missing_features is None):
            pass  # nop

        else:
            # assume remove_missing_features is a filepath

            logger.info(f"Trying to load shas to ignore from {remove_missing_features}...")

            # open file in read mode
            with open(remove_missing_features, 'r') as f:
                shas_to_remove = json.load(f)  # deserialize from Json object to python object
            shas_to_remove = set(shas_to_remove)  # create a set from list (duplicate values will be ignored)

            # remove from vals all the items that are in indexes_to_remove set
            vals = [value for value in vals if value[retrieve_ind['sha256']] not in shas_to_remove]

            logger.info(f"Dataset now has {len(vals)} samples.")

        # create a list of keys (sha256) from vals
        self.keylist = list(map(lambda x: x[retrieve_ind['sha256']], vals))

        if self.return_malicious:
            # create a list of labels from vals
            self.labels = list(map(lambda x: x[retrieve_ind['is_malware']], vals))

        if self.return_counts:
            # retrieve the list of counts from vals
            self.count_labels = list(map(lambda x: x[retrieve_ind['rl_ls_const_positives']], vals))

        if self.return_tags:
            # create a numpy array of lists of tags from vals
            # Convert the input (list of tags per val in vals) to a numpy array and get the transpose (.T)
            self.tag_labels = np.asarray([list(map(lambda x: x[retrieve_ind[t]], vals)) for t in Dataset.tags]).T

            if binarize_tag_labels:
                # binarize the tag labels -> if the tag is different from 0 then it is set 1, otherwise it is set to 0
                self.tag_labels = (self.tag_labels != 0).astype(int)

    def __len__(self):
        """ Get dataset total length.

        Returns:
            Dataset length.
        """

        return len(self.keylist)  # return the total number of samples

    def __getitem__(self,
                    index):  # index of the item to get
        """ Get item from dataset.

        Args:
            index: Index of the item to get
        Returns:
            Sha256 (if required), features and labels associated to the sample with index 'index'.
        """

        labels = {}  # initialize labels set for this particular sample
        key = self.keylist[index]  # get sha256 key associated to this index
        features = self.features_lmdb_reader(key)  # get feature vector associated to this sample sha256

        if self.return_malicious:
            labels['malware'] = self.labels[index]  # get malware label for this sample through the index

        if self.return_counts:
            labels['count'] = self.count_labels[index]  # get count for this sample through the index

        if self.return_tags:
            labels['tags'] = self.tag_labels[index]  # get tags list for this sample through the index

        if self.return_shas:
            # return sha256, features and labels associated to the sample with index 'index'
            return key, features, labels
        else:
            return features, labels  # return features and labels associated to the sample with index 'index'
