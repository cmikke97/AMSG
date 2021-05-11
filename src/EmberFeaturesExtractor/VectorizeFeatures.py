import json  # JSON encoder and decoder
import multiprocessing
import os  # Provides a portable way of using operating system dependent functionality

import numpy as np  # The fundamental package for scientific computing with Python
from tqdm import tqdm

from features import PEFeatureExtractor  # Import PEFeatureExtractor from features.py


def raw_feature_iterator(file_paths):
    """
    Yield raw feature strings from the inputed file paths

    :param file_paths:
    """
    for path in file_paths:
        with open(path, "r") as fin:
            for line in fin:
                yield line


def vectorize(irow,
              raw_features_string,
              X_path,
              y_path,
              extractor,
              nrows):
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


def vectorize_unpack(args):
    """
    Pass through function for unpacking vectorize arguments

    :param args:
    """
    return vectorize(*args)


def vectorize_subset(X_path,
                     y_path,
                     raw_feature_paths,
                     extractor,
                     nrows):
    """
    Vectorize a subset of data and write it to disk

    :param X_path:
    :param y_path:
    :param raw_feature_paths:
    :param extractor:
    :param nrows:
    """
    # Create space on disk to write features to
    X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(nrows, extractor.dim))
    y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=nrows)
    del X, y

    # Distribute the vectorization work
    pool = multiprocessing.Pool()
    argument_iterator = ((irow, raw_features_string, X_path, y_path, extractor, nrows)
                         for irow, raw_features_string in enumerate(raw_feature_iterator(raw_feature_paths)))
    for _ in tqdm.tqdm(pool.imap_unordered(vectorize_unpack, argument_iterator), total=nrows):
        pass


def create_vectorized_features(data_dir,
                               feature_version=2):
    """
    Create feature vectors from raw features and write them to disk

    :param data_dir:
    :param feature_version:
    """
    extractor = PEFeatureExtractor(feature_version)

    print("Vectorizing training set")
    X_path = os.path.join(data_dir, "X_train.dat")
    y_path = os.path.join(data_dir, "y_train.dat")
    raw_feature_paths = [os.path.join(data_dir, "train_features_{}.jsonl".format(i)) for i in range(6)]
    nrows = sum([1 for fp in raw_feature_paths for line in open(fp)])
    vectorize_subset(X_path, y_path, raw_feature_paths, extractor, nrows)

    print("Vectorizing test set")
    X_path = os.path.join(data_dir, "X_test.dat")
    y_path = os.path.join(data_dir, "y_test.dat")
    raw_feature_paths = [os.path.join(data_dir, "test_features.jsonl")]
    nrows = sum([1 for fp in raw_feature_paths for line in open(fp)])
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