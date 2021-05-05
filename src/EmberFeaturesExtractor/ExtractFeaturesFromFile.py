import json  # JSON encoder and decoder
import os  # Provides a portable way of using operating system dependent functionality

import baker  # Easy, powerful access to Python functions from the command line
import numpy as np  # The fundamental package for scientific computing with Python
from logzero import logger  # Robust and effective logging for Python

from features import PEFeatureExtractor


@baker.command
def extract_features_from_pe(binary_path,  # path to the PE file
                             raw_features_dest_file,  # where to write raw features
                             feature_version=2,  # EMBER feature version
                             print_warnings=False,  # whether to print warnings or not
                             ):
    """
    Extract EMBER features from PE file

    :param binary_path: Path to the PE file
    :param raw_features_dest_file: where to write raw features
    :param feature_version: EMBER feature version (default=2)
    :param print_warnings: whether to print warnings or not (default=False)
    """

    if not os.path.exists(binary_path):
        logger.error("{} does not exist".format(binary_path))
        return

    logger.info("Opening file {}".format(binary_path))
    file_data = open(binary_path, "rb").read()

    logger.info("Extracting features")
    extractor = PEFeatureExtractor(feature_version, print_feature_warning=print_warnings)

    raw_features = extractor.raw_features(file_data)
    raw_features_json = json.dumps(raw_features)

    with open(raw_features_dest_file, "a") as raw_file:
        raw_file.write(raw_features_json)

    features = np.array(extractor.feature_vector(file_data), dtype=np.float32)

    logger.info("Feature vector")
    print(features)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
