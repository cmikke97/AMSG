import json  # JSON encoder and decoder
import sqlite3  # Provides a SQL interface compliant with the DB-API 2.0 specification
import zlib  # Allows compression and decompression, using the zlib library

import baker  # Easy, powerful access to Python functions from the command line
import lmdb  # Python binding for the LMDB ‘Lightning’ Database
import msgpack  # Efficient binary serialization format
import numpy as np  # The fundamental package for scientific computing with Python
import tqdm  # Instantly makes loops show a smart progress meter
from logzero import logger  # Robust and effective logging for Python
# used to import data.Dataset -> we will subclass it; it will then be passed to data.Dataloader which is at the heart
# of PyTorch data loading utility
from torch.utils import data

import config as config  # import config.py


class LMDBReader(object):  # lmdb (lightning database) reader

    def __init__(self,
                 path,  # Location of lmdb database
                 postproc_func=None):  # post processing function to apply to data points

        # set self data post processing function
        self.postproc_func = postproc_func

        # open the lmdb (lightning database) -> the result is an open lmdb environment
        self.env = lmdb.open(path,  # Location of directory
                             readonly=True,  # Disallow any write operations
                             map_size=1e13,  # Maximum size database may grow to; used to size the memory mapping
                             max_readers=1024)  # Maximum number of simultaneous read transactions

    def __call__(self,
                 key):  # key (sha256) of the data point to retrieve

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

    x = np.asarray(x[0], dtype=np.float32)  # Convert the input (x[0]) to a numpy array of float32
    lz = x < 0  # create a numpy array of boolean -> lz[i] is true when x[i] < 0
    gz = x > 0  # create a numpy array of boolean -> lz[i] is true when x[i] > 0
    x[lz] = - np.log(1 - x[lz])  # if lz[i] is true -> assign x[i] = -np.log(1-x[i])
    x[gz] = np.log(1 + x[gz])  # if gz[i] is true -> assign x[i] = np.log(1+x[i])
    return x


def tags_postproc_func(x):  # data point to apply the post processing function to

    x = list(x[b'labels'].values())  # return datapoint labels as a list of labels
    x = np.asarray(x)  # transform list to a numpy array of labels
    return x


class Dataset(data.Dataset):
    # list of malware tags
    tags = ["adware", "flooder", "ransomware", "dropper", "spyware", "packed",
            "crypto_miner", "file_infector", "installer", "worm", "downloader"]

    def __init__(self,
                 metadb_path,
                 # path to the metadb (sqlite3 database containing index, labels, tags, and counts for the data)
                 features_lmdb_path,  # path to the features lmbd (database containing the data features)
                 return_malicious=True,  # whether to return the malicious label for the data point or not
                 return_counts=True,  # whether to return the counts for the data point or not
                 return_tags=True,  # whether to return the tags for the data points or not
                 return_shas=False,  # whether to return the sha256 of the data points or not
                 mode='train',  # mode of use of the dataset object (may be 'train', 'validation' or 'test')
                 binarize_tag_labels=True,  # whether to binarize or not the tag values
                 n_samples=None,  # maximum number of data points to consider (None if you want to consider them all)
                 remove_missing_features=True,
                 # whether to remove data points with missing features or not; it can be False/None/'scan'/filepath
                 # in case it is 'scan' a scan will be performed on the database in order to remove the data points
                 # with missing features;
                 # in case it is a filepath then a file (in Json format) will be used to determine
                 # the data points with missing features
                 postprocess_function=features_postproc_func):  # post processing function to use on each data point

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
            query += ' where(rl_fs_t <= {})'.format(config.train_validation_split)

        # if in validation select all data points between two timestamps (train_validation_split and
        # validation_test_split)
        elif mode == 'validation':
            query += ' where((rl_fs_t >= {}) and (rl_fs_t < {}))'.format(config.train_validation_split,
                                                                         config.validation_test_split)

        # if in test select all data points after validation_test_split timestamp
        elif mode == 'test':
            query += ' where(rl_fs_t >= {})'.format(config.validation_test_split)

        # else provide an error
        else:
            raise ValueError('invalid mode: {}'.format(mode))

        # log info
        logger.info('Opening Dataset at {} in {} mode.'.format(metadb_path, mode))

        # if n_samples is not None then limit the query to output a maximum of n_samples rows
        if type(n_samples) is not None:
            query += ' limit {}'.format(n_samples)

        vals = cur.execute(query).fetchall()  # execute the SQL query and fetch all results as a list
        conn.close()  # close database connection

        # log info
        logger.info(f"{len(vals)} samples loaded.")

        # map the items we're retrieving to an index (e.g. {'sha256': 0, 'is_malware': 1, ...})
        retrieve_ind = dict(zip(retrieve, list(range(len(retrieve)))))

        if remove_missing_features == 'scan':  # if remove_missing_features is equal to the keyword 'scan'
            # log info
            logger.info("Removing samples with missing features...")

            indexes_to_remove = []  # initialize list of indexes to remove

            # log info
            logger.info("Checking dataset for keys with missing features.")

            # open the lmdb (lightning database) -> the result is an open lmdb environment
            temp_env = lmdb.open(features_lmdb_path,  # Location of directory
                                 readonly=True,  # Disallow any write operations
                                 map_size=1e13,  # Maximum size database may grow to; used to size the memory mapping
                                 max_readers=256)  # Maximum number of simultaneous read transactions

            # Execute a transaction on the database
            with temp_env.begin() as txn:
                # perform a loop -> for index, item in decorated iterator over samples (from metadb)
                for index, item in tqdm.tqdm(enumerate(vals),  # Iterable to decorate with a progressbar
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
            pass  # NOP

        else:
            # assume remove_missing_features is a filepath

            # log info
            logger.info(f"Trying to load shas to ignore from {remove_missing_features}...")

            # open file in read mode
            with open(remove_missing_features, 'r') as f:
                shas_to_remove = json.load(f)  # deserialize from Json object to python object
            shas_to_remove = set(shas_to_remove)  # create a set from list (duplicate values will be ignored)

            # remove from vals all the items that are in indexes_to_remove set
            vals = [value for value in vals if value[retrieve_ind['sha256']] not in shas_to_remove]

            # log info
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

        return len(self.keylist)  # return the total number of samples

    def __getitem__(self,
                    index):  # index of the item to get

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


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
