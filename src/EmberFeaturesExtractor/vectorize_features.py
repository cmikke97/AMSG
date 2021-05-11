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


def vectorize(irow,  # raw feature index
              raw_features_string,  # raw feature string
              X_path,  # features vector destination filename
              y_path,  # labels vector destination filename
              extractor,  # PEFeatureExtractor instance
              nrows):  # total number of rows in raw features files
    """
    Vectorize a single sample of raw features and write to a large numpy file

    :param irow: Raw feature index
    :param raw_features_string: Raw feature string
    :param X_path: Features vector destination filename
    :param y_path: Labels vector destination filename
    :param extractor: PEFeatureExtractor instance
    :param nrows: Total number of rows in raw features files
    """

    # deserialize json object to Python object
    raw_features = json.loads(raw_features_string)
    # get feature vector from raw feature object (using PE extractor)
    feature_vector = extractor.process_raw_features(raw_features)

    # open y memory map in Read+ mode
    y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=nrows)
    # save current label as y's irow-th element
    y[irow] = raw_features["label"]

    # open X memory map in Read+ mode
    X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(nrows, extractor.dim))
    # save current feature vector as X's irow-th element
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


def read_vectorized_features(fresh_dataset_dir,  # directory where to find the fresh dataset
                             feature_version=2):  # Ember features version
    """
    Read vectorized features into memory mapped numpy arrays

    :param fresh_dataset_dir: Directory where to find the fresh dataset
    :param feature_version: Ember features version
    """

    # instantiate PE feature extractor
    extractor = PEFeatureExtractor(feature_version)
    # get feature dimension from extractor
    ndim = extractor.dim

    # generate X (features vector) and y (labels vector) file names
    X_test_path = os.path.join(fresh_dataset_dir, "X_fresh.dat")
    y_test_path = os.path.join(fresh_dataset_dir, "y_fresh.dat")
    # open y (labels) memory map in Read mode
    y = np.memmap(y_test_path, dtype=np.float32, mode="r")
    # get number of elements from y vector
    N = y.shape[0]
    # open X (features) memory map in Read mode
    X = np.memmap(X_test_path, dtype=np.float32, mode="r", shape=(N, ndim))

    # return features and labels vectors
    return X, y
