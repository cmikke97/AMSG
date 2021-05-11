import json  # JSON encoder and decoder
import multiprocessing
import os  # Provides a portable way of using operating system dependent functionality

import numpy as np  # The fundamental package for scientific computing with Python
from tqdm import tqdm

from features import PEFeatureExtractor  # Import PEFeatureExtractor from features.py
from logzero import logger


def raw_feature_iterator(file_paths):  # list of files to read, one line at a time
    """
    Yield raw feature strings from the inputed file paths

    :param file_paths:  List of files to read, one line at a time
    """
    # for all filenames in file paths list
    for path in file_paths:
        # open file in Read mode
        with open(path, "r") as fin:
            # yield each line
            for line in fin:
                yield line


def vectorize(irow,  #
              raw_features_string,  #
              X_path,  #
              y_path,  #
              extractor,  #
              nrows):  #
    """
    Vectorize a single sample of raw features and write to a large numpy file

    :param irow:
    :param raw_features_string:
    :param X_path:
    :param y_path:
    :param extractor:
    :param nrows:
    """
    raw_features = json.loads(raw_features_string)
    feature_vector = extractor.process_raw_features(raw_features)

    y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=nrows)
    y[irow] = raw_features["label"]

    X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(nrows, extractor.dim))
    X[irow] = feature_vector


def vectorize_unpack(args):  # vectorization arguments
    """
    Pass through function for unpacking vectorize arguments

    :param args: Vectorization arguments
    """

    # vectorize one single raw feature object (inside args)
    return vectorize(*args)


def vectorize_subset(X_path,  # features vector destination filename
                     y_path,  # labels vector destination filename
                     raw_feature_paths,  # list of files where to look for raw features
                     extractor,  # PEFeatureExtractor instance
                     nrows):  # total number of rows in raw features files
    """
    Vectorize a subset of data and write it to disk

    :param X_path: Features vector destination filename
    :param y_path: Labels vector destination filename
    :param raw_feature_paths: List of files where to look for raw features
    :param extractor: PEFeatureExtractor instance
    :param nrows: Total number of rows in raw features files
    """
    # Create space on disk to write features (and labels) to
    X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(nrows, extractor.dim))
    y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=nrows)
    # delete X and y vectors, we do not need them now -> this will flush the memmap instance writing the changes
    # to the file
    del X, y

    # Instantiate process pool to distribute the vectorization work
    pool = multiprocessing.Pool()
    # instantiate vectorization arguments iterator getting raw features (and row indexes) from files
    argument_iterator = ((irow, raw_features_string, X_path, y_path, extractor, nrows)
                         for irow, raw_features_string in enumerate(raw_feature_iterator(raw_feature_paths)))
    # instantiate progress bar and launch parallel vectorization processes
    for _ in tqdm(pool.imap_unordered(vectorize_unpack, argument_iterator), total=nrows):
        pass  # nop


def create_vectorized_features(fresh_dataset_dir,  # directory where to find the fresh (raw) dataset
                               feature_version=2):  # Ember features version
    """
    Create feature vectors from raw features and write them to disk

    :param fresh_dataset_dir: Directory where to find the fresh (raw) dataset
    :param feature_version: Ember features version (default: 2)
    """

    # instantiate PE feature extractor
    extractor = PEFeatureExtractor(feature_version)

    logger.info("Vectorizing training set")
    # generate X (features vector) and y (labels vector) file names
    X_path = os.path.join(fresh_dataset_dir, "X_fresh.dat")
    y_path = os.path.join(fresh_dataset_dir, "y_fresh.dat")
    # get list of all files inside data directory
    raw_feature_paths = [os.path.join(fresh_dataset_dir, fp) for fp in os.listdir(fresh_dataset_dir)
                         if os.path.isfile(os.path.join(fresh_dataset_dir, fp))]
    # compute total number of lines inside the files
    nrows = sum([1 for fp in raw_feature_paths for line in open(fp)])
    # vectorize raw features
    vectorize_subset(X_path, y_path, raw_feature_paths, extractor, nrows)


def read_vectorized_features(data_dir,
                             subset=None,
                             feature_version=2):
    """
    Read vectorized features into memory mapped numpy arrays

    :param data_dir:
    :param subset:
    :param feature_version:
    """
    if subset is not None and subset not in ["train", "test"]:
        return None

    extractor = PEFeatureExtractor(feature_version)
    ndim = extractor.dim
    X_train = None
    y_train = None
    X_test = None
    y_test = None

    if subset is None or subset == "train":
        X_train_path = os.path.join(data_dir, "X_train.dat")
        y_train_path = os.path.join(data_dir, "y_train.dat")
        y_train = np.memmap(y_train_path, dtype=np.float32, mode="r")
        N = y_train.shape[0]
        X_train = np.memmap(X_train_path, dtype=np.float32, mode="r", shape=(N, ndim))
        if subset == "train":
            return X_train, y_train

    if subset is None or subset == "test":
        X_test_path = os.path.join(data_dir, "X_test.dat")
        y_test_path = os.path.join(data_dir, "y_test.dat")
        y_test = np.memmap(y_test_path, dtype=np.float32, mode="r")
        N = y_test.shape[0]
        X_test = np.memmap(X_test_path, dtype=np.float32, mode="r", shape=(N, ndim))
        if subset == "test":
            return X_test, y_test

    return X_train, y_train, X_test, y_test
