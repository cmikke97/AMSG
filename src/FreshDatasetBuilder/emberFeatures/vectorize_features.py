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

import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
from multiprocessing.pool import ThreadPool  # pool of worker threads jobs can be submitted to

import numpy as np  # the fundamental package for scientific computing with Python
from logzero import logger  # robust and effective logging for Python
from tqdm import tqdm  # instantly makes loops show a smart progress meter

from .features import PEFeatureExtractor


def features_postproc_func(x):  # data point to apply the post processing function to
    """ Features post-processing function.

    Args:
        x: Data point to apply the post processing function to
    Returns:
        x.
    """

    x = np.asarray(x, dtype=np.float32)  # Convert the input (x) to a numpy array of float32
    lz = x < 0  # create a numpy array of boolean -> lz[i] is true when x[i] < 0
    gz = x > 0  # create a numpy array of boolean -> lz[i] is true when x[i] > 0
    x[lz] = - np.log(1 - x[lz])  # if lz[i] is true -> assign x[i] = -np.log(1-x[i])
    x[gz] = np.log(1 + x[gz])  # if gz[i] is true -> assign x[i] = np.log(1+x[i])

    return x


def raw_feature_iterator(file_paths):  # list of files to read, one line at a time
    """ Yield raw feature strings from the inputed file paths.

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
    """ Vectorize a single sample of raw features and write to a large numpy file.

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
    feature_vector = features_postproc_func(extractor.process_raw_features(raw_features))

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
    """ Pass through function for unpacking vectorize arguments.

    Args
        args: Vectorization arguments
    Returns:
        The return value of function vectorize (nothing).
    """

    # vectorize one single raw feature object (inside args)
    return vectorize(*args)


def vectorize_subset(X_path,  # features vector destination filename
                     y_path,  # labels vector destination filename
                     S_path,  # shas vector destination filename
                     raw_feature_paths,  # list of files where to look for raw features
                     extractor,  # PEFeatureExtractor instance
                     nrows):  # total number of rows in raw features files
    """ Vectorize a subset of data and write it to disk.

    Args:
        X_path: Features vector destination filename
        y_path: Labels vector destination filename
        S_path: Shas vector destination filename
        raw_feature_paths: List of files where to look for raw features
        extractor: PEFeatureExtractor instance
        nrows: Total number of rows in raw features files
    """

    # Create space on disk to write features, labels and shas to
    X = np.memmap(X_path, dtype=np.float32, mode="w+", shape=(nrows, extractor.dim))
    y = np.memmap(y_path, dtype=np.float32, mode="w+", shape=nrows)
    S = np.memmap(S_path, dtype=np.dtype('U64'), mode="w+", shape=nrows)
    # delete X, y and S vectors-> this will flush the memmap instance writing the changes to the files
    del X, y, S

    # Instantiate thread pool to distribute the vectorization work
    pool = ThreadPool()
    # instantiate vectorization arguments iterator getting raw features (and row indexes) from files
    argument_iterator = ((irow, raw_features_string, X_path, y_path, S_path, extractor, nrows)
                         for irow, raw_features_string in enumerate(raw_feature_iterator(raw_feature_paths)))
    # instantiate progress bar and launch parallel vectorization processes
    for _ in tqdm(pool.imap_unordered(vectorize_unpack, argument_iterator), total=nrows):
        pass  # nop

    # close and terminate thread pool
    pool.close()
    pool.terminate()


def create_vectorized_features(dataset_dest_dir,  # dir where to find the raw features and where to write the dataset
                               raw_features_paths,  # list of all files containing raw features
                               feature_version=2):  # Ember features version
    """ Create feature vectors from raw features and write them to disk.

    Args:
        dataset_dest_dir: Dir where to find the raw features and where to write the dataset
        raw_features_paths: List of all files containing raw features
        feature_version: Ember features version (default: 2)
    """

    # instantiate PE feature extractor
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=False)

    logger.info("Vectorizing training set..")
    # generate X (features vector), y (labels vector) and S (shas) file names
    X_path = os.path.join(dataset_dest_dir, "X_fresh.dat")
    y_path = os.path.join(dataset_dest_dir, "y_fresh.dat")
    S_path = os.path.join(dataset_dest_dir, "S_fresh.dat")

    # compute total number of lines inside the files
    nrows = sum([1 for fp in raw_features_paths for line in open(fp)])
    # vectorize raw features
    vectorize_subset(X_path, y_path, S_path, raw_features_paths, extractor, nrows)
