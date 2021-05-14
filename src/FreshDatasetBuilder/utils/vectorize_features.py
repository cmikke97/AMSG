import json  # JSON encoder and decoder
import multiprocessing  # supports spawning processes using an API similar to the threading module
import os  # Provides a portable way of using operating system dependent functionality

import numpy as np  # The fundamental package for scientific computing with Python
from logzero import logger  # Robust and effective logging for Python
from tqdm import tqdm  # Instantly makes loops show a smart progress meter

from .features import PEFeatureExtractor  # Import PEFeatureExtractor from features.py


def raw_feature_iterator(file_paths):  # list of files to read, one line at a time
    """ Yield raw feature strings from the inputed file paths

    Args:
        file_paths:  List of files to read, one line at a time
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
              S_path,  # shas vector destination filename
              extractor,  # PEFeatureExtractor instance
              nrows):  # total number of rows in raw features files
    """ Vectorize a single sample of raw features and write to a large numpy file

    Args:
        irow: Raw feature index
        raw_features_string: Raw feature string
        X_path: Features vector destination filename
        y_path: Labels vector destination filename
        S_path: Shas vector destination filename
        extractor: PEFeatureExtractor instance
    nrows: Total number of rows in raw features files
    """

    # deserialize json object to Python object
    raw_features = json.loads(raw_features_string)
    # get feature vector from raw feature object (using PE extractor)
    feature_vector = extractor.process_raw_features(raw_features)

    # open S memory map in Read+ mode
    S = np.memmap(S_path, dtype=np.dtype('U64'), mode="r+", shape=(nrows,))
    # save current sha as S's irow-th element
    S[irow] = raw_features['sha256']

    # open y memory map in Read+ mode
    y = np.memmap(y_path, dtype=np.float32, mode="r+", shape=(nrows,))
    # save current label as y's irow-th element
    y[irow] = raw_features['label']

    # open X memory map in Read+ mode
    X = np.memmap(X_path, dtype=np.float32, mode="r+", shape=(nrows, extractor.dim))
    # save current feature vector as X's irow-th element
    X[irow] = feature_vector


def vectorize_unpack(args):  # vectorization arguments
    """ Pass through function for unpacking vectorize arguments

    :param args: Vectorization arguments
    """

    # vectorize one single raw feature object (inside args)
    return vectorize(*args)


def vectorize_subset(X_path,  # features vector destination filename
                     y_path,  # labels vector destination filename
                     S_path,  # shas vector destination filename
                     raw_feature_paths,  # list of files where to look for raw features
                     extractor,  # PEFeatureExtractor instance
                     nrows):  # total number of rows in raw features files
    """ Vectorize a subset of data and write it to disk

    :param X_path: Features vector destination filename
    :param y_path: Labels vector destination filename
    :param S_path: Shas vector destination filename
    :param raw_feature_paths: List of files where to look for raw features
    :param extractor: PEFeatureExtractor instance
    :param nrows: Total number of rows in raw features files
    """
    # Create space on disk to write features, labels and shas to
    X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(nrows, extractor.dim))
    y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=nrows)
    S = np.memmap(S_path, dtype=np.dtype('U64'), mode="w+", shape=nrows)
    # delete X, y and S vectors-> this will flush the memmap instance writing the changes to the files
    del X, y, S

    # Instantiate process pool to distribute the vectorization work
    pool = multiprocessing.Pool()
    # instantiate vectorization arguments iterator getting raw features (and row indexes) from files
    argument_iterator = ((irow, raw_features_string, X_path, y_path, S_path, extractor, nrows)
                         for irow, raw_features_string in enumerate(raw_feature_iterator(raw_feature_paths)))
    # instantiate progress bar and launch parallel vectorization processes
    for _ in tqdm(pool.imap_unordered(vectorize_unpack, argument_iterator), total=nrows):
        pass  # nop


def create_vectorized_features(dataset_dest_dir,  # dir where to find the raw features and where to write the dataset
                               feature_version=2):  # Ember features version
    """ Create feature vectors from raw features and write them to disk

    :param dataset_dest_dir: Dir where to find the raw features and where to write the dataset
    :param feature_version: Ember features version (default: 2)
    """

    # instantiate PE feature extractor
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=False)

    logger.info("Vectorizing training set..")
    # generate X (features vector), y (labels vector) and S (shas) file names
    X_path = os.path.join(dataset_dest_dir, "X_fresh.dat")
    y_path = os.path.join(dataset_dest_dir, "y_fresh.dat")
    S_path = os.path.join(dataset_dest_dir, "S_fresh.dat")

    # get list of all files inside data directory
    raw_feature_paths = [os.path.join(dataset_dest_dir, fp) for fp in os.listdir(dataset_dest_dir)
                         if os.path.isfile(os.path.join(dataset_dest_dir, fp))
                         and os.path.splitext(fp)[-1].lower() == '.json']

    # compute total number of lines inside the files
    nrows = sum([1 for fp in raw_feature_paths for line in open(fp)])
    # vectorize raw features
    vectorize_subset(X_path, y_path, S_path, raw_feature_paths, extractor, nrows)
